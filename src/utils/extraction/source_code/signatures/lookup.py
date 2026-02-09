"""Interface/enum/struct lookup helpers."""

import re
from typing import List, Optional, Set

from ..shared import logger


class SourceCodeSignatureLookupMixin:
    def _find_struct_in_interfaces(self, struct_name: str, source_code: str, already_found: Optional[set] = None) -> Optional[str]:
        """
        Search for a struct definition in interfaces within the source code.
        Also recursively finds nested structs referenced by the main struct.

        This is used when a struct is defined in a parent interface (inheritance chain)
        rather than in the main contract.

        Args:
            struct_name: Name of the struct to find
            source_code: Full source code including interfaces
            already_found: Set of struct names already found (to avoid infinite recursion)

        Returns:
            Struct definition string (may include multiple structs if nested) or None if not found
        """
        if already_found is None:
            already_found = set()

        # Avoid infinite recursion
        if struct_name in already_found:
            return None

        # Pattern to match the specific struct definition
        # Handles multi-line structs with nested braces
        struct_pattern = rf'struct\s+{re.escape(struct_name)}\s*\{{'

        match = re.search(struct_pattern, source_code)
        if not match:
            logger.debug(f"Struct {struct_name} not found in source code")
            return None

        # Found the start, now find the matching closing brace
        start_pos = match.start()
        brace_start = match.end() - 1  # Position of opening brace

        open_braces = 0
        i = brace_start
        struct_def = None
        while i < len(source_code):
            if source_code[i] == '{':
                open_braces += 1
            elif source_code[i] == '}':
                open_braces -= 1
                if open_braces == 0:
                    # Found matching closing brace
                    struct_def = source_code[start_pos:i + 1].strip()
                    logger.info(f"Found struct {struct_name} in interfaces")
                    break
            i += 1

        if not struct_def:
            logger.warning(f"Could not find closing brace for struct {struct_name}")
            return None

        already_found.add(struct_name)

        # Now look for nested structs in this struct's fields
        # Extract types from struct body and look for nested struct types
        nested_structs = []
        body_match = re.search(r'\{([^}]+)\}', struct_def)
        if body_match:
            body = body_match.group(1)
            # Look for capitalized type names that could be nested structs
            primitive_types = {
                'address', 'bool', 'string', 'bytes', 'uint', 'int',
                'uint8', 'uint16', 'uint24', 'uint32', 'uint64', 'uint128', 'uint256',
                'int8', 'int16', 'int24', 'int32', 'int64', 'int128', 'int256',
                'bytes1', 'bytes2', 'bytes3', 'bytes4', 'bytes8', 'bytes16', 'bytes20', 'bytes32'
            }

            for line in body.split(';'):
                line = line.strip()
                if not line:
                    continue
                # Extract type from line like "RewardClaim body" or "ClaimType claimType"
                type_match = re.match(r'([A-Za-z_][A-Za-z0-9_\.]*)', line)
                if type_match:
                    type_name = type_match.group(1)
                    # Handle qualified names
                    if '.' in type_name:
                        type_name = type_name.split('.')[-1]
                    # Check if it's likely a nested struct (capitalized, not primitive, not already found)
                    if (type_name and type_name[0].isupper() and
                            type_name.lower() not in primitive_types and
                            type_name not in already_found):
                        nested_struct_def = self._find_struct_in_interfaces(type_name, source_code, already_found)
                        if nested_struct_def:
                            nested_structs.append(nested_struct_def)

        # Combine: nested structs first, then main struct (so dependencies are defined first)
        if nested_structs:
            return '\n\n'.join(nested_structs) + '\n\n' + struct_def
        return struct_def


    def _extract_enum_types_from_structs(self, structs: List[str]) -> set:
        """
        Extract potential enum type names from struct definitions.

        Args:
            structs: List of struct definition strings

        Returns:
            Set of potential enum type names found in the structs
        """
        enum_types = set()

        # Common Solidity primitive types to exclude
        primitive_types = {
            'address', 'bool', 'string', 'bytes', 'uint', 'int',
            'uint8', 'uint16', 'uint24', 'uint32', 'uint64', 'uint128', 'uint256',
            'int8', 'int16', 'int24', 'int32', 'int64', 'int128', 'int256',
            'bytes1', 'bytes2', 'bytes3', 'bytes4', 'bytes8', 'bytes16', 'bytes20', 'bytes32'
        }

        for struct_def in structs:
            # Extract body from struct
            body_match = re.search(r'\{([^}]+)\}', struct_def)
            if not body_match:
                continue

            body = body_match.group(1)

            for line in body.split(';'):
                line = line.strip()
                if not line:
                    continue

                # Extract type from line like "ClaimType claimType"
                type_match = re.match(r'([A-Za-z_][A-Za-z0-9_\.]*)', line)
                if type_match:
                    type_name = type_match.group(1)
                    # Handle qualified names
                    if '.' in type_name:
                        type_name = type_name.split('.')[-1]

                    # Check if it's likely an enum (capitalized, not primitive)
                    # Enums in Solidity often end with "Type" or have short names
                    if (type_name and type_name[0].isupper() and
                            type_name.lower() not in primitive_types):
                        enum_types.add(type_name)
                        logger.debug(f"Found potential enum type in struct: {type_name}")

        return enum_types


    def _extract_nested_types_from_structs(self, structs: List[str]) -> set:
        """
        Extract all nested type references from struct definitions, including qualified names.
        
        This handles types like:
        - Simple types: SendParam, MessagingFee
        - Qualified types: IStargate.SendParam, IStargate.MessagingFee
        
        Args:
            structs: List of struct definition strings
            
        Returns:
            Set of type references found in the structs (both simple and qualified)
        """
        nested_types = set()
        
        # Common Solidity primitive types to exclude
        primitive_types = {
            'address', 'bool', 'string', 'bytes', 'uint', 'int',
            'uint8', 'uint16', 'uint24', 'uint32', 'uint64', 'uint128', 'uint256',
            'int8', 'int16', 'int24', 'int32', 'int64', 'int128', 'int256',
            'bytes1', 'bytes2', 'bytes3', 'bytes4', 'bytes8', 'bytes16', 'bytes20', 'bytes32',
            'payable'
        }
        
        for struct_def in structs:
            # Extract body from struct
            body_match = re.search(r'\{([^}]+)\}', struct_def)
            if not body_match:
                continue
                
            body = body_match.group(1)
            
            for line in body.split(';'):
                line = line.strip()
                if not line:
                    continue
                
                # Extract type from line - handle arrays and mappings too
                # Pattern matches: TypeName, Interface.TypeName, TypeName[], Interface.TypeName[]
                type_match = re.match(r'([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)\s*(?:\[\])?\s+\w+', line)
                if type_match:
                    type_name = type_match.group(1)
                    base_type = type_name.split('.')[0] if '.' in type_name else type_name
                    
                    # Skip primitives
                    if base_type.lower() in primitive_types:
                        continue
                    
                    # Check if it starts with uppercase (custom type/struct/interface)
                    if type_name and type_name[0].isupper():
                        nested_types.add(type_name)
                        logger.debug(f"Found nested type in struct: {type_name}")
        
        return nested_types


    def _find_struct_in_interface(self, interface_name: str, struct_name: str, source_code: str) -> Optional[str]:
        """
        Find a struct definition inside a specific interface.
        
        Args:
            interface_name: Name of the interface (e.g., 'IStargate')
            struct_name: Name of the struct to find (e.g., 'SendParam')
            source_code: Full source code
            
        Returns:
            Struct definition string or None if not found
        """
        # First find the interface definition
        interface_pattern = rf'interface\s+{re.escape(interface_name)}\s*(?:is\s+[^{{]+)?\s*\{{'
        interface_match = re.search(interface_pattern, source_code)
        
        if not interface_match:
            logger.debug(f"Interface {interface_name} not found")
            return None
        
        # Find the interface body
        start_pos = interface_match.end() - 1
        open_braces = 0
        interface_end = start_pos
        
        for i in range(start_pos, len(source_code)):
            if source_code[i] == '{':
                open_braces += 1
            elif source_code[i] == '}':
                open_braces -= 1
                if open_braces == 0:
                    interface_end = i + 1
                    break
        
        interface_body = source_code[start_pos:interface_end]
        
        # Now search for the struct within the interface body
        struct_pattern = rf'struct\s+{re.escape(struct_name)}\s*\{{'
        struct_match = re.search(struct_pattern, interface_body)
        
        if not struct_match:
            logger.debug(f"Struct {struct_name} not found in interface {interface_name}")
            return None
        
        # Extract the full struct definition
        struct_start = struct_match.start()
        brace_start = struct_match.end() - 1
        open_braces = 0
        
        for i in range(brace_start, len(interface_body)):
            if interface_body[i] == '{':
                open_braces += 1
            elif interface_body[i] == '}':
                open_braces -= 1
                if open_braces == 0:
                    struct_def = interface_body[struct_start:i + 1].strip()
                    logger.info(f"Found struct {interface_name}.{struct_name} in interface")
                    return struct_def
        
        return None


    def _find_enum_in_interfaces(self, enum_name: str, source_code: str) -> Optional[str]:
        """
        Search for an enum definition in interfaces within the source code.

        Args:
            enum_name: Name of the enum to find
            source_code: Full source code including interfaces

        Returns:
            Enum definition string or None if not found
        """
        # Pattern to match the specific enum definition
        # Handles multi-line enums with nested content
        enum_pattern = rf'enum\s+{re.escape(enum_name)}\s*\{{'

        match = re.search(enum_pattern, source_code)
        if not match:
            logger.debug(f"Enum {enum_name} not found in source code")
            return None

        # Found the start, now find the matching closing brace
        start_pos = match.start()
        brace_start = match.end() - 1  # Position of opening brace

        open_braces = 0
        i = brace_start
        while i < len(source_code):
            if source_code[i] == '{':
                open_braces += 1
            elif source_code[i] == '}':
                open_braces -= 1
                if open_braces == 0:
                    # Found matching closing brace
                    enum_def = source_code[start_pos:i + 1].strip()
                    logger.info(f"Found enum {enum_name} in interfaces")
                    return enum_def
            i += 1

        logger.warning(f"Could not find closing brace for enum {enum_name}")
        return None
