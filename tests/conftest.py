"""Shared fixtures for the erc7730-analyzer test suite."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
import pytest
from httpx import ASGITransport

os.environ.setdefault("DISABLE_OIDC_AUTH", "true")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("ETHERSCAN_API_KEY", "test-key")

import service.app as app_mod  # noqa: E402
from service.config import load_config  # noqa: E402
from service.jobs import JobRegistry  # noqa: E402


@asynccontextmanager
async def app_client() -> AsyncIterator[httpx.AsyncClient]:
    """Spin up the FastAPI app with in-memory state (no lifespan)."""
    cfg = load_config()
    app_mod._config = cfg
    app_mod._registry = JobRegistry(
        retention_ttl_seconds=cfg.job_retention_ttl,
        max_log_lines=cfg.max_retained_log_lines,
    )
    app_mod._analysis_semaphore = asyncio.Semaphore(1)

    transport = ASGITransport(app=app_mod.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app_mod._config = None
    app_mod._registry = None
    app_mod._analysis_semaphore = None


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with app_client() as c:
        yield c
