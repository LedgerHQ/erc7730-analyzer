"""Target function resolution stage for dependency extraction."""

import re
from typing import Any, Dict, Optional, Tuple

from ..parser import SolidityCodeParser
from ..shared import logger


def resolve_target_function(
    self,
    function_name: str,
    extracted_code: Dict[str, Any],
    function_signature: Optional[str],
    selector_only: bool,
    selector: Optional[str],
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[str], Optional[Dict[str, Any]]]:
        # Find the function
        target_function = None
        source_text = extracted_code.get('source_code') or ""
        
        # For Diamond proxies: try to use facet-specific source code for faster lookups
        facet_specific_code = None
        facet_source_text = None
        facet_addr = None
        if selector:
            selector_to_facet = extracted_code.get('_selector_to_facet', {})
            per_facet_codes = extracted_code.get('_per_facet_codes', {})
            
            # DEBUG: Log what's available
            logger.info(f"  🔍 DEBUG: _selector_to_facet has {len(selector_to_facet)} mappings, _per_facet_codes has {len(per_facet_codes)} facets")
            
            facet_addr = selector_to_facet.get(selector)
            logger.debug(f"  🔍 DEBUG: Looking for facet_addr={facet_addr}, per_facet_codes keys={list(per_facet_codes.keys())[:3]}...")
            if facet_addr and facet_addr in per_facet_codes:
                facet_specific_code = per_facet_codes[facet_addr]
                facet_source_text = facet_specific_code.get('source_code', '')
                facet_func_count = len(facet_specific_code.get('functions', {}))
                facet_struct_count = len(facet_specific_code.get('structs', {}))
                facet_struct_names = list(facet_specific_code.get('structs', {}).keys())
                logger.info(f"  🎯 Using facet-specific source for {selector} (facet: {facet_addr[:10]}..., {facet_func_count} functions, {facet_struct_count} structs)")
                logger.info(f"  🎯 Facet-specific structs: {facet_struct_names[:10]}{'...' if len(facet_struct_names) > 10 else ''}")
            elif facet_addr:
                logger.warning(f"  ⚠ Facet {facet_addr[:10]}... not in per_facet_codes (has {len(per_facet_codes)} facets)")
            elif selector_to_facet:
                logger.warning(f"  ⚠ Selector {selector} not in selector_to_facet mapping (has {len(selector_to_facet)} selectors)")
            else:
                logger.debug(f"  No _selector_to_facet mapping available - using full merged source")

        # Get custom types mapping for resolving type aliases
        custom_types = extracted_code.get('custom_types', {})
        custom_type_mapping = {}
        for type_name, type_decl in custom_types.items():
            # Extract base type from "type TypeName is BaseType;"
            match = re.search(r'type\s+\w+\s+is\s+([^;]+);', type_decl)
            if match:
                base_type = match.group(1).strip()
                custom_type_mapping[type_name] = base_type
                logger.debug(f"  Custom type mapping: {type_name} -> {base_type}")

        # IMPORTANT: For Diamond proxies, prefer facet-specific types to avoid name collisions
        # The same struct name can have DIFFERENT definitions in different facets!
        type_source = facet_specific_code if facet_specific_code else extracted_code
        type_source_name = f"facet {facet_addr[:10]}..." if (facet_specific_code and facet_addr) else "merged source"
        
        # Add interfaces and contracts (they all map to address in ABI)
        interfaces = type_source.get('interfaces', [])
        for interface_name in interfaces:
            custom_type_mapping[interface_name] = 'address'
            logger.debug(f"  Interface/Contract mapping: {interface_name} -> address")

        # Add enums (they all map to uint8 in ABI)
        enums = type_source.get('enums', {})
        for enum_name in enums.keys():
            custom_type_mapping[enum_name] = 'uint8'
            logger.debug(f"  Enum mapping: {enum_name} -> uint8")

        # Get struct mapping for resolving struct types to tuples
        # CRITICAL: Use facet-specific structs to avoid wrong definitions from other facets
        structs = type_source.get('structs', {})
        logger.info(f"  📚 Found {len(structs)} structs to map from {type_source_name}: {list(structs.keys())}")
        
        # DEBUG: Log actual StargateData definition if present
        if 'StargateData' in structs:
            logger.info(f"  🔍 DEBUG StargateData raw definition from {type_source_name}:")
            logger.info(f"  {structs['StargateData'][:500]}...")
            if facet_addr:
                logger.info(f"  🔍 DEBUG: Facet address used = {facet_addr}")
        struct_type_mapping = {}
        for struct_name, struct_def in structs.items():
            # Extract tuple representation from struct, resolving custom types and nested structs
            tuple_repr = self._struct_to_tuple(struct_def, custom_type_mapping, structs)
            if tuple_repr:
                struct_type_mapping[struct_name] = tuple_repr
                logger.info(f"  📦 Struct mapping: {struct_name} -> {tuple_repr}")
            else:
                logger.warning(f"  ⚠️  Failed to parse struct: {struct_name}")

        # Pre-cache extracted functions for fast lookup (avoid O(n) scans)
        all_functions_cache = extracted_code.get('functions', {}) or {}
        functions_by_name = extracted_code.get('_functions_by_name')
        if functions_by_name is None:
            functions_by_name = {}
            for func_data in all_functions_cache.values():
                functions_by_name.setdefault(func_data['name'], []).append(func_data)
            extracted_code['_functions_by_name'] = functions_by_name
        
        # Build facet-specific functions cache if using facet-specific code
        facet_functions_by_name = {}
        if facet_specific_code:
            for func_data in facet_specific_code.get('functions', {}).values():
                facet_functions_by_name.setdefault(func_data['name'], []).append(func_data)

        # If signature is provided, normalize it for comparison
        normalized_target_sig = None
        if function_signature:
            normalized_target_sig = self._normalize_signature_for_matching(function_signature, custom_type_mapping, struct_type_mapping)
            logger.info(f"  Looking for function with normalized signature: {normalized_target_sig}")

        # Get main contract name and build inheritance hierarchy
        # For Diamond proxies: use facet-specific contract name if available
        main_contract_name = extracted_code.get('contract_name')
        if facet_specific_code and facet_specific_code.get('contract_name'):
            main_contract_name = facet_specific_code.get('contract_name')
            logger.info(f"  Using facet contract name: {main_contract_name}")

        # Extract inheritance relationships from source code
        # For Diamond proxies: use facet source code for inheritance parsing
        source_for_parsing = facet_source_text if facet_source_text else extracted_code.get('source_code', '')
        parser = SolidityCodeParser(source_for_parsing)
        inheritance_map = parser.extract_inheritance_chain()

        # DEBUG: Log inheritance extraction results
        logger.info(f"  🔍 DEBUG: main_contract_name = '{main_contract_name}'")
        logger.info(f"  🔍 DEBUG: inheritance_map = {inheritance_map}")

        # Auto-detect main contract if not provided
        # The main contract is the "leaf" - appears in inheritance_map but isn't a parent of others
        if not main_contract_name and inheritance_map:
            # Find all contracts that are parents
            all_parents = set()
            for parents in inheritance_map.values():
                all_parents.update(parents)

            # Main contract candidates: in inheritance_map but not a parent of others
            candidates = [name for name in inheritance_map.keys() if name not in all_parents]

            if candidates:
                # If multiple candidates, prefer the first one (usually the main contract)
                main_contract_name = candidates[0]
                logger.info(f"  Auto-detected main contract: {main_contract_name} (from {len(candidates)} candidates)")
                if len(candidates) > 1:
                    logger.info(f"  Other contract candidates: {candidates[1:]}")

        # Build full inheritance hierarchy (main -> parents -> grandparents -> ...)
        inheritance_hierarchy = []
        if main_contract_name:
            inheritance_hierarchy = self._build_inheritance_hierarchy(main_contract_name, inheritance_map)
            logger.info(f"  🔍 DEBUG: Built inheritance_hierarchy = {inheritance_hierarchy}")
            if len(inheritance_hierarchy) > 1:
                logger.info(f"  Inheritance hierarchy: {' -> '.join(inheritance_hierarchy)}")
        else:
            logger.warning(f"  ⚠️  No main_contract_name - cannot build inheritance hierarchy")

        # Compute target selector if signature is provided
        target_selector = None
        if normalized_target_sig:
            target_selector = self._compute_function_selector(
                normalized_target_sig,
                custom_type_mapping,
                struct_type_mapping
            )
            logger.info(f"  Target selector: {target_selector}")

        # Collect all matching candidates (by name and visibility) using cached lookup
        # For Diamond proxies with facet-specific code, prefer facet functions
        if facet_functions_by_name:
            all_candidates = [
                f for f in facet_functions_by_name.get(function_name, [])
                if f['visibility'] in ['public', 'external']
            ]
            if all_candidates:
                logger.info(f"  Found {len(all_candidates)} candidates in facet-specific code")
            else:
                # Fallback to merged functions
                all_candidates = [
                    f for f in functions_by_name.get(function_name, [])
                    if f['visibility'] in ['public', 'external']
                ]
                logger.info(f"  No facet candidates, using {len(all_candidates)} from merged code")
        else:
            all_candidates = [
                f for f in functions_by_name.get(function_name, [])
                if f['visibility'] in ['public', 'external']
            ]

        # Filter out interface definitions (contract_name = None)
        contract_candidates = [f for f in all_candidates if f.get('contract_name') is not None]

        if not contract_candidates:
            logger.warning(f"  All {len(all_candidates)} matching functions are interface definitions")
            contract_candidates = all_candidates

        logger.info(f"  Found {len(contract_candidates)} candidate functions with name '{function_name}'")

        # DEBUG: Check Phase 1 condition
        logger.info(f"  🔍 DEBUG: target_selector={target_selector}, inheritance_hierarchy={inheritance_hierarchy}")
        logger.info(f"  🔍 DEBUG: Phase 1 condition check - target_selector: {bool(target_selector)}, inheritance_hierarchy: {bool(inheritance_hierarchy)}")

        # PHASE 1: Try to match by EXACT SELECTOR following inheritance hierarchy
        target_function = None
        if target_selector and inheritance_hierarchy:
            logger.info(f"  Phase 1: Searching by selector {target_selector} following inheritance chain...")
            for contract_name in inheritance_hierarchy:
                # Find candidates in this contract
                contract_funcs = [f for f in contract_candidates if f.get('contract_name') == contract_name]
                if not contract_funcs:
                    continue

                # Check if any have matching selector
                for func in contract_funcs:
                    # Skip functions without signature (interface definitions)
                    if 'signature' not in func:
                        continue

                    func_sig = self._normalize_signature_for_matching(
                        func['signature'],
                        custom_type_mapping,
                        struct_type_mapping
                    )
                    func_selector = self._compute_function_selector(
                        func_sig,
                        custom_type_mapping,
                        struct_type_mapping
                    )

                    # Debug logging to diagnose selector mismatch
                    logger.info(f"    Checking: {func['signature'][:80]}...")
                    logger.info(f"      Normalized: {func_sig[:80]}...")
                    logger.info(f"      Computed selector: {func_selector} (target: {target_selector})")

                    if func_selector == target_selector:
                        # Found exact selector match!
                        target_function = func
                        logger.info(f"  ✓ Found exact selector match in {contract_name}: {func['signature']}")
                        break

                if target_function:
                    break
        else:
            logger.info(f"  ⚠️  Phase 1 SKIPPED - target_selector: {bool(target_selector)}, inheritance_hierarchy: {inheritance_hierarchy}")
            
            # PHASE 1b: If we have facet-specific candidates but no inheritance hierarchy,
            # still try to match by selector directly
            if target_selector and contract_candidates and not target_function:
                logger.info(f"  Phase 1b: Checking {len(contract_candidates)} candidates by selector (no inheritance)...")
                for func in contract_candidates:
                    # Compute selector for this function
                    func_sig = self._normalize_signature_for_matching(func.get('signature', ''))
                    if not func_sig:
                        continue
                    
                    func_selector = self._compute_function_selector(
                        func_sig,
                        custom_type_mapping,
                        struct_type_mapping
                    )
                    
                    logger.debug(f"    Checking: {func['signature'][:60]}... -> {func_selector}")
                    
                    if func_selector == target_selector:
                        # Found exact selector match!
                        target_function = func
                        contract_name = func.get('contract_name', 'Unknown')
                        logger.info(f"  ✓ Found selector match: {contract_name}.{func.get('name', 'unknown')} (line {func.get('start_line', 0)})")
                        break

        # PHASE 2: If no selector match, try to match by NAME following inheritance hierarchy
        if not target_function and not selector_only and inheritance_hierarchy:
            logger.info(f"  Phase 2: Searching by name following inheritance chain...")
            for contract_name in inheritance_hierarchy:
                # Find candidates in this contract
                contract_funcs = [f for f in contract_candidates if f.get('contract_name') == contract_name]
                if not contract_funcs:
                    continue

                # Prefer non-virtual functions
                non_virtual = [f for f in contract_funcs if not f.get('is_virtual', False)]
                if non_virtual:
                    target_function = non_virtual[0]
                    logger.info(f"  ✓ Found by name in {contract_name}: {target_function.get('signature', target_function.get('name', 'unknown'))} (non-virtual)")
                else:
                    target_function = contract_funcs[0]
                    logger.info(f"  ✓ Found by name in {contract_name}: {target_function.get('signature', target_function.get('name', 'unknown'))} (virtual)")
                break

        # PHASE 3: Fallback - if still not found, use old logic (prefer non-virtual, latest line)
        if not target_function and not selector_only and contract_candidates:
            logger.info(f"  Phase 3: Fallback - using non-inheritance matching...")
            non_virtual = [f for f in contract_candidates if not f.get('is_virtual', False)]
            if non_virtual:
                # Sort by line number (later = more likely to be the actual implementation)
                non_virtual.sort(key=lambda f: f.get('start_line', 0), reverse=True)
                target_function = non_virtual[0]
                logger.info(f"  ✓ Selected: {target_function.get('contract_name', 'Unknown')}.{target_function.get('name', 'unknown')} (line {target_function.get('start_line', 0)})")
            else:
                contract_candidates.sort(key=lambda f: f.get('start_line', 0), reverse=True)
                target_function = contract_candidates[0]
                logger.info(f"  ✓ Selected: {target_function.get('contract_name', 'Unknown')}.{target_function.get('name', 'unknown')} (line {target_function.get('start_line', 0)}, virtual)")

        # Log all candidates if multiple were found
        if target_function and len(contract_candidates) > 1:
            logger.debug(f"  All {len(contract_candidates)} candidates:")
            for func in contract_candidates:
                is_selected = (func == target_function)
                marker = "✓ SELECTED" if is_selected else "  "
                contract = func.get('contract_name', 'Unknown')
                is_override = "override" if func.get('is_override') else ""
                is_virtual = "virtual" if func.get('is_virtual') else ""
                modifiers = f"{is_override} {is_virtual}".strip()
                func_sig = func.get('signature', func.get('name', 'unknown'))
                logger.debug(f"    {marker} {contract}.{func_sig} {modifiers} (line {func.get('start_line', 0)})")

        if not target_function:
            if selector_only:
                logger.info(f"  No exact selector match found (selector_only mode)")
            else:
                logger.warning(f"Function {function_name} not found - no matching name or visibility")
            empty_result = {
                'function': None,
                'custom_types': [],
                'using_statements': [],
                'libraries': [],
                'structs': [],
                'internal_functions': [],
                'enums': [],
                'total_lines': 0,
                'truncated': False
            }
            return None, facet_specific_code, facet_addr, empty_result


        return target_function, facet_specific_code, facet_addr, None
