"""
ABI handling for ERC-7730 analyzer.

This module provides ABI parsing and function selector utilities.
"""

import json
from typing import Any

import requests
from eth_utils.abi import (
    abi_to_signature,
    function_abi_to_4byte_selector,
    function_signature_to_4byte_selector,
)

from ..extraction.source_code.shared import BLOCKSCOUT_URLS
from ..rpc_helpers import (
    etherscan_response_indicates_chain_unsupported,
    is_etherscan_contract_endpoint_unsupported,
    is_etherscan_proxy_eth_call_unsupported,
    mark_etherscan_contract_endpoint_unsupported,
    mark_etherscan_proxy_eth_call_unsupported,
    rpc_eth_call,
)


class ABI:
    """
    Class to interact with contract ABI.
    Handles function selector calculation and ABI lookups.
    """

    def __init__(self, abi: list):
        """
        Initialize with an ABI.

        Args:
            abi: Contract ABI as a list of dictionaries
        """
        self.abi = abi
        self._functions_by_selector: dict[str, dict[str, Any]] = {}
        self._functions_by_signature_key: dict[str, dict[str, Any]] = {}
        self._build_function_indexes()

    @staticmethod
    def _function_signature_to_selector(signature: str) -> str:
        """
        Convert a function signature to a function selector.

        Args:
            signature: Function signature (e.g., "transfer(address,uint256)")

        Returns:
            Function selector as hex string (e.g., "0xa9059cbb")
        """
        return "0x" + function_signature_to_4byte_selector(signature).hex()

    @staticmethod
    def _normalize_signature_lookup(signature: str) -> str:
        return "".join(str(signature or "").split())

    @classmethod
    def _format_param_for_display_signature(
        cls,
        param: dict[str, Any],
        *,
        include_names: bool,
        tuple_keyword: bool,
    ) -> str:
        param_type = param.get("type", "")
        param_name = str(param.get("name") or "").strip()

        if param_type.startswith("tuple"):
            components = param.get("components") or []
            inner = ", ".join(
                cls._format_param_for_display_signature(
                    component,
                    include_names=include_names,
                    tuple_keyword=tuple_keyword,
                )
                for component in components
            )
            tuple_suffix = param_type[len("tuple") :]
            tuple_prefix = "tuple" if tuple_keyword else ""
            rendered_type = f"{tuple_prefix}({inner}){tuple_suffix}"
        else:
            rendered_type = param_type

        if include_names and param_name:
            return f"{rendered_type} {param_name}"
        return rendered_type

    @classmethod
    def _function_abi_to_display_signature(
        cls,
        function_abi: dict[str, Any],
        *,
        include_names: bool,
        tuple_keyword: bool,
    ) -> str | None:
        if function_abi.get("type") != "function":
            return None

        function_name = function_abi.get("name")
        if not function_name:
            return None

        inputs = function_abi.get("inputs", [])
        rendered_inputs = ", ".join(
            cls._format_param_for_display_signature(
                input_param,
                include_names=include_names,
                tuple_keyword=tuple_keyword,
            )
            for input_param in inputs
        )
        return f"{function_name}({rendered_inputs})"

    def _build_function_indexes(self) -> None:
        self._functions_by_selector = {}
        self._functions_by_signature_key = {}

        for item in self.abi:
            if item.get("type") != "function":
                continue

            try:
                canonical_signature = abi_to_signature(item)
                selector = "0x" + function_abi_to_4byte_selector(item).hex()
            except Exception:
                continue

            inputs = item.get("inputs", [])
            display_signature = self._function_abi_to_display_signature(
                item,
                include_names=True,
                tuple_keyword=False,
            )
            tuple_keyword_display_signature = self._function_abi_to_display_signature(
                item,
                include_names=True,
                tuple_keyword=True,
            )
            signature_without_names = self._function_abi_to_display_signature(
                item,
                include_names=False,
                tuple_keyword=False,
            )
            tuple_signature_without_names = self._function_abi_to_display_signature(
                item,
                include_names=False,
                tuple_keyword=True,
            )
            metadata = {
                "name": item["name"],
                "param_names": [param.get("name") for param in inputs],
                "param_internal_types": [param.get("internalType") for param in inputs],
                "signature": canonical_signature,
                "display_signature": display_signature,
                "tuple_keyword_display_signature": tuple_keyword_display_signature,
                "selector": selector,
                "stateMutability": item.get("stateMutability", "nonpayable"),
            }
            self._functions_by_selector[selector.lower()] = metadata

            aliases = {
                canonical_signature,
                display_signature,
                tuple_keyword_display_signature,
                signature_without_names,
                tuple_signature_without_names,
            }
            for alias in aliases:
                if not alias:
                    continue
                self._functions_by_signature_key[self._normalize_signature_lookup(alias)] = metadata

    def _param_abi_type_to_str(self, param) -> str:
        """
        Recursively convert ABI input types into signature strings.

        Args:
            param: Parameter definition from ABI

        Returns:
            Type string for signature (e.g., "address", "(uint256,address)")
        """
        if param["type"] == "tuple":
            inner = ",".join(self._param_abi_type_to_str(p) for p in param["components"])
            return f"({inner})" + ("[]" if param.get("type").endswith("[]") else "")
        elif param["type"].startswith("tuple["):
            inner = ",".join(self._param_abi_type_to_str(p) for p in param["components"])
            return f"({inner})" + param["type"][5:]
        else:
            return param["type"]

    def find_function_by_selector(self, selector: str) -> dict:
        """
        Find function by selector in ABI.

        The selector is the first 4 bytes of the keccak256 hash of the function signature,
        e.g., keccak256("transfer(address,uint256)") = '0xa9059cbb'.

        Args:
            selector: Function selector as hex string

        Returns:
            Dictionary with function metadata:
            - name: Function name
            - param_names: List of parameter names
            - param_internal_types: List of parameter internal types
            - signature: Full function signature
            - selector: Function selector
            - stateMutability: Function state mutability (payable, nonpayable, view, pure)
        """
        return self._functions_by_selector.get(selector.lower(), {})

    def find_function_by_signature(self, signature: str) -> dict:
        """
        Find a function using any ABI-derived signature alias.

        Supports:
        - canonical compiler-style signatures, e.g. "transfer(address,uint256)"
        - v2 human-readable signatures with parameter names using bare tuple syntax
        - compatibility aliases that still use explicit `tuple(...)`
        """
        if not signature:
            return {}

        if signature.startswith("0x") and len(signature) == 10:
            return self.find_function_by_selector(signature)

        normalized_signature = self._normalize_signature_lookup(signature)
        return self._functions_by_signature_key.get(normalized_signature, {})


def detect_diamond_proxy(contract_address: str, chain_id: int, etherscan_api_key: str) -> list[str] | None:
    """
    Detect if contract is a Diamond proxy (EIP-2535) and return all facet addresses.

    Uses the DiamondLoupe interface facets() function to get all facet addresses.

    Args:
        contract_address: Contract address
        chain_id: Chain ID
        etherscan_api_key: Etherscan API key

    Returns:
        List of facet addresses if Diamond proxy, None otherwise
    """
    import logging

    logger = logging.getLogger(__name__)

    try:
        # Call facets() function from DiamondLoupe interface
        # Selector: 0x7a0ed627
        facets_selector = "0x7a0ed627"

        base_url = f"https://api.etherscan.io/v2/api?chainid={chain_id}"

        params = {
            "module": "proxy",
            "action": "eth_call",
            "to": contract_address,
            "data": facets_selector,
            "tag": "latest",
            "apikey": etherscan_api_key,
        }

        result = None
        if is_etherscan_proxy_eth_call_unsupported(chain_id):
            logger.info(
                "Skipping explorer facets() call on chain %s: proxy eth_call already marked unsupported for this run",
                chain_id,
            )
        else:
            try:
                response = requests.get(base_url, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()

                if "error" in data or data.get("status") == "0" or data.get("message") == "NOTOK":
                    error_msg = data.get("result") or data.get("message") or "API error"
                    logger.warning(f"facets() explorer call failed on chain {chain_id}: {error_msg}")
                    if etherscan_response_indicates_chain_unsupported(data):
                        mark_etherscan_proxy_eth_call_unsupported(chain_id)
                else:
                    result = data.get("result")
            except Exception as exc:
                logger.warning(f"facets() explorer call raised on chain {chain_id}: {exc}")

        if result is None:
            logger.info("Trying direct RPC fallback for facets() on chain %s...", chain_id)
            rpc_result, rpc_error, rpc_url = rpc_eth_call(chain_id, contract_address, facets_selector, timeout=10)
            if rpc_error:
                logger.warning("facets() RPC fallback (%s): %s", rpc_url or "no rpc url", rpc_error)
                logger.debug(
                    "Not a Diamond proxy (facets() failed via explorer and RPC%s)",
                    f" {rpc_url}" if rpc_url else "",
                )
                return None
            result = rpc_result
            logger.info("facets() RPC fallback via %s succeeded", rpc_url)

        if not result or result == "0x":
            logger.debug("Not a Diamond proxy (empty result)")
            return None
        logger.info(f"✓ facets() call succeeded - this is a Diamond proxy (response: {len(result)} chars)")

        # Parse the ABI-encoded Facet[] array
        hex_data = result[2:] if result.startswith("0x") else result

        if len(hex_data) < 64:
            logger.warning("facets() response too short to parse")
            return None

        # Parse array offset and length
        array_offset = int(hex_data[:64], 16)
        array_start = array_offset * 2

        if len(hex_data) < array_start + 64:
            logger.warning("facets() response too short after offset")
            return None

        array_length = int(hex_data[array_start : array_start + 64], 16)
        logger.info(f"Diamond proxy has {array_length} facets")

        if array_length == 0:
            return None

        # Parse each facet struct to extract facet addresses
        facet_addresses = []
        data_start = array_start + 64

        for i in range(array_length):
            # Each facet is: (address facetAddress, bytes4[] functionSelectors)
            # First 32 bytes: offset to facet struct
            # Next 32 bytes: facet address (padded)
            facet_offset_pos = data_start + (i * 64)
            if len(hex_data) < facet_offset_pos + 64:
                break

            facet_data_offset = int(hex_data[facet_offset_pos : facet_offset_pos + 64], 16)
            facet_data_pos = array_start + 64 + (facet_data_offset * 2)

            if len(hex_data) < facet_data_pos + 64:
                break

            # Extract facet address (last 40 hex chars of 32-byte word)
            facet_address = "0x" + hex_data[facet_data_pos + 24 : facet_data_pos + 64]

            if facet_address != "0x" + "0" * 40:
                facet_addresses.append(facet_address.lower())

        # Remove duplicates
        facet_addresses = list(set(facet_addresses))
        logger.info(f"✓ Found {len(facet_addresses)} unique facet addresses")

        return facet_addresses if facet_addresses else None

    except Exception as e:
        logger.debug(f"Diamond proxy detection failed: {e}")
        return None


def detect_proxy_implementation(contract_address: str, chain_id: int, etherscan_api_key: str) -> str | None:
    """
    Detect if contract is a simple proxy and return implementation address.

    Checks common proxy patterns:
    - EIP-1967 implementation slot
    - Etherscan's built-in proxy detection

    NOTE: Does NOT handle Diamond proxies (EIP-2535) - use detect_diamond_proxy() for those.

    Args:
        contract_address: Contract address
        chain_id: Chain ID
        etherscan_api_key: Etherscan API key

    Returns:
        Implementation address or None
    """
    import logging

    logger = logging.getLogger(__name__)

    try:
        # EIP-1967 implementation slot
        # keccak256("eip1967.proxy.implementation") - 1
        impl_slot = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"

        base_url = f"https://api.etherscan.io/v2/api?chainid={chain_id}"
        if not is_etherscan_proxy_eth_call_unsupported(chain_id):
            params = {
                "module": "proxy",
                "action": "eth_getStorageAt",
                "address": contract_address,
                "position": impl_slot,
                "tag": "latest",
                "apikey": etherscan_api_key,
            }

            response = requests.get(base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Check for API errors first
            if "error" in data or data.get("status") == "0" or data.get("message") == "NOTOK":
                logger.debug("API error when checking EIP-1967 implementation slot")
                # Continue to next detection method
            elif data.get("result") and data["result"] != "0x" + "0" * 64:
                # Ensure result is valid hex before extracting address
                result = data["result"]
                if result.startswith("0x") and len(result) == 66:  # 0x + 64 hex chars
                    # Extract address from storage slot (last 20 bytes)
                    impl_address = "0x" + result[-40:]
                    if impl_address != "0x" + "0" * 40:
                        logger.info(f"Detected EIP-1967 proxy, implementation: {impl_address}")
                        return impl_address

        # Try Etherscan's built-in proxy detection
        if not is_etherscan_contract_endpoint_unsupported(chain_id):
            params = {
                "module": "contract",
                "action": "getsourcecode",
                "address": contract_address,
                "apikey": etherscan_api_key,
            }

            response = requests.get(base_url, params=params, timeout=10)
            data = response.json()

            if etherscan_response_indicates_chain_unsupported(data):
                mark_etherscan_contract_endpoint_unsupported(chain_id)
            elif data.get("result") and len(data["result"]) > 0:
                result = data["result"][0]
                impl = result.get("Implementation")
                # Validate it's actually an address (0x followed by 40 hex chars)
                if impl and isinstance(impl, str) and impl.startswith("0x") and len(impl) == 42:
                    try:
                        # Verify it's valid hex
                        int(impl, 16)
                        logger.info(f"Detected simple proxy via Etherscan API, implementation: {impl}")
                        return impl
                    except ValueError:
                        logger.debug(f"Invalid implementation address format: {impl}")

        if chain_id in BLOCKSCOUT_URLS and chain_id != 1116:
            try:
                url = f"{BLOCKSCOUT_URLS[chain_id]}/api/v2/smart-contracts/{contract_address}"
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                data = response.json()
                implementations = data.get("implementations") or []
                if implementations:
                    impl = implementations[0].get("address") or implementations[0].get("address_hash")
                    if impl and isinstance(impl, str) and impl.startswith("0x") and len(impl) == 42:
                        try:
                            int(impl, 16)
                            logger.info(f"Detected proxy via Blockscout smart-contracts API, implementation: {impl}")
                            return impl
                        except ValueError:
                            logger.debug(f"Invalid Blockscout implementation address format: {impl}")
            except Exception as exc:
                logger.debug(f"Blockscout proxy detection failed: {exc}")

    except Exception as e:
        logger.debug(f"Simple proxy detection failed: {e}")

    return None


def fetch_single_contract_abi(
    contract_address: str,
    chain_id: int,
    etherscan_api_key: str,
) -> list[dict[str, Any]] | None:
    """Fetch one address ABI via Etherscan, with Blockscout fallback on unsupported chains."""
    import logging

    logger = logging.getLogger(__name__)

    if is_etherscan_contract_endpoint_unsupported(chain_id):
        return fetch_contract_abi_from_blockscout(contract_address, chain_id)

    params = {"module": "contract", "action": "getabi", "address": contract_address, "apikey": etherscan_api_key}
    base_url = f"https://api.etherscan.io/v2/api?chainid={chain_id}"
    try:
        response = requests.get(base_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logger.error(f"Exception fetching ABI: {exc}")
        return None

    if etherscan_response_indicates_chain_unsupported(data):
        mark_etherscan_contract_endpoint_unsupported(chain_id)
        return fetch_contract_abi_from_blockscout(contract_address, chain_id)

    if data.get("status") == "1":
        try:
            abi = json.loads(data["result"])
        except Exception as exc:
            logger.warning("Failed to parse ABI JSON for %s on chain %s: %s", contract_address, chain_id, exc)
            return None
        logger.info(f"Fetched ABI with {len(abi)} entries from {contract_address}")
        return abi

    logger.warning(f"Failed to fetch ABI: {data.get('message', 'Unknown error')}")
    return None


def fetch_contract_abi_from_blockscout(contract_address: str, chain_id: int) -> list[dict[str, Any]] | None:
    """Fetch one address ABI from Blockscout's smart-contracts API when available."""
    import logging

    logger = logging.getLogger(__name__)

    if chain_id not in BLOCKSCOUT_URLS or chain_id == 1116:
        return None

    url = f"{BLOCKSCOUT_URLS[chain_id]}/api/v2/smart-contracts/{contract_address}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logger.debug("Blockscout ABI fetch failed for %s on chain %s: %s", contract_address, chain_id, exc)
        return None

    abi = data.get("abi")
    if isinstance(abi, list) and abi:
        logger.info("Fetched ABI with %s entries from Blockscout for %s", len(abi), contract_address)
        return abi
    if isinstance(abi, str) and abi.strip():
        try:
            parsed = json.loads(abi)
        except Exception as exc:
            logger.warning(
                "Failed to parse Blockscout ABI JSON for %s on chain %s: %s", contract_address, chain_id, exc
            )
            return None
        if isinstance(parsed, list) and parsed:
            logger.info("Fetched ABI with %s entries from Blockscout for %s", len(parsed), contract_address)
            return parsed

    logger.debug("Blockscout ABI unavailable for %s on chain %s", contract_address, chain_id)
    return None


def fetch_contract_abi(
    contract_address: str, chain_id: int, etherscan_api_key: str
) -> tuple[list[dict] | None, dict, bool]:
    """
    Fetch contract ABI from Etherscan with proxy detection.

    Handles three cases:
    1. Diamond proxies (EIP-2535): Fetches ABI from all facets and merges them
    2. Simple proxies (EIP-1967): Fetches ABI from implementation
    3. Regular contracts: Fetches ABI directly

    Args:
        contract_address: Ethereum contract address
        chain_id: Chain ID for the contract
        etherscan_api_key: Etherscan API key

    Returns:
        Tuple of:
        - abi: Contract ABI as a list of dictionaries, or None if fetch fails
        - selector_sources: Dict mapping selector -> list of {facet_address, chain_id, signature}
        - is_diamond: True if Diamond proxy detected
    """
    import logging

    from .merger import ABIMerger

    logger = logging.getLogger(__name__)

    # First, check if this is a Diamond proxy
    facet_addresses = detect_diamond_proxy(contract_address, chain_id, etherscan_api_key)

    if facet_addresses:
        # Diamond proxy: fetch and merge ABIs from all facets
        logger.info(f"Diamond proxy detected with {len(facet_addresses)} facets")
        logger.info("Fetching ABIs from all facets and merging...")

        merger = ABIMerger()
        successful_fetches = 0
        failed_fetches = 0

        for i, facet_address in enumerate(facet_addresses, 1):
            logger.info(f"  [{i}/{len(facet_addresses)}] Fetching ABI for facet {facet_address}...")
            try:
                facet_abi = fetch_single_contract_abi(facet_address, chain_id, etherscan_api_key)
                if facet_abi:
                    # Pass facet_address to track selector -> facet mapping
                    stats = merger.add_abi(facet_abi, chain_id, source_address=facet_address, source_kind="facet")
                    logger.debug(
                        f"    ✓ Added {stats['new_functions']} functions, {stats['new_events']} events "
                        f"({stats['duplicate_functions']} duplicates skipped)"
                    )
                    successful_fetches += 1
                else:
                    logger.warning(f"    ✗ Failed to fetch ABI for facet {facet_address}")
                    failed_fetches += 1
            except Exception as e:
                logger.warning(f"    ✗ Exception fetching facet ABI: {e}")
                failed_fetches += 1

        if successful_fetches == 0:
            logger.error("Failed to fetch ABI from any facet")
            return None, {}, False

        merged_abi = merger.get_merged_abi()
        selector_sources = merger.get_selector_sources()
        stats = merger.get_statistics()

        logger.info("=" * 60)
        logger.info("Diamond Proxy ABI Merge Summary:")
        logger.info(f"  Facets queried: {len(facet_addresses)}")
        logger.info(f"  Successful fetches: {successful_fetches}")
        logger.info(f"  Failed fetches: {failed_fetches}")
        logger.info(f"  Total unique functions: {stats['total_functions']}")
        logger.info(f"  Total unique events: {stats['total_events']}")
        logger.info(f"  Selector provenance entries: {len(selector_sources)}")
        logger.info("=" * 60)

        # Return tuple: (abi, selector_sources, is_diamond)
        return merged_abi, selector_sources, True

    # Not a Diamond proxy - check for simple proxy
    impl_address = detect_proxy_implementation(contract_address, chain_id, etherscan_api_key)

    if impl_address:
        logger.info(f"Detected simple proxy, fetching ABI for implementation: {impl_address}")
        address_to_fetch = impl_address
    else:
        address_to_fetch = contract_address

    try:
        abi = fetch_single_contract_abi(address_to_fetch, chain_id, etherscan_api_key)
        if abi:
            # Return tuple: (abi, selector_sources, is_diamond)
            return abi, {}, False
    except Exception as e:
        logger.error(f"Exception fetching ABI: {e}")
    return None, {}, False
