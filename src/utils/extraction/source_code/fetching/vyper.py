"""Vyper extraction helpers for function discovery."""

import re
from typing import Dict

from ..shared import logger


class SourceCodeFetchingVyperMixin:
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

            # Extract parameters to build signature
            # Find closing parenthesis for parameters (handle multi-line and nested parens)
            paren_start = match.end() - 1  # Position of opening (
            paren_count = 1
            paren_end = paren_start + 1
            while paren_end < len(source_code) and paren_count > 0:
                if source_code[paren_end] == '(':
                    paren_count += 1
                elif source_code[paren_end] == ')':
                    paren_count -= 1
                paren_end += 1

            # Extract parameter text
            params_text = source_code[paren_start + 1:paren_end - 1].strip()

            # Parse Vyper parameters: "param_name: param_type, ..."
            # Extract just the types for signature
            param_types = []
            if params_text:
                # Split by comma (handle nested types)
                params = []
                current_param = []
                bracket_depth = 0
                for char in params_text:
                    if char == ',' and bracket_depth == 0:
                        params.append(''.join(current_param).strip())
                        current_param = []
                    else:
                        if char in '([{':
                            bracket_depth += 1
                        elif char in ')]}':
                            bracket_depth -= 1
                        current_param.append(char)
                if current_param:
                    params.append(''.join(current_param).strip())

                # Extract type from each parameter (format: name: type)
                for param in params:
                    if ':' in param:
                        param_type = param.split(':', 1)[1].strip()
                        param_types.append(param_type)

            # Build signature
            signature = f"{func_name}({','.join(param_types)})"

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
                'signature': signature,
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

            # Extract parameters to build signature
            # Find closing parenthesis for parameters (handle multi-line and nested parens)
            paren_start = match.end() - 1  # Position of opening (
            paren_count = 1
            paren_end = paren_start + 1
            while paren_end < len(source_code) and paren_count > 0:
                if source_code[paren_end] == '(':
                    paren_count += 1
                elif source_code[paren_end] == ')':
                    paren_count -= 1
                paren_end += 1

            # Extract parameter text
            params_text = source_code[paren_start + 1:paren_end - 1].strip()

            # Parse Vyper parameters: "param_name: param_type, ..."
            # Extract just the types for signature
            param_types = []
            if params_text:
                # Split by comma (handle nested types)
                params = []
                current_param = []
                bracket_depth = 0
                for char in params_text:
                    if char == ',' and bracket_depth == 0:
                        params.append(''.join(current_param).strip())
                        current_param = []
                    else:
                        if char in '([{':
                            bracket_depth += 1
                        elif char in ')]}':
                            bracket_depth -= 1
                        current_param.append(char)
                if current_param:
                    params.append(''.join(current_param).strip())

                # Extract type from each parameter (format: name: type)
                for param in params:
                    if ':' in param:
                        param_type = param.split(':', 1)[1].strip()
                        param_types.append(param_type)

            # Build signature
            signature = f"{func_name}({','.join(param_types)})"

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
                    'signature': signature,
                    'body': body,
                    'line_count': line_count,
                    'start_line': start_line
                }

        logger.info(f"Extracted {len(functions)} functions from Vyper code")
        if functions:
            function_names = [f['name'] for f in functions.values()]
            logger.info(f"Vyper functions found: {', '.join(function_names[:20])}")

        return functions

