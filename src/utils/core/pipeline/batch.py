"""Pipeline stage: concurrent audit execution."""

import logging
from typing import Any

from ...auditing import generate_clear_signing_audits_batch
from ...auditing.models import AuditResult
from ...reporting.markdown_formatter import format_audit_reports

logger = logging.getLogger(__name__)


class AnalyzerPipelineBatchMixin:
    def _run_batch_audits(self, context: dict[str, Any]) -> None:
        """Execute audit tasks concurrently and cache results by selector."""
        prepared_selectors = context["prepared_selectors"]
        # ====================================================================
        # PHASE 2: BATCH API CALLS (Concurrent - maximum efficiency)
        # ====================================================================
        # Execute all API calls concurrently using asyncio.

        # Collect all audit tasks that need API calls
        audit_tasks = [p["audit_task"] for p in prepared_selectors if p["audit_task"] is not None]

        audit_results = []
        if audit_tasks:
            logger.info(f"\n{'=' * 60}")
            logger.info(f"PHASE 2: Executing {len(audit_tasks)} API calls concurrently...")
            logger.info(f"{'=' * 60}")

            # Execute batch API calls with concurrency limit and retry logic
            audit_results = generate_clear_signing_audits_batch(
                tasks=audit_tasks, max_concurrent=self.max_concurrent_api_calls, max_retries=self.max_api_retries
            )

            logger.info(f"\n{'=' * 60}")
            logger.info("PHASE 2 COMPLETE: All API calls finished")
            logger.info(f"{'=' * 60}")
        else:
            logger.info(f"\n{'=' * 60}")
            logger.info("PHASE 2 SKIPPED: No audit tasks to process")
            logger.info(f"{'=' * 60}")

        # Create a map from selector to audit result for easy lookup
        audit_results_map = {r.selector: r for r in audit_results}

        for prepared in prepared_selectors:
            synthetic_report_data = prepared.get("synthetic_report_data")
            selector = prepared.get("selector")
            if not selector or not synthetic_report_data or selector in audit_results_map:
                continue

            critical_report, detailed_report = format_audit_reports(synthetic_report_data)
            audit_results_map[selector] = AuditResult(
                selector=selector,
                function_signature=prepared["function_data"]["signature"],
                critical_report=critical_report,
                detailed_report=detailed_report,
                report_data=synthetic_report_data,
                success=True,
            )
            logger.info("Synthesized report for %s without AI because selector is missing from merged ABI", selector)

        context["audit_results_map"] = audit_results_map
