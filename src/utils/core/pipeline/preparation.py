"""Pipeline stage: decode samples and prepare audit tasks."""

import logging
import time
from typing import Any

from ...auditing import prepare_audit_task
from ..helpers import truncate_byte_arrays

logger = logging.getLogger(__name__)


class AnalyzerPipelinePreparationMixin:
    def _resolve_function_data_with_abi_status(self, selector: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        """Resolve selector metadata and record whether it truly exists in the merged ABI."""
        selector_lower = selector.lower()
        format_key = self.selector_to_format_key.get(selector_lower, selector)

        merged_abi_function = None
        if self.abi_helper and selector_lower.startswith("0x"):
            merged_abi_function = self.abi_helper.find_function_by_selector(selector_lower)

        if merged_abi_function:
            return merged_abi_function, {
                "status": "merged_abi",
                "selector": selector_lower,
                "format_key": format_key,
                "selector_found_in_merged_abi": True,
                "error": None,
            }

        function_data = self.get_function_abi_by_selector(selector)
        if function_data:
            error = (
                f"Selector {selector_lower} was not found in the merged ABI. "
                f"The analyzer used descriptor-derived fallback metadata from "
                f"'{format_key}' instead."
            )
            logger.warning(error)
            return function_data, {
                "status": "descriptor_fallback",
                "selector": selector_lower,
                "format_key": format_key,
                "selector_found_in_merged_abi": False,
                "error": error,
            }

        error = f"Selector {selector_lower} was not found in the merged ABI and no descriptor fallback metadata was available."
        logger.warning(error)
        return None, {
            "status": "not_found",
            "selector": selector_lower,
            "format_key": format_key,
            "selector_found_in_merged_abi": False,
            "error": error,
        }

    def _log_function_source_block(self, function_source: dict[str, Any]) -> None:
        """Log the final source snippet sent to the model."""
        if not function_source or not function_source.get("function"):
            return
        if not logger.isEnabledFor(logging.INFO):
            return

        code_block = f"\n{'=' * 60}\n"
        code_block += "SOURCE CODE (being sent to AI):\n"
        code_block += f"{'=' * 60}\n\n"

        if function_source.get("function_docstring"):
            code_block += f"// Docstring:\n{function_source['function_docstring']}\n\n"

        if function_source.get("custom_types"):
            code_block += "// Custom types:\n"
            for custom_type in function_source["custom_types"]:
                code_block += f"{custom_type}\n"
            code_block += "\n"

        if function_source.get("using_statements"):
            code_block += "// Using statements:\n"
            for using_stmt in function_source["using_statements"]:
                code_block += f"{using_stmt}\n"
            code_block += "\n"

        if function_source.get("constants"):
            code_block += "// Constants:\n"
            for constant in function_source["constants"]:
                code_block += f"{constant}\n"
            code_block += "\n"

        if function_source.get("modifiers"):
            code_block += "// Modifiers used by main function:\n"
            for modifier in function_source["modifiers"]:
                code_block += f"{modifier}\n\n"

        if function_source.get("structs"):
            code_block += "// Structs:\n"
            for struct in function_source["structs"]:
                code_block += f"{struct}\n"
            code_block += "\n"

        if function_source.get("enums"):
            code_block += "// Enums:\n"
            for enum in function_source["enums"]:
                code_block += f"{enum}\n"
            code_block += "\n"

        code_block += "// Main function:\n"
        code_block += function_source["function"]

        if function_source.get("internal_functions"):
            code_block += "\n\n// Internal functions called:\n"
            for internal_func in function_source["internal_functions"]:
                if internal_func.get("docstring"):
                    code_block += f"{internal_func['docstring']}\n"
                code_block += f"{internal_func['body']}\n\n"

        if function_source.get("parent_functions"):
            code_block += "\n\n// Parent contract implementations (from super. calls):\n"
            for parent_func in function_source["parent_functions"]:
                parent_name = parent_func.get("parent_contract", "Unknown")
                func_name = parent_func.get("function_name", "unknown")
                code_block += f"// From {parent_name}.{func_name}():\n"
                code_block += f"{parent_func['body']}\n\n"

        if function_source.get("libraries"):
            code_block += "\n// Libraries:\n"
            for library in function_source["libraries"]:
                code_block += f"{library}\n\n"

        code_block += f"\n{'=' * 60}\n"
        logger.debug(code_block)

    def _build_missing_abi_report_data(
        self,
        *,
        selector: str,
        function_signature: str,
        erc7730_format: dict[str, Any],
        abi_resolution: dict[str, Any],
        format_key: str,
    ) -> dict[str, Any]:
        """Build a synthetic critical report when selector is absent from the merged ABI."""
        error_text = abi_resolution.get("error") or "Selector was not found in the merged ABI."
        issue_summary = "Selector not found in merged ABI"
        details = {
            "what_descriptor_shows": (
                "The descriptor defines this function key and the analyzer can calculate a selector from it."
            ),
            "what_actually_happens": (
                "This selector was not found in the merged ABI fetched from the configured deployments, "
                "so the descriptor could not be anchored to a verified live ABI entry for this run."
            ),
            "why_critical": (
                "Without a merged-ABI match, transaction fetching, source-code resolution, and AI analysis were "
                "skipped because the descriptor may target an outdated or wrong function."
            ),
            "evidence": error_text,
        }
        return {
            "function_signature": function_signature,
            "selector": selector,
            "erc7730_format": erc7730_format,
            "descriptor_format_key": format_key,
            "abi_resolution": abi_resolution,
            "critical_issues": [{"issue": issue_summary, "details": details}],
            "recommendations": {"fixes": [], "spec_limitations": [], "optional_improvements": []},
            "intent_analysis": {
                "declared_intent": "Skipped",
                "assessment": error_text,
                "spelling_errors": [],
            },
            "missing_parameters": [],
            "display_issues": [],
            "transaction_samples": [],
            "overall_assessment": {
                "coverage_score": {
                    "score": 0,
                    "explanation": "Analysis was skipped because the selector is not present in the merged ABI.",
                },
                "security_risk": {
                    "level": "high",
                    "reasoning": (
                        "The descriptor is not matched to any function in the merged ABI for this run, so the "
                        "analyzer cannot verify that it describes a currently deployed function."
                    ),
                },
            },
        }

    def _build_selector_task_entry(
        self,
        *,
        context: dict[str, Any],
        selector: str,
        function_data: dict[str, Any],
        abi_resolution: dict[str, Any],
        selector_deployment: dict[str, Any],
        decoded_txs: list[dict[str, Any]],
        function_source: dict[str, Any] = None,
        source_resolution: dict[str, Any] = None,
        synthetic_report_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build one prepared selector entry from already collected inputs."""
        erc7730_data = context["erc7730_data"]
        deployments = context["deployments"]
        function_name = function_data["name"]

        format_key = self.selector_to_format_key.get(selector, selector)
        abi_format_match = None
        if not (format_key.startswith("0x") and len(format_key) == 10):
            abi_format_match = self._match_function_signature_to_abi(format_key)

        normalized_format_key = (
            abi_format_match.get("signature")
            if abi_format_match
            else (
                self._normalize_function_signature(format_key)
                if hasattr(self, "_normalize_function_signature")
                else format_key
            )
        )
        selector_lower = selector.lower()
        if format_key.startswith("0x") and len(format_key) == 10:
            format_key_selector = format_key.lower()
            format_key_function_name = None
        else:
            format_key_selector = (
                "0x" + self.w3.keccak(text=normalized_format_key).hex()[:8] if normalized_format_key else None
            )
            format_key_function_name = format_key.split("(", 1)[0].strip() if "(" in format_key else format_key.strip()

        if format_key.startswith("0x") and len(format_key) == 10:
            descriptor_key_style = "legacy_selector"
        elif abi_format_match and format_key == abi_format_match.get("display_signature"):
            descriptor_key_style = "signature_with_names"
        elif normalized_format_key == format_key:
            descriptor_key_style = "canonical_signature"
        else:
            descriptor_key_style = "signature_with_names"

        erc7730_format = erc7730_data.get("display", {}).get("formats", {}).get(format_key, {})

        from ...reporting.reporter import expand_erc7730_format_with_refs

        erc7730_format_expanded = expand_erc7730_format_with_refs(erc7730_format, erc7730_data, format_key)

        source_resolution = source_resolution or {
            "match_mode": "not_found",
            "chain_id": None,
            "address": None,
            "selector_mapped": selector in self.selector_sources,
            "truncated": False,
        }

        self._log_function_source_block(function_source)

        audit_task = None
        if erc7730_format and abi_resolution.get("status") == "merged_abi":
            has_no_transactions = not decoded_txs
            if has_no_transactions:
                logger.debug(f"Preparing STATIC audit task for {selector} (no transactions)")
            else:
                logger.debug(f"Preparing audit task for {selector}")

            descriptor_context = {
                "kind": "contract",
                "format_key": format_key,
                "normalized_format_key": normalized_format_key,
                "descriptor_key_style": descriptor_key_style,
                "function_name": function_name,
                "function_signature": function_data["signature"],
                "deployments": deployments,
                "selector_deployment": selector_deployment,
                "binding_checks": {
                    "selector": selector_lower,
                    "format_key": format_key,
                    "normalized_format_key": normalized_format_key,
                    "format_key_selector": format_key_selector,
                    "format_key_function_name": format_key_function_name,
                    "format_key_matches_selector": format_key_selector == selector_lower
                    if format_key_selector
                    else None,
                    "format_key_matches_function_signature": (
                        normalized_format_key == function_data["signature"]
                        if not (format_key.startswith("0x") and len(format_key) == 10)
                        else None
                    ),
                    "format_key_matches_function_name": (
                        format_key_function_name == function_name if format_key_function_name else None
                    ),
                },
            }
            factory_constraint = erc7730_data.get("context", {}).get("contract", {}).get("factory")
            if factory_constraint:
                descriptor_context["factory"] = factory_constraint

            screenshot_map = context.get("screenshot_data", {})
            selector_screenshot_data = screenshot_map.get(selector.lower()) or None

            audit_task = prepare_audit_task(
                selector=selector,
                decoded_transactions=decoded_txs,
                erc7730_format=erc7730_format_expanded,
                function_signature=function_data["signature"],
                source_code=function_source,
                use_smart_referencing=self.use_smart_referencing,
                erc4626_context=self.erc4626_context,
                erc20_context=self.erc20_context,
                protocol_name=self.protocol_name,
                descriptor_context=descriptor_context,
                abi_resolution=abi_resolution,
                source_resolution=source_resolution,
                analysis_mode=self.analysis_mode,
                tool_context={
                    "abi": context["abi"],
                    "deployments": deployments,
                    "erc7730_data": erc7730_data,
                    "extracted_codes": self.extracted_codes,
                    "source_extractor": self.source_extractor,
                    "selector_sources": self.selector_sources,
                    "selector_to_format_key": self.selector_to_format_key,
                    "selector_deployment": selector_deployment,
                    "max_selector_tool_rounds": self.max_selector_tool_rounds,
                    "max_tool_requests_per_round": self.max_tool_requests_per_round,
                    "analysis_memory": context.setdefault("analysis_memory", {}),
                },
                screenshot_data=selector_screenshot_data,
                llm_model=self.llm_model,
                llm_reasoning_effort=self.llm_reasoning_effort,
            )

        return {
            "selector": selector,
            "format_key": format_key,
            "function_name": function_name,
            "function_data": function_data,
            "abi_resolution": abi_resolution,
            "selector_deployment": selector_deployment,
            "decoded_txs": decoded_txs,
            "erc7730_format": erc7730_format,
            "function_source": function_source,
            "source_resolution": source_resolution,
            "audit_task": audit_task,
            "synthetic_report_data": synthetic_report_data,
        }

    def _prepare_selector_audit_tasks(self, context: dict[str, Any]) -> None:
        """Prepare decoded tx samples, source snippets, and audit payload tasks."""
        selectors = context["selectors"]
        all_selector_txs = context["all_selector_txs"]
        deployment_per_selector = context["deployment_per_selector"]
        default_deployment = context["default_deployment"]
        erc7730_data = context["erc7730_data"]
        selector_abi_resolution = context.get("selector_abi_resolution", {})
        selector_function_data = context.get("selector_function_data", {})
        # ====================================================================
        # PHASE 1: PRE-PROCESSING (Sequential - maintains log coherence)
        # ====================================================================
        # Prepare all data and audit tasks before making any API calls.
        # This keeps the preparation logs in order and allows batch API calls.

        logger.info(f"\n{'=' * 60}")
        logger.info(f"PHASE 1: Preparing audit tasks for {len(selectors)} selectors...")
        logger.info(f"{'=' * 60}")

        # Store prepared data for each selector
        prepared_selectors = []  # List of dicts with all pre-processed data

        for selector in selectors:
            logger.info(f"Preparing selector: {selector}")

            # Get function metadata
            function_data = selector_function_data.get(selector.lower())
            abi_resolution = selector_abi_resolution.get(selector.lower())
            if function_data is None or abi_resolution is None:
                function_data, abi_resolution = self._resolve_function_data_with_abi_status(selector)
            if not function_data:
                logger.warning(f"Skipping selector {selector} - no matching ABI entry")
                continue

            function_name = function_data["name"]
            logger.debug(f"Function name: {function_name}")
            logger.debug(f"Function signature: {function_data['signature']}")

            if abi_resolution.get("status") != "merged_abi":
                logger.warning(
                    "Skipping tx/source/AI for %s because it was not found in the merged ABI",
                    selector,
                )
                selector_deployment = deployment_per_selector.get(selector.lower(), default_deployment)
                synthetic_report_data = self._build_missing_abi_report_data(
                    selector=selector,
                    function_signature=function_data["signature"],
                    erc7730_format=erc7730_data.get("display", {}).get("formats", {}).get(
                        self.selector_to_format_key.get(selector, selector), {}
                    ),
                    abi_resolution=abi_resolution,
                    format_key=self.selector_to_format_key.get(selector, selector),
                )
                prepared_selectors.append(
                    self._build_selector_task_entry(
                        context=context,
                        selector=selector,
                        function_data=function_data,
                        abi_resolution=abi_resolution,
                        selector_deployment=selector_deployment,
                        decoded_txs=[],
                        function_source=None,
                        source_resolution={
                            "match_mode": "skipped_missing_abi",
                            "chain_id": None,
                            "address": None,
                            "selector_mapped": selector in self.selector_sources,
                            "truncated": False,
                        },
                        synthetic_report_data=synthetic_report_data,
                    )
                )
                continue

            # Get the pre-fetched transactions for this selector
            transactions = all_selector_txs.get(selector.lower(), [])

            # Get the deployment used for this selector (for chain_id and contract_address)
            selector_deployment = deployment_per_selector.get(selector.lower(), default_deployment)

            if not transactions:
                logger.warning(f"No transactions found for selector {selector} - will perform static analysis only")
            else:
                logger.debug(
                    f"Found {len(transactions)} transactions for selector {selector} on chain {selector_deployment['chainId']}"
                )

            # Decode each transaction
            decoded_txs = []
            for i, tx in enumerate(transactions, 1):
                logger.debug(f"\nTransaction {i}/{len(transactions)}: {tx['hash']}")

                decoded = self.tx_fetcher.decode_transaction_input(tx["input"], function_data, self.abi_helper)
                if decoded is not None:
                    # Extract _raw_fallback before truncation (keep it intact for AI)
                    raw_fallback = decoded.pop("_raw_fallback", None)

                    # Truncate large byte arrays to reduce token usage
                    decoded_clean = truncate_byte_arrays(decoded, max_bytes_length=100)

                    # Re-add raw fallback if it existed (untruncated)
                    if raw_fallback:
                        decoded_clean["_raw_fallback"] = raw_fallback

                    tx_data = {
                        "hash": tx["hash"],
                        "block": tx["blockNumber"],
                        "timestamp": tx["timeStamp"],
                        "from": tx["from"],
                        "to": tx.get("to", ""),
                        "value": tx["value"],
                        "decoded_input": decoded_clean,
                    }

                    # Fetch transaction receipt and decode logs
                    # Only fetch receipt if we have a valid transaction hash (starts with 0x and is 66 chars)
                    tx_hash = tx.get("hash", "")
                    if tx_hash.startswith("0x") and len(tx_hash) == 66:
                        logger.debug(f"Fetching receipt for transaction {tx_hash}")
                        receipt = self.tx_fetcher.fetch_transaction_receipt(tx_hash, selector_deployment["chainId"])
                    else:
                        logger.debug(f"Skipping receipt fetch for transaction {tx_hash} (not a valid TX hash)")
                        receipt = None

                    if receipt and receipt.get("logs"):
                        decoded_logs = []
                        for log in receipt["logs"]:
                            decoded_log = self.tx_fetcher.decode_log_event(log, selector_deployment["chainId"])
                            if decoded_log:
                                decoded_logs.append(decoded_log)

                        if decoded_logs:
                            tx_data["receipt_logs"] = decoded_logs
                            logger.debug(f"Decoded {len(decoded_logs)} log events:")
                            for log in decoded_logs:
                                if log.get("event") == "Transfer":
                                    logger.debug(
                                        f"  Transfer: {log['value_formatted']} from {log['from'][:10]}... to {log['to'][:10]}..."
                                    )
                                elif log.get("event") == "Approval":
                                    logger.debug(
                                        f"  Approval: {log['value_formatted']} from {log['owner'][:10]}... to {log['spender'][:10]}..."
                                    )
                                else:
                                    logger.debug(
                                        f"  {log.get('event', 'Unknown')}: {log.get('address', 'unknown')[:10]}..."
                                    )

                    decoded_txs.append(tx_data)
                    time.sleep(0.2)

                    logger.debug("Decoded parameters:")
                    for param_name, param_value in decoded_clean.items():
                        logger.debug(f"  {param_name}: {param_value}")

            # Extract source code for this specific function (search across all deployments)
            function_source = None
            source_resolution = {
                "match_mode": "not_found",
                "chain_id": None,
                "address": None,
                "selector_mapped": selector in self.selector_sources,
                "truncated": False,
            }
            if self.extracted_codes:
                logger.debug(
                    f"Searching for function '{function_name}' ({function_data['signature']}) across {len(self.extracted_codes)} contract(s)..."
                )

                # PHASE 1: Search ALL contracts for EXACT SELECTOR match first
                logger.debug(
                    f"  Phase 1: Searching for exact selector match across all {len(self.extracted_codes)} contracts..."
                )
                for deployment_key, extracted_code in self.extracted_codes.items():
                    if not extracted_code["source_code"]:
                        continue

                    chain_id = extracted_code["chain_id"]
                    address = extracted_code["address"]
                    logger.debug(f"  Checking {address} on chain {chain_id} (selector only)...")

                    # Log what we know about this selector's mapping
                    if selector in self.selector_sources:
                        sources = self.selector_sources[selector]
                        source_chains = [s.get("chain_id") for s in sources]
                        logger.debug(f"    Selector {selector} is mapped to chains: {source_chains}")
                        if chain_id not in source_chains:
                            logger.debug(f"    → Skipping chain {chain_id} (selector not on this chain)")
                            continue

                    # Try to find by EXACT SELECTOR only (no name fallback)
                    function_source = self.source_extractor.get_function_with_dependencies(
                        function_name,
                        extracted_code,
                        function_signature=function_data["signature"],
                        max_lines=1000,
                        selector_only=True,  # Only match by exact selector, skip name matching
                        selector=selector,  # Pass selector for Diamond proxy facet-specific lookup
                    )

                    if function_source and function_source["function"]:
                        source_resolution = {
                            "match_mode": "exact_selector",
                            "chain_id": chain_id,
                            "address": address,
                            "selector_mapped": selector in self.selector_sources,
                            "truncated": bool(function_source.get("truncated")),
                        }
                        logger.debug(f"✓ Found EXACT SELECTOR MATCH at {address} on chain {chain_id}!")
                        logger.debug(f"✓ Extracted function code ({function_source['total_lines']} lines)")
                        logger.debug(f"  - Constants: {len(function_source.get('constants', []))}")
                        logger.debug(f"  - Modifiers: {len(function_source.get('modifiers', []))}")
                        logger.debug(f"  - Structs: {len(function_source['structs'])}")
                        logger.debug(f"  - Enums: {len(function_source['enums'])}")
                        logger.debug(f"  - Internal functions: {len(function_source['internal_functions'])}")
                        if function_source.get("parent_functions"):
                            logger.debug(
                                f"  - Parent functions (from super.): {len(function_source['parent_functions'])}"
                            )
                            for pf in function_source["parent_functions"]:
                                logger.debug(f"      └─ {pf['parent_contract']}.{pf['function_name']}()")
                        if function_source["truncated"]:
                            logger.debug("  ⚠ Code was truncated to fit within line limit")
                        break  # Stop searching - found exact selector match!

                # PHASE 2: If no exact selector match found, try NAME-based matching in first contract
                if not function_source or not function_source.get("function"):
                    logger.debug(
                        "  Phase 2: No exact selector match found. Trying name-based matching with inheritance in first contract..."
                    )

                    # IMPORTANT: Check if this selector is in any facet ABI
                    # If not, the ERC-7730 may refer to an old version that has been upgraded
                    if selector not in self.selector_sources:
                        logger.warning(f"  ⚠️  SELECTOR MISMATCH: {selector} is NOT in any facet ABI!")
                        logger.warning("  ⚠️  The ERC-7730 may refer to an OLD function version that has been upgraded.")
                        logger.warning(
                            "  ⚠️  Name-based matching may find a DIFFERENT version with different parameters!"
                        )

                    # Get extracted_code from a chain where the selector IS mapped
                    # This is critical for Diamond proxies - the selector may only exist on certain chains
                    first_extracted_code = None
                    first_deployment_key = None

                    # First, try to find a chain where this selector has a facet mapping
                    if selector in self.selector_sources:
                        mapped_chains = [s.get("chain_id") for s in self.selector_sources[selector]]
                        for deployment_key, extracted_code in self.extracted_codes.items():
                            if extracted_code["source_code"] and extracted_code.get("chain_id") in mapped_chains:
                                first_extracted_code = extracted_code
                                first_deployment_key = deployment_key
                                logger.debug(
                                    f"  Using extracted_code from chain {extracted_code.get('chain_id')} where selector is mapped"
                                )
                                break

                    # Fallback: use any contract with source code
                    if not first_extracted_code:
                        for deployment_key, extracted_code in self.extracted_codes.items():
                            if extracted_code["source_code"]:
                                first_extracted_code = extracted_code
                                first_deployment_key = deployment_key
                                break

                    if first_extracted_code:
                        chain_id = first_extracted_code["chain_id"]
                        address = first_extracted_code["address"]
                        logger.debug(f"  Checking {address} on chain {chain_id} (with name fallback)...")

                        function_source = self.source_extractor.get_function_with_dependencies(
                            function_name,
                            first_extracted_code,
                            function_signature=function_data["signature"],
                            max_lines=1000,
                            selector_only=False,  # Allow name-based fallback with inheritance
                            selector=selector,  # Pass selector for Diamond proxy facet-specific lookup
                        )

                        if function_source and function_source["function"]:
                            source_resolution = {
                                "match_mode": "name_fallback",
                                "chain_id": chain_id,
                                "address": address,
                                "selector_mapped": selector in self.selector_sources,
                                "truncated": bool(function_source.get("truncated")),
                            }
                            logger.debug(f"✓ Found by name (with inheritance) at {address} on chain {chain_id}")
                            logger.debug(f"✓ Extracted function code ({function_source['total_lines']} lines)")
                            logger.debug(f"  - Constants: {len(function_source.get('constants', []))}")
                            logger.debug(f"  - Modifiers: {len(function_source.get('modifiers', []))}")
                            logger.debug(f"  - Structs: {len(function_source['structs'])}")
                            logger.debug(f"  - Enums: {len(function_source['enums'])}")
                            logger.debug(f"  - Internal functions: {len(function_source['internal_functions'])}")
                            if function_source.get("parent_functions"):
                                logger.debug(
                                    f"  - Parent functions (from super.): {len(function_source['parent_functions'])}"
                                )
                                for pf in function_source["parent_functions"]:
                                    logger.debug(f"      └─ {pf['parent_contract']}.{pf['function_name']}()")
                            if function_source["truncated"]:
                                logger.debug("  ⚠ Code was truncated to fit within line limit")

                if not function_source or not function_source.get("function"):
                    logger.warning(
                        f"Function '{function_name}' not found in any of the {len(self.extracted_codes)} contract(s)"
                    )

            prepared_selectors.append(
                self._build_selector_task_entry(
                    context=context,
                    selector=selector,
                    function_data=function_data,
                    abi_resolution=abi_resolution,
                    selector_deployment=selector_deployment,
                    decoded_txs=decoded_txs,
                    function_source=function_source,
                    source_resolution=source_resolution,
                    synthetic_report_data=None,
                )
            )

        logger.info(f"\n{'=' * 60}")
        logger.info(f"PHASE 1 COMPLETE: Prepared {len(prepared_selectors)} audit tasks")
        logger.info(f"{'=' * 60}")
        context["prepared_selectors"] = prepared_selectors

    def _prepare_selector_audit_tasks_from_prepared_inputs(self, context: dict[str, Any]) -> None:
        """Build audit tasks from a frozen benchmark-input snapshot."""
        selectors = context["selectors"]
        deployments = context["deployments"]
        prepared_inputs_data = context.get("prepared_inputs_data") or {}
        default_deployment = (
            deployments[0]
            if deployments
            else {
                "address": "N/A",
                "chainId": 1,
            }
        )

        prepared_selector_inputs = prepared_inputs_data.get("selectors") or {}
        extracted_codes = prepared_inputs_data.get("extracted_codes")
        selector_abi_resolution = context.get("selector_abi_resolution", {})
        selector_function_data = context.get("selector_function_data", {})
        if not prepared_selector_inputs and isinstance(prepared_inputs_data.get("contracts"), dict):
            prepared_selector_inputs = {}
            extracted_codes = extracted_codes if isinstance(extracted_codes, dict) else {}

            for contract_key, contract_entry in prepared_inputs_data["contracts"].items():
                if not isinstance(contract_entry, dict):
                    continue

                contract_address = contract_entry.get("address") or contract_key
                chain_id = int(contract_entry.get("chainId") or 1)
                selector_deployment = {
                    "address": contract_address,
                    "chainId": chain_id,
                }

                selector_meta = contract_entry.get("selectors") or {}
                source_by_selector = contract_entry.get("source_code") or {}
                tx_by_selector = contract_entry.get("transactions") or {}

                selector_keys = (
                    {str(key).lower() for key in selector_meta.keys()}
                    | {str(key).lower() for key in source_by_selector.keys()}
                    | {str(key).lower() for key in tx_by_selector.keys()}
                )

                for selector_key in selector_keys:
                    meta = selector_meta.get(selector_key) or selector_meta.get(selector_key.lower()) or {}
                    source_packet = source_by_selector.get(selector_key) or source_by_selector.get(selector_key.lower())
                    tx_samples = tx_by_selector.get(selector_key) or tx_by_selector.get(selector_key.lower()) or []

                    prepared_selector_inputs[selector_key] = {
                        **meta,
                        "selector_deployment": meta.get("selector_deployment") or selector_deployment,
                        "function_source": meta.get("function_source") or source_packet,
                        "decoded_transactions": (
                            meta.get("decoded_transactions") or meta.get("decoded_txs") or tx_samples
                        ),
                    }

        self.extracted_codes = extracted_codes if isinstance(extracted_codes, dict) else {}
        self.erc4626_context = prepared_inputs_data.get("erc4626_context")
        self.erc20_context = prepared_inputs_data.get("erc20_context")
        if prepared_inputs_data.get("protocol_name"):
            self.protocol_name = prepared_inputs_data["protocol_name"]

        logger.info(f"\n{'=' * 60}")
        logger.info(f"PHASE 1: Preparing audit tasks for {len(selectors)} selectors from prepared benchmark inputs...")
        logger.info(f"{'=' * 60}")
        logger.debug(f"Loaded {len(self.extracted_codes)} cached source packet(s) from prepared benchmark inputs")

        prepared_selectors = []
        for selector in selectors:
            logger.info(f"Preparing selector from frozen inputs: {selector}")

            function_data = selector_function_data.get(selector.lower())
            abi_resolution = selector_abi_resolution.get(selector.lower())
            if function_data is None or abi_resolution is None:
                function_data, abi_resolution = self._resolve_function_data_with_abi_status(selector)
            if not function_data:
                format_key = self.selector_to_format_key.get(selector, selector)
                function_data = self._build_function_metadata_from_format_key(
                    format_key,
                    selector=selector,
                )
                if function_data:
                    abi_resolution = {
                        "status": "descriptor_fallback",
                        "selector": selector.lower(),
                        "format_key": format_key,
                        "selector_found_in_merged_abi": False,
                        "error": (
                            f"Selector {selector.lower()} was not found in the merged ABI. "
                            f"The analyzer used descriptor-derived fallback metadata from "
                            f"'{format_key}' instead."
                        ),
                    }
                    logger.debug(
                        f"Using descriptor-derived function metadata for {selector}: {function_data['signature']}"
                    )
                else:
                    logger.warning(f"Skipping selector {selector} - no matching ABI entry or descriptor fallback")
                    continue

            function_name = function_data["name"]
            logger.debug(f"Function name: {function_name}")
            logger.debug(f"Function signature: {function_data['signature']}")

            selector_inputs = (
                prepared_selector_inputs.get(selector) or prepared_selector_inputs.get(selector.lower()) or {}
            )
            if not selector_inputs:
                logger.warning(f"No frozen selector inputs found for {selector} - continuing with static-only context")

            selector_deployment = selector_inputs.get("selector_deployment") or default_deployment
            decoded_txs = selector_inputs.get("decoded_transactions") or selector_inputs.get("decoded_txs") or []
            function_source = selector_inputs.get("function_source")
            source_resolution = selector_inputs.get("source_resolution") or {
                "match_mode": "prepared_missing",
                "chain_id": selector_deployment.get("chainId"),
                "address": selector_deployment.get("address"),
                "selector_mapped": selector in self.selector_sources,
                "truncated": False,
            }

            synthetic_report_data = None
            if abi_resolution.get("status") != "merged_abi":
                logger.warning(
                    "Skipping cached tx/source/AI for %s because it was not found in the merged ABI",
                    selector,
                )
                decoded_txs = []
                function_source = None
                source_resolution = {
                    "match_mode": "skipped_missing_abi",
                    "chain_id": None,
                    "address": None,
                    "selector_mapped": selector in self.selector_sources,
                    "truncated": False,
                }
                synthetic_report_data = self._build_missing_abi_report_data(
                    selector=selector,
                    function_signature=function_data["signature"],
                    erc7730_format=erc7730_data.get("display", {}).get("formats", {}).get(
                        self.selector_to_format_key.get(selector, selector), {}
                    ),
                    abi_resolution=abi_resolution,
                    format_key=self.selector_to_format_key.get(selector, selector),
                )

            logger.debug(
                f"Loaded {len(decoded_txs)} decoded transaction(s) and "
                f"{'found' if function_source else 'did not find'} cached source context for {selector}"
            )

            prepared_selectors.append(
                self._build_selector_task_entry(
                    context=context,
                    selector=selector,
                    function_data=function_data,
                    abi_resolution=abi_resolution,
                    selector_deployment=selector_deployment,
                    decoded_txs=decoded_txs,
                    function_source=function_source,
                    source_resolution=source_resolution,
                    synthetic_report_data=synthetic_report_data,
                )
            )

        logger.info(f"\n{'=' * 60}")
        logger.info(f"PHASE 1 COMPLETE: Prepared {len(prepared_selectors)} audit tasks from frozen benchmark inputs")
        logger.info(f"{'=' * 60}")
        context["prepared_selectors"] = prepared_selectors
