"""Selector computation and inheritance-aware signature normalization."""

from typing import Dict, List, Optional, Set

from eth_utils import keccak

from ..shared import logger


class SourceCodeSignatureSelectorMixin:
    def _compute_function_selector(
        self,
        function_signature: str,
        custom_type_mapping: Optional[Dict[str, str]] = None,
        struct_type_mapping: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Compute the 4-byte function selector from a function signature.

        Args:
            function_signature: Function signature (e.g., "mint(uint256,address)")
            custom_type_mapping: Optional mapping of custom types to base types
            struct_type_mapping: Optional mapping of struct types to tuple representations

        Returns:
            Function selector as hex string (e.g., "0x40c10f19")
        """
        # Normalize the signature to handle custom types and structs
        normalized_sig = self._normalize_signature_for_matching(
            function_signature,
            custom_type_mapping or {},
            struct_type_mapping or {}
        )

        # Compute keccak256 hash and take first 4 bytes
        selector = "0x" + keccak(text=normalized_sig).hex()[:8]
        return selector


    def _build_inheritance_hierarchy(
        self,
        contract_name: str,
        inheritance_map: Dict[str, List[str]]
    ) -> List[str]:
        """
        Build the full inheritance hierarchy for a contract, ordered by priority.

        The order is: [contract_name, direct_parents..., grandparents..., etc.]
        This follows the C3 linearization (MRO) used by Solidity.

        Args:
            contract_name: Name of the contract
            inheritance_map: Dict mapping contract names to their direct parents

        Returns:
            List of contract names in priority order (from most specific to most general)
        """
        if not contract_name:
            return []

        # Use depth-first search with post-order traversal to build hierarchy
        visited: Set[str] = set()
        hierarchy: List[str] = []

        def dfs(current: str):
            if current in visited:
                return
            visited.add(current)

            # Visit parents first (depth-first)
            parents = inheritance_map.get(current, [])
            for parent in parents:
                dfs(parent)

            # Add current contract after visiting all parents (post-order)
            # This ensures parents come before the contract that inherits from them
            if current not in hierarchy:
                hierarchy.append(current)

        dfs(contract_name)

        # Reverse to get priority order: most specific (child) first, most general (base) last
        hierarchy.reverse()

        logger.debug(f"Built inheritance hierarchy for {contract_name}: {hierarchy}")
        return hierarchy


    def _normalize_signature_for_matching(
        self,
        signature: str,
        custom_type_mapping: Optional[Dict[str, str]] = None,
        struct_type_mapping: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Normalize a function signature to just function name and parameter types for matching.

        Converts:
        - "approve(uint256 proposalId, uint256 index)" -> "approve(uint256,uint256)"
        - "approve(uint256,uint256)" -> "approve(uint256,uint256)"
        - "transfer(address memory to, uint256 amount)" -> "transfer(address,uint256)"
        - "swap(Address dex, uint256 amount)" -> "swap(uint256,uint256)" (if Address maps to uint256)
        - "swap(SwapDescription desc)" -> "swap((address,address,uint256))" (if struct is defined)

        Args:
            signature: Function signature with or without parameter names
            custom_type_mapping: Optional dict mapping custom type names to their underlying types
                                 (e.g., {'Address': 'uint256', 'TakerTraits': 'uint256'})
            struct_type_mapping: Optional dict mapping struct names to their tuple representations
                                (e.g., {'SwapDescription': '(address,address,uint256)'})

        Returns:
            Normalized signature with only types, custom types and structs resolved
        """
        if custom_type_mapping is None:
            custom_type_mapping = {}
        if struct_type_mapping is None:
            struct_type_mapping = {}
        if '(' not in signature or ')' not in signature:
            return signature

        func_name = signature[:signature.index('(')]
        params_str = signature[signature.index('(') + 1:signature.rindex(')')]

        if not params_str.strip():
            return f"{func_name}()"

        # Split parameters by comma, but respect parentheses for tuple types
        params = []
        current_param = []
        paren_depth = 0

        for char in params_str:
            if char == '(':
                paren_depth += 1
                current_param.append(char)
            elif char == ')':
                paren_depth -= 1
                current_param.append(char)
            elif char == ',' and paren_depth == 0:
                # Top-level comma - parameter separator
                params.append(''.join(current_param).strip())
                current_param = []
            else:
                current_param.append(char)

        # Don't forget the last parameter
        if current_param:
            params.append(''.join(current_param).strip())

        # Extract only the type (first token) from each parameter
        types = []
        for param in params:
            if not param:
                continue
            # For tuple types like "(address,address,uint256) paramName", split and take just the tuple
            if param.startswith('('):
                # Find the closing parenthesis
                paren_depth = 0
                tuple_end = 0
                for i, char in enumerate(param):
                    if char == '(':
                        paren_depth += 1
                    elif char == ')':
                        paren_depth -= 1
                        if paren_depth == 0:
                            tuple_end = i + 1
                            break
                # Extract just the tuple type (including closing paren)
                tuple_type = param[:tuple_end]
                # Check if there's an array bracket after the tuple
                remaining = param[tuple_end:].strip()
                if remaining.startswith('['):
                    # Handle tuple arrays like "(uint256,uint256)[]"
                    bracket_end = remaining.find(']') + 1
                    tuple_type += remaining[:bracket_end]
                types.append(tuple_type)
            else:
                # Remove storage location keywords and parameter names
                # Split by whitespace and take the first token (the type)
                tokens = param.split()
                if tokens:
                    param_type = tokens[0]
                    # Handle array types: might be split like "uint256 [ ]" or "uint256[]"
                    if len(tokens) > 1 and tokens[1].startswith('['):
                        param_type += tokens[1]

                    # Resolve custom types to their underlying types
                    # Handle arrays: "CustomType[]" -> resolve CustomType, keep []
                    base_type = param_type
                    array_suffix = ''
                    if '[' in param_type:
                        bracket_pos = param_type.index('[')
                        base_type = param_type[:bracket_pos]
                        array_suffix = param_type[bracket_pos:]

                    # Resolve types: try direct lookup first, then qualified name lookup
                    resolved_type = None
                    lookup_name = base_type

                    # Try direct lookup in custom types (enums, interfaces, UDVTs)
                    if lookup_name in custom_type_mapping:
                        resolved_type = custom_type_mapping[lookup_name]
                        logger.debug(f"    Resolved type: {base_type}{array_suffix} -> {resolved_type}{array_suffix}")
                    # Try direct lookup in structs
                    elif lookup_name in struct_type_mapping:
                        resolved_type = struct_type_mapping[lookup_name]
                        logger.debug(f"    Resolved struct type: {base_type}{array_suffix} -> {resolved_type}{array_suffix}")
                    # If not found and contains '.', try unqualified name (handles ANY qualified type)
                    elif '.' in lookup_name:
                        unqualified_name = lookup_name.split('.')[-1]
                        # Try custom types (enums, interfaces, UDVTs)
                        if unqualified_name in custom_type_mapping:
                            resolved_type = custom_type_mapping[unqualified_name]
                            logger.debug(f"    Resolved qualified type: {base_type}{array_suffix} -> {resolved_type}{array_suffix}")
                        # Try structs
                        elif unqualified_name in struct_type_mapping:
                            resolved_type = struct_type_mapping[unqualified_name]
                            logger.debug(f"    Resolved qualified struct type: {base_type}{array_suffix} -> {resolved_type}{array_suffix}")

                    # Apply resolved type or keep original
                    if resolved_type:
                        param_type = resolved_type + array_suffix
                    # else: keep param_type as-is (primitive or unknown type)

                    # Normalize type aliases (uint -> uint256, int -> int256, etc.)
                    param_type = self._normalize_type_aliases(param_type)

                    types.append(param_type)

        return f"{func_name}({','.join(types)})"
