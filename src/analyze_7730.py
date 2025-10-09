#!/usr/bin/env python3
"""
Analyze ERC-7730 clear signing files and fetch transaction data from Etherscan.

This script:
1. Parses ERC-7730 JSON files to extract function selectors
2. Fetches the last 5 valid transactions for each selector from Etherscan
3. Decodes transaction calldata and logs receipts and maps it to ABI function inputs
4. Generates audit reports using AI
"""

import json
import logging
import sys
import time
import os
from typing import Dict, List, Any, Optional
from pathlib import Path
import requests
from web3 import Web3
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(override=True)

# Import the ABI class from utils
sys.path.append(str(Path(__file__).parent))
from utils.abi_utils import ABI

# Logger will be configured in main() based on --debug flag
logger = logging.getLogger(__name__)


class ERC7730Analyzer:
    """Analyzer for ERC-7730 clear signing files with Etherscan integration."""

    def __init__(self, etherscan_api_key: Optional[str] = None, lookback_days: int = 20):
        """
        Initialize the analyzer.

        Args:
            etherscan_api_key: Etherscan API key for fetching transaction data
            lookback_days: Number of days to look back for transaction history (default: 20)
        """
        self.etherscan_api_key = etherscan_api_key
        self.lookback_days = lookback_days
        self.w3 = Web3()
        self.abi_helper = None  # Will be initialized when ABI is loaded
        self.token_decimals_cache = {}  # Cache for token decimals
        self.token_symbol_cache = {}  # Cache for token symbols

    def parse_erc7730_file(self, file_path: Path) -> Dict[str, Any]:
        """
        Parse an ERC-7730 JSON file and extract relevant information.

        Args:
            file_path: Path to the ERC-7730 JSON file

        Returns:
            Dictionary containing parsed data
        """
        logger.info(f"Parsing ERC-7730 file: {file_path}")

        try:
            with open(file_path, 'r') as f:
                data = json.load(f)

            logger.info(f"Successfully loaded {file_path}")
            return data
        except Exception as e:
            logger.error(f"Failed to parse {file_path}: {e}")
            raise

    def extract_selectors(self, erc7730_data: Dict[str, Any]) -> List[str]:
        """
        Extract all function selectors from ERC-7730 data.

        Args:
            erc7730_data: Parsed ERC-7730 JSON data

        Returns:
            List of function selectors (4-byte hex strings)
        """
        logger.info("Extracting function selectors from ERC-7730 data")

        selectors = []

        # Selectors are in the display.formats section as keys
        if 'display' in erc7730_data and 'formats' in erc7730_data['display']:
            formats = erc7730_data['display']['formats']
            selectors = list(formats.keys())

        logger.info(f"Found {len(selectors)} selectors: {selectors}")
        return selectors

    def get_contract_deployments(self, erc7730_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract all contract deployments from ERC-7730 data.

        Args:
            erc7730_data: Parsed ERC-7730 JSON data

        Returns:
            List of deployment dictionaries with 'address' and 'chainId' keys
        """
        try:
            deployments = erc7730_data['context']['contract']['deployments']
            # Get all deployments with their chainIds
            deployment_list = []
            for deployment in deployments:
                address = deployment.get('address')
                chain_id = deployment.get('chainId')
                if address and chain_id:
                    deployment_list.append({
                        'address': address,
                        'chainId': chain_id
                    })
            logger.info(f"Found {len(deployment_list)} contract deployments across various chains")
            return deployment_list
        except Exception as e:
            logger.error(f"Failed to extract contract deployments: {e}")
            return []

    def fetch_contract_abi(self, contract_address: str, chain_id: int = 1) -> Optional[List[Dict]]:
        """
        Fetch contract ABI from Etherscan.

        Args:
            contract_address: Ethereum contract address
            chain_id: Chain ID for the contract (default: 1 for mainnet)

        Returns:
            Contract ABI as a list of dictionaries
        """
        if not self.etherscan_api_key:
            logger.warning("No Etherscan API key provided, cannot fetch ABI")
            return None

        logger.info(f"Fetching ABI for contract {contract_address} on chain {chain_id}")

        params = {
            'module': 'contract',
            'action': 'getabi',
            'address': contract_address,
            'apikey': self.etherscan_api_key
        }

        try:
            base_url = f"https://api.etherscan.io/v2/api?chainid={chain_id}"
            response = requests.get(base_url, params=params)
            response.raise_for_status()
            data = response.json()

            if data['status'] == '1':
                abi = json.loads(data['result'])
                logger.info(f"Successfully fetched ABI with {len(abi)} entries")
                return abi
            else:
                logger.error(f"Etherscan API error: {data.get('message', 'Unknown error')}")
                return None
        except Exception as e:
            logger.error(f"Failed to fetch ABI: {e}")
            return None

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
        This is much more efficient than calling the API separately for each selector.

        Args:
            contract_address: Contract address
            selectors: List of function selectors (4-byte hex)
            chain_id: Chain ID for the contract (default: 1 for mainnet)
            per_selector: Number of transactions to fetch per selector
            window_size: Number of blocks per window (default: 10000)
            page_size: Number of transactions per page (default: 1000, max allowed by Etherscan)
            max_retries: Maximum retry attempts per request

        Returns:
            Dictionary mapping selector -> list of transaction dictionaries
        """
        if not self.etherscan_api_key:
            logger.warning("No block explorer API key provided, cannot fetch transactions")
            return {s: [] for s in selectors}

        logger.info(f"Fetching transactions for {len(selectors)} selectors on chain {chain_id}")

        # Initialize result dict with lowercase selectors for case-insensitive matching
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
        max_pages = 10000 // page_size  # Etherscan limit: page × offset ≤ 10,000
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
                    'sort': 'desc',  # newest first
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
                            # Check if we hit the page limit (page × offset > 10,000)
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
                            # Return what we have so far
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
                time.sleep(0.2)  # Rate limiting between pages

            # Move to next (older) window
            block_high = block_low - 1
            time.sleep(0.2)  # Rate limiting between windows

        logger.info(f"Scanned {total_txs_scanned} total transactions")
        for sel, tx_list in selector_txs.items():
            logger.info(f"Selector {sel}: found {len(tx_list)}/{selector_wanted[sel]} transactions")

        return selector_txs

    def fetch_transactions_for_selector(
        self,
        contract_address: str,
        selector: str,
        chain_id: int = 1,
        limit: int = 5,
        window_size: int = 10000,
        page_size: int = 1000,
        max_retries: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Fetch the last N transactions for a specific function selector using pagination.
        Searches within a 1-year window, walking backwards from the present.

        Args:
            contract_address: Contract address
            selector: Function selector (4-byte hex)
            chain_id: Chain ID for the contract (default: 1 for mainnet)
            limit: Number of transactions to fetch
            window_size: Number of blocks per window (default: 5000, smaller to avoid 10k page limit)
            page_size: Number of transactions per page (default: 1000, max allowed by Etherscan)
            max_retries: Maximum retry attempts per request

        Returns:
            List of transaction dictionaries

        Note:
            Etherscan has a limit where page × offset ≤ 10,000. With offset=1000, we can only
            access 10 pages (10,000 txs) per window. Smaller windows help ensure we don't miss txs.
        """
        if not self.etherscan_api_key:
            logger.warning("No block explorer API key provided, cannot fetch transactions")
            return []

        logger.info(f"Fetching last {limit} transactions for selector {selector} on chain {chain_id}")

        # Get block range for the last year
        now = int(time.time())
        year_ago = now - 90 * 24 * 60 * 60

        start_block = self.get_block_by_timestamp(year_ago, "after", chain_id)
        end_block = self.get_block_by_timestamp(now, "before", chain_id)

        if not start_block or not end_block:
            logger.warning("Could not determine block range for 1-year window, using fallback")
            # Fallback: use a large recent block range
            end_block = 99999999
            start_block = max(0, end_block - 2500000)  # Approximate 1 year of blocks

        logger.info(f"Searching for transactions between blocks {start_block} and {end_block}")

        matching_txs = []
        base_url = f"https://api.etherscan.io/v2/api?chainid={chain_id}"

        # Walk windows from newest to oldest
        block_high = end_block
        while block_high >= start_block and len(matching_txs) < limit:
            block_low = max(start_block, block_high - window_size + 1)
            logger.debug(f"Scanning window: blocks {block_low} to {block_high}")

            # Paginated scan within this window
            page = 1
            while len(matching_txs) < limit:
                params = {
                    'module': 'account',
                    'action': 'txlist',
                    'address': contract_address,
                    'startblock': block_low,
                    'endblock': block_high,
                    'sort': 'desc',  # newest first
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
                            # Check if we hit the page limit (page × offset > 10,000)
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
                            return matching_txs
                        logger.warning(f"Attempt {attempt + 1} failed, retrying... ({e})")
                        time.sleep(0.7 * (attempt + 1))

                if txs is None:
                    break

                # Filter by selector
                for tx in txs:
                    if tx.get('isError') == '0' and tx.get('input', '').startswith(selector):
                        matching_txs.append(tx)
                        if len(matching_txs) >= limit:
                            break

                # If we got fewer transactions than page_size, no more pages in this window
                if len(txs) < page_size:
                    break

                page += 1
                time.sleep(0.2)  # Rate limiting between pages

            # Move to next (older) window
            block_high = block_low - 1
            time.sleep(0.2)  # Rate limiting between windows

        logger.info(f"Found {len(matching_txs)} matching transactions for selector {selector}")
        return matching_txs

    def get_function_abi_by_selector(
        self,
        selector: str
    ) -> Optional[Dict]:
        """
        Find the function ABI entry matching a given selector.

        Args:
            selector: Function selector (4-byte hex) or function signature

        Returns:
            Function metadata or None
        """
        if not self.abi_helper:
            logger.error("ABI helper not initialized")
            return None

        # If selector is a function signature (not hex), convert it to selector first
        if not selector.startswith('0x'):
            hex_selector = self.abi_helper._function_signature_to_selector(selector)
            logger.info(f"Converted signature '{selector}' to selector '{hex_selector}'")
        else:
            hex_selector = selector

        function_data = self.abi_helper.find_function_by_selector(hex_selector)

        if function_data:
            logger.info(f"Found matching function: {function_data['signature']} -> {hex_selector}")
            return function_data
        else:
            logger.warning(f"No function found for selector {hex_selector}")
            return None

    def fetch_transaction_receipt(
        self,
        tx_hash: str,
        chain_id: int = 1
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch transaction receipt from Etherscan.

        Args:
            tx_hash: Transaction hash
            chain_id: Chain ID for the transaction (default: 1 for mainnet)

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

            # ERC-20 Transfer event: Transfer(address indexed from, address indexed to, uint256 value)
            # Signature: 0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef
            if event_signature == '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef':
                if len(topics) >= 3:
                    from_address = '0x' + topics[1][-40:]
                    to_address = '0x' + topics[2][-40:]
                    # Decode value from data field
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

            # ERC-20 Approval event: Approval(address indexed owner, address indexed spender, uint256 value)
            # Signature: 0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925
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
            # Call symbol() function via Etherscan API - signature: 0x95d89b41
            params = {
                'module': 'proxy',
                'action': 'eth_call',
                'to': token_address,
                'data': '0x95d89b41',  # symbol() function signature
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
                    # Symbol is returned as bytes32 or dynamic string
                    # Try to decode as string (skip first 64 chars which are offset and length)
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
                            # Cache the result
                            self.token_symbol_cache[cache_key] = symbol
                            logger.debug(f"Fetched symbol for {token_address}: {symbol}")
                            time.sleep(0.1)  # Small delay to avoid rate limiting
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
            # Call decimals() function via Etherscan API - signature: 0x313ce567
            params = {
                'module': 'proxy',
                'action': 'eth_call',
                'to': token_address,
                'data': '0x313ce567',  # decimals() function signature
                'tag': 'latest',
                'apikey': self.etherscan_api_key
            }

            base_url = f"https://api.etherscan.io/v2/api?chainid={chain_id}"
            response = requests.get(base_url, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get('result') and data['result'] != '0x':
                # Decode the result (should be a uint8)
                decimals = int(data['result'], 16)
                # Cache the result
                self.token_decimals_cache[cache_key] = decimals
                logger.debug(f"Fetched decimals for {token_address}: {decimals}")
                time.sleep(0.1)  # Small delay to avoid rate limiting
                return decimals

        except Exception as e:
            logger.debug(f"Failed to fetch decimals for {token_address}: {e}")

        return None

    def format_token_amount(self, value: int, token_address: str, chain_id: int = 1) -> str:
        """
        Format token amount using actual decimals and symbol from contract, or raw value if unavailable.

        Args:
            value: Raw token amount
            token_address: Token contract address
            chain_id: Chain ID for the token

        Returns:
            Formatted token amount string
        """
        token_short = token_address[:10] + '...' if len(token_address) > 10 else token_address

        # Try to get symbol and decimals from the contract
        symbol = self.get_token_symbol(token_address, chain_id)
        decimals = self.get_token_decimals(token_address, chain_id)

        if decimals is not None:
            # Format with actual decimals
            formatted = value / (10 ** decimals)
            amount_str = f"{formatted:.6f}".rstrip('0').rstrip('.')

            # Use symbol if available, otherwise use token address
            if symbol:
                return f"{amount_str} {symbol}"
            else:
                return f"{amount_str} ({token_short})"
        else:
            # Fall back to raw value
            if symbol:
                return f"{value} (raw) {symbol}"
            else:
                return f"{value} (raw, {token_short})"

    def decode_transaction_input(
        self,
        tx_input: str,
        function_data: Dict
    ) -> Optional[Dict[str, Any]]:
        """
        Decode transaction calldata using the function metadata.

        Args:
            tx_input: Transaction input data (hex string)
            function_data: Function metadata from ABI helper

        Returns:
            Dictionary mapping parameter names to decoded values
        """
        try:
            # Remove the function selector (first 4 bytes)
            calldata = tx_input[10:]  # Remove '0x' and 8 hex chars (4 bytes)

            # Get the full ABI entry for this function
            function_name = function_data['name']
            function_abi_entry = None
            for item in self.abi_helper.abi:
                if item.get('type') == 'function' and item.get('name') == function_name:
                    # Verify it's the right overload by checking inputs match
                    input_types = [self.abi_helper._param_abi_type_to_str(inp) for inp in item.get('inputs', [])]
                    sig = f"{function_name}({','.join(input_types)})"
                    if sig == function_data['signature']:
                        function_abi_entry = item
                        break

            if not function_abi_entry:
                logger.error(f"Could not find full ABI entry for {function_data['signature']}")
                return None

            # Get input types for decoding
            inputs = function_abi_entry.get('inputs', [])
            input_types = [self.abi_helper._param_abi_type_to_str(inp) for inp in inputs]
            input_names = function_data['param_names']

            # Decode the calldata
            decoded_values = self.w3.codec.decode(input_types, bytes.fromhex(calldata))

            # Create a dictionary mapping names to values
            result = {}
            for name, value, input_def in zip(input_names, decoded_values, inputs):
                # Handle tuple types - expand them into nested dictionaries
                if input_def.get('type', '').startswith('tuple'):
                    tuple_result = {}
                    components = input_def.get('components', [])

                    # value is a tuple/list of values
                    for comp_idx, component in enumerate(components):
                        comp_name = component.get('name', f'field_{comp_idx}')
                        comp_value = value[comp_idx] if comp_idx < len(value) else None

                        # Format the component value
                        if isinstance(comp_value, bytes):
                            tuple_result[comp_name] = '0x' + comp_value.hex()
                        elif isinstance(comp_value, list):
                            tuple_result[comp_name] = str(tuple(
                                ('0x' + v.hex() if isinstance(v, bytes) else v)
                                for v in comp_value
                            ))
                        else:
                            tuple_result[comp_name] = str(comp_value)

                    # If the tuple parameter has no name or is named "params", flatten it
                    if not name or name == 'params':
                        result.update(tuple_result)
                    else:
                        result[name] = tuple_result
                # Convert bytes and addresses to hex strings
                elif isinstance(value, bytes):
                    result[name] = '0x' + value.hex()
                elif isinstance(value, list):
                    # Format lists/arrays nicely
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

    def format_erc7730_value(
        self,
        value: Any,
        format_type: str,
        field_def: Dict[str, Any],
        decoded_input: Dict[str, Any]
    ) -> str:
        """
        Format a value according to its ERC-7730 format type.

        Args:
            value: The raw value to format
            format_type: The ERC-7730 format type (tokenAmount, addressName, unit, etc.)
            field_def: The field definition from ERC-7730
            decoded_input: All decoded inputs (for resolving tokenPath)

        Returns:
            Formatted string value
        """
        try:
            if format_type == "tokenAmount":
                # For tokenAmount, we need to apply decimals
                # Try to get token address from tokenPath parameter
                params = field_def.get('params', {})
                token_path = params.get('tokenPath', '')

                # Common token decimals (hardcoded for now)
                token_decimals = {
                    '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2': ('WETH', 18),  # WETH
                    '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48': ('USDC', 6),   # USDC
                    '0xdAC17F958D2ee523a2206206994597C13D831ec7': ('USDT', 6),   # USDT
                    '0x6B175474E89094C44Da98b954EedeAC495271d0F': ('DAI', 18),   # DAI
                }

                # Try to get token address from decoded input if tokenPath is specified
                token_address = None
                if token_path and token_path in decoded_input:
                    token_address = decoded_input[token_path]

                # Format the amount
                if isinstance(value, (int, str)):
                    amount = int(value) if isinstance(value, str) else value

                    # Get token info if we have it
                    if token_address and token_address in token_decimals:
                        symbol, decimals = token_decimals[token_address]
                        formatted_amount = amount / (10 ** decimals)
                        return f"{formatted_amount:.6f} {symbol}".rstrip('0').rstrip('.')
                    else:
                        # Use 18 decimals as default for unknown tokens
                        formatted_amount = amount / (10 ** 18)
                        if token_address:
                            return f"{formatted_amount:.6f} (token: {token_address[:10]}...)".rstrip('0').rstrip('.')
                        else:
                            return f"{formatted_amount:.6f}".rstrip('0').rstrip('.')

            elif format_type == "addressName":
                # For addresses, just show the address (ENS resolution would require async calls)
                if isinstance(value, str):
                    if len(value) == 42:  # Full address
                        return f"{value[:6]}...{value[-4:]}"
                    return value

            elif format_type == "unit":
                # For units (like fees), check if there's a decimals parameter
                params = field_def.get('params', {})
                decimals = params.get('decimals', 0)

                if isinstance(value, (int, str)):
                    amount = int(value) if isinstance(value, str) else value
                    if decimals > 0:
                        formatted = amount / (10 ** decimals)
                        return f"{formatted}%"
                    return f"{amount}%"

            elif format_type == "amount":
                # For ETH amounts (in wei)
                if isinstance(value, (int, str)):
                    amount = int(value) if isinstance(value, str) else value
                    eth_amount = amount / (10 ** 18)
                    return f"{eth_amount:.6f} ETH".rstrip('0').rstrip('.')

            # For raw or unknown formats, just return the value as-is
            return str(value)

        except Exception as e:
            logger.warning(f"Error formatting value {value} with format {format_type}: {e}")
            return str(value)

    def generate_clear_signing_audit(
        self,
        selector: str,
        decoded_transactions: List[Dict],
        erc7730_format: Dict,
        function_signature: str
    ) -> str:
        """
        Use AI to generate a clear signing audit report comparing decoded transactions
        with ERC-7730 format definitions.

        Args:
            selector: Function selector
            decoded_transactions: List of decoded transactions
            erc7730_format: ERC-7730 format definition for this selector
            function_signature: Function signature

        Returns:
            Audit report as markdown
        """
        try:
            client = OpenAI()
            logger.info(f"Generating clear signing audit for selector {selector}")

            # Prepare the prompt
            prompt = f"""You are a clear signing security auditor. Analyze whether the ERC-7730 clear signing metadata properly covers all important transaction parameters.

**Function:** {function_signature}
**Selector:** {selector}

**ERC-7730 Format Definition:**
```json
{json.dumps(erc7730_format, indent=2)}
```

**Decoded Transaction Samples:**

Each transaction includes:
- **decoded_input**: Parameters extracted from transaction calldata (what user intended to send)
- **receipt_logs**: Events emitted during transaction execution (what actually happened on-chain)
  - Transfer events show actual token movements
  - Approval events show permission grants
  - Other events show state changes

```json
{json.dumps(decoded_transactions, indent=2)}
```

**Important:** Pay special attention to receipt_logs! They reveal the ACTUAL token transfers and approvals that occurred.
Compare these with what the user sees in ERC-7730 to ensure nothing is hidden or misleading.

**Your Task:**
Write a concise audit report with the following sections. Use markdown formatting extensively for readability:

---

## 🔍 Clear Signing Audit Report

### 📋 Function: `{function_signature}`
**Selector:** `{selector}`

---

### 1️⃣ Intent Analysis

> **Declared Intent:** *"{erc7730_format.get('intent', 'N/A')}"*

Write one sentence assessing if this intent is accurate and clear.

---

### 2️⃣ Critical Issues

> 🔴 **CRITICAL** - Issues that could lead to users being deceived or losing funds

**Check for:**
- Token addresses shown are inverted/incorrect vs receipt_logs
- Amount values mapped to wrong tokens
- Critical parameters shown with misleading labels
- Hidden information in receipt_logs that should be shown
- Approvals not disclosed to users
- Mismatch between displayed intent and actual token movements in logs

List critical issues as bullet points. If none: **✅ No critical issues found**

---

### 3️⃣ Missing Parameters

> ⚠️ *Parameters present in ABI but NOT shown to users in ERC-7730*

| Parameter | Why It's Important | Risk Level |
|-----------|-------------------|:----------:|
| `parameter_name` | Brief explanation | 🔴 High / 🟡 Medium / 🟢 Low |

If no parameters are missing, write: **✅ All parameters are covered**

---

### 4️⃣ Display Issues

> 🟡 **Issues with how information is presented to users**

List display/formatting issues. Examples:
- Parameter labels unclear or confusing
- Missing context (e.g., recipient not clearly identified)
- Format issues (decimals, addresses, etc.)

If none: **✅ No display issues found**

---

### 5️⃣ Transaction Samples - What Users See vs What Actually Happens

Analyze up to 3 transactions (not all 5).

#### 📝 Transaction 1: `[hash]`

**User Intent (from ERC-7730):**
| Field | ✅ User Sees | ❌ Hidden/Missing |
|-------|-------------|-------------------|
| **Label from ERC-7730** | *Formatted value* | *What's not shown* |

**Actual Effects (from receipt_logs):**
| Event | Details | Disclosed? |
|-------|---------|:----------:|
| Transfer/Approval | Token, From, To, Amount | ✅ Yes / ❌ No |

Add 2-3 rows per table showing the most important fields.

Repeat for 2-3 more transactions.

---

### 6️⃣ Overall Assessment

| Metric | Score/Rating | Explanation |
|--------|--------------|-------------|
| **Coverage Score** | X/10 | Brief reasoning |
| **Security Risk** | 🔴 High / 🟡 Medium / 🟢 Low | One sentence why |

#### 💡 Key Recommendations
- Recommendation 1 (be specific)
- Recommendation 2 (be specific)
- Recommendation 3 (if needed)

---

**Use bold, italic, emojis, tables, blockquotes, and horizontal rules to make it visually appealing and easy to scan.**"""

            response = client.chat.completions.create(
                model="gpt-5-mini",
                messages=[{"role": "user", "content": prompt}]
            )

            audit_report = response.choices[0].message.content
            logger.info(f"Successfully generated audit report for {selector}")
            return audit_report

        except Exception as e:
            logger.error(f"Failed to generate audit report: {e}")
            return f"Error generating audit: {str(e)}"

    def analyze(
        self,
        erc7730_file: Path,
        abi_file: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        Main analysis function.

        Args:
            erc7730_file: Path to ERC-7730 JSON file
            abi_file: Optional path to ABI JSON file (if not provided, fetches from Etherscan)

        Returns:
            Analysis results
        """
        logger.info(f"Starting analysis of {erc7730_file}")

        # Parse ERC-7730 file
        erc7730_data = self.parse_erc7730_file(erc7730_file)

        # Extract contract deployments (address + chainId)
        deployments = self.get_contract_deployments(erc7730_data)
        if not deployments:
            logger.error("Could not extract contract deployments from ERC-7730 file")
            return {}

        # Get ABI - first check if it's embedded in the ERC-7730 file
        abi = erc7730_data.get('context', {}).get('contract', {}).get('abi')

        # Check if ABI is a URL string that needs to be fetched
        if abi and isinstance(abi, str):
            logger.info(f"ABI is a URL, fetching from: {abi}")
            try:
                response = requests.get(abi)
                response.raise_for_status()
                abi = response.json()
                logger.info(f"Successfully fetched ABI from URL ({len(abi)} entries)")
            except Exception as e:
                logger.error(f"Failed to fetch ABI from URL: {e}")
                abi = None

        if abi and isinstance(abi, list) and len(abi) > 0:
            logger.info(f"Using ABI from ERC-7730 file ({len(abi)} entries)")
        elif abi_file:
            logger.info(f"Loading ABI from file: {abi_file}")
            with open(abi_file, 'r') as f:
                abi = json.load(f)
        else:
            # Try to fetch ABI from first deployment
            first_deployment = deployments[0]
            abi = self.fetch_contract_abi(first_deployment['address'], first_deployment['chainId'])

        if not abi:
            logger.error("Could not obtain contract ABI")
            return {}

        # Initialize the ABI helper
        self.abi_helper = ABI(abi)
        logger.info("ABI helper initialized")

        # Extract selectors
        selectors = self.extract_selectors(erc7730_data)

        # Analyze each selector
        results = {
            'deployments': deployments,
            'context': erc7730_data.get('context', {}),
            'selectors': {}
        }

        # OPTIMIZATION: Fetch transactions for ALL selectors at once instead of one-by-one
        # This dramatically reduces API calls and execution time
        logger.info(f"\n{'='*60}")
        logger.info(f"Fetching transactions for all {len(selectors)} selectors at once...")
        logger.info(f"{'='*60}")

        all_selector_txs = {}
        used_deployment = None

        # Try each deployment until we find transactions
        for deployment in deployments:
            contract_address = deployment['address']
            chain_id = deployment['chainId']
            logger.info(f"Trying deployment: {contract_address} on chain {chain_id}")

            all_selector_txs = self.fetch_all_transactions_for_selectors(
                contract_address,
                selectors,
                chain_id,
                per_selector=5
            )

            # Check if we found any transactions
            if any(len(txs) > 0 for txs in all_selector_txs.values()):
                used_deployment = deployment
                logger.info(f"Using deployment {contract_address} on chain {chain_id}")
                break

        if not used_deployment:
            logger.warning("No transactions found across all deployments")
            return results

        # Now analyze each selector with its pre-fetched transactions
        for selector in selectors:
            logger.info(f"\n{'='*60}")
            logger.info(f"Analyzing selector: {selector}")
            logger.info(f"{'='*60}")

            # Get function metadata
            function_data = self.get_function_abi_by_selector(selector)
            if not function_data:
                logger.warning(f"Skipping selector {selector} - no matching ABI entry")
                continue

            function_name = function_data['name']
            logger.info(f"Function name: {function_name}")
            logger.info(f"Function signature: {function_data['signature']}")

            # Get the pre-fetched transactions for this selector
            transactions = all_selector_txs.get(selector.lower(), [])

            if not transactions:
                logger.warning(f"No transactions found for selector {selector}")
                continue

            logger.info(f"Found {len(transactions)} transactions for selector {selector}")

            # Decode each transaction
            decoded_txs = []
            for i, tx in enumerate(transactions, 1):
                logger.info(f"\nTransaction {i}/{len(transactions)}: {tx['hash']}")

                decoded = self.decode_transaction_input(tx['input'], function_data)
                if decoded:
                    tx_data = {
                        'hash': tx['hash'],
                        'block': tx['blockNumber'],
                        'timestamp': tx['timeStamp'],
                        'from': tx['from'],
                        'to': tx.get('to', ''),
                        'value': tx['value'],
                        'decoded_input': decoded
                    }

                    # Fetch transaction receipt and decode logs
                    logger.info(f"Fetching receipt for transaction {tx['hash']}")
                    receipt = self.fetch_transaction_receipt(tx['hash'], used_deployment['chainId'])

                    if receipt and receipt.get('logs'):
                        decoded_logs = []
                        for log in receipt['logs']:
                            decoded_log = self.decode_log_event(log, used_deployment['chainId'])
                            if decoded_log:
                                decoded_logs.append(decoded_log)

                        if decoded_logs:
                            tx_data['receipt_logs'] = decoded_logs
                            logger.info(f"Decoded {len(decoded_logs)} log events:")
                            for log in decoded_logs:
                                if log.get('event') == 'Transfer':
                                    logger.info(f"  Transfer: {log['value_formatted']} from {log['from'][:10]}... to {log['to'][:10]}...")
                                elif log.get('event') == 'Approval':
                                    logger.info(f"  Approval: {log['value_formatted']} from {log['owner'][:10]}... to {log['spender'][:10]}...")
                                else:
                                    logger.info(f"  {log.get('event', 'Unknown')}: {log.get('address', 'unknown')[:10]}...")

                    decoded_txs.append(tx_data)
                    time.sleep(0.2)  # Rate limiting for receipt fetches

                    logger.info(f"Decoded parameters:")
                    for param_name, param_value in decoded.items():
                        logger.info(f"  {param_name}: {param_value}")

            # Generate clear signing audit report
            erc7730_format = erc7730_data.get('display', {}).get('formats', {}).get(selector, {})
            audit_report = None

            if erc7730_format and decoded_txs:
                logger.info(f"\n{'='*60}")
                logger.info(f"Generating AI audit report for {selector}...")
                logger.info(f"{'='*60}")

                audit_report = self.generate_clear_signing_audit(
                    selector,
                    decoded_txs,
                    erc7730_format,
                    function_data['signature']
                )

                logger.info(f"\n{audit_report}\n")

            results['selectors'][selector] = {
                'function_name': function_name,
                'function_signature': function_data['signature'],
                'contract_address': used_deployment['address'],
                'chain_id': used_deployment['chainId'],
                'transactions': decoded_txs,
                'erc7730_format': erc7730_format,
                'audit_report': audit_report
            }

        logger.info(f"\n{'='*60}")
        logger.info("Analysis complete!")
        logger.info(f"{'='*60}")

        return results


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Analyze ERC-7730 clear signing files and fetch transaction data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables (can also be set in .env file):
  ERC7730_FILE          Path to ERC-7730 JSON file
  ABI_FILE              Path to contract ABI JSON file (optional)
  ETHERSCAN_API_KEY     Etherscan API key
  OPENAI_API_KEY        OpenAI API key for AI-powered audits (optional)
  LOOKBACK_DAYS         Number of days to look back (default: 20)

Priority: Command-line arguments > Environment variables > Defaults
        """
    )
    parser.add_argument(
        '--erc7730_file',
        type=Path,
        default=os.getenv('ERC7730_FILE'),
        help='Path to ERC-7730 JSON file (env: ERC7730_FILE)'
    )
    parser.add_argument(
        '--abi',
        type=Path,
        default=os.getenv('ABI_FILE'),
        help='Path to contract ABI JSON file (env: ABI_FILE, optional)'
    )
    parser.add_argument(
        '--api-key',
        default=os.getenv('ETHERSCAN_API_KEY'),
        help='Etherscan API key (env: ETHERSCAN_API_KEY)'
    )
    parser.add_argument(
        '--lookback-days',
        type=int,
        default=int(os.getenv('LOOKBACK_DAYS') or '20'),
        help='Number of days to look back for transaction history (env: LOOKBACK_DAYS, default: 20)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        default=False,
        help='Enable debug mode to log to file (default: False, no logging to file or console)'
    )

    args = parser.parse_args()

    # Configure logging based on --debug flag
    if args.debug:
        # Create output directory for log file
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)

        # Enable file logging when debug is True
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(output_dir / 'analyze_7730.log')
            ]
        )
    else:
        # Disable logging output when debug is False
        logging.basicConfig(
            level=logging.CRITICAL,  # Only show critical errors
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.NullHandler()  # No output
            ]
        )

    # Validate required arguments
    if not args.erc7730_file:
        parser.error("--erc7730_file is required (or set ERC7730_FILE environment variable)")

    if not args.api_key:
        parser.error("--api-key is required (or set ETHERSCAN_API_KEY environment variable)")

    # Initialize analyzer
    analyzer = ERC7730Analyzer(
        etherscan_api_key=args.api_key,
        lookback_days=args.lookback_days
    )

    # Run analysis
    results = analyzer.analyze(args.erc7730_file, args.abi)

    # Always create output directory and save results
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    logger.info(f"Saving results to {output_dir}")

    # Generate summary file only (no individual audit files)
    context_id = results.get('context', {}).get('$id', 'unknown').replace(' ', '_')
    summary_file = output_dir / f"SUMMARY_{context_id}.md"
    logger.info(f"Generating summary file at {summary_file}")
    generate_summary_file(results, analyzer, summary_file)

    # Also save JSON results for programmatic access
    json_output = output_dir / f"results_{context_id}.json"
    logger.info(f"Saving JSON results to {json_output}")
    with open(json_output, 'w') as f:
        json.dump(results, f, indent=2)

    logger.info(f"\n{'='*60}")
    logger.info(f"Analysis complete!")
    logger.info(f"Summary report: {summary_file}")
    logger.info(f"JSON results: {json_output}")
    logger.info(f"{'='*60}\n")

    return results


def extract_risk_level(audit_report: str) -> str:
    """Extract risk level from AI audit report."""
    import re
    # Look for patterns like "🔴 High", "🟡 Medium", "🟢 Low", or "High/Medium/Low"
    high_pattern = r'(🔴|High)'
    medium_pattern = r'(🟡|Medium)'
    low_pattern = r'(🟢|Low)'

    if re.search(high_pattern, audit_report, re.IGNORECASE):
        return 'High'
    elif re.search(medium_pattern, audit_report, re.IGNORECASE):
        return 'Medium'
    elif re.search(low_pattern, audit_report, re.IGNORECASE):
        return 'Low'
    return 'Unknown'


def extract_coverage_score(audit_report: str) -> str:
    """Extract coverage score from AI audit report."""
    import re
    # Look for patterns like "Coverage Score: 7/10" or "7/10"
    match = re.search(r'Coverage Score[:\s]*(\d+/10)', audit_report, re.IGNORECASE)
    if match:
        return match.group(1)
    return 'N/A'


def extract_critical_issues(audit_report: str) -> list:
    """Extract critical issues from AI audit report."""
    import re
    critical = []
    # Look for the Critical Issues section
    crit_section = re.search(r'2️⃣ Critical Issues(.*?)(?=3️⃣|---)', audit_report, re.DOTALL | re.IGNORECASE)
    if crit_section:
        section_text = crit_section.group(1)
        # Skip blockquote lines (start with >)
        # Extract only bullet points (lines starting with - or *)
        for line in section_text.split('\n'):
            line = line.strip()
            if line.startswith('-') or line.startswith('*'):
                # Remove the bullet marker
                issue_text = re.sub(r'^[-*]\s+', '', line).strip()
                # Filter out "no issues" indicators - expanded list
                no_issue_indicators = [
                    '✅',
                    'no critical issues',
                    'none observed',
                    'if none:',
                    'none:',
                    'not observed',
                ]
                # Check if line contains any "no issue" indicator
                is_no_issue = any(indicator in issue_text.lower() for indicator in no_issue_indicators)

                if issue_text and not is_no_issue:
                    critical.append(issue_text)
    return critical


def extract_missing_parameters(audit_report: str) -> list:
    """Extract missing parameters from AI audit report."""
    import re
    missing = []
    # Look for parameter names in the missing parameters table
    # Pattern: | `parameter_name` | ... | ... |
    matches = re.findall(r'\|\s*`([^`]+)`\s*\|[^|]+\|[^|]+\|', audit_report)
    if matches:
        missing.extend(matches)
    return missing


def extract_display_issues(audit_report: str) -> list:
    """Extract display issues from AI audit report."""
    import re
    display = []
    # Look for the Display Issues section
    display_section = re.search(r'4️⃣ Display Issues(.*?)(?=5️⃣|---)', audit_report, re.DOTALL | re.IGNORECASE)
    if display_section:
        section_text = display_section.group(1)
        # Extract only bullet points (lines starting with - or *)
        for line in section_text.split('\n'):
            line = line.strip()
            if line.startswith('-') or line.startswith('*'):
                # Remove the bullet marker
                issue_text = re.sub(r'^[-*]\s+', '', line).strip()
                # Filter out "no issues" indicators
                no_issue_indicators = [
                    '✅',
                    'no display issues',
                    'none observed',
                    'if none:',
                    'none:',
                    'not observed',
                ]
                is_no_issue = any(indicator in issue_text.lower() for indicator in no_issue_indicators)

                if issue_text and not is_no_issue:
                    display.append(issue_text)
    return display


def extract_recommendations(audit_report: str) -> list:
    """Extract recommendations from AI audit report."""
    import re
    recommendations = []
    # Look for the recommendations section
    rec_section = re.search(r'Key Recommendations[:\s]*(.*?)(?=---|\Z)', audit_report, re.DOTALL | re.IGNORECASE)
    if rec_section:
        # Extract bullet points
        bullets = re.findall(r'[-*]\s+(.+)', rec_section.group(1))
        recommendations.extend([b.strip() for b in bullets if b.strip()])
    return recommendations[:3]  # Limit to 3


def generate_summary_file(results: Dict, analyzer: 'ERC7730Analyzer', summary_file: Path):
    """
    Generate a single comprehensive report file with summary table and detailed sections.

    Args:
        results: Analysis results dictionary
        audit_dir: Directory containing audit reports
        summary_file: Path to summary file
    """
    # Get contract info
    deployments = results.get('deployments', [])
    context_id = results.get('context', {}).get('$id', 'N/A')

    # Get unique chain IDs
    chain_ids = sorted(set(d['chainId'] for d in deployments))
    chain_ids_str = ', '.join(str(cid) for cid in chain_ids)

    report = f"""# 📊 Clear Signing Audit Report

**Contract ID:** {context_id}
**Total Deployments Analyzed:** {len(deployments)}
**Chain IDs:** {chain_ids_str}

---

## Summary Table

"""

    critical_issues_list = []
    major_issues_list = []
    minor_issues_list = []
    no_issues_list = []

    for selector, selector_data in results.get('selectors', {}).items():
        function_name = selector_data.get('function_name', 'unknown')
        audit_file = f"audit_{selector}_{function_name}.md"
        audit_report = selector_data.get('audit_report', '')

        # Extract coverage and missing parameters info
        transactions = selector_data.get('transactions', [])
        if transactions:
            tx = transactions[0]
            decoded_input = tx.get('decoded_input', {})
            erc7730_format = selector_data.get('erc7730_format', {})
            erc7730_fields = {field.get('path', '').replace('params.', ''): field
                             for field in (erc7730_format.get('fields') or [])}
            excluded_fields = [e.replace('params.', '') for e in (erc7730_format.get('excluded') or [])]

            total_params = len(decoded_input)
            shown_count = len([p for p in decoded_input.keys() if p in erc7730_fields])
            excluded_count = len([p for p in decoded_input.keys() if p in excluded_fields])
            missing_count = total_params - shown_count - excluded_count
            coverage_pct = (shown_count / total_params * 100) if total_params > 0 else 0

            missing_params = [p for p in decoded_input.keys()
                            if p not in erc7730_fields and p not in excluded_fields]

            # Extract key information from AI audit report
            if audit_report:
                risk_level = extract_risk_level(audit_report)
                coverage_score = extract_coverage_score(audit_report)
                critical_issues_from_ai = extract_critical_issues(audit_report)
                ai_missing_params = extract_missing_parameters(audit_report)
                display_issues_from_ai = extract_display_issues(audit_report)
                recommendations = extract_recommendations(audit_report)
            else:
                risk_level = 'Unknown'
                coverage_score = 'N/A'
                critical_issues_from_ai = []
                ai_missing_params = []
                display_issues_from_ai = []
                recommendations = []

            issue_data = {
                'selector': selector,
                'function_name': function_name,
                'audit_file': audit_file,
                'coverage_pct': coverage_pct,
                'missing_count': missing_count,
                'missing_params': missing_params,
                'shown_count': shown_count,
                'excluded_count': excluded_count,
                'total_params': total_params,
                'risk_level': risk_level,
                'coverage_score': coverage_score,
                'critical_issues': critical_issues_from_ai,
                'ai_missing_params': ai_missing_params,
                'display_issues': display_issues_from_ai,
                'recommendations': recommendations
            }

            # Categorize by severity - only use AI critical issues if they exist
            has_ai_critical = len(critical_issues_from_ai) > 0
            has_missing_params = len(ai_missing_params) > 0

            # Critical = Has actual critical issues from AI (inverted tokens, misleading data, etc.)
            if has_ai_critical:
                critical_issues_list.append(issue_data)
            # Major = Has missing parameters with medium/high risk OR multiple display issues
            elif has_missing_params or len(display_issues_from_ai) > 2:
                major_issues_list.append(issue_data)
            # Minor = Only has display issues or low coverage
            elif len(display_issues_from_ai) > 0 or coverage_pct < 100:
                minor_issues_list.append(issue_data)
            else:
                no_issues_list.append(issue_data)

    # Build summary table
    all_issues = critical_issues_list + major_issues_list + minor_issues_list + no_issues_list

    report += "| Function | Selector | Severity | Issues | Coverage | Link |\n"
    report += "|----------|----------|----------|--------|----------|------|\n"

    for issue in all_issues:
        # Determine severity and description based on what issues exist
        has_critical = len(issue['critical_issues']) > 0
        has_missing = len(issue['ai_missing_params']) > 0
        has_display = len(issue['display_issues']) > 0

        # Priority: Show the highest severity issue type that exists
        if has_critical:
            severity = "🔴 Critical"
            quick_desc = issue['critical_issues'][0][:60] + "..." if len(issue['critical_issues'][0]) > 60 else issue['critical_issues'][0]
        elif has_missing:
            severity = "🟡 Major"
            quick_desc = f"Missing: {', '.join(issue['ai_missing_params'][:2])}"
            if len(issue['ai_missing_params']) > 2:
                quick_desc += f" (+{len(issue['ai_missing_params']) - 2} more)"
        elif has_display:
            severity = "🟢 Minor"
            quick_desc = issue['display_issues'][0][:60] + "..." if len(issue['display_issues'][0]) > 60 else issue['display_issues'][0]
        else:
            severity = "✅ None"
            quick_desc = "Complete coverage"

        report += f"| `{issue['function_name']}` | `{issue['selector']}` | {severity} | {quick_desc} | {issue['coverage_pct']:.0f}% | [View](#selector-{issue['selector'][2:]}) |\n"

    report += "\n---\n\n## 📈 Statistics\n\n"
    report += f"| Metric | Count |\n"
    report += f"|--------|-------|\n"
    report += f"| 🔴 Critical | {len(critical_issues_list)} |\n"
    report += f"| 🟡 Major | {len(major_issues_list)} |\n"
    report += f"| 🟢 Minor | {len(minor_issues_list)} |\n"
    report += f"| ✅ No Issues | {len(no_issues_list)} |\n"
    report += f"| **Total** | **{len(all_issues)}** |\n\n"

    report += "---\n\n# Detailed Analysis\n\n"

    # Now add detailed sections for each selector
    for selector, selector_data in results.get('selectors', {}).items():
        function_name = selector_data.get('function_name', 'unknown')
        function_sig = selector_data.get('function_signature', 'N/A')

        contract_addr = selector_data.get('contract_address', 'N/A')
        chain_id = selector_data.get('chain_id', 'N/A')
        report += f"## <a id=\"selector-{selector[2:]}\"></a> {function_name}\n\n"
        report += f"**Selector:** `{selector}` | **Signature:** `{function_sig}`\n\n"
        report += f"**Contract Address:** `{contract_addr}` | **Chain ID:** {chain_id}\n\n"

        # Add ERC-7730 format at the top
        report += "<details>\n<summary><b>📋 ERC-7730 Format Definition</b></summary>\n\n"
        report += "```json\n"
        report += json.dumps(selector_data.get('erc7730_format', {}), indent=2)
        report += "\n```\n\n</details>\n\n"

        # Add side-by-side comparison (collapsible)
        transactions = selector_data.get('transactions', [])
        if transactions:
            report += "<details>\n<summary><b>🔍 Side-by-Side Comparison (ABI vs ERC-7730)</b></summary>\n\n"

            for i, tx in enumerate(transactions, 1):
                report += f"### Transaction {i}: `{tx['hash']}`\n\n"
                report += f"**Block:** {tx['block']} | **From:** {tx['from']} | **Value:** {tx['value']}\n\n"

                # Create comparison table
                report += "| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |\n"
                report += "|-----------|-------------------|----------------------|\n"

                decoded_input = tx.get('decoded_input', {})
                erc7730_format = selector_data.get('erc7730_format', {})
                erc7730_fields = {field.get('path', '').replace('params.', ''): field
                                 for field in (erc7730_format.get('fields') or [])}
                required_fields = [r.replace('params.', '') for r in (erc7730_format.get('required') or [])]
                excluded_fields = [e.replace('params.', '') for e in (erc7730_format.get('excluded') or [])]

                for param_name, param_value in decoded_input.items():
                    # Format ABI value
                    if isinstance(param_value, str) and len(param_value) > 66:
                        abi_display = f"`{param_value[:32]}...{param_value[-32:]}`"
                    else:
                        abi_display = f"`{param_value}`"

                    # Format ERC-7730 value
                    if param_name in erc7730_fields:
                        field_def = erc7730_fields[param_name]
                        label = field_def.get('label', param_name)
                        format_type = field_def.get('format', 'raw')
                        # Use the analyzer instance to format
                        # Note: This requires passing analyzer instance to this function
                        erc7730_display = f"**{label}**<br/>Format: `{format_type}`"
                    elif param_name in excluded_fields:
                        erc7730_display = "❌ Hidden"
                    else:
                        erc7730_display = "⚠️ Not shown"

                    report += f"| `{param_name}` | {abi_display} | {erc7730_display} |\n"

                report += "\n"

                # Add receipt logs if available
                receipt_logs = tx.get('receipt_logs', [])
                if receipt_logs:
                    report += "#### 📋 Transaction Events (from receipt)\n\n"
                    report += "| Event | Token | Details | Amount |\n"
                    report += "|-------|-------|---------|--------|\n"

                    for log in receipt_logs:
                        event_type = log.get('event', 'Unknown')
                        if event_type == 'Transfer':
                            token = log.get('token', 'unknown')[:10] + '...'
                            from_addr = log.get('from', 'unknown')[:10] + '...'
                            to_addr = log.get('to', 'unknown')[:10] + '...'
                            amount = log.get('value_formatted', 'N/A')
                            report += f"| 🔄 Transfer | `{token}` | From: `{from_addr}`<br/>To: `{to_addr}` | {amount} |\n"
                        elif event_type == 'Approval':
                            token = log.get('token', 'unknown')[:10] + '...'
                            owner = log.get('owner', 'unknown')[:10] + '...'
                            spender = log.get('spender', 'unknown')[:10] + '...'
                            amount = log.get('value_formatted', 'N/A')
                            report += f"| ✅ Approval | `{token}` | Owner: `{owner}`<br/>Spender: `{spender}` | {amount} |\n"
                        else:
                            address = log.get('address', 'unknown')[:10] + '...'
                            signature = log.get('signature', 'N/A')[:18] + '...'
                            report += f"| ❓ {event_type} | `{address}` | Signature: `{signature}` | - |\n"

                    report += "\n"

            report += "</details>\n\n"

        # Add AI audit report
        audit_report_content = selector_data.get('audit_report', '')
        if audit_report_content:
            report += "---\n\n"
            report += audit_report_content
            report += "\n\n---\n\n"
        else:
            report += "---\n\n*No audit report available for this selector.*\n\n---\n\n"

    # Write report file
    with open(summary_file, 'w') as f:
        f.write(report)

    logger.info(f"Comprehensive report saved to {summary_file}")


if __name__ == '__main__':
    main()


