"""Type and struct normalization helpers for signature matching."""

import re
from typing import Dict, Optional

from ..shared import logger


class SourceCodeSignatureTypeMixin:
    def _struct_to_tuple(
        self,
        struct_def: str,
        custom_type_mapping: Optional[Dict[str, str]] = None,
        all_structs: Optional[Dict[str, str]] = None
    ) -> Optional[str]:
        """
        Convert a struct definition to its tuple representation, recursively resolving
        custom types and nested structs.

        Example:
            struct SwapDescription {
                IERC20 srcToken;      // Interface -> address
                address dstToken;
                uint256 amount;
            }

        Returns: "(address,address,uint256)" (with IERC20 resolved to address)

        Args:
            struct_def: Struct definition string
            custom_type_mapping: Optional mapping of custom types to base types
            all_structs: Optional dict of all struct definitions for recursive resolution

        Returns:
            Tuple representation or None if parsing fails
        """
        if custom_type_mapping is None:
            custom_type_mapping = {}
        if all_structs is None:
            all_structs = {}

        try:
            # Extract fields from struct body
            match = re.search(r'\{([^}]+)\}', struct_def)
            if not match:
                return None

            body = match.group(1)

            # Extract field types (first token before semicolon on each line)
            types = []
            for line in body.split(';'):
                line = line.strip()
                if not line:
                    continue
                # Split by whitespace and take first token (the type)
                tokens = line.split()
                if tokens:
                    field_type = tokens[0]

                    # Resolve types: try direct lookup first, then qualified name lookup
                    lookup_name = field_type

                    # Try direct lookup in custom types (enums, interfaces, UDVTs)
                    if lookup_name in custom_type_mapping:
                        field_type = custom_type_mapping[lookup_name]
                    # Try direct lookup in structs (recursive resolution)
                    elif lookup_name in all_structs:
                        nested_tuple = self._struct_to_tuple(all_structs[lookup_name], custom_type_mapping, all_structs)
                        if nested_tuple:
                            field_type = nested_tuple
                    # If not found and contains '.', try unqualified name (handles ANY qualified type)
                    elif '.' in lookup_name:
                        unqualified_name = lookup_name.split('.')[-1]
                        # Try custom types (enums, interfaces, UDVTs)
                        if unqualified_name in custom_type_mapping:
                            field_type = custom_type_mapping[unqualified_name]
                        # Try structs (recursive resolution)
                        elif unqualified_name in all_structs:
                            nested_tuple = self._struct_to_tuple(all_structs[unqualified_name], custom_type_mapping, all_structs)
                            if nested_tuple:
                                field_type = nested_tuple
                    # else: keep field_type as-is (primitive or unknown type)

                    # Normalize type aliases (uint -> uint256, int -> int256, etc.)
                    field_type = self._normalize_type_aliases(field_type)

                    types.append(field_type)

            if not types:
                return None

            return f"({','.join(types)})"
        except Exception as e:
            logger.debug(f"Failed to parse struct: {e}")
            return None


    def _normalize_type_aliases(self, param_type: str) -> str:
        """
        Normalize Solidity type aliases to their canonical forms.

        Solidity allows shorthand aliases:
        - uint = uint256
        - int = int256
        - ufixed = ufixed128x18
        - fixed = fixed128x18

        Args:
            param_type: Type string (may include array suffix)

        Returns:
            Normalized type string
        """
        # Handle arrays: uint[] -> normalize uint -> uint256[]
        base_type = param_type
        array_suffix = ''
        if '[' in param_type:
            bracket_pos = param_type.index('[')
            base_type = param_type[:bracket_pos]
            array_suffix = param_type[bracket_pos:]

        # Normalize type aliases
        if base_type == 'uint':
            base_type = 'uint256'
        elif base_type == 'int':
            base_type = 'int256'
        elif base_type == 'ufixed':
            base_type = 'ufixed128x18'
        elif base_type == 'fixed':
            base_type = 'fixed128x18'

        return base_type + array_suffix


    def _extract_struct_types_from_signature(self, signature: str) -> set:
        """
        Extract struct type names from a function signature.

        Args:
            signature: Function signature (e.g., "initialiseWeightBasedClaims(RewardClaimWithProof[] calldata _proofs)")

        Returns:
            Set of struct type names found in the signature
        """
        struct_types = set()

        # Extract parameter types from signature
        # Pattern: find types before variable names in function signature
        # Look for capitalized type names that could be structs (not uint256, address, etc.)
        # Handle arrays: TypeName[], TypeName[5], etc.

        # First, extract the parameters section
        param_match = re.search(r'\(([^)]*)\)', signature)
        if not param_match:
            return struct_types

        params_str = param_match.group(1)

        # Common Solidity primitive types to exclude
        primitive_types = {
            'address', 'bool', 'string', 'bytes', 'uint', 'int',
            'uint8', 'uint16', 'uint24', 'uint32', 'uint64', 'uint128', 'uint256',
            'int8', 'int16', 'int24', 'int32', 'int64', 'int128', 'int256',
            'bytes1', 'bytes2', 'bytes3', 'bytes4', 'bytes8', 'bytes16', 'bytes20', 'bytes32',
            'calldata', 'memory', 'storage'  # Storage modifiers
        }

        # Split by comma and process each parameter
        for param in params_str.split(','):
            param = param.strip()
            if not param:
                continue

            # Extract the type (first token before array brackets, storage modifier, or variable name)
            # Pattern: TypeName[] memory _varName OR TypeName _varName
            type_match = re.match(r'([A-Za-z_][A-Za-z0-9_\.]*)', param)
            if type_match:
                type_name = type_match.group(1)

                # Handle qualified names like IRewardManager.RewardClaimWithProof
                if '.' in type_name:
                    type_name = type_name.split('.')[-1]  # Take last part

                # Check if it's likely a struct (capitalized, not a primitive)
                if type_name and type_name[0].isupper() and type_name.lower() not in primitive_types:
                    struct_types.add(type_name)
                    logger.debug(f"Found potential struct type in signature: {type_name}")

        return struct_types
