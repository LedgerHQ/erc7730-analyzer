"""
Core analyzer logic for ERC-7730 clear signing files.

This module orchestrates the analysis of ERC-7730 files including:
- Parsing ERC-7730 JSON files
- Extracting function selectors
- Coordinating transaction fetching and decoding
- Generating audit reports
"""

import json
import logging
import time
from typing import Dict, List, Any, Optional
from pathlib import Path
import requests
from web3 import Web3

from .abi import ABI, fetch_contract_abi
from .transactions import TransactionFetcher
from .prompts import generate_clear_signing_audit
from .source_code import SourceCodeExtractor

logger = logging.getLogger(__name__)


class ERC7730Analyzer:
    """Analyzer for ERC-7730 clear signing files with Etherscan integration."""

    def __init__(self, etherscan_api_key: Optional[str] = None, lookback_days: int = 20, enable_source_code: bool = True):
        """
        Initialize the analyzer.

        Args:
            etherscan_api_key: Etherscan API key for fetching transaction data
            lookback_days: Number of days to look back for transaction history (default: 20)
            enable_source_code: Whether to extract and include source code in analysis (default: True)
        """
        self.etherscan_api_key = etherscan_api_key
        self.lookback_days = lookback_days
        self.enable_source_code = enable_source_code
        self.w3 = Web3()
        self.abi_helper = None
        self.tx_fetcher = TransactionFetcher(etherscan_api_key, lookback_days)
        self.source_extractor = SourceCodeExtractor(etherscan_api_key) if enable_source_code else None
        self.selector_to_format_key = {}
        self.extracted_code = None  # Will store extracted code for the contract

    def parse_erc7730_file(self, file_path: Path) -> Dict[str, Any]:
        """
        Parse an ERC-7730 JSON file and extract relevant information.

        Args:
            file_path: Path to the ERC-7730 JSON file

        Returns:
            Dictionary containing parsed data
        """
        logger.info(f"Parsing ERC-7730 file: {file_path}")

        try:
            with open(file_path, 'r') as f:
                data = json.load(f)

            logger.info(f"Successfully loaded {file_path}")
            return data
        except Exception as e:
            logger.error(f"Failed to parse {file_path}: {e}")
            raise

    def extract_selectors(self, erc7730_data: Dict[str, Any]) -> tuple[List[str], Dict[str, str]]:
        """
        Extract all function selectors from ERC-7730 data.
        Converts function signatures to selectors if needed.

        Args:
            erc7730_data: Parsed ERC-7730 JSON data

        Returns:
            Tuple of (selectors list, mapping from selector to original format key)
        """
        logger.info("Extracting function selectors from ERC-7730 data")

        selectors = []
        selector_to_format_key = {}

        # Selectors are in the display.formats section as keys
        if 'display' in erc7730_data and 'formats' in erc7730_data['display']:
            formats = erc7730_data['display']['formats']
            for key in formats.keys():
                # Check if key is already a selector
                if key.startswith('0x') and len(key) == 10:
                    selector = key.lower()
                    selectors.append(selector)
                    selector_to_format_key[selector] = key
                else:
                    # It's a function signature, calculate the selector
                    selector = '0x' + self.w3.keccak(text=key).hex()[:8]
                    logger.info(f"Calculated selector for '{key}': {selector}")
                    selectors.append(selector.lower())
                    selector_to_format_key[selector.lower()] = key

        logger.info(f"Found {len(selectors)} selectors: {selectors}")
        return selectors, selector_to_format_key

    def get_contract_deployments(self, erc7730_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract all contract deployments from ERC-7730 data.

        Args:
            erc7730_data: Parsed ERC-7730 JSON data

        Returns:
            List of deployment dictionaries with 'address' and 'chainId' keys
        """
        try:
            deployments = erc7730_data['context']['contract']['deployments']
            deployment_list = []
            for deployment in deployments:
                address = deployment.get('address')
                chain_id = deployment.get('chainId')
                if address and chain_id:
                    deployment_list.append({
                        'address': address,
                        'chainId': chain_id
                    })
            logger.info(f"Found {len(deployment_list)} contract deployments across various chains")
            return deployment_list
        except Exception as e:
            logger.error(f"Failed to extract contract deployments: {e}")
            return []

    def get_function_abi_by_selector(self, selector: str) -> Optional[Dict]:
        """
        Find the function ABI entry matching a given selector.

        Args:
            selector: Function selector (4-byte hex) or function signature

        Returns:
            Function metadata or None
        """
        if not self.abi_helper:
            logger.error("ABI helper not initialized")
            return None

        # If selector is a function signature, convert it
        if not selector.startswith('0x'):
            hex_selector = self.abi_helper._function_signature_to_selector(selector)
            logger.info(f"Converted signature '{selector}' to selector '{hex_selector}'")
        else:
            hex_selector = selector

        function_data = self.abi_helper.find_function_by_selector(hex_selector)

        if function_data:
            logger.info(f"Found matching function: {function_data['signature']} -> {hex_selector}")
            return function_data
        else:
            logger.warning(f"No function found for selector {hex_selector}")
            return None

    def analyze(
        self,
        erc7730_file: Path,
        abi_file: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        Main analysis function.

        Args:
            erc7730_file: Path to ERC-7730 JSON file
            abi_file: Optional path to ABI JSON file

        Returns:
            Analysis results
        """
        logger.info(f"Starting analysis of {erc7730_file}")

        # Parse ERC-7730 file
        erc7730_data = self.parse_erc7730_file(erc7730_file)

        # Extract contract deployments
        deployments = self.get_contract_deployments(erc7730_data)
        if not deployments:
            logger.error("Could not extract contract deployments from ERC-7730 file")
            return {}

        # Get ABI - check if it's embedded in the ERC-7730 file
        abi = erc7730_data.get('context', {}).get('contract', {}).get('abi')

        # Check if ABI is a URL string
        if abi and isinstance(abi, str):
            logger.info(f"ABI is a URL, fetching from: {abi}")
            try:
                response = requests.get(abi)
                response.raise_for_status()
                data = response.json()

                # Handle Etherscan API response format vs. direct JSON
                if isinstance(data, dict) and 'result' in data:
                    if isinstance(data['result'], str):
                        abi = json.loads(data['result'])
                    else:
                        abi = data['result']
                else:
                    abi = data

                logger.info(f"Successfully fetched ABI from URL ({len(abi)} entries)")
            except Exception as e:
                logger.error(f"Failed to fetch ABI from URL: {e}")
                abi = None

        if abi and isinstance(abi, list) and len(abi) > 0:
            logger.info(f"Using ABI from ERC-7730 file ({len(abi)} entries)")
        elif abi_file:
            logger.info(f"Loading ABI from file: {abi_file}")
            with open(abi_file, 'r') as f:
                abi = json.load(f)
        else:
            # Try to fetch ABI from first deployment
            first_deployment = deployments[0]
            abi = fetch_contract_abi(
                first_deployment['address'],
                first_deployment['chainId'],
                self.etherscan_api_key
            )

        if not abi:
            logger.error("Could not obtain contract ABI")
            return {}

        # Initialize the ABI helper
        self.abi_helper = ABI(abi)
        logger.info("ABI helper initialized")

        # Extract selectors and their mapping to format keys
        selectors, self.selector_to_format_key = self.extract_selectors(erc7730_data)

        # Analyze each selector
        results = {
            'deployments': deployments,
            'context': erc7730_data.get('context', {}),
            'erc7730_full': erc7730_data,  # Store full ERC-7730 data for reference expansion
            'selectors': {}
        }

        # First, identify which selectors are payable by checking their ABI
        logger.info(f"\n{'='*60}")
        logger.info(f"Identifying payable functions...")
        logger.info(f"{'='*60}")

        payable_selectors = set()
        for selector in selectors:
            function_data = self.get_function_abi_by_selector(selector)
            if function_data and function_data.get('stateMutability') == 'payable':
                payable_selectors.add(selector.lower())
                logger.info(f"Function {function_data['name']} ({selector}) is payable")

        if payable_selectors:
            logger.info(f"Found {len(payable_selectors)} payable function(s)")

        # Fetch transactions for ALL selectors at once
        logger.info(f"\n{'='*60}")
        logger.info(f"Fetching transactions for all {len(selectors)} selectors at once...")
        logger.info(f"{'='*60}")

        # Initialize transaction storage and track which selectors still need txs
        all_selector_txs = {s.lower(): [] for s in selectors}
        selectors_needing_txs = set(s.lower() for s in selectors)
        deployment_per_selector = {}  # Track which deployment was used for each selector

        # Try each deployment, continuing to search for selectors that don't have transactions yet
        for deployment in deployments:
            if not selectors_needing_txs:
                # All selectors have transactions, no need to continue
                break

            contract_address = deployment['address']
            chain_id = deployment['chainId']
            logger.info(f"Trying deployment: {contract_address} on chain {chain_id}")
            logger.info(f"  Looking for transactions for {len(selectors_needing_txs)} remaining selector(s)")

            # Fetch transactions only for selectors that don't have any yet
            deployment_txs = self.tx_fetcher.fetch_all_transactions_for_selectors(
                contract_address,
                list(selectors_needing_txs),
                chain_id,
                per_selector=5,
                payable_selectors=payable_selectors
            )

            # Update results for selectors that found transactions
            for selector, txs in deployment_txs.items():
                if txs and selector in selectors_needing_txs:
                    all_selector_txs[selector] = txs
                    selectors_needing_txs.remove(selector)
                    deployment_per_selector[selector] = deployment
                    logger.info(f"  ✓ Found {len(txs)} transaction(s) for {selector} on chain {chain_id}")

        # Log final results
        found_count = len([s for s, txs in all_selector_txs.items() if txs])
        not_found_count = len(selectors_needing_txs)

        logger.info(f"\n{'='*60}")
        logger.info(f"Transaction search complete:")
        logger.info(f"  ✓ {found_count} selector(s) with transactions")
        if not_found_count > 0:
            logger.warning(f"  ⚠ {not_found_count} selector(s) without transactions: {list(selectors_needing_txs)}")
        logger.info(f"{'='*60}\n")

        # Use the first deployment that had transactions for source code extraction
        used_deployment = deployment_per_selector.get(next(iter(deployment_per_selector), None)) if deployment_per_selector else deployments[0] if deployments else None

        if not used_deployment:
            logger.warning("No transactions found across all deployments")
            # Continue anyway for static analysis
            used_deployment = deployments[0] if deployments else None
            if not used_deployment:
                return results

        # Extract source code once at the beginning
        if self.enable_source_code and self.source_extractor:
            logger.info(f"\n{'='*60}")
            logger.info("Extracting contract source code...")
            logger.info(f"{'='*60}")

            self.extracted_code = self.source_extractor.extract_contract_code(
                used_deployment['address'],
                used_deployment['chainId'],
                selectors=selectors
            )

            if self.extracted_code['source_code']:
                logger.info(f"✓ Source code extracted successfully")
                logger.info(f"  - Functions: {len(self.extracted_code['functions'])}")
                logger.info(f"  - Structs: {len(self.extracted_code['structs'])}")
                logger.info(f"  - Enums: {len(self.extracted_code['enums'])}")
                if self.extracted_code['is_proxy']:
                    logger.info(f"  - Proxy detected, using implementation: {self.extracted_code['implementation']}")
                if self.extracted_code['is_diamond']:
                    logger.info(f"  - Diamond proxy detected with {len(set(self.extracted_code['facets'].values()))} facets")
            else:
                logger.warning("Could not extract source code, continuing without it")

        # Analyze each selector with its pre-fetched transactions
        for selector in selectors:
            logger.info(f"\n{'='*60}")
            logger.info(f"Analyzing selector: {selector}")
            logger.info(f"{'='*60}")

            # Get function metadata
            function_data = self.get_function_abi_by_selector(selector)
            if not function_data:
                logger.warning(f"Skipping selector {selector} - no matching ABI entry")
                continue

            function_name = function_data['name']
            logger.info(f"Function name: {function_name}")
            logger.info(f"Function signature: {function_data['signature']}")

            # Get the pre-fetched transactions for this selector
            transactions = all_selector_txs.get(selector.lower(), [])

            # Get the deployment used for this selector (for chain_id and contract_address)
            selector_deployment = deployment_per_selector.get(selector.lower(), used_deployment)

            if not transactions:
                logger.warning(f"No transactions found for selector {selector} - will perform static analysis only")
            else:
                logger.info(f"Found {len(transactions)} transactions for selector {selector} on chain {selector_deployment['chainId']}")

            # Decode each transaction
            decoded_txs = []
            for i, tx in enumerate(transactions, 1):
                logger.info(f"\nTransaction {i}/{len(transactions)}: {tx['hash']}")

                decoded = self.tx_fetcher.decode_transaction_input(
                    tx['input'],
                    function_data,
                    self.abi_helper
                )
                if decoded is not None:
                    tx_data = {
                        'hash': tx['hash'],
                        'block': tx['blockNumber'],
                        'timestamp': tx['timeStamp'],
                        'from': tx['from'],
                        'to': tx.get('to', ''),
                        'value': tx['value'],
                        'decoded_input': decoded
                    }

                    # Fetch transaction receipt and decode logs
                    logger.info(f"Fetching receipt for transaction {tx['hash']}")
                    receipt = self.tx_fetcher.fetch_transaction_receipt(
                        tx['hash'],
                        selector_deployment['chainId']
                    )

                    if receipt and receipt.get('logs'):
                        decoded_logs = []
                        for log in receipt['logs']:
                            decoded_log = self.tx_fetcher.decode_log_event(
                                log,
                                selector_deployment['chainId']
                            )
                            if decoded_log:
                                decoded_logs.append(decoded_log)

                        if decoded_logs:
                            tx_data['receipt_logs'] = decoded_logs
                            logger.info(f"Decoded {len(decoded_logs)} log events:")
                            for log in decoded_logs:
                                if log.get('event') == 'Transfer':
                                    logger.info(f"  Transfer: {log['value_formatted']} from {log['from'][:10]}... to {log['to'][:10]}...")
                                elif log.get('event') == 'Approval':
                                    logger.info(f"  Approval: {log['value_formatted']} from {log['owner'][:10]}... to {log['spender'][:10]}...")
                                else:
                                    logger.info(f"  {log.get('event', 'Unknown')}: {log.get('address', 'unknown')[:10]}...")

                    decoded_txs.append(tx_data)
                    time.sleep(0.2)

                    logger.info(f"Decoded parameters:")
                    for param_name, param_value in decoded.items():
                        logger.info(f"  {param_name}: {param_value}")

            # Generate clear signing audit report
            format_key = self.selector_to_format_key.get(selector, selector)
            erc7730_format = erc7730_data.get('display', {}).get('formats', {}).get(format_key, {})

            # Import the expand function to get full context for AI
            from .reporter import expand_erc7730_format_with_refs
            erc7730_format_expanded = expand_erc7730_format_with_refs(erc7730_format, erc7730_data)

            audit_report = None

            # Extract source code for this specific function
            function_source = None
            if self.extracted_code and self.extracted_code['source_code']:
                logger.info(f"Extracting source code for function: {function_name}")
                function_source = self.source_extractor.get_function_with_dependencies(
                    function_name,
                    self.extracted_code,
                    max_lines=300
                )

                if function_source and function_source['function']:
                    logger.info(f"✓ Extracted function code ({function_source['total_lines']} lines)")
                    logger.info(f"  - Constants: {len(function_source.get('constants', []))}")
                    logger.info(f"  - Structs: {len(function_source['structs'])}")
                    logger.info(f"  - Enums: {len(function_source['enums'])}")
                    logger.info(f"  - Internal functions: {len(function_source['internal_functions'])}")
                    if function_source['truncated']:
                        logger.info(f"  ⚠ Code was truncated to fit within line limit")

                    # Display code in debug mode as a single cohesive block
                    if logger.isEnabledFor(logging.INFO):
                        code_block = f"\n{'='*60}\n"
                        code_block += "SOURCE CODE (being sent to AI):\n"
                        code_block += f"{'='*60}\n\n"

                        if function_source.get('function_docstring'):
                            code_block += f"// Docstring:\n{function_source['function_docstring']}\n\n"

                        if function_source.get('constants'):
                            code_block += "// Constants:\n"
                            for constant in function_source['constants']:
                                code_block += f"{constant}\n"
                            code_block += "\n"

                        if function_source['structs']:
                            code_block += "// Structs:\n"
                            for struct in function_source['structs']:
                                code_block += f"{struct}\n"
                            code_block += "\n"

                        if function_source['enums']:
                            code_block += "// Enums:\n"
                            for enum in function_source['enums']:
                                code_block += f"{enum}\n"
                            code_block += "\n"

                        code_block += "// Main function:\n"
                        code_block += function_source['function']

                        if function_source['internal_functions']:
                            code_block += "\n\n// Internal functions called:\n"
                            for internal_func in function_source['internal_functions']:
                                # Format internal function with docstring and body
                                if internal_func.get('docstring'):
                                    code_block += f"{internal_func['docstring']}\n"
                                code_block += f"{internal_func['body']}\n\n"

                        code_block += f"\n{'='*60}\n"

                        # Single log call for entire code block
                        logger.info(code_block)

            # Generate clear signing audit report
            audit_report_critical = None
            audit_report_detailed = None
            has_no_transactions = not decoded_txs

            if erc7730_format:
                logger.info(f"\n{'='*60}")
                if has_no_transactions:
                    logger.info(f"Generating STATIC AI audit report for {selector} (no transactions)...")
                else:
                    logger.info(f"Generating AI audit report for {selector}...")
                logger.info(f"{'='*60}")

                critical_report, detailed_report = generate_clear_signing_audit(
                    selector,
                    decoded_txs,  # Will be empty list if no transactions
                    erc7730_format_expanded,  # Use expanded format with metadata and display.definitions
                    function_data['signature'],
                    source_code=function_source
                )

                # If no transactions, prepend a critical warning to BOTH reports
                if has_no_transactions:
                    no_tx_warning = """🔴 **CRITICAL WARNING: No Historical Transactions Found**

⚠️ This analysis is based ONLY on static source code review without real transaction data.

**Issue:** No transactions were found for this selector within the configured lookback period.

**Impact:** The analysis cannot verify:
- Actual on-chain behavior and token flows
- Real-world parameter values and edge cases
- Event emissions and receipt logs
- Integration with other contracts

**Recommendations:**
1. Increase the `LOOKBACK_DAYS` environment variable to search a longer time period
2. Provide manual sample transactions for this selector to enable dynamic analysis
3. Verify this function is actually being used in production
4. If this is a new/unused function, consider removing it from the ERC-7730 file until it's actively used

---

"""
                    # Prepend warning to BOTH reports
                    critical_report = no_tx_warning + critical_report
                    detailed_report = no_tx_warning + detailed_report

                audit_report_critical = critical_report
                audit_report_detailed = detailed_report

                logger.info(f"\nCritical Report:\n{critical_report}\n")
                logger.info(f"\nDetailed Report:\n{detailed_report}\n")

            results['selectors'][selector] = {
                'function_name': function_name,
                'function_signature': function_data['signature'],
                'contract_address': selector_deployment['address'],
                'chain_id': selector_deployment['chainId'],
                'transactions': decoded_txs,
                'erc7730_format': erc7730_format,
                'audit_report_critical': audit_report_critical,
                'audit_report_detailed': audit_report_detailed
            }

        logger.info(f"\n{'='*60}")
        logger.info("Analysis complete!")
        logger.info(f"{'='*60}")

        return results
