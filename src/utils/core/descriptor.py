"""Descriptor parsing, include merging, selector extraction, and ABI lookup."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AnalyzerDescriptorMixin:
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

