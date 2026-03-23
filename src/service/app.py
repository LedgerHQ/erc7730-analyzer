"""FastAPI application — single /analyze endpoint with SSE streaming.

Usage
-----
    python -m service.app
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import jwt
import uvicorn
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from .auth import verify_request_token
from .config import ServiceConfig, load_config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global config (populated at startup)
# ---------------------------------------------------------------------------
_config: ServiceConfig | None = None


def get_config() -> ServiceConfig:
    assert _config is not None, "Service not initialised"
    return _config


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _config  # noqa: PLW0603
    _config = load_config()

    logger.info(
        "[SERVICE] Starting — host=%s port=%s allowed_repos=%s",
        _config.host,
        _config.port,
        _config.allowed_repos,
    )
    yield
    logger.info("[SERVICE] Shutting down")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="ERC-7730 Analyzer Service",
    version="0.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------
class AnalyzeRequest(BaseModel):
    """Payload sent by the CI client.

    Every field except ``descriptor`` is optional.  When omitted the server
    falls back to its own ``ServiceConfig`` defaults.
    """

    descriptor: dict[str, Any] = Field(..., description="Full ERC-7730 JSON descriptor")
    descriptor_filename: str = Field("calldata-unknown.json", description="Original filename")
    abi: dict[str, Any] | list[Any] | None = Field(None, description="Optional ABI override")

    # LLM
    analysis_mode: str | None = Field(None, description="single / multi")
    model: str | None = Field(None)
    reasoning_effort: str | None = Field(None)

    # Data collection
    lookback_days: int | None = Field(None)
    max_concurrent_api_calls: int | None = Field(None)
    max_api_retries: int | None = Field(None)

    # Agentic
    max_selector_tool_rounds: int | None = Field(None)
    max_tool_requests_per_round: int | None = Field(None)

    # Screenshots (enable_screenshots can override server default per-request)
    enable_screenshots: bool | None = Field(None)
    screenshot_device: str | None = Field(None)


class HealthResponse(BaseModel):
    status: str = "ok"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
class _SSEProgress:
    """Thin adapter that lets the analyzer report progress via SSE."""

    def __init__(self, queue: asyncio.Queue):
        self._q = queue

    def put(self, event_type: str, data: Any):
        self._q.put_nowait({"event": event_type, "data": json.dumps(data) if not isinstance(data, str) else data})


async def _run_analysis(
    descriptor_path: Path,
    abi_path: Path | None,
    cfg: ServiceConfig,
    overrides: AnalyzeRequest,
    progress: _SSEProgress,
) -> dict[str, Any]:
    """Run the analyzer in a thread so we don't block the event loop."""
    # Inject secrets into os.environ for downstream code that reads them
    os.environ["ETHERSCAN_API_KEY"] = cfg.etherscan_api_key
    os.environ["OPENAI_API_KEY"] = cfg.openai_api_key
    if cfg.coredao_api_key:
        os.environ["COREDAO_API_KEY"] = cfg.coredao_api_key
    if cfg.infura_rpc_key:
        os.environ["INFURA_RPC_KEY"] = cfg.infura_rpc_key
    if cfg.gating_token:
        os.environ["GATING_TOKEN"] = cfg.gating_token
    if cfg.github_token:
        os.environ["GITHUB_TOKEN"] = cfg.github_token
    if cfg.cal_service_url:
        os.environ["CAL_SERVICE_URL"] = cfg.cal_service_url
    if cfg.cal_service_staging:
        os.environ["CAL_SERVICE_STAGING"] = cfg.cal_service_staging

    from utils.core import ERC7730Analyzer

    def _or(request_val, server_val):
        return request_val if request_val is not None else server_val

    analyzer = ERC7730Analyzer(
        etherscan_api_key=cfg.etherscan_api_key,
        coredao_api_key=cfg.coredao_api_key,
        lookback_days=_or(overrides.lookback_days, cfg.lookback_days),
        max_concurrent_api_calls=_or(overrides.max_concurrent_api_calls, cfg.max_concurrent_api_calls),
        max_api_retries=_or(overrides.max_api_retries, cfg.max_api_retries),
        analysis_mode=_or(overrides.analysis_mode, cfg.default_analysis_mode),
        max_selector_tool_rounds=_or(overrides.max_selector_tool_rounds, cfg.max_selector_tool_rounds),
        max_tool_requests_per_round=_or(overrides.max_tool_requests_per_round, cfg.max_tool_requests_per_round),
        llm_model=_or(overrides.model, cfg.default_model),
        llm_reasoning_effort=_or(overrides.reasoning_effort, cfg.default_reasoning_effort),
        enable_screenshots=_or(overrides.enable_screenshots, cfg.enable_screenshots),
        screenshot_device=_or(overrides.screenshot_device, cfg.screenshot_device),
        cs_tester_root=cfg.cs_tester_root,
        coin_apps_path=cfg.coin_apps_path,
    )

    progress.put("status", "Analysis started")

    # Intercept log records to stream them as SSE events
    log_queue = progress._q
    _handler = _QueueLogHandler(log_queue)
    _handler.setLevel(logging.INFO)
    root_logger = logging.getLogger()
    root_logger.addHandler(_handler)

    try:
        results = await asyncio.to_thread(
            analyzer.analyze,
            descriptor_path,
            abi_path,
            None,  # raw_txs
            None,  # prepared_inputs
        )
    finally:
        root_logger.removeHandler(_handler)

    return results


class _QueueLogHandler(logging.Handler):
    """Forwards INFO+ log records into the SSE queue as 'log' events."""

    def __init__(self, queue: asyncio.Queue):
        super().__init__()
        self._q = queue

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            self._q.put_nowait({"event": "log", "data": msg})
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse()


@app.post("/analyze")
async def analyze(
    body: AnalyzeRequest,
    authorization: str | None = Header(None),
):
    """Run full ERC-7730 analysis and stream progress via SSE.

    Returns an SSE stream with these event types:
    - ``status``: high-level phase transitions
    - ``log``:    analyzer log lines
    - ``report``: final JSON payload (results + report markdown)
    - ``error``:  fatal error message
    """
    cfg = get_config()

    # --- auth ---
    try:
        await verify_request_token(
            authorization,
            allowed_repos=cfg.allowed_repos,
            issuer=cfg.oidc_issuer,
        )
    except jwt.exceptions.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    # --- write descriptor (and optional ABI) to temp files ---
    tmp_dir = Path(tempfile.mkdtemp(prefix="erc7730_svc_"))
    descriptor_path = tmp_dir / body.descriptor_filename
    descriptor_path.write_text(json.dumps(body.descriptor, indent=2))

    abi_path: Path | None = None
    if body.abi:
        abi_path = tmp_dir / "abi.json"
        abi_path.write_text(json.dumps(body.abi, indent=2))

    queue: asyncio.Queue = asyncio.Queue()
    progress = _SSEProgress(queue)

    async def _event_generator():
        analysis_task = asyncio.create_task(
            _run_analysis(descriptor_path, abi_path, cfg, body, progress)
        )

        try:
            while not analysis_task.done():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=1.0)
                    yield event
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": ""}

            # Drain remaining events
            while not queue.empty():
                yield queue.get_nowait()

            results = analysis_task.result()

            if not results or not isinstance(results, dict):
                yield {"event": "error", "data": "Analysis returned no results"}
                return

            # Generate reports in-memory
            from utils.reporting.reporter import (
                generate_criticals_report,
                generate_summary_file,
            )

            report_dir = tmp_dir / "output"
            report_dir.mkdir(exist_ok=True)

            context = results.get("context", {})
            metadata = results.get("metadata", {})
            protocol_name = (
                context.get("$id")
                or metadata.get("contractName")
                or metadata.get("owner")
                or metadata.get("info", {}).get("legalName")
                or body.descriptor_filename.replace("calldata-", "").replace(".json", "")
            )
            context_id = protocol_name.replace(" ", "_")
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")

            summary_file = report_dir / f"FULL_REPORT_{context_id}_{ts}.md"
            generate_summary_file(results, summary_file, inline_base64=True)

            criticals_file = report_dir / f"CRITICALS_{context_id}_{ts}.md"
            generate_criticals_report(results, criticals_file, inline_base64=True)

            has_criticals = False
            if criticals_file.exists():
                content = criticals_file.read_text()
                has_criticals = "| 🔴" in content

            payload = {
                "protocol": context_id,
                "has_criticals": has_criticals,
                "summary_report": summary_file.read_text() if summary_file.exists() else "",
                "criticals_report": criticals_file.read_text() if criticals_file.exists() else "",
                "results_json": results,
            }

            yield {"event": "report", "data": json.dumps(payload, default=str)}
            yield {"event": "status", "data": "done"}

        except Exception as exc:
            logger.exception("[SERVICE] Analysis failed")
            yield {"event": "error", "data": str(exc)}

    return EventSourceResponse(_event_generator())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="ERC-7730 Analyzer Service")
    parser.add_argument("--host", default=None, help="Bind host (env: SERVICE_HOST)")
    parser.add_argument("--port", type=int, default=None, help="Bind port (env: SERVICE_PORT)")
    args = parser.parse_args()

    cfg = load_config()
    host = args.host or cfg.host
    port = args.port or cfg.port

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    uvicorn.run(
        "service.app:app",
        host=host,
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
