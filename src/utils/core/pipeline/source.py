"""Pipeline stage: source extraction and ERC context enrichment."""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class AnalyzerPipelineSourceMixin:
    def _extract_source_and_context(self, context: Dict[str, Any]) -> None:
        """Extract source code and build ERC4626/ERC20 context when possible."""
        deployments = context['deployments']
        selectors = context['selectors']
        erc7730_data = context['erc7730_data']
        # Extract source code from ALL deployments (multi-chain support)
        if self.enable_source_code and self.source_extractor and deployments:
            logger.info(f"\n{'='*60}")
            logger.info("Extracting contract source code from all deployments...")
            logger.info(f"{'='*60}")
            
            # Clear cache to ensure fresh extraction with current selector_sources
            self.source_extractor.clear_cache()

            # Track which (chain_id, address) pairs we've already extracted to avoid duplicates
            extracted_contracts = set()

            for deployment in deployments:
                chain_id = deployment['chainId']
                address = deployment['address'].lower()  # Normalize to lowercase

                # Skip if we already extracted this specific contract
                contract_key = (chain_id, address)
                if contract_key in extracted_contracts:
                    logger.info(f"Skipping {address} on chain {chain_id} - already extracted")
                    continue

                logger.info(f"\n📦 Extracting from chain {chain_id} at {address}")
                
                # Log selector_sources state for debugging
                if self.selector_sources:
                    # Show a few sample mappings
                    sample_sels = list(self.selector_sources.keys())[:3]
                    logger.info(f"  Using {len(self.selector_sources)} selector→facet mappings (sample: {sample_sels})")
                else:
                    logger.warning(f"  No selector_sources available - Diamond detection may have failed")

                extracted_code = self.source_extractor.extract_contract_code(
                    address,
                    chain_id,
                    selectors=selectors,
                    selector_sources=self.selector_sources  # Pass selector→facet mapping for efficient Diamond extraction
                )

                if extracted_code['source_code']:
                    # Store with unique key combining chain_id and address
                    storage_key = f"{chain_id}_{address}"
                    self.extracted_codes[storage_key] = extracted_code
                    extracted_contracts.add(contract_key)

                    logger.info(f"✓ Source code extracted successfully for {address} on chain {chain_id}")
                    logger.info(f"  - Functions: {len(extracted_code['functions'])}")
                    logger.info(f"  - Structs: {len(extracted_code['structs'])}")
                    logger.info(f"  - Enums: {len(extracted_code['enums'])}")
                    if extracted_code['is_proxy']:
                        logger.info(f"  - Proxy detected, using implementation: {extracted_code['implementation']}")
                    if extracted_code['is_diamond']:
                        logger.info(f"  - Diamond proxy detected with {len(set(extracted_code['facets'].values()))} facets")
                else:
                    logger.warning(f"Could not extract source code for {address} on chain {chain_id}")

            if self.extracted_codes:
                logger.info(f"\n✓ Successfully extracted source code from {len(self.extracted_codes)} contract(s): {list(self.extracted_codes.keys())}")

                # Detect ERC4626 from source code if not already detected from includes
                if not self.erc4626_context:
                    logger.info("\n🔍 Checking source code for ERC4626 patterns...")
                    for deployment_key, extracted_code in self.extracted_codes.items():
                        if extracted_code.get('source_code') and isinstance(extracted_code['source_code'], str):
                            contract_name = extracted_code.get('contract_name')
                            source_detection = self._detect_erc4626_from_source(
                                extracted_code['source_code'],
                                contract_name=contract_name
                            )
                            if source_detection['is_erc4626']:
                                chain_id = extracted_code['chain_id']
                                address = extracted_code['address']
                                logger.info(f"🏦 ERC4626 vault confirmed from source code at {address} on chain {chain_id}")
                                logger.info(f"   Detection method: {source_detection.get('detection_patterns', [])}")

                                # Get underlying token from metadata constants if available
                                underlying_token = erc7730_data.get('metadata', {}).get('constants', {}).get('underlyingToken')
                                if underlying_token:
                                    logger.info(f"   Underlying token from metadata: {underlying_token}")

                                # Query on-chain asset() value
                                asset_from_chain = self._query_erc4626_asset(
                                    address,
                                    chain_id
                                )

                                self.erc4626_context = self._build_erc4626_context(
                                    includes_detected=False,
                                    source_detection=source_detection,
                                    underlying_token=underlying_token,
                                    asset_from_chain=asset_from_chain
                                )
                                logger.info(f"   ✓ ERC4626 context built successfully")
                                break  # Found ERC4626, no need to check other chains

                # Detect ERC20 from source code (if not ERC4626, since ERC4626 extends ERC20)
                if not self.erc20_context and not self.erc4626_context:
                    logger.info("\n🔍 Checking source code for ERC20 patterns...")
                    for deployment_key, extracted_code in self.extracted_codes.items():
                        if extracted_code.get('source_code') and isinstance(extracted_code['source_code'], str):
                            contract_name = extracted_code.get('contract_name')
                            source_detection = self._detect_erc20_from_source(
                                extracted_code['source_code'],
                                contract_name=contract_name
                            )
                            if source_detection['is_erc20']:
                                chain_id = extracted_code['chain_id']
                                address = extracted_code['address']
                                logger.info(f"🪙 ERC20 token confirmed from source code at {address} on chain {chain_id}")
                                logger.info(f"   Detection method: {source_detection.get('detected_patterns', [])}")

                                self.erc20_context = {
                                    'is_erc20_token': True,
                                    'contract_name': source_detection['main_contract'],
                                    'detected_patterns': source_detection['detected_patterns'],
                                    'detection_source': 'source_code'
                                }
                                logger.info(f"   ✓ ERC20 context built successfully")
                                break  # Found ERC20, no need to check other chains

                    if not self.erc4626_context:
                        logger.debug("   ✗ No ERC4626 patterns detected in source code")

                # If detected from includes but no on-chain query yet, do it now
                if self.erc4626_context and not self.erc4626_context.get('asset_from_chain'):
                    logger.info("🔍 Querying on-chain asset() for ERC4626 vault...")
                    for deployment in deployments:
                        asset_from_chain = self._query_erc4626_asset(
                            deployment['address'],
                            deployment['chainId']
                        )
                        if asset_from_chain:
                            self.erc4626_context['asset_from_chain'] = asset_from_chain
                            logger.info(f"   ✓ Updated ERC4626 context with on-chain asset")
                            break

                if self.erc4626_context:
                    logger.info(f"\n{'='*60}")
                    logger.info(f"🏦 ERC4626 VAULT CONTEXT ACTIVE")
                    logger.info(f"   Detection: {self.erc4626_context.get('detection_source', 'unknown')}")
                    if self.erc4626_context.get('underlying_token'):
                        logger.info(f"   Underlying token (metadata): {self.erc4626_context['underlying_token']}")
                    if self.erc4626_context.get('asset_from_chain'):
                        logger.info(f"   Asset token (on-chain): {self.erc4626_context['asset_from_chain']}")
                    logger.info(f"   AI will be informed about ERC4626 vault semantics")
                    logger.info(f"{'='*60}\n")
            else:
                logger.warning("Could not extract source code from any deployment, continuing without it")


