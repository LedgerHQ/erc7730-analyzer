"""Pipeline stage: transaction collection and optional manual tx integration."""

import logging
from typing import Any, Dict, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class AnalyzerPipelineTransactionsMixin:
    def _collect_selector_transactions(
        self,
        context: Dict[str, Any],
        raw_txs_file: Optional[Path] = None,
    ) -> None:
        """Fetch transaction samples per selector across deployments."""
        selectors = context['selectors']
        deployments = context['deployments']
        abi = context['abi']
        # First, identify which selectors are payable by checking their ABI
        logger.info(f"\n{'='*60}")
        logger.info(f"Identifying payable functions...")
        logger.info(f"{'='*60}")

        payable_selectors = set()
        for selector in selectors:
            function_data = self.get_function_abi_by_selector(selector)
            if function_data and function_data.get('stateMutability') == 'payable':
                payable_selectors.add(selector.lower())
                logger.info(f"Function {function_data['name']} ({selector}) is payable")

        if payable_selectors:
            logger.info(f"Found {len(payable_selectors)} payable function(s)")

        # Fetch transactions for ALL selectors at once
        logger.info(f"\n{'='*60}")
        logger.info(f"Fetching transactions for all {len(selectors)} selectors at once...")
        logger.info(f"{'='*60}")

        # Initialize transaction storage and track how many samples are still needed
        transactions_per_selector = 5  # Matches tx_fetcher default
        all_selector_txs = {s.lower(): [] for s in selectors}
        selectors_remaining = {
            s.lower(): transactions_per_selector
            for s in selectors
        }
        deployment_per_selector = {}  # Track which deployment was used for each selector
        default_deployment = deployments[0] if deployments else {
            'address': 'N/A',
            'chainId': 1
        }

        # Try each deployment, continuing to search for selectors that don't have transactions yet
        for deployment in deployments:
            selectors_to_query = [
                selector
                for selector, remaining in selectors_remaining.items()
                if remaining > 0
            ]

            if not selectors_to_query:
                # All selectors have transactions, no need to continue
                break

            contract_address = deployment['address']
            chain_id = deployment['chainId']
            logger.info(f"Trying deployment: {contract_address} on chain {chain_id}")
            logger.info(f"  Looking for transactions for {len(selectors_to_query)} remaining selector(s)")

            # Fetch transactions only for selectors that don't have any yet
            deployment_txs = self.tx_fetcher.fetch_all_transactions_for_selectors(
                contract_address,
                selectors_to_query,
                chain_id,
                per_selector=transactions_per_selector,
                payable_selectors=payable_selectors
            )

            # Update results for selectors that found transactions
            for selector, txs in deployment_txs.items():
                if not txs:
                    continue

                selector_lower = selector.lower()
                if selector_lower not in selectors_remaining:
                    continue

                remaining_needed = selectors_remaining[selector_lower]
                if remaining_needed <= 0:
                    continue

                # Only keep as many transactions as still needed
                to_add = txs[:remaining_needed]
                if not to_add:
                    continue

                all_selector_txs[selector_lower].extend(to_add)
                selectors_remaining[selector_lower] = max(0, remaining_needed - len(to_add))
                deployment_per_selector.setdefault(selector_lower, deployment)
                logger.info(
                    f"  ✓ Aggregated {len(all_selector_txs[selector_lower])}/"
                    f"{transactions_per_selector} transaction(s) for {selector_lower} "
                    f"(added {len(to_add)} from chain {chain_id})"
                )

        # Log final results
        satisfied_selectors = [
            sel for sel, remaining in selectors_remaining.items()
            if remaining <= 0
        ]
        selectors_missing = [
            sel for sel, remaining in selectors_remaining.items()
            if remaining > 0
        ]

        found_count = len(satisfied_selectors)
        not_found_count = len(selectors_missing)

        logger.info(f"\n{'='*60}")
        logger.info(f"Transaction search complete:")
        logger.info(f"  ✓ {found_count} selector(s) with transactions")
        if not_found_count > 0:
            logger.warning(
                f"  ⚠ {not_found_count} selector(s) still missing samples: {selectors_missing}"
            )
        logger.info(f"{'='*60}\n")

        # Integrate manual transactions if provided
        if raw_txs_file:
            logger.info(f"\n{'='*60}")
            logger.info(f"Integrating manual transactions from {raw_txs_file}")
            logger.info(f"{'='*60}")

            # Use the primary deployment for manual transaction integration
            primary_deployment = deployments[0] if deployments else None
            if primary_deployment:
                all_selector_txs = self.tx_fetcher.integrate_manual_transactions(
                    all_selector_txs,
                    raw_txs_file,
                    primary_deployment['address'],
                    abi,
                    primary_deployment['chainId']
                )
                logger.info(f"{'='*60}\n")
            else:
                logger.warning("No deployment available for manual transaction integration")

        context['all_selector_txs'] = all_selector_txs
        context['deployment_per_selector'] = deployment_per_selector
        context['default_deployment'] = default_deployment
