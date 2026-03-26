"""Tests for the local analyzer CLI entrypoint."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import main as main_mod

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_main_passes_descriptor_directory_as_include_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    descriptor = tmp_path / "descriptor.json"
    descriptor.write_text("{}")

    class DummyAnalyzer:
        def __init__(self, **kwargs):
            captured["init_kwargs"] = kwargs

        def analyze(self, *args, **kwargs):
            captured["analyze_args"] = args
            captured["analyze_kwargs"] = kwargs
            return {"context": {"$id": "demo"}, "metadata": {}}

    def _write_summary(results, path, **kwargs):
        path.write_text("# Summary\n")

    def _write_criticals(results, path, **kwargs):
        path.write_text("No critical issues found\n")

    def _write_json(results, path):
        path.write_text("{}")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main_mod, "ERC7730Analyzer", DummyAnalyzer)
    monkeypatch.setattr(main_mod, "generate_summary_file", _write_summary)
    monkeypatch.setattr(main_mod, "generate_criticals_report", _write_criticals)
    monkeypatch.setattr(main_mod, "save_json_results", _write_json)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "analyze_7730",
            "--erc7730_file",
            str(descriptor),
            "--api-key",
            "test-key",
        ],
    )

    assert main_mod.main() == 0
    assert captured["analyze_kwargs"] == {"include_root": descriptor.parent.resolve()}
