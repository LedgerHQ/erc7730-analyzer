"""Core setup and chain-level API metadata helpers."""

import logging
from typing import Any, Dict, Optional

import requests
from web3 import Web3

from ..constants import BLOCKSCOUT_URLS

logger = logging.getLogger(__name__)


class TransactionFetcherCoreBaseMixin:
    def __init__(self, etherscan_api_key: Optional[str] = None, lookback_days: int = 20):
        """
        Initialize the transaction fetcher.

        Args:
            etherscan_api_key: Etherscan API key for fetching data
            lookback_days: Number of days to look back for transaction history
        """
        self.etherscan_api_key = etherscan_api_key
        self.lookback_days = lookback_days
        self.w3 = Web3()
        self.token_decimals_cache = {}
        self.token_symbol_cache = {}
        self.api_type_per_chain = {}  # Track which API worked for each chain


    def _get_api_base_url(self, chain_id: int, use_blockscout: bool = False) -> str:
        """
        Get the appropriate API base URL for a chain.

        Args:
            chain_id: Chain ID
            use_blockscout: Force use of Blockscout API

        Returns:
            Base URL for API requests
        """
        chain_id = int(chain_id)  # Ensure it's an int
        if use_blockscout and chain_id in BLOCKSCOUT_URLS:
            return BLOCKSCOUT_URLS[chain_id]
        return f"https://api.etherscan.io/v2/api?chainid={chain_id}"


    def _get_current_block_number(self, chain_id: int, use_blockscout: bool = False) -> Optional[int]:
        """
        Get the current block number using eth_blockNumber.

        Args:
            chain_id: Chain ID
            use_blockscout: Use Blockscout API instead of Etherscan

        Returns:
            Current block number or None if error
        """
        chain_id = int(chain_id)

        # Special handling for Core DAO (chain 1116) - uses Etherscan-style API
        if chain_id == 1116 and use_blockscout:
            return self._get_coredao_block_number()

        # Use Blockscout v2 API if available
        if use_blockscout and chain_id in BLOCKSCOUT_URLS:
            stats = self._fetch_blockscout_v2_stats(chain_id)
            if stats and 'total_blocks' in stats:
                try:
                    # total_blocks is a string like "60681962"
                    block_number = int(stats['total_blocks'])
                    return block_number
                except (ValueError, TypeError):
                    logger.debug("Failed to parse block number from Blockscout v2 stats")
            return None

        params = {
            'module': 'proxy',
            'action': 'eth_blockNumber',
        }

        # Etherscan requires API key
        if not use_blockscout:
            if not self.etherscan_api_key:
                return None
            params['apikey'] = self.etherscan_api_key

        try:
            base_url = self._get_api_base_url(chain_id, use_blockscout)
            response = requests.get(base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get('result'):
                # Result is in hex format (0x...)
                block_number = int(data['result'], 16)
                return block_number
            return None
        except Exception as e:
            logger.debug(f"Failed to get current block number: {e}")
            return None


    def _get_coredao_block_number(self) -> Optional[int]:
        """
        Get current block number from Core DAO API.

        Returns:
            Current block number or None if error
        """
        try:
            from dotenv import load_dotenv
            import os
            load_dotenv(override=True)
            coredao_api_key = os.getenv('COREDAO_API_KEY', '')

            base_url = BLOCKSCOUT_URLS[1116]
            params = {
                'module': 'proxy',
                'action': 'eth_blockNumber'
            }

            if coredao_api_key:
                params['apikey'] = coredao_api_key

            response = requests.get(base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get('result'):
                # Result is in hex format (0x...)
                block_number = int(data['result'], 16)
                logger.info(f"Core DAO current block number: {block_number}")
                return block_number
            return None
        except Exception as e:
            logger.debug(f"Failed to get Core DAO block number: {e}")
            return None


    def _fetch_blockscout_v2_stats(self, chain_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetch stats from Blockscout v2 API to get current block number.

        Args:
            chain_id: Chain ID

        Returns:
            Stats dictionary or None if error
        """
        chain_id = int(chain_id)
        if chain_id not in BLOCKSCOUT_URLS:
            return None

        try:
            base_url = BLOCKSCOUT_URLS[chain_id]
            response = requests.get(f"{base_url}/api/v2/stats", timeout=10)
            response.raise_for_status()
            data = response.json()
            return data
        except Exception as e:
            logger.debug(f"Failed to fetch Blockscout v2 stats: {e}")
            return None

