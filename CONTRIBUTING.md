# Contributing to ERC-7730 Clear Signing Analyzer

Thank you for your interest in contributing! This project helps secure the Ethereum ecosystem by auditing ERC-7730 clear signing metadata. Every contribution matters.

## Table of Contents

- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Submitting a Calldata File for Analysis](#submitting-a-calldata-file-for-analysis)
- [Contributing Code](#contributing-code)
- [Commit Convention](#commit-convention)
- [Pull Request Process](#pull-request-process)
- [Project Structure](#project-structure)
- [Reporting Issues](#reporting-issues)

## Getting Started

1. **Fork** the repository on GitHub
2. **Clone** your fork locally:
   ```bash
   git clone https://github.com/<your-username>/erc7730-analyzer.git
   cd erc7730-analyzer
   ```
3. **Add upstream** remote:
   ```bash
   git remote add upstream https://github.com/LedgerHQ/erc7730-analyzer.git
   ```

## Development Setup

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (recommended package manager)
- API keys: [Etherscan](https://etherscan.io/apis) and [OpenAI](https://platform.openai.com/api-keys)

### Install Dependencies

```bash
uv sync
```

### Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and fill in your API keys:

```
OPENAI_API_KEY=sk-...
ETHERSCAN_API_KEY=...
```

### Verify Setup

```bash
uv run analyze_7730 --erc7730_file path/to/calldata.json
```

### Docker (Alternative)

```bash
docker build -t erc7730-analyzer .
docker run --rm \
  -v $(pwd)/.env:/app/.env \
  -v $(pwd)/your-calldata.json:/app/calldata.json \
  -v $(pwd)/output:/app/output \
  erc7730-analyzer --erc7730_file calldata.json
```

## Submitting a Calldata File for Analysis

The most common contribution is submitting a new ERC-7730 calldata file for audit. The CI workflow will automatically analyze it.

1. Create a branch:
   ```bash
   git checkout -b analyze/<protocol-name>
   ```
2. Add your calldata file at the repo root, named `calldata-<ProtocolName>.json`
3. Open a PR against `main`
4. The **Analyze** workflow runs automatically on any `calldata-*.json` file in a PR
5. Check the workflow results for critical issues and recommendations

### Calldata File Format

The calldata JSON file must follow the [ERC-7730 specification](specs/erc-7730.md). At minimum it should contain:

- Contract address and chain ID
- Function selectors with display formatting
- Parameter descriptions and formatting rules

## Contributing Code

### Branching

- Branch from `main` for all changes
- Use descriptive branch names:
  - `feat/<description>` for new features
  - `fix/<description>` for bug fixes
  - `docs/<description>` for documentation
  - `refactor/<description>` for code restructuring

### Key Areas for Contribution

| Area | Path | Description |
|------|------|-------------|
| **Audit Rules** | `src/utils/audit_rules/` | Static analysis rules (JSON-based) |
| **Smart Rules** | `src/utils/auditing/smart_rules.py` | Dynamic analysis heuristics |
| **ABI Handling** | `src/utils/abi/` | ABI fetching, parsing, and merging |
| **Transaction Clients** | `src/utils/clients/` | Blockchain data fetching |
| **AI Prompts** | `src/utils/prompts.py` | Prompt engineering for the analysis |
| **Report Generation** | `src/utils/reporting/` | Markdown report formatting |

### Adding Audit Rules

Audit rules live in `src/utils/audit_rules/` as JSON files. To add a new rule:

1. Identify the appropriate category file (`critical_issues.json`, `display_issues.json`, `recommendations.json`, etc.)
2. Add your rule following the existing format
3. Test with a calldata file that would trigger the rule

## Commit Convention

This project uses **semantic commits with emoji prefixes**:

| Emoji | Type | Usage |
|-------|------|-------|
| `🎉 init:` | Initial | Project initialization |
| `✨ feat:` | Feature | New feature or capability |
| `🐛 fix:` | Fix | Bug fix |
| `📝 docs:` | Docs | Documentation changes |
| `💄 style:` | Style | Formatting, no code change |
| `♻️ refactor:` | Refactor | Code restructuring |
| `✅ test:` | Test | Adding or updating tests |
| `👷 ci:` | CI | CI/CD workflow changes |
| `⬆️ deps:` | Deps | Dependency updates |
| `🐳 docker:` | Docker | Docker-related changes |
| `🔧 chore:` | Chore | Maintenance tasks |

**Examples:**
```
✨ feat: add support for Polygon chain transactions
🐛 fix: handle missing ABI gracefully for proxy contracts
📝 docs: add examples for custom audit rules
⬆️ deps: bump openai from 1.0.0 to 1.5.0
```

## Pull Request Process

1. **Keep PRs focused** -- one feature or fix per PR
2. **Update documentation** if your change affects usage or configuration
3. **Write clear PR descriptions** explaining what and why
4. **Ensure the CI passes** -- the Analyze workflow must complete successfully for calldata PRs
5. **Be responsive** to review feedback

### PR Title Format

Use the same semantic commit format for PR titles:
```
✨ feat: add Base chain support for transaction fetching
```

## Project Structure

```
erc7730-analyzer/
├── src/
│   ├── main.py                  # CLI entry point
│   └── utils/
│       ├── abi/                 # ABI fetching, parsing, merging
│       ├── audit_rules/         # Static analysis rules (JSON)
│       ├── auditing/            # Audit engine and smart rules
│       ├── clients/             # Blockchain API clients
│       │   └── transactions/    # Transaction fetching and decoding
│       ├── prompts.py           # AI prompt templates
│       └── reporting/           # Report generation
├── specs/                       # ERC-7730 specification and fragments
├── .github/workflows/           # CI/CD
├── Dockerfile
├── pyproject.toml
└── .env.example
```

## Reporting Issues

- Use [GitHub Issues](https://github.com/LedgerHQ/erc7730-analyzer/issues) to report bugs or request features
- Include as much context as possible: calldata file, error output, expected behavior
- For security-related issues, please reach out privately rather than opening a public issue

## License

By contributing, you agree that your contributions will be licensed under the [CC0 1.0 Universal](LICENSE) license.
