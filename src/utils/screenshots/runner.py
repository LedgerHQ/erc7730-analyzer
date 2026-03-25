"""Run cs-tester CLI to capture Ledger device screenshots for transactions."""

import asyncio
import json
import logging
import os
import shutil
import socket
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
TRIM_HEAD = 1
TRIM_TAIL = 3

PERSISTENT_SPECULOS_PORT = 5555
PERSISTENT_SPECULOS_API_PORT = 5000
SPECULOS_STARTUP_TIMEOUT = 30
_PERSISTENT_CONTAINER_NAME = "erc7730-persistent-speculos"
SPECULOS_DEV_TOOLS_IMAGE = "ghcr.io/ledgerhq/ledger-app-builder/ledger-app-dev-tools:latest"

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
        self._persistent_speculos_proc: subprocess.Popen | None = None
        self._persistent_speculos_port: int | None = None
        self._persistent_speculos_container: str | None = None

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
        if not shutil.which("docker") and not shutil.which("speculos"):
            self._add_unavailability_reason("neither docker CLI nor native speculos found on PATH")
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
        if not shutil.which("docker"):
            return
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
    # Persistent Speculos lifecycle
    # ------------------------------------------------------------------

    async def _start_persistent_speculos(self) -> int:
        """Start a single Speculos instance that persists across all cs-tester runs.

        Native ``speculos`` binary is preferred (App Runner / CI).  Falls back
        to a long-lived Docker container for local dev.  Returns the API port.
        """
        elf_path = self._artifact_elf_path()
        if not elf_path.is_file():
            raise RuntimeError(f"No Ethereum app ELF at {elf_path}")

        port = PERSISTENT_SPECULOS_PORT

        if shutil.which("speculos"):
            logger.info("[SCREENSHOTS] Starting native persistent Speculos (port=%d, elf=%s)", port, elf_path)
            self._persistent_speculos_proc = subprocess.Popen(
                ["speculos", str(elf_path), "--display", "headless", "--api-port", str(port)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        elif shutil.which("docker"):
            logger.info("[SCREENSHOTS] Starting Docker persistent Speculos (port=%d, elf=%s)", port, elf_path)
            subprocess.run(["docker", "rm", "-f", _PERSISTENT_CONTAINER_NAME], capture_output=True)
            uid, gid = os.getuid(), os.getgid()
            result = subprocess.run(
                [
                    "docker", "run", "--rm", "-d",
                    "--name", _PERSISTENT_CONTAINER_NAME,
                    "-p", f"{port}:{PERSISTENT_SPECULOS_API_PORT}",
                    "-v", f"{elf_path}:/custom-app/app.elf:ro",
                    SPECULOS_DEV_TOOLS_IMAGE,
                    "speculos", "/custom-app/app.elf",
                    "--display", "headless",
                    "--api-port", str(PERSISTENT_SPECULOS_API_PORT),
                    "--vnc-port", str(PERSISTENT_SPECULOS_API_PORT + 900),
                    "--user", f"{uid}:{gid}",
                ],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode != 0:
                raise RuntimeError(f"Docker Speculos start failed: {result.stderr[-500:]}")
            self._persistent_speculos_container = _PERSISTENT_CONTAINER_NAME
        else:
            raise RuntimeError("No speculos or docker available")

        await self._wait_for_speculos_api(port)
        self._persistent_speculos_port = port
        self._speculos_sem = asyncio.Semaphore(1)
        logger.info("[SCREENSHOTS] Persistent Speculos ready on port %d", port)
        return port

    async def _wait_for_speculos_api(self, port: int, timeout: int = SPECULOS_STARTUP_TIMEOUT) -> None:
        """Block until the Speculos HTTP API and Ethereum app are responsive."""
        import urllib.request
        import urllib.error

        url = f"http://localhost:{port}/"
        for attempt in range(timeout * 2):
            try:
                resp = urllib.request.urlopen(url, timeout=2)
                resp.close()
                break
            except (urllib.error.URLError, OSError, ConnectionRefusedError):
                await asyncio.sleep(0.5)
        else:
            raise TimeoutError(f"Speculos API not ready on port {port} after {timeout}s")
        await asyncio.to_thread(self._wait_for_app_ready_sync, port)
        await asyncio.to_thread(self._set_speculos_automation, port)

    def _restart_persistent_speculos_sync(self) -> None:
        """Restart Speculos to get a clean app state between cs-tester runs.

        Docker: ``docker restart --timeout 1`` (~1.2s) then wait for API.
        Native: kill + respawn the process.

        After the HTTP API responds, sends a GET_VERSION APDU to the Ethereum
        app to ensure it has fully loaded before returning.
        """
        import time
        import urllib.error
        import urllib.request

        port = self._persistent_speculos_port or PERSISTENT_SPECULOS_PORT

        if self._persistent_speculos_container:
            subprocess.run(
                ["docker", "restart", "--timeout", "1", self._persistent_speculos_container],
                capture_output=True, timeout=30,
            )
        elif self._persistent_speculos_proc:
            elf_path = self._artifact_elf_path()
            self._persistent_speculos_proc.terminate()
            try:
                self._persistent_speculos_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._persistent_speculos_proc.kill()
            self._persistent_speculos_proc = subprocess.Popen(
                ["speculos", str(elf_path), "--display", "headless", "--api-port", str(port)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        else:
            return

        url = f"http://localhost:{port}/"
        for _ in range(SPECULOS_STARTUP_TIMEOUT * 2):
            try:
                resp = urllib.request.urlopen(url, timeout=2)
                resp.close()
                break
            except (urllib.error.URLError, OSError, ConnectionRefusedError):
                time.sleep(0.5)
        else:
            logger.warning("[SCREENSHOTS] Speculos API not ready after restart — continuing anyway")
            return

        self._wait_for_app_ready_sync(port)
        self._set_speculos_automation(port)

    @staticmethod
    def _wait_for_app_ready_sync(port: int, timeout: int = 10) -> None:
        """Confirm the Ethereum app is fully ready for transaction processing.

        Phase 1: Poll GET_APP_CONFIGURATION until the app responds with 9000.
        Phase 2: Wait for the clear-signing subsystem to finish initializing
                 (the app responds to basic APDUs before its internal state
                 machine is ready to accept transaction signing commands).
        """
        import time
        import urllib.error
        import urllib.request

        apdu_url = f"http://localhost:{port}/apdu"
        get_config = json.dumps({"data": "e006000000"}).encode()
        for attempt in range(timeout * 4):
            try:
                req = urllib.request.Request(
                    apdu_url,
                    data=get_config,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                resp = urllib.request.urlopen(req, timeout=2)
                body = json.loads(resp.read())
                resp.close()
                status = body.get("data", "")[-4:]
                if status == "9000":
                    logger.debug("[SCREENSHOTS] Ethereum app APDU OK on port %d, waiting for subsystem init", port)
                    time.sleep(1.5)
                    return
                logger.debug("[SCREENSHOTS] App APDU returned status %s, retrying...", status)
            except (urllib.error.URLError, OSError, ConnectionRefusedError, json.JSONDecodeError):
                pass
            time.sleep(0.25)
        logger.warning("[SCREENSHOTS] Ethereum app did not respond to GET_APP_CONFIGURATION after %ds — continuing", timeout)

    @staticmethod
    def _set_speculos_automation(port: int) -> None:
        """Install Speculos automation rules to dismiss first-boot prompts.

        The Ethereum app shows modal prompts like 'Enable Transaction Check?'
        the first time a transaction is sent after a fresh start.  These rules
        automatically tap 'Maybe later' whenever that text appears on screen.
        """
        import urllib.error
        import urllib.request

        url = f"http://localhost:{port}/automation"
        rules = {
            "version": 1,
            "rules": [
                {"text": "Maybe later", "actions": [["finger", 200, 620, True], ["finger", 200, 620, False]]},
            ],
        }
        try:
            payload = json.dumps(rules).encode()
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=5).close()
            logger.info("[SCREENSHOTS] Speculos automation rules installed on port %d", port)
        except (urllib.error.URLError, OSError) as exc:
            logger.warning("[SCREENSHOTS] Failed to set Speculos automation rules: %s", exc)

    def _stop_persistent_speculos(self) -> None:
        """Tear down the persistent Speculos instance."""
        if self._persistent_speculos_proc:
            logger.info("[SCREENSHOTS] Stopping native persistent Speculos (pid=%d)", self._persistent_speculos_proc.pid)
            self._persistent_speculos_proc.terminate()
            try:
                self._persistent_speculos_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._persistent_speculos_proc.kill()
            self._persistent_speculos_proc = None

        if self._persistent_speculos_container:
            logger.info("[SCREENSHOTS] Stopping Docker persistent Speculos container")
            subprocess.run(["docker", "rm", "-f", self._persistent_speculos_container], capture_output=True)
            self._persistent_speculos_container = None

        self._persistent_speculos_port = None
        self._speculos_sem = None

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
        """Run a single cs-tester invocation, throttled by the Speculos semaphore.

        After each run, Speculos is restarted to guarantee a clean app state
        for the next invocation (the emulated Ethereum app does not reset
        cleanly between signings).
        """
        sem = self._get_speculos_semaphore()
        async with sem:
            result = await asyncio.to_thread(
                self._run_cs_tester_once, selector, tx_hash, raw_tx, erc7730_file, attempt,
            )
            if self._persistent_speculos_port is not None:
                await asyncio.to_thread(self._restart_persistent_speculos_sync)
            return result

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
        """Run screenshot capture for all selectors.

        A persistent Speculos instance is started once before processing and
        torn down afterwards.  cs-tester is invoked with ``--external-speculos``
        so it connects to the pre-existing instance instead of spawning its own
        Docker container, cutting per-transaction overhead from ~30s to ~4s.
        """
        try:
            await self._start_persistent_speculos()
        except Exception as exc:
            logger.warning("[SCREENSHOTS] Failed to start persistent Speculos: %s", exc)
            return {}

        try:
            return await self._capture_all_selectors_inner(
                selectors_info=selectors_info,
                erc7730_file=erc7730_file,
            )
        finally:
            self._stop_persistent_speculos()

    async def _capture_all_selectors_inner(
        self,
        *,
        selectors_info: list[dict[str, Any]],
        erc7730_file: Path,
    ) -> dict[str, list[TxScreenshots]]:
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

    @staticmethod
    def _wait_for_screenshots_or_exit(
        proc: subprocess.Popen,
        screenshots_dir: Path,
        selector: str,
        tx_hash: str,
        *,
        max_wait: int = 120,
        stable_after: float = 3.0,
        min_grace: float = 15.0,
    ) -> bool:
        """Poll until cs-tester exits or screenshot files stop appearing.

        Returns ``True`` when usable screenshots were produced — either from
        a clean exit (code 0), screenshots stabilising while alive, or a
        non-zero exit that still left blind-signed screenshots on disk.

        Returns ``False`` only when no screenshots exist at all.

        The *min_grace* period prevents premature termination: during this
        initial window, stability-based termination only fires when more
        than 2 screenshots already exist (the home screen alone isn't
        enough to declare "done").
        """
        import time

        start = time.monotonic()
        deadline = start + max_wait
        last_count = 0
        last_change = time.monotonic()

        while time.monotonic() < deadline:
            ret = proc.poll()
            if ret is not None:
                if ret == 0:
                    logger.info("[SCREENSHOTS][%s] cs-tester completed for tx %s", selector, tx_hash[:10])
                    return True
                stderr = ""
                if proc.stderr:
                    stderr = proc.stderr.read().decode(errors="replace")[-500:]
                has_screenshots = any(screenshots_dir.glob("screenshot_*.png"))
                if has_screenshots:
                    logger.info(
                        "[SCREENSHOTS][%s] cs-tester exited with code %d for tx %s (blind-signed, keeping screenshots)",
                        selector, ret, tx_hash[:10],
                    )
                    return True
                logger.warning(
                    "[SCREENSHOTS][%s] cs-tester exited with code %d for tx %s: %s",
                    selector, ret, tx_hash[:10], stderr,
                )
                return False

            current_count = len(list(screenshots_dir.glob("screenshot_*.png")))
            if current_count != last_count:
                last_count = current_count
                last_change = time.monotonic()

            elapsed = time.monotonic() - start
            in_grace = elapsed < min_grace
            stable_elapsed = time.monotonic() - last_change

            if last_count > 0 and stable_elapsed >= stable_after:
                if in_grace and last_count <= 2:
                    pass  # too early — wait for clear-signing screens
                else:
                    logger.info(
                        "[SCREENSHOTS][%s] %d screenshot(s) stable for %.0fs — terminating cs-tester for tx %s",
                        selector, last_count, stable_after, tx_hash[:10],
                    )
                    return True

            time.sleep(0.5)

        logger.warning("[SCREENSHOTS][%s] cs-tester timed out after %ds for tx %s", selector, max_wait, tx_hash[:10])
        return False

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
        cs_global_opts = [
            "cs-tester", "cli",
            "--device", self.device,
            "--screenshot-folder-path", str(screenshots_dir),
            "--erc7730-files", str(erc7730_file.resolve()),
            "--log-level", "warn",
        ]
        if self._persistent_speculos_port is not None:
            cs_global_opts.extend([
                "--speculos-port", str(self._persistent_speculos_port),
                "--external-speculos",
            ])
        cs_global_opts.extend(["raw-file", str(input_file)])
        cmd = [*self._pnpm_cmd(*cs_global_opts)]

        env = dict(os.environ)

        from .erc7730_api import ensure_running as _ensure_erc7730_api
        api_port = _ensure_erc7730_api()
        env["ERC7730_API_URL"] = f"http://127.0.0.1:{api_port}"

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
                "[SCREENSHOTS][%s] Running cs-tester for tx %s device=%s custom_app=%s",
                selector, tx_hash[:10], self.device, custom_app_path,
            )
            logger.debug("[SCREENSHOTS][%s] cmd: %s", selector, " ".join(cmd))
        else:
            logger.info(
                "[SCREENSHOTS][%s] Retry %d/%d for tx %s",
                selector,
                attempt,
                CS_TESTER_MAX_RETRIES,
                tx_hash[:10],
            )

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(self.cs_tester_root),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            logger.warning("[SCREENSHOTS][%s] pnpm not found", selector)
            return {"tx_hash": tx_hash, "screenshots": []}
        except Exception as exc:
            logger.warning("[SCREENSHOTS][%s] cs-tester failed to start for tx %s: %s", selector, tx_hash[:10], exc)
            return {"tx_hash": tx_hash, "screenshots": []}

        try:
            success = self._wait_for_screenshots_or_exit(proc, screenshots_dir, selector, tx_hash)
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=3)

        if not success:
            return {"tx_hash": tx_hash, "screenshots": []}

        all_pngs = sorted(screenshots_dir.glob("screenshot_*.png"), key=_sort_key)

        if len(all_pngs) > TRIM_HEAD + TRIM_TAIL + 1:
            meaningful = all_pngs[TRIM_HEAD : len(all_pngs) - TRIM_TAIL]
        elif len(all_pngs) > TRIM_HEAD:
            meaningful = all_pngs[TRIM_HEAD:]
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
