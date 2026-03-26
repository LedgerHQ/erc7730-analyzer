"""Integration tests for the POST/GET /analyze API contract."""

from __future__ import annotations

import asyncio
import json
import sys
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

import service.app as app_mod
import service.client as client_mod

if TYPE_CHECKING:
    from pathlib import Path

    import httpx


async def _mock_execute(*, job, semaphore, **kwargs):
    """Fast mock that acquires the semaphore and completes the job."""
    async with semaphore:
        job.set_status("running", "Analysis started")
        job.set_result({
            "protocol": "test_proto",
            "has_criticals": False,
            "summary_report": "# Test Report",
            "criticals_report": "",
            "results_json": {"selectors": []},
        })


async def _blocking_execute(*, job, semaphore, **kwargs):
    """Mock that holds the semaphore indefinitely (for capacity tests)."""
    async with semaphore:
        job.set_status("running", "Holding semaphore")
        job.append_log("live log line")
        await asyncio.sleep(60)


def _run_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, run_analysis):
    """Invoke the CLI with a relative output dir like CI does."""
    descriptor = tmp_path / "descriptor.json"
    descriptor.write_text("{}")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(client_mod, "run_analysis", run_analysis)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "erc7730-client",
            "--no-auth",
            "--service-url",
            "http://service.test",
            "--descriptor",
            str(descriptor),
            "--output-dir",
            "output",
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        client_mod.main()

    return exc_info.value.code, tmp_path / "output"


class TestHealth:
    async def test_returns_ok(self, client: httpx.AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestPostAnalyze:
    async def test_returns_202(self, client: httpx.AsyncClient):
        with patch.object(app_mod, "_execute_analysis", _mock_execute):
            resp = await client.post("/analyze", json={"descriptor": {"test": True}})
        assert resp.status_code == 202
        body = resp.json()
        assert "run_key" in body
        assert body["status"] in ("queued", "running", "succeeded")
        assert "started_at" in body
        assert "updated_at" in body

    async def test_missing_descriptor_returns_422(self, client: httpx.AsyncClient):
        resp = await client.post("/analyze", json={})
        assert resp.status_code == 422

    async def test_at_capacity_returns_503(self, client: httpx.AsyncClient):
        with patch.object(app_mod, "_execute_analysis", _blocking_execute):
            resp1 = await client.post("/analyze", json={"descriptor": {"a": 1}})
            assert resp1.status_code == 202

            await asyncio.sleep(0.1)

            resp2 = await client.post("/analyze", json={"descriptor": {"b": 2}})
            assert resp2.status_code == 503


class TestGetAnalyze:
    async def test_not_found(self, client: httpx.AsyncClient):
        resp = await client.get("/analyze", params={"run_key": "nonexistent"})
        assert resp.status_code == 404

    async def test_missing_run_key_returns_400(self, client: httpx.AsyncClient):
        resp = await client.get("/analyze")
        assert resp.status_code == 400

    async def test_returns_running_job(self, client: httpx.AsyncClient):
        with patch.object(app_mod, "_execute_analysis", _blocking_execute):
            post = await client.post("/analyze", json={"descriptor": {"x": 1}})
            run_key = post.json()["run_key"]

            await asyncio.sleep(0.1)

            get = await client.get("/analyze", params={"run_key": run_key})
            assert get.status_code == 202
            assert get.json()["status"] == "running"
            assert "recent_logs" not in get.json()

    async def test_running_job_includes_logs_when_verbose(self, client: httpx.AsyncClient):
        with patch.object(app_mod, "_execute_analysis", _blocking_execute):
            post = await client.post("/analyze", json={"descriptor": {"x": 1}, "verbose": True})
            run_key = post.json()["run_key"]

            await asyncio.sleep(0.1)

            get = await client.get("/analyze", params={"run_key": run_key})
            assert get.status_code == 202
            assert get.json()["recent_logs"] == ["live log line"]

    async def test_running_job_can_explicitly_suppress_logs(self, client: httpx.AsyncClient):
        with patch.object(app_mod, "_execute_analysis", _blocking_execute):
            post = await client.post("/analyze", json={"descriptor": {"x": 1}, "verbose": True})
            run_key = post.json()["run_key"]

            await asyncio.sleep(0.1)

            get = await client.get("/analyze", params={"run_key": run_key, "include_logs": "false"})
            assert get.status_code == 202
            assert "recent_logs" not in get.json()


class TestFullPollingFlow:
    async def test_post_then_poll_to_success(self, client: httpx.AsyncClient):
        with patch.object(app_mod, "_execute_analysis", _mock_execute):
            post = await client.post("/analyze", json={"descriptor": {"test": True}})
            assert post.status_code == 202
            run_key = post.json()["run_key"]

            await asyncio.sleep(0.2)

            get = await client.get("/analyze", params={"run_key": run_key})
            assert get.status_code == 200
            body = get.json()
            assert body["status"] == "succeeded"
            assert body["protocol"] == "test_proto"
            assert body["has_criticals"] is False
            assert "summary_report" in body
            assert "results_json" in body


class TestClientCli:
    def test_creates_output_dir_and_status_artifact_for_criticals(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        def _mock_run_analysis(**kwargs):
            return {
                "status": "succeeded",
                "protocol": "demo-protocol",
                "has_criticals": True,
                "summary_report": "# Summary\n",
                "criticals_report": "# Criticals\n",
                "results_json": {},
            }

        exit_code, output_dir = _run_client(monkeypatch, tmp_path, _mock_run_analysis)

        assert exit_code == 1
        assert output_dir.is_dir()
        assert (output_dir / "FULL_REPORT_demo-protocol.md").exists()
        assert (output_dir / "CRITICALS_demo-protocol.md").exists()
        assert (output_dir / "results_demo-protocol.json").exists()

        status = json.loads((output_dir / "analysis_status.json").read_text())
        assert status == {
            "status": "succeeded",
            "protocol": "demo-protocol",
            "has_criticals": True,
        }

    def test_creates_output_dir_for_failed_status(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        def _mock_run_analysis(**kwargs):
            return {
                "status": "failed",
                "error": "remote analysis failed",
            }

        exit_code, output_dir = _run_client(monkeypatch, tmp_path, _mock_run_analysis)

        assert exit_code == 1
        assert output_dir.is_dir()

        status = json.loads((output_dir / "analysis_status.json").read_text())
        assert status == {
            "status": "failed",
            "protocol": "unknown",
            "has_criticals": False,
            "error": "remote analysis failed",
        }

    def test_creates_output_dir_when_request_raises(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        def _mock_run_analysis(**kwargs):
            raise RuntimeError("connection dropped")

        exit_code, output_dir = _run_client(monkeypatch, tmp_path, _mock_run_analysis)

        assert exit_code == 1
        assert output_dir.is_dir()

        status = json.loads((output_dir / "analysis_status.json").read_text())
        assert status == {
            "status": "failed",
            "protocol": "unknown",
            "has_criticals": False,
            "error": "RuntimeError: connection dropped",
        }
