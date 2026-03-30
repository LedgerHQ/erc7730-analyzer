"""Integration tests for the POST/GET /analyze API contract."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from typing import TYPE_CHECKING
from unittest.mock import patch

import httpx
import pytest

import service.app as app_mod
import service.client as client_mod

if TYPE_CHECKING:
    from pathlib import Path

    from starlette.testclient import TestClient


async def _mock_execute(*, job, semaphore, **kwargs):
    """Fast mock that acquires the semaphore and completes the job."""
    async with semaphore:
        job.set_status("running", "Analysis started")
        job.set_result(
            {
                "protocol": "test_proto",
                "has_criticals": False,
                "summary_report": "# Test Report",
                "criticals_report": "",
                "results_json": {"selectors": []},
            }
        )


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
    def test_returns_ok(self, client: TestClient):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["semaphore_locked"] is False
        assert data["active_jobs"] == 0


class TestPostAnalyze:
    def test_returns_202(self, client: TestClient):
        with patch.object(app_mod, "_execute_analysis", _mock_execute):
            resp = client.post("/analyze", json={"descriptor": {"test": True}})
        assert resp.status_code == 202
        body = resp.json()
        assert "run_key" in body
        assert body["status"] in ("queued", "running", "succeeded")
        assert "started_at" in body
        assert "updated_at" in body

    def test_missing_descriptor_returns_422(self, client: TestClient):
        resp = client.post("/analyze", json={})
        assert resp.status_code == 422

    def test_at_capacity_returns_503(self, client: TestClient):
        with patch.object(app_mod, "_execute_analysis", _blocking_execute):
            resp1 = client.post("/analyze", json={"descriptor": {"a": 1}})
            assert resp1.status_code == 202

            time.sleep(0.1)

            resp2 = client.post("/analyze", json={"descriptor": {"b": 2}})
            assert resp2.status_code == 503


class TestGetAnalyze:
    def test_not_found(self, client: TestClient):
        resp = client.get("/analyze", params={"run_key": "nonexistent"})
        assert resp.status_code == 404

    def test_missing_run_key_returns_400(self, client: TestClient):
        resp = client.get("/analyze")
        assert resp.status_code == 400

    def test_returns_running_job(self, client: TestClient):
        with patch.object(app_mod, "_execute_analysis", _blocking_execute):
            post = client.post("/analyze", json={"descriptor": {"x": 1}})
            run_key = post.json()["run_key"]

            time.sleep(0.1)

            get = client.get("/analyze", params={"run_key": run_key})
            assert get.status_code == 202
            assert get.json()["status"] == "running"
            assert "recent_logs" not in get.json()

    def test_running_job_includes_logs_when_verbose(self, client: TestClient):
        with patch.object(app_mod, "_execute_analysis", _blocking_execute):
            post = client.post("/analyze", json={"descriptor": {"x": 1}, "verbose": True})
            run_key = post.json()["run_key"]

            time.sleep(0.1)

            get = client.get("/analyze", params={"run_key": run_key})
            assert get.status_code == 202
            assert get.json()["recent_logs"] == ["live log line"]

    def test_running_job_can_explicitly_suppress_logs(self, client: TestClient):
        with patch.object(app_mod, "_execute_analysis", _blocking_execute):
            post = client.post("/analyze", json={"descriptor": {"x": 1}, "verbose": True})
            run_key = post.json()["run_key"]

            time.sleep(0.1)

            get = client.get("/analyze", params={"run_key": run_key, "include_logs": "false"})
            assert get.status_code == 202
            assert "recent_logs" not in get.json()


class TestFullPollingFlow:
    def test_post_then_poll_to_success(self, client: TestClient):
        with patch.object(app_mod, "_execute_analysis", _mock_execute):
            post = client.post("/analyze", json={"descriptor": {"test": True}})
            assert post.status_code == 202
            run_key = post.json()["run_key"]

            time.sleep(0.2)

            get = client.get("/analyze", params={"run_key": run_key})
            assert get.status_code == 200
            body = get.json()
            assert body["status"] == "succeeded"
            assert body["protocol"] == "test_proto"
            assert body["has_criticals"] is False
            assert "summary_report" in body
            assert "results_json" in body


class TestClientCli:
    def test_creates_output_dir_and_status_artifact_for_criticals(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
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

        assert exit_code == 2
        assert output_dir.is_dir()

        status = json.loads((output_dir / "analysis_status.json").read_text())
        assert status["status"] == "failed"
        assert status["has_criticals"] is False
        assert status["error"] == "remote analysis failed"

    def test_creates_output_dir_when_request_raises(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        def _mock_run_analysis(**kwargs):
            raise RuntimeError("connection dropped")

        exit_code, output_dir = _run_client(monkeypatch, tmp_path, _mock_run_analysis)

        assert exit_code == 2
        assert output_dir.is_dir()

        status = json.loads((output_dir / "analysis_status.json").read_text())
        assert status["status"] == "failed"
        assert status["has_criticals"] is False
        assert "RuntimeError: connection dropped" in status["error"]


class TestClientAuthRefresh:
    def test_start_analysis_refreshes_token_for_each_retry(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        descriptor = tmp_path / "descriptor.json"
        descriptor.write_text("{}")

        seen_tokens: list[str | None] = []
        responses = [
            httpx.Response(504, request=httpx.Request("POST", "http://service.test/analyze")),
            httpx.Response(502, request=httpx.Request("POST", "http://service.test/analyze")),
            httpx.Response(
                202,
                request=httpx.Request("POST", "http://service.test/analyze"),
                json={"run_key": "rk", "status": "queued"},
            ),
        ]
        token_counter = {"value": 0}

        def _next_token() -> str:
            token_counter["value"] += 1
            return f"token-{token_counter['value']}"

        def _fake_post(url: str, *, json: dict, headers: dict[str, str], timeout: httpx.Timeout) -> httpx.Response:
            del url, json, timeout
            seen_tokens.append(headers.get("Authorization"))
            return responses.pop(0)

        monkeypatch.setattr(client_mod.httpx, "post", _fake_post)
        monkeypatch.setattr(client_mod.time, "sleep", lambda _: None)
        monkeypatch.setattr(client_mod, "_MAX_HTTP_RETRIES", 2)

        result = client_mod.start_analysis(
            service_url="http://service.test",
            descriptor_path=descriptor,
            get_auth_token=_next_token,
        )

        assert result == {"run_key": "rk", "status": "queued"}
        assert seen_tokens == ["Bearer token-1", "Bearer token-2", "Bearer token-3"]

    def test_poll_analysis_refreshes_token_for_each_retry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen_tokens: list[str | None] = []
        responses = [
            httpx.Response(504, request=httpx.Request("GET", "http://service.test/analyze")),
            httpx.Response(502, request=httpx.Request("GET", "http://service.test/analyze")),
            httpx.Response(
                202,
                request=httpx.Request("GET", "http://service.test/analyze"),
                json={"status": "running"},
            ),
        ]
        token_counter = {"value": 0}

        def _next_token() -> str:
            token_counter["value"] += 1
            return f"token-{token_counter['value']}"

        def _fake_get(
            url: str,
            *,
            headers: dict[str, str],
            params: dict[str, str],
            timeout: httpx.Timeout,
        ) -> httpx.Response:
            del url, params, timeout
            seen_tokens.append(headers.get("Authorization"))
            return responses.pop(0)

        monkeypatch.setattr(client_mod.httpx, "get", _fake_get)
        monkeypatch.setattr(client_mod.time, "sleep", lambda _: None)
        monkeypatch.setattr(client_mod, "_MAX_HTTP_RETRIES", 2)

        result = client_mod.poll_analysis(
            service_url="http://service.test",
            run_key="rk",
            get_auth_token=_next_token,
            include_logs=True,
        )

        assert result == {"status": "running"}
        assert seen_tokens == ["Bearer token-1", "Bearer token-2", "Bearer token-3"]
