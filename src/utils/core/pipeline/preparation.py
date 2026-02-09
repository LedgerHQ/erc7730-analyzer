"""Pipeline stage: decode samples and prepare audit tasks."""

import logging
import time
from typing import Any, Dict

from ..helpers import truncate_byte_arrays
from ...auditing import prepare_audit_task

logger = logging.getLogger(__name__)


class AnalyzerPipelinePreparationMixin:
    def _prepare_selector_audit_tasks(self, context: Dict[str, Any]) -> None:
        """Prepare decoded tx samples, source snippets, and audit payload tasks."""
        selectors = context['selectors']
        all_selector_txs = context['all_selector_txs']
        deployment_per_selector = context['deployment_per_selector']
        default_deployment = context['default_deployment']
        erc7730_data = context['erc7730_data']
        # ====================================================================
        # PHASE 1: PRE-PROCESSING (Sequential - maintains log coherence)
        # ====================================================================
        # Prepare all data and audit tasks before making any API calls.
        # This keeps the preparation logs in order and allows batch API calls.

        logger.info(f"\n{'='*60}")
        logger.info(f"PHASE 1: Preparing audit tasks for {len(selectors)} selectors...")
        logger.info(f"{'='*60}")

        # Store prepared data for each selector
        prepared_selectors = []  # List of dicts with all pre-processed data

        for selector in selectors:
            logger.info(f"\n{'='*60}")
            logger.info(f"Preparing selector: {selector}")
            logger.info(f"{'='*60}")

            # Get function metadata
            function_data = self.get_function_abi_by_selector(selector)
            if not function_data:
                logger.warning(f"Skipping selector {selector} - no matching ABI entry")
                continue

            function_name = function_data['name']
            logger.info(f"Function name: {function_name}")
            logger.info(f"Function signature: {function_data['signature']}")

            # Get the pre-fetched transactions for this selector
            transactions = all_selector_txs.get(selector.lower(), [])

            # Get the deployment used for this selector (for chain_id and contract_address)
            selector_deployment = deployment_per_selector.get(selector.lower(), default_deployment)

            if not transactions:
                logger.warning(f"No transactions found for selector {selector} - will perform static analysis only")
            else:
                logger.info(f"Found {len(transactions)} transactions for selector {selector} on chain {selector_deployment['chainId']}")

            # Decode each transaction
            decoded_txs = []
            for i, tx in enumerate(transactions, 1):
                logger.info(f"\nTransaction {i}/{len(transactions)}: {tx['hash']}")

                decoded = self.tx_fetcher.decode_transaction_input(
                    tx['input'],
                    function_data,
                    self.abi_helper
                )
                if decoded is not None:
                    # Extract _raw_fallback before truncation (keep it intact for AI)
                    raw_fallback = decoded.pop('_raw_fallback', None)

                    # Truncate large byte arrays to reduce token usage
                    decoded_clean = truncate_byte_arrays(decoded, max_bytes_length=100)

                    # Re-add raw fallback if it existed (untruncated)
                    if raw_fallback:
                        decoded_clean['_raw_fallback'] = raw_fallback

                    tx_data = {
                        'hash': tx['hash'],
                        'block': tx['blockNumber'],
                        'timestamp': tx['timeStamp'],
                        'from': tx['from'],
                        'to': tx.get('to', ''),
                        'value': tx['value'],
                        'decoded_input': decoded_clean
                    }

                    # Fetch transaction receipt and decode logs
                    # Only fetch receipt if we have a valid transaction hash (starts with 0x and is 66 chars)
                    tx_hash = tx.get('hash', '')
                    if tx_hash.startswith('0x') and len(tx_hash) == 66:
                        logger.info(f"Fetching receipt for transaction {tx_hash}")
                        receipt = self.tx_fetcher.fetch_transaction_receipt(
                            tx_hash,
                            selector_deployment['chainId']
                        )
                    else:
                        logger.debug(f"Skipping receipt fetch for transaction {tx_hash} (not a valid TX hash)")
                        receipt = None

                    if receipt and receipt.get('logs'):
                        decoded_logs = []
                        for log in receipt['logs']:
                            decoded_log = self.tx_fetcher.decode_log_event(
                                log,
                                selector_deployment['chainId']
                            )
                            if decoded_log:
                                decoded_logs.append(decoded_log)

                        if decoded_logs:
                            tx_data['receipt_logs'] = decoded_logs
                            logger.info(f"Decoded {len(decoded_logs)} log events:")
                            for log in decoded_logs:
                                if log.get('event') == 'Transfer':
                                    logger.info(f"  Transfer: {log['value_formatted']} from {log['from'][:10]}... to {log['to'][:10]}...")
                                elif log.get('event') == 'Approval':
                                    logger.info(f"  Approval: {log['value_formatted']} from {log['owner'][:10]}... to {log['spender'][:10]}...")
                                else:
                                    logger.info(f"  {log.get('event', 'Unknown')}: {log.get('address', 'unknown')[:10]}...")

                    decoded_txs.append(tx_data)
                    time.sleep(0.2)

                    logger.info(f"Decoded parameters:")
                    for param_name, param_value in decoded_clean.items():
                        logger.info(f"  {param_name}: {param_value}")

            # Generate clear signing audit report
            format_key = self.selector_to_format_key.get(selector, selector)
            erc7730_format = erc7730_data.get('display', {}).get('formats', {}).get(format_key, {})

            # Import the expand function to get full context for AI
            from ...reporting.reporter import expand_erc7730_format_with_refs
            erc7730_format_expanded = expand_erc7730_format_with_refs(
                erc7730_format,
                erc7730_data,
                format_key
            )

            # Extract source code for this specific function (search across all deployments)
            function_source = None
            if self.extracted_codes:
                logger.info(f"Searching for function '{function_name}' ({function_data['signature']}) across {len(self.extracted_codes)} contract(s)...")

                # PHASE 1: Search ALL contracts for EXACT SELECTOR match first
                logger.info(f"  Phase 1: Searching for exact selector match across all {len(self.extracted_codes)} contracts...")
                for deployment_key, extracted_code in self.extracted_codes.items():
                    if not extracted_code['source_code']:
                        continue

                    chain_id = extracted_code['chain_id']
                    address = extracted_code['address']
                    logger.info(f"  Checking {address} on chain {chain_id} (selector only)...")

                    # Log what we know about this selector's mapping
                    if selector in self.selector_sources:
                        sources = self.selector_sources[selector]
                        source_chains = [s.get('chain_id') for s in sources]
                        logger.info(f"    Selector {selector} is mapped to chains: {source_chains}")
                        if chain_id not in source_chains:
                            logger.info(f"    → Skipping chain {chain_id} (selector not on this chain)")
                            continue
                    
                    # Try to find by EXACT SELECTOR only (no name fallback)
                    function_source = self.source_extractor.get_function_with_dependencies(
                        function_name,
                        extracted_code,
                        function_signature=function_data['signature'],
                        max_lines=1000,
                        selector_only=True,  # Only match by exact selector, skip name matching
                        selector=selector  # Pass selector for Diamond proxy facet-specific lookup
                    )

                    if function_source and function_source['function']:
                        logger.info(f"✓ Found EXACT SELECTOR MATCH at {address} on chain {chain_id}!")
                        logger.info(f"✓ Extracted function code ({function_source['total_lines']} lines)")
                        logger.info(f"  - Constants: {len(function_source.get('constants', []))}")
                        logger.info(f"  - Modifiers: {len(function_source.get('modifiers', []))}")
                        logger.info(f"  - Structs: {len(function_source['structs'])}")
                        logger.info(f"  - Enums: {len(function_source['enums'])}")
                        logger.info(f"  - Internal functions: {len(function_source['internal_functions'])}")
                        if function_source.get('parent_functions'):
                            logger.info(f"  - Parent functions (from super.): {len(function_source['parent_functions'])}")
                            for pf in function_source['parent_functions']:
                                logger.info(f"      └─ {pf['parent_contract']}.{pf['function_name']}()")
                        if function_source['truncated']:
                            logger.info(f"  ⚠ Code was truncated to fit within line limit")
                        break  # Stop searching - found exact selector match!

                # PHASE 2: If no exact selector match found, try NAME-based matching in first contract
                if not function_source or not function_source.get('function'):
                    logger.info(f"  Phase 2: No exact selector match found. Trying name-based matching with inheritance in first contract...")
                    
                    # IMPORTANT: Check if this selector is in any facet ABI
                    # If not, the ERC-7730 may refer to an old version that has been upgraded
                    if selector not in self.selector_sources:
                        logger.warning(f"  ⚠️  SELECTOR MISMATCH: {selector} is NOT in any facet ABI!")
                        logger.warning(f"  ⚠️  The ERC-7730 may refer to an OLD function version that has been upgraded.")
                        logger.warning(f"  ⚠️  Name-based matching may find a DIFFERENT version with different parameters!")

                    # Get extracted_code from a chain where the selector IS mapped
                    # This is critical for Diamond proxies - the selector may only exist on certain chains
                    first_extracted_code = None
                    first_deployment_key = None
                    
                    # First, try to find a chain where this selector has a facet mapping
                    if selector in self.selector_sources:
                        mapped_chains = [s.get('chain_id') for s in self.selector_sources[selector]]
                        for deployment_key, extracted_code in self.extracted_codes.items():
                            if extracted_code['source_code'] and extracted_code.get('chain_id') in mapped_chains:
                                first_extracted_code = extracted_code
                                first_deployment_key = deployment_key
                                logger.info(f"  Using extracted_code from chain {extracted_code.get('chain_id')} where selector is mapped")
                                break
                    
                    # Fallback: use any contract with source code
                    if not first_extracted_code:
                        for deployment_key, extracted_code in self.extracted_codes.items():
                            if extracted_code['source_code']:
                                first_extracted_code = extracted_code
                                first_deployment_key = deployment_key
                                break

                    if first_extracted_code:
                        chain_id = first_extracted_code['chain_id']
                        address = first_extracted_code['address']
                        logger.info(f"  Checking {address} on chain {chain_id} (with name fallback)...")

                        function_source = self.source_extractor.get_function_with_dependencies(
                            function_name,
                            first_extracted_code,
                            function_signature=function_data['signature'],
                            max_lines=1000,
                            selector_only=False,  # Allow name-based fallback with inheritance
                            selector=selector  # Pass selector for Diamond proxy facet-specific lookup
                        )

                        if function_source and function_source['function']:
                            logger.info(f"✓ Found by name (with inheritance) at {address} on chain {chain_id}")
                            logger.info(f"✓ Extracted function code ({function_source['total_lines']} lines)")
                            logger.info(f"  - Constants: {len(function_source.get('constants', []))}")
                            logger.info(f"  - Modifiers: {len(function_source.get('modifiers', []))}")
                            logger.info(f"  - Structs: {len(function_source['structs'])}")
                            logger.info(f"  - Enums: {len(function_source['enums'])}")
                            logger.info(f"  - Internal functions: {len(function_source['internal_functions'])}")
                            if function_source.get('parent_functions'):
                                logger.info(f"  - Parent functions (from super.): {len(function_source['parent_functions'])}")
                                for pf in function_source['parent_functions']:
                                    logger.info(f"      └─ {pf['parent_contract']}.{pf['function_name']}()")
                            if function_source['truncated']:
                                logger.info(f"  ⚠ Code was truncated to fit within line limit")

                if not function_source or not function_source.get('function'):
                    logger.warning(f"Function '{function_name}' not found in any of the {len(self.extracted_codes)} contract(s)")

            # Display code in debug mode as a single cohesive block
            if function_source and function_source.get('function'):
                if logger.isEnabledFor(logging.INFO):
                    code_block = f"\n{'='*60}\n"
                    code_block += "SOURCE CODE (being sent to AI):\n"
                    code_block += f"{'='*60}\n\n"

                    if function_source.get('function_docstring'):
                        code_block += f"// Docstring:\n{function_source['function_docstring']}\n\n"

                    # 1. Custom types (highest priority)
                    if function_source.get('custom_types'):
                        code_block += "// Custom types:\n"
                        for custom_type in function_source['custom_types']:
                            code_block += f"{custom_type}\n"
                        code_block += "\n"

                    # 2. Using statements
                    if function_source.get('using_statements'):
                        code_block += "// Using statements:\n"
                        for using_stmt in function_source['using_statements']:
                            code_block += f"{using_stmt}\n"
                        code_block += "\n"

                    # 3. Constants
                    if function_source.get('constants'):
                        code_block += "// Constants:\n"
                        for constant in function_source['constants']:
                            code_block += f"{constant}\n"
                        code_block += "\n"

                    # 3.5. Modifiers used by the main function
                    if function_source.get('modifiers'):
                        code_block += "// Modifiers used by main function:\n"
                        for modifier in function_source['modifiers']:
                            code_block += f"{modifier}\n\n"

                    # 4. Structs
                    if function_source['structs']:
                        code_block += "// Structs:\n"
                        for struct in function_source['structs']:
                            code_block += f"{struct}\n"
                        code_block += "\n"

                    # 5. Enums
                    if function_source['enums']:
                        code_block += "// Enums:\n"
                        for enum in function_source['enums']:
                            code_block += f"{enum}\n"
                        code_block += "\n"

                    # 6. Main function
                    code_block += "// Main function:\n"
                    code_block += function_source['function']

                    # 7. Internal functions called
                    if function_source['internal_functions']:
                        code_block += "\n\n// Internal functions called:\n"
                        for internal_func in function_source['internal_functions']:
                            # Format internal function with docstring and body
                            if internal_func.get('docstring'):
                                code_block += f"{internal_func['docstring']}\n"
                            code_block += f"{internal_func['body']}\n\n"

                    # 8. Parent functions (from super. calls)
                    if function_source.get('parent_functions'):
                        code_block += "\n\n// Parent contract implementations (from super. calls):\n"
                        for parent_func in function_source['parent_functions']:
                            parent_name = parent_func.get('parent_contract', 'Unknown')
                            func_name = parent_func.get('function_name', 'unknown')
                            code_block += f"// From {parent_name}.{func_name}():\n"
                            code_block += f"{parent_func['body']}\n\n"

                    # 9. Libraries (lowest priority)
                    if function_source.get('libraries'):
                        code_block += "\n// Libraries:\n"
                        for library in function_source['libraries']:
                            code_block += f"{library}\n\n"

                    code_block += f"\n{'='*60}\n"

                    # Single log call for entire code block
                    logger.info(code_block)

            # Prepare the audit task if we have a format
            audit_task = None
            if erc7730_format:
                has_no_transactions = not decoded_txs
                if has_no_transactions:
                    logger.info(f"Preparing STATIC audit task for {selector} (no transactions)")
                else:
                    logger.info(f"Preparing audit task for {selector}")

                audit_task = prepare_audit_task(
                    selector=selector,
                    decoded_transactions=decoded_txs,
                    erc7730_format=erc7730_format_expanded,
                    function_signature=function_data['signature'],
                    source_code=function_source,
                    use_smart_referencing=self.use_smart_referencing,
                    erc4626_context=self.erc4626_context,
                    erc20_context=self.erc20_context,
                    protocol_name=self.protocol_name
                )

            # Store all prepared data for this selector
            prepared_selectors.append({
                'selector': selector,
                'function_name': function_name,
                'function_data': function_data,
                'selector_deployment': selector_deployment,
                'decoded_txs': decoded_txs,
                'erc7730_format': erc7730_format,
                'function_source': function_source,
                'audit_task': audit_task
            })

        logger.info(f"\n{'='*60}")
        logger.info(f"PHASE 1 COMPLETE: Prepared {len(prepared_selectors)} audit tasks")
        logger.info(f"{'='*60}")
        context['prepared_selectors'] = prepared_selectors
