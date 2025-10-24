# ERC-7730 Clear Signing Analyzer

A comprehensive tool for analyzing ERC-7730 clear signing metadata files by fetching and decoding real transaction data, including transaction receipts with event logs, from blockchain explorers.

## Features

- 📊 **Batch Transaction Fetching**: Fetches transactions for multiple function selectors in a single pass
- 🔍 **ABI Decoding**: Decodes transaction calldata using contract ABIs
- 📋 **Receipt Log Analysis**: Fetches and decodes transaction receipts to analyze actual on-chain events (Transfers, Approvals, etc.)
- 📝 **Source Code Analysis**: Fetches and analyzes contract source code patterns for deeper security insights
- 📊 **Coverage Analysis**: Compares what users see vs. what the contract receives and what actually happens on-chain
- 🤖 **AI-Powered Auditing**: Generates two types of security reports:
  - Critical Issues Report for quick security assessment
  - Comprehensive Summary Report with detailed analysis and recommendations

## Installation

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/erc7730-analyzer.git
cd erc7730-analyzer

# Install dependencies
pip install -r requirements.txt
```

## Usage

You can configure the tool in two ways:

### Option 1: Using .env File (Recommended)

1. Copy the example env file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and fill in your values:
   ```bash
   ERC7730_FILE=path/to/your/erc7730.json
   ETHERSCAN_API_KEY=your_api_key_here
   OPENAI_API_KEY=your_openai_key_here 
   ```

3. Run the analyzer (no arguments needed):
   ```bash
   python analyze_7730.py
   ```

### Option 2: Command-Line Arguments

```bash
python analyze_7730.py \
  --erc7730_file path/to/erc7730.json \
  --api-key YOUR_ETHERSCAN_API_KEY
```

Results will be automatically saved to the `output/` directory.

### With Custom ABI

```bash
python analyze_7730.py \
  --erc7730_file path/to/erc7730.json \
  --abi path/to/abi.json \
  --api-key YOUR_ETHERSCAN_API_KEY
```

### Additional Options

#### Custom ABI File

If your ERC-7730 file doesn't include an embedded ABI or ABI URL:

```bash
python analyze_7730.py \
  --erc7730_file path/to/erc7730.json \
  --abi path/to/custom-abi.json \
  --api-key YOUR_ETHERSCAN_API_KEY
```

Or in `.env`:
```bash
ABI_FILE=path/to/custom-abi.json
```

#### Custom Lookback Period

By default, the tool looks back 20 days for transaction history. You can customize this:

```bash
python analyze_7730.py \
  --erc7730_file path/to/erc7730.json \
  --api-key YOUR_ETHERSCAN_API_KEY \
  --lookback-days 90
```

Or in `.env`:
```bash
LOOKBACK_DAYS=90
```

**Note:** Longer lookback periods will make more API calls and may take longer to complete.

#### Debug Mode

Enable debug logging to file:

```bash
python analyze_7730.py \
  --erc7730_file path/to/erc7730.json \
  --api-key YOUR_ETHERSCAN_API_KEY \
  --debug
```

This creates detailed logs in `output/analyze_7730.log` for troubleshooting.

### All Available Options

| Option | Environment Variable | Description | Required | Default |
|--------|---------------------|-------------|----------|---------|
| `--erc7730_file` | `ERC7730_FILE` | Path to ERC-7730 JSON file | Yes | - |
| `--api-key` | `ETHERSCAN_API_KEY` | Etherscan API key | Yes | - |
| `--abi` | `ABI_FILE` | Path to custom ABI JSON file | No | Fetched from ERC-7730 or Etherscan |
| `--lookback-days` | `LOOKBACK_DAYS` | Days to look back for transactions | No | 20 |
| `--debug` | N/A | Enable debug logging to file | No | False |
| N/A | `OPENAI_API_KEY` | OpenAI API key for AI audits | Yes | - |

**Priority:** Command-line arguments > Environment variables > Defaults

## How It Works

1. **Parse ERC-7730 File**: Extracts function selectors and clear signing metadata
2. **Fetch ABI**: Gets contract ABI from the ERC-7730 file, provided file, or Etherscan
3. **Batch Fetch Transactions**: Efficiently fetches recent transactions for all selectors at once
4. **Extract Source Code**: Fetches contract source code from Etherscan for pattern analysis
5. **Decode Transactions**: Decodes calldata using the contract ABI
6. **Fetch Transaction Receipts**: Gets transaction receipts and decodes event logs (Transfer, Approval, Swap, etc.)
7. **Fetch Token Metadata**: Automatically queries token contracts for symbols and decimals for readable formatting
8. **Compare Coverage**: Analyzes what parameters are shown to users vs. hidden vs. what actually happened on-chain
9. **Generate AI Audit**: Creates two security reports - a critical issues report and a comprehensive summary report

## Output

The tool generates files in the `output/` directory:

- **Critical Issues Report** (`CRITICALS_<contract_id>.md`): Quick security overview with critical findings and recommendations

- **Summary Report** (`SUMMARY_<contract_id>.md`): Comprehensive analysis with:
  - Summary table of all functions analyzed
  - Statistics on security issues
  - Detailed per-function analysis with transaction samples
  - Transaction receipt event logs (decoded Transfers, Approvals, etc.)
  - Side-by-side comparison of user-facing data vs. actual on-chain events
  - AI-generated audit reports with recommendations

- **JSON Results** (`results_<contract_id>.json`): Machine-readable analysis data including decoded receipt logs

- **Log File** (`analyze_7730.log`): Detailed execution logs for debugging (only created when `--debug` flag is used)

All output files are automatically placed in the `output/` directory which is created if it doesn't exist.

## API Keys

### Etherscan API Key

Get your free API key from [Etherscan](https://etherscan.io/apis) (supports 50+ chains).

Set it via:
```bash
export ETHERSCAN_API_KEY="your_key_here"
```

Or pass it directly:
```bash
python analyze_7730.py --api-key YOUR_KEY ...
```

### OpenAI API Key

For AI-powered audit reports, set your OpenAI API key:
```bash
export OPENAI_API_KEY="your_openai_key_here"
```

## Configuration

The tool uses the following defaults:

- **Lookback period**: 20 days (configurable with `--lookback-days`)
- **Transactions per selector**: 5 (configurable in code)
- **Block window size**: 10,000 blocks (configurable in code)
- **Page size**: 1,000 transactions (configurable in code)
- **Max retries**: 3 attempts (configurable in code)

## Limitations

- **Etherscan Rate Limits**: Free tier has rate limits (5 calls/second). The tool makes additional API calls for transaction receipts and token metadata (symbols/decimals), which are cached to minimize requests. The default 20-day lookback period was chosen to balance finding sufficient transaction samples while avoiding excessive API calls. Increasing the lookback period may result in rate limiting or require a paid Etherscan plan.
- **Event Decoding**: Currently supports decoding common events like Transfer, Approval. Other event types are shown as "Unknown" with raw data. Support for additional event types can be added as needed.
- **Token Decimals/Symbols**: Automatically fetched via Etherscan API for most ERC-20 tokens. If the call fails, raw values are shown. Non-standard tokens may not display correctly.
- **Page Limit**: Etherscan enforces `page × offset ≤ 10,000` limit per request window
- **Chain Support**: Requires Etherscan v2 API support for the target chain
- **AI-Generated Reports**: The AI audit reports may contain false positives and should be manually reviewed. Always verify findings before taking action.
- **AI Model Selection**: The tool uses GPT-5-mini by default, which balances good results with faster response times and lower costs. You can modify the code to use other models based on your needs.

## License

MIT License - see LICENSE file for details

