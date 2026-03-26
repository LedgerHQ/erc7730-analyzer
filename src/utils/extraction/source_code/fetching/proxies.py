"""Proxy and diamond detection helpers."""

import requests
from web3 import Web3

from ....rpc_helpers import (
    etherscan_response_indicates_chain_unsupported,
    is_etherscan_contract_endpoint_unsupported,
    is_etherscan_proxy_eth_call_unsupported,
    mark_etherscan_contract_endpoint_unsupported,
    mark_etherscan_proxy_eth_call_unsupported,
)
from ..shared import BLOCKSCOUT_URLS, logger, resolve_rpc_url, rpc_eth_call


class SourceCodeFetchingProxyMixin:
    def detect_proxy_implementation(self, contract_address: str, chain_id: int) -> str | None:
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
        logger.info(f"Checking if {contract_address} is a proxy contract...")
        try:
            # EIP-1967 implementation slot
            # keccak256("eip1967.proxy.implementation") - 1
            impl_slot = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"

            # Try RPC FIRST (most reliable) if we have an RPC URL
            rpc_url = resolve_rpc_url(chain_id)
            if rpc_url:
                logger.info("  Trying direct RPC call to read storage slot...")
                try:
                    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 10}))
                    if w3.is_connected():
                        # Read the EIP-1967 implementation storage slot
                        storage_value = w3.eth.get_storage_at(
                            Web3.to_checksum_address(contract_address), int(impl_slot, 16)
                        )

                        # Convert bytes to hex string
                        storage_hex = storage_value.hex() if isinstance(storage_value, bytes) else hex(storage_value)
                        if not storage_hex.startswith("0x"):
                            storage_hex = "0x" + storage_hex

                        logger.debug(f"  RPC storage slot result: {storage_hex}")

                        # Check if non-zero
                        if storage_hex != "0x" + "0" * 64 and int(storage_hex, 16) != 0:
                            # Extract address from storage slot (last 20 bytes)
                            impl_address = "0x" + storage_hex[-40:]
                            if impl_address != "0x" + "0" * 40:
                                logger.info(f"Detected EIP-1967 proxy via RPC, implementation: {impl_address}")
                                return impl_address
                            else:
                                logger.debug("  RPC storage slot is empty (all zeros)")
                        else:
                            logger.debug("  RPC storage slot is empty or all zeros")
                    else:
                        logger.warning("  Could not connect to RPC endpoint")
                except Exception as e:
                    logger.warning(f"  Error reading storage via RPC: {e}")

            # Try Etherscan and Blockscout APIs as fallback
            for use_blockscout in [False, True]:
                if use_blockscout and chain_id not in BLOCKSCOUT_URLS:
                    logger.debug(f"Chain {chain_id} not in Blockscout URLs, skipping")
                    continue

                # Skip Blockscout API for Core DAO (chain 1116) - uses different API structure
                if use_blockscout and chain_id == 1116:
                    logger.info("  Skipping Blockscout API for Core DAO (chain 1116) - incompatible API structure")
                    continue

                api_name = "Blockscout" if use_blockscout else "Etherscan"
                logger.info(f"  Trying {api_name} for EIP-1967 storage slot...")

                if use_blockscout:
                    # Use Blockscout API
                    base_url = BLOCKSCOUT_URLS[chain_id]
                    params = {
                        "module": "proxy",
                        "action": "eth_getStorageAt",
                        "address": contract_address,
                        "position": impl_slot,
                        "tag": "latest",
                    }
                else:
                    # Use Etherscan API
                    base_url = f"https://api.etherscan.io/v2/api?chainid={chain_id}"
                    params = {
                        "module": "proxy",
                        "action": "eth_getStorageAt",
                        "address": contract_address,
                        "position": impl_slot,
                        "tag": "latest",
                        "apikey": self.etherscan_api_key,
                    }

                try:
                    response = requests.get(base_url, params=params, timeout=10)
                    response.raise_for_status()
                    data = response.json()

                    # Check for API errors first
                    if "error" in data or data.get("status") == "0" or data.get("message") == "NOTOK":
                        logger.warning(f"  {api_name} API error: {data.get('message', 'unknown error')}")
                        # Continue to next detection method
                        continue
                    elif data.get("result") and data["result"] != "0x" + "0" * 64:
                        # Ensure result is valid hex before extracting address
                        result = data["result"]
                        logger.debug(f"  {api_name} storage slot result: {result}")
                        if result.startswith("0x") and len(result) == 66:  # 0x + 64 hex chars
                            # Extract address from storage slot (last 20 bytes)
                            impl_address = "0x" + result[-40:]
                            if impl_address != "0x" + "0" * 40:
                                logger.info(f"Detected EIP-1967 proxy, implementation: {impl_address}")
                                return impl_address
                            else:
                                logger.debug(f"  {api_name} storage slot is empty (all zeros)")
                        else:
                            logger.debug(f"  {api_name} storage slot has invalid format (length: {len(result)})")
                    else:
                        logger.debug(f"  {api_name} storage slot is empty or all zeros")
                except Exception as e:
                    logger.warning(f"  Error checking proxy via {api_name}: {e}")
                    continue

            # Try Etherscan's built-in proxy detection
            try:
                if not is_etherscan_contract_endpoint_unsupported(chain_id):
                    base_url_etherscan = f"https://api.etherscan.io/v2/api?chainid={chain_id}"
                    params = {
                        "module": "contract",
                        "action": "getsourcecode",
                        "address": contract_address,
                        "apikey": self.etherscan_api_key,
                    }

                    response = requests.get(base_url_etherscan, params=params, timeout=10)
                    data = response.json()

                    if etherscan_response_indicates_chain_unsupported(data):
                        mark_etherscan_contract_endpoint_unsupported(chain_id)
                    elif data.get("result") and len(data["result"]) > 0:
                        result = data["result"][0]
                        impl = result.get("Implementation")
                        if impl:
                            logger.info(f"Detected proxy via Etherscan, implementation: {impl}")
                            return impl
            except Exception as e:
                logger.debug(f"Etherscan proxy detection failed: {e}")

            # Try Blockscout's smart-contracts API for proxy info (skip for Core DAO)
            if chain_id in BLOCKSCOUT_URLS and chain_id != 1116:
                logger.info("  Trying Blockscout smart-contracts API...")
                try:
                    base_url_blockscout = BLOCKSCOUT_URLS[chain_id]
                    url = f"{base_url_blockscout}/api/v2/smart-contracts/{contract_address}"
                    response = requests.get(url, timeout=10)
                    response.raise_for_status()
                    data = response.json()

                    # Check for proxy information in Blockscout response
                    if data and isinstance(data, dict):
                        # Blockscout might have 'implementations' or 'proxy_type' fields
                        implementations = data.get("implementations") or []
                        logger.info(f"  Blockscout returned {len(implementations)} implementation(s)")
                        if implementations and len(implementations) > 0:
                            impl = implementations[0].get("address") or implementations[0].get("address_hash")
                            if impl:
                                logger.info(
                                    f"Detected proxy via Blockscout smart-contracts API, implementation: {impl}"
                                )
                                return impl
                except Exception as e:
                    logger.warning(f"  Blockscout smart-contracts API failed: {e}")

            logger.info(f"No proxy implementation detected for {contract_address}")
            return None

        except Exception as e:
            logger.warning(f"Proxy detection failed with exception: {e}")
            return None

    def _detect_diamond_via_sourcecode(self, contract_address: str, chain_id: int) -> dict[str, str]:
        """
        Fallback method: Detect Diamond proxy by checking if contract name contains 'Diamond'.

        This is a heuristic approach when eth_call to facetAddress fails.
        """
        try:
            if is_etherscan_contract_endpoint_unsupported(chain_id):
                contract_name = self.get_contract_name_from_blockscout(contract_address, chain_id) or ""
                if "diamond" in contract_name.lower():
                    logger.info("Contract name from Blockscout suggests Diamond proxy pattern")
                    return {"_is_diamond_but_unmapped": True}
                return {}

            params = {
                "module": "contract",
                "action": "getsourcecode",
                "address": contract_address,
                "apikey": self.etherscan_api_key,
            }

            base_url = f"https://api.etherscan.io/v2/api?chainid={chain_id}"
            response = requests.get(base_url, params=params)
            data = response.json()

            if etherscan_response_indicates_chain_unsupported(data):
                mark_etherscan_contract_endpoint_unsupported(chain_id)
                contract_name = self.get_contract_name_from_blockscout(contract_address, chain_id) or ""
                if "diamond" in contract_name.lower():
                    logger.info("Contract name from Blockscout suggests Diamond proxy pattern")
                    return {"_is_diamond_but_unmapped": True}
                return {}

            if data.get("result") and len(data["result"]) > 0:
                result = data["result"][0]
                contract_name = result.get("ContractName", "")

                logger.info(f"Contract name from Etherscan: {contract_name}")

                # Check if this looks like a Diamond proxy based on name
                if "diamond" in contract_name.lower():
                    logger.info("Contract name suggests Diamond proxy pattern")
                    # For Diamond proxies, we can't easily get facet mappings without eth_call
                    # Return empty dict to signal "is Diamond but can't map facets"
                    # The caller should handle this by not treating it as a simple proxy
                    return {"_is_diamond_but_unmapped": True}

            return {}

        except Exception as e:
            logger.debug(f"Diamond detection via source code failed: {e}")
            return {}

    def detect_diamond_proxy(self, contract_address: str, chain_id: int, selectors: list[str]) -> dict[str, str]:
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
            facets_selector = "0x7a0ed627"

            base_url = f"https://api.etherscan.io/v2/api?chainid={chain_id}"
            logger.info("Testing Diamond proxy using facets() function")
            logger.debug(f"Call data: {facets_selector}")

            def _log_call_payload(label: str, payload: object) -> None:
                payload_str = str(payload)
                if len(payload_str) > 100:
                    logger.debug(
                        f"{label} response: {payload_str[:100]}... (truncated, {len(payload_str)} chars total)"
                    )
                else:
                    logger.debug(f"{label} response: {payload_str}")

            def _explorer_eth_call(call_data: str, label: str) -> tuple[str | None, str | None]:
                if is_etherscan_proxy_eth_call_unsupported(chain_id):
                    return None, "explorer proxy eth_call already marked unsupported for this chain"
                params = {
                    "module": "proxy",
                    "action": "eth_call",
                    "to": contract_address,
                    "data": call_data,
                    "tag": "latest",
                    "apikey": self.etherscan_api_key,
                }
                try:
                    response = requests.get(base_url, params=params, timeout=10)
                    response.raise_for_status()
                    data = response.json()
                except Exception as exc:
                    return None, str(exc)

                _log_call_payload(label, data)

                if "error" in data or data.get("status") == "0" or data.get("message") == "NOTOK":
                    if etherscan_response_indicates_chain_unsupported(data):
                        mark_etherscan_proxy_eth_call_unsupported(chain_id)
                    if "error" in data:
                        error_msg = data.get("error", {}).get("message", "unknown error")
                    else:
                        error_msg = data.get("result", "API error")
                    return None, error_msg

                if "result" not in data:
                    return None, "missing result"

                return data.get("result"), None

            def _rpc_eth_call_logged(call_data: str, label: str) -> tuple[str | None, str | None]:
                result, error_msg, rpc_url = rpc_eth_call(chain_id, contract_address, call_data, timeout=10)
                if error_msg:
                    logger.warning(f"{label} RPC fallback ({rpc_url or 'no rpc url'}): {error_msg}")
                    return None, error_msg
                _log_call_payload(f"{label} RPC fallback via {rpc_url}", result)
                return result, None

            result, error_msg = _explorer_eth_call(facets_selector, "facets()")
            use_rpc_for_followups = False
            if error_msg:
                logger.warning(f"facets() call failed: {error_msg}")
                logger.info("Trying direct RPC fallback...")
                result, error_msg = _rpc_eth_call_logged(facets_selector, "facets()")
                if error_msg:
                    logger.info("Trying fallback detection method...")
                    return self._detect_diamond_via_sourcecode(contract_address, chain_id)
                use_rpc_for_followups = True

            if not result or result == "0x":
                logger.info("facets() returned empty result - not a Diamond proxy")
                return {}
            logger.info(f"✓ facets() succeeded! Response length: {len(result)} chars")

            # Parse the ABI-encoded Facet[] array to get the number of facets
            try:
                # Skip the first 0x and parse as hex
                hex_data = result[2:] if result.startswith("0x") else result

                # The structure is:
                # - offset to array (32 bytes)
                # - array length (32 bytes)
                # - then each Facet struct

                if len(hex_data) < 64:
                    logger.warning("facets() response too short to parse")
                    return self._detect_diamond_via_sourcecode(contract_address, chain_id)

                # Parse array offset and length
                array_offset = int(hex_data[0:64], 16)
                logger.debug(f"Array offset: {array_offset}")

                # The actual array data starts at array_offset * 2 (hex chars)
                array_start = array_offset * 2
                if len(hex_data) < array_start + 64:
                    logger.warning("facets() response too short after offset")
                    return self._detect_diamond_via_sourcecode(contract_address, chain_id)

                array_length = int(hex_data[array_start : array_start + 64], 16)
                logger.debug(f"Number of facets: {array_length}")

                if array_length == 0:
                    logger.debug("No facets found in response")
                    return {}

                # Now that we confirmed it's a Diamond, map each selector to its facet
                logger.info(f"✓ Confirmed Diamond proxy with {array_length} facets")
                logger.info(f"Now mapping {len(selectors)} selectors to their facets...")

                # Use facetAddress(bytes4) for each selector to get its facet
                facet_address_selector = "0xcdffacc6"

                for selector in selectors:
                    # Call facetAddress(selector)
                    call_data = facet_address_selector + selector[2:10].ljust(64, "0")

                    if use_rpc_for_followups:
                        facet_result, facet_error = _rpc_eth_call_logged(call_data, f"facetAddress({selector})")
                    else:
                        facet_result, facet_error = _explorer_eth_call(call_data, f"facetAddress({selector})")
                        if facet_error:
                            logger.info(f"  Falling back to direct RPC for selector {selector}...")
                            facet_result, facet_error = _rpc_eth_call_logged(call_data, f"facetAddress({selector})")

                    if facet_result and facet_result != "0x":
                        # Extract facet address from result (last 20 bytes / 40 hex chars)
                        facet_address = "0x" + facet_result[-40:].lower()
                        # Check it's not zero address
                        if facet_address != "0x" + "0" * 40:
                            selector_to_facet[selector] = facet_address
                            logger.debug(f"  Selector {selector} -> Facet {facet_address}")
                    else:
                        logger.warning(f"  Failed to get facet for selector {selector}: {facet_error or 'no result'}")

                if selector_to_facet:
                    unique_facets = len(set(selector_to_facet.values()))
                    logger.info(
                        f"✓ Successfully mapped {len(selector_to_facet)} selectors to {unique_facets} unique facet(s)"
                    )
                    return selector_to_facet
                else:
                    logger.warning("Could not map any selectors to facets")
                    return {"_is_diamond_but_unmapped": True}

            except Exception as parse_error:
                logger.warning(f"Error parsing facets() response: {parse_error}")
                logger.info("But facets() call succeeded, so this IS a Diamond proxy")
                return {"_is_diamond_but_unmapped": True}

        except Exception as e:
            logger.warning(f"Diamond proxy detection failed: {e}")
            return {}
