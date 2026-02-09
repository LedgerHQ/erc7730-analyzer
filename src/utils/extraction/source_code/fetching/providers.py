"""Source-provider fetchers (Sourcify/Etherscan/Blockscout)."""

import json
from typing import Dict, Optional

import requests

from ..shared import BLOCKSCOUT_URLS, logger


class SourceCodeFetchingProviderMixin:
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


    def get_contract_name_from_etherscan(self, contract_address: str, chain_id: int) -> Optional[str]:
        """
        Get the deployed contract name from Etherscan.

        Args:
            contract_address: Contract address
            chain_id: Chain ID

        Returns:
            Contract name or None
        """
        try:
            base_url = f"https://api.etherscan.io/v2/api?chainid={chain_id}"
            params = {
                'module': 'contract',
                'action': 'getsourcecode',
                'address': contract_address,
                'apikey': self.etherscan_api_key
            }

            response = requests.get(base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data['status'] == '1' and data.get('result'):
                contract_name = data['result'][0].get('ContractName', '')
                if contract_name:
                    logger.debug(f"Contract name from Etherscan: {contract_name}")
                    return contract_name

        except Exception as e:
            logger.debug(f"Failed to get contract name from Etherscan: {e}")

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


    def fetch_source_from_blockscout(self, contract_address: str, chain_id: int) -> Optional[str]:
        """
        Fetch source code from Blockscout v2 API or Core DAO API.

        Args:
            contract_address: Contract address
            chain_id: Chain ID

        Returns:
            Combined source code or None
        """
        if chain_id not in BLOCKSCOUT_URLS:
            logger.debug(f"Chain {chain_id} not in Blockscout URLs")
            return None

        try:
            base_url = BLOCKSCOUT_URLS[chain_id]

            # Special handling for Core DAO (chain 1116) - uses different API structure
            if chain_id == 1116:
                url = f"{base_url}/contracts/source_code_of_verified_contract/{contract_address}"
                params = {}
                if self.coredao_api_key:
                    params['apikey'] = self.coredao_api_key

                logger.info(f"Fetching from Core DAO API: {url}")
                try:
                    response = requests.get(url, params=params, timeout=10)
                    logger.info(f"Core DAO API response status: {response.status_code}")

                    if response.status_code == 401:
                        logger.error(f"Core DAO API authentication failed - check API key")
                        return None

                    response.raise_for_status()
                    data = response.json()
                    logger.info(f"Core DAO API response keys: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")

                    # Core DAO API uses Etherscan-style response format
                    if data and data.get('status') == '1' and 'result' in data:
                        result = data['result']
                        if isinstance(result, list) and len(result) > 0:
                            contract_data = result[0]
                            source_code = contract_data.get('SourceCode', '')

                            if source_code:
                                # Parse multi-file format (JSON string starting with {{)
                                if source_code.startswith('{{'):
                                    import json
                                    # Remove outer braces and parse
                                    source_json = json.loads(source_code[1:-1])
                                    sources = source_json.get('sources', {})

                                    combined_code = []
                                    for filename, file_data in sources.items():
                                        content = file_data.get('content', '')
                                        if content:
                                            combined_code.append(f"// File: {filename}\n{content}")

                                    if combined_code:
                                        final_source = '\n\n'.join(combined_code)
                                        logger.info(f"Fetched source code from Core DAO API ({len(final_source)} chars, {len(combined_code)} files)")
                                        return final_source
                                else:
                                    # Single file source code
                                    logger.info(f"Fetched source code from Core DAO API ({len(source_code)} chars)")
                                    return source_code
                            else:
                                logger.info(f"Core DAO API returned empty SourceCode")
                        else:
                            logger.info(f"Core DAO API result is not a list or is empty")
                    else:
                        logger.info(f"Core DAO API response: status={data.get('status')}, message={data.get('message')}")
                    return None
                except Exception as e:
                    logger.error(f"Failed to fetch from Core DAO API: {e}")
                    return None

            # Standard Blockscout v2 API
            url = f"{base_url}/api/v2/smart-contracts/{contract_address}"

            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Check if source code is available
            if not data or 'source_code' not in data:
                logger.debug(f"No source code found on Blockscout")
                return None

            source_code = data['source_code']

            if not source_code:
                return None

            # Check for 'additional_sources' which contains imported files
            additional_sources = data.get('additional_sources', [])

            # Handle multi-file format
            if isinstance(source_code, dict):
                combined_code = []
                for filename, content in source_code.items():
                    if isinstance(content, str):
                        combined_code.append(f"// File: {filename}\n{content}")

                if combined_code:
                    logger.info(f"Fetched {len(combined_code)} files from Blockscout")
                    return '\n\n'.join(combined_code)

            # Single file - check if we need to add additional sources
            combined_code = []
            if isinstance(source_code, str):
                # Add main source
                combined_code.append(f"// Main Contract\n{source_code}")

                # Add additional sources (imported files)
                if additional_sources:
                    logger.info(f"Found {len(additional_sources)} additional source files")
                    for source in additional_sources:
                        filename = source.get('file_path', 'unknown')
                        content = source.get('source_code', '')
                        if content:
                            combined_code.append(f"// File: {filename}\n{content}")

                final_source = '\n\n'.join(combined_code)
                logger.info(f"Fetched source code from Blockscout ({len(final_source)} chars, {len(combined_code)} files)")
                return final_source

            return None

        except Exception as e:
            logger.debug(f"Failed to fetch from Blockscout: {e}")
            return None

