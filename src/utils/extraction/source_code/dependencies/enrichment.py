"""Dependency enrichment stage after target function resolution."""

import re
from typing import Any, Dict, Optional

from ..parser import SolidityCodeParser
from ..shared import logger


def build_dependency_result(
    self,
    extracted_code: Dict[str, Any],
    target_function: Dict[str, Any],
    facet_specific_code: Optional[Dict[str, Any]],
    facet_addr: Optional[str],
    max_lines: int,
) -> Dict[str, Any]:
        # Parse function to find internal calls, library calls, and super calls
        parser = SolidityCodeParser(target_function['body'])
        internal_calls = parser.find_internal_functions_used(target_function['body'])
        library_calls = parser.find_library_calls(target_function['body'])
        super_calls = parser.find_super_calls(target_function['body'])

        # Collect dependencies
        result = {
            'function': target_function['body'],
            'function_docstring': target_function.get('docstring'),
            'custom_types': [],
            'using_statements': [],
            'libraries': [],
            'structs': [],
            'modifiers': [],  # Will store modifier code used by this function
            'internal_functions': [],  # Will store dicts with 'body' and 'docstring'
            'parent_functions': [],  # NEW: Will store parent implementations from super. calls
            'enums': [],
            'constants': [],
            'total_lines': target_function['line_count'],
            'truncated': False
        }

        # IMPORTANT: For Diamond proxies, use facet-specific dependencies (structs, enums, modifiers, etc.)
        # to avoid name collisions with unrelated structs from other facets.
        # If we found the function in a specific facet, use that facet's dependencies.
        # Otherwise, fall back to the merged extracted_code.
        if facet_specific_code:
            dependency_source = facet_specific_code
            dependency_source_name = f"facet {facet_addr[:10]}..."
            logger.info(f"  📦 Using facet-specific dependencies from {dependency_source_name}")
        else:
            dependency_source = extracted_code
            dependency_source_name = "merged source"
            logger.debug(f"  📦 Using merged dependencies (no facet-specific source)")

        # Collect all code to scan for constant references
        all_code_to_scan = [target_function['body']]

        # Add referenced structs and enums (check BOTH function body AND signature for references)
        # Get function signature to also check for struct types in parameters
        func_signature = target_function.get('signature', '')
        func_body = target_function['body']
        func_text_to_search = f"{func_signature}\n{func_body}"  # Search both signature and body

        # Track which structs we've already added
        added_structs = set()
        
        # Get source code for interface searches
        source_code = dependency_source.get('source_code', '') or extracted_code.get('source_code', '')

        # PHASE 1: Add structs directly referenced in function signature/body
        for struct_name, struct_code in dependency_source.get('structs', {}).items():
            if struct_name in func_text_to_search:
                result['structs'].append(struct_code)
                result['total_lines'] += struct_code.count('\n') + 1
                added_structs.add(struct_name)
                logger.info(f"    ✓ Including struct: {struct_name} (from {dependency_source_name})")

        # PHASE 2: Search for missing structs from signature in interfaces
        struct_types_in_signature = self._extract_struct_types_from_signature(func_signature)
        missing_structs = struct_types_in_signature - added_structs

        if missing_structs and source_code:
            logger.info(f"    🔍 Searching for missing structs in interfaces: {missing_structs}")
            for missing_struct in missing_structs:
                struct_def = self._find_struct_in_interfaces(missing_struct, source_code)
                if struct_def:
                    result['structs'].append(struct_def)
                    result['total_lines'] += struct_def.count('\n') + 1
                    added_structs.add(missing_struct)
                    logger.info(f"    ✓ Found struct in interface: {missing_struct}")
                else:
                    logger.warning(f"    ✗ Struct {missing_struct} not found in interfaces")

        # PHASE 3: RECURSIVE extraction of nested types from structs
        # This handles types like IStargate.SendParam inside StargateData
        max_iterations = 10  # Prevent infinite loops
        iteration = 0
        structs_to_process = list(result['structs'])
        processed_types = set(added_structs)
        
        while structs_to_process and iteration < max_iterations:
            iteration += 1
            # Extract nested types from current structs (including qualified names)
            nested_types = self._extract_nested_types_from_structs(structs_to_process)
            new_types = nested_types - processed_types
            
            if not new_types:
                break
                
            logger.info(f"    🔄 Iteration {iteration}: Found {len(new_types)} new nested types: {new_types}")
            structs_to_process = []  # Reset for next iteration
            
            for type_ref in new_types:
                processed_types.add(type_ref)
                
                # Handle qualified names like IStargate.SendParam
                if '.' in type_ref:
                    interface_name, struct_name = type_ref.split('.', 1)
                    struct_def = self._find_struct_in_interface(interface_name, struct_name, source_code)
                    if struct_def:
                        result['structs'].append(struct_def)
                        result['total_lines'] += struct_def.count('\n') + 1
                        added_structs.add(type_ref)
                        structs_to_process.append(struct_def)  # Process this struct for more nested types
                        logger.info(f"    ✓ Found nested struct: {type_ref}")
                    else:
                        logger.debug(f"    ⚠ Nested type {type_ref} not found in interface {interface_name}")
                else:
                    # Simple type name - search in dependency_source structs first
                    if type_ref in dependency_source.get('structs', {}):
                        struct_code = dependency_source['structs'][type_ref]
                        result['structs'].append(struct_code)
                        result['total_lines'] += struct_code.count('\n') + 1
                        added_structs.add(type_ref)
                        structs_to_process.append(struct_code)
                        logger.info(f"    ✓ Found nested struct: {type_ref} (from {dependency_source_name})")
                    else:
                        # Try interfaces
                        struct_def = self._find_struct_in_interfaces(type_ref, source_code)
                        if struct_def:
                            result['structs'].append(struct_def)
                            result['total_lines'] += struct_def.count('\n') + 1
                            added_structs.add(type_ref)
                            structs_to_process.append(struct_def)
                            logger.info(f"    ✓ Found nested struct in interface: {type_ref}")

        # PHASE 4: Check for enums in function body, signature, AND all the structs we've added
        all_text_for_enum_search = func_text_to_search + '\n' + '\n'.join(result['structs'])
        added_enums = set()

        for enum_name, enum_code in dependency_source.get('enums', {}).items():
            if enum_name in all_text_for_enum_search:
                result['enums'].append(enum_code)
                result['total_lines'] += enum_code.count('\n') + 1
                added_enums.add(enum_name)
                logger.info(f"    ✓ Including enum: {enum_name} (from {dependency_source_name})")

        # PHASE 5: Search for missing enums in interfaces
        potential_types_in_structs = self._extract_enum_types_from_structs(result['structs'])
        missing_types = potential_types_in_structs - added_enums - added_structs

        if missing_types and source_code:
            logger.info(f"    🔍 Searching for missing enums in interfaces: {missing_types}")
            for missing_type in missing_types:
                # Try as an enum
                enum_def = self._find_enum_in_interfaces(missing_type, source_code)
                if enum_def:
                    result['enums'].append(enum_def)
                    result['total_lines'] += enum_def.count('\n') + 1
                    added_enums.add(missing_type)
                    logger.info(f"    ✓ Found enum in interface: {missing_type}")
                else:
                    logger.debug(f"    ⚠ Type {missing_type} not found as enum in interfaces")

        # Add modifiers used by this function
        modifiers_used = target_function.get('modifiers', [])
        if modifiers_used:
            logger.info(f"  - Function uses modifiers: {modifiers_used}")
            for modifier_name in modifiers_used:
                if modifier_name in dependency_source.get('modifiers', {}):
                    modifier_code = dependency_source['modifiers'][modifier_name]
                    result['modifiers'].append(modifier_code)
                    result['total_lines'] += modifier_code.count('\n') + 1
                    logger.info(f"    ✓ Including modifier: {modifier_name} (from {dependency_source_name})")
                else:
                    logger.warning(f"    ✗ Modifier {modifier_name} not found in {dependency_source_name}")

        # Add referenced custom types (e.g., type TakerTraits is uint256;)
        # Also track which custom types are used to find their associated libraries
        used_custom_types = set()
        for type_name, type_code in dependency_source.get('custom_types', {}).items():
            # Check if type is referenced in function body or structs
            if type_name in target_function['body'] or any(type_name in s for s in result['structs']):
                result['custom_types'].append(type_code)
                result['total_lines'] += type_code.count('\n') + 1
                used_custom_types.add(type_name)
                logger.info(f"    ✓ Including custom type: {type_name} (from {dependency_source_name})")

        # Collect library names from library calls for using statement filtering
        referenced_library_names = set()
        for lib_call in library_calls:
            if '.' in lib_call:
                lib_name = lib_call.split('.')[0]
                referenced_library_names.add(lib_name)

        # Also find libraries associated with custom types via "using" statements
        # Pattern: "using LibraryName for CustomType;"
        for using_stmt in dependency_source.get('using_statements', []):
            for type_name in used_custom_types:
                if f"for {type_name}" in using_stmt:
                    # Extract library name from "using LibName for TypeName;"
                    match = re.search(r'using\s+(\w+)\s+for\s+' + type_name, using_stmt)
                    if match:
                        lib_name = match.group(1)
                        referenced_library_names.add(lib_name)
                        logger.info(f"    ✓ Found library {lib_name} for custom type {type_name} via using statement")

        # Add using statements related to types or libraries referenced in the function
        for using_stmt in dependency_source.get('using_statements', []):
            # Include using statements if:
            # 1. They relate to custom types we included
            # 2. They relate to libraries that are called
            should_include = False
            for type_name in [t.split()[-2] for t in result['custom_types']]:  # Extract type name from "type X is Y;"
                if type_name in using_stmt:
                    should_include = True
                    break
            if not should_include:
                for lib_name in referenced_library_names:
                    if lib_name in using_stmt:
                        should_include = True
                        break
            if should_include:
                result['using_statements'].append(using_stmt)
                result['total_lines'] += 1
                logger.info(f"    ✓ Including using statement: {using_stmt}")

        # Add internal functions that are called - WITH RECURSIVE EXTRACTION
        # PRIORITY: Search in main contract first, then in parent/other contracts
        # We need to recursively find functions called by internal functions
        processed_internal_calls = set()
        internal_calls_to_process = list(set(internal_calls))  # Start with calls from main function

        # Get main contract name for prioritization
        main_contract = target_function.get('contract_name')

        logger.info(f"  - Initial internal calls found: {internal_calls_to_process}")
        if main_contract:
            logger.debug(f"  - Will prioritize functions from main contract: {main_contract}")

        while internal_calls_to_process:
            internal_call = internal_calls_to_process.pop(0)

            # Skip if already processed
            if internal_call in processed_internal_calls:
                continue
            processed_internal_calls.add(internal_call)

            found = False
            func_to_use = None

            # PRIORITY 1: Check in internal_functions from main contract first (use dependency_source)
            if main_contract:
                for func_data in dependency_source.get('internal_functions', {}).values():
                    if func_data['name'] == internal_call and func_data.get('contract_name') == main_contract:
                        func_to_use = func_data
                        logger.info(f"    ✓ Including internal function from main contract: {internal_call}()")
                        found = True
                        break

            # PRIORITY 2: If not in main contract, check in other internal_functions (use dependency_source)
            if not found:
                # Debug: Log available internal functions
                if not found:
                    available_internal = [f"{fd.get('name')}({fd.get('contract_name', '?')})"
                                         for fd in dependency_source.get('internal_functions', {}).values()]
                    logger.info(f"    🔍 Searching for '{internal_call}' in {len(available_internal)} internal functions: {available_internal[:10]}")

                for func_data in dependency_source.get('internal_functions', {}).values():
                    if func_data['name'] == internal_call:
                        func_to_use = func_data
                        contract_src = func_data.get('contract_name', 'unknown')
                        logger.info(f"    ✓ Including internal function from {contract_src}: {internal_call}()")
                        found = True
                        break

            # PRIORITY 3: Check in public/external functions from main contract (use dependency_source)
            # NOTE: Compare signature (not just name) to allow overloaded functions with same name but different params
            if not found and main_contract:
                for func_data in dependency_source.get('functions', {}).values():
                    if func_data['name'] == internal_call and func_data.get('signature') != target_function.get('signature'):
                        if func_data.get('contract_name') == main_contract:
                            func_to_use = func_data
                            logger.info(f"    ✓ Including public function from main contract: {internal_call}() [overloaded: {func_data.get('signature')}]")
                            found = True
                            break

            # PRIORITY 4: If not found, check in all other public/external functions (use dependency_source)
            # NOTE: Compare signature (not just name) to allow overloaded functions with same name but different params
            if not found:
                for func_data in dependency_source.get('functions', {}).values():
                    if func_data['name'] == internal_call and func_data.get('signature') != target_function.get('signature'):
                        func_to_use = func_data
                        contract_src = func_data.get('contract_name', 'unknown')
                        logger.info(f"    ✓ Including public/external function from {contract_src}: {internal_call}() [overloaded: {func_data.get('signature')}]")
                        found = True
                        break

            # Process the found function
            if func_to_use:
                result['internal_functions'].append({
                    'body': func_to_use['body'],
                    'docstring': func_to_use.get('docstring')
                })
                all_code_to_scan.append(func_to_use['body'])  # Scan internal functions for constants too
                result['total_lines'] += func_to_use['line_count']

                # RECURSIVE: Find functions called BY this function
                nested_calls = parser.find_internal_functions_used(func_to_use['body'])
                for nested_call in nested_calls:
                    if nested_call not in processed_internal_calls and nested_call not in internal_calls_to_process:
                        internal_calls_to_process.append(nested_call)
                        logger.debug(f"      → Found nested call: {nested_call}()")

                # Check for super. calls in this function
                nested_super_calls = parser.find_super_calls(func_to_use['body'])
                if nested_super_calls:
                    logger.info(f"      → Found super. calls in {internal_call}(): {nested_super_calls}")
                    super_calls.extend(nested_super_calls)  # Add to the main super_calls list

                # Scan this function for library calls too
                lib_calls_in_func = parser.find_library_calls(func_to_use['body'])
                library_calls.extend(lib_calls_in_func)

            if not found:
                logger.debug(f"    ⚠ Internal call {internal_call}() not found in extracted functions")

        # Add library functions that are called (e.g., LibAsset.isNativeAsset)
        # We need to recursively scan for nested library calls
        processed_lib_calls = set()
        lib_calls_to_process = list(set(library_calls))  # Remove duplicates

        # Cache for full source code function extraction (to avoid repeated expensive parsing)
        all_funcs_cache = None

        if lib_calls_to_process:
            logger.info(f"  - Library calls found: {lib_calls_to_process}")

        while lib_calls_to_process:
            lib_call = lib_calls_to_process.pop(0)
            if lib_call in processed_lib_calls:
                continue
            processed_lib_calls.add(lib_call)

            # lib_call is in format "LibraryName.functionName"
            parts = lib_call.split('.')
            if len(parts) == 2:
                lib_name, func_name = parts

                # Skip if func_name looks like a struct/type constructor (starts with capital letter)
                # e.g., IAugustusFeeVault.FeeRegistration is a struct, not a function
                if func_name and func_name[0].isupper():
                    logger.debug(f"    ⚠ Skipping {lib_call} - appears to be a type/struct constructor, not a function")
                    continue

                found = False

                # First try: Search in dependency_source internal_functions
                for func_data in dependency_source.get('internal_functions', {}).values():
                    if func_data['name'] == func_name:
                        # Found the library function
                        result['internal_functions'].append({
                            'body': func_data['body'],
                            'docstring': func_data.get('docstring')
                        })
                        all_code_to_scan.append(func_data['body'])
                        result['total_lines'] += func_data['line_count']
                        logger.info(f"    ✓ Found library function {lib_call}")

                        # Recursively find more library calls in this library function
                        nested_lib_calls = parser.find_library_calls(func_data['body'])
                        for nested_call in nested_lib_calls:
                            if nested_call not in processed_lib_calls:
                                lib_calls_to_process.append(nested_call)
                                logger.info(f"      → Found nested library call: {nested_call}")
                        found = True
                        break

                # Second try: If not found in internal_functions, search directly in source code
                # Use facet-specific source first, fall back to merged source
                fallback_source = dependency_source.get('source_code', '') or extracted_code.get('source_code', '')
                if not found and fallback_source:
                    # Use cached extraction to avoid repeated expensive parsing
                    if all_funcs_cache is None:
                        logger.info(f"    ⚠ {func_name} not in internal_functions, parsing source code (first time)...")
                        source_parser = SolidityCodeParser(fallback_source)
                        all_funcs_cache = source_parser.extract_functions()
                        logger.debug(f"    ✓ Cached {len(all_funcs_cache)} functions from source code")
                    else:
                        logger.debug(f"    ⚠ {func_name} not in internal_functions, using cached source code...")

                    # Look for the function by name in cached results
                    for func_sig, func_data in all_funcs_cache.items():
                        if func_data['name'] == func_name:
                            lib_func_body = func_data['body']
                            result['internal_functions'].append({
                                'body': lib_func_body,
                                'docstring': func_data.get('docstring')
                            })
                            all_code_to_scan.append(lib_func_body)
                            result['total_lines'] += func_data['line_count']
                            logger.info(f"    ✓ Found library function {lib_call} via full source search")

                            # Recursively find more library calls
                            nested_lib_calls = parser.find_library_calls(lib_func_body)
                            for nested_call in nested_lib_calls:
                                if nested_call not in processed_lib_calls:
                                    lib_calls_to_process.append(nested_call)
                                    logger.info(f"      → Found nested library call: {nested_call}")
                            found = True
                            break

                if not found:
                    logger.warning(f"    ✗ Could not find library function {lib_call} in source code")

        # Add full library definitions for referenced libraries
        for lib_name in referenced_library_names:
            if lib_name in dependency_source.get('libraries', {}):
                library_code = dependency_source['libraries'][lib_name]
                result['libraries'].append(library_code)
                result['total_lines'] += library_code.count('\n') + 1
                logger.info(f"    ✓ Including full library: {lib_name} (from {dependency_source_name})")

        # Debug: Show all available constants (will be extracted after parent function processing)
        all_constants = list(dependency_source.get('constants', {}).keys())
        if all_constants:
            logger.info(f"  - Available constants in {dependency_source_name}: {', '.join(all_constants[:10])}{' ...' if len(all_constants) > 10 else ''}")

        # Handle super. calls - extract inheritance chain and find parent implementations
        # Do this AFTER collecting all internal functions so we catch super calls in nested functions
        if super_calls and extracted_code.get('source_code'):
            # Deduplicate super calls
            super_calls = list(set(super_calls))
            logger.info(f"\n🔗 INHERITANCE CHAIN FOLLOWING")
            logger.info(f"   Found {len(super_calls)} unique super. call(s): {', '.join(super_calls)}")

            # Create a full parser to get inheritance info
            full_parser = SolidityCodeParser(extracted_code['source_code'])
            inheritance_chain = full_parser.extract_inheritance_chain()

            if inheritance_chain:
                logger.info(f"   Extracted inheritance relationships:")
                for contract, parents in inheritance_chain.items():
                    logger.info(f"      {contract} → {', '.join(parents)}")

                # For each super call, search in all parent contracts
                for super_func_name in super_calls:
                    logger.info(f"\n   Searching for super.{super_func_name}() in parent contracts...")
                    found = False
                    # Search through all contracts that have parents
                    for contract_name, parents in inheritance_chain.items():
                        for parent_name in parents:
                            logger.debug(f"      Checking {parent_name}...")
                            parent_func = full_parser.find_function_in_parent(super_func_name, parent_name)
                            if parent_func:
                                result['parent_functions'].append({
                                    'body': parent_func['body'],
                                    'parent_contract': parent_name,
                                    'function_name': super_func_name
                                })
                                all_code_to_scan.append(parent_func['body'])  # Scan parent functions for constants too
                                result['total_lines'] += parent_func['line_count']
                                logger.info(f"      ✓ Found in {parent_name}.{super_func_name}() ({parent_func['line_count']} lines)")

                                # RECURSIVE: Scan parent function for internal calls, library calls, and nested super calls
                                parent_internal_calls = parser.find_internal_functions_used(parent_func['body'])
                                for nested_call in parent_internal_calls:
                                    if nested_call not in processed_internal_calls and nested_call not in internal_calls_to_process:
                                        internal_calls_to_process.append(nested_call)
                                        logger.info(f"         → Found internal call in parent: {nested_call}()")

                                # Scan for library calls in parent function
                                parent_lib_calls = parser.find_library_calls(parent_func['body'])
                                if parent_lib_calls:
                                    logger.info(f"         → Found library calls in parent: {parent_lib_calls}")
                                    library_calls.extend(parent_lib_calls)

                                # Scan for nested super calls in parent function
                                parent_super_calls = parser.find_super_calls(parent_func['body'])
                                if parent_super_calls:
                                    logger.info(f"         → Found nested super. calls in parent: {parent_super_calls}")
                                    # Add to super_calls list to be processed in the outer loop
                                    for nested_super in parent_super_calls:
                                        if nested_super not in super_calls:
                                            super_calls.append(nested_super)

                                found = True
                                break
                        if found:
                            break

                    if not found:
                        logger.warning(f"      ⚠ Could not find parent implementation for super.{super_func_name}()")
            else:
                logger.warning(f"   ⚠ No inheritance chain found in source code")
                logger.warning(f"   Cannot resolve super. calls: {super_calls}")
        elif super_calls:
            logger.warning(f"  ⚠ Found super. calls but no source code available: {super_calls}")

        # Process any internal calls discovered from parent functions
        # (parent functions are extracted above, so any new internal calls need to be processed now)
        if internal_calls_to_process:
            logger.info(f"\n🔗 PROCESSING INTERNAL CALLS FROM PARENT FUNCTIONS")
            logger.info(f"   Found {len(internal_calls_to_process)} internal call(s) to process from parent functions")

            while internal_calls_to_process:
                internal_call = internal_calls_to_process.pop(0)

                # Skip if already processed
                if internal_call in processed_internal_calls:
                    continue
                processed_internal_calls.add(internal_call)

                found = False
                func_to_use = None

                # Search for the internal function (same logic as before, using dependency_source)
                # PRIORITY 1: Check in internal_functions from main contract first
                if main_contract:
                    for func_data in dependency_source.get('internal_functions', {}).values():
                        if func_data['name'] == internal_call and func_data.get('contract_name') == main_contract:
                            func_to_use = func_data
                            logger.info(f"    ✓ Including internal function from main contract: {internal_call}()")
                            found = True
                            break

                # PRIORITY 2: If not in main contract, check in other internal_functions
                if not found:
                    for func_data in dependency_source.get('internal_functions', {}).values():
                        if func_data['name'] == internal_call:
                            func_to_use = func_data
                            contract_src = func_data.get('contract_name', 'unknown')
                            logger.info(f"    ✓ Including internal function from {contract_src}: {internal_call}()")
                            found = True
                            break

                # PRIORITY 3: Check in public/external functions from main contract
                # NOTE: Compare signature (not just name) to allow overloaded functions with same name but different params
                if not found and main_contract:
                    for func_data in dependency_source.get('functions', {}).values():
                        if func_data['name'] == internal_call and func_data.get('signature') != target_function.get('signature'):
                            if func_data.get('contract_name') == main_contract:
                                func_to_use = func_data
                                logger.info(f"    ✓ Including public function from main contract: {internal_call}() [overloaded: {func_data.get('signature')}]")
                                found = True
                                break

                # PRIORITY 4: If not found, check in all other public/external functions
                # NOTE: Compare signature (not just name) to allow overloaded functions with same name but different params
                if not found:
                    for func_data in dependency_source.get('functions', {}).values():
                        if func_data['name'] == internal_call and func_data.get('signature') != target_function.get('signature'):
                            func_to_use = func_data
                            contract_src = func_data.get('contract_name', 'unknown')
                            logger.info(f"    ✓ Including public/external function from {contract_src}: {internal_call}() [overloaded: {func_data.get('signature')}]")
                            found = True
                            break

                # Process the found function
                if func_to_use:
                    result['internal_functions'].append({
                        'body': func_to_use['body'],
                        'docstring': func_to_use.get('docstring')
                    })
                    all_code_to_scan.append(func_to_use['body'])
                    result['total_lines'] += func_to_use['line_count']

                    # RECURSIVE: Find functions called BY this function
                    nested_calls = parser.find_internal_functions_used(func_to_use['body'])
                    for nested_call in nested_calls:
                        if nested_call not in processed_internal_calls and nested_call not in internal_calls_to_process:
                            internal_calls_to_process.append(nested_call)
                            logger.debug(f"      → Found nested call: {nested_call}()")

                    # Check for super. calls in this function
                    nested_super_calls = parser.find_super_calls(func_to_use['body'])
                    if nested_super_calls:
                        logger.info(f"      → Found super. calls in {internal_call}(): {nested_super_calls}")
                        # Note: We won't process these super calls since parent extraction is already done
                        # This is a limitation - nested super calls from functions discovered via parent functions won't be followed

                    # Scan this function for library calls too
                    lib_calls_in_func = parser.find_library_calls(func_to_use['body'])
                    if lib_calls_in_func:
                        library_calls.extend(lib_calls_in_func)
                        # Add to processing queue if not already processed
                        for lib_call in lib_calls_in_func:
                            if lib_call not in processed_lib_calls:
                                lib_calls_to_process.append(lib_call)

                if not found:
                    logger.debug(f"    ⚠ Internal call {internal_call}() not found in extracted functions")

        # Process any new library calls discovered from parent functions or their internal calls
        if lib_calls_to_process:
            logger.info(f"\n🔗 PROCESSING LIBRARY CALLS FROM PARENT FUNCTIONS")
            logger.info(f"   Found {len(lib_calls_to_process)} library call(s) to process")

            while lib_calls_to_process:
                lib_call = lib_calls_to_process.pop(0)
                if lib_call in processed_lib_calls:
                    continue
                processed_lib_calls.add(lib_call)

                # lib_call is in format "LibraryName.functionName"
                parts = lib_call.split('.')
                if len(parts) == 2:
                    lib_name, func_name = parts

                    # Skip if func_name looks like a struct/type constructor (starts with capital letter)
                    # e.g., IAugustusFeeVault.FeeRegistration is a struct, not a function
                    if func_name and func_name[0].isupper():
                        logger.debug(f"    ⚠ Skipping {lib_call} - appears to be a type/struct constructor, not a function")
                        continue

                    found = False

                    # First try: Search in dependency_source internal_functions
                    for func_data in dependency_source.get('internal_functions', {}).values():
                        if func_data['name'] == func_name:
                            # Found the library function
                            result['internal_functions'].append({
                                'body': func_data['body'],
                                'docstring': func_data.get('docstring')
                            })
                            all_code_to_scan.append(func_data['body'])
                            result['total_lines'] += func_data['line_count']
                            logger.info(f"    ✓ Found library function {lib_call}")

                            # Recursively find more library calls in this library function
                            nested_lib_calls = parser.find_library_calls(func_data['body'])
                            for nested_call in nested_lib_calls:
                                if nested_call not in processed_lib_calls:
                                    lib_calls_to_process.append(nested_call)
                                    logger.info(f"      → Found nested library call: {nested_call}")
                            found = True
                            break

                    if not found:
                        logger.debug(f"    ⚠ Library function {lib_call} not found in {dependency_source_name}")

        # Re-scan all code for constants (now includes parent functions and their internal calls)
        if all_code_to_scan:
            combined_code = '\n'.join(all_code_to_scan)

            # Clear previous constants to rescan
            result['constants'] = []
            constants_found = []
            constants_to_check = []

            # First pass: find constants directly referenced in the code
            for const_name, const_decl in dependency_source.get('constants', {}).items():
                if re.search(r'\b' + re.escape(const_name) + r'\b', combined_code):
                    result['constants'].append(const_decl)
                    result['total_lines'] += 1
                    constants_found.append(const_name)
                    constants_to_check.append(const_decl)

            # Second pass: recursively find constants referenced by other constants
            processed_constants = set(constants_found)
            while constants_to_check:
                const_decl = constants_to_check.pop(0)
                for const_name, const_decl_check in dependency_source.get('constants', {}).items():
                    if const_name not in processed_constants:
                        if re.search(r'\b' + re.escape(const_name) + r'\b', const_decl):
                            result['constants'].append(const_decl_check)
                            result['total_lines'] += 1
                            constants_found.append(const_name)
                            constants_to_check.append(const_decl_check)
                            processed_constants.add(const_name)

            if constants_found:
                logger.info(f"  - Constants extracted (including from parent functions): {', '.join(constants_found)}")

        # Check if we need to truncate
        if result['total_lines'] > max_lines:
            result['truncated'] = True
            original_internal_count = len(result['internal_functions'])
            logger.warning(
                f"⚠️  Code extraction exceeded {max_lines} lines limit "
                f"(total: {result['total_lines']} lines). Truncating internal functions..."
            )

            # Prioritize: main function > structs/enums > internal functions
            # Keep main function always, truncate internal functions if needed
            available_lines = max_lines - target_function['line_count']
            available_lines -= sum(s.count('\n') + 1 for s in result['structs'])
            available_lines -= sum(e.count('\n') + 1 for e in result['enums'])

            if available_lines < 0:
                # Even structs/enums are too much, keep only function
                logger.warning(
                    f"  - Main function + structs/enums exceed limit. "
                    f"Keeping only main function ({target_function['line_count']} lines)"
                )
                result['structs'] = []
                result['enums'] = []
                result['internal_functions'] = []
            else:
                # Truncate internal functions
                truncated_internals = []
                for internal_func_data in result['internal_functions']:
                    func_lines = internal_func_data['body'].count('\n') + 1
                    if available_lines >= func_lines:
                        truncated_internals.append(internal_func_data)
                        available_lines -= func_lines
                    else:
                        break

                kept_count = len(truncated_internals)
                dropped_count = original_internal_count - kept_count
                result['internal_functions'] = truncated_internals

                if dropped_count > 0:
                    logger.warning(
                        f"  - Kept {kept_count}/{original_internal_count} internal functions "
                        f"({dropped_count} dropped due to line limit)"
                    )

        return result
