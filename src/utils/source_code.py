"""
Source code extraction and management for ERC-7730 analyzer.

This module handles:
- Fetching contract source code from Sourcify/Etherscan
- Parsing Solidity and Vyper code to extract functions, structs, and internal functions
- Proxy detection and implementation fetching
- Diamond proxy facet resolution
- Caching extracted code for efficient lookups
"""

import json
import logging
import re
from typing import Dict, List, Any, Optional
import requests

logger = logging.getLogger(__name__)


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
        # Matches: function name(params) [everything until opening brace]
        # Uses simple non-backtracking pattern to avoid catastrophic backtracking on complex modifiers
        # Matches everything between ) and { as visibility_block, then parse it separately
        function_pattern = r'function\s+(\w+)\s*\(([^)]*)\)\s+([^{]+)\{'

        for match in re.finditer(function_pattern, self.source_code):
            function_name = match.group(1)
            params = match.group(2).strip()
            visibility_block = match.group(3).strip()

            # Determine visibility
            visibility = 'internal'  # default
            if 'public' in visibility_block:
                visibility = 'public'
            elif 'external' in visibility_block:
                visibility = 'external'
            elif 'private' in visibility_block:
                visibility = 'private'

            # Extract full function body
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

            function_body = self.source_code[match.start():body_end]

            # Calculate line numbers
            start_line = self.source_code[:start_pos].count('\n') + 1
            end_line = self.source_code[:body_end].count('\n') + 1

            # Extract docstring (NatSpec comment before function)
            docstring = self._extract_docstring_before_position(start_pos)

            # Create unique key
            key = f"{function_name}_{visibility}_{start_line}"

            functions[key] = {
                'name': function_name,
                'visibility': visibility,
                'signature': f"{function_name}({params})",
                'body': function_body,
                'docstring': docstring,
                'start_line': start_line,
                'end_line': end_line,
                'line_count': end_line - start_line + 1
            }

            logger.debug(f"Found function: {function_name} ({visibility}) at lines {start_line}-{end_line}")

        return functions

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


class SourceCodeExtractor:
    """
    Main class for extracting and managing contract source code.
    Handles proxies, diamond proxies, and code caching.
    """

    def __init__(self, etherscan_api_key: str):
        """
        Initialize the extractor.

        Args:
            etherscan_api_key: Etherscan API key
        """
        self.etherscan_api_key = etherscan_api_key
        self.code_cache = {}  # Cache: contract_address -> extracted code dict

    def is_vyper_code(self, source_code: str) -> bool:
        """
        Detect if source code is Vyper.

        Args:
            source_code: The source code to check

        Returns:
            True if Vyper, False if Solidity
        """
        # Vyper-specific patterns
        vyper_patterns = [
            r'@external',
            r'@internal',
            r'@view',
            r'@pure',
            r'@payable',
            r'def\s+__init__\(',  # Vyper constructor
            r':\s*constant\(',     # Vyper constant
        ]

        for pattern in vyper_patterns:
            if re.search(pattern, source_code):
                return True

        return False

    def extract_vyper_functions(self, source_code: str) -> Dict[str, Dict]:
        """
        Extract functions from Vyper source code.

        Vyper functions have decorators (@external, @internal, etc.) at column 0,
        followed by the function definition. Interface declarations are indented
        and don't have these decorators, so we can distinguish them.

        Args:
            source_code: Vyper source code

        Returns:
            Dict mapping function keys to function data
        """
        functions = {}

        # Strategy: Look for any decorator block at column 0 followed by function definitions
        # Then check if @external or @internal is present in the decorators
        # Pattern explanation:
        # - ((?:^@[^\n]*\n)+) - One or more decorator lines at start of line (captured)
        # - ^def\s+(\w+)\s*\( - def keyword, function name, and opening paren at start of line
        # We'll find the closing paren separately since parameters can be multi-line and contain nested parens

        decorator_pattern = r'((?:^@[^\n]*\n)+)^def\s+(\w+)\s*\('

        matches = list(re.finditer(decorator_pattern, source_code, re.MULTILINE))
        logger.info(f"Found {len(matches)} functions with decorators")

        for match in matches:
            decorators_text = match.group(1)  # All decorator lines
            func_name = match.group(2)  # Function name

            # Check if @external or @internal is in the decorators
            visibility = None
            if '@external' in decorators_text:
                visibility = 'external'
            elif '@internal' in decorators_text:
                visibility = 'internal'

            if not visibility:
                logger.info(f"  Skipping '{func_name}' - no @external or @internal decorator")
                continue

            logger.info(f"  Found {visibility} function: {func_name}")

            # Extract function body from source
            start_pos = match.start()
            end_pos = len(source_code)

            # Find next @external or @internal decorator (indicates next function)
            # or next interface/event/struct definition
            next_func_match = re.search(r'\n(?:@(?:external|internal)|interface\s+\w+:|event\s+\w+:|struct\s+\w+:)', source_code[match.end():])
            if next_func_match:
                end_pos = match.end() + next_func_match.start()

            body = source_code[start_pos:end_pos].strip()
            line_count = body.count('\n') + 1
            start_line = source_code[:start_pos].count('\n') + 1

            func_key = f"{func_name}_{visibility}_{start_line}"
            functions[func_key] = {
                'name': func_name,
                'visibility': visibility,
                'body': body,
                'line_count': line_count,
                'start_line': start_line
            }

        # Also look for special functions without @external/@internal decorators
        # These include __init__, __default__, etc.
        special_pattern = r'^def\s+((?:__\w+__))\s*\('
        special_matches = list(re.finditer(special_pattern, source_code, re.MULTILINE))
        logger.info(f"Found {len(special_matches)} special functions (e.g., __init__, __default__)")

        for match in special_matches:
            func_name = match.group(1)

            # Extract function body
            start_pos = match.start()
            end_pos = len(source_code)

            # Find next function or top-level definition
            next_match = re.search(r'\n(?:@(?:external|internal)|^def\s+\w+|interface\s+\w+:|event\s+\w+:|struct\s+\w+:)', source_code[match.end():], re.MULTILINE)
            if next_match:
                end_pos = match.end() + next_match.start()

            body = source_code[start_pos:end_pos].strip()
            line_count = body.count('\n') + 1
            start_line = source_code[:start_pos].count('\n') + 1

            # Special functions are considered 'external' for visibility purposes
            visibility = 'external'

            func_key = f"{func_name}_{visibility}_{start_line}"
            if func_key not in functions:  # Avoid duplicates
                functions[func_key] = {
                    'name': func_name,
                    'visibility': visibility,
                    'body': body,
                    'line_count': line_count,
                    'start_line': start_line
                }

        logger.info(f"Extracted {len(functions)} functions from Vyper code")
        if functions:
            function_names = [f['name'] for f in functions.values()]
            logger.info(f"Vyper functions found: {', '.join(function_names[:20])}")

        return functions

    def fetch_source_from_sourcify(self, contract_address: str, chain_id: int) -> Optional[str]:
        """
        Fetch source code from Sourcify.

        Args:
            contract_address: Contract address
            chain_id: Chain ID

        Returns:
            Combined source code or None
        """
        try:
            base_url = f"https://sourcify.dev/server/v2/contract/{chain_id}/{contract_address}"
            response = requests.get(base_url, headers={"accept": "application/json"})

            if response.status_code != 200:
                logger.debug(f"Contract not found on Sourcify (chain {chain_id})")
                return None

            data = response.json()

            # Combine all source files
            sources = data.get('sources', {})
            combined_code = []

            for filename, file_data in sources.items():
                content = file_data.get('content', '')
                combined_code.append(f"// File: {filename}\n{content}")

            if combined_code:
                logger.info(f"Fetched {len(sources)} files from Sourcify")
                return '\n\n'.join(combined_code)

            return None

        except Exception as e:
            logger.debug(f"Failed to fetch from Sourcify: {e}")
            return None

    def fetch_source_from_etherscan(self, contract_address: str, chain_id: int) -> Optional[str]:
        """
        Fetch source code from Etherscan.

        Args:
            contract_address: Contract address
            chain_id: Chain ID

        Returns:
            Combined source code or None
        """
        try:
            base_url = f"https://api.etherscan.io/v2/api?chainid={chain_id}"
            params = {
                'module': 'contract',
                'action': 'getsourcecode',
                'address': contract_address,
                'apikey': self.etherscan_api_key
            }

            response = requests.get(base_url, params=params)
            response.raise_for_status()
            data = response.json()

            if data['status'] != '1' or not data.get('result'):
                logger.debug(f"No source code found on Etherscan")
                return None

            result = data['result'][0]
            source_code = result.get('SourceCode', '')

            if not source_code:
                return None

            # Handle multi-file format (starts with {{)
            if source_code.startswith('{{'):
                try:
                    json_str = source_code[1:-1]  # Remove outer braces
                    sources_dict = json.loads(json_str)

                    combined_code = []
                    if 'sources' in sources_dict:
                        for filename, filedata in sources_dict['sources'].items():
                            content = filedata.get('content', '')
                            combined_code.append(f"// File: {filename}\n{content}")
                    else:
                        for filename, filedata in sources_dict.items():
                            if isinstance(filedata, dict) and 'content' in filedata:
                                content = filedata.get('content', '')
                                combined_code.append(f"// File: {filename}\n{content}")

                    if combined_code:
                        logger.info(f"Fetched {len(combined_code)} files from Etherscan")
                        return '\n\n'.join(combined_code)

                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse multi-file JSON: {e}")
                    return source_code

            # Single file
            logger.info(f"Fetched source code from Etherscan ({len(source_code)} chars)")
            return source_code

        except Exception as e:
            logger.error(f"Failed to fetch from Etherscan: {e}")
            return None

    def detect_proxy_implementation(self, contract_address: str, chain_id: int) -> Optional[str]:
        """
        Detect if contract is a proxy and return implementation address.

        Checks common proxy patterns:
        - EIP-1967 implementation slot
        - EIP-1822 (UUPS) proxies
        - OpenZeppelin proxy patterns

        Args:
            contract_address: Contract address
            chain_id: Chain ID

        Returns:
            Implementation address or None
        """
        try:
            # EIP-1967 implementation slot
            # keccak256("eip1967.proxy.implementation") - 1
            impl_slot = '0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc'

            params = {
                'module': 'proxy',
                'action': 'eth_getStorageAt',
                'address': contract_address,
                'position': impl_slot,
                'tag': 'latest',
                'apikey': self.etherscan_api_key
            }

            base_url = f"https://api.etherscan.io/v2/api?chainid={chain_id}"
            response = requests.get(base_url, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get('result') and data['result'] != '0x' + '0' * 64:
                # Extract address from storage slot (last 20 bytes)
                impl_address = '0x' + data['result'][-40:]
                if impl_address != '0x' + '0' * 40:
                    logger.info(f"Detected EIP-1967 proxy, implementation: {impl_address}")
                    return impl_address

            # Try Etherscan's built-in proxy detection
            params = {
                'module': 'contract',
                'action': 'getsourcecode',
                'address': contract_address,
                'apikey': self.etherscan_api_key
            }

            response = requests.get(base_url, params=params)
            data = response.json()

            if data.get('result') and len(data['result']) > 0:
                result = data['result'][0]
                impl = result.get('Implementation')
                if impl:
                    logger.info(f"Detected proxy via Etherscan, implementation: {impl}")
                    return impl

            return None

        except Exception as e:
            logger.debug(f"Proxy detection failed: {e}")
            return None

    def _detect_diamond_via_sourcecode(self, contract_address: str, chain_id: int) -> Dict[str, str]:
        """
        Fallback method: Detect Diamond proxy by checking if contract name contains 'Diamond'.

        This is a heuristic approach when eth_call to facetAddress fails.
        """
        try:
            params = {
                'module': 'contract',
                'action': 'getsourcecode',
                'address': contract_address,
                'apikey': self.etherscan_api_key
            }

            base_url = f"https://api.etherscan.io/v2/api?chainid={chain_id}"
            response = requests.get(base_url, params=params)
            data = response.json()

            if data.get('result') and len(data['result']) > 0:
                result = data['result'][0]
                contract_name = result.get('ContractName', '')

                logger.info(f"Contract name from Etherscan: {contract_name}")

                # Check if this looks like a Diamond proxy based on name
                if 'diamond' in contract_name.lower():
                    logger.info(f"Contract name suggests Diamond proxy pattern")
                    # For Diamond proxies, we can't easily get facet mappings without eth_call
                    # Return empty dict to signal "is Diamond but can't map facets"
                    # The caller should handle this by not treating it as a simple proxy
                    return {'_is_diamond_but_unmapped': True}

            return {}

        except Exception as e:
            logger.debug(f"Diamond detection via source code failed: {e}")
            return {}

    def detect_diamond_proxy(self, contract_address: str, chain_id: int, selectors: List[str]) -> Dict[str, str]:
        """
        Detect diamond proxy and map selectors to facet addresses using the facets() function.

        Args:
            contract_address: Diamond proxy address
            chain_id: Chain ID
            selectors: List of selectors from ERC-7730 file to map

        Returns:
            Dictionary mapping selector -> facet address (empty if not a Diamond)
        """
        selector_to_facet = {}

        try:
            if not selectors:
                return {}

            # Use the facets() function from Diamond Loupe
            # facets() returns Facet[] where Facet = {address facetAddress, bytes4[] functionSelectors}
            # Selector for facets(): 0x7a0ed627
            facets_selector = '0x7a0ed627'

            params = {
                'module': 'proxy',
                'action': 'eth_call',
                'to': contract_address,
                'data': facets_selector,
                'tag': 'latest',
                'apikey': self.etherscan_api_key
            }

            base_url = f"https://api.etherscan.io/v2/api?chainid={chain_id}"
            logger.info(f"Testing Diamond proxy using facets() function")
            logger.info(f"Call data: {facets_selector}")

            response = requests.get(base_url, params=params)
            data = response.json()

            logger.info(f"facets() API response: {data}")

            # Check if the call succeeded
            if 'error' in data:
                error_msg = data.get('error', {}).get('message', 'unknown error')
                logger.info(f"facets() call failed: {error_msg}")
                logger.info(f"Trying fallback detection method...")
                return self._detect_diamond_via_sourcecode(contract_address, chain_id)

            if not data.get('result') or data['result'] == '0x':
                logger.info(f"facets() returned empty result - not a Diamond proxy")
                return {}

            result = data['result']
            logger.info(f"✓ facets() succeeded! Response length: {len(result)} chars")

            # Parse the ABI-encoded Facet[] array to get the number of facets
            try:
                # Skip the first 0x and parse as hex
                hex_data = result[2:] if result.startswith('0x') else result

                # The structure is:
                # - offset to array (32 bytes)
                # - array length (32 bytes)
                # - then each Facet struct

                if len(hex_data) < 64:
                    logger.warning(f"facets() response too short to parse")
                    return self._detect_diamond_via_sourcecode(contract_address, chain_id)

                # Parse array offset and length
                array_offset = int(hex_data[0:64], 16)
                logger.info(f"Array offset: {array_offset}")

                # The actual array data starts at array_offset * 2 (hex chars)
                array_start = array_offset * 2
                if len(hex_data) < array_start + 64:
                    logger.warning(f"facets() response too short after offset")
                    return self._detect_diamond_via_sourcecode(contract_address, chain_id)

                array_length = int(hex_data[array_start:array_start + 64], 16)
                logger.info(f"Number of facets: {array_length}")

                if array_length == 0:
                    logger.info(f"No facets found in response")
                    return {}

                # Now that we confirmed it's a Diamond, map each selector to its facet
                logger.info(f"✓ Confirmed Diamond proxy with {array_length} facets")
                logger.info(f"Now mapping {len(selectors)} selectors to their facets...")

                # Use facetAddress(bytes4) for each selector to get its facet
                facet_address_selector = '0xcdffacc6'

                for selector in selectors:
                    # Call facetAddress(selector)
                    call_data = facet_address_selector + selector[2:10].ljust(64, "0")

                    facet_params = {
                        'module': 'proxy',
                        'action': 'eth_call',
                        'to': contract_address,
                        'data': call_data,
                        'tag': 'latest',
                        'apikey': self.etherscan_api_key
                    }

                    facet_response = requests.get(base_url, params=facet_params)
                    facet_data = facet_response.json()

                    logger.info(f"  facetAddress({selector}) response: {facet_data}")

                    if facet_data.get('result') and 'error' not in facet_data and facet_data['result'] != '0x':
                        # Extract facet address from result (last 20 bytes / 40 hex chars)
                        facet_address = '0x' + facet_data['result'][-40:].lower()
                        # Check it's not zero address
                        if facet_address != '0x' + '0' * 40:
                            selector_to_facet[selector] = facet_address
                            logger.info(f"  Selector {selector} -> Facet {facet_address}")
                    else:
                        error_msg = facet_data.get('error', {}).get('message', 'no result') if 'error' in facet_data else 'no result'
                        logger.warning(f"  Failed to get facet for selector {selector}: {error_msg}")

                if selector_to_facet:
                    unique_facets = len(set(selector_to_facet.values()))
                    logger.info(f"✓ Successfully mapped {len(selector_to_facet)} selectors to {unique_facets} unique facet(s)")
                    return selector_to_facet
                else:
                    logger.warning(f"Could not map any selectors to facets")
                    return {'_is_diamond_but_unmapped': True}

            except Exception as parse_error:
                logger.warning(f"Error parsing facets() response: {parse_error}")
                logger.info(f"But facets() call succeeded, so this IS a Diamond proxy")
                return {'_is_diamond_but_unmapped': True}

        except Exception as e:
            logger.debug(f"Diamond proxy detection failed: {e}")
            return {}

    def extract_contract_code(
        self,
        contract_address: str,
        chain_id: int,
        selectors: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Extract and parse contract source code.

        Args:
            contract_address: Contract address
            chain_id: Chain ID
            selectors: Optional list of selectors to filter diamond facets

        Returns:
            Dictionary with extracted code:
            {
                'address': str,
                'is_proxy': bool,
                'implementation': Optional[str],
                'is_diamond': bool,
                'facets': Dict[str, str],  # selector -> facet_address
                'source_code': str,
                'functions': Dict,
                'structs': Dict,
                'enums': Dict,
                'internal_functions': Dict
            }
        """
        # Check cache
        cache_key = f"{chain_id}:{contract_address.lower()}"
        if cache_key in self.code_cache:
            logger.debug(f"Using cached code for {contract_address}")
            return self.code_cache[cache_key]

        logger.info(f"Extracting source code for {contract_address} on chain {chain_id}")

        result = {
            'address': contract_address,
            'is_proxy': False,
            'implementation': None,
            'is_diamond': False,
            'facets': {},
            'source_code': None,
            'functions': {},
            'structs': {},
            'enums': {},
            'constants': {},
            'internal_functions': {}
        }

        # Save original address for Diamond proxy detection
        original_address = contract_address

        # Check for diamond proxy FIRST (before checking EIP-1967 proxy)
        # Diamond proxies should be detected using the original proxy address
        if selectors:
            logger.info(f"Checking for Diamond proxy with {len(selectors)} selectors: {selectors[:3]}...")
            facets = self.detect_diamond_proxy(original_address, chain_id, selectors)
            if facets and '_is_diamond_but_unmapped' in facets:
                # Detected as Diamond but couldn't map facets
                result['is_diamond'] = True
                result['facets'] = {}
                logger.info(f"✓ Detected Diamond proxy (but cannot map selectors to facets)")
                # For Diamond proxies, DON'T extract source code from any single implementation
                # The source code is distributed across multiple facets
                logger.warning(f"Skipping source code extraction for Diamond proxy - source is distributed across facets")
                self.code_cache[cache_key] = result
                return result
            elif facets:
                # Successfully mapped selectors to facets
                result['is_diamond'] = True
                result['facets'] = facets
                unique_facet_addresses = set(facets.values())
                logger.info(f"✓ Detected Diamond proxy with {len(unique_facet_addresses)} unique facets")

                # Extract source code from each unique facet
                logger.info(f"Extracting source code from {len(unique_facet_addresses)} unique facets...")
                all_functions = {}
                all_custom_types = {}
                all_using_statements = []
                all_libraries = {}
                all_structs = {}
                all_enums = {}
                all_constants = {}
                all_internal_functions = {}

                for facet_addr in unique_facet_addresses:
                    logger.info(f"  Fetching source code for facet {facet_addr}...")

                    # Fetch source code (try Sourcify first, then Etherscan)
                    source_code = self.fetch_source_from_sourcify(facet_addr, chain_id)
                    if not source_code:
                        source_code = self.fetch_source_from_etherscan(facet_addr, chain_id)

                    if source_code:
                        # Detect if facet code is Vyper or Solidity
                        is_vyper = self.is_vyper_code(source_code)

                        if is_vyper:
                            logger.info(f"    Detected Vyper code in facet - using Vyper parser")
                            facet_functions = self.extract_vyper_functions(source_code)
                            facet_structs = {}
                            facet_enums = {}
                            facet_constants = {}
                            facet_internal = {
                                k: v for k, v in facet_functions.items()
                                if v['visibility'] == 'internal'
                            }
                        else:
                            logger.info(f"    Detected Solidity code in facet - using Solidity parser")
                            # Parse the source code
                            parser = SolidityCodeParser(source_code)

                            facet_custom_types = parser.extract_custom_types()
                            facet_using_statements = parser.extract_using_statements()
                            facet_libraries = parser.extract_libraries()
                            facet_structs = parser.extract_structs()
                            facet_enums = parser.extract_enums()
                            facet_constants = parser.extract_constants()
                            facet_functions = parser.extract_functions()

                            # Separate internal functions
                            facet_internal = {
                                k: v for k, v in facet_functions.items()
                                if v['visibility'] in ['internal', 'private']
                            }

                        # Merge into combined results
                        all_functions.update(facet_functions)
                        all_custom_types.update(facet_custom_types)
                        all_using_statements.extend(facet_using_statements)
                        all_libraries.update(facet_libraries)
                        all_structs.update(facet_structs)
                        all_enums.update(facet_enums)
                        all_constants.update(facet_constants)
                        all_internal_functions.update(facet_internal)

                        logger.info(f"    Added {len(facet_functions)} functions, {len(facet_custom_types)} custom types, {len(facet_using_statements)} using statements, {len(facet_libraries)} libraries, {len(facet_structs)} structs, {len(facet_enums)} enums, {len(facet_constants)} constants from facet")
                    else:
                        logger.warning(f"    Could not fetch source code for facet {facet_addr}")

                result['functions'] = all_functions
                result['custom_types'] = all_custom_types
                result['using_statements'] = all_using_statements
                result['libraries'] = all_libraries
                result['structs'] = all_structs
                result['enums'] = all_enums
                result['constants'] = all_constants
                result['internal_functions'] = all_internal_functions
                result['source_code'] = f"Diamond proxy with {len(unique_facet_addresses)} facets"

                logger.info(f"✓ Extracted total: {len(all_functions)} functions, {len(all_custom_types)} custom types, {len(all_using_statements)} using statements, {len(all_libraries)} libraries, {len(all_structs)} structs, {len(all_enums)} enums, {len(all_constants)} constants from all facets")

                # Cache and return
                self.code_cache[cache_key] = result
                return result
            else:
                # Not a Diamond proxy, check for standard EIP-1967 proxy
                impl_address = self.detect_proxy_implementation(contract_address, chain_id)
                if impl_address:
                    result['is_proxy'] = True
                    result['implementation'] = impl_address
                    contract_address = impl_address  # Use implementation for source code
                    logger.info(f"Using implementation address: {impl_address}")

        # Fetch source code (try Sourcify first, then Etherscan)
        source_code = self.fetch_source_from_sourcify(contract_address, chain_id)
        if not source_code:
            source_code = self.fetch_source_from_etherscan(contract_address, chain_id)

        if not source_code:
            logger.warning(f"Could not fetch source code for {contract_address}")
            self.code_cache[cache_key] = result
            return result

        result['source_code'] = source_code

        # Detect if code is Vyper or Solidity
        is_vyper = self.is_vyper_code(source_code)

        if is_vyper:
            logger.info("Detected Vyper code - using Vyper parser")
            # Extract functions using Vyper parser
            result['functions'] = self.extract_vyper_functions(source_code)
            # Vyper doesn't have structs/enums in the same way as Solidity
            result['structs'] = {}
            result['enums'] = {}
            result['constants'] = {}
            result['internal_functions'] = {
                k: v for k, v in result['functions'].items()
                if v['visibility'] == 'internal'
            }
        else:
            logger.info("Detected Solidity code - using Solidity parser")
            # Parse using Solidity parser
            parser = SolidityCodeParser(source_code)

            logger.info("  [1/7] Extracting custom types...")
            result['custom_types'] = parser.extract_custom_types()
            logger.info(f"  ✓ Found {len(result['custom_types'])} custom types")

            logger.info("  [2/7] Extracting using statements...")
            result['using_statements'] = parser.extract_using_statements()
            logger.info(f"  ✓ Found {len(result['using_statements'])} using statements")

            logger.info("  [3/8] Extracting libraries...")
            result['libraries'] = parser.extract_libraries()
            logger.info(f"  ✓ Found {len(result['libraries'])} libraries")

            logger.info("  [4/8] Extracting interfaces...")
            result['interfaces'] = parser.extract_interfaces()
            logger.info(f"  ✓ Found {len(result['interfaces'])} interfaces/contracts")

            logger.info("  [5/8] Extracting structs...")
            result['structs'] = parser.extract_structs()
            logger.info(f"  ✓ Found {len(result['structs'])} structs")

            logger.info("  [6/8] Extracting enums...")
            result['enums'] = parser.extract_enums()
            logger.info(f"  ✓ Found {len(result['enums'])} enums")

            logger.info("  [7/8] Extracting constants...")
            result['constants'] = parser.extract_constants()
            logger.info(f"  ✓ Found {len(result['constants'])} constants")

            logger.info("  [8/8] Extracting functions (this may take a while for large contracts)...")
            result['functions'] = parser.extract_functions()
            logger.info(f"  ✓ Found {len(result['functions'])} functions")

            # Separate internal functions
            result['internal_functions'] = {
                k: v for k, v in result['functions'].items()
                if v['visibility'] in ['internal', 'private']
            }

        logger.info(f"Extracted {len(result['functions'])} functions, "
                   f"{len(result.get('custom_types', {}))} custom types, "
                   f"{len(result.get('using_statements', []))} using statements, "
                   f"{len(result.get('libraries', {}))} libraries, "
                   f"{len(result['structs'])} structs, "
                   f"{len(result['enums'])} enums, "
                   f"{len(result['constants'])} constants")

        # Cache the result
        self.code_cache[cache_key] = result

        return result

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

                    # Resolve custom types (including interfaces that were extracted)
                    if field_type in custom_type_mapping:
                        field_type = custom_type_mapping[field_type]
                    # Resolve nested structs recursively
                    elif field_type in all_structs:
                        nested_tuple = self._struct_to_tuple(all_structs[field_type], custom_type_mapping, all_structs)
                        if nested_tuple:
                            field_type = nested_tuple

                    types.append(field_type)

            if not types:
                return None

            return f"({','.join(types)})"
        except Exception as e:
            logger.debug(f"Failed to parse struct: {e}")
            return None

    @staticmethod
    def _normalize_signature_for_matching(
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

                    # Check if this is a custom type (including interfaces) and resolve it
                    if base_type in custom_type_mapping:
                        resolved_type = custom_type_mapping[base_type]
                        param_type = resolved_type + array_suffix
                        logger.debug(f"    Resolved type: {base_type}{array_suffix} -> {param_type}")
                    # Check if this is a struct type and resolve it to tuple
                    elif base_type in struct_type_mapping:
                        resolved_type = struct_type_mapping[base_type]
                        param_type = resolved_type + array_suffix
                        logger.debug(f"    Resolved struct type: {base_type}{array_suffix} -> {param_type}")

                    types.append(param_type)

        return f"{func_name}({','.join(types)})"

    def get_function_with_dependencies(
        self,
        function_name: str,
        extracted_code: Dict[str, Any],
        function_signature: Optional[str] = None,
        max_lines: int = 300
    ) -> Dict[str, Any]:
        """
        Get a function's code along with its dependencies (structs, internal functions, libraries, etc.).

        Args:
            function_name: Name of the function
            extracted_code: Extracted code dictionary from extract_contract_code()
            function_signature: Optional function signature with parameter types (e.g., "approve(uint256,uint256)")
                                to disambiguate overloaded functions. If not provided, matches by name only.
            max_lines: Maximum number of lines to include (truncate if exceeded)

        Returns:
            Dictionary with:
            {
                'function': str,
                'custom_types': List[str],
                'using_statements': List[str],
                'libraries': List[str],
                'structs': List[str],
                'internal_functions': List[str],
                'enums': List[str],
                'total_lines': int,
                'truncated': bool
            }
        """
        # Find the function
        target_function = None

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

        # Add interfaces and contracts (they all map to address in ABI)
        interfaces = extracted_code.get('interfaces', [])
        for interface_name in interfaces:
            custom_type_mapping[interface_name] = 'address'
            logger.debug(f"  Interface/Contract mapping: {interface_name} -> address")

        # Add enums (they all map to uint8 in ABI)
        enums = extracted_code.get('enums', {})
        for enum_name in enums.keys():
            custom_type_mapping[enum_name] = 'uint8'
            logger.debug(f"  Enum mapping: {enum_name} -> uint8")

        # Get struct mapping for resolving struct types to tuples
        structs = extracted_code.get('structs', {})
        struct_type_mapping = {}
        for struct_name, struct_def in structs.items():
            # Extract tuple representation from struct, resolving custom types and nested structs
            tuple_repr = self._struct_to_tuple(struct_def, custom_type_mapping, structs)
            if tuple_repr:
                struct_type_mapping[struct_name] = tuple_repr
                logger.debug(f"  Struct type mapping: {struct_name} -> {tuple_repr}")

        # If signature is provided, normalize it for comparison
        normalized_target_sig = None
        if function_signature:
            normalized_target_sig = self._normalize_signature_for_matching(function_signature, custom_type_mapping, struct_type_mapping)
            logger.info(f"  Looking for function with normalized signature: {normalized_target_sig}")

        # Track all candidates for better error reporting
        candidates = []

        for func_data in extracted_code['functions'].values():
            if func_data['name'] == function_name and func_data['visibility'] in ['public', 'external']:
                # If signature is provided, match by signature; otherwise match by name only
                if normalized_target_sig:
                    # Normalize the extracted signature for comparison
                    # The extracted signature has parameter names, so we need to normalize it
                    extracted_sig = self._normalize_signature_for_matching(func_data['signature'], custom_type_mapping, struct_type_mapping)
                    candidates.append((func_data['signature'], extracted_sig))
                    logger.info(f"    Comparing: {extracted_sig} vs {normalized_target_sig}")
                    if extracted_sig == normalized_target_sig:
                        target_function = func_data
                        logger.info(f"  ✓ Matched function by signature: {func_data['signature']} -> {extracted_sig}")
                        break
                else:
                    # Fallback: match by name only (old behavior)
                    target_function = func_data
                    logger.info(f"  ✓ Matched function by name only: {func_data['signature']}")
                    break

        if not target_function:
            if candidates:
                logger.warning(f"Function {function_name} not found - signature mismatch")
                logger.warning(f"  Target signature: {normalized_target_sig}")
                logger.warning(f"  Found {len(candidates)} candidate(s) with same name but different signatures:")
                for orig_sig, norm_sig in candidates:
                    logger.warning(f"    - {orig_sig} -> {norm_sig}")
            else:
                logger.warning(f"Function {function_name} not found - no matching name or visibility")
            return {
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

        # Parse function to find internal calls and library calls
        parser = SolidityCodeParser(target_function['body'])
        internal_calls = parser.find_internal_functions_used(target_function['body'])
        library_calls = parser.find_library_calls(target_function['body'])

        # Collect dependencies
        result = {
            'function': target_function['body'],
            'function_docstring': target_function.get('docstring'),
            'custom_types': [],
            'using_statements': [],
            'libraries': [],
            'structs': [],
            'internal_functions': [],  # Will store dicts with 'body' and 'docstring'
            'enums': [],
            'constants': [],
            'total_lines': target_function['line_count'],
            'truncated': False
        }

        # Collect all code to scan for constant references
        all_code_to_scan = [target_function['body']]

        # Add referenced structs and enums (simple heuristic: check if name appears in function)
        for struct_name, struct_code in extracted_code['structs'].items():
            if struct_name in target_function['body']:
                result['structs'].append(struct_code)
                result['total_lines'] += struct_code.count('\n') + 1

        for enum_name, enum_code in extracted_code['enums'].items():
            if enum_name in target_function['body']:
                result['enums'].append(enum_code)
                result['total_lines'] += enum_code.count('\n') + 1

        # Add referenced custom types (e.g., type TakerTraits is uint256;)
        # Also track which custom types are used to find their associated libraries
        used_custom_types = set()
        for type_name, type_code in extracted_code.get('custom_types', {}).items():
            # Check if type is referenced in function body or structs
            if type_name in target_function['body'] or any(type_name in s for s in result['structs']):
                result['custom_types'].append(type_code)
                result['total_lines'] += type_code.count('\n') + 1
                used_custom_types.add(type_name)
                logger.info(f"    ✓ Including custom type: {type_name}")

        # Collect library names from library calls for using statement filtering
        referenced_library_names = set()
        for lib_call in library_calls:
            if '.' in lib_call:
                lib_name = lib_call.split('.')[0]
                referenced_library_names.add(lib_name)

        # Also find libraries associated with custom types via "using" statements
        # Pattern: "using LibraryName for CustomType;"
        for using_stmt in extracted_code.get('using_statements', []):
            for type_name in used_custom_types:
                if f"for {type_name}" in using_stmt:
                    # Extract library name from "using LibName for TypeName;"
                    match = re.search(r'using\s+(\w+)\s+for\s+' + type_name, using_stmt)
                    if match:
                        lib_name = match.group(1)
                        referenced_library_names.add(lib_name)
                        logger.info(f"    ✓ Found library {lib_name} for custom type {type_name} via using statement")

        # Add using statements related to types or libraries referenced in the function
        for using_stmt in extracted_code.get('using_statements', []):
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

        # Add internal functions that are called
        # Also scan them for library calls
        for internal_call in internal_calls:
            found = False

            # First check in internal_functions (private/internal visibility)
            for func_data in extracted_code['internal_functions'].values():
                if func_data['name'] == internal_call:
                    result['internal_functions'].append({
                        'body': func_data['body'],
                        'docstring': func_data.get('docstring')
                    })
                    all_code_to_scan.append(func_data['body'])  # Scan internal functions for constants too
                    result['total_lines'] += func_data['line_count']
                    logger.info(f"    ✓ Including internal function: {internal_call}()")

                    # Scan this internal function for library calls too
                    internal_lib_calls = parser.find_library_calls(func_data['body'])
                    library_calls.extend(internal_lib_calls)
                    found = True
                    break

            # If not found in internal functions, check in all functions (public/external)
            # This handles wrapper functions that call other public functions
            if not found:
                for func_data in extracted_code['functions'].values():
                    if func_data['name'] == internal_call and func_data['name'] != function_name:
                        # Avoid infinite recursion by not including the function itself
                        result['internal_functions'].append({
                            'body': func_data['body'],
                            'docstring': func_data.get('docstring')
                        })
                        all_code_to_scan.append(func_data['body'])
                        result['total_lines'] += func_data['line_count']
                        logger.info(f"    ✓ Including called public/external function: {internal_call}()")

                        # Scan this function for library calls too
                        public_lib_calls = parser.find_library_calls(func_data['body'])
                        library_calls.extend(public_lib_calls)
                        break

        # Add library functions that are called (e.g., LibAsset.isNativeAsset)
        # We need to recursively scan for nested library calls
        processed_lib_calls = set()
        lib_calls_to_process = list(set(library_calls))  # Remove duplicates

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
                found = False

                # First try: Search in extracted internal_functions
                for func_data in extracted_code['internal_functions'].values():
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
                if not found and extracted_code.get('source_code'):
                    logger.info(f"    ⚠ {func_name} not in internal_functions, searching full source code...")
                    # Use SolidityCodeParser to extract the function properly
                    source_parser = SolidityCodeParser(extracted_code['source_code'])
                    all_funcs = source_parser.extract_functions()

                    # Look for the function by name
                    for func_sig, func_data in all_funcs.items():
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
            if lib_name in extracted_code.get('libraries', {}):
                library_code = extracted_code['libraries'][lib_name]
                result['libraries'].append(library_code)
                result['total_lines'] += library_code.count('\n') + 1
                logger.info(f"    ✓ Including full library: {lib_name}")

        # Find constants used in the function and its internal calls (including library functions)
        combined_code = '\n'.join(all_code_to_scan)

        # Debug: Show all available constants
        all_constants = list(extracted_code.get('constants', {}).keys())
        if all_constants:
            logger.info(f"  - Available constants in source: {', '.join(all_constants[:10])}{' ...' if len(all_constants) > 10 else ''}")

        constants_found = []
        constants_to_check = []

        # First pass: find constants directly referenced in the code
        for const_name, const_decl in extracted_code.get('constants', {}).items():
            # Check if constant is referenced in the code
            # Match: ConstName or Library.ConstName
            if re.search(r'\b' + re.escape(const_name) + r'\b', combined_code):
                result['constants'].append(const_decl)
                result['total_lines'] += 1  # Constants are usually single line
                constants_found.append(const_name)
                constants_to_check.append(const_decl)  # Check this constant's value for more constant references

        # Second pass: recursively find constants referenced by other constants
        # E.g., if NATIVE_ASSETID = NULL_ADDRESS, we need to extract NULL_ADDRESS too
        processed_constants = set(constants_found)
        while constants_to_check:
            const_decl = constants_to_check.pop(0)
            # Look for other constant references in this constant's declaration
            for const_name, const_decl_check in extracted_code.get('constants', {}).items():
                if const_name not in processed_constants:
                    # Check if this constant is referenced in any already-extracted constant
                    if re.search(r'\b' + re.escape(const_name) + r'\b', const_decl):
                        result['constants'].append(const_decl_check)
                        result['total_lines'] += 1
                        constants_found.append(const_name)
                        constants_to_check.append(const_decl_check)
                        processed_constants.add(const_name)

        if constants_found:
            logger.info(f"  - Constants extracted: {', '.join(constants_found)}")

        # Check if we need to truncate
        if result['total_lines'] > max_lines:
            result['truncated'] = True
            # Prioritize: main function > structs/enums > internal functions
            # Keep main function always, truncate internal functions if needed
            available_lines = max_lines - target_function['line_count']
            available_lines -= sum(s.count('\n') + 1 for s in result['structs'])
            available_lines -= sum(e.count('\n') + 1 for e in result['enums'])

            if available_lines < 0:
                # Even structs/enums are too much, keep only function
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
                result['internal_functions'] = truncated_internals

        return result
