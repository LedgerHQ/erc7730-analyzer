"""Helpers to fetch Ethereum app ELF files from app-ethereum CI artifacts.

Used at Docker **build** time via ``python3 elf_artifacts.py`` (see Dockerfile).
The production service only reads the baked ELF from disk.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import sys
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


class MultiElfFetchResult(TypedDict):
    """Result of baking multiple device ELFs from one artifact zip."""

    run_id: int
    artifact_id: int
    head_sha: str
    artifact_name: str
    devices: dict[str, str]
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


def parse_devices_csv(devices_csv: str) -> list[str]:
    """Split comma-separated device names, normalize order (sorted unique)."""
    parts = [p.strip().lower() for p in devices_csv.replace(";", ",").split(",") if p.strip()]
    if not parts:
        raise ValueError("at least one device name is required")
    seen: set[str] = set()
    ordered: list[str] = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            ordered.append(p)
    return ordered


def _elf_zip_member_for_device(device: str) -> str:
    rel = Path(normalize_device_name(device)) / "bin" / "app.elf"
    return str(rel).replace("\\", "/")


def install_elfs_from_zip(
    zip_bytes: bytes,
    *,
    devices: list[str],
    output_root: str | Path,
) -> dict[str, Path]:
    """Extract ``{device}/bin/app.elf`` for each device from one artifact zip."""
    output_dir = Path(output_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, Path] = {}
    for raw in devices:
        norm = normalize_device_name(raw)
        member = _elf_zip_member_for_device(norm)
        dest = output_dir / Path(member)
        _extract_member_from_zip(zip_bytes, member=member, output_path=dest)
        result[norm] = dest
    return result


def fetch_latest_ethereum_app_elves(
    *,
    token: str,
    devices: list[str],
    output_root: str | Path,
    owner: str = DEFAULT_OWNER,
    repo: str = DEFAULT_REPO,
    branch: str = DEFAULT_BRANCH,
    workflow_name: str = DEFAULT_WORKFLOW_NAME,
    artifact_name: str = DEFAULT_ARTIFACT_NAME,
    timeout: int = 60,
) -> MultiElfFetchResult:
    """Fetch the latest artifact zip once and extract ELFs for every listed device.

    Skips re-download when stamp and on-disk ELFs already match the resolved run.
    """
    normalized = [normalize_device_name(d) for d in devices]
    norm_unique = sorted(set(normalized))
    output_dir = Path(output_root)
    output_dir.mkdir(parents=True, exist_ok=True)
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

    run_id = int(run["id"])
    art_id = int(artifact["id"])
    head_sha = str(run.get("head_sha") or "")

    paths = {d: output_dir / Path(_elf_zip_member_for_device(d)) for d in norm_unique}
    existing_stamp = read_latest_elf_stamp(output_dir) or {}
    stamp_devices = existing_stamp.get("devices")
    stamp_devices_ok = isinstance(stamp_devices, list) and sorted(str(x) for x in stamp_devices) == norm_unique
    all_files = all(p.is_file() for p in paths.values())

    if (
        all_files
        and stamp_devices_ok
        and existing_stamp.get("run_id") == run_id
        and existing_stamp.get("artifact_id") == art_id
        and existing_stamp.get("head_sha") == head_sha
        and existing_stamp.get("artifact_name") == artifact_name
    ):
        logger.info(
            "[SCREENSHOTS][SETUP] Ethereum ELFs already current for %s (run=%s artifact=%s)",
            norm_unique,
            run_id,
            art_id,
        )
        return {
            "run_id": run_id,
            "artifact_id": art_id,
            "head_sha": head_sha,
            "artifact_name": artifact_name,
            "devices": {d: str(paths[d]) for d in norm_unique},
            "updated": False,
        }

    logger.info(
        "[SCREENSHOTS][SETUP] Downloading %s from %s/%s run=%s artifact=%s for devices=%s",
        artifact_name,
        owner,
        repo,
        run_id,
        art_id,
        norm_unique,
    )
    zip_bytes = _download_artifact_zip(
        session,
        owner=owner,
        repo=repo,
        artifact_id=art_id,
        timeout=max(timeout, 120),
    )
    install_elfs_from_zip(zip_bytes, devices=norm_unique, output_root=output_dir)

    stamp_payload = {
        "owner": owner,
        "repo": repo,
        "branch": branch,
        "workflow_name": workflow_name,
        "artifact_name": artifact_name,
        "run_id": run_id,
        "artifact_id": art_id,
        "head_sha": head_sha,
        "devices": norm_unique,
    }
    stamp_path.write_text(json.dumps(stamp_payload, indent=2))
    for d, p in paths.items():
        logger.info("[SCREENSHOTS][SETUP] Updated Ethereum ELF for %s at %s", d, p)

    return {
        "run_id": run_id,
        "artifact_id": art_id,
        "head_sha": head_sha,
        "artifact_name": artifact_name,
        "devices": {d: str(paths[d]) for d in norm_unique},
        "updated": True,
    }


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
    """Fetch the latest successful artifact-backed Ethereum app ELF for one device."""
    norm = normalize_device_name(device)
    multi = fetch_latest_ethereum_app_elves(
        token=token,
        devices=[device],
        output_root=output_root,
        owner=owner,
        repo=repo,
        branch=branch,
        workflow_name=workflow_name,
        artifact_name=artifact_name,
        timeout=timeout,
    )
    elf_path = multi["devices"][norm]
    return {
        "elf_path": elf_path,
        "artifact_id": multi["artifact_id"],
        "run_id": multi["run_id"],
        "head_sha": multi["head_sha"],
        "artifact_name": multi["artifact_name"],
        "updated": multi["updated"],
    }


def install_elfs_from_artifact_id(
    *,
    token: str,
    devices: list[str],
    artifact_id: int,
    output_root: str | Path,
    owner: str = DEFAULT_OWNER,
    repo: str = DEFAULT_REPO,
    timeout: int = 120,
) -> MultiElfFetchResult:
    """Download a specific GitHub Actions artifact zip and extract ELFs for each device."""
    norm_unique = sorted({normalize_device_name(d) for d in devices})
    output_dir = Path(output_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp_path = output_dir / STAMP_FILENAME

    zip_bytes = download_artifact_zip(
        token=token,
        owner=owner,
        repo=repo,
        artifact_id=artifact_id,
        timeout=max(timeout, 120),
    )
    paths = install_elfs_from_zip(zip_bytes, devices=norm_unique, output_root=output_dir)

    stamp_payload = {
        "owner": owner,
        "repo": repo,
        "artifact_id": artifact_id,
        "devices": norm_unique,
        "source": "pinned_artifact_id",
    }
    stamp_path.write_text(json.dumps(stamp_payload, indent=2))
    for d, p in paths.items():
        logger.info("[SCREENSHOTS][BUILD] Installed Ethereum ELF for %s from artifact_id=%s at %s", d, artifact_id, p)

    return {
        "run_id": 0,
        "artifact_id": artifact_id,
        "head_sha": "",
        "artifact_name": "",
        "devices": {d: str(p) for d, p in paths.items()},
        "updated": True,
    }


def install_elf_from_artifact_id(
    *,
    token: str,
    device: str,
    artifact_id: int,
    output_root: str | Path,
    owner: str = DEFAULT_OWNER,
    repo: str = DEFAULT_REPO,
    timeout: int = 120,
) -> LatestElfResult:
    """Download a specific GitHub Actions artifact zip and extract ``{device}/bin/app.elf``."""
    norm = normalize_device_name(device)
    multi = install_elfs_from_artifact_id(
        token=token,
        devices=[device],
        artifact_id=artifact_id,
        output_root=output_root,
        owner=owner,
        repo=repo,
        timeout=timeout,
    )
    return {
        "elf_path": multi["devices"][norm],
        "artifact_id": artifact_id,
        "run_id": 0,
        "head_sha": "",
        "artifact_name": "",
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


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for Docker build stage (fetch ELF into *output-root*)."""
    parser = argparse.ArgumentParser(
        description="Fetch Ethereum app ELF from GitHub Actions (build-time only).",
    )
    parser.add_argument("--output-root", type=Path, required=True, help="Directory for device/bin/app.elf tree")
    parser.add_argument(
        "--devices",
        default="stax,flex",
        help="Comma-separated device names to extract from the artifact (default: stax,flex)",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="Single device (overrides --devices if set; for backward compatibility)",
    )
    parser.add_argument("--artifact-id", type=int, default=None, help="Pin to a specific artifact id (optional)")
    parser.add_argument(
        "--token-file",
        type=Path,
        default=Path("/run/secrets/github_token"),
        help="File containing GitHub PAT (default: BuildKit secret mount path)",
    )
    parser.add_argument("--owner", default=DEFAULT_OWNER)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    parser.add_argument("--workflow-name", default=DEFAULT_WORKFLOW_NAME)
    parser.add_argument("--artifact-name", default=DEFAULT_ARTIFACT_NAME)
    args = parser.parse_args(argv)

    token = (os.environ.get("GITHUB_TOKEN") or "").strip()
    if not token:
        try:
            token = args.token_file.read_text().strip()
        except OSError as exc:
            print(f"Could not read token file {args.token_file}: {exc}", file=sys.stderr)
            return 1
    if not token:
        print("GITHUB_TOKEN is empty (set env or pass a valid --token-file)", file=sys.stderr)
        return 1

    try:
        if args.device:
            devices = parse_devices_csv(args.device)
        else:
            devices = parse_devices_csv(args.devices)
    except ValueError as exc:
        print(f"Invalid --devices/--device: {exc}", file=sys.stderr)
        return 1

    try:
        if args.artifact_id is not None:
            install_elfs_from_artifact_id(
                token=token,
                devices=devices,
                artifact_id=args.artifact_id,
                output_root=args.output_root,
                owner=args.owner,
                repo=args.repo,
            )
        else:
            fetch_latest_ethereum_app_elves(
                token=token,
                devices=devices,
                output_root=args.output_root,
                owner=args.owner,
                repo=args.repo,
                branch=args.branch,
                workflow_name=args.workflow_name,
                artifact_name=args.artifact_name,
            )
    except Exception as exc:
        print(f"ELF fetch failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
