"""Pipeline orchestrator combining staged analysis flow."""

from pathlib import Path
from typing import Any

from .batch import AnalyzerPipelineBatchMixin
from .finalize import AnalyzerPipelineFinalizeMixin
from .preparation import AnalyzerPipelinePreparationMixin
from .screenshots import AnalyzerPipelineScreenshotsMixin
from .setup import AnalyzerPipelineSetupMixin
from .source import AnalyzerPipelineSourceMixin
from .transactions import AnalyzerPipelineTransactionsMixin


class AnalyzerPipelineMixin(
    AnalyzerPipelineSetupMixin,
    AnalyzerPipelineTransactionsMixin,
    AnalyzerPipelineSourceMixin,
    AnalyzerPipelinePreparationMixin,
    AnalyzerPipelineScreenshotsMixin,
    AnalyzerPipelineBatchMixin,
    AnalyzerPipelineFinalizeMixin,
):
    """Main analyzer pipeline split by setup/tx/source/prep/batch/finalize flows."""

    def analyze(
        self,
        erc7730_file: Path,
        abi_file: Path | None = None,
        raw_txs_file: Path | None = None,
        prepared_inputs_file: Path | None = None,
    ) -> dict[str, Any]:
        self.report_progress("Loading descriptor and ABI")
        context = self._setup_analysis_context(
            erc7730_file,
            abi_file,
            prepared_inputs_file,
        )
        if not context:
            return {}

        context["erc7730_file"] = erc7730_file
        selector_count = len(context.get("selectors", []))

        if prepared_inputs_file:
            self.report_progress("Capturing screenshots")
            self._capture_screenshots(context)
            self.report_progress(f"Preparing audit tasks for {selector_count} selector(s)")
            self._prepare_selector_audit_tasks_from_prepared_inputs(context)
        else:
            self.report_progress(f"Fetching transactions for {selector_count} selector(s)")
            self._collect_selector_transactions(context, raw_txs_file)
            self.report_progress("Capturing screenshots")
            self._capture_screenshots(context)
            self.report_progress("Extracting source code")
            self._extract_source_and_context(context)
            self.report_progress(f"Preparing audit tasks for {selector_count} selector(s)")
            self._prepare_selector_audit_tasks(context)
        self.report_progress(f"Running audits for {len(context.get('prepared_selectors', []))} selector(s)")
        self._run_batch_audits(context)
        self.report_progress("Finalizing analysis results")
        results = self._finalize_results(context)

        if hasattr(self, "tx_fetcher") and hasattr(self.tx_fetcher, "close_snowflake_connections"):
            self.tx_fetcher.close_snowflake_connections()

        return results
