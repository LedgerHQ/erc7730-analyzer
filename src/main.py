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
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

from utils.analyzer import ERC7730Analyzer
from utils.reporter import generate_summary_file, generate_criticals_report, save_json_results, parse_first_report

# Load environment variables
load_dotenv(override=True)

logger = logging.getLogger(__name__)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Analyze ERC-7730 clear signing files and fetch transaction data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables (can also be set in .env file):
  ERC7730_FILE          Path to ERC-7730 JSON file
  ABI_FILE              Path to contract ABI JSON file (optional)
  ETHERSCAN_API_KEY     Etherscan API key
  OPENAI_API_KEY        OpenAI API key for AI-powered audits (optional)
  LOOKBACK_DAYS         Number of days to look back (default: 20)

Priority: Command-line arguments > Environment variables > Defaults
        """
    )
    parser.add_argument(
        '--erc7730_file',
        type=Path,
        default=os.getenv('ERC7730_FILE'),
        help='Path to ERC-7730 JSON file (env: ERC7730_FILE)'
    )
    parser.add_argument(
        '--abi',
        type=Path,
        default=os.getenv('ABI_FILE'),
        help='Path to contract ABI JSON file (env: ABI_FILE, optional)'
    )
    parser.add_argument(
        '--api-key',
        default=os.getenv('ETHERSCAN_API_KEY'),
        help='Etherscan API key (env: ETHERSCAN_API_KEY)'
    )
    parser.add_argument(
        '--lookback-days',
        type=int,
        default=int(os.getenv('LOOKBACK_DAYS') or '20'),
        help='Number of days to look back for transaction history (env: LOOKBACK_DAYS, default: 20)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        default=False,
        help='Enable debug mode to log to file (default: False)'
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
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(output_dir / 'analyze_7730.log')
            ]
        )
    else:
        # Disable logging output when debug is False
        logging.basicConfig(
            level=logging.CRITICAL,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.NullHandler()
            ]
        )

    # Validate required arguments
    if not args.erc7730_file:
        parser.error("--erc7730_file is required (or set ERC7730_FILE environment variable)")

    if not args.api_key:
        parser.error("--api-key is required (or set ETHERSCAN_API_KEY environment variable)")

    # Initialize analyzer
    analyzer = ERC7730Analyzer(
        etherscan_api_key=args.api_key,
        lookback_days=args.lookback_days
    )

    # Run analysis
    results = analyzer.analyze(args.erc7730_file, args.abi)

    # Always create output directory and save results
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    logger.info(f"Saving results to {output_dir}")

    # Generate timestamp for filenames
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    context_id = results.get('context', {}).get('$id', 'unknown').replace(' ', '_')

    # Generate detailed summary file
    summary_file = output_dir / f"SUMMARY_{context_id}_{timestamp}.md"
    logger.info(f"Generating detailed summary file at {summary_file}")
    generate_summary_file(results, summary_file)

    # Generate critical issues mini report
    criticals_file = output_dir / f"CRITICALS_{context_id}_{timestamp}.md"
    logger.info(f"Generating critical issues report at {criticals_file}")
    generate_criticals_report(results, criticals_file)

    # Save JSON results
    json_output = output_dir / f"results_{context_id}_{timestamp}.json"
    logger.info(f"Saving JSON results to {json_output}")
    save_json_results(results, json_output)

    logger.info(f"\n{'='*60}")
    logger.info(f"Analysis complete!")
    logger.info(f"Detailed report: {summary_file}")
    logger.info(f"Critical issues: {criticals_file}")
    logger.info(f"JSON results: {json_output}")
    logger.info(f"{'='*60}\n")

    # Check if there are any critical issues by reading the CRITICALS report file
    has_critical_issues = False

    if criticals_file.exists():
        logger.info(f"Checking CRITICALS report: {criticals_file}")
        criticals_content = criticals_file.read_text()

        # Check if the summary table contains any 🔴 symbols (indicating critical issues)
        # The table format is: | function | selector | 🔴 Issue... | [View]... |
        if '| 🔴' in criticals_content:
            has_critical_issues = True
            # Count how many functions have critical issues
            critical_count = criticals_content.count('| 🔴')
            logger.warning(f"⚠️  Found {critical_count} function(s) with critical issues in summary table")

        # Also check for sections that are NOT "No critical issues found"
        # Look for critical issue sections that contain actual issues
        if not has_critical_issues:
            # Check if there are any sections with critical issues listed
            import re
            critical_sections = re.findall(r'### 🔴 Critical Issues\n\n(.*?)(?=\n###|\n---|\Z)', criticals_content, re.DOTALL)
            for section in critical_sections:
                # If section has bullet points (actual issues), not just "No critical issues found"
                if section.strip() and '- ' in section and 'No critical issues found' not in section:
                    has_critical_issues = True
                    logger.warning("⚠️  Found critical issues in detailed sections")
                    break

    # Return exit code based on critical issues
    if has_critical_issues:
        logger.error(f"\n❌ CRITICAL ISSUES FOUND")
        logger.error("Analysis failed - PR merge should be blocked")
        return 1
    else:
        logger.info("\n✅ NO CRITICAL ISSUES - All functions passed analysis")
        logger.info("Analysis passed - PR merge is allowed")
        return 0


if __name__ == '__main__':
    sys.exit(main())
