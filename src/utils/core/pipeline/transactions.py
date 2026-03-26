"""Pipeline stage: transaction collection and optional manual tx integration."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from ...clients.transactions.fetcher import TransactionFetcher

logger = logging.getLogger(__name__)


class AnalyzerPipelineTransactionsMixin:
    def _collect_selector_transactions(
        self,
        context: dict[str, Any],
        raw_txs_file: Path | None = None,
    ) -> None:
        """Fetch transaction samples per selector across deployments."""
        selectors = context["selectors"]
        abi_backed_selectors = context.get("abi_backed_selectors", selectors)
        abi_backed_selector_set = {s.lower() for s in abi_backed_selectors}
        deployments = context["deployments"]
        abi = context["abi"]
        # First, identify which selectors are payable by checking their ABI
        logger.info(f"\n{'=' * 60}")
        logger.info("Identifying payable functions...")
        logger.info(f"{'=' * 60}")

        payable_selectors = set()
        for selector in abi_backed_selectors:
            function_data = (context.get("selector_function_data", {}) or {}).get(selector.lower())
            if function_data is None:
                function_data = self.get_function_abi_by_selector(selector)
            if function_data and function_data.get("stateMutability") == "payable":
                payable_selectors.add(selector.lower())
                logger.debug(f"Function {function_data['name']} ({selector}) is payable")

        if payable_selectors:
            logger.info(f"Found {len(payable_selectors)} payable function(s)")

        # Fetch transactions for ALL selectors at once
        logger.info(f"\n{'=' * 60}")
        logger.info(f"Fetching transactions for all {len(selectors)} selectors at once...")
        logger.info(f"{'=' * 60}")
        skipped_selectors = [s for s in selectors if s.lower() not in abi_backed_selector_set]
        if skipped_selectors:
            logger.warning(
                "Skipping transaction fetch for %d selector(s) not found in merged ABI: %s",
                len(skipped_selectors),
                skipped_selectors,
            )

        # Initialize transaction storage and track how many samples are still needed
        transactions_per_selector = 5  # Matches tx_fetcher default
        all_selector_txs = {s.lower(): [] for s in selectors}
        selectors_remaining = {s.lower(): transactions_per_selector for s in abi_backed_selectors}
        deployment_per_selector = {}  # Track which deployment was used for each selector
        default_deployment = deployments[0] if deployments else {"address": "N/A", "chainId": 1}

        def _merge_deployment_transactions(
            completed_deployment: dict[str, Any],
            deployment_txs: dict[str, list[dict[str, Any]]],
            *,
            source_label: str | None = None,
        ) -> None:
            chain_id = completed_deployment["chainId"]
            for selector, txs in deployment_txs.items():
                if not txs:
                    continue

                selector_lower = selector.lower()
                if selector_lower not in selectors_remaining:
                    continue

                remaining_needed = selectors_remaining[selector_lower]
                if remaining_needed <= 0:
                    continue

                to_add = txs[:remaining_needed]
                if not to_add:
                    continue

                all_selector_txs[selector_lower].extend(to_add)
                selectors_remaining[selector_lower] = max(0, remaining_needed - len(to_add))
                deployment_per_selector.setdefault(selector_lower, completed_deployment)
                if source_label:
                    logger.debug(
                        f"  ✓ Aggregated {len(all_selector_txs[selector_lower])}/"
                        f"{transactions_per_selector} transaction(s) for {selector_lower} "
                        f"(added {len(to_add)} from chain {chain_id} via {source_label})"
                    )
                else:
                    logger.debug(
                        f"  ✓ Aggregated {len(all_selector_txs[selector_lower])}/"
                        f"{transactions_per_selector} transaction(s) for {selector_lower} "
                        f"(added {len(to_add)} from chain {chain_id})"
                    )

        selectors_to_query = list(selectors_remaining.keys())
        if deployments and selectors_to_query:
            deployments_by_chain: dict[int, list[tuple[int, dict[str, Any]]]] = {}
            for deployment_index, deployment in enumerate(deployments):
                deployments_by_chain.setdefault(int(deployment["chainId"]), []).append((deployment_index, deployment))

            max_workers = max(
                1,
                min(len(deployments), int(getattr(self, "max_concurrent_api_calls", len(deployments)) or len(deployments))),
            )
            fallback_deployment_indices = set(range(len(deployments)))

            if self.tx_fetcher._snowflake_tx_history_enabled():
                snowflake_successful_deployment_indices: set[int] = set()
                snowflake_failed_deployment_indices: set[int] = set()
                chain_workers = max(
                    1,
                    min(
                        len(deployments_by_chain),
                        int(getattr(self, "max_concurrent_api_calls", len(deployments_by_chain)) or len(deployments_by_chain)),
                    ),
                )
                logger.info(
                    "Launching chain-batched Snowflake transaction fetches for %d chain(s) with up to %d worker(s)",
                    len(deployments_by_chain),
                    chain_workers,
                )

                def _fetch_chain_snowflake_transactions(
                    chain_id: int,
                    deployment_items: list[tuple[int, dict[str, Any]]],
                ) -> tuple[
                    int,
                    list[tuple[int, dict[str, Any]]],
                    dict[str, dict[str, list[dict[str, Any]]]] | None,
                    dict[tuple[int, str], dict[str, Any]],
                    dict[int, str],
                ]:
                    addresses = [deployment["address"] for _, deployment in deployment_items]
                    logger.info(
                        "Trying %d deployment(s) on chain %s in one Snowflake batch",
                        len(addresses),
                        chain_id,
                    )
                    worker_fetcher = TransactionFetcher(self.etherscan_api_key, self.lookback_days)
                    chain_result = worker_fetcher._fetch_transactions_from_snowflake_for_addresses(
                        contract_addresses=addresses,
                        selectors=selectors_to_query,
                        chain_id=chain_id,
                        per_selector=transactions_per_selector,
                        payable_selectors=payable_selectors,
                    )
                    return (
                        chain_id,
                        deployment_items,
                        chain_result,
                        dict(getattr(worker_fetcher, "_snowflake_transaction_row_cache", {})),
                        dict(getattr(worker_fetcher, "api_type_per_chain", {})),
                    )

                batched_snowflake_results: dict[int, tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]] = {}
                with ThreadPoolExecutor(max_workers=chain_workers) as executor:
                    future_map = {
                        executor.submit(_fetch_chain_snowflake_transactions, chain_id, deployment_items): chain_id
                        for chain_id, deployment_items in deployments_by_chain.items()
                    }
                    for future in as_completed(future_map):
                        chain_id = future_map[future]
                        try:
                            (
                                completed_chain_id,
                                deployment_items,
                                chain_result,
                                snowflake_cache,
                                api_type_per_chain,
                            ) = future.result()
                        except Exception as exc:
                            logger.warning("Batched Snowflake transaction fetch failed for chain %s: %s", chain_id, exc)
                            snowflake_failed_deployment_indices.update(idx for idx, _ in deployments_by_chain.get(chain_id, []))
                            continue

                        if chain_result is None:
                            snowflake_failed_deployment_indices.update(idx for idx, _ in deployment_items)
                            continue

                        snowflake_successful_deployment_indices.update(idx for idx, _ in deployment_items)

                        self.tx_fetcher._snowflake_transaction_row_cache.update(snowflake_cache)
                        self.tx_fetcher.api_type_per_chain.update(api_type_per_chain)
                        if any(
                            len(txs) > 0
                            for address_result in chain_result.values()
                            for txs in address_result.values()
                        ):
                            self.tx_fetcher.api_type_per_chain[completed_chain_id] = "Snowflake"

                        for deployment_index, deployment in deployment_items:
                            deployment_txs = chain_result.get(deployment["address"].lower())
                            if deployment_txs is None:
                                continue
                            batched_snowflake_results[deployment_index] = (deployment, deployment_txs)

                if batched_snowflake_results:
                    logger.info("Merging chain-batched Snowflake results in deployment order...")
                    for deployment_index, _deployment in enumerate(deployments):
                        result_bundle = batched_snowflake_results.get(deployment_index)
                        if result_bundle is None:
                            continue
                        completed_deployment, deployment_txs = result_bundle
                        _merge_deployment_transactions(
                            completed_deployment,
                            deployment_txs,
                            source_label="Snowflake",
                        )

                fallback_deployment_indices = set(snowflake_failed_deployment_indices)
                if snowflake_successful_deployment_indices and not fallback_deployment_indices:
                    logger.info("Snowflake completed for all deployment batches; explorer fallback disabled")
                elif snowflake_successful_deployment_indices and fallback_deployment_indices:
                    logger.info(
                        "Snowflake completed for %d deployment(s) and failed/unavailable for %d deployment(s); explorer fallback limited to failed/unavailable deployments",
                        len(snowflake_successful_deployment_indices),
                        len(fallback_deployment_indices),
                    )

            selectors_to_query = [selector for selector, remaining in selectors_remaining.items() if remaining > 0]
            fallback_deployments = [(idx, deployments[idx]) for idx in sorted(fallback_deployment_indices)]
            if not selectors_to_query:
                logger.info("Snowflake satisfied all selector transaction requirements before explorer fallback")
            elif not fallback_deployments:
                logger.info(
                    "Snowflake query completed for all deployment batches; keeping Snowflake results without explorer fallback"
                )
            else:
                # Explorer APIs (Etherscan / Blockscout) are rate-limited,
                # so we must call them sequentially — unlike Snowflake.
                fallback_workers = 1
                logger.info(
                    "Launching sequential explorer fallback fetches for %d deployment(s)",
                    len(fallback_deployments),
                )

                def _fetch_deployment_transactions(
                    deployment_index: int,
                    deployment: dict[str, Any],
                ) -> tuple[
                    int,
                    dict[str, Any],
                    dict[str, list[dict[str, Any]]],
                    dict[tuple[int, str], dict[str, Any]],
                    dict[int, str],
                ]:
                    contract_address = deployment["address"]
                    chain_id = deployment["chainId"]
                    logger.info("Trying deployment: %s on chain %s", contract_address, chain_id)
                    logger.info("  Looking for transactions for %d remaining selector(s)", len(selectors_to_query))

                    worker_fetcher = TransactionFetcher(self.etherscan_api_key, self.lookback_days)
                    deployment_txs = worker_fetcher.fetch_all_transactions_for_selectors(
                        contract_address,
                        selectors_to_query,
                        chain_id,
                        per_selector=transactions_per_selector,
                        payable_selectors=payable_selectors,
                        skip_snowflake=True,
                    )
                    return (
                        deployment_index,
                        deployment,
                        deployment_txs,
                        dict(getattr(worker_fetcher, "_snowflake_transaction_row_cache", {})),
                        dict(getattr(worker_fetcher, "api_type_per_chain", {})),
                    )

                deployment_results: dict[
                    int,
                    tuple[
                        dict[str, Any],
                        dict[str, list[dict[str, Any]]],
                        dict[tuple[int, str], dict[str, Any]],
                        dict[int, str],
                    ],
                ] = {}

                with ThreadPoolExecutor(max_workers=fallback_workers) as executor:
                    future_map = {
                        executor.submit(_fetch_deployment_transactions, idx, deployment): idx
                        for idx, deployment in fallback_deployments
                    }
                    for future in as_completed(future_map):
                        deployment_index = future_map[future]
                        deployment = deployments[deployment_index]
                        contract_address = deployment["address"]
                        chain_id = deployment["chainId"]
                        try:
                            _, completed_deployment, deployment_txs, snowflake_cache, api_type_per_chain = future.result()
                        except Exception as exc:
                            logger.warning(
                                "Transaction fetch failed for deployment %s on chain %s: %s",
                                contract_address,
                                chain_id,
                                exc,
                            )
                            continue
                        deployment_results[deployment_index] = (
                            completed_deployment,
                            deployment_txs,
                            snowflake_cache,
                            api_type_per_chain,
                        )
                        logger.info(
                            "Completed transaction fetch for deployment %s on chain %s",
                            contract_address,
                            chain_id,
                        )

                for deployment_index, _deployment in enumerate(deployments):
                    result_bundle = deployment_results.get(deployment_index)
                    if result_bundle is None:
                        continue

                    completed_deployment, deployment_txs, snowflake_cache, api_type_per_chain = result_bundle
                    self.tx_fetcher._snowflake_transaction_row_cache.update(snowflake_cache)
                    self.tx_fetcher.api_type_per_chain.update(api_type_per_chain)
                    _merge_deployment_transactions(completed_deployment, deployment_txs)

        # Log final results
        satisfied_selectors = [sel for sel, remaining in selectors_remaining.items() if remaining <= 0]
        selectors_missing = [sel for sel, remaining in selectors_remaining.items() if remaining > 0]

        found_count = len(satisfied_selectors)
        not_found_count = len(selectors_missing)

        logger.info(f"\n{'=' * 60}")
        logger.info("Transaction search complete:")
        logger.info(f"  ✓ {found_count} selector(s) with transactions")
        if not_found_count > 0:
            logger.warning(f"  ⚠ {not_found_count} selector(s) still missing samples: {selectors_missing}")
        logger.info(f"{'=' * 60}\n")

        # Integrate manual transactions if provided
        if raw_txs_file:
            logger.info(f"\n{'=' * 60}")
            logger.info(f"Integrating manual transactions from {raw_txs_file}")
            logger.info(f"{'=' * 60}")

            # Use the primary deployment for manual transaction integration
            primary_deployment = deployments[0] if deployments else None
            if primary_deployment:
                all_selector_txs = self.tx_fetcher.integrate_manual_transactions(
                    all_selector_txs, raw_txs_file, primary_deployment["address"], abi, primary_deployment["chainId"]
                )
                logger.info(f"{'=' * 60}\n")
            else:
                logger.warning("No deployment available for manual transaction integration")

        context["all_selector_txs"] = all_selector_txs
        context["deployment_per_selector"] = deployment_per_selector
        context["default_deployment"] = default_deployment
