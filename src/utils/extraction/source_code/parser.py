"""Solidity source parser used by extraction and dependency resolution flows."""

import re
from typing import Any, Dict, List, Optional

from .shared import logger

class SolidityCodeParser:
    """Parser for extracting functions, structs, and internal functions from Solidity code.

    Note: For Vyper contracts, use SourceCodeExtractor.extract_vyper_functions() instead.
    """

    def __init__(self, source_code: str):
        """
        Initialize parser with source code.

        Args:
            source_code: Full Solidity source code
        """
        self.source_code = source_code
        self.cleaned_code = self._remove_comments(source_code)

    @staticmethod
    def _remove_comments(text: str) -> str:
        """Remove comments from Solidity code."""
        # Remove block comments
        text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
        # Remove line comments
        text = re.sub(r'//.*', '', text)
        return text

    def extract_interfaces(self) -> List[str]:
        """
        Extract all interface names from the code.

        Interfaces and contracts used as types always map to 'address' in the ABI.

        Returns:
            List of interface names
        """
        interfaces = []

        # Pattern to match interface definitions
        interface_pattern = r'interface\s+(\w+)\s*\{'

        for match in re.finditer(interface_pattern, self.cleaned_code):
            interface_name = match.group(1)
            interfaces.append(interface_name)
            logger.debug(f"Found interface: {interface_name}")

        # Also match abstract contracts and regular contracts (they can be used as types too)
        contract_pattern = r'(?:abstract\s+)?contract\s+(\w+)\s*(?:is\s+[^{]+)?\s*\{'

        for match in re.finditer(contract_pattern, self.cleaned_code):
            contract_name = match.group(1)
            interfaces.append(contract_name)
            logger.debug(f"Found contract type: {contract_name}")

        return interfaces

    def extract_structs(self) -> Dict[str, str]:
        """
        Extract all struct definitions from the code.

        Returns:
            Dictionary mapping struct name to struct definition
        """
        structs = {}

        # Pattern to match struct definitions
        struct_pattern = r'struct\s+(\w+)\s*\{([^}]+)\}'

        for match in re.finditer(struct_pattern, self.cleaned_code):
            struct_name = match.group(1)
            struct_body = match.group(0)
            
            # IMPORTANT: Detect duplicate struct definitions (common in flattened source)
            if struct_name in structs:
                old_def = structs[struct_name][:100]
                new_def = struct_body[:100]
                if old_def != new_def:
                    logger.warning(f"⚠️  DUPLICATE STRUCT '{struct_name}' - definitions differ!")
                    logger.warning(f"   OLD: {old_def}...")
                    logger.warning(f"   NEW: {new_def}...")
                    logger.warning(f"   Using FIRST definition (ignoring later duplicate)")
                    continue  # Skip the duplicate - keep first definition
            
            structs[struct_name] = struct_body.strip()
            logger.debug(f"Found struct: {struct_name}")

        return structs

    def extract_enums(self) -> Dict[str, str]:
        """
        Extract all enum definitions from the code.

        Returns:
            Dictionary mapping enum name to enum definition
        """
        enums = {}

        enum_pattern = r'enum\s+(\w+)\s*\{([^}]+)\}'

        for match in re.finditer(enum_pattern, self.cleaned_code):
            enum_name = match.group(1)
            enum_body = match.group(0)
            enums[enum_name] = enum_body.strip()
            logger.debug(f"Found enum: {enum_name}")

        return enums

    def extract_constants(self) -> Dict[str, str]:
        """
        Extract all constant declarations from the code.

        Returns:
            Dictionary mapping constant name to constant declaration
        """
        constants = {}

        # Pattern to match constant declarations - handle both orders of visibility and constant
        # Matches: type constant NAME = value;
        # Matches: type internal constant NAME = value;
        # Matches: type constant internal NAME = value;
        # Pattern: type [internal/private/public] constant [internal/private/public] NAME = value;
        constant_pattern = r'(\w+)\s+(?:internal\s+|private\s+|public\s+)?constant\s+(?:internal\s+|private\s+|public\s+)?(\w+)\s*=\s*([^;]+);'

        for match in re.finditer(constant_pattern, self.cleaned_code):
            const_type = match.group(1)
            const_name = match.group(2)
            const_value = match.group(3).strip()
            const_decl = f"{const_type} constant {const_name} = {const_value};"
            constants[const_name] = const_decl
            if 'NATIVE' in const_name or 'ASSET' in const_name:
                logger.info(f"Found constant: {const_name} = {const_value}")
            else:
                logger.debug(f"Found constant: {const_name}")

        # Also check if the source code contains NATIVE_ASSETID but we didn't extract it
        if 'NATIVE_ASSETID' in self.cleaned_code and 'NATIVE_ASSETID' not in constants:
            logger.warning("⚠️  Source contains 'NATIVE_ASSETID' but it wasn't extracted by regex!")
            # Try to find it manually
            lines_with_native = [line.strip() for line in self.cleaned_code.split('\n') if 'NATIVE_ASSETID' in line and '=' in line]
            if lines_with_native:
                logger.info(f"Lines containing NATIVE_ASSETID: {lines_with_native[:3]}")

        return constants

    def extract_custom_types(self) -> Dict[str, str]:
        """
        Extract all custom type definitions from the code.

        Custom types are user-defined types like: type TakerTraits is uint256;

        Returns:
            Dictionary mapping type name to type declaration
        """
        custom_types = {}

        # Pattern to match: type TypeName is BaseType;
        type_pattern = r'type\s+(\w+)\s+is\s+([^;]+);'

        for match in re.finditer(type_pattern, self.cleaned_code):
            type_name = match.group(1)
            type_decl = match.group(0).strip()
            custom_types[type_name] = type_decl
            logger.debug(f"Found custom type: {type_name}")

        return custom_types

    def extract_using_statements(self) -> List[str]:
        """
        Extract all 'using' statements from the code.

        Using statements attach library functions to types: using LibName for TypeName;

        Returns:
            List of using statement strings
        """
        using_statements = []

        # Pattern to match: using LibName for TypeName;
        using_pattern = r'using\s+\w+\s+for\s+[^;]+;'

        for match in re.finditer(using_pattern, self.cleaned_code):
            using_stmt = match.group(0).strip()
            using_statements.append(using_stmt)
            logger.debug(f"Found using statement: {using_stmt}")

        return using_statements

    def extract_modifiers(self) -> Dict[str, str]:
        """
        Extract all modifier definitions from the code.

        Returns:
            Dictionary mapping modifier name to modifier code
        """
        modifiers = {}

        # Pattern to match modifier definitions
        # modifier modifierName(params) { body }
        modifier_pattern = r'modifier\s+(\w+)\s*\(([^)]*)\)\s*\{'

        for match in re.finditer(modifier_pattern, self.source_code):
            modifier_name = match.group(1)
            start_pos = match.start()
            body_start = match.end() - 1  # Position of opening brace

            # Find matching closing brace
            open_braces = 0
            i = body_start
            while i < len(self.source_code):
                if self.source_code[i] == '{':
                    open_braces += 1
                elif self.source_code[i] == '}':
                    open_braces -= 1
                    if open_braces == 0:
                        body_end = i + 1
                        break
                i += 1
            else:
                body_end = len(self.source_code)

            modifier_body = self.source_code[start_pos:body_end]
            modifiers[modifier_name] = modifier_body.strip()
            logger.debug(f"Found modifier: {modifier_name}")

        return modifiers

    def extract_libraries(self) -> Dict[str, str]:
        """
        Extract all library definitions from the code.

        Returns:
            Dictionary mapping library name to full library code
        """
        libraries = {}

        # Pattern to match library declaration
        library_pattern = r'library\s+(\w+)\s*\{'

        for match in re.finditer(library_pattern, self.source_code):
            library_name = match.group(1)
            start_pos = match.start()
            body_start = match.end() - 1  # Position of opening brace

            # Find matching closing brace
            open_braces = 0
            i = body_start
            while i < len(self.source_code):
                if self.source_code[i] == '{':
                    open_braces += 1
                elif self.source_code[i] == '}':
                    open_braces -= 1
                    if open_braces == 0:
                        body_end = i + 1
                        break
                i += 1
            else:
                body_end = len(self.source_code)

            library_body = self.source_code[start_pos:body_end]
            libraries[library_name] = library_body.strip()
            logger.debug(f"Found library: {library_name}")

        return libraries

    def extract_functions(self) -> Dict[str, Dict[str, Any]]:
        """
        Extract all function definitions (public, external, internal, private).

        Returns:
            Dictionary mapping function signature to function data:
            {
                'name': str,
                'visibility': str,
                'signature': str,
                'body': str,
                'docstring': Optional[str],
                'start_line': int,
                'end_line': int
            }
        """
        functions = {}

        # Pattern to match function declarations
        # First find: function name(
        # Then manually balance parentheses to handle nested params
        function_start_pattern = r'function\s+(\w+)\s*\('

        for match in re.finditer(function_start_pattern, self.source_code):
            function_name = match.group(1)

            # Find matching closing parenthesis by balancing
            paren_start = match.end() - 1  # Position of opening (
            paren_count = 1
            i = match.end()
            params_end = None

            while i < len(self.source_code) and paren_count > 0:
                if self.source_code[i] == '(':
                    paren_count += 1
                elif self.source_code[i] == ')':
                    paren_count -= 1
                    if paren_count == 0:
                        params_end = i
                        break
                i += 1

            if params_end is None:
                continue  # Malformed function, skip

            # Extract parameters
            params_raw = self.source_code[match.end():params_end].strip()

            # Find visibility block and opening brace
            # Look for { after the closing )
            remainder = self.source_code[params_end + 1:]
            brace_match = re.search(r'^([^{]*)\{', remainder)

            if not brace_match:
                continue  # No opening brace found, skip

            visibility_block = brace_match.group(1).strip()

            # Clean comments from params for signature
            params_clean = self._clean_comments_from_params(params_raw)

            # Determine visibility
            visibility = 'internal'  # default
            if 'public' in visibility_block:
                visibility = 'public'
            elif 'external' in visibility_block:
                visibility = 'external'
            elif 'private' in visibility_block:
                visibility = 'private'

            # Check if function is virtual or override
            is_virtual = 'virtual' in visibility_block
            is_override = 'override' in visibility_block

            # Extract full function body
            start_pos = match.start()
            # Position of opening brace (after visibility block)
            body_start = params_end + 1 + len(brace_match.group(1))  # Position of {

            # Find which contract this function belongs to
            contract_name = self._find_contract_for_position(start_pos)

            # Find matching closing brace
            open_braces = 0
            i = body_start
            while i < len(self.source_code):
                if self.source_code[i] == '{':
                    open_braces += 1
                elif self.source_code[i] == '}':
                    open_braces -= 1
                    if open_braces == 0:
                        body_end = i + 1
                        break
                i += 1
            else:
                body_end = len(self.source_code)

            function_body = self.source_code[match.start():body_end]

            # Calculate line numbers
            start_line = self.source_code[:start_pos].count('\n') + 1
            end_line = self.source_code[:body_end].count('\n') + 1

            # Extract docstring (NatSpec comment before function)
            docstring = self._extract_docstring_before_position(start_pos)

            # Extract modifiers used by this function
            modifiers_used = self.find_modifiers_used(visibility_block)

            # Create unique key
            key = f"{function_name}_{visibility}_{start_line}"

            functions[key] = {
                'name': function_name,
                'visibility': visibility,
                'signature': f"{function_name}({params_clean})",
                'body': function_body,
                'docstring': docstring,
                'modifiers': modifiers_used,  # NEW: List of modifier names
                'is_virtual': is_virtual,
                'is_override': is_override,
                'contract_name': contract_name,
                'start_line': start_line,
                'end_line': end_line,
                'line_count': end_line - start_line + 1
            }

            if modifiers_used:
                logger.debug(f"Found function: {function_name} ({visibility}) with modifiers {modifiers_used} at lines {start_line}-{end_line}")
            else:
                logger.debug(f"Found function: {function_name} ({visibility}) at lines {start_line}-{end_line}")

        return functions

    def _find_contract_for_position(self, position: int) -> Optional[str]:
        """
        Find which contract a given position in source code belongs to.

        Args:
            position: Character position in source code

        Returns:
            Contract name or None if not found
        """
        code_before = self.source_code[:position]

        # Find all contract declarations before this position
        # Pattern matches: contract Name, contract Name is Parent1, Parent2
        contract_pattern = r'(?:abstract\s+)?contract\s+(\w+)(?:\s+is\s+[^{]+)?\s*\{'

        last_contract = None
        last_contract_pos = -1

        for match in re.finditer(contract_pattern, code_before):
            contract_start = match.start()
            # Find the closing brace for this contract
            open_braces = 0
            i = match.end() - 1  # Start at the opening brace
            while i < len(self.source_code):
                if self.source_code[i] == '{':
                    open_braces += 1
                elif self.source_code[i] == '}':
                    open_braces -= 1
                    if open_braces == 0:
                        contract_end = i
                        # Check if our position is within this contract
                        if contract_start < position <= contract_end:
                            # This is the innermost contract containing our position
                            if contract_start > last_contract_pos:
                                last_contract = match.group(1)
                                last_contract_pos = contract_start
                        break
                i += 1

        return last_contract

    def _extract_docstring_before_position(self, position: int) -> Optional[str]:
        """Extract NatSpec comment immediately before a given position."""
        code_before = self.source_code[:position]
        lines = code_before.split('\n')

        docstring_lines = []
        inside_doc = False

        for line in reversed(lines):
            stripped = line.strip()
            if stripped.endswith('*/'):
                inside_doc = True
                docstring_lines.insert(0, line)
            elif inside_doc:
                docstring_lines.insert(0, line)
                if stripped.startswith('/**') or stripped.startswith('///'):
                    break
            elif stripped != '':
                # Non-comment code before function
                break

        return '\n'.join(docstring_lines).strip() if docstring_lines else None

    def _clean_comments_from_params(self, params: str) -> str:
        """
        Remove inline comments from function parameters.

        Example:
            Input:  "uint256 amount, // comment\n        address receiver"
            Output: "uint256 amount, address receiver"
        """
        # Remove single-line comments (//...)
        cleaned = re.sub(r'//[^\n]*', '', params)

        # Remove multi-line comments (/* ... */)
        cleaned = re.sub(r'/\*.*?\*/', '', cleaned, flags=re.DOTALL)

        # Remove excessive whitespace and newlines
        cleaned = ' '.join(cleaned.split())

        return cleaned

    def find_internal_functions_used(self, function_body: str) -> List[str]:
        """
        Find internal function calls within a function body.

        Args:
            function_body: The function body code

        Returns:
            List of internal function names called
        """
        internal_calls = []

        # Pattern to match function calls: functionName(
        call_pattern = r'\b([a-zA-Z_]\w*)\s*\('

        for match in re.finditer(call_pattern, function_body):
            func_name = match.group(1)
            # Filter out common keywords and built-in functions
            if func_name not in ['if', 'for', 'while', 'require', 'assert', 'revert', 'return',
                                  'keccak256', 'abi', 'address', 'uint', 'bytes', 'string']:
                internal_calls.append(func_name)

        return list(set(internal_calls))  # Remove duplicates

    def find_library_calls(self, function_body: str) -> List[str]:
        """
        Find library function calls within a function body (e.g., LibAsset.isNativeAsset).

        Args:
            function_body: The function body code

        Returns:
            List of library function calls in format "LibraryName.functionName"
        """
        library_calls = []

        # Pattern to match library calls: LibraryName.functionName(
        library_call_pattern = r'\b([A-Z][a-zA-Z0-9_]*)\.([\w]+)\s*\('

        for match in re.finditer(library_call_pattern, function_body):
            lib_name = match.group(1)
            func_name = match.group(2)
            library_calls.append(f"{lib_name}.{func_name}")

        return list(set(library_calls))  # Remove duplicates

    def find_modifiers_used(self, visibility_block: str) -> List[str]:
        """
        Find modifiers used in a function's visibility block.

        Args:
            visibility_block: The text between function parameters and opening brace
                             (e.g., "external virtual override ensure(deadline) returns (uint[])")

        Returns:
            List of modifier names used (e.g., ["ensure"])
        """
        modifiers = []

        # Pattern to match modifier calls: modifierName(args) or just modifierName
        # This should appear after visibility and before returns/{
        # Common patterns: ensure(deadline), onlyOwner, nonReentrant
        modifier_pattern = r'\b([a-z_][a-zA-Z0-9_]*)\s*(?:\([^)]*\))?'

        # Keywords to exclude (not modifiers)
        keywords = {'public', 'private', 'internal', 'external', 'pure', 'view',
                   'payable', 'virtual', 'override', 'returns', 'return'}

        for match in re.finditer(modifier_pattern, visibility_block):
            modifier_name = match.group(1)
            # Exclude keywords
            if modifier_name not in keywords:
                modifiers.append(modifier_name)

        return list(set(modifiers))  # Remove duplicates

    def find_super_calls(self, function_body: str) -> List[str]:
        """
        Find super.functionName() calls within a function body.

        Args:
            function_body: The function body code

        Returns:
            List of function names called via super (e.g., ["deposit", "withdraw"])
        """
        super_calls = []

        # Pattern to match super.functionName(
        super_pattern = r'super\.(\w+)\s*\('

        for match in re.finditer(super_pattern, function_body):
            func_name = match.group(1)
            super_calls.append(func_name)
            logger.debug(f"Found super call: super.{func_name}()")

        return list(set(super_calls))

    def extract_inheritance_chain(self) -> Dict[str, List[str]]:
        """
        Extract inheritance relationships from all contracts in the source code.

        Returns:
            Dictionary mapping contract name to list of parent contracts
            e.g., {"MyVault": ["ERC4626", "Ownable"], "ERC4626": ["ERC20"]}
        """
        inheritance = {}

        # Pattern to match contract inheritance: contract Name is Parent1, Parent2
        # Also handles abstract contract
        contract_pattern = r'(?:abstract\s+)?contract\s+(\w+)\s+is\s+([^{]+)\s*\{'

        for match in re.finditer(contract_pattern, self.cleaned_code):
            contract_name = match.group(1)
            parents_str = match.group(2)

            # Parse parent contracts (may include constructor calls)
            # e.g., "ERC4626(asset_), Ownable(owner)" -> ["ERC4626", "Ownable"]
            parents = []
            for parent in parents_str.split(','):
                parent = parent.strip()
                # Extract just the contract name (before any parentheses)
                parent_name = re.match(r'(\w+)', parent)
                if parent_name:
                    parents.append(parent_name.group(1))

            inheritance[contract_name] = parents
            logger.debug(f"Found inheritance: {contract_name} is {parents}")

        return inheritance

    def find_function_in_parent(self, function_name: str, parent_name: str) -> Optional[Dict[str, Any]]:
        """
        Find a function definition in a specific parent contract.

        Args:
            function_name: Name of the function to find
            parent_name: Name of the parent contract to search in

        Returns:
            Function data dict or None if not found
        """
        # Find the parent contract definition
        # Pattern: contract ParentName ... { ... }
        parent_pattern = rf'(?:abstract\s+)?contract\s+{re.escape(parent_name)}\s+(?:is\s+[^{{]+)?\s*\{{'

        match = re.search(parent_pattern, self.source_code)
        if not match:
            logger.debug(f"Parent contract {parent_name} not found in source")
            return None

        # Find the contract body (everything between { and matching })
        start_pos = match.end() - 1  # Position of opening brace
        open_braces = 0
        contract_body_start = start_pos
        contract_body_end = len(self.source_code)

        i = start_pos
        while i < len(self.source_code):
            if self.source_code[i] == '{':
                open_braces += 1
            elif self.source_code[i] == '}':
                open_braces -= 1
                if open_braces == 0:
                    contract_body_end = i
                    break
            i += 1

        contract_body = self.source_code[contract_body_start:contract_body_end + 1]

        # Search for the function in this contract's body
        # Pattern: function functionName(
        func_pattern = rf'function\s+{re.escape(function_name)}\s*\(([^)]*)\)\s+([^{{]+)\{{'

        func_match = re.search(func_pattern, contract_body)
        if not func_match:
            logger.debug(f"Function {function_name} not found in {parent_name}")
            return None

        # Extract the full function body
        func_start = contract_body_start + func_match.start()
        body_start = contract_body_start + func_match.end() - 1

        # Find matching closing brace
        open_braces = 0
        i = body_start
        while i < len(self.source_code):
            if self.source_code[i] == '{':
                open_braces += 1
            elif self.source_code[i] == '}':
                open_braces -= 1
                if open_braces == 0:
                    body_end = i + 1
                    break
            i += 1
        else:
            body_end = len(self.source_code)

        function_body = self.source_code[func_start:body_end]

        # Determine visibility
        visibility_block = func_match.group(2).strip()
        visibility = 'internal'
        if 'public' in visibility_block:
            visibility = 'public'
        elif 'external' in visibility_block:
            visibility = 'external'
        elif 'private' in visibility_block:
            visibility = 'private'

        params_clean = self._clean_comments_from_params(func_match.group(1).strip())
        start_line = self.source_code[:func_start].count('\n') + 1
        end_line = self.source_code[:body_end].count('\n') + 1

        logger.info(f"  ✓ Found {function_name} in parent {parent_name}")

        return {
            'name': function_name,
            'visibility': visibility,
            'signature': f"{function_name}({params_clean})",
            'body': function_body,
            'parent_contract': parent_name,
            'start_line': start_line,
            'end_line': end_line,
            'line_count': end_line - start_line + 1
        }
