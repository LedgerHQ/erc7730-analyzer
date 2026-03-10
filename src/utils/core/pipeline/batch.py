"""Pipeline stage: concurrent audit execution."""

from __future__ import annotations

import logging
from typing import Any

from ...auditing import generate_clear_signing_audits_batch

logger = logging.getLogger(__name__)


class AnalyzerPipelineBatchMixin:
    def _run_batch_audits(self, context: dict[str, Any]) -> None:
        """Execute audit tasks concurrently and cache results by selector."""
        prepared_selectors = context["prepared_selectors"]
        # ====================================================================
        # PHASE 2: BATCH API CALLS (Concurrent - maximum efficiency)
        # ====================================================================
        # Execute all API calls concurrently using asyncio.

        audit_tasks = [p["audit_task"] for p in prepared_selectors if p["audit_task"] is not None]

        audit_results = []
        if audit_tasks:
            logger.info(f"\n{'=' * 60}")
            logger.info(f"PHASE 2: Executing {len(audit_tasks)} API calls concurrently...")
            logger.info(f"{'=' * 60}")

            audit_results = generate_clear_signing_audits_batch(
                tasks=audit_tasks,
                llm_config=self.llm_config,
                max_concurrent=self.max_concurrent_api_calls,
                max_retries=self.max_api_retries,
            )

            logger.info(f"\n{'=' * 60}")
            logger.info("PHASE 2 COMPLETE: All API calls finished")
            logger.info(f"{'=' * 60}")
        else:
            logger.info(f"\n{'=' * 60}")
            logger.info("PHASE 2 SKIPPED: No audit tasks to process")
            logger.info(f"{'=' * 60}")

        audit_results_map = {r.selector: r for r in audit_results}

        context["audit_results_map"] = audit_results_map
