"""Thin SSE client used by CI to call the remote analyzer service.

Usage from CI::

    python -m service.client \
        --service-url https://analyzer.example.com \
        --descriptor registry/calldata-MyToken.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)


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
# Core streaming call
# ---------------------------------------------------------------------------
def stream_analysis(
    *,
    service_url: str,
    descriptor_path: Path,
    abi_path: Path | None = None,
    overrides: dict[str, Any] | None = None,
    auth_token: str | None = None,
) -> dict:
    """POST descriptor to the service and consume the SSE stream.

    ``overrides`` is a flat dict of optional fields matching
    ``AnalyzeRequest`` (analysis_mode, model, enable_screenshots, …).
    Returns the final report payload dict, or raises on error.
    """
    descriptor = json.loads(descriptor_path.read_text())
    abi = json.loads(abi_path.read_text()) if abi_path else None

    payload: dict[str, Any] = {
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

    report_payload: dict | None = None
    error_msg: str | None = None

    with httpx.stream(
        "POST",
        url,
        json=payload,
        headers=headers,
        timeout=httpx.Timeout(connect=30, read=600, write=30, pool=30),
    ) as response:
        if response.status_code == 401:
            raise PermissionError(f"Authentication failed: {response.text}")
        response.raise_for_status()

        buf = ""
        current_event = "message"
        for chunk in response.iter_text():
            buf += chunk
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                line = line.rstrip("\r")

                if line.startswith("event:"):
                    current_event = line[len("event:"):].strip()
                elif line.startswith("data:"):
                    data = line[len("data:"):].strip()
                    _handle_sse_event(current_event, data)

                    if current_event == "report":
                        try:
                            report_payload = json.loads(data)
                        except json.JSONDecodeError:
                            pass
                    elif current_event == "error":
                        error_msg = data

                    current_event = "message"
                elif line == "":
                    current_event = "message"

    if error_msg:
        raise RuntimeError(f"Service returned error: {error_msg}")
    if report_payload is None:
        raise RuntimeError("Stream ended without a report event")

    return report_payload


def _handle_sse_event(event_type: str, data: str):
    """Print SSE events to stderr for CI log visibility."""
    if event_type == "log":
        print(data, file=sys.stderr)
    elif event_type == "status":
        print(f"[STATUS] {data}", file=sys.stderr)
    elif event_type == "ping":
        pass
    elif event_type == "error":
        print(f"[ERROR] {data}", file=sys.stderr)
    elif event_type == "report":
        print("[STATUS] Report received", file=sys.stderr)


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

  # Local service with DISABLE_OIDC_AUTH=1:
  python -m service.client --no-auth --service-url http://127.0.0.1:8080 --descriptor ...

        """,
    )

    # Required
    parser.add_argument("--service-url", required=True, help="Base URL of the analyzer service")
    parser.add_argument("--descriptor", type=Path, required=True, help="Path to ERC-7730 JSON descriptor")
    parser.add_argument("--abi", type=Path, default=None, help="Optional ABI file")
    parser.add_argument(
        "--no-auth",
        action="store_true",
        help="Omit bearer token (use when the service runs with DISABLE_OIDC_AUTH)",
    )

    # LLM overrides
    parser.add_argument("--analysis-mode", choices=("single", "multi"), default=None, help="Audit strategy")
    parser.add_argument("--model", default=None, help="LLM model name")
    parser.add_argument("--reasoning-effort", choices=("low", "medium", "high"), default=None)

    # Data collection overrides
    parser.add_argument("--lookback-days", type=int, default=None, help="Transaction lookback window")
    parser.add_argument("--max-concurrent", type=int, default=None, help="Max concurrent API calls")
    parser.add_argument("--max-retries", type=int, default=None, help="Max API retries")

    # Agentic overrides
    parser.add_argument("--max-selector-tool-rounds", type=int, default=None)
    parser.add_argument("--max-tool-requests-per-round", type=int, default=None)

    # Screenshot overrides
    parser.add_argument("--enable-screenshots", action="store_true", default=None, help="Enable screenshot capture")
    parser.add_argument("--no-screenshots", action="store_true", default=False, help="Explicitly disable screenshots")
    parser.add_argument("--screenshot-device", choices=("stax", "flex"), default=None)

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Build overrides dict (only non-None values are sent)
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

    # Screenshots: explicit enable / disable / server default
    if args.no_screenshots:
        overrides["enable_screenshots"] = False
    elif args.enable_screenshots:
        overrides["enable_screenshots"] = True

    skip_auth = args.no_auth or os.getenv("DISABLE_OIDC_AUTH", "").lower() in ("1", "true", "yes")
    if skip_auth:
        print("[CLIENT] Skipping OIDC token (DISABLE_OIDC_AUTH or --no-auth)", file=sys.stderr)
        token = None
    else:
        print("[CLIENT] Requesting GitHub OIDC token...", file=sys.stderr)
        token = _get_oidc_token()

    report = stream_analysis(
        service_url=args.service_url,
        descriptor_path=args.descriptor,
        abi_path=args.abi,
        overrides=overrides,
        auth_token=token,
    )

    # Write reports to output/ relative to the project root (not CWD)
    project_root = Path(__file__).resolve().parent.parent.parent
    output_dir = project_root / "output"
    output_dir.mkdir(exist_ok=True)

    protocol = report.get("protocol", "unknown")
    has_criticals = report.get("has_criticals", False)

    if report.get("summary_report"):
        summary_path = output_dir / f"FULL_REPORT_{protocol}.md"
        summary_path.write_text(report["summary_report"])
        print(f"[CLIENT] Full report: {summary_path}", file=sys.stderr)

    if report.get("criticals_report"):
        criticals_path = output_dir / f"CRITICALS_{protocol}.md"
        criticals_path.write_text(report["criticals_report"])
        print(f"[CLIENT] Criticals report: {criticals_path}", file=sys.stderr)

    if report.get("results_json"):
        json_path = output_dir / f"results_{protocol}.json"
        json_path.write_text(json.dumps(report["results_json"], indent=2, default=str))
        print(f"[CLIENT] JSON results: {json_path}", file=sys.stderr)

    if has_criticals:
        print("[CLIENT] CRITICAL ISSUES FOUND — exit 1", file=sys.stderr)
        sys.exit(1)
    else:
        print("[CLIENT] No critical issues — exit 0", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
