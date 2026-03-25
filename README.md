# ERC-7730 Clear Signing Analyzer

AI-powered security auditor for ERC-7730 clear signing descriptor files. Validates that transaction descriptors accurately represent what smart contracts actually do — and optionally captures Ledger device screenshots to verify on-device rendering.

## Overview

ERC-7730 defines how wallets display human-readable transaction information. A malicious or incorrect descriptor could mislead users into signing harmful transactions. This tool:

1. Parses the ERC-7730 descriptor and resolves its ABI / format definitions
2. Fetches real transactions from the blockchain (Snowflake, Etherscan, Blockscout, RPC)
3. Decodes calldata against the ABI and extracts contract source code
4. Optionally captures Ledger device screenshots via `clear-signing-tester` + Speculos
5. Sends everything to an LLM for per-selector security audit
6. Generates markdown reports with critical issues, recommendations, and screenshots

```
┌─────────────────┐     ┌──────────────────┐     ┌───────────────────────┐
│  ERC-7730 File  │     │  Data Sources    │     │  Ledger Screenshots   │
│  (descriptor)   │     │  Snowflake       │     │  cs-tester + Speculos │
│                 │     │  Etherscan       │     └───────────┬───────────┘
│                 │     │  Blockscout      │                 │
│                 │     │  JSON-RPC        │                 │
└────────┬────────┘     └────────┬─────────┘                 │
         │                       │                           │
         └───────────────────────┼───────────────────────────┘
                                 ▼
                  ┌──────────────────────────┐
                  │   Pipeline               │
                  │  • Decode transactions   │
                  │  • Extract source code   │
                  │  • Capture screenshots   │
                  └──────────────┬───────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                   ▼
   ┌──────────────────┐ ┌────────────────┐ ┌────────────────┐
   │ Primary Auditor  │ │   Validator    │ │    Reducer     │
   │ Drafts findings  │ │ Challenges the │ │ Merges into    │
   │ per selector     │ │ draft, requests│ │ final verdict  │
   │                  │ │ extra evidence │ │                │
   └────────┬─────────┘ └───────┬────────┘ └───────┬────────┘
            └────────────────────┼──────────────────┘
                                 ▼
                  ┌──────────────────────────┐
                  │   Audit Reports          │
                  │  • CRITICALS_*.md        │
                  │  • FULL_REPORT_*.md      │
                  │  • results_*.json        │
                  └──────────────────────────┘
```

### Multi-Agent Audit (multi mode)

Each selector is audited by a three-agent pipeline:

1. **Primary Auditor** — receives the selector packet (descriptor, decoded transactions, source code, screenshots) and produces a draft audit report. Can request tools (extra source code, ABI lookups) if evidence is missing.
2. **Validator** — skeptically challenges the primary draft. Looks for unsupported assumptions, overconfident severity, and missed issues. Can gather its own tool evidence.
3. **Reducer** — receives both reports plus all tool evidence and produces the final conservative verdict. If the validator fully agrees with the primary, the reducer is skipped.

In `single` mode, a single LLM call per selector replaces the three-agent flow.

## Key Features

| Feature | Description |
|---------|-------------|
| **Critical Issue Detection** | Identifies hidden or misleading parameters that could enable attacks |
| **Source Code Analysis** | Extracts and analyzes relevant contract functions |
| **Real Transaction Validation** | Decodes actual on-chain transactions, not just static analysis |
| **Ledger Screenshot Capture** | Renders transactions on emulated Ledger devices (Stax/Flex) |
| **Multi-Source Fetching** | Snowflake → Etherscan → Blockscout → RPC fallback chain |
| **Spec Limitation Warnings** | Flags parameters that ERC-7730 cannot properly display |
| **Actionable Fixes** | Provides JSON snippets to fix identified issues |

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- API keys: OpenAI, Etherscan

Optional (for screenshots):
- Docker (Speculos runs as a sibling container)
- `device-sdk-ts` with `clear-signing-tester` built
- Ethereum app ELF files for the target Ledger device

### Installation

```bash
git clone https://github.com/LedgerHQ/erc7730-analyzer.git
cd erc7730-analyzer

uv sync

cp .env.example .env
# Edit .env with your API keys
```

### Usage

```bash
# Basic analysis
uv run analyze_7730 --erc7730_file path/to/calldata.json

# With screenshots on Ledger Stax
uv run analyze_7730 --erc7730_file path/to/calldata.json --enable-screenshots

# Multi-agent mode (deeper analysis, more LLM rounds)
uv run analyze_7730 --erc7730_file path/to/calldata.json --analysis-mode multi

# Custom model and reasoning effort
uv run analyze_7730 --erc7730_file path/to/calldata.json --model gpt-5.4 --reasoning-effort high

# Debug logging
uv run analyze_7730 --erc7730_file path/to/calldata.json --debug
```

Reports are saved to `./output/`:
- `CRITICALS_<protocol>.md` — critical issues requiring immediate attention
- `FULL_REPORT_<protocol>.md` — comprehensive analysis with all findings
- `results_<protocol>.json` — raw structured results

## Configuration

### Environment Variables

Set in `.env` or pass directly:

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | LLM API key for analysis |
| `ETHERSCAN_API_KEY` | Yes | For fetching ABI, source code, and transactions |
| `COREDAO_API_KEY` | No | For Core DAO chain (1116) |
| `INFURA_RPC_KEY` | No | Infura project key for RPC fallback |
| `SNOWFLAKE_ENABLED` | No | Enable Snowflake as primary tx source (`true`/`false`) |
| `SNOWFLAKE_USER` | No | Snowflake authentication user |
| `SNOWFLAKE_INSTANCE` | No | Snowflake account identifier |
| `SNOWFLAKE_WAREHOUSE` | No | Snowflake warehouse name |
| `SNOWFLAKE_ROLE` | No | Snowflake role |
| `SNOWFLAKE_PRIVATE_KEY` | No | Snowflake RSA private key (PEM) |
| `ENABLE_SCREENSHOTS` | No | Capture Ledger device screenshots (`true`/`false`) |
| `CS_TESTER_ROOT` | No | Path to `device-sdk-ts` repo root |
| `ETH_APP_ELF_ROOT` | No | Path to directory containing Ethereum app ELF files |
| `LLM_MODEL` | No | Model name (default: `gpt-5.4-nano`) |
| `LLM_REASONING_EFFORT` | No | `low`, `medium`, or `high` (default: `low`) |
| `ANALYSIS_MODE` | No | `single` or `multi` (default: `single`) |
| `LOOKBACK_DAYS` | No | Transaction lookback period in days (default: `7`) |
| `MAX_CONCURRENT_API_CALLS` | No | Max concurrent internal API/model calls (default: `2`) |
| `MAX_SELECTOR_TOOL_ROUNDS` | No | Max multi-agent evidence-gathering rounds (default: `1`) |
| `MAX_TOOL_REQUESTS_PER_ROUND` | No | Max tool requests per multi-agent round (default: `1`) |

### CLI Arguments

All environment variables can be overridden via CLI flags. Run `uv run analyze_7730 --help` for the full list.

## Service API

The analyzer runs as a FastAPI service behind AWS App Runner. It exposes an
async polling API so analyses can run far longer than App Runner's 120-second
request timeout.

### `POST /analyze`

Start (or resume) an analysis. Returns immediately with a job handle.

- **Auth**: Bearer token (GitHub OIDC JWT). Skipped when `DISABLE_OIDC_AUTH=true`.
- **Body**: JSON matching `AnalyzeRequest` (required field: `descriptor`).
- **Idempotency**: when OIDC is enabled the job is keyed by
  `(repository, run_id, run_attempt)` from the JWT. Repeating the same POST
  returns the existing job instead of starting a duplicate.
- **Responses**:
  - `202 Accepted` — job created or still running.
  - `200 OK` — job already completed (result included).
  - `503 Service Unavailable` — another analysis is in progress.

### `GET /analyze`

Poll the status of a running analysis or retrieve the final result.

- **Auth**: same Bearer token. When OIDC is disabled, pass `?run_key=<key>`
  (the key returned by POST).
- **Responses**:
  - `202 Accepted` — job queued or running (includes `poll_after_seconds` hint
    and `recent_logs` tail).
  - `200 OK` — job succeeded (includes `protocol`, `has_criticals`,
    `summary_report`, `criticals_report`, `results_json`).
  - `404 Not Found` — no job for this run.

### Operational notes

| Aspect | Detail |
|--------|--------|
| **Job storage** | In-memory (transitional). Jobs are lost on restart, deploy, or crash. |
| **Concurrency** | One analysis at a time (`asyncio.Semaphore(1)`). |
| **Scaling** | App Runner pinned to `max_instances=1` while storage is in-memory. |
| **TTL** | Completed jobs are evicted after `JOB_RETENTION_TTL` seconds (default 3600). |
| **Timeout** | Background analysis times out after 45 minutes. |

### Service environment variables

In addition to the standard config variables listed above, the service accepts:

| Variable | Default | Description |
|----------|---------|-------------|
| `JOB_RETENTION_TTL` | `3600` | Seconds to retain completed jobs before eviction |
| `MAX_RETAINED_LOG_LINES` | `500` | Max log lines kept per job for progress polling |
| `POLL_INTERVAL_HINT` | `5` | Suggested poll interval returned to clients (seconds) |

## Project Structure

```
erc7730-analyzer/
├── src/
│   ├── main.py                    # CLI entry point
│   ├── service/                   # FastAPI service (API mode)
│   │   ├── app.py                 # POST/GET /analyze (async polling)
│   │   ├── auth.py                # GitHub OIDC auth + run-key derivation
│   │   ├── client.py              # Python client (POST + poll loop)
│   │   ├── config.py              # Service configuration
│   │   └── jobs.py                # In-memory job model and registry
│   └── utils/
│       ├── core/                  # Analysis pipeline orchestration
│       ├── abi/                   # ABI fetching and parsing
│       ├── extraction/            # Contract source code extraction
│       ├── clients/               # Transaction fetching (Snowflake, Etherscan, etc.)
│       ├── auditing/              # LLM audit logic (single + multi-agent)
│       ├── reporting/             # Markdown and JSON report generation
│       ├── screenshots/           # Ledger screenshot capture via cs-tester
│       ├── rpc_helpers.py         # JSON-RPC fallback utilities
│       └── audit_rules/           # Static analysis rule definitions (JSON)
├── tests/                         # pytest suite (auth, jobs, API contract)
├── docs/
│   └── DEPLOYMENT.md             # Deployment and local testing guide
├── testing/registry/              # Test descriptor files
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

## License

CC0 1.0 Universal — see LICENSE file for details.
