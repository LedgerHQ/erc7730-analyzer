# ERC-7730 Clear Signing Analyzer

A comprehensive tool for analyzing ERC-7730 clear signing metadata files by fetching and decoding real transaction data from blockchain explorers.

## Features

- 📊 **Batch Transaction Fetching**: Fetches transactions for multiple function selectors in a single pass
- 🔍 **ABI Decoding**: Decodes transaction calldata using contract ABIs
- 📝 **Coverage Analysis**: Compares what users see vs. what the contract receives
- 🤖 **AI-Powered Auditing**: Generates detailed security audit reports using OpenAI

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

### All Available Options

| Option | Environment Variable | Description | Required | Default |
|--------|---------------------|-------------|----------|---------|
| `--erc7730_file` | `ERC7730_FILE` | Path to ERC-7730 JSON file | Yes | - |
| `--api-key` | `ETHERSCAN_API_KEY` | Etherscan API key | Yes | - |
| `--abi` | `ABI_FILE` | Path to custom ABI JSON file | No | Fetched from ERC-7730 or Etherscan |
| `--lookback-days` | `LOOKBACK_DAYS` | Days to look back for transactions | No | 20 |
| N/A | `OPENAI_API_KEY` | OpenAI API key for AI audits | Yes | - |

**Priority:** Command-line arguments > Environment variables > Defaults

## How It Works

1. **Parse ERC-7730 File**: Extracts function selectors and clear signing metadata
2. **Fetch ABI**: Gets contract ABI from the ERC-7730 file, provided file, or Etherscan
3. **Batch Fetch Transactions**: Efficiently fetches recent transactions for all selectors at once
4. **Decode Transactions**: Decodes calldata using the contract ABI
5. **Compare Coverage**: Analyzes what parameters are shown to users vs. hidden
6. **Generate AI Audit**: Creates comprehensive security audit reports

## Output

The tool generates files in the `output/` directory:

- **Summary Report** (`SUMMARY_<contract_id>.md`): Comprehensive analysis with:
  - Summary table of all functions analyzed
  - Statistics on security issues
  - Detailed per-function analysis with transaction samples
  - AI-generated audit reports with recommendations

- **JSON Results** (`results_<contract_id>.json`): Machine-readable analysis data

- **Log File** (`analyze_7730.log`): Detailed execution logs for debugging

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

- **Etherscan Rate Limits**: Free tier has rate limits (5 calls/second)
- **Page Limit**: Etherscan enforces `page × offset ≤ 10,000` limit
- **Chain Support**: Requires Etherscan v2 API support for the target chain
- **AI-Generated Reports**: The AI audit reports may contain false positives and should be manually reviewed. The tool intentionally does not limit the AI's analysis scope to avoid missing critical security issues - this means some flagged items may be overly cautious. Always verify findings before taking action.

## License

MIT License - see LICENSE file for details

