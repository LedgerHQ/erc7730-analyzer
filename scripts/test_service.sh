#!/usr/bin/env bash
# ============================================================================
# Local CI simulation for the analyzer service.
#
# Mimics the full GitHub Actions flow:
#   1. (optionally) Start a mock OIDC provider
#   2. Start the analyzer service
#   3. Run the client against it — same flags the CI workflow uses
#   4. Check exit code + reports
#
# Usage:
#   ./scripts/test_service.sh                                  # dev mode (no auth)
#   ./scripts/test_service.sh --oidc                           # full OIDC auth flow
#   ./scripts/test_service.sh --oidc path/to/descriptor.json   # custom file + OIDC
#   ANALYSIS_MODE=multi ./scripts/test_service.sh              # env overrides
#
# Prerequisites:
#   - .env file with ETHERSCAN_API_KEY, OPENAI_API_KEY
#   - `uv sync` already run
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SRC_DIR="$PROJECT_ROOT/src"

# --- Colours ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# --- Parse flags ---
USE_OIDC=false
DESCRIPTOR=""

for arg in "$@"; do
    case "$arg" in
        --oidc) USE_OIDC=true ;;
        *)      DESCRIPTOR="$arg" ;;
    esac
done

# --- Configurable via env ---
DESCRIPTOR="${DESCRIPTOR:-$PROJECT_ROOT/testing/registry/uniswap/calldata-UniswapV3Router02.json}"
SERVICE_PORT="${SERVICE_PORT:-8730}"
MOCK_OIDC_PORT="${MOCK_OIDC_PORT:-8740}"
HOST="${SERVICE_HOST:-127.0.0.1}"
ANALYSIS_MODE="${ANALYSIS_MODE:-single}"
ENABLE_SCREENSHOTS="${ENABLE_SCREENSHOTS:-false}"
MODEL="${MODEL:-}"
REASONING_EFFORT="${REASONING_EFFORT:-}"
LOOKBACK_DAYS="${LOOKBACK_DAYS:-20}"

SERVICE_URL="http://${HOST}:${SERVICE_PORT}"
MOCK_OIDC_URL="http://${HOST}:${MOCK_OIDC_PORT}"

SERVICE_PID=""
MOCK_OIDC_PID=""

cleanup() {
    for pid_var in SERVICE_PID MOCK_OIDC_PID; do
        pid="${!pid_var}"
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            echo -e "${YELLOW}Stopping $pid_var (pid=$pid)...${NC}"
            kill "$pid" 2>/dev/null || true
            wait "$pid" 2>/dev/null || true
        fi
    done
}
trap cleanup EXIT

# ====================================================================
# Step 0 (optional): Start mock OIDC provider
# ====================================================================
if [ "$USE_OIDC" = true ]; then
    echo -e "${CYAN}=== Step 0: Starting mock OIDC provider ===${NC}"
    echo -e "  Port: $MOCK_OIDC_PORT"
    echo -e "  Issuer: $MOCK_OIDC_URL"
    echo ""

    python3 "$SCRIPT_DIR/mock_oidc.py" --host "$HOST" --port "$MOCK_OIDC_PORT" &
    MOCK_OIDC_PID=$!
    sleep 1

    # Verify JWKS endpoint
    echo -n "  Checking JWKS..."
    if curl -sf "${MOCK_OIDC_URL}/.well-known/jwks" > /dev/null 2>&1; then
        echo -e " ${GREEN}ok${NC}"
    else
        echo -e " ${RED}FAILED${NC}"
        exit 1
    fi

    # Verify token endpoint
    echo -n "  Minting test token..."
    TEST_TOKEN=$(curl -sf "${MOCK_OIDC_URL}/token?audience=erc7730-analyzer" | python3 -c "import sys,json; print(json.load(sys.stdin)['value'])")
    if [ -n "$TEST_TOKEN" ]; then
        echo -e " ${GREEN}ok${NC} (${#TEST_TOKEN} chars)"
    else
        echo -e " ${RED}FAILED${NC}"
        exit 1
    fi
    echo ""
fi

# ====================================================================
# Step 1: Start analyzer service
# ====================================================================
echo -e "${CYAN}=== Step 1: Starting analyzer service ===${NC}"

if [ "$USE_OIDC" = true ]; then
    echo -e "  Mode: ${YELLOW}PRODUCTION (OIDC verification ON)${NC}"
    echo -e "  OIDC issuer: $MOCK_OIDC_URL"
    cd "$SRC_DIR"
    OIDC_ISSUER_URL="$MOCK_OIDC_URL" \
    ALLOWED_REPOS="LedgerHQ/clear-signing-erc7730-registry" \
    python -m service.app --host "$HOST" --port "$SERVICE_PORT" &
    SERVICE_PID=$!
else
    echo -e "  Mode: ${GREEN}DEV (no auth)${NC}"
    cd "$SRC_DIR"
    SERVICE_DEV_MODE=true python -m service.app --dev --host "$HOST" --port "$SERVICE_PORT" &
    SERVICE_PID=$!
fi

echo -e "  Port: $SERVICE_PORT"
echo -e "  Descriptor: $DESCRIPTOR"
echo ""

# Wait for health endpoint
echo -n "  Waiting for service..."
for i in $(seq 1 30); do
    if curl -sf "${SERVICE_URL}/health" > /dev/null 2>&1; then
        echo -e " ${GREEN}ready${NC}"
        break
    fi
    if ! kill -0 "$SERVICE_PID" 2>/dev/null; then
        echo -e " ${RED}FAILED (service exited)${NC}"
        exit 1
    fi
    echo -n "."
    sleep 1
done

HEALTH=$(curl -sf "${SERVICE_URL}/health" 2>/dev/null || echo '{}')
echo -e "  Health: $HEALTH"
echo ""

# ====================================================================
# Step 2: Run client (mimics CI)
# ====================================================================
echo -e "${CYAN}=== Step 2: Running client (CI simulation) ===${NC}"

CLIENT_ARGS=(
    --service-url "$SERVICE_URL"
    --descriptor "$DESCRIPTOR"
    --analysis-mode "$ANALYSIS_MODE"
    --lookback-days "$LOOKBACK_DAYS"
)

if [ "$USE_OIDC" = true ]; then
    # Client will acquire OIDC token from the mock provider
    export ACTIONS_ID_TOKEN_REQUEST_URL="${MOCK_OIDC_URL}/token"
    export ACTIONS_ID_TOKEN_REQUEST_TOKEN="mock"
    echo -e "  Auth: ${YELLOW}OIDC (via mock at $MOCK_OIDC_URL)${NC}"
else
    CLIENT_ARGS+=(--no-oidc)
    echo -e "  Auth: ${GREEN}skipped (dev mode)${NC}"
fi

if [ "$ENABLE_SCREENSHOTS" = "true" ]; then
    CLIENT_ARGS+=(--enable-screenshots)
fi
if [ -n "$MODEL" ]; then
    CLIENT_ARGS+=(--model "$MODEL")
fi
if [ -n "$REASONING_EFFORT" ]; then
    CLIENT_ARGS+=(--reasoning-effort "$REASONING_EFFORT")
fi

echo -e "  Command: python -m service.client ${CLIENT_ARGS[*]}"
echo ""

set +e
cd "$SRC_DIR"
python -m service.client "${CLIENT_ARGS[@]}"
CLIENT_EXIT=$?
set -e

echo ""

# ====================================================================
# Step 3: Check results
# ====================================================================
echo -e "${CYAN}=== Step 3: Results ===${NC}"

if [ -d "$PROJECT_ROOT/output" ]; then
    echo -e "  Reports generated:"
    ls -la "$PROJECT_ROOT/output"/*.md 2>/dev/null || echo "  (no .md reports)"
    ls -la "$PROJECT_ROOT/output"/*.json 2>/dev/null || echo "  (no .json results)"
fi

echo ""
if [ $CLIENT_EXIT -eq 0 ]; then
    echo -e "  ${GREEN}EXIT CODE: 0 — No critical issues (CI would PASS)${NC}"
else
    echo -e "  ${RED}EXIT CODE: $CLIENT_EXIT — Critical issues found (CI would FAIL / block merge)${NC}"
fi

if [ "$USE_OIDC" = true ]; then
    echo ""
    echo -e "  ${CYAN}OIDC flow tested end-to-end:${NC}"
    echo -e "    mock issuer → JWT minted → client sent Bearer token → service verified via JWKS"
fi

exit $CLIENT_EXIT
