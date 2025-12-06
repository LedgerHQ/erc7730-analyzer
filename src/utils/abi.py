"""
ABI handling for ERC-7730 analyzer.

This module provides ABI parsing and function selector utilities.
"""

import json
import requests
from typing import Dict, List, Optional
from eth_utils import keccak


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

    @staticmethod
    def _function_signature_to_selector(signature: str) -> str:
        """
        Convert a function signature to a function selector.

        Args:
            signature: Function signature (e.g., "transfer(address,uint256)")

        Returns:
            Function selector as hex string (e.g., "0xa9059cbb")
        """
        return "0x" + keccak(text=signature).hex()[:8]

    def _param_abi_type_to_str(self, param) -> str:
        """
        Recursively convert ABI input types into signature strings.

        Args:
            param: Parameter definition from ABI

        Returns:
            Type string for signature (e.g., "address", "(uint256,address)")
        """
        if param["type"] == "tuple":
            inner = ",".join(
                self._param_abi_type_to_str(p) for p in param["components"]
            )
            return f"({inner})" + ("[]" if param.get("type").endswith("[]") else "")
        elif param["type"].startswith("tuple["):
            inner = ",".join(
                self._param_abi_type_to_str(p) for p in param["components"]
            )
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
        for item in self.abi:
            if item.get("type") != "function":
                continue

            name = item["name"]
            inputs = item.get("inputs", [])
            native_types = ",".join(self._param_abi_type_to_str(p) for p in inputs)
            signature = f"{name}({native_types})"

            computed_selector = self._function_signature_to_selector(signature)
            if computed_selector == selector.lower():
                return {
                    "name": name,
                    "param_names": [item.get("name") for item in inputs],
                    "param_internal_types": [
                        item.get("internalType") for item in inputs
                    ],
                    "signature": signature,
                    "selector": computed_selector,
                    "stateMutability": item.get("stateMutability", "nonpayable"),
                }
        return {}


def detect_diamond_proxy(
    contract_address: str,
    chain_id: int,
    etherscan_api_key: str
) -> Optional[List[str]]:
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
        facets_selector = '0x7a0ed627'

        params = {
            'module': 'proxy',
            'action': 'eth_call',
            'to': contract_address,
            'data': facets_selector,
            'tag': 'latest',
            'apikey': etherscan_api_key
        }

        base_url = f"https://api.etherscan.io/v2/api?chainid={chain_id}"
        response = requests.get(base_url, params=params, timeout=10)
        data = response.json()

        # Check if the call succeeded
        if 'error' in data or not data.get('result') or data['result'] == '0x':
            logger.debug(f"Not a Diamond proxy (facets() call failed or empty)")
            return None

        result = data['result']
        logger.info(f"✓ facets() call succeeded - this is a Diamond proxy (response: {len(result)} chars)")

        # Parse the ABI-encoded Facet[] array
        hex_data = result[2:] if result.startswith('0x') else result

        if len(hex_data) < 64:
            logger.warning(f"facets() response too short to parse")
            return None

        # Parse array offset and length
        array_offset = int(hex_data[:64], 16)
        array_start = array_offset * 2

        if len(hex_data) < array_start + 64:
            logger.warning(f"facets() response too short after offset")
            return None

        array_length = int(hex_data[array_start:array_start + 64], 16)
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

            facet_data_offset = int(hex_data[facet_offset_pos:facet_offset_pos + 64], 16)
            facet_data_pos = array_start + 64 + (facet_data_offset * 2)

            if len(hex_data) < facet_data_pos + 64:
                break

            # Extract facet address (last 40 hex chars of 32-byte word)
            facet_address = '0x' + hex_data[facet_data_pos + 24:facet_data_pos + 64]

            if facet_address != '0x' + '0' * 40:
                facet_addresses.append(facet_address.lower())

        # Remove duplicates
        facet_addresses = list(set(facet_addresses))
        logger.info(f"✓ Found {len(facet_addresses)} unique facet addresses")

        return facet_addresses if facet_addresses else None

    except Exception as e:
        logger.debug(f"Diamond proxy detection failed: {e}")
        return None


def detect_proxy_implementation(
    contract_address: str,
    chain_id: int,
    etherscan_api_key: str
) -> Optional[str]:
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
        impl_slot = '0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc'

        params = {
            'module': 'proxy',
            'action': 'eth_getStorageAt',
            'address': contract_address,
            'position': impl_slot,
            'tag': 'latest',
            'apikey': etherscan_api_key
        }

        base_url = f"https://api.etherscan.io/v2/api?chainid={chain_id}"
        response = requests.get(base_url, params=params, timeout=10)
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
            'apikey': etherscan_api_key
        }

        response = requests.get(base_url, params=params, timeout=10)
        data = response.json()

        if data.get('result') and len(data['result']) > 0:
            result = data['result'][0]
            impl = result.get('Implementation')
            # Validate it's actually an address (0x followed by 40 hex chars)
            if impl and isinstance(impl, str) and impl.startswith('0x') and len(impl) == 42:
                try:
                    # Verify it's valid hex
                    int(impl, 16)
                    logger.info(f"Detected simple proxy via Etherscan API, implementation: {impl}")
                    return impl
                except ValueError:
                    logger.debug(f"Invalid implementation address format: {impl}")

    except Exception as e:
        logger.debug(f"Simple proxy detection failed: {e}")

    return None


def fetch_contract_abi(
    contract_address: str,
    chain_id: int,
    etherscan_api_key: str
) -> Optional[List[Dict]]:
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
        Contract ABI as a list of dictionaries, or None if fetch fails
    """
    import logging
    from .abi_merger import ABIMerger
    logger = logging.getLogger(__name__)

    # First, check if this is a Diamond proxy
    facet_addresses = detect_diamond_proxy(contract_address, chain_id, etherscan_api_key)

    if facet_addresses:
        # Diamond proxy: fetch and merge ABIs from all facets
        logger.info(f"Diamond proxy detected with {len(facet_addresses)} facets")
        logger.info(f"Fetching ABIs from all facets and merging...")

        merger = ABIMerger()
        successful_fetches = 0
        failed_fetches = 0

        for i, facet_address in enumerate(facet_addresses, 1):
            logger.info(f"  [{i}/{len(facet_addresses)}] Fetching ABI for facet {facet_address}...")

            params = {
                'module': 'contract',
                'action': 'getabi',
                'address': facet_address,
                'apikey': etherscan_api_key
            }

            try:
                base_url = f"https://api.etherscan.io/v2/api?chainid={chain_id}"
                response = requests.get(base_url, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()

                if data['status'] == '1':
                    facet_abi = json.loads(data['result'])
                    stats = merger.add_abi(facet_abi, i)
                    logger.info(f"    ✓ Added {stats['new_functions']} functions, {stats['new_events']} events "
                              f"({stats['duplicate_functions']} duplicates skipped)")
                    successful_fetches += 1
                else:
                    logger.warning(f"    ✗ Failed to fetch ABI for facet {facet_address}")
                    failed_fetches += 1

            except Exception as e:
                logger.warning(f"    ✗ Exception fetching facet ABI: {e}")
                failed_fetches += 1

        if successful_fetches == 0:
            logger.error(f"Failed to fetch ABI from any facet")
            return None

        merged_abi = merger.get_merged_abi()
        stats = merger.get_statistics()

        logger.info("=" * 60)
        logger.info("Diamond Proxy ABI Merge Summary:")
        logger.info(f"  Facets queried: {len(facet_addresses)}")
        logger.info(f"  Successful fetches: {successful_fetches}")
        logger.info(f"  Failed fetches: {failed_fetches}")
        logger.info(f"  Total unique functions: {stats['total_functions']}")
        logger.info(f"  Total unique events: {stats['total_events']}")
        logger.info("=" * 60)

        return merged_abi

    # Not a Diamond proxy - check for simple proxy
    impl_address = detect_proxy_implementation(contract_address, chain_id, etherscan_api_key)

    if impl_address:
        logger.info(f"Detected simple proxy, fetching ABI for implementation: {impl_address}")
        address_to_fetch = impl_address
    else:
        address_to_fetch = contract_address

    params = {
        'module': 'contract',
        'action': 'getabi',
        'address': address_to_fetch,
        'apikey': etherscan_api_key
    }

    try:
        base_url = f"https://api.etherscan.io/v2/api?chainid={chain_id}"
        response = requests.get(base_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data['status'] == '1':
            abi = json.loads(data['result'])
            logger.info(f"Fetched ABI with {len(abi)} entries from {address_to_fetch}")
            return abi
        else:
            logger.warning(f"Failed to fetch ABI: {data.get('message', 'Unknown error')}")
            return None
    except Exception as e:
        logger.error(f"Exception fetching ABI: {e}")
        return None
