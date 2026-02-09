"""ERC-7730 format expansion utilities."""

from typing import Any, Dict

def expand_erc7730_format_with_refs(selector_format: Dict[str, Any], full_erc7730: Dict[str, Any], selector: str = None) -> Dict[str, Any]:
    """
    Expand ERC-7730 format to include referenced definitions, constants, and enums.

    Args:
        selector_format: The format definition for a specific selector
        full_erc7730: The complete ERC-7730 data with metadata and display sections
        selector: The function selector (e.g., "0x54840d1a") to use as key in display.formats

    Returns:
        Expanded format with inline definitions, constants, and enums, using proper ERC-7730 structure
    """
    result = {}

    # Collect referenced definitions
    referenced_defs = set()
    referenced_constants = set()
    referenced_enums = set()

    def find_refs(obj):
        """Recursively find $ref references in the format"""
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key == '$ref' and isinstance(value, str):
                    # Extract definition name from $.display.definitions._minAmountOut
                    if value.startswith('$.display.definitions.'):
                        def_name = value.replace('$.display.definitions.', '')
                        referenced_defs.add(def_name)
                    # Extract enum name from $.metadata.enums.interestRateMode
                    elif value.startswith('$.metadata.enums.'):
                        enum_name = value.replace('$.metadata.enums.', '')
                        referenced_enums.add(enum_name)
                elif isinstance(value, (dict, list)):
                    find_refs(value)
        elif isinstance(obj, list):
            for item in obj:
                find_refs(item)

    def find_constant_refs(obj):
        """Recursively find references to $.metadata.constants"""
        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(value, str) and '$.metadata.constants.' in value:
                    # Extract constant name
                    const_name = value.replace('$.metadata.constants.', '')
                    referenced_constants.add(const_name)
                elif isinstance(value, (dict, list)):
                    find_constant_refs(value)
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, str) and '$.metadata.constants.' in item:
                    const_name = item.replace('$.metadata.constants.', '')
                    referenced_constants.add(const_name)
                else:
                    find_constant_refs(item)

    # Find all references
    find_refs(selector_format)
    find_constant_refs(selector_format)

    # Also check definitions for enum and constant references
    if referenced_defs and 'display' in full_erc7730 and 'definitions' in full_erc7730['display']:
        for def_name in referenced_defs:
            if def_name in full_erc7730['display']['definitions']:
                # Check for both enum and constant references in definitions
                find_refs(full_erc7730['display']['definitions'][def_name])
                find_constant_refs(full_erc7730['display']['definitions'][def_name])

    # Build result with metadata (constants and enums) if any are referenced
    if referenced_constants or referenced_enums:
        result['metadata'] = {}

        # Add referenced constants
        if referenced_constants and 'metadata' in full_erc7730 and 'constants' in full_erc7730['metadata']:
            result['metadata']['constants'] = {}
            for const_name in referenced_constants:
                if const_name in full_erc7730['metadata']['constants']:
                    result['metadata']['constants'][const_name] = full_erc7730['metadata']['constants'][const_name]

        # Add referenced enums
        if referenced_enums and 'metadata' in full_erc7730 and 'enums' in full_erc7730['metadata']:
            result['metadata']['enums'] = {}
            for enum_name in referenced_enums:
                if enum_name in full_erc7730['metadata']['enums']:
                    result['metadata']['enums'][enum_name] = full_erc7730['metadata']['enums'][enum_name]

    # Build result with display section (definitions + formats)
    if referenced_defs or selector_format:
        if 'display' not in result:
            result['display'] = {}

        # Add referenced definitions
        if referenced_defs:
            result['display']['definitions'] = {}
            if 'display' in full_erc7730 and 'definitions' in full_erc7730['display']:
                for def_name in referenced_defs:
                    if def_name in full_erc7730['display']['definitions']:
                        result['display']['definitions'][def_name] = full_erc7730['display']['definitions'][def_name]

        # Add the selector format in proper ERC-7730 structure: display.formats[selector]
        if selector_format:
            result['display']['formats'] = {}
            # Use selector as key if provided, otherwise use $id or fallback
            format_key = selector or selector_format.get('$id', 'unknown')
            result['display']['formats'][format_key] = selector_format

    return result

