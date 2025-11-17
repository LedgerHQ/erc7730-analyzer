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
        self.extracted_codes = {}  # Will store extracted code for each chain deployment (keyed by chainId)

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

            # Merge includes if present
            base_path = Path(file_path).parent
            data = self._merge_includes(data, base_path)

            logger.info(f"Successfully loaded {file_path}")
            return data
        except Exception as e:
            logger.error(f"Failed to parse {file_path}: {e}")
            raise

    def _merge_includes(self, data: Dict[str, Any], base_path: Path) -> Dict[str, Any]:
        """
        Merge ERC-7730 includes into the main file.

        Args:
            data: Parsed ERC-7730 JSON data
            base_path: Directory path of the main file

        Returns:
            Merged ERC-7730 data with includes resolved
        """
        if 'includes' not in data:
            return data

        include_file = data['includes']
        include_path = base_path / include_file

        logger.info(f"Merging include file: {include_path}")

        try:
            with open(include_path, 'r') as f:
                include_data = json.load(f)

            # Recursively merge includes in the included file
            include_data = self._merge_includes(include_data, base_path)

            # Merge metadata (constants, enums, etc.)
            if 'metadata' in include_data:
                if 'metadata' not in data:
                    data['metadata'] = {}
                for key, value in include_data['metadata'].items():
                    if key not in data['metadata']:
                        data['metadata'][key] = value
                    elif isinstance(value, dict) and isinstance(data['metadata'][key], dict):
                        # Deep merge for nested dicts (e.g., constants, enums)
                        # Include file values come first, main file can override
                        data['metadata'][key] = {**value, **data['metadata'][key]}

            # Merge display definitions
            if 'display' in include_data:
                if 'display' not in data:
                    data['display'] = {}
                if 'definitions' in include_data['display']:
                    if 'definitions' not in data['display']:
                        data['display']['definitions'] = {}
                    # Include file definitions are added first, main file can override
                    data['display']['definitions'] = {**include_data['display']['definitions'], **data['display']['definitions']}

                # Merge display formats
                if 'formats' in include_data['display']:
                    if 'formats' not in data['display']:
                        data['display']['formats'] = {}
                    # Include file formats are added first, main file can override
                    data['display']['formats'] = {**include_data['display']['formats'], **data['display']['formats']}

            # Remove includes key after merging
            del data['includes']

            logger.info(f"Successfully merged include: {include_file}")

        except Exception as e:
            logger.error(f"Failed to merge include {include_file}: {e}")
            raise

        return data

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
                if not isinstance(key, str):
                    logger.warning(f"Skipping non-string display key: {key}")
                    continue

                formatted_key = key.strip()

                # Check if key is already a selector
                if formatted_key.startswith('0x') and len(formatted_key) == 10:
                    selector = formatted_key.lower()
                    selectors.append(selector)
                    selector_to_format_key[selector] = key
                    continue

                # Normalize signature before hashing so parameter names don't affect selectors
                normalized_signature = self._normalize_function_signature(formatted_key)
                if not normalized_signature:
                    logger.warning(f"Could not normalize signature '{formatted_key}' - skipping")
                    continue

                selector = '0x' + self.w3.keccak(text=normalized_signature).hex()[:8]
                if normalized_signature != formatted_key:
                    logger.info(
                        f"Calculated selector for '{formatted_key}' "
                        f"(normalized '{normalized_signature}'): {selector}"
                    )
                else:
                    logger.info(f"Calculated selector for '{formatted_key}': {selector}")

                selector_lower = selector.lower()
                selectors.append(selector_lower)
                selector_to_format_key[selector_lower] = key

        logger.info(f"Found {len(selectors)} selectors: {selectors}")
        return selectors, selector_to_format_key

    def _normalize_function_signature(self, signature: str) -> str:
        """
        Convert a display format signature (which may include parameter names)
        into its canonical Solidity signature (types only).
        """
        signature = signature.strip()
        if not signature or '(' not in signature or ')' not in signature:
            return signature

        open_idx = signature.find('(')
        close_idx = signature.rfind(')')
        if close_idx <= open_idx:
            return signature

        function_name = signature[:open_idx].strip()
        params_body = signature[open_idx + 1:close_idx]

        if not function_name:
            return signature

        params = self._split_signature_params(params_body)
        normalized_params = [self._normalize_param_type(param) for param in params if param]

        return f"{function_name}({','.join(normalized_params)})"

    def _split_signature_params(self, params_str: str) -> List[str]:
        """
        Split a function parameter string into individual parameters while
        respecting nested tuple parentheses.
        """
        params = []
        current = []
        depth = 0

        for char in params_str:
            if char == ',' and depth == 0:
                param = ''.join(current).strip()
                if param:
                    params.append(param)
                current = []
                continue

            if char == '(':
                depth += 1
            elif char == ')':
                depth = max(depth - 1, 0)

            current.append(char)

        # Add the last parameter
        tail = ''.join(current).strip()
        if tail:
            params.append(tail)

        return params

    def _normalize_param_type(self, param: str) -> str:
        """
        Remove parameter names, storage modifiers, and whitespace from a single
        parameter string to obtain its canonical Solidity type representation.
        """
        param = param.strip()
        if not param:
            return ''

        # Tuple parameter e.g. "(address src,address dst) desc"
        if param[0] == '(':
            depth = 0
            inner_chars = []
            idx = 0

            while idx < len(param):
                char = param[idx]
                if char == '(':
                    depth += 1
                    if depth > 1:
                        inner_chars.append(char)
                elif char == ')':
                    depth -= 1
                    if depth > 0:
                        inner_chars.append(char)
                    if depth == 0:
                        idx += 1
                        break
                else:
                    if depth > 0:
                        inner_chars.append(char)
                idx += 1

            inner_str = ''.join(inner_chars)
            inner_params = self._split_signature_params(inner_str)
            normalized_inner = ','.join(
                filter(None, (self._normalize_param_type(p) for p in inner_params))
            )

            # Capture any array suffix like [] or [2]
            suffix_chars = []
            while idx < len(param) and param[idx] in '[]0123456789':
                suffix_chars.append(param[idx])
                idx += 1

            return f"({normalized_inner}){''.join(suffix_chars)}"

        # Non-tuple parameter: take the first token as the type (e.g., "uint256 amount")
        token = param.split()[0]
        return token.rstrip(',')

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
        abi_file: Optional[Path] = None,
        raw_txs_file: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        Main analysis function.

        Args:
            erc7730_file: Path to ERC-7730 JSON file
            abi_file: Optional path to ABI JSON file
            raw_txs_file: Optional path to JSON file with raw transactions

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

        # Initialize transaction storage and track how many samples are still needed
        transactions_per_selector = 5  # Matches tx_fetcher default
        all_selector_txs = {s.lower(): [] for s in selectors}
        selectors_remaining = {
            s.lower(): transactions_per_selector
            for s in selectors
        }
        deployment_per_selector = {}  # Track which deployment was used for each selector
        default_deployment = deployments[0] if deployments else {
            'address': 'N/A',
            'chainId': 1
        }

        # Try each deployment, continuing to search for selectors that don't have transactions yet
        for deployment in deployments:
            selectors_to_query = [
                selector
                for selector, remaining in selectors_remaining.items()
                if remaining > 0
            ]

            if not selectors_to_query:
                # All selectors have transactions, no need to continue
                break

            contract_address = deployment['address']
            chain_id = deployment['chainId']
            logger.info(f"Trying deployment: {contract_address} on chain {chain_id}")
            logger.info(f"  Looking for transactions for {len(selectors_to_query)} remaining selector(s)")

            # Fetch transactions only for selectors that don't have any yet
            deployment_txs = self.tx_fetcher.fetch_all_transactions_for_selectors(
                contract_address,
                selectors_to_query,
                chain_id,
                per_selector=transactions_per_selector,
                payable_selectors=payable_selectors
            )

            # Update results for selectors that found transactions
            for selector, txs in deployment_txs.items():
                if not txs:
                    continue

                selector_lower = selector.lower()
                if selector_lower not in selectors_remaining:
                    continue

                remaining_needed = selectors_remaining[selector_lower]
                if remaining_needed <= 0:
                    continue

                # Only keep as many transactions as still needed
                to_add = txs[:remaining_needed]
                if not to_add:
                    continue

                all_selector_txs[selector_lower].extend(to_add)
                selectors_remaining[selector_lower] = max(0, remaining_needed - len(to_add))
                deployment_per_selector.setdefault(selector_lower, deployment)
                logger.info(
                    f"  ✓ Aggregated {len(all_selector_txs[selector_lower])}/"
                    f"{transactions_per_selector} transaction(s) for {selector_lower} "
                    f"(added {len(to_add)} from chain {chain_id})"
                )

        # Log final results
        satisfied_selectors = [
            sel for sel, remaining in selectors_remaining.items()
            if remaining <= 0
        ]
        selectors_missing = [
            sel for sel, remaining in selectors_remaining.items()
            if remaining > 0
        ]

        found_count = len(satisfied_selectors)
        not_found_count = len(selectors_missing)

        logger.info(f"\n{'='*60}")
        logger.info(f"Transaction search complete:")
        logger.info(f"  ✓ {found_count} selector(s) with transactions")
        if not_found_count > 0:
            logger.warning(
                f"  ⚠ {not_found_count} selector(s) still missing samples: {selectors_missing}"
            )
        logger.info(f"{'='*60}\n")

        # Integrate manual transactions if provided
        if raw_txs_file:
            logger.info(f"\n{'='*60}")
            logger.info(f"Integrating manual transactions from {raw_txs_file}")
            logger.info(f"{'='*60}")

            # Use the primary deployment for manual transaction integration
            primary_deployment = deployments[0] if deployments else None
            if primary_deployment:
                all_selector_txs = self.tx_fetcher.integrate_manual_transactions(
                    all_selector_txs,
                    raw_txs_file,
                    primary_deployment['address'],
                    abi,
                    primary_deployment['chainId']
                )
                logger.info(f"{'='*60}\n")
            else:
                logger.warning("No deployment available for manual transaction integration")

        # Extract source code from ALL deployments (multi-chain support)
        if self.enable_source_code and self.source_extractor and deployments:
            logger.info(f"\n{'='*60}")
            logger.info("Extracting contract source code from all deployments...")
            logger.info(f"{'='*60}")

            # Track which chains we've already extracted from to avoid duplicates
            extracted_chains = set()

            for deployment in deployments:
                chain_id = deployment['chainId']
                address = deployment['address']

                # Skip if we already extracted from this chain
                if chain_id in extracted_chains:
                    logger.info(f"Skipping chain {chain_id} - already extracted")
                    continue

                logger.info(f"\n📦 Extracting from chain {chain_id} at {address}")

                extracted_code = self.source_extractor.extract_contract_code(
                    address,
                    chain_id,
                    selectors=selectors
                )

                if extracted_code['source_code']:
                    self.extracted_codes[chain_id] = extracted_code
                    extracted_chains.add(chain_id)

                    logger.info(f"✓ Source code extracted successfully for chain {chain_id}")
                    logger.info(f"  - Functions: {len(extracted_code['functions'])}")
                    logger.info(f"  - Structs: {len(extracted_code['structs'])}")
                    logger.info(f"  - Enums: {len(extracted_code['enums'])}")
                    if extracted_code['is_proxy']:
                        logger.info(f"  - Proxy detected, using implementation: {extracted_code['implementation']}")
                    if extracted_code['is_diamond']:
                        logger.info(f"  - Diamond proxy detected with {len(set(extracted_code['facets'].values()))} facets")
                else:
                    logger.warning(f"Could not extract source code for chain {chain_id}")

            if self.extracted_codes:
                logger.info(f"\n✓ Successfully extracted source code from {len(self.extracted_codes)} chain(s): {list(self.extracted_codes.keys())}")
            else:
                logger.warning("Could not extract source code from any deployment, continuing without it")

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
            selector_deployment = deployment_per_selector.get(selector.lower(), default_deployment)

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
                    # Only fetch receipt if we have a valid transaction hash (starts with 0x and is 66 chars)
                    tx_hash = tx.get('hash', '')
                    if tx_hash.startswith('0x') and len(tx_hash) == 66:
                        logger.info(f"Fetching receipt for transaction {tx_hash}")
                        receipt = self.tx_fetcher.fetch_transaction_receipt(
                            tx_hash,
                            selector_deployment['chainId']
                        )
                    else:
                        logger.debug(f"Skipping receipt fetch for transaction {tx_hash} (not a valid TX hash)")
                        receipt = None

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

            # Extract source code for this specific function (search across all chains)
            function_source = None
            if self.extracted_codes:
                logger.info(f"Searching for function '{function_name}' across {len(self.extracted_codes)} chain(s)...")

                # Try each chain until we find the function
                for chain_id, extracted_code in self.extracted_codes.items():
                    if not extracted_code['source_code']:
                        continue

                    logger.info(f"  Checking chain {chain_id}...")
                    function_source = self.source_extractor.get_function_with_dependencies(
                        function_name,
                        extracted_code,
                        max_lines=300
                    )

                    if function_source and function_source['function']:
                        logger.info(f"✓ Found function on chain {chain_id}!")
                        logger.info(f"✓ Extracted function code ({function_source['total_lines']} lines)")
                        logger.info(f"  - Constants: {len(function_source.get('constants', []))}")
                        logger.info(f"  - Structs: {len(function_source['structs'])}")
                        logger.info(f"  - Enums: {len(function_source['enums'])}")
                        logger.info(f"  - Internal functions: {len(function_source['internal_functions'])}")
                        if function_source['truncated']:
                            logger.info(f"  ⚠ Code was truncated to fit within line limit")
                        break  # Stop searching once found
                    else:
                        logger.info(f"  Function not found on chain {chain_id}")

                if not function_source or not function_source.get('function'):
                    logger.warning(f"Function '{function_name}' not found in any of the {len(self.extracted_codes)} chain(s)")

            # Display code in debug mode as a single cohesive block
            if function_source and function_source.get('function'):
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
