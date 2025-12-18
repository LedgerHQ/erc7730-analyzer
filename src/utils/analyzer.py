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
from .abi_merger import merge_abis_from_deployments
from .transactions import TransactionFetcher
from .prompts import generate_clear_signing_audit
from .source_code import SourceCodeExtractor

logger = logging.getLogger(__name__)


class ERC7730Analyzer:
    """Analyzer for ERC-7730 clear signing files with Etherscan integration."""

    # ERC4626 detection patterns
    ERC4626_INCLUDE_PATTERNS = [
        'erc4626',
        'erc-4626',
        '4626-vault',
        '4626vault',
    ]

    ERC4626_SOURCE_PATTERNS = [
        r'ERC4626',
        r'IERC4626',
        r'function\s+asset\s*\(\s*\)',
        r'function\s+deposit\s*\([^)]*\)\s*(?:public|external)',
        r'function\s+mint\s*\([^)]*\)\s*(?:public|external)',
        r'function\s+withdraw\s*\([^)]*\)\s*(?:public|external)',
        r'function\s+redeem\s*\([^)]*\)\s*(?:public|external)',
    ]

    def __init__(self, etherscan_api_key: Optional[str] = None, lookback_days: int = 20, enable_source_code: bool = True, use_smart_referencing: bool = True):
        """
        Initialize the analyzer.

        Args:
            etherscan_api_key: Etherscan API key for fetching transaction data
            lookback_days: Number of days to look back for transaction history (default: 20)
            enable_source_code: Whether to extract and include source code in analysis (default: True)
            use_smart_referencing: Whether to use smart rule referencing to reduce token usage (default: True)
        """
        self.etherscan_api_key = etherscan_api_key
        self.lookback_days = lookback_days
        self.enable_source_code = enable_source_code
        self.use_smart_referencing = use_smart_referencing
        self.w3 = Web3()
        self.abi_helper = None
        self.tx_fetcher = TransactionFetcher(etherscan_api_key, lookback_days)
        self.source_extractor = SourceCodeExtractor(etherscan_api_key) if enable_source_code else None
        self.selector_to_format_key = {}
        self.extracted_codes = {}  # Will store extracted code for each chain deployment (keyed by chainId)
        self.erc4626_context = None  # Will store ERC4626 vault context if detected
        self.erc20_context = None  # Will store ERC20 token context if detected

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

    def _detect_erc4626_from_includes(self, includes_path: str) -> bool:
        """
        Detect if descriptor is an ERC4626 vault based on includes path.

        Args:
            includes_path: The includes path from the descriptor

        Returns:
            True if ERC4626 pattern detected
        """
        logger.debug(f"Checking includes path for ERC4626 patterns: {includes_path}")
        includes_lower = includes_path.lower()
        for pattern in self.ERC4626_INCLUDE_PATTERNS:
            if pattern in includes_lower:
                logger.info(f"🏦 ERC4626 pattern '{pattern}' found in includes: {includes_path}")
                return True
        return False

    def _detect_erc4626_from_source(self, source_code: str, contract_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Detect ERC4626 pattern from contract source code.

        IMPORTANT: Only detects if the DEPLOYED contract inherits from ERC4626,
        not if ERC4626 exists anywhere in the source.

        Args:
            source_code: The contract source code
            contract_name: Name of the deployed contract from Etherscan (if available)

        Returns:
            Dict with detection results:
            {
                'is_erc4626': bool,
                'detected_patterns': List[str],
                'inherits_erc4626': bool,
                'has_asset_function': bool,
                'main_contract': str  # Name of the deployed contract
            }
        """
        logger.debug("Analyzing source code for ERC4626 patterns...")

        result = {
            'is_erc4626': False,
            'detected_patterns': [],
            'inherits_erc4626': False,
            'has_asset_function': False,
            'main_contract': contract_name
        }

        if not source_code:
            logger.debug("No source code provided for ERC4626 detection")
            return result

        import re
        from .source_code import SolidityCodeParser

        # Parse inheritance chain
        parser = SolidityCodeParser(source_code)
        inheritance_chain = parser.extract_inheritance_chain()

        if not inheritance_chain:
            logger.debug("   ✗ No contracts with inheritance found")
            return result

        # If contract_name not provided by Etherscan, use heuristic
        if not contract_name:
            logger.debug("   Contract name not provided, using heuristic...")
            contract_pattern = r'(?:abstract\s+)?contract\s+(\w+)(?:\s+is\s+[^{]+)?\s*\{'
            all_contracts = []
            for match in re.finditer(contract_pattern, source_code):
                is_abstract = 'abstract' in match.group(0)
                contract_name_match = match.group(1)
                position = match.start()
                all_contracts.append((contract_name_match, is_abstract, position))

            # Sort by position (last in file)
            all_contracts.sort(key=lambda x: x[2], reverse=True)

            # Find first non-abstract contract (from the end of file)
            for contract_name_candidate, is_abstract, _ in all_contracts:
                if not is_abstract:
                    contract_name = contract_name_candidate
                    break

        if not contract_name:
            logger.debug(f"   ✗ Could not determine deployed contract name")
            return result

        result['main_contract'] = contract_name
        logger.info(f"   📝 Deployed contract: {contract_name}")

        # Check if the main contract (or its ancestors) inherits from ERC4626
        def inherits_from_erc4626(contract_name, chain):
            """Recursively check if contract inherits from ERC4626."""
            if contract_name not in chain:
                return False

            parents = chain[contract_name]
            for parent in parents:
                if 'ERC4626' in parent or 'IERC4626' in parent:
                    return True
                # Recursively check parent's inheritance
                if inherits_from_erc4626(parent, chain):
                    return True
            return False

        if inherits_from_erc4626(contract_name, inheritance_chain):
            result['inherits_erc4626'] = True
            parents = inheritance_chain.get(contract_name, [])
            result['detected_patterns'].append(f'inheritance: contract {contract_name} is {", ".join(parents)}')
            logger.info(f"   ✓ {contract_name} inherits from ERC4626")

        # Check for asset() function in the main contract specifically
        # Extract just the main contract's code
        main_contract_match = re.search(
            rf'(?:abstract\s+)?contract\s+{re.escape(contract_name)}\s+(?:is\s+[^{{]+)?\s*\{{',
            source_code
        )
        if main_contract_match:
            # Find the contract body
            start = main_contract_match.end() - 1  # Start at opening brace
            open_braces = 0
            i = start
            while i < len(source_code):
                if source_code[i] == '{':
                    open_braces += 1
                elif source_code[i] == '}':
                    open_braces -= 1
                    if open_braces == 0:
                        contract_body = source_code[start:i+1]
                        if re.search(r'function\s+asset\s*\(\s*\)', contract_body):
                            result['has_asset_function'] = True
                            result['detected_patterns'].append('asset() function')
                            logger.info(f"   ✓ {contract_name} has asset() function")
                        break
                i += 1

        # Determine if it's ERC4626 based on main contract only
        if result['inherits_erc4626']:
            result['is_erc4626'] = True
            logger.info(f"   ✓ Confirmed ERC4626: {contract_name} inherits from ERC4626/IERC4626")
        else:
            logger.info(f"   ✗ Not ERC4626: {contract_name} does not inherit from ERC4626")

        return result

    def _detect_erc20_from_source(self, source_code: str, contract_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Detect if the deployed contract is an ERC20 token.

        Args:
            source_code: The contract source code
            contract_name: Name of the deployed contract from Etherscan (if available)

        Returns:
            Dict with detection results:
            {
                'is_erc20': bool,
                'detected_patterns': List[str],
                'inherits_erc20': bool,
                'main_contract': str
            }
        """
        logger.debug("Analyzing source code for ERC20 patterns...")

        result = {
            'is_erc20': False,
            'detected_patterns': [],
            'inherits_erc20': False,
            'main_contract': contract_name
        }

        if not source_code:
            logger.debug("No source code provided for ERC20 detection")
            return result

        import re
        from .source_code import SolidityCodeParser

        # Parse inheritance chain
        parser = SolidityCodeParser(source_code)
        inheritance_chain = parser.extract_inheritance_chain()

        if not inheritance_chain:
            logger.debug("   ✗ No contracts with inheritance found")
            return result

        # If contract_name not provided by Etherscan, use heuristic
        if not contract_name:
            logger.debug("   Contract name not provided, using heuristic...")
            contract_pattern = r'(?:abstract\s+)?contract\s+(\w+)(?:\s+is\s+[^{]+)?\s*\{'
            all_contracts = []
            for match in re.finditer(contract_pattern, source_code):
                is_abstract = 'abstract' in match.group(0)
                contract_name_match = match.group(1)
                position = match.start()
                all_contracts.append((contract_name_match, is_abstract, position))

            # Sort by position (last in file)
            all_contracts.sort(key=lambda x: x[2], reverse=True)

            # Find first non-abstract contract (from the end of file)
            for contract_name_candidate, is_abstract, _ in all_contracts:
                if not is_abstract:
                    contract_name = contract_name_candidate
                    break

        if not contract_name:
            logger.debug(f"   ✗ Could not determine deployed contract name")
            return result

        result['main_contract'] = contract_name
        logger.info(f"   📝 Checking if {contract_name} is ERC20...")

        # Check if the main contract (or its ancestors) inherits from ERC20
        def inherits_from_erc20(contract_name, chain):
            """Recursively check if contract inherits from ERC20."""
            if contract_name not in chain:
                return False

            parents = chain[contract_name]
            for parent in parents:
                # Common ERC20 patterns
                if any(pattern in parent for pattern in ['ERC20', 'IERC20', 'BEP20', 'IBEP20']):
                    return True
                # Recursively check parent's inheritance
                if inherits_from_erc20(parent, chain):
                    return True
            return False

        if inherits_from_erc20(contract_name, inheritance_chain):
            result['inherits_erc20'] = True
            parents = inheritance_chain.get(contract_name, [])
            result['detected_patterns'].append(f'inheritance: contract {contract_name} is {", ".join(parents)}')
            logger.info(f"   ✓ {contract_name} inherits from ERC20")

        # Determine if it's ERC20 based on main contract only
        if result['inherits_erc20']:
            result['is_erc20'] = True
            logger.info(f"   ✓ Confirmed ERC20: {contract_name} inherits from ERC20/IERC20")
        else:
            logger.debug(f"   ✗ Not ERC20: {contract_name} does not inherit from ERC20")

        return result

    def _query_erc4626_asset(self, contract_address: str, chain_id: int) -> Optional[str]:
        """
        Query the asset() function on-chain for ERC4626 vaults.

        Args:
            contract_address: The vault contract address
            chain_id: Chain ID

        Returns:
            The underlying asset address or None if query fails
        """
        try:
            logger.info(f"🏦 Querying asset() for ERC4626 vault {contract_address} on chain {chain_id}...")

            # asset() selector: 0x38d52e0f
            asset_selector = '0x38d52e0f'

            params = {
                'module': 'proxy',
                'action': 'eth_call',
                'to': contract_address,
                'data': asset_selector,
                'tag': 'latest',
                'apikey': self.etherscan_api_key
            }

            base_url = f"https://api.etherscan.io/v2/api?chainid={chain_id}"
            response = requests.get(base_url, params=params)
            data = response.json()

            if (data.get('result') and
                'error' not in data and
                data.get('status') != '0' and
                data['result'] != '0x' and
                len(data['result']) >= 42):
                # Extract address from result (last 20 bytes / 40 hex chars)
                asset_address = '0x' + data['result'][-40:].lower()
                if asset_address != '0x' + '0' * 40:
                    logger.info(f"   ✓ ERC4626 asset() returned: {asset_address}")
                    return asset_address
                else:
                    logger.warning(f"   ⚠ asset() returned zero address")
            else:
                logger.warning(f"   ⚠ asset() call failed or returned empty result")

            return None
        except Exception as e:
            logger.warning(f"   ⚠ Failed to query asset(): {e}")
            return None

    def _build_erc4626_context(self, includes_detected: bool, source_detection: Dict[str, Any], underlying_token: str = None, asset_from_chain: str = None) -> Dict[str, Any]:
        """
        Build ERC4626 context information for the AI prompt.

        Args:
            includes_detected: Whether ERC4626 was detected from includes
            source_detection: Detection results from source code analysis
            underlying_token: The underlying asset token address (from metadata constants)
            asset_from_chain: The underlying asset address queried from on-chain asset()

        Returns:
            Dict with ERC4626 context for AI prompt
        """
        return {
            'is_erc4626_vault': includes_detected or source_detection.get('is_erc4626', False),
            'detection_source': 'includes' if includes_detected else ('source_code' if source_detection.get('is_erc4626') else 'none'),
            'detected_patterns': source_detection.get('detected_patterns', []),
            'underlying_token': underlying_token,
            'asset_from_chain': asset_from_chain
        }

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

        # Check for ERC4626 pattern in includes path BEFORE merging
        if self._detect_erc4626_from_includes(include_file):
            logger.info(f"🏦 ERC4626 vault detected from includes: {include_file}")
            # Get underlying token from metadata constants if available
            underlying_token = data.get('metadata', {}).get('constants', {}).get('underlyingToken')
            self.erc4626_context = self._build_erc4626_context(
                includes_detected=True,
                source_detection={},
                underlying_token=underlying_token
            )

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
                response = requests.get(abi, timeout=10)
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
                logger.warning(f"Failed to fetch ABI from URL: {e}")
                logger.info("Falling back to next ABI source...")
                abi = None

        # Check if we have a valid ABI from ERC-7730 file
        if abi and isinstance(abi, list) and len(abi) > 0:
            logger.info(f"Using ABI from ERC-7730 file ({len(abi)} entries)")
        elif abi_file and abi_file.exists() and abi_file.is_file():
            # Try loading from ABI file if provided and valid
            logger.info(f"Loading ABI from file: {abi_file}")
            try:
                with open(abi_file, 'r') as f:
                    abi = json.load(f)
                logger.info(f"Successfully loaded ABI from file ({len(abi)} entries)")
            except Exception as e:
                logger.warning(f"Failed to load ABI from file: {e}")
                logger.info("Falling back to API fetch...")
                abi = None

        # If no ABI yet, fetch from deployments via API
        if not abi or not isinstance(abi, list) or len(abi) == 0:
            logger.info("No ABI from ERC-7730 file or ABI file, fetching from API...")
            # Fetch and merge ABIs from all deployments
            abi, fetch_results = merge_abis_from_deployments(
                deployments,
                fetch_contract_abi,
                self.etherscan_api_key
            )

        if not abi:
            logger.error("Could not obtain contract ABI from any source (ERC-7730, file, or API)")
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
            'erc4626_context': self.erc4626_context,  # Include ERC4626 vault context if detected
            'erc20_context': self.erc20_context,  # Include ERC20 token context if detected
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

                # Detect ERC4626 from source code if not already detected from includes
                if not self.erc4626_context:
                    logger.info("\n🔍 Checking source code for ERC4626 patterns...")
                    for chain_id, extracted_code in self.extracted_codes.items():
                        if extracted_code.get('source_code') and isinstance(extracted_code['source_code'], str):
                            contract_name = extracted_code.get('contract_name')
                            source_detection = self._detect_erc4626_from_source(
                                extracted_code['source_code'],
                                contract_name=contract_name
                            )
                            if source_detection['is_erc4626']:
                                logger.info(f"🏦 ERC4626 vault confirmed from source code on chain {chain_id}")
                                logger.info(f"   Detection method: {source_detection.get('detection_patterns', [])}")

                                # Get underlying token from metadata constants if available
                                underlying_token = erc7730_data.get('metadata', {}).get('constants', {}).get('underlyingToken')
                                if underlying_token:
                                    logger.info(f"   Underlying token from metadata: {underlying_token}")

                                # Query on-chain asset() value
                                asset_from_chain = self._query_erc4626_asset(
                                    extracted_code['address'],
                                    chain_id
                                )

                                self.erc4626_context = self._build_erc4626_context(
                                    includes_detected=False,
                                    source_detection=source_detection,
                                    underlying_token=underlying_token,
                                    asset_from_chain=asset_from_chain
                                )
                                logger.info(f"   ✓ ERC4626 context built successfully")
                                break  # Found ERC4626, no need to check other chains

                # Detect ERC20 from source code (if not ERC4626, since ERC4626 extends ERC20)
                if not self.erc20_context and not self.erc4626_context:
                    logger.info("\n🔍 Checking source code for ERC20 patterns...")
                    for chain_id, extracted_code in self.extracted_codes.items():
                        if extracted_code.get('source_code') and isinstance(extracted_code['source_code'], str):
                            contract_name = extracted_code.get('contract_name')
                            source_detection = self._detect_erc20_from_source(
                                extracted_code['source_code'],
                                contract_name=contract_name
                            )
                            if source_detection['is_erc20']:
                                logger.info(f"🪙 ERC20 token confirmed from source code on chain {chain_id}")
                                logger.info(f"   Detection method: {source_detection.get('detected_patterns', [])}")

                                self.erc20_context = {
                                    'is_erc20_token': True,
                                    'contract_name': source_detection['main_contract'],
                                    'detected_patterns': source_detection['detected_patterns'],
                                    'detection_source': 'source_code'
                                }
                                logger.info(f"   ✓ ERC20 context built successfully")
                                break  # Found ERC20, no need to check other chains

                    if not self.erc4626_context:
                        logger.debug("   ✗ No ERC4626 patterns detected in source code")

                # If detected from includes but no on-chain query yet, do it now
                if self.erc4626_context and not self.erc4626_context.get('asset_from_chain'):
                    logger.info("🔍 Querying on-chain asset() for ERC4626 vault...")
                    for deployment in deployments:
                        asset_from_chain = self._query_erc4626_asset(
                            deployment['address'],
                            deployment['chainId']
                        )
                        if asset_from_chain:
                            self.erc4626_context['asset_from_chain'] = asset_from_chain
                            logger.info(f"   ✓ Updated ERC4626 context with on-chain asset")
                            break

                if self.erc4626_context:
                    logger.info(f"\n{'='*60}")
                    logger.info(f"🏦 ERC4626 VAULT CONTEXT ACTIVE")
                    logger.info(f"   Detection: {self.erc4626_context.get('detection_source', 'unknown')}")
                    if self.erc4626_context.get('underlying_token'):
                        logger.info(f"   Underlying token (metadata): {self.erc4626_context['underlying_token']}")
                    if self.erc4626_context.get('asset_from_chain'):
                        logger.info(f"   Asset token (on-chain): {self.erc4626_context['asset_from_chain']}")
                    logger.info(f"   AI will be informed about ERC4626 vault semantics")
                    logger.info(f"{'='*60}\n")
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
                logger.info(f"Searching for function '{function_name}' ({function_data['signature']}) across {len(self.extracted_codes)} chain(s)...")

                # Try each chain until we find the function
                for chain_id, extracted_code in self.extracted_codes.items():
                    if not extracted_code['source_code']:
                        continue

                    logger.info(f"  Checking chain {chain_id}...")
                    function_source = self.source_extractor.get_function_with_dependencies(
                        function_name,
                        extracted_code,
                        function_signature=function_data['signature'],  # Try smart matching, fallback to name
                        max_lines=1000  # Increased from 300 to include more internal functions
                    )

                    if function_source and function_source['function']:
                        logger.info(f"✓ Found function on chain {chain_id}!")
                        logger.info(f"✓ Extracted function code ({function_source['total_lines']} lines)")
                        logger.info(f"  - Constants: {len(function_source.get('constants', []))}")
                        logger.info(f"  - Structs: {len(function_source['structs'])}")
                        logger.info(f"  - Enums: {len(function_source['enums'])}")
                        logger.info(f"  - Internal functions: {len(function_source['internal_functions'])}")
                        if function_source.get('parent_functions'):
                            logger.info(f"  - Parent functions (from super.): {len(function_source['parent_functions'])}")
                            for pf in function_source['parent_functions']:
                                logger.info(f"      └─ {pf['parent_contract']}.{pf['function_name']}()")
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

                    # 1. Custom types (highest priority)
                    if function_source.get('custom_types'):
                        code_block += "// Custom types:\n"
                        for custom_type in function_source['custom_types']:
                            code_block += f"{custom_type}\n"
                        code_block += "\n"

                    # 2. Using statements
                    if function_source.get('using_statements'):
                        code_block += "// Using statements:\n"
                        for using_stmt in function_source['using_statements']:
                            code_block += f"{using_stmt}\n"
                        code_block += "\n"

                    # 3. Constants
                    if function_source.get('constants'):
                        code_block += "// Constants:\n"
                        for constant in function_source['constants']:
                            code_block += f"{constant}\n"
                        code_block += "\n"

                    # 4. Structs
                    if function_source['structs']:
                        code_block += "// Structs:\n"
                        for struct in function_source['structs']:
                            code_block += f"{struct}\n"
                        code_block += "\n"

                    # 5. Enums
                    if function_source['enums']:
                        code_block += "// Enums:\n"
                        for enum in function_source['enums']:
                            code_block += f"{enum}\n"
                        code_block += "\n"

                    # 6. Main function
                    code_block += "// Main function:\n"
                    code_block += function_source['function']

                    # 7. Internal functions called
                    if function_source['internal_functions']:
                        code_block += "\n\n// Internal functions called:\n"
                        for internal_func in function_source['internal_functions']:
                            # Format internal function with docstring and body
                            if internal_func.get('docstring'):
                                code_block += f"{internal_func['docstring']}\n"
                            code_block += f"{internal_func['body']}\n\n"

                    # 8. Parent functions (from super. calls)
                    if function_source.get('parent_functions'):
                        code_block += "\n\n// Parent contract implementations (from super. calls):\n"
                        for parent_func in function_source['parent_functions']:
                            parent_name = parent_func.get('parent_contract', 'Unknown')
                            func_name = parent_func.get('function_name', 'unknown')
                            code_block += f"// From {parent_name}.{func_name}():\n"
                            code_block += f"{parent_func['body']}\n\n"

                    # 9. Libraries (lowest priority)
                    if function_source.get('libraries'):
                        code_block += "\n// Libraries:\n"
                        for library in function_source['libraries']:
                            code_block += f"{library}\n\n"

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

                critical_report, detailed_report, report_json = generate_clear_signing_audit(
                    selector,
                    decoded_txs,  # Will be empty list if no transactions
                    erc7730_format_expanded,  # Use expanded format with metadata and display.definitions
                    function_data['signature'],
                    source_code=function_source,
                    use_smart_referencing=self.use_smart_referencing,
                    erc4626_context=self.erc4626_context,  # Pass ERC4626 vault context if detected
                    erc20_context=self.erc20_context  # Pass ERC20 token context if detected
                )

                audit_report_critical = critical_report
                audit_report_detailed = detailed_report
                audit_report_json = report_json

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
                'audit_report_detailed': audit_report_detailed,
                'audit_report_json': audit_report_json,
                'source_code': function_source  # Store source code for reports
            }

        logger.info(f"\n{'='*60}")
        logger.info("Analysis complete!")
        logger.info(f"{'='*60}")

        return results
