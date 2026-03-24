#!/usr/bin/env bash
# ===========================================================================
# Entrypoint for the ERC-7730 Analyzer container.
#
# Modes:
#   service  — Start the FastAPI service (default)
#   cli      — Run the analyzer CLI directly
#   *        — Rejected with error
#
# Secrets are expected via environment variables.  In production (AWS),
# they come from Secrets Manager injected into the App Runner env.
# Locally, use --env-file .env.
# ===========================================================================
set -euo pipefail

# --- Unpack Snowflake credentials JSON blob (set by App Runner from SM) ---
if [ -n "${SNOWFLAKE_CREDENTIALS_JSON:-}" ]; then
  _sf_val() { jq -r --arg k "$1" '.[$k] // empty' <<< "${SNOWFLAKE_CREDENTIALS_JSON}" 2>/dev/null; }
  export SNOWFLAKE_USER="${SNOWFLAKE_USER:-$(_sf_val user)}"
  export SNOWFLAKE_INSTANCE="${SNOWFLAKE_INSTANCE:-$(_sf_val instance)}"
  export SNOWFLAKE_WAREHOUSE="${SNOWFLAKE_WAREHOUSE:-$(_sf_val warehouse)}"
  export SNOWFLAKE_ROLE="${SNOWFLAKE_ROLE:-$(_sf_val role)}"
  export SNOWFLAKE_PRIVATE_KEY="${SNOWFLAKE_PRIVATE_KEY:-$(_sf_val private_key)}"
  unset SNOWFLAKE_CREDENTIALS_JSON
  echo "[entrypoint] Unpacked Snowflake credentials from JSON blob"
fi

MODE="${1:-service}"
shift 2>/dev/null || true

case "$MODE" in
  service)
    echo "[entrypoint] Starting analyzer service on ${SERVICE_HOST:-0.0.0.0}:${SERVICE_PORT:-8080}"
    exec uv run --no-sync python -m service.app \
      --host "${SERVICE_HOST:-0.0.0.0}" \
      --port "${SERVICE_PORT:-8080}" \
      "$@"
    ;;

  cli)
    echo "[entrypoint] Running analyzer CLI"
    exec uv run --no-sync analyze_7730 "$@"
    ;;

  *)
    echo "[entrypoint] Unknown mode: $MODE — expected 'service' or 'cli'" >&2
    exit 1
    ;;
esac
