"""Pipeline orchestrator combining staged analysis flow."""

from pathlib import Path
from typing import Any, Dict, Optional

from .batch import AnalyzerPipelineBatchMixin
from .finalize import AnalyzerPipelineFinalizeMixin
from .preparation import AnalyzerPipelinePreparationMixin
from .setup import AnalyzerPipelineSetupMixin
from .source import AnalyzerPipelineSourceMixin
from .transactions import AnalyzerPipelineTransactionsMixin


class AnalyzerPipelineMixin(
    AnalyzerPipelineSetupMixin,
    AnalyzerPipelineTransactionsMixin,
    AnalyzerPipelineSourceMixin,
    AnalyzerPipelinePreparationMixin,
    AnalyzerPipelineBatchMixin,
    AnalyzerPipelineFinalizeMixin,
):
    """Main analyzer pipeline split by setup/tx/source/prep/batch/finalize flows."""

    def analyze(
        self,
        erc7730_file: Path,
        abi_file: Optional[Path] = None,
        raw_txs_file: Optional[Path] = None,
    ) -> Dict[str, Any]:
        context = self._setup_analysis_context(erc7730_file, abi_file)
        if not context:
            return {}

        self._collect_selector_transactions(context, raw_txs_file)
        self._extract_source_and_context(context)
        self._prepare_selector_audit_tasks(context)
        self._run_batch_audits(context)
        return self._finalize_results(context)
