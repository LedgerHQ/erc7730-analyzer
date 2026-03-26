"""Pytest configuration."""

import os

import pytest
from starlette.testclient import TestClient

# Local tests: avoid requiring real OIDC / secrets when importing the service app.
os.environ.setdefault("DISABLE_OIDC_AUTH", "1")


@pytest.fixture
def client():
    """Sync HTTP client against the FastAPI app (runs ASGI lifespan)."""
    from service.app import app

    with TestClient(app) as tc:
        yield tc
