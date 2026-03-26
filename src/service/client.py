"""Async polling client used by CI to call the remote analyzer service.

Usage from CI::

    python -m service.client \
        --service-url https://analyzer.example.com \
        --descriptor registry/calldata-MyToken.json
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from utils.bundle_zip import (
    BundleError,
    build_descriptor_bundle_zip_bytes,
    default_bundle_root_for_descriptor,
    normalize_bundle_entrypoint,
)

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = httpx.Timeout(connect=30, read=60, write=30, pool=30)
_MAX_POLL_SECONDS = 2700  # 45 minutes


def _use_bundle_mode(descriptor_path: Path, bundle_root: Path | None) -> bool:
    if bundle_root is not None:
        return True
    try:
        data = json.loads(descriptor_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return isinstance(data, dict) and "includes" in data


def _build_bundle_fields(descriptor_path: Path, bundle_root: Path | None) -> dict[str, Any]:
    root = (bundle_root or default_bundle_root_for_descriptor(descriptor_path)).resolve()
    entry = descriptor_path.resolve()
    try:
        rel = entry.relative_to(root)
    except ValueError as exc:
        raise BundleError("descriptor file must be under bundle root") from exc
    entry_rel = rel.as_posix()
    normalize_bundle_entrypoint(entry_rel)
    zip_bytes = build_descriptor_bundle_zip_bytes(entry, root)
    return {
        "descriptor_bundle_base64": base64.standard_b64encode(zip_bytes).decode("ascii"),
        "bundle_entrypoint": entry_rel,
    }


# ---------------------------------------------------------------------------
# OIDC helpers
# ---------------------------------------------------------------------------
def _get_oidc_token(audience: str = "erc7730-analyzer") -> str:
    """Request a short-lived OIDC token from GitHub Actions runtime."""
    request_url = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL")
    request_token = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN")

    if not request_url or not request_token:
        raise RuntimeError(
            "GitHub OIDC env vars (ACTIONS_ID_TOKEN_REQUEST_URL / "
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN) are not set. "
            "Make sure the workflow has `permissions: id-token: write`."
        )

    resp = httpx.get(
        f"{request_url}&audience={audience}",
        headers={"Authorization": f"bearer {request_token}"},
        timeout=10,
    )
    resp.raise_for_status()
    token = resp.json().get("value")
    if not token:
        raise RuntimeError("OIDC token response missing 'value' field")
    return token


# ---------------------------------------------------------------------------
# Core API calls
# ---------------------------------------------------------------------------
def start_analysis(
    *,
    service_url: str,
    descriptor_path: Path,
    abi_path: Path | None = None,
    overrides: dict[str, Any] | None = None,
    auth_token: str | None = None,
    bundle_root: Path | None = None,
) -> dict[str, Any]:
    """``POST /analyze`` — start an analysis and return the initial status."""
    abi = json.loads(abi_path.read_text()) if abi_path else None

    if _use_bundle_mode(descriptor_path, bundle_root):
        payload = _build_bundle_fields(descriptor_path, bundle_root)
    else:
        descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
        payload = {
            "descriptor": descriptor,
            "descriptor_filename": descriptor_path.name,
        }
    if abi is not None:
        payload["abi"] = abi
    if overrides:
        for key, val in overrides.items():
            if val is not None:
                payload[key] = val

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    url = f"{service_url.rstrip('/')}/analyze"

    resp = httpx.post(url, json=payload, headers=headers, timeout=_REQUEST_TIMEOUT)
    if resp.status_code == 401:
        raise PermissionError(f"Authentication failed: {resp.text}")
    if resp.status_code == 503:
        raise RuntimeError(f"Service at capacity: {resp.text}")
    resp.raise_for_status()
    return resp.json()


def poll_analysis(
    *,
    service_url: str,
    run_key: str,
    auth_token: str | None = None,
    include_logs: bool = False,
) -> dict[str, Any]:
    """``GET /analyze`` — poll the job status."""
    headers: dict[str, str] = {}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    url = f"{service_url.rstrip('/')}/analyze"
    params: dict[str, str] = {"include_logs": "true" if include_logs else "false"}
    if not auth_token:
        params["run_key"] = run_key

    resp = httpx.get(url, headers=headers, params=params, timeout=_REQUEST_TIMEOUT)
    if resp.status_code == 401:
        raise PermissionError(f"Authentication failed: {resp.text}")
    resp.raise_for_status()
    return resp.json()


def run_analysis(
    *,
    service_url: str,
    descriptor_path: Path,
    abi_path: Path | None = None,
    overrides: dict[str, Any] | None = None,
    get_auth_token: Callable[[], str | None] | None = None,
    max_poll_seconds: int = _MAX_POLL_SECONDS,
    verbose: bool = False,
    bundle_root: Path | None = None,
) -> dict[str, Any]:
    """Start analysis, poll until completion, and return the final payload.

    ``get_auth_token`` is called before every request so short-lived OIDC
    tokens are refreshed transparently.
    """

    def _token() -> str | None:
        return get_auth_token() if get_auth_token else None

    token = _token()
    print("[CLIENT] Starting analysis...", file=sys.stderr)
    if verbose:
        print("[CLIENT] Verbose live logs enabled", file=sys.stderr)
    start_resp = start_analysis(
        service_url=service_url,
        descriptor_path=descriptor_path,
        abi_path=abi_path,
        overrides=overrides,
        auth_token=token,
        bundle_root=bundle_root,
    )

    run_key = start_resp["run_key"]
    status = start_resp["status"]
    print(f"[CLIENT] Run key: {run_key}", file=sys.stderr)
    print(f"[CLIENT] Status:  {status}", file=sys.stderr)

    if status in ("succeeded", "failed", "expired"):
        return start_resp

    poll_interval = start_resp.get("poll_after_seconds", 5)
    deadline = time.monotonic() + max_poll_seconds
    seen_log_lines: set[str] = set()
    last_status_line: tuple[str, str] | None = None

    while time.monotonic() < deadline:
        time.sleep(poll_interval)

        token = _token()
        resp = poll_analysis(
            service_url=service_url,
            run_key=run_key,
            auth_token=token,
            include_logs=verbose,
        )

        status = resp["status"]
        status_msg = resp.get("status_message", "")

        if verbose:
            for line in resp.get("recent_logs", []):
                if line not in seen_log_lines:
                    seen_log_lines.add(line)
                    print(line, file=sys.stderr)

        status_line = (status, status_msg)
        if status_line != last_status_line:
            print(f"[STATUS] {status}: {status_msg}", file=sys.stderr)
            last_status_line = status_line

        if status in ("succeeded", "failed", "expired"):
            return resp

        poll_interval = min(resp.get("poll_after_seconds", 5), 15)

    raise RuntimeError(f"Analysis timed out after {max_poll_seconds}s (last status: {status})")


# ---------------------------------------------------------------------------
# Output artifacts
# ---------------------------------------------------------------------------
def _prepare_output_dir(output_dir: Path | None) -> Path:
    """Resolve and create the report directory before any network work starts."""
    resolved = output_dir if output_dir else Path.cwd() / "output"
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _write_status_artifact(
    output_dir: Path,
    *,
    status: str,
    protocol: str = "unknown",
    has_criticals: bool = False,
    error: str | None = None,
) -> Path:
    """Persist a small machine-readable status file for CI upload/debugging."""
    status_path = output_dir / "analysis_status.json"
    payload: dict[str, Any] = {
        "status": status,
        "protocol": protocol,
        "has_criticals": has_criticals,
    }
    if error:
        payload["error"] = error
    status_path.write_text(json.dumps(payload, indent=2))
    return status_path


def _write_report_artifacts(output_dir: Path, report: dict[str, Any]) -> tuple[str, bool]:
    """Write any report artifacts returned by the service."""
    protocol = report.get("protocol", "unknown")
    has_criticals = bool(report.get("has_criticals", False))

    if report.get("summary_report"):
        summary_path = output_dir / f"FULL_REPORT_{protocol}.md"
        summary_path.write_text(report["summary_report"])
        print(f"[CLIENT] Full report: {summary_path}", file=sys.stderr)

    if report.get("criticals_report"):
        criticals_path = output_dir / f"CRITICALS_{protocol}.md"
        criticals_path.write_text(report["criticals_report"])
        print(f"[CLIENT] Criticals report: {criticals_path}", file=sys.stderr)

    if "results_json" in report and report["results_json"] is not None:
        json_path = output_dir / f"results_{protocol}.json"
        json_path.write_text(json.dumps(report["results_json"], indent=2, default=str))
        print(f"[CLIENT] JSON results: {json_path}", file=sys.stderr)

    return protocol, has_criticals


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="ERC-7730 Analyzer CI Client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
All --<param> flags correspond 1:1 to AnalyzeRequest fields on the
server.  Omitted flags fall back to the server's default config.

Examples:

  # CI usage (OIDC auto-acquired):
  python -m service.client \\
      --service-url "$ANALYZER_SERVICE_URL" \\
      --descriptor calldata-MyToken.json \\
      --analysis-mode multi

  # Verbose polling with live logs:
  python -m service.client \\
      --service-url "$ANALYZER_SERVICE_URL" \\
      --descriptor calldata-MyToken.json \\
      --verbose

  # Local service with DISABLE_OIDC_AUTH=1:
  python -m service.client --no-auth --service-url http://127.0.0.1:8080 --descriptor ...

        """,
    )

    parser.add_argument("--service-url", required=True, help="Base URL of the analyzer service")
    parser.add_argument("--descriptor", type=Path, required=True, help="Path to ERC-7730 JSON descriptor")
    parser.add_argument("--abi", type=Path, default=None, help="Optional ABI file")
    parser.add_argument(
        "--bundle-root",
        type=Path,
        default=None,
        help="Root directory for resolving includes when uploading a zip bundle (default: descriptor directory)",
    )
    parser.add_argument(
        "--no-auth",
        action="store_true",
        help="Omit bearer token (use when the service runs with DISABLE_OIDC_AUTH)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory to write report artifacts to (default: ./output relative to CWD)",
    )

    parser.add_argument("--analysis-mode", choices=("single", "multi"), default=None, help="Audit strategy")
    parser.add_argument("--model", default=None, help="LLM model name")
    parser.add_argument("--reasoning-effort", choices=("low", "medium", "high"), default=None)

    parser.add_argument("--lookback-days", type=int, default=None, help="Transaction lookback window")
    parser.add_argument("--max-concurrent", type=int, default=None, help="Max concurrent API calls")
    parser.add_argument("--max-retries", type=int, default=None, help="Max API retries")

    parser.add_argument("--max-selector-tool-rounds", type=int, default=None)
    parser.add_argument("--max-tool-requests-per-round", type=int, default=None)

    parser.add_argument("--enable-screenshots", action="store_true", default=None, help="Enable screenshot capture")
    parser.add_argument("--no-screenshots", action="store_true", default=False, help="Explicitly disable screenshots")
    parser.add_argument("--screenshot-device", choices=("stax", "flex"), default=None)
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed live analysis logs during polling",
    )

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    output_dir = _prepare_output_dir(args.output_dir)

    overrides: dict[str, Any] = {}

    if args.analysis_mode:
        overrides["analysis_mode"] = args.analysis_mode
    if args.model:
        overrides["model"] = args.model
    if args.reasoning_effort:
        overrides["reasoning_effort"] = args.reasoning_effort
    if args.lookback_days is not None:
        overrides["lookback_days"] = args.lookback_days
    if args.max_concurrent is not None:
        overrides["max_concurrent_api_calls"] = args.max_concurrent
    if args.max_retries is not None:
        overrides["max_api_retries"] = args.max_retries
    if args.max_selector_tool_rounds is not None:
        overrides["max_selector_tool_rounds"] = args.max_selector_tool_rounds
    if args.max_tool_requests_per_round is not None:
        overrides["max_tool_requests_per_round"] = args.max_tool_requests_per_round
    if args.screenshot_device:
        overrides["screenshot_device"] = args.screenshot_device

    if args.no_screenshots:
        overrides["enable_screenshots"] = False
    elif args.enable_screenshots:
        overrides["enable_screenshots"] = True
    if args.verbose:
        overrides["verbose"] = True

    skip_auth = args.no_auth or os.getenv("DISABLE_OIDC_AUTH", "").lower() in ("1", "true", "yes")
    if skip_auth:
        print("[CLIENT] Skipping OIDC token (DISABLE_OIDC_AUTH or --no-auth)", file=sys.stderr)
        token_getter: Callable[[], str | None] | None = None
    else:
        print("[CLIENT] Will use GitHub OIDC tokens", file=sys.stderr)
        token_getter = _get_oidc_token

    try:
        report = run_analysis(
            service_url=args.service_url,
            descriptor_path=args.descriptor,
            abi_path=args.abi,
            overrides=overrides,
            get_auth_token=token_getter,
            verbose=args.verbose,
            bundle_root=args.bundle_root,
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        status_path = _write_status_artifact(output_dir, status="failed", error=error)
        print(f"[CLIENT] Analysis request failed: {error}", file=sys.stderr)
        print(f"[CLIENT] Status artifact: {status_path}", file=sys.stderr)
        sys.exit(1)

    protocol, has_criticals = _write_report_artifacts(output_dir, report)
    status = report.get("status", "succeeded")

    if status != "succeeded":
        error = report.get("error") or report.get("status_message") or f"Analysis ended with status: {status}"
        status_path = _write_status_artifact(
            output_dir,
            status=status,
            protocol=protocol,
            has_criticals=has_criticals,
            error=error,
        )
        print(f"[CLIENT] Analysis failed: {error}", file=sys.stderr)
        print(f"[CLIENT] Status artifact: {status_path}", file=sys.stderr)
        sys.exit(1)

    status_path = _write_status_artifact(
        output_dir,
        status=status,
        protocol=protocol,
        has_criticals=has_criticals,
    )
    print(f"[CLIENT] Status artifact: {status_path}", file=sys.stderr)

    if has_criticals:
        print("[CLIENT] CRITICAL ISSUES FOUND — exit 1", file=sys.stderr)
        sys.exit(1)
    else:
        print("[CLIENT] No critical issues — exit 0", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
