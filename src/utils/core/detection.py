"""Detection mixin for ERC4626/ERC20 semantics and include-based hints."""

import logging
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)


class AnalyzerDetectionMixin:
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
        from ..extraction.source_code import SolidityCodeParser

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
        from ..extraction.source_code import SolidityCodeParser

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
            'detection_source': 'Detected from ERC-7730 includes (references eip4626.schema.json)' if includes_detected else ('Detected from source code analysis' if source_detection.get('is_erc4626') else 'Not detected'),
            'detected_patterns': source_detection.get('detected_patterns', []),
            'underlying_token': underlying_token,
            'asset_from_chain': asset_from_chain
        }
