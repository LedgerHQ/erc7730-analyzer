#!/usr/bin/env python3
"""
Main entry point for ERC-7730 Clear Signing Analyzer.

This script orchestrates the analysis workflow:
1. Parse command-line arguments
2. Initialize the analyzer
3. Run analysis
4. Generate reports
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from utils.core import ERC7730Analyzer
from utils.llm import BACKEND_DEFAULTS, VALID_BACKENDS
from utils.reporting.reporter import generate_criticals_report, generate_summary_file, save_json_results

load_dotenv(override=True)

logger = logging.getLogger(__name__)


def _status(msg: str) -> None:
    """Print a progress line to stderr."""
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze ERC-7730 clear signing files and fetch transaction data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables (can also be set in .env file):
  ERC7730_FILE             Path to ERC-7730 JSON file
  ABI_FILE                 Path to contract ABI JSON file (optional)
  RAW_TXS_FILE             Path to JSON file with raw transactions (optional)
  ETHERSCAN_API_KEY        Etherscan API key
  COREDAO_API_KEY          Core DAO API key (optional, for chain 1116)
  OPENAI_API_KEY           OpenAI API key (for openai backend)
  ANTHROPIC_API_KEY        Anthropic API key (for anthropic backend)
  LOOKBACK_DAYS            Number of days to look back (default: 20)
  MAX_CONCURRENT_API_CALLS Maximum concurrent API calls (default: 10)
  MAX_API_RETRIES          Maximum retry attempts per API call (default: 3)

LLM Backends:
  openai      OpenAI-compatible API (default model: gpt-4o)
  anthropic   Anthropic API (default model: claude-sonnet-4-20250514)
  cursor      Cursor agent CLI in ask mode (default model: opus-4.6, no API key needed)

Priority: Command-line arguments > Environment variables > Defaults
        """,
    )
    parser.add_argument(
        "--erc7730_file",
        type=Path,
        default=os.getenv("ERC7730_FILE"),
        help="Path to ERC-7730 JSON file (env: ERC7730_FILE)",
    )
    parser.add_argument(
        "--abi",
        type=Path,
        default=os.getenv("ABI_FILE"),
        help="Path to contract ABI JSON file (env: ABI_FILE, optional)",
    )
    parser.add_argument(
        "--raw-txs",
        type=Path,
        default=os.getenv("RAW_TXS_FILE"),
        help="Path to JSON file with raw transactions (env: RAW_TXS_FILE, optional)",
    )
    parser.add_argument(
        "--api-key", default=os.getenv("ETHERSCAN_API_KEY"), help="Etherscan API key (env: ETHERSCAN_API_KEY)"
    )
    parser.add_argument(
        "--coredao-api-key",
        default=os.getenv("COREDAO_API_KEY"),
        help="Core DAO API key for chain 1116 (env: COREDAO_API_KEY, optional)",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=int(os.getenv("LOOKBACK_DAYS") or "20"),
        help="Number of days to look back for transaction history (env: LOOKBACK_DAYS, default: 20)",
    )
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=int(os.getenv("MAX_CONCURRENT_API_CALLS") or "8"),
        help="Maximum number of concurrent API calls (env: MAX_CONCURRENT_API_CALLS, default: 8)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=int(os.getenv("MAX_API_RETRIES") or "3"),
        help="Maximum retry attempts per API call (env: MAX_API_RETRIES, default: 3)",
    )
    parser.add_argument(
        "--debug", action="store_true", default=False, help="Enable debug mode to log to file (default: False)"
    )

    # LLM backend options
    backends_help = ", ".join(VALID_BACKENDS)
    parser.add_argument(
        "--backend", choices=VALID_BACKENDS, default="openai", help=f"LLM backend: {backends_help} (default: openai)"
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model name (default depends on backend: "
        + ", ".join(f"{b}={d['model']}" for b, d in BACKEND_DEFAULTS.items())
        + ")",
    )
    parser.add_argument(
        "--llm-api-key", default=None, help="API key for the LLM backend (overrides env var for the selected backend)"
    )
    parser.add_argument(
        "--llm-api-url", default=None, help="Custom API base URL for the LLM backend (openai/anthropic only)"
    )

    args = parser.parse_args()

    # Configure logging based on --debug flag
    if args.debug:
        # Create output directory for log file
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)

        # Enable file logging when debug is True
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[logging.FileHandler(output_dir / "analyze_7730.log")],
        )
    else:
        # Disable logging output when debug is False
        logging.basicConfig(
            level=logging.CRITICAL, format="%(asctime)s - %(levelname)s - %(message)s", handlers=[logging.NullHandler()]
        )

    # Validate required arguments
    if not args.erc7730_file:
        parser.error("--erc7730_file is required (or set ERC7730_FILE environment variable)")

    if not args.api_key:
        parser.error("--api-key is required (or set ETHERSCAN_API_KEY environment variable)")

    # Initialize analyzer
    analyzer = ERC7730Analyzer(
        etherscan_api_key=args.api_key,
        coredao_api_key=args.coredao_api_key,
        lookback_days=args.lookback_days,
        max_concurrent_api_calls=args.max_concurrent,
        max_api_retries=args.max_retries,
        backend=args.backend,
        model=args.model,
        api_key=args.llm_api_key,
        api_url=args.llm_api_url,
    )

    # Run analysis
    results = analyzer.analyze(args.erc7730_file, args.abi, args.raw_txs)

    # Check if analysis failed
    if not results or not isinstance(results, dict):
        logger.error("Analysis failed - no results returned")
        return 1

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    context = results.get("context", {})
    protocol_name = context.get("$id") or context.get("owner") or context.get("legalname")
    if not protocol_name:
        filename = Path(args.erc7730_file).stem
        protocol_name = filename[9:] if filename.startswith("calldata-") else filename

    context_id = protocol_name.replace(" ", "_") if protocol_name else "unknown"

    summary_file = output_dir / f"FULL_REPORT_{context_id}_{timestamp}.md"
    generate_summary_file(results, summary_file)

    criticals_file = output_dir / f"CRITICALS_{context_id}_{timestamp}.md"
    generate_criticals_report(results, criticals_file)

    json_output = output_dir / f"results_{context_id}_{timestamp}.json"
    save_json_results(results, json_output)

    _status(f"Reports saved to {output_dir}/:")
    _status(f"  Full report:      {summary_file.name}")
    _status(f"  Critical issues:  {criticals_file.name}")
    _status(f"  JSON results:     {json_output.name}")

    # Determine exit code from critical issues
    has_critical_issues = False

    if criticals_file.exists():
        criticals_content = criticals_file.read_text()

        if "| 🔴" in criticals_content:
            has_critical_issues = True
            critical_count = criticals_content.count("| 🔴")
            _status(f"\nCRITICAL ISSUES FOUND ({critical_count} function(s))")

        if not has_critical_issues:
            import re

            critical_sections = re.findall(
                r"### 🔴 Critical Issues\n\n(.*?)(?=\n###|\n---|\Z)", criticals_content, re.DOTALL
            )
            for section in critical_sections:
                if (
                    section.strip()
                    and ("- " in section or re.search(r"\d+\. ", section))
                    and "No critical issues found" not in section.lower()
                ):
                    has_critical_issues = True
                    _status("\nCRITICAL ISSUES FOUND (see report)")
                    break

    if has_critical_issues:
        return 1
    else:
        _status("\nNo critical issues found.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
