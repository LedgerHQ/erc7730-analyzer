"""Explorer-specific transaction fetch helpers."""

import logging
from typing import Any, Dict, List, Optional

import requests

from ..constants import BLOCKSCOUT_URLS

logger = logging.getLogger(__name__)


class TransactionFetcherCoreExplorerMixin:
    def _fetch_coredao_transactions(
        self,
        contract_address: str,
        filter_type: str = "to"
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Fetch transactions from Core DAO API (Etherscan-style) with pagination.

        Args:
            contract_address: Contract address
            filter_type: "to", "from", or None for all transactions

        Returns:
            List of transactions or None if error
        """
        try:
            from dotenv import load_dotenv
            import os
            load_dotenv(override=True)
            coredao_api_key = os.getenv('COREDAO_API_KEY', '')

            base_url = BLOCKSCOUT_URLS[1116]
            all_transactions = []
            max_pages = 10  # Fetch up to 10 pages (1000 transactions with 100 per page)
            page = 1

            logger.info(f"Fetching transactions from Core DAO API for {contract_address}")

            while page <= max_pages:
                params = {
                    'module': 'account',
                    'action': 'txlist',
                    'address': contract_address,
                    'sort': 'desc',
                    'page': page,
                    'offset': 100  # Core DAO API limit per page
                }

                if coredao_api_key:
                    params['apikey'] = coredao_api_key

                response = requests.get(base_url, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()

                if data.get('status') == '1' and 'result' in data:
                    transactions = data['result']

                    if not transactions or len(transactions) == 0:
                        # No more transactions
                        break

                    all_transactions.extend(transactions)
                    logger.info(f"Core DAO API page {page} returned {len(transactions)} transactions (total: {len(all_transactions)})")

                    # If we got fewer than 100, we've reached the end
                    if len(transactions) < 100:
                        break

                    page += 1
                else:
                    logger.info(f"Core DAO API response on page {page}: status={data.get('status')}, message={data.get('message')}")
                    break

            if all_transactions:
                logger.info(f"Core DAO API returned total of {len(all_transactions)} transactions across {page} page(s)")
                transactions = all_transactions

                # Filter by direction if specified
                if filter_type == "to":
                    transactions = [tx for tx in transactions if tx.get('to', '').lower() == contract_address.lower()]
                elif filter_type == "from":
                    transactions = [tx for tx in transactions if tx.get('from', '').lower() == contract_address.lower()]

                # Convert Etherscan format to Blockscout v2 format
                converted_txs = []
                for tx in transactions:
                    converted_tx = {
                        'hash': tx.get('hash', ''),
                        'from': {'hash': tx.get('from', '')},
                        'to': {'hash': tx.get('to', '')} if tx.get('to') else None,
                        'value': tx.get('value', '0'),
                        'raw_input': tx.get('input', '0x'),  # Blockscout v2 uses 'raw_input'
                        'block': int(tx.get('blockNumber', 0)),  # Blockscout v2 uses 'block'
                        'timestamp': tx.get('timeStamp', ''),
                        'method': None,  # Will be determined later
                        'status': 'ok' if tx.get('txreceipt_status') == '1' else 'error',
                        'gas_used': tx.get('gasUsed', '0'),
                        'gas_price': tx.get('gasPrice', '0')
                    }
                    converted_txs.append(converted_tx)

                logger.info(f"Converted {len(converted_txs)} Core DAO transactions to standard format")
                return converted_txs
            else:
                logger.info(f"No transactions found from Core DAO API")
                return None

        except Exception as e:
            logger.debug(f"Failed to fetch transactions from Core DAO API: {e}")
            return None


    def _fetch_blockscout_v2_transactions(
        self,
        contract_address: str,
        chain_id: int,
        filter_type: str = "to"
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Fetch transactions from Blockscout v2 API or Core DAO API.

        Args:
            contract_address: Contract address
            chain_id: Chain ID
            filter_type: "to", "from", or None for all transactions

        Returns:
            List of transactions or None if error
        """
        chain_id = int(chain_id)
        if chain_id not in BLOCKSCOUT_URLS:
            return None

        # Special handling for Core DAO (chain 1116) - uses Etherscan-style API
        if chain_id == 1116:
            return self._fetch_coredao_transactions(contract_address, filter_type)

        try:
            base_url = BLOCKSCOUT_URLS[chain_id]
            url = f"{base_url}/api/v2/addresses/{contract_address}/transactions"
            params = {}
            if filter_type:
                params['filter'] = filter_type

            all_transactions = []
            next_page_params = None
            max_pages = 10  # Limit to prevent infinite loops

            for _ in range(max_pages):
                if next_page_params:
                    response = requests.get(url, params=next_page_params, timeout=10)
                else:
                    response = requests.get(url, params=params, timeout=10)

                response.raise_for_status()
                data = response.json()

                items = data.get('items', [])
                all_transactions.extend(items)

                # Check if there's a next page
                next_page_params_raw = data.get('next_page_params')
                if not next_page_params_raw:
                    break

                # Update params for next page
                next_page_params = params.copy()
                next_page_params.update(next_page_params_raw)

                time.sleep(0.3)  # Rate limiting

            logger.debug(f"Fetched {len(all_transactions)} transactions from Blockscout v2")
            return all_transactions

        except Exception as e:
            logger.debug(f"Failed to fetch Blockscout v2 transactions: {e}")
            return None


    def _convert_blockscout_v2_to_etherscan_format(self, tx: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert Blockscout v2 transaction format to Etherscan format.

        Args:
            tx: Blockscout v2 transaction

        Returns:
            Transaction in Etherscan format
        """
        return {
            'hash': tx.get('hash', ''),
            'blockNumber': str(tx.get('block', 0)),
            'timeStamp': str(tx.get('timestamp', '')),
            'from': tx.get('from', {}).get('hash', ''),
            'to': tx.get('to', {}).get('hash', '') if tx.get('to') else '',
            'value': str(tx.get('value', '0')),
            'input': tx.get('raw_input', ''),
            'isError': '0' if tx.get('status') == 'ok' else '1',
            'gasUsed': str(tx.get('gas_used', '0')),
            'gasPrice': str(tx.get('gas_price', '0')),
        }


    def get_block_by_timestamp(self, timestamp: int, closest: str, chain_id: int = 1, use_blockscout: bool = False) -> Optional[int]:
        """
        Get block number by timestamp using Etherscan or Blockscout API.

        Args:
            timestamp: Unix timestamp
            closest: "before" or "after"
            chain_id: Chain ID
            use_blockscout: Use Blockscout API instead of Etherscan

        Returns:
            Block number or None if error
        """
        chain_id = int(chain_id)  # Ensure it's an int

        if not self.etherscan_api_key and not use_blockscout:
            return None

        params = {
            'module': 'block',
            'action': 'getblocknobytime',
            'timestamp': timestamp,
            'closest': closest,
        }

        # Blockscout doesn't require API key
        if not use_blockscout:
            params['apikey'] = self.etherscan_api_key

        try:
            base_url = self._get_api_base_url(chain_id, use_blockscout)
            response = requests.get(base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data['status'] == '1':
                return int(data['result'])
            else:
                logger.debug(f"Could not get block by timestamp: {data.get('message', 'Unknown error')}")
                return None
        except Exception as e:
            logger.debug(f"Failed to get block by timestamp: {e}")
            return None

