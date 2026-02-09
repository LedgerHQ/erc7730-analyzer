"""Calldata decoding helpers for function inputs."""

import logging
from typing import Any, Dict, List, Optional

from ...abi import ABI

logger = logging.getLogger(__name__)


class TransactionFetcherDecodingMixin:
    def _convert_decoded_value(self, value, type_info):
        """
        Recursively convert decoded ABI values to proper Python types.

        Handles:
        - bytes → hex strings
        - tuples (structs) → dicts with component names
        - tuple[] (array of structs) → list of dicts
        - Nested structs and arrays

        Args:
            value: Raw decoded value from web3
            type_info: ABI type information dict with 'type' and optional 'components'

        Returns:
            Properly formatted value
        """
        type_str = type_info.get('type', '')

        # Handle array of structs (tuple[], tuple[3], tuple[][], etc.)
        if type_str.startswith('tuple['):
            components = type_info.get('components', [])
            result = []

            # Recursively handle each struct in the array
            for item in value:
                struct_dict = {}
                for idx, component in enumerate(components):
                    comp_name = component.get('name', f'field_{idx}')
                    comp_value = item[idx] if idx < len(item) else None

                    # Recursively convert based on component type
                    struct_dict[comp_name] = self._convert_decoded_value(comp_value, component)

                result.append(struct_dict)

            return result

        # Handle single struct (tuple)
        elif type_str == 'tuple':
            components = type_info.get('components', [])
            struct_dict = {}

            for idx, component in enumerate(components):
                comp_name = component.get('name', f'field_{idx}')
                comp_value = value[idx] if idx < len(value) else None

                # Recursively convert based on component type
                struct_dict[comp_name] = self._convert_decoded_value(comp_value, component)

            return struct_dict

        # Handle bytes
        elif isinstance(value, bytes):
            return '0x' + value.hex()

        # Handle arrays (of primitives or bytes)
        elif isinstance(value, (list, tuple)):
            # For arrays like uint256[], bytes[], address[], etc.
            # Create a minimal type_info for array elements
            converted = []
            for item in value:
                if isinstance(item, bytes):
                    converted.append('0x' + item.hex())
                elif isinstance(item, (list, tuple)):
                    # Nested array - recurse
                    converted.append(self._convert_decoded_value(item, {'type': 'unknown'}))
                else:
                    converted.append(item)
            return type(value)(converted)

        # Primitives (int, str, bool, None, address)
        else:
            return value

    def _has_complex_types(self, inputs: List[Dict]) -> bool:
        """
        Check if function inputs contain complex types that might need fallback.

        Args:
            inputs: List of ABI input definitions

        Returns:
            True if complex types detected
        """
        def check_type(type_info):
            type_str = type_info.get('type', '')

            # Multi-dimensional arrays (e.g., uint256[][], bytes[][])
            if type_str.count('[') > 1:
                return True

            # Check nested struct components recursively
            if type_str.startswith('tuple'):
                components = type_info.get('components', [])
                for comp in components:
                    if check_type(comp):
                        return True

            return False

        return any(check_type(inp) for inp in inputs)

    def decode_transaction_input(
        self,
        tx_input: str,
        function_data: Dict,
        abi_helper
    ) -> Optional[Dict[str, Any]]:
        """
        Decode transaction calldata using the function metadata.

        Hybrid approach:
        - Decodes all standard types (primitives, arrays, structs, nested structs)
        - Includes raw calldata + ABI for complex edge cases or decoding failures
        - AI can use decoded data or fall back to raw if needed

        Args:
            tx_input: Transaction input data (hex string)
            function_data: Function metadata from ABI helper
            abi_helper: ABI helper instance

        Returns:
            Dictionary mapping parameter names to decoded values
            May include '_raw_fallback' with raw calldata + ABI for complex cases
        """
        try:
            # Remove the function selector
            calldata = tx_input[10:]

            # Get the full ABI entry for this function
            function_name = function_data['name']
            function_abi_entry = None
            for item in abi_helper.abi:
                if item.get('type') == 'function' and item.get('name') == function_name:
                    input_types = [abi_helper._param_abi_type_to_str(inp) for inp in item.get('inputs', [])]
                    sig = f"{function_name}({','.join(input_types)})"
                    if sig == function_data['signature']:
                        function_abi_entry = item
                        break

            if not function_abi_entry:
                logger.error(f"Could not find full ABI entry for {function_data['signature']}")
                return None

            # Get input types for decoding
            inputs = function_abi_entry.get('inputs', [])
            input_types = [abi_helper._param_abi_type_to_str(inp) for inp in inputs]
            input_names = function_data['param_names']

            # Decode the calldata
            decoded_values = self.w3.codec.decode(input_types, bytes.fromhex(calldata))

            # Create a dictionary mapping names to values
            result = {}
            for name, value, input_def in zip(input_names, decoded_values, inputs):
                # Use the comprehensive recursive converter
                converted_value = self._convert_decoded_value(value, input_def)

                # Special handling for unnamed tuple params (flatten into result)
                if input_def.get('type') == 'tuple' and (not name or name == 'params'):
                    # Flatten unnamed struct params into the result dict
                    if isinstance(converted_value, dict):
                        result.update(converted_value)
                    else:
                        result[name] = converted_value
                else:
                    result[name] = converted_value

            # Check for complex types that might need AI verification
            has_complex = self._has_complex_types(inputs)

            if has_complex:
                # Include raw fallback for AI to cross-check if needed
                result['_raw_fallback'] = {
                    'note': 'Complex types detected - raw calldata included for verification',
                    'raw_calldata': tx_input,
                    'function_abi': function_abi_entry
                }
                logger.info(f"Complex types detected in {function_name} - included raw fallback")

            logger.debug(f"Decoded transaction input: {result}")
            return result

        except Exception as e:
            logger.error(f"Failed to decode transaction input: {e}")

            # Decoding failed - provide raw data for AI to decode
            try:
                # Try to get the ABI entry even if decoding failed
                function_name = function_data['name']
                function_abi_entry = None
                for item in abi_helper.abi:
                    if item.get('type') == 'function' and item.get('name') == function_name:
                        input_types = [abi_helper._param_abi_type_to_str(inp) for inp in item.get('inputs', [])]
                        sig = f"{function_name}({','.join(input_types)})"
                        if sig == function_data['signature']:
                            function_abi_entry = item
                            break

                return {
                    '_decoding_failed': True,
                    '_error': str(e),
                    '_raw_fallback': {
                        'note': 'Decoding failed - AI should decode from raw calldata',
                        'raw_calldata': tx_input,
                        'function_abi': function_abi_entry
                    }
                }
            except Exception as fallback_error:
                logger.error(f"Failed to build fallback decoding payload: {fallback_error}")
                return {
                    '_decoding_failed': True,
                    '_error': f"{e}; fallback_error={fallback_error}",
                    '_raw_fallback': {
                        'note': 'Decoding failed and fallback payload generation failed',
                        'raw_calldata': tx_input,
                        'function_abi': None
                    }
                }
