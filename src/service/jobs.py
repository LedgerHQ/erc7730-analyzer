"""In-memory analysis job registry.

Provides the AnalysisJob model and a bounded-retention registry keyed by
run-scoped identifiers derived from GitHub OIDC JWT claims.

This is a transitional single-instance design.  The JobRegistry interface
is intentionally narrow so it can later be swapped for DynamoDB / S3
without reworking the API surface.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

JobStatus = Literal["queued", "running", "succeeded", "failed", "expired"]


@dataclass
class AnalysisJob:
    """Mutable state for one analysis run."""

    run_key: str
    status: JobStatus = "queued"
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    repository: str = ""
    workflow: str = ""
    ref: str = ""
    sha: str = ""
    sub: str = ""
    run_id: str = ""
    run_attempt: str = ""

    status_message: str = ""
    log_lines: list[str] = field(default_factory=list)

    result: dict[str, Any] | None = None
    error: str | None = None

    tmp_dir: Path | None = field(default=None, repr=False)
    _task: asyncio.Task[None] | None = field(default=None, repr=False)

    @property
    def is_terminal(self) -> bool:
        return self.status in ("succeeded", "failed", "expired")

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def append_log(self, line: str, *, max_lines: int = 500) -> None:
        self.log_lines.append(line)
        if len(self.log_lines) > max_lines:
            excess = len(self.log_lines) - max_lines
            del self.log_lines[:excess]
        self.touch()

    def set_status(self, status: JobStatus, message: str = "") -> None:
        self.status = status
        if message:
            self.status_message = message
        self.touch()

    def set_result(self, result: dict[str, Any]) -> None:
        safe = json.loads(json.dumps(result, default=str))
        self.result = safe
        self.set_status("succeeded", "Analysis complete")

    def set_error(self, error: str) -> None:
        self.error = error
        self.set_status("failed", error)

    def cleanup_tmp(self) -> None:
        if self.tmp_dir and self.tmp_dir.exists():
            shutil.rmtree(self.tmp_dir, ignore_errors=True)
            self.tmp_dir = None

    def to_status_dict(
        self,
        *,
        include_result: bool = False,
        include_logs: bool = False,
        poll_after_seconds: int = 5,
        recent_log_count: int = 20,
    ) -> dict[str, Any]:
        """Serialize job state for API responses."""
        d: dict[str, Any] = {
            "run_key": self.run_key,
            "status": self.status,
            "status_message": self.status_message,
            "started_at": self.started_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
        if not self.is_terminal:
            d["poll_after_seconds"] = poll_after_seconds
        if self.error:
            d["error"] = self.error
        if include_result and self.result is not None:
            d.update(self.result)
        if include_logs and self.log_lines and not self.is_terminal:
            d["recent_logs"] = self.log_lines[-recent_log_count:]
        return d


class JobRegistry:
    """Thread-safe in-memory registry with TTL-based eviction."""

    def __init__(self, *, retention_ttl_seconds: int = 3600, max_log_lines: int = 500):
        self._jobs: dict[str, AnalysisJob] = {}
        self._lock = asyncio.Lock()
        self._retention_ttl = retention_ttl_seconds
        self._max_log_lines = max_log_lines

    @property
    def max_log_lines(self) -> int:
        return self._max_log_lines

    async def get(self, run_key: str) -> AnalysisJob | None:
        async with self._lock:
            return self._jobs.get(run_key)

    async def create_or_get(
        self,
        run_key: str,
        *,
        caller_metadata: dict[str, str] | None = None,
    ) -> tuple[AnalysisJob, bool]:
        """Return ``(job, created)``.  Existing jobs are returned unmodified."""
        async with self._lock:
            existing = self._jobs.get(run_key)
            if existing is not None:
                return existing, False

            meta = caller_metadata or {}
            job = AnalysisJob(
                run_key=run_key,
                repository=meta.get("repository", ""),
                workflow=meta.get("workflow", ""),
                ref=meta.get("ref", ""),
                sha=meta.get("sha", ""),
                sub=meta.get("sub", ""),
                run_id=meta.get("run_id", ""),
                run_attempt=meta.get("run_attempt", ""),
            )
            self._jobs[run_key] = job
            return job, True

    async def remove(self, run_key: str) -> None:
        async with self._lock:
            job = self._jobs.pop(run_key, None)
            if job:
                job.cleanup_tmp()

    async def active_count(self) -> int:
        async with self._lock:
            return sum(1 for j in self._jobs.values() if not j.is_terminal)

    async def cleanup_expired(self) -> int:
        """Remove terminal jobs older than retention TTL.  Returns count removed."""
        now = time.time()
        to_remove: list[str] = []
        async with self._lock:
            for key, job in self._jobs.items():
                if job.is_terminal:
                    age = now - job.updated_at.timestamp()
                    if age > self._retention_ttl:
                        to_remove.append(key)
            for key in to_remove:
                job = self._jobs.pop(key)
                job.cleanup_tmp()
        if to_remove:
            logger.info("[JOBS] Evicted %d expired job(s)", len(to_remove))
        return len(to_remove)
