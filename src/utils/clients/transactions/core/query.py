"""Primary API query loops for selector transaction retrieval."""

import logging
import time
from typing import Any, Dict, List, Optional

import requests

from ..constants import BLOCKSCOUT_URLS

logger = logging.getLogger(__name__)


class TransactionFetcherCoreQueryMixin:
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

        # Normalize selectors to lowercase for consistent dictionary keys
        selectors = [s.lower() for s in selectors]
        selector_txs = {s: [] for s in selectors}
        selector_wanted = {s: per_selector for s in selectors}

        # Only keep payable selectors that are part of this batch
        if payable_selectors is None:
            payable_selectors = set()
        else:
            payable_selectors = {s.lower() for s in payable_selectors}
        payable_selectors = {s for s in payable_selectors if s in selector_txs}

        # For payable selectors, track native ETH and ERC20 transactions separately
        selector_native_txs = {s: [] for s in payable_selectors}
        selector_erc20_txs = {s: [] for s in payable_selectors}

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

        # Normalize selectors to lowercase for consistent dictionary keys
        selectors = [s.lower() for s in selectors]
        selector_txs = {s: [] for s in selectors}
        selector_wanted = {s: per_selector for s in selectors}

        # Only keep payable selectors that are part of this batch
        if payable_selectors is None:
            payable_selectors = set()
        else:
            payable_selectors = {s.lower() for s in payable_selectors}
        payable_selectors = {s for s in payable_selectors if s in selector_txs}

        # For payable selectors, track native ETH and ERC20 transactions separately
        selector_native_txs = {s: [] for s in payable_selectors}
        selector_erc20_txs = {s: [] for s in payable_selectors}

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
        MAX_CONSECUTIVE_FAILURES = 3  # Abort after 3 consecutive failures (reduced from 5 for faster bailout)

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
                        response = requests.get(base_url, params=params, timeout=10)
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
