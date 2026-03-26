"""HTTP service tests for descriptor bundle upload."""

import base64
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from utils.bundle_zip import bundle_zip_to_base64


@pytest.fixture
def sync_client(monkeypatch: pytest.MonkeyPatch):
    """Patch background analysis so tests do not run the full analyzer."""
    import service.app as app_module

    monkeypatch.setattr(app_module, "_execute_analysis", AsyncMock())

    from service.app import app

    with TestClient(app) as tc:
        yield tc


def test_post_analyze_single_descriptor(sync_client: TestClient) -> None:
    resp = sync_client.post(
        "/analyze",
        json={
            "descriptor": {"$schema": "x", "context": {"$id": "T"}, "metadata": {}, "display": {"formats": {}}},
            "descriptor_filename": "d.json",
        },
    )
    assert resp.status_code == 202
    body = resp.json()
    assert "run_key" in body


def test_post_analyze_bundle_zip(sync_client: TestClient, tmp_path: Path) -> None:
    root = tmp_path / "bundle"
    (root / "p").mkdir(parents=True)
    main = root / "p" / "m.json"
    inc = root / "q" / "i.json"
    inc.parent.mkdir(parents=True)
    main.write_text(json.dumps({"includes": "../q/i.json", "metadata": {}, "display": {"formats": {}}}))
    inc.write_text(json.dumps({"metadata": {}, "display": {"formats": {}}}))

    b64 = bundle_zip_to_base64(main, root)

    resp = sync_client.post(
        "/analyze",
        json={
            "descriptor_bundle_base64": b64,
            "bundle_entrypoint": "p/m.json",
        },
    )
    assert resp.status_code == 202, resp.text


def test_post_analyze_rejects_descriptor_and_bundle(sync_client: TestClient) -> None:
    resp = sync_client.post(
        "/analyze",
        json={
            "descriptor": {"metadata": {}},
            "descriptor_bundle_base64": "eJwDAAAAAAE=",
            "bundle_entrypoint": "x.json",
        },
    )
    assert resp.status_code == 422


def test_post_analyze_invalid_zip_cleans_up_job_and_tmpdir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import service.app as app_module

    tmp_dir = tmp_path / "svc_invalid_zip"

    def _mkdtemp(*, prefix: str) -> str:
        tmp_dir.mkdir()
        return str(tmp_dir)

    monkeypatch.setattr(app_module, "_execute_analysis", AsyncMock())
    monkeypatch.setattr(app_module.tempfile, "mkdtemp", _mkdtemp)

    from service.app import app

    with TestClient(app) as tc:
        resp = tc.post(
            "/analyze",
            json={
                "descriptor_bundle_base64": base64.standard_b64encode(b"not a zip").decode("ascii"),
                "bundle_entrypoint": "entry.json",
            },
        )

    assert resp.status_code == 400
    assert resp.json() == {"detail": "invalid bundle zip payload"}
    assert not tmp_dir.exists()
    assert app_module._registry is not None
    assert app_module._registry._jobs == {}


def test_post_analyze_missing_bundle_entrypoint_cleans_up_job_and_tmpdir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import service.app as app_module

    tmp_dir = tmp_path / "svc_missing_entry"

    def _mkdtemp(*, prefix: str) -> str:
        tmp_dir.mkdir()
        return str(tmp_dir)

    root = tmp_path / "bundle"
    root.mkdir()
    entry = root / "entry.json"
    entry.write_text(json.dumps({"metadata": {}, "display": {"formats": {}}}))
    b64 = bundle_zip_to_base64(entry, root)

    monkeypatch.setattr(app_module, "_execute_analysis", AsyncMock())
    monkeypatch.setattr(app_module.tempfile, "mkdtemp", _mkdtemp)

    from service.app import app

    with TestClient(app) as tc:
        resp = tc.post(
            "/analyze",
            json={
                "descriptor_bundle_base64": b64,
                "bundle_entrypoint": "missing.json",
            },
        )

    assert resp.status_code == 400
    assert resp.json() == {"detail": "bundle entrypoint not found"}
    assert not tmp_dir.exists()
    assert app_module._registry is not None
    assert app_module._registry._jobs == {}


def test_build_bundle_fields_default_to_descriptor_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from service.client import _build_bundle_fields

    workspace = tmp_path / "workspace"
    descriptor_dir = workspace / "descriptors"
    other_cwd = workspace / "elsewhere"
    descriptor_dir.mkdir(parents=True)
    other_cwd.mkdir()

    descriptor = descriptor_dir / "main.json"
    include_file = descriptor_dir / "include.json"
    descriptor.write_text(json.dumps({"includes": "include.json", "metadata": {}, "display": {"formats": {}}}))
    include_file.write_text(json.dumps({"metadata": {}, "display": {"formats": {}}}))

    monkeypatch.chdir(other_cwd)

    payload = _build_bundle_fields(descriptor, None)

    assert payload["bundle_entrypoint"] == "main.json"
