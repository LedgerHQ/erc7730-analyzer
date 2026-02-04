# ERC-7730 Clear Signing Analyzer

AI-powered security auditor for ERC-7730 clear signing metadata files. Validates that transaction descriptors accurately represent what smart contracts actually do.

## Overview

ERC-7730 defines how wallets display human-readable transaction information. A malicious or incorrect descriptor could mislead users into signing harmful transactions. This tool:

1. Fetches real transactions from the blockchain
2. Analyzes smart contract source code
3. Compares what the descriptor shows vs. what actually happens
4. Generates audit reports with critical issues and recommendations

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  ERC-7730 File  │     │   Etherscan     │     │    OpenAI       │
│  (calldata.json)│     │   (ABI + Txs)   │     │   (Analysis)    │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 ▼
                    ┌────────────────────────┐
                    │   ERC-7730 Analyzer    │
                    │  • Decode transactions │
                    │  • Extract source code │
                    │  • AI audit per func   │
                    └────────────┬───────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │   Audit Reports        │
                    │  • CRITICALS_*.md      │
                    │  • SUMMARY_*.md        │
                    └────────────────────────┘
```

## Key Features

| Feature | Description |
|---------|-------------|
| **Critical Issue Detection** | Identifies parameters hidden from users that could enable attacks |
| **Source Code Analysis** | Extracts and analyzes relevant contract functions |
| **Real Transaction Validation** | Uses actual on-chain transactions, not just static analysis |
| **Spec Limitation Warnings** | Flags parameters that ERC-7730 cannot properly display |
| **Actionable Fixes** | Provides JSON snippets to fix identified issues |

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- API keys: Etherscan, OpenAI

### Installation

```bash
# Clone the repository
git clone https://github.com/example/erc7730-analyzer.git
cd erc7730-analyzer

# Install dependencies
uv sync

# Configure API keys
cp .env.example .env
# Edit .env with your API keys
```

### Usage

```bash
# Analyze an ERC-7730 file
uv run analyze_7730 --erc7730_file path/to/calldata.json

# With debug output
uv run analyze_7730 --erc7730_file path/to/calldata.json --debug

# Custom lookback period (days)
uv run analyze_7730 --erc7730_file path/to/calldata.json --lookback-days 30
```

Reports are saved to `./output/`:
- `CRITICALS_*.md` - Critical issues requiring immediate attention
- `SUMMARY_*.md` - Full analysis with all findings

### Docker

```bash
# Build
docker build -t erc7730-analyzer .

# Run
docker run --rm \
  -v $(pwd)/.env:/app/.env \
  -v $(pwd)/your-calldata.json:/app/calldata.json \
  -v $(pwd)/output:/app/output \
  erc7730-analyzer --erc7730_file calldata.json
```

## Configuration

Environment variables (set in `.env` or pass directly):

| Variable | Required | Description |
|----------|----------|-------------|
| `ETHERSCAN_API_KEY` | Yes | For fetching ABI and transactions |
| `OPENAI_API_KEY` | Yes | For AI-powered analysis |
| `COREDAO_API_KEY` | No | For Core DAO chain (1116) |
| `LOOKBACK_DAYS` | No | Transaction lookback period (default: 20) |

## Example Output

The analyzer produces reports highlighting:

- **Critical Issues**: Hidden parameters, misleading labels, missing approvals
- **Missing Parameters**: ABI parameters not shown to users
- **Display Issues**: UX problems like missing units or unclear formatting
- **Recommendations**: Specific JSON fixes with code snippets

## Project Structure

```
erc7730-analyzer/
├── src/
│   ├── main.py              # CLI entry point
│   └── utils/
│       ├── analyzer.py      # Core analysis logic
│       ├── abi.py           # ABI fetching and parsing
│       ├── source_code.py   # Contract source extraction
│       ├── transactions.py  # Transaction fetching
│       ├── prompts.py       # AI prompt templates
│       ├── reporter.py      # Report generation
│       └── audit_rules/     # Static analysis rules
├── specs/                   # ERC-7730 specification
├── Dockerfile
└── pyproject.toml
```

## License

MIT License - see LICENSE file for details.
