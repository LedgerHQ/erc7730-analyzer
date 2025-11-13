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
from pathlib import Path
import requests
from web3 import Web3

from .raw_tx_parser import load_raw_transactions, group_transactions_by_selector
from .abi import ABI

logger = logging.getLogger(__name__)


# Blockscout API endpoints for chains that don't use Etherscan
# Note: These use Blockscout v2 API with different structure than Etherscan
BLOCKSCOUT_URLS = {
    44787: 'https://celo-alfajores.blockscout.com',  # Celo Alfajores Testnet
    42220: 'https://celo.blockscout.com',             # Celo Mainnet
    100: 'https://gnosis.blockscout.com',             # Gnosis Chain
    # Add more as needed
}


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
            response = requests.get(base_url, params=params)
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
            response = requests.get(f"{base_url}/api/v2/stats")
            response.raise_for_status()
            data = response.json()
            return data
        except Exception as e:
            logger.debug(f"Failed to fetch Blockscout v2 stats: {e}")
            return None

    def _fetch_blockscout_v2_transactions(
        self,
        contract_address: str,
        chain_id: int,
        filter_type: str = "to"
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Fetch transactions from Blockscout v2 API.

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
                    response = requests.get(url, params=next_page_params)
                else:
                    response = requests.get(url, params=params)

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
            response = requests.get(base_url, params=params)
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

    def fetch_all_transactions_for_selectors(
        self,
        contract_address: str,
        selectors: List[str],
        chain_id: int = 1,
        per_selector: int = 5,
        window_size: int = 10000,
        page_size: int = 1000,
        max_retries: int = 3,
        payable_selectors: set = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Efficiently fetch transactions for MULTIPLE selectors at once.
        Fetches each Etherscan page ONCE and distributes matches to all selectors.

        For payable functions, tries to fetch diverse transaction samples:
        - At least 1 transaction with msg.value > 0 (native ETH transfer)
        - At least 1 transaction with msg.value = 0 (ERC20 transfer)
        If both types aren't available, uses whatever transactions are found.

        Args:
            contract_address: Contract address
            selectors: List of function selectors (4-byte hex)
            chain_id: Chain ID for the contract
            per_selector: Number of transactions to fetch per selector
            window_size: Number of blocks per window
            page_size: Number of transactions per page
            max_retries: Maximum retry attempts per request
            payable_selectors: Set of selectors that are payable functions

        Returns:
            Dictionary mapping selector -> list of transaction dictionaries
        """
        if not self.etherscan_api_key:
            logger.warning("No block explorer API key provided, cannot fetch transactions")
            return {s: [] for s in selectors}

        if payable_selectors is None:
            payable_selectors = set()

        # Ensure chain_id is an int for dictionary lookups
        chain_id = int(chain_id)

        # Try Etherscan first, then Blockscout as fallback
        for api_attempt, use_blockscout in enumerate([False, True]):
            # Skip Blockscout attempt if chain doesn't have Blockscout support
            if use_blockscout and chain_id not in BLOCKSCOUT_URLS:
                continue

            api_name = "Blockscout" if use_blockscout else "Etherscan"
            if api_attempt > 0:
                logger.info(f"Switching to {api_name} API for chain {chain_id}")

            logger.info(f"Fetching transactions for {len(selectors)} selectors on chain {chain_id} using {api_name}")
            if payable_selectors:
                logger.info(f"  - {len(payable_selectors)} payable function(s) - will fetch diverse samples")

            result = self._fetch_transactions_with_api(
                contract_address,
                selectors,
                chain_id,
                per_selector,
                window_size,
                page_size,
                max_retries,
                payable_selectors,
                use_blockscout
            )

            # Check if we got any transactions
            if any(len(txs) > 0 for txs in result.values()):
                logger.info(f"✓ Successfully found transactions using {api_name}")
                self.api_type_per_chain[chain_id] = api_name
                return result

            # No transactions found with this API
            logger.warning(f"No transactions found using {api_name} for chain {chain_id}")

            # If this was Etherscan and Blockscout is available, try Blockscout next
            if not use_blockscout:
                if chain_id in BLOCKSCOUT_URLS:
                    logger.info(f"Chain {chain_id} has Blockscout support - will try Blockscout next")
                    continue  # Try next iteration (Blockscout)
                else:
                    logger.info(f"Chain {chain_id} has no Blockscout support - giving up")
                    break
            else:
                # This was Blockscout and it also failed
                logger.info(f"Both Etherscan and Blockscout failed for chain {chain_id}")
                break

        logger.warning(f"No transactions found for any selector on chain {chain_id}")
        return {s.lower(): [] for s in selectors}

    def integrate_manual_transactions(
        self,
        fetched_txs: Dict[str, List[Dict[str, Any]]],
        raw_txs_file: Optional[Path],
        contract_address: str,
        abi: List[Dict[str, Any]],
        chain_id: int = 1
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Integrate manually provided raw transactions with fetched transactions.

        Manual transactions are parsed, decoded, and merged with fetched transactions.
        They are added to the beginning of the transaction list for each selector.

        Args:
            fetched_txs: Dictionary of fetched transactions (selector -> list of txs)
            raw_txs_file: Path to JSON file with raw transactions (optional)
            contract_address: Contract address to verify against
            abi: Contract ABI for decoding
            chain_id: Chain ID

        Returns:
            Combined dictionary of transactions with manual txs prepended
        """
        if not raw_txs_file or not raw_txs_file.exists():
            logger.info("No manual transactions file provided")
            return fetched_txs

        logger.info(f"Loading manual transactions from {raw_txs_file}")

        # Load and parse raw transactions
        parsed_manual_txs = load_raw_transactions(raw_txs_file)

        if not parsed_manual_txs:
            logger.warning("No valid manual transactions found in file")
            return fetched_txs

        # Group by selector
        manual_by_selector = group_transactions_by_selector(parsed_manual_txs)

        logger.info(f"Found {len(parsed_manual_txs)} manual transaction(s) for {len(manual_by_selector)} selector(s)")

        # Create ABI helper for decoding
        abi_helper = ABI(abi)

        # Convert manual transactions to the format expected by the analyzer
        result = {k: list(v) for k, v in fetched_txs.items()}  # Copy fetched txs

        for selector, manual_txs in manual_by_selector.items():
            selector_lower = selector.lower()

            # Filter manual transactions for this contract only
            contract_manual_txs = [
                tx for tx in manual_txs
                if tx.get('to', '').lower() == contract_address.lower()
            ]

            if not contract_manual_txs:
                logger.debug(f"No manual transactions for contract {contract_address} with selector {selector}")
                continue

            logger.info(f"Processing {len(contract_manual_txs)} manual transaction(s) for selector {selector}")

            # Convert to analyzer format and decode
            converted_txs = []
            for manual_tx in contract_manual_txs:
                # Create transaction dict in Etherscan format
                tx_dict = {
                    'hash': manual_tx.get('tx_hash', 'manual_tx'),
                    'from': '0x0000000000000000000000000000000000000000',  # Unknown sender
                    'to': manual_tx['to'],
                    'value': str(manual_tx['value']),
                    'input': manual_tx['input'],
                    'blockNumber': '0',
                    'timeStamp': '0',
                    'source': 'manual',
                    'description': manual_tx.get('description', '')
                }

                # Get function data from ABI for this selector
                function_data = abi_helper.find_function_by_selector(selector)

                if not function_data:
                    logger.warning(f"No function found in ABI for selector {selector}")
                    continue

                # Decode the transaction input
                decoded_input = self.decode_transaction_input(
                    manual_tx['input'],
                    function_data,
                    abi_helper
                )

                if decoded_input:
                    tx_dict['decoded_input'] = decoded_input
                    logger.debug(f"✓ Decoded manual TX for selector {selector}")
                else:
                    logger.warning(f"✗ Failed to decode manual TX for selector {selector}")
                    continue

                # Try to fetch receipt if we have a real tx hash
                if manual_tx.get('tx_hash') and manual_tx['tx_hash'].startswith('0x'):
                    logger.info(f"Attempting to fetch receipt for manual TX {manual_tx['tx_hash']}")
                    receipt = self.fetch_transaction_receipt(
                        manual_tx['tx_hash'],
                        chain_id
                    )
                    if receipt:
                        tx_dict['receipt_logs'] = receipt.get('receipt_logs', [])
                        logger.info(f"✓ Fetched receipt with {len(receipt.get('receipt_logs', []))} logs")

                converted_txs.append(tx_dict)

            # Merge with fetched transactions (manual txs first)
            if selector_lower not in result:
                result[selector_lower] = []

            result[selector_lower] = converted_txs + result[selector_lower]
            logger.info(f"✓ Added {len(converted_txs)} manual transaction(s) to selector {selector} "
                       f"(total: {len(result[selector_lower])})")

        return result

    def _fetch_transactions_blockscout_v2(
        self,
        contract_address: str,
        selectors: List[str],
        chain_id: int,
        per_selector: int,
        payable_selectors: set
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Fetch transactions using Blockscout v2 API.

        Args:
            contract_address: Contract address
            selectors: List of function selectors
            chain_id: Chain ID
            per_selector: Number of transactions per selector
            payable_selectors: Set of payable selectors

        Returns:
            Dictionary mapping selector -> list of transactions
        """
        chain_id = int(chain_id)

        # Initialize result dict with lowercase selectors
        selector_txs = {s.lower(): [] for s in selectors}
        selector_wanted = {s.lower(): per_selector for s in selectors}

        # For payable selectors, track native ETH and ERC20 transactions separately
        selector_native_txs = {s.lower(): [] for s in payable_selectors}
        selector_erc20_txs = {s.lower(): [] for s in payable_selectors}

        # Fetch transactions from Blockscout v2
        blockscout_txs = self._fetch_blockscout_v2_transactions(
            contract_address,
            chain_id,
            filter_type="to"
        )

        if not blockscout_txs:
            logger.warning("No transactions found from Blockscout v2 API")
            return selector_txs

        total_txs_scanned = 0

        # Process each transaction and distribute to selectors
        for tx in blockscout_txs:
            # Convert to Etherscan format
            etherscan_tx = self._convert_blockscout_v2_to_etherscan_format(tx)

            # Skip failed transactions
            if etherscan_tx.get('isError') != '0':
                continue

            inp = etherscan_tx.get('input', '')
            if len(inp) < 10:
                continue

            total_txs_scanned += 1

            # Check if this transaction matches any selector we're looking for
            tx_selector = inp[:10].lower()
            if tx_selector in selector_txs:
                # For payable selectors, categorize by value
                if tx_selector in payable_selectors:
                    native_count = len(selector_native_txs[tx_selector])
                    erc20_count = len(selector_erc20_txs[tx_selector])
                    total_count = native_count + erc20_count

                    # Skip if we already have enough
                    if total_count >= selector_wanted[tx_selector]:
                        continue

                    # Determine if this is a native ETH or ERC20 transaction
                    tx_value = int(etherscan_tx.get('value', '0'))
                    is_native = tx_value > 0

                    if is_native:
                        selector_native_txs[tx_selector].append(etherscan_tx)
                        logger.debug(f"Found native ETH tx for {tx_selector}: {etherscan_tx.get('hash')} (value: {tx_value})")
                    else:
                        selector_erc20_txs[tx_selector].append(etherscan_tx)
                        logger.debug(f"Found ERC20 tx for {tx_selector}: {etherscan_tx.get('hash')}")
                else:
                    # For non-payable selectors, just add normally
                    if len(selector_txs[tx_selector]) < selector_wanted[tx_selector]:
                        selector_txs[tx_selector].append(etherscan_tx)
                        logger.debug(f"Found match for {tx_selector}: {etherscan_tx.get('hash')}")

        # Combine native and ERC20 transactions for payable selectors
        for sel in payable_selectors:
            native_txs = selector_native_txs[sel]
            erc20_txs = selector_erc20_txs[sel]

            # Strategy: Try to get at least 1 of each type if possible
            combined = []

            # First, add at least 1 native if available
            if native_txs:
                combined.append(native_txs[0])

            # Then, add at least 1 ERC20 if available
            if erc20_txs:
                combined.append(erc20_txs[0])

            # Fill remaining slots, alternating between native and ERC20
            remaining_slots = selector_wanted[sel] - len(combined)
            native_idx = 1
            erc20_idx = 1

            while remaining_slots > 0:
                added = False

                # Try to add a native tx
                if native_idx < len(native_txs):
                    combined.append(native_txs[native_idx])
                    native_idx += 1
                    remaining_slots -= 1
                    added = True

                # Try to add an ERC20 tx
                if remaining_slots > 0 and erc20_idx < len(erc20_txs):
                    combined.append(erc20_txs[erc20_idx])
                    erc20_idx += 1
                    remaining_slots -= 1
                    added = True

                # If we couldn't add anything, break
                if not added:
                    break

            selector_txs[sel] = combined

        logger.info(f"Scanned {total_txs_scanned} total transactions from Blockscout v2")
        for sel, tx_list in selector_txs.items():
            if sel in payable_selectors:
                native_count = sum(1 for tx in tx_list if int(tx.get('value', '0')) > 0)
                erc20_count = len(tx_list) - native_count
                logger.info(f"Selector {sel} (payable): found {len(tx_list)}/{selector_wanted[sel]} transactions ({native_count} native ETH, {erc20_count} ERC20)")
            else:
                logger.info(f"Selector {sel}: found {len(tx_list)}/{selector_wanted[sel]} transactions")

        return selector_txs

    def _fetch_transactions_with_api(
        self,
        contract_address: str,
        selectors: List[str],
        chain_id: int,
        per_selector: int,
        window_size: int,
        page_size: int,
        max_retries: int,
        payable_selectors: set,
        use_blockscout: bool = False
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Internal method to fetch transactions using either Etherscan or Blockscout API.

        Returns:
            Dictionary mapping selector -> list of transactions
        """
        chain_id = int(chain_id)  # Ensure it's an int

        # If using Blockscout v2, use the new API
        if use_blockscout and chain_id in BLOCKSCOUT_URLS:
            return self._fetch_transactions_blockscout_v2(
                contract_address,
                selectors,
                chain_id,
                per_selector,
                payable_selectors
            )

        # Initialize result dict with lowercase selectors
        selector_txs = {s.lower(): [] for s in selectors}
        selector_wanted = {s.lower(): per_selector for s in selectors}

        # For payable selectors, track native ETH and ERC20 transactions separately
        selector_native_txs = {s.lower(): [] for s in payable_selectors}
        selector_erc20_txs = {s.lower(): [] for s in payable_selectors}

        # Get block range for the lookback period
        now = int(time.time())
        lookback_ago = now - self.lookback_days * 24 * 60 * 60
        logger.info(f"Looking back {self.lookback_days} days for transaction history")

        start_block = self.get_block_by_timestamp(lookback_ago, "after", chain_id, use_blockscout)
        end_block = self.get_block_by_timestamp(now, "before", chain_id, use_blockscout)

        if not start_block or not end_block:
            logger.warning("Could not determine block range, fetching current block number")
            # Try to get current block number from the API
            current_block = self._get_current_block_number(chain_id, use_blockscout)
            if current_block:
                end_block = current_block
                # Look back by reasonable number of blocks (assuming ~5 sec blocks, 20 days = ~345k blocks)
                blocks_to_lookback = self.lookback_days * 24 * 60 * 12  # 12 blocks per minute
                start_block = max(0, end_block - blocks_to_lookback)
                logger.info(f"Using current block {current_block}, looking back {blocks_to_lookback} blocks")
            else:
                logger.warning("Could not get current block, using conservative fallback")
                # Very conservative fallback - assume chain has at most 30M blocks
                end_block = 30000000
                start_block = max(0, end_block - 2500000)

        logger.info(f"Searching for transactions between blocks {start_block} and {end_block}")

        base_url = self._get_api_base_url(chain_id, use_blockscout)
        max_pages = 10000 // page_size
        total_txs_scanned = 0
        consecutive_failures = 0  # Track consecutive API failures for early abort
        MAX_CONSECUTIVE_FAILURES = 5  # Abort after 5 consecutive failures

        def all_done() -> bool:
            """Check if we have enough samples for all selectors"""
            for sel, txs in selector_txs.items():
                if sel in payable_selectors:
                    # For payable selectors, check if we have diverse samples
                    # We want at least 1 native and 1 ERC20, if possible
                    native_count = len(selector_native_txs[sel])
                    erc20_count = len(selector_erc20_txs[sel])
                    total_needed = selector_wanted[sel]

                    # Ideal: at least 1 of each type, and total meets requirement
                    has_enough = (native_count + erc20_count) >= total_needed
                    if not has_enough:
                        return False
                else:
                    # For non-payable selectors, just check total count
                    if len(txs) < selector_wanted[sel]:
                        return False
            return True

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
                }

                # Blockscout doesn't require API key
                if not use_blockscout:
                    params['apikey'] = self.etherscan_api_key

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
                                consecutive_failures = 0  # Reset on successful response (even if no txs)
                                break
                            if 'Result window is too large' in data.get('message', ''):
                                logger.info(f"Hit page limit at page {page}, moving to next window")
                                txs = []
                                consecutive_failures = 0
                                break
                            # NOTOK or other errors
                            consecutive_failures += 1
                            logger.warning(f"API warning: {data.get('message', 'Unknown error')} (failure {consecutive_failures}/{MAX_CONSECUTIVE_FAILURES})")

                            # Early abort if too many consecutive failures
                            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                                logger.warning(f"Aborting after {consecutive_failures} consecutive API failures - API likely not supported for chain {chain_id}")
                                return selector_txs

                            txs = []
                            break

                        txs = data['result']
                        consecutive_failures = 0  # Reset on success
                        break
                    except Exception as e:
                        consecutive_failures += 1
                        if attempt + 1 == max_retries:
                            logger.error(f"Failed to fetch transactions after {max_retries} attempts: {e}")

                            # Check if we should abort entirely
                            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                                logger.warning(f"Aborting due to repeated failures")
                                return selector_txs

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
                    if tx_selector in selector_txs:
                        # For payable selectors, categorize by value
                        if tx_selector in payable_selectors:
                            native_count = len(selector_native_txs[tx_selector])
                            erc20_count = len(selector_erc20_txs[tx_selector])
                            total_count = native_count + erc20_count

                            # Skip if we already have enough
                            if total_count >= selector_wanted[tx_selector]:
                                continue

                            # Determine if this is a native ETH or ERC20 transaction
                            tx_value = int(tx.get('value', '0'))
                            is_native = tx_value > 0

                            if is_native:
                                selector_native_txs[tx_selector].append(tx)
                                logger.debug(f"Found native ETH tx for {tx_selector}: {tx.get('hash')} (value: {tx_value})")
                            else:
                                selector_erc20_txs[tx_selector].append(tx)
                                logger.debug(f"Found ERC20 tx for {tx_selector}: {tx.get('hash')}")
                        else:
                            # For non-payable selectors, just add normally
                            if len(selector_txs[tx_selector]) < selector_wanted[tx_selector]:
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

        # Combine native and ERC20 transactions for payable selectors
        for sel in payable_selectors:
            native_txs = selector_native_txs[sel]
            erc20_txs = selector_erc20_txs[sel]

            # Strategy: Try to get at least 1 of each type if possible
            # Then fill remaining slots with whatever is available
            combined = []

            # First, add at least 1 native if available
            if native_txs:
                combined.append(native_txs[0])

            # Then, add at least 1 ERC20 if available
            if erc20_txs:
                combined.append(erc20_txs[0])

            # Fill remaining slots, alternating between native and ERC20
            remaining_slots = selector_wanted[sel] - len(combined)
            native_idx = 1  # Start from index 1 since we already took index 0
            erc20_idx = 1

            while remaining_slots > 0:
                added = False

                # Try to add a native tx
                if native_idx < len(native_txs):
                    combined.append(native_txs[native_idx])
                    native_idx += 1
                    remaining_slots -= 1
                    added = True

                # Try to add an ERC20 tx
                if remaining_slots > 0 and erc20_idx < len(erc20_txs):
                    combined.append(erc20_txs[erc20_idx])
                    erc20_idx += 1
                    remaining_slots -= 1
                    added = True

                # If we couldn't add anything, break
                if not added:
                    break

            selector_txs[sel] = combined

        logger.info(f"Scanned {total_txs_scanned} total transactions")
        for sel, tx_list in selector_txs.items():
            if sel in payable_selectors:
                native_count = sum(1 for tx in tx_list if int(tx.get('value', '0')) > 0)
                erc20_count = len(tx_list) - native_count
                logger.info(f"Selector {sel} (payable): found {len(tx_list)}/{selector_wanted[sel]} transactions ({native_count} native ETH, {erc20_count} ERC20)")
            else:
                logger.info(f"Selector {sel}: found {len(tx_list)}/{selector_wanted[sel]} transactions")

        return selector_txs

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
        if use_blockscout and chain_id in BLOCKSCOUT_URLS:
            try:
                base_url = BLOCKSCOUT_URLS[chain_id]
                url = f"{base_url}/api/v2/transactions/{tx_hash}"
                response = requests.get(url)
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

        # Use Etherscan API
        params = {
            'module': 'proxy',
            'action': 'eth_getTransactionReceipt',
            'txhash': tx_hash,
        }

        # Etherscan requires API key
        if not use_blockscout:
            params['apikey'] = self.etherscan_api_key

        try:
            base_url = self._get_api_base_url(chain_id, use_blockscout)
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
