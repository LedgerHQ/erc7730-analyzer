"""Run cs-tester CLI to capture Ledger device screenshots for transactions."""

import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any, TypedDict

from .elf_artifacts import (
    DEFAULT_ARTIFACT_NAME,
    DEFAULT_BRANCH,
    DEFAULT_OWNER,
    DEFAULT_REPO,
    DEFAULT_WORKFLOW_NAME,
    fetch_latest_ethereum_app_elf,
    normalize_device_name,
)
from .raw_tx import fetch_raw_transaction_async

logger = logging.getLogger(__name__)

DEFAULT_RUNTIME_ROOT = Path(os.getenv("CS_TESTER_RUNTIME_ROOT", "/tmp/erc7730-screenshots"))
_LEGACY_CS_TESTER_ROOT = Path(os.path.expanduser("~/Desktop/clear_sign/device-sdk-ts"))
_LEGACY_COIN_APPS_PATH = Path(os.path.expanduser("~/Desktop/clear_sign/coin-apps"))
DEFAULT_CS_TESTER_ROOT = str(_LEGACY_CS_TESTER_ROOT if _LEGACY_CS_TESTER_ROOT.exists() else DEFAULT_RUNTIME_ROOT / "device-sdk-ts")
DEFAULT_COIN_APPS_PATH = str(_LEGACY_COIN_APPS_PATH if _LEGACY_COIN_APPS_PATH.exists() else DEFAULT_RUNTIME_ROOT / "coin-apps")
DEFAULT_ETH_APP_ELF_ROOT = str(DEFAULT_RUNTIME_ROOT / "ethereum-app-elfs")
DEFAULT_DMK_REPO = "LedgerHQ/device-sdk-ts"
DEFAULT_DMK_REF = "develop"
DEFAULT_SPECULOS_IMAGE = "ghcr.io/ledgerhq/speculos"
MAX_TXS_PER_SELECTOR = 2
MAX_CONCURRENT_SPECULOS = min(max(os.cpu_count() or 4, 3), 8)
CS_TESTER_MAX_RETRIES = 3
CS_TESTER_RETRY_DELAY = 3
TRIM_HEAD = 3
TRIM_TAIL = 3

_BOOT_LOCK = threading.Lock()
_DMK_STAMP_FILENAME = ".erc7730_analyzer_dmk_ready.json"


class TxScreenshots(TypedDict):
    tx_hash: str
    screenshots: list[str]


class ScreenshotRunner:
    """Generate Ledger device screenshots using cs-tester + Speculos.

    In the Docker/API deployment model, device-sdk-ts is pre-built in the
    image. At runtime the runner:

    - Pulls latest device-sdk-ts changes (public, no auth)
    - Checks the latest successful app-ethereum CI artifact and refreshes the
      device-specific Ethereum app ELF if it changed
    - Ensures the Speculos Docker image is present

    Legacy COIN_APPS_PATH support is retained as a fallback, but the primary
    path is the CI artifact-backed custom app ELF.
    """

    def __init__(
        self,
        etherscan_api_key: str,
        cs_tester_root: str | None = None,
        coin_apps_path: str | None = None,
        device: str = "stax",
    ):
        self.etherscan_api_key = etherscan_api_key
        self.runtime_root = Path(os.getenv("CS_TESTER_RUNTIME_ROOT", str(DEFAULT_RUNTIME_ROOT)))
        self.cs_tester_root = Path(cs_tester_root or os.getenv("CS_TESTER_ROOT", DEFAULT_CS_TESTER_ROOT))
        self.coin_apps_path = Path(coin_apps_path or os.getenv("COIN_APPS_PATH", DEFAULT_COIN_APPS_PATH))
        self.eth_app_elf_root = Path(os.getenv("ETH_APP_ELF_ROOT", DEFAULT_ETH_APP_ELF_ROOT))
        self.device = os.getenv("CS_TESTER_DEVICE", device)
        self.dmk_repo = os.getenv("DMK_REPO", DEFAULT_DMK_REPO)
        self.dmk_ref = os.getenv("DMK_REF", DEFAULT_DMK_REF)
        self.speculos_image = os.getenv("SPECULOS_IMAGE", DEFAULT_SPECULOS_IMAGE)
        self.gating_token = os.getenv("GATING_TOKEN", "").strip()
        self.github_token = (
            os.getenv("APP_ETHEREUM_ARTIFACT_TOKEN", "").strip() or os.getenv("GITHUB_TOKEN", "").strip()
        )
        self.app_eth_owner = os.getenv("APP_ETHEREUM_REPO_OWNER", DEFAULT_OWNER)
        self.app_eth_repo = os.getenv("APP_ETHEREUM_REPO_NAME", DEFAULT_REPO)
        self.app_eth_branch = os.getenv("APP_ETHEREUM_BRANCH", DEFAULT_BRANCH)
        self.app_eth_workflow_name = os.getenv("APP_ETHEREUM_WORKFLOW_NAME", DEFAULT_WORKFLOW_NAME)
        self._speculos_sem: asyncio.Semaphore | None = None
        self.app_eth_artifact_name = os.getenv("APP_ETHEREUM_ARTIFACT_NAME", DEFAULT_ARTIFACT_NAME)
        self.last_unavailability_reasons: list[str] = []

    # ------------------------------------------------------------------
    # Availability checks
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Verify that all screenshot prerequisites are present."""
        self.last_unavailability_reasons = []
        if not self.gating_token:
            self._add_unavailability_reason("missing GATING_TOKEN")
            return False
        if not self._ensure_runtime_ready():
            return False
        if not (self.cs_tester_root / "apps" / "clear-signing-tester").is_dir():
            self._add_unavailability_reason(f"cs-tester not found at {self.cs_tester_root}")
            return False
        if not self._has_any_ethereum_app():
            if not self.github_token:
                self._add_unavailability_reason("missing GITHUB_TOKEN")
            self._add_unavailability_reason(
                f"no Ethereum app ELF available at {self._artifact_elf_path()} and no legacy COIN_APPS_PATH fallback"
            )
            return False
        if not shutil.which("pnpm") and not shutil.which("corepack"):
            self._add_unavailability_reason("pnpm/corepack not found on PATH")
            return False
        if not shutil.which("docker"):
            self._add_unavailability_reason("docker CLI not found on PATH")
            return False
        return True

    def availability_diagnostic(self) -> str:
        """Return a compact human-readable explanation of why screenshots are unavailable."""
        if not self.last_unavailability_reasons:
            return "unknown screenshot preflight issue"
        return "; ".join(self.last_unavailability_reasons)

    def _add_unavailability_reason(self, reason: str) -> None:
        if reason not in self.last_unavailability_reasons:
            self.last_unavailability_reasons.append(reason)

    def _coin_apps_has_elfs(self) -> bool:
        return any(self.coin_apps_path.glob(f"{self.device}/*/Ethereum/*.elf"))

    def _artifact_elf_path(self) -> Path:
        normalized_device = normalize_device_name(self.device)
        return self.eth_app_elf_root / normalized_device / "bin" / "app.elf"

    def _has_artifact_elf(self) -> bool:
        return self._artifact_elf_path().is_file()

    def _has_any_ethereum_app(self) -> bool:
        return self._has_artifact_elf()

    # ------------------------------------------------------------------
    # Runtime readiness
    # ------------------------------------------------------------------

    def _ensure_runtime_ready(self) -> bool:
        """Verify pre-built assets exist and refresh mutable runtime assets."""
        if not (self.cs_tester_root / "apps" / "clear-signing-tester").is_dir():
            self._add_unavailability_reason(
                f"device-sdk-ts not found at {self.cs_tester_root} — "
                "build the Docker image or clone manually"
            )
            return False

        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self.eth_app_elf_root.mkdir(parents=True, exist_ok=True)

        with _BOOT_LOCK:
            if not os.getenv("CS_TESTER_RUNTIME_ROOT"):
                self._maybe_update_dmk()
            self._maybe_update_elfs()
            self._ensure_speculos_image()

        if self._has_any_ethereum_app():
            return True

        if not self.github_token:
            self._add_unavailability_reason("missing GITHUB_TOKEN")
        self._add_unavailability_reason(
            f"no Ethereum app ELF available at {self._artifact_elf_path()} and no legacy COIN_APPS_PATH fallback"
        )
        return False

    # ------------------------------------------------------------------
    # device-sdk-ts update (public, no auth)
    # ------------------------------------------------------------------

    def _maybe_update_dmk(self) -> None:
        """Pull latest device-sdk-ts changes if the checkout is a git repo.

        If no stamp file exists but the build is already functional
        (node_modules + apps/clear-signing-tester present), write a stamp
        and skip the update — avoids needless reinstalls on local setups.
        """
        if not (self.cs_tester_root / ".git").is_dir():
            return

        stamp_path = self.cs_tester_root / _DMK_STAMP_FILENAME
        stamp = self._read_stamp(stamp_path)

        if stamp and stamp.get("ref") == self.dmk_ref:
            logger.info("[SCREENSHOTS][SETUP] device-sdk-ts already at %s — skipping pull", self.dmk_ref)
            return

        build_functional = (
            (self.cs_tester_root / "node_modules").is_dir()
            and (self.cs_tester_root / "apps" / "clear-signing-tester").is_dir()
        )

        if not stamp and build_functional:
            logger.info("[SCREENSHOTS][SETUP] device-sdk-ts build already present — writing stamp, skipping update")
            stamp_path.write_text(json.dumps({"repo": self.dmk_repo, "ref": self.dmk_ref}, indent=2))
            return

        # Save current HEAD so we can revert if install/build fails
        prev_head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(self.cs_tester_root),
            capture_output=True, text=True,
        ).stdout.strip()

        try:
            logger.info("[SCREENSHOTS][SETUP] Pulling device-sdk-ts %s@%s", self.dmk_repo, self.dmk_ref)
            self._run_command(
                ["git", "fetch", "--depth", "1", "origin", self.dmk_ref],
                cwd=self.cs_tester_root, timeout=300,
                description=f"Fetching {self.dmk_repo}@{self.dmk_ref}",
            )

            # Check if FETCH_HEAD is the same as current HEAD (no change)
            fetch_head = subprocess.run(
                ["git", "rev-parse", "FETCH_HEAD"],
                cwd=str(self.cs_tester_root),
                capture_output=True, text=True,
            ).stdout.strip()
            if fetch_head == prev_head:
                logger.info("[SCREENSHOTS][SETUP] device-sdk-ts already up to date")
                stamp_path.write_text(json.dumps({"repo": self.dmk_repo, "ref": self.dmk_ref}, indent=2))
                return

            self._run_command(
                ["git", "checkout", "--detach", "FETCH_HEAD"],
                cwd=self.cs_tester_root, timeout=120,
                description=f"Checking out {self.dmk_repo}@{self.dmk_ref}",
            )
            self._run_command(
                self._pnpm_cmd("install", "--frozen-lockfile"),
                cwd=self.cs_tester_root, timeout=600,
                description="Installing device-sdk-ts dependencies",
            )
            self._run_command(
                self._pnpm_cmd("build:libs"),
                cwd=self.cs_tester_root, timeout=600,
                description="Building device-sdk-ts libraries",
            )
            stamp_path.write_text(json.dumps({"repo": self.dmk_repo, "ref": self.dmk_ref}, indent=2))
        except Exception as exc:
            logger.warning("[SCREENSHOTS][SETUP] device-sdk-ts update failed, reverting to %s: %s", prev_head[:10], exc)
            if prev_head:
                subprocess.run(
                    ["git", "checkout", "--detach", prev_head],
                    cwd=str(self.cs_tester_root),
                    capture_output=True, timeout=60,
                )

    # ------------------------------------------------------------------
    # ELF update (app-ethereum CI artifacts via PAT)
    # ------------------------------------------------------------------

    def _maybe_update_elfs(self) -> None:
        """Refresh the device ELF from the latest successful app-ethereum build artifact."""
        if not self.github_token:
            logger.info("[SCREENSHOTS][SETUP] GITHUB_TOKEN not set — skipping artifact ELF refresh")
            return

        try:
            result = fetch_latest_ethereum_app_elf(
                token=self.github_token,
                device=self.device,
                output_root=self.eth_app_elf_root,
                owner=self.app_eth_owner,
                repo=self.app_eth_repo,
                branch=self.app_eth_branch,
                workflow_name=self.app_eth_workflow_name,
                artifact_name=self.app_eth_artifact_name,
            )
        except Exception as exc:
            logger.warning("[SCREENSHOTS][SETUP] Failed to refresh Ethereum app ELF: %s", exc)
            return

        if result["updated"]:
            logger.info(
                "[SCREENSHOTS][SETUP] Refreshed Ethereum app ELF from run=%s artifact=%s",
                result["run_id"],
                result["artifact_id"],
            )
        else:
            logger.info(
                "[SCREENSHOTS][SETUP] Ethereum app ELF already current (run=%s artifact=%s)",
                result["run_id"],
                result["artifact_id"],
            )

    # ------------------------------------------------------------------
    # Speculos image
    # ------------------------------------------------------------------

    def _ensure_speculos_image(self) -> None:
        """Pull the Speculos Docker image if not already present."""
        try:
            inspect = subprocess.run(
                ["docker", "image", "inspect", self.speculos_image],
                capture_output=True, text=True,
            )
            if inspect.returncode == 0:
                return
            self._run_command(
                ["docker", "pull", self.speculos_image],
                timeout=600,
                description=f"Pulling {self.speculos_image}",
            )
        except Exception as exc:
            logger.warning("[SCREENSHOTS][SETUP] Speculos image pull failed: %s", exc)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _read_stamp(self, path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text())
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    def _run_command(
        self,
        cmd: list[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        timeout: int | None = None,
        description: str,
    ) -> None:
        logger.info("[SCREENSHOTS][SETUP] %s", description)
        result = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            stderr = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"{description} failed: {stderr[-600:] or f'exit {result.returncode}'}")

    def _pnpm_cmd(self, *args: str) -> list[str]:
        if shutil.which("pnpm"):
            return ["pnpm", *args]
        return ["corepack", "pnpm", *args]

    # ------------------------------------------------------------------
    # Async entry point
    # ------------------------------------------------------------------

    def _get_speculos_semaphore(self) -> asyncio.Semaphore:
        """Lazily create a per-event-loop semaphore to cap concurrent Speculos containers."""
        if self._speculos_sem is None:
            self._speculos_sem = asyncio.Semaphore(MAX_CONCURRENT_SPECULOS)
        return self._speculos_sem

    async def _run_cs_tester_throttled(
        self, selector: str, tx_hash: str, raw_tx: str, erc7730_file: Path, attempt: int,
    ) -> TxScreenshots:
        """Run a single cs-tester invocation, throttled by the Speculos semaphore."""
        sem = self._get_speculos_semaphore()
        async with sem:
            return await asyncio.to_thread(
                self._run_cs_tester_once, selector, tx_hash, raw_tx, erc7730_file, attempt,
            )

    async def capture_for_selector_async(
        self,
        *,
        selector: str,
        chain_id: int,
        transactions: list[dict[str, Any]],
        erc7730_file: Path,
    ) -> list[TxScreenshots]:
        """Capture screenshots for up to MAX_TXS_PER_SELECTOR transactions.

        Runs each transaction through cs-tester individually so screenshots
        can be cleanly associated with their tx hash, and trims the
        non-meaningful boot/confirm frames (first TRIM_HEAD, last TRIM_TAIL).

        Concurrent Speculos containers are capped at MAX_CONCURRENT_SPECULOS
        to avoid overwhelming Docker.
        """
        txs_to_process = transactions[:MAX_TXS_PER_SELECTOR]
        if not txs_to_process:
            return []

        raw_entries: list[tuple[str, str]] = []
        fetch_tasks = []
        for tx in txs_to_process:
            tx_hash = tx.get("hash", "")
            raw_tx = tx.get("raw_tx") or tx.get("rawTx") or tx.get("raw_transaction")
            if isinstance(raw_tx, str) and raw_tx.startswith("0x") and tx_hash.startswith("0x") and len(tx_hash) == 66:
                raw_entries.append((tx_hash, raw_tx))
                continue
            if tx_hash.startswith("0x") and len(tx_hash) == 66:
                fetch_tasks.append(
                    (
                        tx_hash,
                        fetch_raw_transaction_async(
                            tx_hash,
                            chain_id,
                            self.etherscan_api_key,
                        ),
                    )
                )

        for tx_hash, coro in fetch_tasks:
            raw_tx = await coro
            if raw_tx:
                raw_entries.append((tx_hash, raw_tx))

        if not raw_entries:
            logger.warning("[SCREENSHOTS][%s] No raw transactions could be reconstructed", selector)
            return []

        pending = list(raw_entries)
        completed: list[TxScreenshots] = []

        for attempt in range(CS_TESTER_MAX_RETRIES):
            if not pending:
                break

            coros = [
                self._run_cs_tester_throttled(selector, tx_hash, raw_tx, erc7730_file, attempt)
                for tx_hash, raw_tx in pending
            ]
            batch_results = await asyncio.gather(*coros, return_exceptions=True)

            next_pending: list[tuple[str, str]] = []
            for (tx_hash, raw_tx), result in zip(pending, batch_results, strict=False):
                if isinstance(result, Exception):
                    logger.warning("[SCREENSHOTS][%s] cs-tester raised for tx %s: %s", selector, tx_hash[:10], result)
                    next_pending.append((tx_hash, raw_tx))
                elif result and result["screenshots"]:
                    completed.append(result)
                else:
                    next_pending.append((tx_hash, raw_tx))

            if next_pending and attempt < CS_TESTER_MAX_RETRIES - 1:
                logger.info(
                    "[SCREENSHOTS][%s] %d tx(s) failed attempt %d, retrying concurrently...",
                    selector,
                    len(next_pending),
                    attempt + 1,
                )
                await asyncio.sleep(CS_TESTER_RETRY_DELAY * (attempt + 1))

            pending = next_pending

        if pending:
            logger.warning(
                "[SCREENSHOTS][%s] %d tx(s) failed after %d attempt(s): %s",
                selector,
                len(pending),
                CS_TESTER_MAX_RETRIES,
                ", ".join(h[:10] for h, _ in pending),
            )

        return completed

    async def capture_all_selectors_async(
        self,
        *,
        selectors_info: list[dict[str, Any]],
        erc7730_file: Path,
    ) -> dict[str, list[TxScreenshots]]:
        """Run screenshot capture for all selectors concurrently."""

        async def _one(info: dict[str, Any]) -> tuple[str, list[TxScreenshots]]:
            sel = info["selector"]
            tx_screenshots = await self.capture_for_selector_async(
                selector=sel,
                chain_id=info["chain_id"],
                transactions=info["transactions"],
                erc7730_file=erc7730_file,
            )
            return sel.lower(), tx_screenshots

        results = await asyncio.gather(
            *[_one(info) for info in selectors_info],
            return_exceptions=True,
        )

        screenshot_map: dict[str, list[TxScreenshots]] = {}
        for result in results:
            if isinstance(result, Exception):
                logger.warning("[SCREENSHOTS] Selector task failed: %s", result)
                continue
            sel, tx_screenshots = result
            if tx_screenshots:
                screenshot_map[sel] = tx_screenshots

        return screenshot_map

    # ------------------------------------------------------------------
    # Single-tx cs-tester execution (one attempt) + trimming
    # ------------------------------------------------------------------

    def _run_cs_tester_once(
        self,
        selector: str,
        tx_hash: str,
        raw_tx: str,
        erc7730_file: Path,
        attempt: int = 0,
    ) -> TxScreenshots:
        """Run cs-tester for a single transaction (one attempt), then trim."""
        screenshots_dir = Path(
            tempfile.mkdtemp(
                prefix=f"cs_screenshots_{selector}_{tx_hash[:10]}_a{attempt}_",
            )
        )
        input_file = screenshots_dir / "input.json"
        input_file.write_text(
            json.dumps(
                [
                    {
                        "txHash": tx_hash,
                        "rawTx": raw_tx,
                        "description": f"{selector} tx {tx_hash[:10]}",
                    }
                ],
                indent=2,
            )
        )

        custom_app_path = self._artifact_elf_path()
        cmd = [
            *self._pnpm_cmd(
                "cs-tester",
                "cli",
                "--device",
                self.device,
                "--screenshot-folder-path",
                str(screenshots_dir),
                "--erc7730-files",
                str(erc7730_file.resolve()),
                "--log-level",
                "warn",
                "raw-file",
                str(input_file),
            ),
        ]

        env = dict(os.environ)
        if not custom_app_path.is_file():
            logger.warning(
                "[SCREENSHOTS][%s] No Ethereum app ELF at %s for device %s",
                selector, custom_app_path, self.device,
            )
            return {"tx_hash": tx_hash, "screenshots": []}

        cmd.extend(["--custom-app", str(custom_app_path)])
        # cs-tester always mounts COIN_APPS_PATH as a Docker volume
        # (-v $COIN_APPS_PATH:/apps) even with --custom-app.  Set it to
        # a valid directory to prevent "docker: invalid spec: :/apps".
        if not env.get("COIN_APPS_PATH"):
            env["COIN_APPS_PATH"] = str(custom_app_path.parent)

        if attempt == 0:
            logger.info(
                "[SCREENSHOTS][%s] Running cs-tester for tx %s device=%s%s",
                selector,
                tx_hash[:10],
                self.device,
                f" custom_app={custom_app_path}",
            )
        else:
            logger.info(
                "[SCREENSHOTS][%s] Retry %d/%d for tx %s",
                selector,
                attempt,
                CS_TESTER_MAX_RETRIES,
                tx_hash[:10],
            )

        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.cs_tester_root),
                env=env,
                capture_output=True,
                text=True,
                timeout=180,
            )

            if result.returncode != 0:
                logger.warning(
                    "[SCREENSHOTS][%s] cs-tester exited with code %d for tx %s: %s",
                    selector,
                    result.returncode,
                    tx_hash[:10],
                    result.stderr[-500:] if result.stderr else "(no stderr)",
                )
                return {"tx_hash": tx_hash, "screenshots": []}

            logger.info("[SCREENSHOTS][%s] cs-tester completed for tx %s", selector, tx_hash[:10])
        except subprocess.TimeoutExpired:
            logger.warning("[SCREENSHOTS][%s] cs-tester timed out for tx %s", selector, tx_hash[:10])
            return {"tx_hash": tx_hash, "screenshots": []}
        except FileNotFoundError:
            logger.warning("[SCREENSHOTS][%s] pnpm not found", selector)
            return {"tx_hash": tx_hash, "screenshots": []}
        except Exception as exc:
            logger.warning("[SCREENSHOTS][%s] cs-tester failed for tx %s: %s", selector, tx_hash[:10], exc)
            return {"tx_hash": tx_hash, "screenshots": []}

        all_pngs = sorted(screenshots_dir.glob("screenshot_*.png"), key=_sort_key)

        if len(all_pngs) > TRIM_HEAD + TRIM_TAIL:
            meaningful = all_pngs[TRIM_HEAD : len(all_pngs) - TRIM_TAIL]
        elif all_pngs:
            meaningful = all_pngs
        else:
            meaningful = []

        if meaningful:
            logger.info(
                "[SCREENSHOTS][%s] Kept %d/%d screenshot(s) for tx %s (trimmed %d head + %d tail)",
                selector,
                len(meaningful),
                len(all_pngs),
                tx_hash[:10],
                TRIM_HEAD,
                TRIM_TAIL,
            )
        else:
            logger.warning(
                "[SCREENSHOTS][%s] No screenshots captured for tx %s on attempt %d",
                selector,
                tx_hash[:10],
                attempt + 1,
            )

        return {"tx_hash": tx_hash, "screenshots": [str(p) for p in meaningful]}


def _sort_key(path: Path) -> int:
    """Extract numeric index from screenshot_N.png for natural sorting."""
    stem = path.stem
    parts = stem.split("_")
    try:
        return int(parts[-1])
    except (ValueError, IndexError):
        return 0
