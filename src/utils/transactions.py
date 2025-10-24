"""
Transaction and receipt handling for ERC-7730 analyzer.

This module handles:
- Fetching transactions from Etherscan
- Fetching transaction receipts
- Decoding transaction inputs
- Decoding log events (Transfer, Approval, etc.)
- Token metadata fetching (symbols, decimals)
"""

import logging
import time
from typing import Dict, List, Any, Optional
import requests
from web3 import Web3

logger = logging.getLogger(__name__)


class TransactionFetcher:
    """Handles fetching and decoding of transactions and receipts."""

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

    def get_block_by_timestamp(self, timestamp: int, closest: str, chain_id: int = 1) -> Optional[int]:
        """
        Get block number by timestamp using Etherscan API.

        Args:
            timestamp: Unix timestamp
            closest: "before" or "after"
            chain_id: Chain ID

        Returns:
            Block number or None if error
        """
        if not self.etherscan_api_key:
            return None

        params = {
            'module': 'block',
            'action': 'getblocknobytime',
            'timestamp': timestamp,
            'closest': closest,
            'apikey': self.etherscan_api_key
        }

        try:
            base_url = f"https://api.etherscan.io/v2/api?chainid={chain_id}"
            response = requests.get(base_url, params=params)
            response.raise_for_status()
            data = response.json()

            if data['status'] == '1':
                return int(data['result'])
            else:
                logger.warning(f"Could not get block by timestamp: {data.get('message', 'Unknown error')}")
                return None
        except Exception as e:
            logger.warning(f"Failed to get block by timestamp: {e}")
            return None

    def fetch_all_transactions_for_selectors(
        self,
        contract_address: str,
        selectors: List[str],
        chain_id: int = 1,
        per_selector: int = 5,
        window_size: int = 10000,
        page_size: int = 1000,
        max_retries: int = 3
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Efficiently fetch transactions for MULTIPLE selectors at once.
        Fetches each Etherscan page ONCE and distributes matches to all selectors.

        Args:
            contract_address: Contract address
            selectors: List of function selectors (4-byte hex)
            chain_id: Chain ID for the contract
            per_selector: Number of transactions to fetch per selector
            window_size: Number of blocks per window
            page_size: Number of transactions per page
            max_retries: Maximum retry attempts per request

        Returns:
            Dictionary mapping selector -> list of transaction dictionaries
        """
        if not self.etherscan_api_key:
            logger.warning("No block explorer API key provided, cannot fetch transactions")
            return {s: [] for s in selectors}

        logger.info(f"Fetching transactions for {len(selectors)} selectors on chain {chain_id}")

        # Initialize result dict with lowercase selectors
        selector_txs = {s.lower(): [] for s in selectors}
        selector_wanted = {s.lower(): per_selector for s in selectors}

        # Get block range for the lookback period
        now = int(time.time())
        lookback_ago = now - self.lookback_days * 24 * 60 * 60
        logger.info(f"Looking back {self.lookback_days} days for transaction history")

        start_block = self.get_block_by_timestamp(lookback_ago, "after", chain_id)
        end_block = self.get_block_by_timestamp(now, "before", chain_id)

        if not start_block or not end_block:
            logger.warning("Could not determine block range, using fallback")
            end_block = 99999999
            start_block = max(0, end_block - 2500000)

        logger.info(f"Searching for transactions between blocks {start_block} and {end_block}")

        base_url = f"https://api.etherscan.io/v2/api?chainid={chain_id}"
        max_pages = 10000 // page_size
        total_txs_scanned = 0

        def all_done() -> bool:
            """Check if we have enough samples for all selectors"""
            return all(len(txs) >= selector_wanted[sel] for sel, txs in selector_txs.items())

        # Walk windows from newest to oldest
        block_high = end_block
        while block_high >= start_block and not all_done():
            block_low = max(start_block, block_high - window_size + 1)
            logger.debug(f"Scanning window: blocks {block_low} to {block_high}")

            # Paginated scan within this window
            page = 1
            while not all_done() and page <= max_pages:
                # Double-check we won't exceed the limit
                if page * page_size > 10000:
                    logger.info(f"Reached page limit (page {page} × offset {page_size} = {page * page_size} > 10000), moving to next window")
                    break

                params = {
                    'module': 'account',
                    'action': 'txlist',
                    'address': contract_address,
                    'startblock': block_low,
                    'endblock': block_high,
                    'sort': 'desc',
                    'page': page,
                    'offset': page_size,
                    'apikey': self.etherscan_api_key
                }

                # Retry logic
                txs = None
                for attempt in range(max_retries):
                    try:
                        response = requests.get(base_url, params=params)
                        response.raise_for_status()
                        data = response.json()

                        if data['status'] != '1':
                            if 'No transactions found' in data.get('message', ''):
                                txs = []
                                break
                            if 'Result window is too large' in data.get('message', ''):
                                logger.info(f"Hit page limit at page {page}, moving to next window")
                                txs = []
                                break
                            logger.warning(f"Etherscan API warning: {data.get('message', 'Unknown error')}")
                            txs = []
                            break

                        txs = data['result']
                        break
                    except Exception as e:
                        if attempt + 1 == max_retries:
                            logger.error(f"Failed to fetch transactions after {max_retries} attempts: {e}")
                            logger.info(f"Scanned {total_txs_scanned} total transactions before error")
                            for sel, tx_list in selector_txs.items():
                                logger.info(f"Selector {sel}: found {len(tx_list)}/{selector_wanted[sel]} transactions")
                            return selector_txs
                        logger.warning(f"Attempt {attempt + 1} failed, retrying... ({e})")
                        time.sleep(0.7 * (attempt + 1))

                if txs is None:
                    break

                total_txs_scanned += len(txs)

                # Distribute matches to ALL selectors in one pass
                for tx in txs:
                    if tx.get('isError') != '0':
                        continue
                    inp = tx.get('input', '')
                    if len(inp) < 10:
                        continue

                    # Check if this transaction matches any selector we're looking for
                    tx_selector = inp[:10].lower()
                    if tx_selector in selector_txs and len(selector_txs[tx_selector]) < selector_wanted[tx_selector]:
                        selector_txs[tx_selector].append(tx)
                        logger.debug(f"Found match for {tx_selector}: {tx.get('hash')}")

                # If we got fewer transactions than page_size, no more pages in this window
                if len(txs) < page_size:
                    break

                page += 1
                time.sleep(0.2)

            # Move to next (older) window
            block_high = block_low - 1
            time.sleep(0.2)

        logger.info(f"Scanned {total_txs_scanned} total transactions")
        for sel, tx_list in selector_txs.items():
            logger.info(f"Selector {sel}: found {len(tx_list)}/{selector_wanted[sel]} transactions")

        return selector_txs

    def fetch_transaction_receipt(
        self,
        tx_hash: str,
        chain_id: int = 1
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch transaction receipt from Etherscan.

        Args:
            tx_hash: Transaction hash
            chain_id: Chain ID for the transaction

        Returns:
            Transaction receipt or None if error
        """
        if not self.etherscan_api_key:
            logger.warning("No Etherscan API key provided, cannot fetch receipt")
            return None

        params = {
            'module': 'proxy',
            'action': 'eth_getTransactionReceipt',
            'txhash': tx_hash,
            'apikey': self.etherscan_api_key
        }

        try:
            base_url = f"https://api.etherscan.io/v2/api?chainid={chain_id}"
            response = requests.get(base_url, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get('result'):
                logger.debug(f"Successfully fetched receipt for {tx_hash}")
                return data['result']
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
            response = requests.get(base_url, params=params)
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
            response = requests.get(base_url, params=params)
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

    def decode_transaction_input(
        self,
        tx_input: str,
        function_data: Dict,
        abi_helper
    ) -> Optional[Dict[str, Any]]:
        """
        Decode transaction calldata using the function metadata.

        Args:
            tx_input: Transaction input data (hex string)
            function_data: Function metadata from ABI helper
            abi_helper: ABI helper instance

        Returns:
            Dictionary mapping parameter names to decoded values
        """
        try:
            # Remove the function selector
            calldata = tx_input[10:]

            # Get the full ABI entry for this function
            function_name = function_data['name']
            function_abi_entry = None
            for item in abi_helper.abi:
                if item.get('type') == 'function' and item.get('name') == function_name:
                    input_types = [abi_helper._param_abi_type_to_str(inp) for inp in item.get('inputs', [])]
                    sig = f"{function_name}({','.join(input_types)})"
                    if sig == function_data['signature']:
                        function_abi_entry = item
                        break

            if not function_abi_entry:
                logger.error(f"Could not find full ABI entry for {function_data['signature']}")
                return None

            # Get input types for decoding
            inputs = function_abi_entry.get('inputs', [])
            input_types = [abi_helper._param_abi_type_to_str(inp) for inp in inputs]
            input_names = function_data['param_names']

            # Decode the calldata
            decoded_values = self.w3.codec.decode(input_types, bytes.fromhex(calldata))

            # Create a dictionary mapping names to values
            result = {}
            for name, value, input_def in zip(input_names, decoded_values, inputs):
                # Handle tuple types
                if input_def.get('type', '').startswith('tuple'):
                    tuple_result = {}
                    components = input_def.get('components', [])

                    for comp_idx, component in enumerate(components):
                        comp_name = component.get('name', f'field_{comp_idx}')
                        comp_value = value[comp_idx] if comp_idx < len(value) else None

                        if isinstance(comp_value, bytes):
                            tuple_result[comp_name] = '0x' + comp_value.hex()
                        elif isinstance(comp_value, list):
                            tuple_result[comp_name] = str(tuple(
                                ('0x' + v.hex() if isinstance(v, bytes) else v)
                                for v in comp_value
                            ))
                        else:
                            tuple_result[comp_name] = str(comp_value)

                    if not name or name == 'params':
                        result.update(tuple_result)
                    else:
                        result[name] = tuple_result
                elif isinstance(value, bytes):
                    result[name] = '0x' + value.hex()
                elif isinstance(value, list):
                    result[name] = str(tuple(
                        ('0x' + v.hex() if isinstance(v, bytes) else v)
                        for v in value
                    ))
                else:
                    result[name] = str(value)

            logger.debug(f"Decoded transaction input: {result}")
            return result
        except Exception as e:
            logger.error(f"Failed to decode transaction input: {e}")
            return None
