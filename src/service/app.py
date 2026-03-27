"""FastAPI application — async job-based /analyze endpoint.

``POST /analyze`` starts (or resumes) an analysis and returns immediately.
``GET  /analyze`` polls job status or retrieves the final result.
``GET  /health``   liveness probe.

Run-scoped identity: when OIDC auth is enabled, jobs are keyed by
``(repository, run_id, run_attempt)`` from the GitHub JWT claims.
When OIDC is disabled (local dev), the POST generates a UUID key that the
client passes back via query parameter on GET.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import tempfile
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import jwt
import uvicorn
from fastapi import FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator

from utils.bundle_zip import (
    BundleError,
    decode_bundle_zip_from_base64,
    normalize_bundle_entrypoint,
    safe_extract_bundle_zip,
)

from .auth import (
    GITHUB_OIDC_ISSUER,
    derive_run_key,
    extract_caller_metadata,
    verify_request_token,
)
from .config import ServiceConfig, load_config
from .jobs import AnalysisJob, JobRegistry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global state (populated at startup)
# ---------------------------------------------------------------------------
_config: ServiceConfig | None = None
_registry: JobRegistry | None = None
_analysis_semaphore: asyncio.Semaphore | None = None
_cleanup_task: asyncio.Task | None = None

_MAX_CONCURRENT_ANALYSES = 1
_ANALYSIS_TIMEOUT_SECONDS = 60 * 45  # 45 minutes


def get_config() -> ServiceConfig:
    assert _config is not None, "Service not initialised"
    return _config


def get_registry() -> JobRegistry:
    assert _registry is not None, "Service not initialised"
    return _registry


def get_semaphore() -> asyncio.Semaphore:
    assert _analysis_semaphore is not None, "Service not initialised"
    return _analysis_semaphore


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
async def _periodic_cleanup(registry: JobRegistry, interval: int = 60) -> None:
    """Background loop that evicts expired jobs."""
    while True:
        await asyncio.sleep(interval)
        try:
            await registry.cleanup_expired()
        except Exception:
            logger.exception("[SERVICE] Job cleanup error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _config, _registry, _analysis_semaphore, _cleanup_task
    _config = load_config()
    _registry = JobRegistry(
        retention_ttl_seconds=_config.job_retention_ttl,
        max_log_lines=_config.max_retained_log_lines,
    )
    _analysis_semaphore = asyncio.Semaphore(_MAX_CONCURRENT_ANALYSES)
    _cleanup_task = asyncio.create_task(_periodic_cleanup(_registry))

    if _config.disable_oidc_auth:
        logger.warning(
            "[SERVICE] DISABLE_OIDC_AUTH is set — JWT verification is disabled; "
            "do not expose this instance to untrusted networks"
        )
    else:
        if _config.oidc_issuer != GITHUB_OIDC_ISSUER:
            if not os.getenv("ALLOW_CUSTOM_OIDC"):
                raise RuntimeError(
                    f"Non-standard OIDC issuer '{_config.oidc_issuer}' requires "
                    "ALLOW_CUSTOM_OIDC=true to be set explicitly"
                )
            logger.warning("[SERVICE] Using custom OIDC issuer: %s", _config.oidc_issuer)

    logger.info(
        "[SERVICE] Starting — host=%s port=%s oidc_auth=%s allowed_repos=%s",
        _config.host,
        _config.port,
        "off" if _config.disable_oidc_auth else "on",
        _config.allowed_repos,
    )
    yield
    if _cleanup_task:
        _cleanup_task.cancel()
    logger.info("[SERVICE] Shutting down")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="ERC-7730 Analyzer Service",
    version="0.2.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

_MAX_BODY_BYTES = 5 * 1024 * 1024  # 5 MB


@app.middleware("http")
async def _security_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > _MAX_BODY_BYTES:
        return JSONResponse(status_code=413, content={"detail": "Payload too large"})

    response: Response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = "default-src 'none'"
    response.headers["X-Request-ID"] = request_id
    return response


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------
class AnalyzeRequest(BaseModel):
    """Payload sent by the CI client."""

    descriptor: dict[str, Any] | None = Field(
        None,
        description="Full ERC-7730 JSON descriptor (omit when using descriptor_bundle_base64)",
    )
    descriptor_filename: str = Field("calldata-unknown.json", description="Original filename", max_length=255)
    abi: dict[str, Any] | list[Any] | None = Field(None, description="Optional ABI override")
    descriptor_bundle_base64: str | None = Field(
        None,
        description="Zip of descriptor tree (standard base64); requires bundle_entrypoint",
    )
    bundle_entrypoint: str | None = Field(
        None,
        max_length=1024,
        description="POSIX path within the zip to the entry descriptor JSON",
    )

    analysis_mode: Literal["single", "multi"] | None = Field(None, description="single / multi")
    model: str | None = Field(None, max_length=64)
    reasoning_effort: Literal["low", "medium", "high"] | None = Field(None)

    lookback_days: int | None = Field(None, ge=1, le=90)
    max_concurrent_api_calls: int | None = Field(None, ge=1, le=50)
    max_api_retries: int | None = Field(None, ge=1, le=10)

    max_selector_tool_rounds: int | None = Field(None, ge=1, le=10)
    max_tool_requests_per_round: int | None = Field(None, ge=1, le=10)

    enable_screenshots: bool | None = Field(None)
    screenshot_device: Literal["stax", "flex"] | None = Field(None)
    verbose: bool | None = Field(None, description="Enable detailed live logs during polling")

    @model_validator(mode="after")
    def _validate_descriptor_or_bundle(self) -> AnalyzeRequest:
        has_bundle = bool(
            self.descriptor_bundle_base64 and self.bundle_entrypoint and str(self.bundle_entrypoint).strip()
        )
        has_desc = self.descriptor is not None
        if has_bundle and has_desc:
            raise ValueError("Send either descriptor or descriptor_bundle_base64+bundle_entrypoint, not both")
        if has_bundle:
            return self
        if has_desc:
            return self
        raise ValueError("descriptor, or descriptor_bundle_base64+bundle_entrypoint, is required")


class HealthResponse(BaseModel):
    status: str = "ok"


# ---------------------------------------------------------------------------
# Auth / identity helpers
# ---------------------------------------------------------------------------
async def _authenticate(
    cfg: ServiceConfig,
    authorization: str | None,
) -> dict[str, Any] | None:
    """Verify JWT and return claims, or ``None`` if auth is disabled."""
    if cfg.disable_oidc_auth:
        return None
    try:
        return await verify_request_token(
            authorization,
            allowed_repos=cfg.allowed_repos,
            issuer=cfg.oidc_issuer,
        )
    except jwt.exceptions.PyJWTError as exc:
        logger.warning("[AUTH] OIDC verification failed: %s", exc)
        raise HTTPException(status_code=401, detail="Authentication failed") from None


def _resolve_run_key(
    claims: dict[str, Any] | None,
    query_run_key: str | None,
) -> str:
    """Derive the run key from JWT claims or fall back to a query parameter."""
    if claims is not None:
        try:
            return derive_run_key(claims)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
    if query_run_key:
        return query_run_key
    raise HTTPException(
        status_code=400,
        detail="run_key query parameter is required when OIDC auth is disabled",
    )


# ---------------------------------------------------------------------------
# Background analysis execution
# ---------------------------------------------------------------------------
class _JobLogHandler(logging.Handler):
    """Forwards live log records into the job's log buffer."""

    def __init__(self, job: AnalysisJob, max_lines: int):
        super().__init__()
        self._job = job
        self._max_lines = max_lines

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            self._job.append_log(msg, max_lines=self._max_lines)
        except Exception:
            pass


def _build_report_payload(
    results: dict[str, Any],
    tmp_dir: Path,
    safe_filename: str,
) -> dict[str, Any]:
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
        or safe_filename.replace("calldata-", "").replace(".json", "")
    )
    context_id = re.sub(r"[^a-zA-Z0-9_-]", "_", protocol_name)[:64]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    summary_file = report_dir / f"FULL_REPORT_{context_id}_{ts}.md"
    generate_summary_file(results, summary_file, inline_base64=True)

    criticals_file = report_dir / f"CRITICALS_{context_id}_{ts}.md"
    generate_criticals_report(results, criticals_file, inline_base64=True)

    has_criticals = False
    if criticals_file.exists():
        content = criticals_file.read_text()
        has_criticals = "| 🔴" in content

    return {
        "protocol": context_id,
        "has_criticals": has_criticals,
        "summary_report": summary_file.read_text() if summary_file.exists() else "",
        "criticals_report": criticals_file.read_text() if criticals_file.exists() else "",
        "results_json": results,
    }


async def _execute_analysis(
    *,
    job: AnalysisJob,
    descriptor_path: Path,
    abi_path: Path | None,
    safe_filename: str,
    include_root: Path,
    cfg: ServiceConfig,
    overrides: AnalyzeRequest,
    semaphore: asyncio.Semaphore,
    max_log_lines: int,
) -> None:
    """Background coroutine: acquire semaphore, run analysis, update job."""
    handler = _JobLogHandler(job, max_log_lines)
    root_logger = logging.getLogger()
    utils_logger = logging.getLogger("utils")
    utils_logger_level = utils_logger.level
    loop = asyncio.get_running_loop()
    handler.setLevel(logging.INFO if job.verbose else logging.WARNING)

    def _report_progress(message: str) -> None:
        loop.call_soon_threadsafe(job.set_status, "running", message)

    try:
        async with semaphore:
            job.set_status("running", "Starting analysis")

            os.environ["ETHERSCAN_API_KEY"] = cfg.etherscan_api_key
            os.environ["OPENAI_API_KEY"] = cfg.openai_api_key
            if cfg.coredao_api_key:
                os.environ["COREDAO_API_KEY"] = cfg.coredao_api_key
            if cfg.infura_rpc_key:
                os.environ["INFURA_RPC_KEY"] = cfg.infura_rpc_key
            if cfg.gating_token:
                os.environ["GATING_TOKEN"] = cfg.gating_token
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
                progress_callback=_report_progress,
            )

            utils_logger.setLevel(logging.INFO if job.verbose else logging.WARNING)
            root_logger.addHandler(handler)
            try:
                results = await asyncio.wait_for(
                    asyncio.to_thread(
                        analyzer.analyze,
                        descriptor_path,
                        abi_path,
                        None,  # raw_txs
                        None,  # prepared_inputs
                        include_root=include_root,
                    ),
                    timeout=_ANALYSIS_TIMEOUT_SECONDS,
                )
            finally:
                root_logger.removeHandler(handler)

            if not results or not isinstance(results, dict):
                job.set_error("Analysis returned no results")
                return

            job.set_status("running", "Generating reports")
            payload = _build_report_payload(results, job.tmp_dir, safe_filename)
            job.set_result(payload)

    except asyncio.CancelledError:
        job.set_error("Analysis cancelled")
    except TimeoutError:
        job.set_error("Analysis timed out")
    except Exception:
        logger.exception("[SERVICE] Analysis failed for %s", job.run_key)
        job.set_error("Internal analysis error")
    finally:
        utils_logger.setLevel(utils_logger_level)
        job.cleanup_tmp()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse()


@app.post("/analyze")
async def analyze_start(
    body: AnalyzeRequest,
    authorization: str | None = Header(None),
):
    """Start an analysis or return the existing job for this run.

    Returns ``202 Accepted`` when the job is queued/running, or
    ``200 OK`` if the same run already completed.
    """
    cfg = get_config()
    registry = get_registry()
    semaphore = get_semaphore()

    claims = await _authenticate(cfg, authorization)

    if claims is not None:
        run_key = derive_run_key(claims)
        caller_meta = extract_caller_metadata(claims)
    else:
        run_key = f"local:{uuid.uuid4()}"
        caller_meta = {}

    job, created = await registry.create_or_get(run_key, caller_metadata=caller_meta)
    if created:
        job.verbose = bool(body.verbose)

    if not created:
        status_code = 200 if job.is_terminal else 202
        return JSONResponse(
            status_code=status_code,
            content=job.to_status_dict(
                include_result=(job.status == "succeeded"),
                poll_after_seconds=cfg.poll_interval_hint,
            ),
        )

    if semaphore.locked():
        await registry.remove(run_key)
        raise HTTPException(status_code=503, detail="Service at capacity, try again later")

    tmp_dir = Path(tempfile.mkdtemp(prefix="erc7730_svc_"))
    job.tmp_dir = tmp_dir
    include_root = tmp_dir
    task_created = False

    try:
        if body.descriptor_bundle_base64 and body.bundle_entrypoint:
            entry_rel = normalize_bundle_entrypoint(body.bundle_entrypoint)
            raw_zip = decode_bundle_zip_from_base64(body.descriptor_bundle_base64)
            safe_extract_bundle_zip(raw_zip, tmp_dir)
            descriptor_path = (tmp_dir / entry_rel).resolve()
            try:
                descriptor_path.relative_to(tmp_dir.resolve())
            except ValueError as exc:
                raise HTTPException(
                    status_code=400,
                    detail="bundle entrypoint escapes extract directory",
                ) from exc
            if not descriptor_path.is_file():
                raise HTTPException(status_code=400, detail="bundle entrypoint not found")
            safe_filename = descriptor_path.name
        else:
            safe_filename = Path(body.descriptor_filename).name
            if not safe_filename or safe_filename.startswith("."):
                safe_filename = "descriptor.json"
            descriptor_path = tmp_dir / safe_filename
            if body.descriptor is None:
                raise HTTPException(status_code=400, detail="descriptor is required")
            descriptor_path.write_text(json.dumps(body.descriptor, indent=2))

        abi_path: Path | None = None
        if body.abi:
            abi_path = tmp_dir / "abi.json"
            abi_path.write_text(json.dumps(body.abi, indent=2))

        task = asyncio.create_task(
            _execute_analysis(
                job=job,
                descriptor_path=descriptor_path,
                abi_path=abi_path,
                safe_filename=safe_filename,
                include_root=include_root,
                cfg=cfg,
                overrides=body,
                semaphore=semaphore,
                max_log_lines=registry.max_log_lines,
            )
        )
        job._task = task
        task_created = True
    except BundleError as exc:
        await registry.remove(run_key)
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except HTTPException:
        await registry.remove(run_key)
        raise
    except Exception:
        if not task_created:
            await registry.remove(run_key)
        raise

    return JSONResponse(
        status_code=202,
        content=job.to_status_dict(poll_after_seconds=cfg.poll_interval_hint),
    )


@app.get("/analyze")
async def analyze_status(
    authorization: str | None = Header(None),
    run_key: str | None = Query(None, description="Required when OIDC auth is disabled"),
    include_logs: bool | None = Query(None, description="Include live log lines for running jobs"),
):
    """Poll the status of a running analysis or retrieve the final result.

    Returns ``404`` when no job exists, ``202`` when queued/running,
    or ``200`` with the full result payload when finished.
    """
    cfg = get_config()
    registry = get_registry()

    claims = await _authenticate(cfg, authorization)
    resolved_key = _resolve_run_key(claims, run_key)

    job = await registry.get(resolved_key)
    if job is None:
        raise HTTPException(status_code=404, detail="No analysis found for this run")

    include_result = job.status == "succeeded"
    effective_include_logs = job.verbose if include_logs is None else include_logs
    status_code = 200 if job.is_terminal else 202

    return JSONResponse(
        status_code=status_code,
        content=job.to_status_dict(
            include_result=include_result,
            include_logs=effective_include_logs,
            poll_after_seconds=cfg.poll_interval_hint,
        ),
    )


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
        workers=1,
        limit_concurrency=20,
        log_level="info",
    )


if __name__ == "__main__":
    main()
