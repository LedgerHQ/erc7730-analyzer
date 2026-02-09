"""Proxy and diamond detection helpers."""

import json
from typing import Dict, List, Optional

import requests
from web3 import Web3

from ..shared import BLOCKSCOUT_URLS, RPC_URLS, logger


class SourceCodeFetchingProxyMixin:
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
        logger.info(f"Checking if {contract_address} is a proxy contract...")
        try:
            # EIP-1967 implementation slot
            # keccak256("eip1967.proxy.implementation") - 1
            impl_slot = '0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc'

            # Try RPC FIRST (most reliable) if we have an RPC URL
            if chain_id in RPC_URLS:
                logger.info(f"  Trying direct RPC call to read storage slot...")
                try:
                    w3 = Web3(Web3.HTTPProvider(RPC_URLS[chain_id], request_kwargs={'timeout': 10}))
                    if w3.is_connected():
                        # Read the EIP-1967 implementation storage slot
                        storage_value = w3.eth.get_storage_at(
                            Web3.to_checksum_address(contract_address),
                            int(impl_slot, 16)
                        )

                        # Convert bytes to hex string
                        storage_hex = storage_value.hex() if isinstance(storage_value, bytes) else hex(storage_value)
                        if not storage_hex.startswith('0x'):
                            storage_hex = '0x' + storage_hex

                        logger.info(f"  RPC storage slot result: {storage_hex}")

                        # Check if non-zero
                        if storage_hex != '0x' + '0' * 64 and int(storage_hex, 16) != 0:
                            # Extract address from storage slot (last 20 bytes)
                            impl_address = '0x' + storage_hex[-40:]
                            if impl_address != '0x' + '0' * 40:
                                logger.info(f"Detected EIP-1967 proxy via RPC, implementation: {impl_address}")
                                return impl_address
                            else:
                                logger.info(f"  RPC storage slot is empty (all zeros)")
                        else:
                            logger.info(f"  RPC storage slot is empty or all zeros")
                    else:
                        logger.info(f"  Could not connect to RPC endpoint")
                except Exception as e:
                    logger.info(f"  Error reading storage via RPC: {e}")

            # Try Etherscan and Blockscout APIs as fallback
            for use_blockscout in [False, True]:
                if use_blockscout and chain_id not in BLOCKSCOUT_URLS:
                    logger.debug(f"Chain {chain_id} not in Blockscout URLs, skipping")
                    continue

                # Skip Blockscout API for Core DAO (chain 1116) - uses different API structure
                if use_blockscout and chain_id == 1116:
                    logger.info(f"  Skipping Blockscout API for Core DAO (chain 1116) - incompatible API structure")
                    continue

                api_name = "Blockscout" if use_blockscout else "Etherscan"
                logger.info(f"  Trying {api_name} for EIP-1967 storage slot...")

                if use_blockscout:
                    # Use Blockscout API
                    base_url = BLOCKSCOUT_URLS[chain_id]
                    params = {
                        'module': 'proxy',
                        'action': 'eth_getStorageAt',
                        'address': contract_address,
                        'position': impl_slot,
                        'tag': 'latest'
                    }
                else:
                    # Use Etherscan API
                    base_url = f"https://api.etherscan.io/v2/api?chainid={chain_id}"
                    params = {
                        'module': 'proxy',
                        'action': 'eth_getStorageAt',
                        'address': contract_address,
                        'position': impl_slot,
                        'tag': 'latest',
                        'apikey': self.etherscan_api_key
                    }

                try:
                    response = requests.get(base_url, params=params, timeout=10)
                    response.raise_for_status()
                    data = response.json()

                    # Check for API errors first
                    if 'error' in data or data.get('status') == '0' or data.get('message') == 'NOTOK':
                        logger.info(f"  {api_name} API error: {data.get('message', 'unknown error')}")
                        # Continue to next detection method
                        continue
                    elif data.get('result') and data['result'] != '0x' + '0' * 64:
                        # Ensure result is valid hex before extracting address
                        result = data['result']
                        logger.info(f"  {api_name} storage slot result: {result}")
                        if result.startswith('0x') and len(result) == 66:  # 0x + 64 hex chars
                            # Extract address from storage slot (last 20 bytes)
                            impl_address = '0x' + result[-40:]
                            if impl_address != '0x' + '0' * 40:
                                logger.info(f"Detected EIP-1967 proxy, implementation: {impl_address}")
                                return impl_address
                            else:
                                logger.info(f"  {api_name} storage slot is empty (all zeros)")
                        else:
                            logger.info(f"  {api_name} storage slot has invalid format (length: {len(result)})")
                    else:
                        logger.info(f"  {api_name} storage slot is empty or all zeros")
                except Exception as e:
                    logger.info(f"  Error checking proxy via {api_name}: {e}")
                    continue

            # Try Etherscan's built-in proxy detection
            try:
                base_url_etherscan = f"https://api.etherscan.io/v2/api?chainid={chain_id}"
                params = {
                    'module': 'contract',
                    'action': 'getsourcecode',
                    'address': contract_address,
                    'apikey': self.etherscan_api_key
                }

                response = requests.get(base_url_etherscan, params=params, timeout=10)
                data = response.json()

                if data.get('result') and len(data['result']) > 0:
                    result = data['result'][0]
                    impl = result.get('Implementation')
                    if impl:
                        logger.info(f"Detected proxy via Etherscan, implementation: {impl}")
                        return impl
            except Exception as e:
                logger.debug(f"Etherscan proxy detection failed: {e}")

            # Try Blockscout's smart-contracts API for proxy info (skip for Core DAO)
            if chain_id in BLOCKSCOUT_URLS and chain_id != 1116:
                logger.info(f"  Trying Blockscout smart-contracts API...")
                try:
                    base_url_blockscout = BLOCKSCOUT_URLS[chain_id]
                    url = f"{base_url_blockscout}/api/v2/smart-contracts/{contract_address}"
                    response = requests.get(url, timeout=10)
                    response.raise_for_status()
                    data = response.json()

                    # Check for proxy information in Blockscout response
                    if data and isinstance(data, dict):
                        # Blockscout might have 'implementations' or 'proxy_type' fields
                        implementations = data.get('implementations') or []
                        logger.info(f"  Blockscout returned {len(implementations)} implementation(s)")
                        if implementations and len(implementations) > 0:
                            impl = implementations[0].get('address')
                            if impl:
                                logger.info(f"Detected proxy via Blockscout smart-contracts API, implementation: {impl}")
                                return impl
                except Exception as e:
                    logger.info(f"  Blockscout smart-contracts API failed: {e}")

            logger.info(f"No proxy implementation detected for {contract_address}")
            return None

        except Exception as e:
            logger.warning(f"Proxy detection failed with exception: {e}")
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

            # Trim response for logging (can be very large for Diamond proxies)
            data_str = str(data)
            if len(data_str) > 100:
                logger.info(f"facets() API response: {data_str[:100]}... (truncated, {len(data_str)} chars total)")
            else:
                logger.info(f"facets() API response: {data_str}")

            # Check if the call succeeded
            # Etherscan API returns status: '1' for success, '0' for failure
            if 'error' in data or data.get('status') == '0' or data.get('message') == 'NOTOK':
                if 'error' in data:
                    error_msg = data.get('error', {}).get('message', 'unknown error')
                else:
                    error_msg = data.get('result', 'API error')
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

                    # Trim response for logging
                    facet_data_str = str(facet_data)
                    if len(facet_data_str) > 100:
                        logger.info(f"  facetAddress({selector}) response: {facet_data_str[:100]}... (truncated)")
                    else:
                        logger.info(f"  facetAddress({selector}) response: {facet_data_str}")

                    # Check if facetAddress() call succeeded
                    if (facet_data.get('result') and
                        'error' not in facet_data and
                        facet_data.get('status') != '0' and
                        facet_data.get('message') != 'NOTOK' and
                        facet_data['result'] != '0x'):
                        # Extract facet address from result (last 20 bytes / 40 hex chars)
                        facet_address = '0x' + facet_data['result'][-40:].lower()
                        # Check it's not zero address
                        if facet_address != '0x' + '0' * 40:
                            selector_to_facet[selector] = facet_address
                            logger.info(f"  Selector {selector} -> Facet {facet_address}")
                    else:
                        if 'error' in facet_data:
                            error_msg = facet_data.get('error', {}).get('message', 'no result')
                        elif facet_data.get('status') == '0':
                            error_msg = facet_data.get('result', 'API error')
                        else:
                            error_msg = 'no result'
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

