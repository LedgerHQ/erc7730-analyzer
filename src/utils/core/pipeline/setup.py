"""Pipeline stage: descriptor/ABI loading and selector setup."""

import json
import logging
from pathlib import Path
from typing import Any

import requests

from ...abi import ABI, fetch_contract_abi
from ...abi.merger import ABIMerger, merge_abis_from_deployments

logger = logging.getLogger(__name__)


class AnalyzerPipelineSetupMixin:
    def _extract_abi_from_prepared_inputs(
        self,
        prepared_inputs_data: dict[str, Any],
    ) -> tuple[list[dict[str, Any]] | None, dict[str, str]]:
        """Return a merged ABI from either legacy or address-keyed prepared inputs."""
        prepared_abi = prepared_inputs_data.get("abi")
        if isinstance(prepared_abi, list) and prepared_abi:
            selector_sources = prepared_inputs_data.get("selector_sources") or {}
            return prepared_abi, selector_sources if isinstance(selector_sources, dict) else {}

        contracts = prepared_inputs_data.get("contracts")
        if not isinstance(contracts, dict) or not contracts:
            return None, {}

        merger = ABIMerger()
        contract_count = 0
        for contract_key, contract_entry in contracts.items():
            if not isinstance(contract_entry, dict):
                continue

            contract_abi = contract_entry.get("abi")
            if not isinstance(contract_abi, list) or not contract_abi:
                continue

            address = contract_entry.get("address") or contract_key
            chain_id = int(contract_entry.get("chainId") or 1)
            merger.add_abi(contract_abi, chain_id, str(address), source_kind="deployment")
            contract_count += 1

        if contract_count == 0:
            return None, {}

        logger.info(f"Merged prepared benchmark ABI from {contract_count} contract bucket(s)")
        return merger.get_merged_abi(), merger.get_selector_sources()

    def _setup_analysis_context(
        self,
        erc7730_file: Path,
        abi_file: Path | None = None,
        prepared_inputs_file: Path | None = None,
    ) -> dict[str, Any] | None:
        """Load descriptor, deployments, ABI, selectors, and base result structure."""
        logger.info(f"Starting analysis of {erc7730_file}")

        prepared_inputs_data = None
        if prepared_inputs_file and prepared_inputs_file.exists() and prepared_inputs_file.is_file():
            logger.info(f"Loading prepared benchmark inputs from {prepared_inputs_file}")
            try:
                with open(prepared_inputs_file, encoding="utf-8") as f:
                    prepared_inputs_data = json.load(f)
                if not isinstance(prepared_inputs_data, dict):
                    raise ValueError("prepared inputs file must contain a JSON object")
            except Exception as exc:
                logger.error(f"Failed to load prepared benchmark inputs: {exc}")
                return None

        # Parse ERC-7730 file
        erc7730_data = self.parse_erc7730_file(erc7730_file)

        # Extract protocol name from descriptor (try multiple fields)
        context = erc7730_data.get("context", {})
        metadata = erc7730_data.get("metadata", {})
        protocol_name = None

        # Try $id first
        if context.get("$id"):
            protocol_name = context["$id"]
        # Try v2 metadata.contractName
        elif metadata.get("contractName"):
            protocol_name = metadata["contractName"]
        # Try metadata owner
        elif metadata.get("owner"):
            protocol_name = metadata["owner"]
        # Legacy fallback
        elif metadata.get("info", {}).get("legalName"):
            protocol_name = metadata["info"]["legalName"]

        # Store protocol name for use in audit tasks
        self.protocol_name = protocol_name

        # Extract contract deployments
        deployments = self.get_contract_deployments(erc7730_data)
        if not deployments:
            logger.error("Could not extract contract deployments from ERC-7730 file")
            return None

        # Get ABI - check if it's embedded in the ERC-7730 file
        abi = erc7730_data.get("context", {}).get("contract", {}).get("abi")

        # Check if ABI is a URL string
        if abi and isinstance(abi, str):
            logger.info(f"ABI is a URL, fetching from: {abi}")
            try:
                response = requests.get(abi, timeout=10)
                response.raise_for_status()
                data = response.json()

                # Handle Etherscan API response format vs. direct JSON
                if isinstance(data, dict) and "result" in data:
                    if isinstance(data["result"], str):
                        abi = json.loads(data["result"])
                    else:
                        abi = data["result"]
                else:
                    abi = data

                logger.info(f"Successfully fetched ABI from URL ({len(abi)} entries)")
            except Exception as e:
                logger.warning(f"Failed to fetch ABI from URL: {e}")
                logger.info("Falling back to next ABI source...")
                abi = None

        # Check if we have a valid ABI from ERC-7730 file
        if abi and isinstance(abi, list) and len(abi) > 0:
            logger.info(f"Using ABI from ERC-7730 file ({len(abi)} entries)")
        elif abi_file and abi_file.exists() and abi_file.is_file():
            # Try loading from ABI file if provided and valid
            logger.info(f"Loading ABI from file: {abi_file}")
            try:
                with open(abi_file) as f:
                    abi = json.load(f)
                logger.info(f"Successfully loaded ABI from file ({len(abi)} entries)")
            except Exception as e:
                logger.warning(f"Failed to load ABI from file: {e}")
                logger.info("Falling back to API fetch...")
                abi = None
        elif prepared_inputs_data:
            abi, prepared_selector_sources = self._extract_abi_from_prepared_inputs(prepared_inputs_data)
            if abi and isinstance(abi, list) and len(abi) > 0:
                logger.info(f"Using ABI from prepared benchmark inputs ({len(abi)} entries)")
                if prepared_selector_sources:
                    self.selector_sources = prepared_selector_sources
            else:
                abi = None

        # If no ABI yet, fetch from deployments via API
        if not abi or not isinstance(abi, list) or len(abi) == 0:
            logger.info("No ABI from ERC-7730 file or ABI file, fetching from API...")
            # Fetch and merge ABIs from all deployments
            abi, fetch_results, selector_sources = merge_abis_from_deployments(
                deployments, fetch_contract_abi, self.etherscan_api_key
            )
            # Store selector sources for efficient Diamond proxy source extraction
            self.selector_sources = selector_sources
            if selector_sources:
                logger.info(f"Stored {len(selector_sources)} selector provenance entries for source extraction")

        if not abi:
            logger.error("Could not obtain contract ABI from any source (ERC-7730, file, or API)")
            return None

        # Initialize the ABI helper
        self.abi_helper = ABI(abi)
        logger.info("ABI helper initialized")

        # Extract selectors and their mapping to format keys
        selectors, self.selector_to_format_key = self.extract_selectors(erc7730_data)

        if prepared_inputs_data:
            selector_sources = prepared_inputs_data.get("selector_sources")
            if isinstance(selector_sources, dict) and selector_sources:
                self.selector_sources = selector_sources
                logger.info(
                    f"Loaded {len(self.selector_sources)} selector provenance entries from prepared benchmark inputs"
                )

        # If selector_sources is empty but we have selectors, try Diamond detection on ALL deployments
        # This handles the case where ABI came from file/URL
        logger.info(
            f"Diamond detection check: selector_sources={len(self.selector_sources)}, selectors={len(selectors)}, deployments={len(deployments)}, has_api_key={bool(self.etherscan_api_key)}"
        )
        if not self.selector_sources and selectors and deployments and self.etherscan_api_key:
            logger.info("ABI loaded from file/URL - checking ALL deployments for Diamond proxy pattern...")
            from ...abi import detect_diamond_proxy as detect_diamond_abi
            from ...abi.merger import ABIMerger

            merger = ABIMerger()

            for deployment in deployments:
                dep_address = deployment.get("address", "")
                dep_chain_id = deployment.get("chainId", 1)

                logger.info(f"Checking {dep_address} on chain {dep_chain_id} for Diamond proxy...")
                facet_addresses = detect_diamond_abi(dep_address, dep_chain_id, self.etherscan_api_key)

                if facet_addresses:
                    logger.info(f"✓ Diamond proxy detected on chain {dep_chain_id} with {len(facet_addresses)} facets")
                    logger.info(
                        f"  Facet addresses: {[f[:10] + '...' for f in facet_addresses[:5]]}{'...' if len(facet_addresses) > 5 else ''}"
                    )

                    # Fetch ABIs from all facets to build selector→facet mapping
                    success_count = 0
                    fail_count = 0
                    total_functions = 0
                    for facet_addr in facet_addresses:
                        try:
                            # Fetch ABI for this facet
                            params = {
                                "module": "contract",
                                "action": "getabi",
                                "address": facet_addr,
                                "apikey": self.etherscan_api_key,
                            }
                            base_url = f"https://api.etherscan.io/v2/api?chainid={dep_chain_id}"
                            response = requests.get(base_url, params=params, timeout=15)
                            data = response.json()

                            if data.get("status") == "1":
                                facet_abi = json.loads(data["result"])
                                func_count = len([item for item in facet_abi if item.get("type") == "function"])
                                merger.add_abi(facet_abi, dep_chain_id, facet_addr, source_kind="facet")
                                success_count += 1
                                total_functions += func_count
                                logger.info(f"    ✓ {facet_addr[:10]}...: {func_count} functions")
                            else:
                                fail_count += 1
                                error_msg = data.get("message", data.get("result", "unknown error"))
                                logger.warning(f"    ✗ {facet_addr[:10]}...: {error_msg}")
                        except Exception as e:
                            fail_count += 1
                            logger.warning(f"    ✗ {facet_addr[:10]}...: {e}")

                    logger.info(
                        f"  Summary: {success_count}/{len(facet_addresses)} facets, {total_functions} total functions (chain {dep_chain_id})"
                    )
                else:
                    logger.debug(f"Not a Diamond proxy on chain {dep_chain_id}")

            # Get selector→facet mappings from all deployments
            self.selector_sources = merger.get_selector_sources()
            if self.selector_sources:
                # Log selector count and check if our target selectors are in there
                logger.info(
                    f"✓ Built {len(self.selector_sources)} selector→facet mappings from all Diamond deployments"
                )
                # Check how many of our ERC-7730 selectors are mapped
                mapped_count = sum(1 for s in selectors if s in self.selector_sources)
                logger.info(f"  Coverage: {mapped_count}/{len(selectors)} ERC-7730 selectors have mappings")
                if mapped_count < len(selectors):
                    missing = [s for s in selectors if s not in self.selector_sources][:5]
                    logger.warning(f"  Missing selectors (first 5): {missing}")

            # For any selectors not yet mapped, try facetAddress(selector) calls as fallback
            # facetAddress() is reliable - if it returns a valid address, the bytecode has this selector
            # The issue may be that the verified source code doesn't match the bytecode
            missing_selectors = [s for s in selectors if s not in self.selector_sources]
            if missing_selectors and self.source_extractor:
                logger.info(f"Attempting facetAddress() fallback for {len(missing_selectors)} unmapped selectors...")
                for deployment in deployments:
                    dep_address = deployment.get("address", "")
                    dep_chain_id = deployment.get("chainId", 1)

                    # Use source_code.py's detect_diamond_proxy which calls facetAddress(selector)
                    facet_mapping = self.source_extractor.detect_diamond_proxy(
                        dep_address, dep_chain_id, missing_selectors
                    )

                    if facet_mapping and "_is_diamond_but_unmapped" not in facet_mapping:
                        for selector, facet_addr in facet_mapping.items():
                            if selector not in self.selector_sources:
                                self.selector_sources[selector] = [
                                    {
                                        "facet_address": facet_addr,
                                        "chain_id": dep_chain_id,
                                        "source_kind": "facet",
                                        "from_facetAddress": True,  # Mark that this came from facetAddress() call
                                    }
                                ]
                        logger.info(
                            f"  Found {len(facet_mapping)} additional mappings via facetAddress() on chain {dep_chain_id}"
                        )
                        # Update missing list
                        missing_selectors = [s for s in selectors if s not in self.selector_sources]
                        if not missing_selectors:
                            break

                if missing_selectors:
                    logger.warning(f"Still missing mappings for {len(missing_selectors)} selectors after fallback")

        selector_abi_resolution = {}
        selector_function_data = {}
        abi_backed_selectors = []
        descriptor_fallback_selectors = []
        for selector in selectors:
            function_data, abi_resolution = self._resolve_function_data_with_abi_status(selector)
            selector_abi_resolution[selector.lower()] = abi_resolution
            if function_data:
                selector_function_data[selector.lower()] = function_data
            if abi_resolution.get("status") == "merged_abi":
                abi_backed_selectors.append(selector)
            else:
                descriptor_fallback_selectors.append(selector)

        logger.info(
            "Selector ABI coverage: %s/%s selector(s) found in merged ABI",
            len(abi_backed_selectors),
            len(selectors),
        )
        if descriptor_fallback_selectors:
            logger.error(
                "Selectors not found in merged ABI (descriptor fallback only): %s",
                descriptor_fallback_selectors,
            )

        # Analyze each selector
        results = {
            "deployments": deployments,
            "context": erc7730_data.get("context", {}),
            "erc7730_full": erc7730_data,  # Store full ERC-7730 data for reference expansion
            "erc4626_context": self.erc4626_context,  # Include ERC4626 vault context if detected
            "erc20_context": self.erc20_context,  # Include ERC20 token context if detected
            "selectors": {},
        }

        return {
            "erc7730_data": erc7730_data,
            "deployments": deployments,
            "abi": abi,
            "selectors": selectors,
            "abi_backed_selectors": abi_backed_selectors,
            "selector_abi_resolution": selector_abi_resolution,
            "selector_function_data": selector_function_data,
            "results": results,
            "prepared_inputs_data": prepared_inputs_data,
        }
