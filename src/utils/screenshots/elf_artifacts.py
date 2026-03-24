"""Helpers to fetch Ethereum app ELF files from app-ethereum CI artifacts."""

from __future__ import annotations

import io
import json
import logging
import zipfile
from pathlib import Path
from typing import Any, TypedDict

import requests

logger = logging.getLogger(__name__)

DEFAULT_OWNER = "LedgerHQ"
DEFAULT_REPO = "app-ethereum"
DEFAULT_BRANCH = "develop"
DEFAULT_WORKFLOW_NAME = "Build and run functional tests using ragger through reusable workflow"
DEFAULT_ARTIFACT_NAME = "ragger_elfs"
DEFAULT_API_VERSION = "2022-11-28"
STAMP_FILENAME = ".erc7730_analyzer_app_elf.json"
DEVICE_ALIASES = {
    "nanosp": "nanos2",
}


class LatestElfResult(TypedDict):
    elf_path: str
    artifact_id: int
    run_id: int
    head_sha: str
    artifact_name: str
    updated: bool


def normalize_device_name(device: str) -> str:
    """Map analyzer/device-sdk aliases to artifact directory names."""
    device_name = (device or "").strip().lower()
    return DEVICE_ALIASES.get(device_name, device_name)


def read_latest_elf_stamp(output_root: Path) -> dict[str, Any] | None:
    """Load the local ELF artifact stamp if present and valid."""
    stamp_path = Path(output_root) / STAMP_FILENAME
    if not stamp_path.is_file():
        return None
    try:
        data = json.loads(stamp_path.read_text())
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def fetch_latest_ethereum_app_elf(
    *,
    token: str,
    device: str,
    output_root: str | Path,
    owner: str = DEFAULT_OWNER,
    repo: str = DEFAULT_REPO,
    branch: str = DEFAULT_BRANCH,
    workflow_name: str = DEFAULT_WORKFLOW_NAME,
    artifact_name: str = DEFAULT_ARTIFACT_NAME,
    timeout: int = 60,
) -> LatestElfResult:
    """Fetch the latest successful artifact-backed Ethereum app ELF for one device.

    The helper checks the latest successful workflow run, finds the configured
    merged build artifact, and only downloads the zip if the run/artifact/head
    SHA changed since the last successful extraction.
    """
    normalized_device = normalize_device_name(device)
    output_dir = Path(output_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    elf_relpath = Path(normalized_device) / "bin" / "app.elf"
    elf_abspath = output_dir / elf_relpath
    stamp_path = output_dir / STAMP_FILENAME

    session = requests.Session()
    session.headers.update(_headers(token))

    run = _get_latest_successful_run(
        session,
        owner=owner,
        repo=repo,
        branch=branch,
        workflow_name=workflow_name,
        timeout=timeout,
    )
    artifact = _get_artifact_for_run(
        session,
        owner=owner,
        repo=repo,
        run_id=int(run["id"]),
        artifact_name=artifact_name,
        timeout=timeout,
    )

    existing_stamp = read_latest_elf_stamp(output_dir) or {}
    if (
        elf_abspath.is_file()
        and existing_stamp.get("run_id") == int(run["id"])
        and existing_stamp.get("artifact_id") == int(artifact["id"])
        and existing_stamp.get("head_sha") == str(run.get("head_sha") or "")
        and existing_stamp.get("device") == normalized_device
        and existing_stamp.get("artifact_name") == artifact_name
    ):
        logger.info(
            "[SCREENSHOTS][SETUP] Ethereum ELF already current for %s (run=%s artifact=%s)",
            normalized_device,
            run["id"],
            artifact["id"],
        )
        return {
            "elf_path": str(elf_abspath),
            "artifact_id": int(artifact["id"]),
            "run_id": int(run["id"]),
            "head_sha": str(run.get("head_sha") or ""),
            "artifact_name": artifact_name,
            "updated": False,
        }

    logger.info(
        "[SCREENSHOTS][SETUP] Downloading %s from %s/%s run=%s artifact=%s for %s",
        artifact_name,
        owner,
        repo,
        run["id"],
        artifact["id"],
        normalized_device,
    )
    zip_bytes = _download_artifact_zip(
        session,
        owner=owner,
        repo=repo,
        artifact_id=int(artifact["id"]),
        timeout=max(timeout, 120),
    )
    _extract_member_from_zip(zip_bytes, member=str(elf_relpath).replace("\\", "/"), output_path=elf_abspath)

    stamp_payload = {
        "owner": owner,
        "repo": repo,
        "branch": branch,
        "workflow_name": workflow_name,
        "artifact_name": artifact_name,
        "run_id": int(run["id"]),
        "artifact_id": int(artifact["id"]),
        "head_sha": str(run.get("head_sha") or ""),
        "device": normalized_device,
        "elf_path": str(elf_relpath).replace("\\", "/"),
    }
    stamp_path.write_text(json.dumps(stamp_payload, indent=2))
    logger.info(
        "[SCREENSHOTS][SETUP] Updated Ethereum ELF for %s at %s",
        normalized_device,
        elf_abspath,
    )

    return {
        "elf_path": str(elf_abspath),
        "artifact_id": int(artifact["id"]),
        "run_id": int(run["id"]),
        "head_sha": str(run.get("head_sha") or ""),
        "artifact_name": artifact_name,
        "updated": True,
    }


def download_artifact_zip(
    *,
    token: str,
    owner: str = DEFAULT_OWNER,
    repo: str = DEFAULT_REPO,
    artifact_id: int,
    timeout: int = 120,
) -> bytes:
    """Download one GitHub Actions artifact zip."""
    session = requests.Session()
    session.headers.update(_headers(token))
    return _download_artifact_zip(
        session,
        owner=owner,
        repo=repo,
        artifact_id=artifact_id,
        timeout=timeout,
    )


def latest_run_and_artifact(
    *,
    token: str,
    owner: str = DEFAULT_OWNER,
    repo: str = DEFAULT_REPO,
    branch: str = DEFAULT_BRANCH,
    workflow_name: str = DEFAULT_WORKFLOW_NAME,
    artifact_name: str = DEFAULT_ARTIFACT_NAME,
    timeout: int = 60,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the latest successful run and matching artifact metadata."""
    session = requests.Session()
    session.headers.update(_headers(token))
    run = _get_latest_successful_run(
        session,
        owner=owner,
        repo=repo,
        branch=branch,
        workflow_name=workflow_name,
        timeout=timeout,
    )
    artifact = _get_artifact_for_run(
        session,
        owner=owner,
        repo=repo,
        run_id=int(run["id"]),
        artifact_name=artifact_name,
        timeout=timeout,
    )
    return run, artifact


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": DEFAULT_API_VERSION,
    }


def _get_latest_successful_run(
    session: requests.Session,
    *,
    owner: str,
    repo: str,
    branch: str,
    workflow_name: str,
    timeout: int,
) -> dict[str, Any]:
    resp = session.get(
        f"https://api.github.com/repos/{owner}/{repo}/actions/runs",
        params={
            "branch": branch,
            "status": "completed",
            "per_page": 20,
        },
        timeout=timeout,
    )
    resp.raise_for_status()

    for run in resp.json().get("workflow_runs", []):
        if run.get("name") == workflow_name and run.get("conclusion") == "success":
            return run

    raise RuntimeError(
        f"No successful workflow run named {workflow_name!r} found on branch {branch!r} for {owner}/{repo}"
    )


def _get_artifact_for_run(
    session: requests.Session,
    *,
    owner: str,
    repo: str,
    run_id: int,
    artifact_name: str,
    timeout: int,
) -> dict[str, Any]:
    resp = session.get(
        f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}/artifacts",
        params={"per_page": 30},
        timeout=timeout,
    )
    resp.raise_for_status()

    for artifact in resp.json().get("artifacts", []):
        if artifact.get("name") == artifact_name and not artifact.get("expired", False):
            return artifact

    raise RuntimeError(f"Artifact {artifact_name!r} not found (or expired) in run {run_id} for {owner}/{repo}")


def _download_artifact_zip(
    session: requests.Session,
    *,
    owner: str,
    repo: str,
    artifact_id: int,
    timeout: int,
) -> bytes:
    resp = session.get(
        f"https://api.github.com/repos/{owner}/{repo}/actions/artifacts/{artifact_id}/zip",
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.content


def _extract_member_from_zip(zip_bytes: bytes, *, member: str, output_path: Path) -> None:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        members = set(zf.namelist())
        if member not in members:
            raise RuntimeError(
                f"Artifact did not contain {member!r}. Available members include: {', '.join(sorted(list(members))[:10])}"
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(member) as src:
            output_path.write_bytes(src.read())
