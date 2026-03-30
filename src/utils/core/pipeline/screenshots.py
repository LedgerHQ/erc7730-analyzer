"""Pipeline stage: generate Ledger device screenshots via cs-tester (async)."""

import asyncio
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class AnalyzerPipelineScreenshotsMixin:
    def _load_prepared_input_screenshot_context(
        self,
        context: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Build tx/deployment maps for screenshot capture from prepared inputs."""
        prepared_inputs_data = context.get("prepared_inputs_data") or {}
        default_deployment = (context.get("deployments") or [{"chainId": 1, "address": "N/A"}])[0]

        all_selector_txs: dict[str, Any] = {}
        deployment_per_selector: dict[str, Any] = {}

        prepared_selector_inputs = prepared_inputs_data.get("selectors")
        if isinstance(prepared_selector_inputs, dict) and prepared_selector_inputs:
            for selector_key, selector_entry in prepared_selector_inputs.items():
                if not isinstance(selector_entry, dict):
                    continue
                selector = str(selector_key).lower()
                txs = (
                    selector_entry.get("decoded_transactions")
                    or selector_entry.get("decoded_txs")
                    or selector_entry.get("transactions")
                    or []
                )
                deployment = selector_entry.get("selector_deployment") or default_deployment
                if txs:
                    all_selector_txs[selector] = txs
                deployment_per_selector[selector] = deployment
            return all_selector_txs, deployment_per_selector

        contracts = prepared_inputs_data.get("contracts")
        if not isinstance(contracts, dict):
            return all_selector_txs, deployment_per_selector

        for contract_key, contract_entry in contracts.items():
            if not isinstance(contract_entry, dict):
                continue

            selector_meta = contract_entry.get("selectors") or {}
            tx_by_selector = contract_entry.get("transactions") or {}
            selector_deployment = {
                "address": contract_entry.get("address") or contract_key,
                "chainId": int(contract_entry.get("chainId") or default_deployment.get("chainId", 1)),
            }

            selector_keys = {str(key).lower() for key in selector_meta} | {str(key).lower() for key in tx_by_selector}

            for selector in selector_keys:
                meta = selector_meta.get(selector) or selector_meta.get(selector.lower()) or {}
                txs = tx_by_selector.get(selector) or tx_by_selector.get(selector.lower()) or []
                deployment = meta.get("selector_deployment") or selector_deployment
                if txs:
                    all_selector_txs[selector] = txs
                deployment_per_selector[selector] = deployment

        return all_selector_txs, deployment_per_selector

    def _capture_screenshots(self, context: dict[str, Any]) -> None:
        """Generate Ledger device screenshots for each selector's transactions."""
        if not getattr(self, "enable_screenshots", False):
            logger.info("[SCREENSHOTS] Screenshot capture is disabled")
            context["screenshot_data"] = {}
            return

        from ...screenshots import ScreenshotRunner

        runner = ScreenshotRunner(
            etherscan_api_key=self.etherscan_api_key,
            cs_tester_root=getattr(self, "cs_tester_root", None),
            coin_apps_path=getattr(self, "coin_apps_path", None),
            device=getattr(self, "screenshot_device", "stax"),
        )

        if not runner.is_available():
            diagnostic = runner.availability_diagnostic()
            logger.warning(
                "[SCREENSHOTS] Screenshot capture unavailable: %s. Skipping screenshot capture.",
                diagnostic,
            )
            context["screenshot_data"] = {}
            return

        erc7730_file = context.get("erc7730_file")
        if not erc7730_file:
            erc7730_data = context.get("erc7730_data", {})
            erc7730_file = erc7730_data.get("_source_path")
        if erc7730_file:
            erc7730_file = Path(erc7730_file)

        all_selector_txs = context.get("all_selector_txs", {})
        deployment_per_selector = context.get("deployment_per_selector", {})
        if context.get("prepared_inputs_data") and not all_selector_txs:
            prepared_txs, prepared_deployments = self._load_prepared_input_screenshot_context(context)
            if prepared_txs:
                logger.info(
                    "[SCREENSHOTS] Loaded %d selector transaction set(s) from prepared inputs",
                    len(prepared_txs),
                )
                all_selector_txs = prepared_txs
                context["all_selector_txs"] = prepared_txs
            if prepared_deployments:
                deployment_per_selector = prepared_deployments
                context["deployment_per_selector"] = prepared_deployments
        default_deployment = context.get("default_deployment", {"chainId": 1})
        selectors = context.get("abi_backed_selectors") or context.get("selectors", [])

        # Build work items for all selectors that have transactions
        selectors_info = []
        for selector in selectors:
            txs = all_selector_txs.get(selector.lower(), [])
            if not txs:
                logger.info("[SCREENSHOTS][%s] No transactions — skipping", selector)
                continue
            deployment = deployment_per_selector.get(selector.lower(), default_deployment)
            selectors_info.append(
                {
                    "selector": selector,
                    "chain_id": int(deployment.get("chainId", 1)),
                    "transactions": txs,
                }
            )

        if not selectors_info:
            logger.info("[SCREENSHOTS] No selectors with transactions to capture")
            context["screenshot_data"] = {}
            return

        import gc

        if hasattr(self, "tx_fetcher") and hasattr(self.tx_fetcher, "close_snowflake_connections"):
            try:
                self.tx_fetcher.close_snowflake_connections()
                logger.info("[SCREENSHOTS] Closed cached Snowflake connections before capture")
            except Exception as exc:
                logger.warning("[SCREENSHOTS] Failed to close Snowflake connections before capture: %s", exc)

        gc.collect()
        logger.info(
            "\n%s\n[SCREENSHOTS] Capturing Ledger screenshots for %d selector(s) (gc.collect done)...\n%s",
            "=" * 60,
            len(selectors_info),
            "=" * 60,
        )

        cancel_event = context.get("cancel_event")
        runner.cancel_event = cancel_event

        screenshot_map = asyncio.run(
            runner.capture_all_selectors_async(
                selectors_info=selectors_info,
                erc7730_file=erc7730_file or Path("descriptor.json"),
            )
        )

        total = sum(len(entry.get("screenshots", [])) for tx_list in screenshot_map.values() for entry in tx_list)
        if total == 0:
            logger.warning(
                "[SCREENSHOTS] All %d selector capture(s) produced 0 screenshots — "
                "check Speculos/qemu-user-static and cs-tester logs above for errors",
                len(selectors_info),
            )
        else:
            logger.info(
                "[SCREENSHOTS] Captured %d meaningful screenshot(s) across %d selector(s)",
                total,
                len(screenshot_map),
            )
        context["screenshot_data"] = screenshot_map
        context["_screenshot_runner"] = runner
