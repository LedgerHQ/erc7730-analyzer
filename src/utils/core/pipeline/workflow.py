"""Pipeline orchestrator combining staged analysis flow."""

from __future__ import annotations

import sys
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from .batch import AnalyzerPipelineBatchMixin
from .finalize import AnalyzerPipelineFinalizeMixin
from .preparation import AnalyzerPipelinePreparationMixin
from .setup import AnalyzerPipelineSetupMixin
from .source import AnalyzerPipelineSourceMixin
from .transactions import AnalyzerPipelineTransactionsMixin


def _status(msg: str, end: str = "\n") -> None:
    """Print a progress line to stderr so it's visible even when stdout is piped."""
    sys.stderr.write(msg + end)
    sys.stderr.flush()


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
        abi_file: Path | None = None,
        raw_txs_file: Path | None = None,
    ) -> dict[str, Any]:
        total_start = time.time()
        _status(f"\n[1/5] Loading descriptor and ABI from {erc7730_file.name}...")
        context = self._setup_analysis_context(erc7730_file, abi_file)
        if not context:
            _status("      Failed to load descriptor/ABI.")
            return {}

        n_selectors = len(context.get("selectors", []))
        _status(f"      Found {n_selectors} selector(s) to audit.")

        _status("[2/5] Fetching on-chain transactions...")
        self._collect_selector_transactions(context, raw_txs_file)

        _status("[3/5] Extracting contract source code...")
        self._extract_source_and_context(context)

        _status("[4/5] Preparing audit tasks...")
        self._prepare_selector_audit_tasks(context)

        backend = self.llm_config.backend
        model = self.llm_config.model
        _status(f"[5/5] Running LLM audits ({backend}/{model}, {n_selectors} task(s))...")
        self._run_batch_audits(context)

        elapsed = time.time() - total_start
        _status(f"\nAnalysis complete in {elapsed:.1f}s.\n")

        return self._finalize_results(context)
