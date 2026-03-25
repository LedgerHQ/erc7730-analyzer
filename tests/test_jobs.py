"""Unit tests for the in-memory AnalysisJob model and JobRegistry."""

from __future__ import annotations

from datetime import datetime

import pytest

from service.jobs import AnalysisJob, JobRegistry


# ---------------------------------------------------------------------------
# AnalysisJob
# ---------------------------------------------------------------------------
class TestAnalysisJob:
    def test_initial_state_is_queued(self):
        job = AnalysisJob(run_key="test")
        assert job.status == "queued"
        assert not job.is_terminal

    def test_running_is_not_terminal(self):
        job = AnalysisJob(run_key="test")
        job.set_status("running")
        assert not job.is_terminal

    def test_succeeded_is_terminal(self):
        job = AnalysisJob(run_key="test")
        job.set_status("succeeded")
        assert job.is_terminal

    def test_failed_is_terminal(self):
        job = AnalysisJob(run_key="test")
        job.set_status("failed", "boom")
        assert job.is_terminal
        assert job.status_message == "boom"

    def test_expired_is_terminal(self):
        job = AnalysisJob(run_key="test")
        job.set_status("expired")
        assert job.is_terminal

    def test_set_result_moves_to_succeeded(self):
        job = AnalysisJob(run_key="test")
        job.set_result({"protocol": "foo"})
        assert job.status == "succeeded"
        assert job.result == {"protocol": "foo"}

    def test_set_result_serializes_non_json_types(self):
        job = AnalysisJob(run_key="test")
        job.set_result({"ts": datetime(2024, 1, 1)})
        assert job.result == {"ts": "2024-01-01 00:00:00"}

    def test_set_error_moves_to_failed(self):
        job = AnalysisJob(run_key="test")
        job.set_error("something broke")
        assert job.status == "failed"
        assert job.error == "something broke"

    def test_append_log_truncates(self):
        job = AnalysisJob(run_key="test")
        for i in range(200):
            job.append_log(f"line {i}", max_lines=50)
        assert len(job.log_lines) == 50
        assert job.log_lines[0] == "line 150"
        assert job.log_lines[-1] == "line 199"

    def test_touch_updates_timestamp(self):
        job = AnalysisJob(run_key="test")
        old_ts = job.updated_at
        job.touch()
        assert job.updated_at >= old_ts

    def test_to_status_dict_queued(self):
        job = AnalysisJob(run_key="k")
        d = job.to_status_dict(poll_after_seconds=10)
        assert d["run_key"] == "k"
        assert d["status"] == "queued"
        assert d["poll_after_seconds"] == 10
        assert "error" not in d

    def test_to_status_dict_succeeded_without_result(self):
        job = AnalysisJob(run_key="k")
        job.set_result({"protocol": "x"})
        d = job.to_status_dict(include_result=False)
        assert d["status"] == "succeeded"
        assert "protocol" not in d
        assert "poll_after_seconds" not in d

    def test_to_status_dict_succeeded_with_result(self):
        job = AnalysisJob(run_key="k")
        job.set_result({"protocol": "x", "has_criticals": False})
        d = job.to_status_dict(include_result=True)
        assert d["protocol"] == "x"
        assert d["has_criticals"] is False

    def test_to_status_dict_includes_logs_when_running(self):
        job = AnalysisJob(run_key="k")
        job.set_status("running")
        job.append_log("line 1")
        job.append_log("line 2")
        d = job.to_status_dict(include_logs=True, recent_log_count=1)
        assert d["recent_logs"] == ["line 2"]

    def test_to_status_dict_omits_logs_when_terminal(self):
        job = AnalysisJob(run_key="k")
        job.append_log("line 1")
        job.set_status("succeeded")
        d = job.to_status_dict(include_logs=True)
        assert "recent_logs" not in d

    def test_to_status_dict_failed_includes_error(self):
        job = AnalysisJob(run_key="k")
        job.set_error("kaboom")
        d = job.to_status_dict()
        assert d["error"] == "kaboom"


# ---------------------------------------------------------------------------
# JobRegistry
# ---------------------------------------------------------------------------
class TestJobRegistry:
    async def test_create_new_job(self):
        reg = JobRegistry()
        job, created = await reg.create_or_get("key1")
        assert created
        assert job.run_key == "key1"

    async def test_get_existing_job(self):
        reg = JobRegistry()
        await reg.create_or_get("key1")
        job = await reg.get("key1")
        assert job is not None
        assert job.run_key == "key1"

    async def test_get_missing_returns_none(self):
        reg = JobRegistry()
        assert await reg.get("nope") is None

    async def test_idempotent_create(self):
        reg = JobRegistry()
        j1, c1 = await reg.create_or_get("key1")
        j2, c2 = await reg.create_or_get("key1")
        assert c1 is True
        assert c2 is False
        assert j1 is j2

    async def test_caller_metadata_stored(self):
        reg = JobRegistry()
        meta = {"repository": "org/repo", "workflow": "ci", "ref": "main",
                "sha": "abc", "sub": "s", "run_id": "1", "run_attempt": "1"}
        job, _ = await reg.create_or_get("key1", caller_metadata=meta)
        assert job.repository == "org/repo"
        assert job.workflow == "ci"

    async def test_active_count(self):
        reg = JobRegistry()
        await reg.create_or_get("a")
        await reg.create_or_get("b")
        assert await reg.active_count() == 2

        j, _ = await reg.create_or_get("a")
        j.set_status("succeeded")
        assert await reg.active_count() == 1

    async def test_remove(self):
        reg = JobRegistry()
        await reg.create_or_get("key1")
        await reg.remove("key1")
        assert await reg.get("key1") is None

    async def test_remove_nonexistent_is_noop(self):
        reg = JobRegistry()
        await reg.remove("nope")

    async def test_cleanup_expired_removes_old_terminal(self):
        reg = JobRegistry(retention_ttl_seconds=0)
        j, _ = await reg.create_or_get("key1")
        j.set_status("succeeded")

        removed = await reg.cleanup_expired()
        assert removed == 1
        assert await reg.get("key1") is None

    async def test_cleanup_keeps_active_jobs(self):
        reg = JobRegistry(retention_ttl_seconds=0)
        await reg.create_or_get("key1")

        removed = await reg.cleanup_expired()
        assert removed == 0
        assert await reg.get("key1") is not None

    async def test_cleanup_keeps_fresh_terminal(self):
        reg = JobRegistry(retention_ttl_seconds=3600)
        j, _ = await reg.create_or_get("key1")
        j.set_status("succeeded")

        removed = await reg.cleanup_expired()
        assert removed == 0

    async def test_max_log_lines_property(self):
        reg = JobRegistry(max_log_lines=42)
        assert reg.max_log_lines == 42
