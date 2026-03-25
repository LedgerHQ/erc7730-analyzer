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
from utils.reporting.reporter import generate_criticals_report, generate_summary_file, save_json_results

# Load environment variables
load_dotenv(override=True)

logger = logging.getLogger(__name__)


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
  PREPARED_INPUTS_FILE     Path to frozen benchmark inputs JSON (optional)
  ETHERSCAN_API_KEY        Etherscan API key
  COREDAO_API_KEY          Core DAO API key (optional, for chain 1116)
  OPENAI_API_KEY           OpenAI API key for AI-powered audits (optional)
  ANALYSIS_MODE            Audit strategy: single or multi (default: single)
  LOOKBACK_DAYS            Number of days to look back (default: 20)
  MAX_CONCURRENT_API_CALLS Maximum concurrent API calls (default: 20)
  MAX_API_RETRIES          Maximum retry attempts per API call (default: 3)
  MAX_SELECTOR_TOOL_ROUNDS Maximum evidence-gathering rounds in multi mode (default: 2)
  MAX_TOOL_REQUESTS_PER_ROUND Maximum tool requests per round in multi mode (default: 2)
  RPC_URL_<CHAIN_ID>       Optional per-chain RPC URL override used by state-check tools
  INFURA_RPC_KEY           Optional Infura key fallback used for mainnet state-check tools
  LLM_MODEL                LLM model name (default: gpt-5.4)
  LLM_REASONING_EFFORT     Reasoning effort: low, medium, high (default: high)
  ENABLE_SCREENSHOTS       Enable Ledger device screenshot capture (default: false)
  CS_TESTER_DEVICE         Device model for screenshots: stax or flex (default: stax)
  CS_TESTER_ROOT           Path to pre-built device-sdk-ts repo root
  CS_TESTER_RUNTIME_ROOT   Base dir for local dev defaults under /tmp/erc7730-screenshots (optional)
  ETH_APP_ELF_ROOT         Root containing <device>/bin/app.elf (baked in Docker; override for local dev)
  COIN_APPS_PATH           Legacy path for local coin-apps layouts (optional)
  SPECULOS_BASE_API_PORT   First port to try for native Speculos HTTP API (default: 5000)
  SPECULOS_STARTUP_TIMEOUT Seconds to wait for Speculos HTTP API (default: 20)
  GATING_TOKEN             Token passed through to cs-tester

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
        "--prepared-inputs",
        type=Path,
        default=os.getenv("PREPARED_INPUTS_FILE"),
        help="Path to frozen benchmark inputs JSON (env: PREPARED_INPUTS_FILE, optional)",
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
        default=int(os.getenv("MAX_CONCURRENT_API_CALLS") or "20"),
        help="Maximum number of concurrent API calls (env: MAX_CONCURRENT_API_CALLS, default: 20)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=int(os.getenv("MAX_API_RETRIES") or "3"),
        help="Maximum retry attempts per API call (env: MAX_API_RETRIES, default: 3)",
    )
    parser.add_argument(
        "--analysis-mode",
        choices=("single", "multi"),
        default=os.getenv("ANALYSIS_MODE") or "single",
        help="Audit strategy to use (env: ANALYSIS_MODE, default: single)",
    )
    parser.add_argument(
        "--max-selector-tool-rounds",
        type=int,
        default=int(os.getenv("MAX_SELECTOR_TOOL_ROUNDS") or "2"),
        help="Maximum evidence-gathering rounds per selector in multi mode (env: MAX_SELECTOR_TOOL_ROUNDS, default: 2)",
    )
    parser.add_argument(
        "--max-tool-requests-per-round",
        type=int,
        default=int(os.getenv("MAX_TOOL_REQUESTS_PER_ROUND") or "2"),
        help="Maximum tool requests the model can make per round in multi mode (env: MAX_TOOL_REQUESTS_PER_ROUND, default: 2)",
    )
    parser.add_argument(
        "--model", default=os.getenv("LLM_MODEL") or "gpt-5.4", help="LLM model name (env: LLM_MODEL, default: gpt-5.4)"
    )
    parser.add_argument(
        "--reasoning-effort",
        choices=("low", "medium", "high"),
        default=os.getenv("LLM_REASONING_EFFORT") or "high",
        help="Reasoning effort for the LLM (env: LLM_REASONING_EFFORT, default: high)",
    )
    parser.add_argument(
        "--enable-screenshots",
        action="store_true",
        default=os.getenv("ENABLE_SCREENSHOTS", "").lower() in ("1", "true", "yes"),
        help="Enable Ledger device screenshot capture via cs-tester (env: ENABLE_SCREENSHOTS, default: false)",
    )
    parser.add_argument(
        "--screenshot-device",
        default=os.getenv("CS_TESTER_DEVICE") or "stax",
        help="Ledger device model for screenshots: stax or flex (env: CS_TESTER_DEVICE, default: stax)",
    )
    parser.add_argument(
        "--cs-tester-root",
        default=os.getenv("CS_TESTER_ROOT"),
        help="Path to device-sdk-ts repo root (env: CS_TESTER_ROOT, optional)",
    )
    parser.add_argument(
        "--coin-apps-path",
        default=os.getenv("COIN_APPS_PATH"),
        help="Legacy fallback path with Ledger app ELF files (env: COIN_APPS_PATH, optional)",
    )
    parser.add_argument(
        "--debug", action="store_true", default=False, help="Enable debug mode to log to file (default: False)"
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
        analysis_mode=args.analysis_mode,
        max_selector_tool_rounds=args.max_selector_tool_rounds,
        max_tool_requests_per_round=args.max_tool_requests_per_round,
        llm_model=args.model,
        llm_reasoning_effort=args.reasoning_effort,
        enable_screenshots=args.enable_screenshots,
        screenshot_device=args.screenshot_device,
        cs_tester_root=args.cs_tester_root,
        coin_apps_path=args.coin_apps_path,
    )

    # Run analysis
    results = analyzer.analyze(
        args.erc7730_file,
        args.abi,
        args.raw_txs,
        args.prepared_inputs,
    )

    # Check if analysis failed
    if not results or not isinstance(results, dict):
        logger.error("Analysis failed - no results returned")
        return 1

    # Always create output directory and save results
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    logger.info(f"Saving results to {output_dir}")

    # Generate timestamp for filenames
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Extract protocol name from descriptor (try multiple fields)
    context = results.get("context", {})
    metadata = results.get("metadata", {})
    protocol_name = None

    # Try $id first
    if context.get("$id"):
        protocol_name = context["$id"]
    # Try v2 metadata.contractName
    elif metadata.get("contractName"):
        protocol_name = metadata["contractName"]
    # Try metadata owner
    elif metadata.get("owner"):
        protocol_name = metadata["owner"]
    # Legacy fallback
    elif metadata.get("info", {}).get("legalName"):
        protocol_name = metadata["info"]["legalName"]
    # Fallback to filename (remove "calldata-" prefix if present)
    else:
        filename = Path(args.erc7730_file).stem  # Get filename without extension
        if filename.startswith("calldata-"):
            protocol_name = filename[9:]  # Remove "calldata-" prefix (9 chars)
        else:
            protocol_name = filename

    context_id = protocol_name.replace(" ", "_") if protocol_name else "unknown"

    # Generate full report file
    summary_file = output_dir / f"FULL_REPORT_{context_id}_{timestamp}.md"
    logger.info(f"Generating full report file at {summary_file}")
    generate_summary_file(results, summary_file)

    # Generate critical issues mini report
    criticals_file = output_dir / f"CRITICALS_{context_id}_{timestamp}.md"
    logger.info(f"Generating critical issues report at {criticals_file}")
    generate_criticals_report(results, criticals_file)

    # Save JSON results
    json_output = output_dir / f"results_{context_id}_{timestamp}.json"
    logger.info(f"Saving JSON results to {json_output}")
    save_json_results(results, json_output)

    logger.info(f"\n{'=' * 60}")
    logger.info("Analysis complete!")
    logger.info(f"Detailed report: {summary_file}")
    logger.info(f"Critical issues: {criticals_file}")
    logger.info(f"JSON results: {json_output}")
    logger.info(f"{'=' * 60}\n")

    # Check if there are any critical issues by reading the CRITICALS_*.md file
    has_critical_issues = False

    if criticals_file.exists():
        logger.info(f"Checking CRITICALS report: {criticals_file}")
        criticals_content = criticals_file.read_text()

        if "| 🔴" in criticals_content:
            has_critical_issues = True
            critical_count = criticals_content.count("| 🔴")
            logger.warning(f"⚠️  Found {critical_count} function(s) with critical issues in summary table")

        # Also check for sections that are NOT "No critical issues found"
        # Look for critical issue sections that contain actual issues
        if not has_critical_issues:
            # Check if there are any sections with critical issues listed
            import re

            critical_sections = re.findall(
                r"### 🔴 Critical Issues\n\n(.*?)(?=\n###|\n---|\Z)", criticals_content, re.DOTALL
            )
            for section in critical_sections:
                # If section has numbered lists or bullet points (actual issues), not just "No critical issues found"
                if (
                    section.strip()
                    and ("- " in section or re.search(r"\d+\. ", section))
                    and "No critical issues found" not in section.lower()
                ):
                    has_critical_issues = True
                    logger.warning("⚠️  Found critical issues in detailed sections")
                    break

    if has_critical_issues:
        logger.error("❌ CRITICAL ISSUES FOUND - PR merge should be blocked")
        return 1
    else:
        logger.info("✅ NO CRITICAL ISSUES - PR merge is allowed")
        return 0


if __name__ == "__main__":
    sys.exit(main())
