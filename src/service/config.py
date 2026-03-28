"""Service configuration loaded from environment / dotenv."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from dotenv import load_dotenv

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class ServiceConfig:
    """All server-side secrets and tunables.

    Values are read once at startup from env vars / .env.
    CI callers never see any of these.
    """

    # --- secrets ---
    etherscan_api_key: str = ""
    openai_api_key: str = ""
    coredao_api_key: str = ""
    infura_rpc_key: str = ""
    gating_token: str = ""

    # --- CAL service ---
    cal_service_url: str = "https://crypto-assets-service.api.ledger.com"
    cal_service_staging: str = "https://crypto-assets-service.api.ledger-test.com"

    # --- OIDC verification ---
    allowed_repos: list[str] = field(default_factory=list)
    oidc_issuer: str = "https://token.actions.githubusercontent.com"
    disable_oidc_auth: bool = False

    # --- analyzer defaults (overridable per request) ---
    default_model: str = "gpt-5.4-nano"
    default_reasoning_effort: str = "low"
    default_analysis_mode: str = "single"
    lookback_days: int = 7
    max_concurrent_api_calls: int = 2
    max_api_retries: int = 3
    max_selector_tool_rounds: int = 1
    max_tool_requests_per_round: int = 1

    # --- screenshots ---
    enable_screenshots: bool = False
    screenshot_device: str = "stax"
    cs_tester_root: str | None = None
    coin_apps_path: str | None = None

    # --- job registry ---
    job_retention_ttl: int = 3600
    max_retained_log_lines: int = 500
    poll_interval_hint: int = 5
    analysis_timeout_seconds: int = 60 * 60 * 3  # 3 hours

    # --- server ---
    host: str = "0.0.0.0"
    port: int = 8080


def load_config(env_file: str | Path | None = None) -> ServiceConfig:
    """Build config from environment variables."""
    if env_file:
        load_dotenv(env_file, override=True)
    else:
        load_dotenv(override=True)

    raw_repos = os.getenv("ALLOWED_REPOS", "LedgerHQ/clear-signing-erc7730-registry")
    allowed = [r.strip() for r in raw_repos.split(",") if r.strip()]

    return ServiceConfig(
        etherscan_api_key=os.getenv("ETHERSCAN_API_KEY", ""),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        coredao_api_key=os.getenv("COREDAO_API_KEY", ""),
        infura_rpc_key=os.getenv("INFURA_RPC_KEY", ""),
        gating_token=os.getenv("GATING_TOKEN", ""),
        cal_service_url=os.getenv("CAL_SERVICE_URL", "https://crypto-assets-service.api.ledger.com"),
        cal_service_staging=os.getenv("CAL_SERVICE_STAGING", "https://crypto-assets-service.api.ledger-test.com"),
        allowed_repos=allowed,
        oidc_issuer=os.getenv("OIDC_ISSUER_URL", "https://token.actions.githubusercontent.com"),
        disable_oidc_auth=os.getenv("DISABLE_OIDC_AUTH", "").lower() in ("1", "true", "yes"),
        default_model=os.getenv("LLM_MODEL", "gpt-5.4-nano"),
        default_reasoning_effort=os.getenv("LLM_REASONING_EFFORT", "low"),
        default_analysis_mode=os.getenv("ANALYSIS_MODE", "single"),
        lookback_days=int(os.getenv("LOOKBACK_DAYS", "7")),
        max_concurrent_api_calls=int(os.getenv("MAX_CONCURRENT_API_CALLS", "2")),
        max_api_retries=int(os.getenv("MAX_API_RETRIES", "3")),
        max_selector_tool_rounds=int(os.getenv("MAX_SELECTOR_TOOL_ROUNDS", "1")),
        max_tool_requests_per_round=int(os.getenv("MAX_TOOL_REQUESTS_PER_ROUND", "1")),
        enable_screenshots=os.getenv("ENABLE_SCREENSHOTS", "").lower() in ("1", "true", "yes"),
        screenshot_device=os.getenv("CS_TESTER_DEVICE", "stax"),
        cs_tester_root=os.getenv("CS_TESTER_ROOT"),
        coin_apps_path=os.getenv("COIN_APPS_PATH"),
        job_retention_ttl=int(os.getenv("JOB_RETENTION_TTL", "3600")),
        max_retained_log_lines=int(os.getenv("MAX_RETAINED_LOG_LINES", "500")),
        poll_interval_hint=int(os.getenv("POLL_INTERVAL_HINT", "5")),
        analysis_timeout_seconds=int(os.getenv("ANALYSIS_TIMEOUT_SECONDS", str(60 * 60 * 3))),
        host=os.getenv("SERVICE_HOST", "0.0.0.0"),
        port=int(os.getenv("SERVICE_PORT", "8080")),
    )
