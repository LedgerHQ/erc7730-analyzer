"""Receipt/log decoding and token metadata helpers."""

import logging
from typing import Any, Dict, Optional

import requests
from web3 import Web3

from .constants import BLOCKSCOUT_URLS

logger = logging.getLogger(__name__)


class TransactionFetcherReceiptMixin:
    def fetch_transaction_receipt(
        self,
        tx_hash: str,
        chain_id: int = 1
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch transaction receipt from Etherscan or Blockscout.

        Args:
            tx_hash: Transaction hash
            chain_id: Chain ID for the transaction

        Returns:
            Transaction receipt or None if error
        """
        chain_id = int(chain_id)  # Ensure it's an int

        if not self.etherscan_api_key:
            logger.warning("No API key provided, cannot fetch receipt")
            return None

        # Use the API that worked for this chain
        use_blockscout = self.api_type_per_chain.get(chain_id) == "Blockscout"

        # For Blockscout v2, get the transaction details which include logs
        # Skip Blockscout v2 API for Core DAO (chain 1116) - use Etherscan-style instead
        if use_blockscout and chain_id in BLOCKSCOUT_URLS and chain_id != 1116:
            try:
                base_url = BLOCKSCOUT_URLS[chain_id]
                url = f"{base_url}/api/v2/transactions/{tx_hash}"
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                data = response.json()

                # Convert Blockscout v2 format to Etherscan receipt format
                if data:
                    receipt = {
                        'transactionHash': data.get('hash', ''),
                        'blockNumber': hex(data.get('block', 0)),
                        'from': data.get('from', {}).get('hash', ''),
                        'to': data.get('to', {}).get('hash', '') if data.get('to') else '',
                        'gasUsed': hex(int(data.get('gas_used', '0'))),
                        'status': '0x1' if data.get('status') == 'ok' else '0x0',
                        'logs': []
                    }

                    # Convert logs format if available
                    if 'logs' in data:
                        for log in data['logs']:
                            receipt['logs'].append({
                                'address': log.get('address', {}).get('hash', '') if isinstance(log.get('address'), dict) else log.get('address', ''),
                                'topics': log.get('topics', []),
                                'data': log.get('data', '0x')
                            })

                    logger.debug(f"Successfully fetched receipt for {tx_hash} from Blockscout v2")
                    return receipt
                else:
                    logger.warning(f"No receipt found for {tx_hash}")
                    return None
            except Exception as e:
                logger.error(f"Failed to fetch receipt from Blockscout v2 for {tx_hash}: {e}")
                return None

        # Use Etherscan API (or Core DAO Etherscan-style API)
        params = {
            'module': 'proxy',
            'action': 'eth_getTransactionReceipt',
            'txhash': tx_hash,
        }

        # Add API key
        if chain_id == 1116:
            # Core DAO uses its own API key
            from dotenv import load_dotenv
            import os
            load_dotenv(override=True)
            coredao_api_key = os.getenv('COREDAO_API_KEY', '')
            if coredao_api_key:
                params['apikey'] = coredao_api_key
        elif not use_blockscout:
            # Etherscan requires API key
            params['apikey'] = self.etherscan_api_key

        try:
            base_url = self._get_api_base_url(chain_id, use_blockscout)
            response = requests.get(base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get('result'):
                result = data['result']
                if isinstance(result, dict):  # Validate it's actually a dict
                    logger.debug(f"Successfully fetched receipt for {tx_hash}")
                    return result
                else:
                    logger.warning(f"Etherscan returned non-dict result for {tx_hash}: {result}")
                    return None
            else:
                logger.warning(f"No receipt found for {tx_hash}")
                return None
        except Exception as e:
            logger.error(f"Failed to fetch receipt for {tx_hash}: {e}")
            return None

    def decode_log_event(self, log: Dict[str, Any], chain_id: int = 1) -> Optional[Dict[str, Any]]:
        """
        Decode a log event, with special handling for common token events.

        Args:
            log: Log entry from transaction receipt
            chain_id: Chain ID for RPC calls

        Returns:
            Decoded event data or None
        """
        try:
            topics = log.get('topics', [])
            if not topics:
                return None

            event_signature = topics[0]

            # ERC-20 Transfer event
            if event_signature == '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef':
                if len(topics) >= 3:
                    from_address = '0x' + topics[1][-40:]
                    to_address = '0x' + topics[2][-40:]
                    value_hex = log.get('data', '0x0')
                    value = int(value_hex, 16) if value_hex != '0x' else 0

                    return {
                        'event': 'Transfer',
                        'token': log.get('address', 'unknown'),
                        'from': from_address,
                        'to': to_address,
                        'value': str(value),
                        'value_formatted': self.format_token_amount(value, log.get('address'), chain_id)
                    }

            # ERC-20 Approval event
            elif event_signature == '0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925':
                if len(topics) >= 3:
                    owner = '0x' + topics[1][-40:]
                    spender = '0x' + topics[2][-40:]
                    value_hex = log.get('data', '0x0')
                    value = int(value_hex, 16) if value_hex != '0x' else 0

                    return {
                        'event': 'Approval',
                        'token': log.get('address', 'unknown'),
                        'owner': owner,
                        'spender': spender,
                        'value': str(value),
                        'value_formatted': self.format_token_amount(value, log.get('address'), chain_id)
                    }

            # For other events, return basic info
            return {
                'event': 'Unknown',
                'signature': event_signature,
                'address': log.get('address', 'unknown'),
                'topics': topics,
                'data': log.get('data', '0x')
            }

        except Exception as e:
            logger.warning(f"Failed to decode log event: {e}")
            return None

    def get_token_symbol(self, token_address: str, chain_id: int = 1) -> Optional[str]:
        """
        Fetch token symbol from the contract using Etherscan API.

        Args:
            token_address: Token contract address
            chain_id: Chain ID for the token

        Returns:
            Token symbol or None if unable to fetch
        """
        # Check cache first
        cache_key = f"{chain_id}:{token_address.lower()}"
        if cache_key in self.token_symbol_cache:
            return self.token_symbol_cache[cache_key]

        if not self.etherscan_api_key:
            return None

        try:
            # Call symbol() function - signature: 0x95d89b41
            params = {
                'module': 'proxy',
                'action': 'eth_call',
                'to': token_address,
                'data': '0x95d89b41',
                'tag': 'latest',
                'apikey': self.etherscan_api_key
            }

            base_url = f"https://api.etherscan.io/v2/api?chainid={chain_id}"
            response = requests.get(base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get('result') and data['result'] != '0x':
                result_hex = data['result']
                result_hex = result_hex[2:] if result_hex.startswith('0x') else result_hex
                if result_hex:
                    try:
                        if len(result_hex) > 128:
                            # Dynamic string format
                            length = int(result_hex[64:128], 16)
                            symbol_hex = result_hex[128:128 + length * 2]
                        else:
                            # bytes32 format or short string
                            symbol_hex = result_hex

                        symbol = bytes.fromhex(symbol_hex).decode('utf-8').rstrip('\x00')
                        if symbol:
                            self.token_symbol_cache[cache_key] = symbol
                            logger.debug(f"Fetched symbol for {token_address}: {symbol}")
                            time.sleep(0.1)
                            return symbol
                    except Exception as e:
                        logger.debug(f"Failed to decode symbol for {token_address}: {e}")

        except Exception as e:
            logger.debug(f"Failed to fetch symbol for {token_address}: {e}")

        return None

    def get_token_decimals(self, token_address: str, chain_id: int = 1) -> Optional[int]:
        """
        Fetch token decimals from the contract using Etherscan API.

        Args:
            token_address: Token contract address
            chain_id: Chain ID for the token

        Returns:
            Number of decimals or None if unable to fetch
        """
        # Check cache first
        cache_key = f"{chain_id}:{token_address.lower()}"
        if cache_key in self.token_decimals_cache:
            return self.token_decimals_cache[cache_key]

        if not self.etherscan_api_key:
            return None

        try:
            # Call decimals() function - signature: 0x313ce567
            params = {
                'module': 'proxy',
                'action': 'eth_call',
                'to': token_address,
                'data': '0x313ce567',
                'tag': 'latest',
                'apikey': self.etherscan_api_key
            }

            base_url = f"https://api.etherscan.io/v2/api?chainid={chain_id}"
            response = requests.get(base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get('result') and data['result'] != '0x':
                decimals = int(data['result'], 16)
                self.token_decimals_cache[cache_key] = decimals
                logger.debug(f"Fetched decimals for {token_address}: {decimals}")
                time.sleep(0.1)
                return decimals

        except Exception as e:
            logger.debug(f"Failed to fetch decimals for {token_address}: {e}")

        return None

    def format_token_amount(self, value: int, token_address: str, chain_id: int = 1) -> str:
        """
        Format token amount using actual decimals and symbol from contract.

        Args:
            value: Raw token amount
            token_address: Token contract address
            chain_id: Chain ID for the token

        Returns:
            Formatted token amount string
        """
        token_short = token_address[:10] + '...' if len(token_address) > 10 else token_address

        symbol = self.get_token_symbol(token_address, chain_id)
        decimals = self.get_token_decimals(token_address, chain_id)

        if decimals is not None:
            formatted = value / (10 ** decimals)
            amount_str = f"{formatted:.6f}".rstrip('0').rstrip('.')

            if symbol:
                return f"{amount_str} {symbol}"
            else:
                return f"{amount_str} ({token_short})"
        else:
            if symbol:
                return f"{value} (raw) {symbol}"
            else:
                return f"{value} (raw, {token_short})"
