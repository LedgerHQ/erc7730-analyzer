"""Selector-level transaction aggregation and manual transaction integration."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from ....abi import ABI
from ....extraction.raw_tx_parser import group_transactions_by_selector, load_raw_transactions
from ..constants import BLOCKSCOUT_URLS

logger = logging.getLogger(__name__)


class TransactionFetcherCoreAggregationMixin:
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
        if not raw_txs_file:
            logger.info("No manual transactions file provided")
            return fetched_txs

        raw_txs_path = Path(raw_txs_file)

        if not raw_txs_path.exists():
            logger.info(f"Manual transactions file {raw_txs_path} not found - skipping")
            return fetched_txs

        if raw_txs_path.is_dir():
            logger.info(f"Manual transactions path {raw_txs_path} is a directory - skipping manual tx integration")
            return fetched_txs

        logger.info(f"Loading manual transactions from {raw_txs_file}")

        # Load and parse raw transactions
        parsed_manual_txs = load_raw_transactions(raw_txs_path)

        if not parsed_manual_txs:
            logger.warning("No valid manual transactions found in file")
            return fetched_txs

        # Fetch transactions that are marked as hash_only
        for manual_tx in parsed_manual_txs:
            if manual_tx.get('mode') == 'hash_only':
                tx_hash = manual_tx['tx_hash']
                logger.info(f"Fetching transaction data for {tx_hash} from Etherscan")

                # Fetch transaction from Etherscan
                try:
                    params = {
                        'module': 'proxy',
                        'action': 'eth_getTransactionByHash',
                        'txhash': tx_hash,
                        'apikey': self.etherscan_api_key
                    }

                    base_url = self._get_api_base_url(chain_id, False)
                    response = requests.get(base_url, params=params, timeout=10)
                    response.raise_for_status()
                    data = response.json()

                    # Etherscan proxy API returns result directly (not wrapped in status/result)
                    tx_data = data.get('result')

                    if tx_data and isinstance(tx_data, dict) and tx_data.get('hash'):
                        manual_tx['to'] = tx_data.get('to', '')
                        manual_tx['input'] = tx_data.get('input', '')
                        manual_tx['value'] = int(tx_data.get('value', '0x0'), 16)
                        manual_tx['selector'] = tx_data.get('input', '')[:10] if tx_data.get('input') else None
                        manual_tx['from'] = tx_data.get('from', '')
                        manual_tx['mode'] = 'fetched'
                        logger.info(f"✓ Fetched transaction: selector={manual_tx['selector']}, to={manual_tx['to']}")
                    else:
                        error_msg = data.get('message') or data.get('error') or 'Transaction not found or invalid response'
                        logger.warning(f"✗ Failed to fetch transaction {tx_hash}: {error_msg}")
                        logger.info(f"Response keys: {list(data.keys() if isinstance(data, dict) else [])}")
                        logger.info(f"Response data: {str(data)[:200]}")
                        manual_tx['mode'] = 'fetch_failed'
                except Exception as e:
                    logger.error(f"✗ Error fetching transaction {tx_hash}: {e}")
                    manual_tx['mode'] = 'fetch_failed'

        # Filter out failed fetches
        parsed_manual_txs = [tx for tx in parsed_manual_txs if tx.get('mode') != 'fetch_failed']

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
            for idx, manual_tx in enumerate(contract_manual_txs, 1):
                # Use a friendly identifier for manual transactions
                tx_hash = manual_tx.get('tx_hash', '').strip()
                tx_id = tx_hash if tx_hash and tx_hash.startswith('0x') else f"manual_tx_{idx}"

                logger.info(f"Processing manual transaction {idx}/{len(contract_manual_txs)} for selector {selector}")
                if manual_tx.get('description'):
                    logger.info(f"  Description: {manual_tx['description']}")

                # Create transaction dict in Etherscan format
                tx_dict = {
                    'hash': tx_id,
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
                    logger.info(f"✓ Successfully decoded manual transaction {tx_id}")
                else:
                    logger.warning(f"✗ Failed to decode manual transaction {tx_id}")
                    continue

                # Try to fetch receipt if we have a real tx hash
                if tx_hash and tx_hash.startswith('0x'):
                    logger.info(f"Attempting to fetch receipt for manual TX {tx_hash}")
                    receipt = self.fetch_transaction_receipt(
                        tx_hash,
                        chain_id
                    )
                    if receipt:
                        tx_dict['receipt_logs'] = receipt.get('receipt_logs', [])
                        logger.info(f"✓ Fetched receipt with {len(receipt.get('receipt_logs', []))} logs")
                else:
                    logger.debug(f"No transaction hash provided for manual TX - skipping receipt fetch")

                converted_txs.append(tx_dict)

            # Merge with fetched transactions (manual txs first)
            if selector_lower not in result:
                result[selector_lower] = []

            result[selector_lower] = converted_txs + result[selector_lower]
            logger.info(f"✓ Added {len(converted_txs)} manual transaction(s) to selector {selector} "
                       f"(total: {len(result[selector_lower])})")

        return result
