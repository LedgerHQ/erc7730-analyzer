"""Run cs-tester CLI to capture Ledger device screenshots for transactions."""

import asyncio
import importlib.util
import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, TypedDict

import requests

from .raw_tx import fetch_raw_transaction_async

logger = logging.getLogger(__name__)

DEFAULT_RUNTIME_ROOT = Path(os.getenv("CS_TESTER_RUNTIME_ROOT", "/tmp/erc7730-screenshots"))
_LEGACY_CS_TESTER_ROOT = Path(os.path.expanduser("~/Desktop/clear_sign/device-sdk-ts"))
_LEGACY_COIN_APPS_PATH = Path(os.path.expanduser("~/Desktop/clear_sign/coin-apps"))
DEFAULT_CS_TESTER_ROOT = str(
    _LEGACY_CS_TESTER_ROOT if _LEGACY_CS_TESTER_ROOT.exists() else DEFAULT_RUNTIME_ROOT / "device-sdk-ts"
)
DEFAULT_COIN_APPS_PATH = str(
    _LEGACY_COIN_APPS_PATH if _LEGACY_COIN_APPS_PATH.exists() else DEFAULT_RUNTIME_ROOT / "coin-apps"
)
DEFAULT_ETH_APP_ELF_ROOT = str(DEFAULT_RUNTIME_ROOT / "ethereum-app-elfs")

DEVICE_ALIASES = {
    "nanosp": "nanos2",
}


def normalize_device_name(device: str) -> str:
    """Map analyzer/device-sdk aliases to artifact directory names."""
    device_name = (device or "").strip().lower()
    return DEVICE_ALIASES.get(device_name, device_name)


SPECULOS_BASE_API_PORT = int(os.getenv("SPECULOS_BASE_API_PORT", "5000"))
SPECULOS_STARTUP_TIMEOUT = float(os.getenv("SPECULOS_STARTUP_TIMEOUT", "20"))
SPECULOS_SHUTDOWN_GRACE_SEC = float(os.getenv("SPECULOS_SHUTDOWN_GRACE_SEC", "5"))
MAX_TXS_PER_SELECTOR = 2
MAX_CONCURRENT_SPECULOS = 1
CS_TESTER_MAX_RETRIES = 3
CS_TESTER_RETRY_DELAY = 3
CS_TESTER_TIMEOUT_SEC = 180
CS_TESTER_STABLE_AFTER_SEC = 3.0
CS_TESTER_POLL_INTERVAL_SEC = 0.5
CS_TESTER_SHUTDOWN_GRACE_SEC = 5.0
LOG_TAIL_CHARS = 800
TRIM_HEAD = 3
TRIM_TAIL = 3

_SPECULOS_PORT_LOCK = threading.Lock()
_RESERVED_PORTS: set[int] = set()


class TxScreenshots(TypedDict):
    tx_hash: str
    screenshots: list[str]


def _tcp_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.2)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _allocate_speculos_api_apdu_ports() -> tuple[int, int]:
    """Return a pair (api_port, apdu_port) with consecutive free ports.

    Ports are added to ``_RESERVED_PORTS`` so that concurrent threads cannot
    allocate the same pair before Speculos actually binds them.  The caller
    **must** call ``_release_speculos_ports`` when done (typically in a
    ``finally`` block).
    """
    with _SPECULOS_PORT_LOCK:
        candidate = SPECULOS_BASE_API_PORT
        while candidate < 65534:
            api, apdu = candidate, candidate + 1
            if (
                api not in _RESERVED_PORTS
                and apdu not in _RESERVED_PORTS
                and not _tcp_port_in_use(api)
                and not _tcp_port_in_use(apdu)
            ):
                _RESERVED_PORTS.add(api)
                _RESERVED_PORTS.add(apdu)
                return api, apdu
            candidate += 2
        raise RuntimeError("Could not allocate free TCP ports for Speculos (api + apdu)")


def _release_speculos_ports(api_port: int, apdu_port: int) -> None:
    """Release previously reserved ports so they can be reused."""
    with _SPECULOS_PORT_LOCK:
        _RESERVED_PORTS.discard(api_port)
        _RESERVED_PORTS.discard(apdu_port)


def _subprocess_output_tail(value: str | bytes | None, limit: int = LOG_TAIL_CHARS) -> str:
    """Return a readable tail of subprocess output for timeout diagnostics."""
    if value is None:
        return "(no output)"
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    text = value.strip()
    if not text:
        return "(no output)"
    return text[-limit:] if len(text) > limit else text


def _file_output_tail(path: Path, limit: int = LOG_TAIL_CHARS) -> str:
    """Return a readable tail of a subprocess log file."""
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(size - (limit * 4), 0), os.SEEK_SET)
            return _subprocess_output_tail(handle.read(), limit=limit)
    except OSError:
        return "(no output)"


class ScreenshotRunner:
    """Generate Ledger device screenshots using cs-tester + native Speculos.

    In the Docker/API deployment model, device-sdk-ts and the Ethereum app ELF
    are baked into the image at build time. At runtime the runner only verifies
    those assets exist, then starts Speculos via the Python ``speculos`` package;
    cs-tester uses ``--external-speculos`` to attach to that instance.
    """

    def __init__(
        self,
        etherscan_api_key: str,
        cs_tester_root: str | None = None,
        coin_apps_path: str | None = None,
        device: str = "stax",
    ):
        self.etherscan_api_key = etherscan_api_key
        self.cs_tester_root = Path(cs_tester_root or os.getenv("CS_TESTER_ROOT", DEFAULT_CS_TESTER_ROOT))
        self.coin_apps_path = Path(coin_apps_path or os.getenv("COIN_APPS_PATH", DEFAULT_COIN_APPS_PATH))
        self.eth_app_elf_root = Path(os.getenv("ETH_APP_ELF_ROOT", DEFAULT_ETH_APP_ELF_ROOT))
        self.device = os.getenv("CS_TESTER_DEVICE", device)
        self.gating_token = os.getenv("GATING_TOKEN", "").strip()
        self._speculos_sem: asyncio.Semaphore | None = None
        self._persistent_speculos_proc: subprocess.Popen | None = None
        self._persistent_speculos_api_port: int | None = None
        self._persistent_speculos_apdu_port: int | None = None
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
            self._add_unavailability_reason(
                f"no Ethereum app ELF at {self._artifact_elf_path()} — rebuild the Docker image or set ETH_APP_ELF_ROOT"
            )
            return False
        if not shutil.which("pnpm") and not shutil.which("corepack"):
            self._add_unavailability_reason("pnpm/corepack not found on PATH")
            return False
        if importlib.util.find_spec("speculos") is None:
            self._add_unavailability_reason("speculos Python package not installed")
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

    def _artifact_elf_path(self) -> Path:
        normalized_device = normalize_device_name(self.device)
        return self.eth_app_elf_root / normalized_device / "bin" / "app.elf"

    def _has_artifact_elf(self) -> bool:
        return self._artifact_elf_path().is_file()

    def _has_any_ethereum_app(self) -> bool:
        return self._has_artifact_elf()

    def _speculos_model(self) -> str:
        """Map analyzer/device aliases to ``speculos -m`` model names."""
        normalized = normalize_device_name(self.device)
        if normalized == "nanos2":
            return "nanosp"
        allowed = {"nanox", "nanosp", "stax", "flex", "apex_p"}
        if normalized in allowed:
            return normalized
        d = (self.device or "").strip().lower()
        return d if d in allowed else "stax"

    # ------------------------------------------------------------------
    # Runtime readiness
    # ------------------------------------------------------------------

    def _ensure_runtime_ready(self) -> bool:
        """Verify pre-built assets exist (no runtime downloads or git/pnpm updates)."""
        if not (self.cs_tester_root / "apps" / "clear-signing-tester").is_dir():
            self._add_unavailability_reason(
                f"device-sdk-ts not found at {self.cs_tester_root} — build the Docker image or clone manually"
            )
            return False
        if not self._has_any_ethereum_app():
            self._add_unavailability_reason(
                f"no Ethereum app ELF at {self._artifact_elf_path()} — rebuild the Docker image or set ETH_APP_ELF_ROOT"
            )
            return False
        return True

    # ------------------------------------------------------------------
    # Native Speculos (Python package)
    # ------------------------------------------------------------------

    def _wait_for_speculos_ready(self, api_port: int, timeout: float) -> None:
        """Poll Speculos HTTP API until it responds or ``timeout`` seconds elapse."""
        url = f"http://127.0.0.1:{api_port}/"
        deadline = time.monotonic() + timeout
        last_err: str | None = None
        while time.monotonic() < deadline:
            try:
                resp = requests.get(url, timeout=1.0)
                if resp.status_code < 500:
                    return
                last_err = f"HTTP {resp.status_code}"
            except requests.RequestException as exc:
                last_err = str(exc)
            time.sleep(0.15)
        raise TimeoutError(f"Speculos did not become ready on port {api_port}: {last_err or 'unknown'}")

    def _start_speculos_process(self, elf_path: Path, api_port: int, apdu_port: int) -> subprocess.Popen:
        """Launch Speculos as a subprocess (headless).

        Stderr is captured via PIPE so that crash diagnostics are available
        when the process exits unexpectedly (e.g. missing qemu/binfmt inside
        a container).  Call ``_read_speculos_stderr`` to drain it.
        """
        cmd = [
            sys.executable,
            "-m",
            "speculos",
            "--model",
            self._speculos_model(),
            "--api-port",
            str(api_port),
            "--apdu-port",
            str(apdu_port),
            "--display",
            "headless",
            str(elf_path.resolve()),
        ]
        logger.info(
            "[SCREENSHOTS][SETUP] Starting native Speculos api=%s apdu=%s model=%s elf=%s",
            api_port,
            apdu_port,
            self._speculos_model(),
            elf_path,
        )
        return subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            env=dict(os.environ),
        )

    @staticmethod
    def _read_speculos_stderr(proc: subprocess.Popen | None, limit: int = LOG_TAIL_CHARS) -> str:
        """Drain and return up to *limit* chars from a Speculos process's stderr."""
        if proc is None or proc.stderr is None:
            return ""
        try:
            raw = proc.stderr.read()
            text = raw.decode("utf-8", errors="replace").strip() if isinstance(raw, bytes) else str(raw).strip()
            return text[-limit:] if len(text) > limit else text
        except Exception:
            return ""

    @staticmethod
    def _stop_speculos_process(proc: subprocess.Popen | None) -> None:
        if proc is None:
            return
        try:
            if proc.stderr is not None:
                try:
                    proc.stderr.close()
                except Exception:
                    pass
            if proc.poll() is not None:
                return
            proc.terminate()
            try:
                proc.wait(timeout=SPECULOS_SHUTDOWN_GRACE_SEC)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        except Exception as exc:
            logger.warning("[SCREENSHOTS][SETUP] Error stopping Speculos process: %s", exc)

    def _start_persistent_speculos(self) -> None:
        """Start one native Speculos instance for the current screenshot batch."""
        if self._persistent_speculos_proc is not None and self._persistent_speculos_proc.poll() is None:
            return

        custom_app_path = self._artifact_elf_path()
        if not custom_app_path.is_file():
            raise RuntimeError(f"No Ethereum app ELF at {custom_app_path}")

        api_port, apdu_port = _allocate_speculos_api_apdu_ports()
        proc: subprocess.Popen | None = None
        logger.info(
            "[SCREENSHOTS][SETUP] Starting persistent native Speculos api=%s apdu=%s model=%s elf=%s",
            api_port,
            apdu_port,
            self._speculos_model(),
            custom_app_path,
        )
        try:
            proc = self._start_speculos_process(custom_app_path, api_port, apdu_port)
            time.sleep(0.1)
            if proc.poll() is not None:
                stderr_tail = self._read_speculos_stderr(proc)
                raise RuntimeError(
                    f"Persistent Speculos exited immediately (code={proc.returncode}). stderr:\n"
                    f"{stderr_tail or '(empty)'}"
                )
            self._wait_for_speculos_ready(api_port, SPECULOS_STARTUP_TIMEOUT)
        except Exception:
            self._stop_speculos_process(proc)
            _release_speculos_ports(api_port, apdu_port)
            raise

        self._persistent_speculos_proc = proc
        self._persistent_speculos_api_port = api_port
        self._persistent_speculos_apdu_port = apdu_port
        logger.info("[SCREENSHOTS][SETUP] Persistent Speculos ready on api=%s apdu=%s", api_port, apdu_port)

    def _stop_persistent_speculos(self) -> None:
        """Stop the current persistent Speculos instance and free its ports."""
        proc = self._persistent_speculos_proc
        api_port = self._persistent_speculos_api_port
        apdu_port = self._persistent_speculos_apdu_port

        self._persistent_speculos_proc = None
        self._persistent_speculos_api_port = None
        self._persistent_speculos_apdu_port = None

        if proc is not None:
            logger.info("[SCREENSHOTS][SETUP] Stopping persistent Speculos api=%s apdu=%s", api_port, apdu_port)
        self._stop_speculos_process(proc)
        if api_port is not None and apdu_port is not None:
            _release_speculos_ports(api_port, apdu_port)

    def _restart_persistent_speculos(self) -> None:
        """Restart Speculos to reset app state between cs-tester invocations."""
        logger.info("[SCREENSHOTS][SETUP] Restarting persistent Speculos for clean app state")
        self._stop_persistent_speculos()
        self._start_persistent_speculos()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _pnpm_cmd(self, *args: str) -> list[str]:
        if shutil.which("pnpm"):
            return ["pnpm", *args]
        return ["corepack", "pnpm", *args]

    @staticmethod
    def _screenshot_progress_signature(screenshots_dir: Path) -> tuple[int, int]:
        """Summarize screenshot progress as (file_count, latest_mtime_ns)."""
        pngs = list(screenshots_dir.glob("screenshot_*.png"))
        if not pngs:
            return 0, 0
        latest_mtime_ns = max(p.stat().st_mtime_ns for p in pngs)
        return len(pngs), latest_mtime_ns

    def _wait_for_screenshots_or_exit(
        self,
        proc: subprocess.Popen,
        screenshots_dir: Path,
        selector: str,
        tx_hash: str,
        *,
        stdout_log: Path,
        stderr_log: Path,
        max_wait: float = CS_TESTER_TIMEOUT_SEC,
        stable_after: float = CS_TESTER_STABLE_AFTER_SEC,
        poll_interval: float = CS_TESTER_POLL_INTERVAL_SEC,
    ) -> bool:
        """Wait for cs-tester to exit or for screenshots to stop changing.

        ``clear-signing-tester`` can hang after successfully producing screenshots
        when attached to an externally managed Speculos. Treat stable screenshots
        as success so the caller can terminate the lingering process.
        """
        deadline = time.monotonic() + max_wait
        last_signature = self._screenshot_progress_signature(screenshots_dir)
        last_change_at = time.monotonic()

        while time.monotonic() < deadline:
            ret = proc.poll()
            current_signature = self._screenshot_progress_signature(screenshots_dir)

            if current_signature != last_signature:
                last_signature = current_signature
                last_change_at = time.monotonic()

            if ret is not None:
                if ret == 0:
                    logger.info("[SCREENSHOTS][%s] cs-tester completed for tx %s", selector, tx_hash[:10])
                    return True
                speculos_status = "unknown"
                speculos_stderr_tail = "(no output)"
                if self._persistent_speculos_proc is not None:
                    speculos_ret = self._persistent_speculos_proc.poll()
                    if speculos_ret is None:
                        speculos_status = "running"
                    else:
                        speculos_status = f"exited(code={speculos_ret})"
                        if logger.isEnabledFor(logging.DEBUG):
                            speculos_stderr_tail = (
                                self._read_speculos_stderr(self._persistent_speculos_proc) or "(empty)"
                            )
                logger.warning(
                    "[SCREENSHOTS][%s] cs-tester exited with code %d for tx %s (persistent Speculos: %s)",
                    selector,
                    ret,
                    tx_hash[:10],
                    speculos_status,
                )
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "[SCREENSHOTS][%s] cs-tester failure details for tx %s\n"
                        "persistent Speculos stderr:\n%s\nstdout:\n%s\nstderr:\n%s",
                        selector,
                        tx_hash[:10],
                        speculos_stderr_tail,
                        _file_output_tail(stdout_log),
                        _file_output_tail(stderr_log),
                    )
                return False

            if last_signature[0] > 0 and (time.monotonic() - last_change_at) >= stable_after:
                logger.info(
                    "[SCREENSHOTS][%s] %d screenshot(s) stable for %.1fs; terminating lingering cs-tester for tx %s",
                    selector,
                    last_signature[0],
                    stable_after,
                    tx_hash[:10],
                )
                return True

            time.sleep(poll_interval)

        logger.warning(
            "[SCREENSHOTS][%s] cs-tester timed out after %ss for tx %s (screenshots=%d)",
            selector,
            max_wait,
            tx_hash[:10],
            last_signature[0],
        )
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "[SCREENSHOTS][%s] cs-tester timeout details for tx %s\nstdout:\n%s\nstderr:\n%s",
                selector,
                tx_hash[:10],
                _file_output_tail(stdout_log),
                _file_output_tail(stderr_log),
            )
        return False

    # ------------------------------------------------------------------
    # Async entry point
    # ------------------------------------------------------------------

    def _get_speculos_semaphore(self) -> asyncio.Semaphore:
        """Lazily create a per-event-loop semaphore to cap concurrent Speculos instances."""
        if self._speculos_sem is None:
            self._speculos_sem = asyncio.Semaphore(MAX_CONCURRENT_SPECULOS)
        return self._speculos_sem

    async def _run_cs_tester_throttled(
        self,
        selector: str,
        tx_hash: str,
        raw_tx: str,
        erc7730_file: Path,
        attempt: int,
    ) -> TxScreenshots:
        """Run a single cs-tester invocation, throttled by the Speculos semaphore."""
        sem = self._get_speculos_semaphore()
        async with sem:
            try:
                return await asyncio.to_thread(
                    self._run_cs_tester_once,
                    selector,
                    tx_hash,
                    raw_tx,
                    erc7730_file,
                    attempt,
                )
            finally:
                if self._persistent_speculos_proc is not None:
                    try:
                        await asyncio.to_thread(self._restart_persistent_speculos)
                    except Exception as exc:
                        logger.warning(
                            "[SCREENSHOTS][%s] Failed to restart Speculos after tx %s: %s",
                            selector,
                            tx_hash[:10],
                            exc,
                        )
                        self._stop_persistent_speculos()

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

        Concurrent Speculos instances are capped at MAX_CONCURRENT_SPECULOS.
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
        try:
            await asyncio.to_thread(self._start_persistent_speculos)
        except Exception as exc:
            logger.warning("[SCREENSHOTS] Failed to start persistent Speculos: %s", exc)
            return {}

        try:

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
        finally:
            await asyncio.to_thread(self._stop_persistent_speculos)

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
        if not custom_app_path.is_file():
            logger.warning(
                "[SCREENSHOTS][%s] No Ethereum app ELF at %s for device %s",
                selector,
                custom_app_path,
                self.device,
            )
            return {"tx_hash": tx_hash, "screenshots": []}

        staged_erc7730_file = screenshots_dir / Path(erc7730_file).name
        try:
            shutil.copy2(erc7730_file, staged_erc7730_file)
        except OSError as exc:
            logger.warning(
                "[SCREENSHOTS][%s] Failed to stage ERC-7730 file %s for tx %s: %s",
                selector,
                erc7730_file,
                tx_hash[:10],
                exc,
            )
            return {"tx_hash": tx_hash, "screenshots": []}

        cs_tester_proc: subprocess.Popen | None = None
        env = dict(os.environ)
        stdout_log = screenshots_dir / "cs_tester.stdout.log"
        stderr_log = screenshots_dir / "cs_tester.stderr.log"
        api_port = self._persistent_speculos_api_port

        if (
            api_port is None
            or self._persistent_speculos_proc is None
            or self._persistent_speculos_proc.poll() is not None
        ):
            logger.warning(
                "[SCREENSHOTS][%s] Persistent Speculos is not running for tx %s",
                selector,
                tx_hash[:10],
            )
            return {"tx_hash": tx_hash, "screenshots": []}

        if attempt == 0:
            logger.info(
                "[SCREENSHOTS][%s] Running cs-tester for tx %s device=%s custom_app=%s external_speculos api_port=%s",
                selector,
                tx_hash[:10],
                self.device,
                custom_app_path,
                api_port,
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
            cmd = [
                *self._pnpm_cmd(
                    "cs-tester",
                    "cli",
                    "--device",
                    self.device,
                    "--external-speculos",
                    "--speculos-port",
                    str(api_port),
                    "--screenshot-folder-path",
                    str(screenshots_dir),
                    "--erc7730-files",
                    str(staged_erc7730_file.resolve()),
                    "--log-level",
                    "warn",
                    "raw-file",
                    str(input_file),
                ),
            ]
            cmd.extend(["--custom-app", str(custom_app_path)])

            with (
                stdout_log.open("w", encoding="utf-8") as stdout_handle,
                stderr_log.open("w", encoding="utf-8") as stderr_handle,
            ):
                cs_tester_proc = subprocess.Popen(
                    cmd,
                    cwd=str(self.cs_tester_root),
                    env=env,
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                )
                success = self._wait_for_screenshots_or_exit(
                    cs_tester_proc,
                    screenshots_dir,
                    selector,
                    tx_hash,
                    stdout_log=stdout_log,
                    stderr_log=stderr_log,
                )
            if not success:
                return {"tx_hash": tx_hash, "screenshots": []}
        except FileNotFoundError:
            logger.warning("[SCREENSHOTS][%s] pnpm not found", selector)
            return {"tx_hash": tx_hash, "screenshots": []}
        except Exception as exc:
            logger.warning("[SCREENSHOTS][%s] cs-tester failed for tx %s: %s", selector, tx_hash[:10], exc)
            return {"tx_hash": tx_hash, "screenshots": []}
        finally:
            if cs_tester_proc is not None and cs_tester_proc.poll() is None:
                cs_tester_proc.terminate()
                try:
                    cs_tester_proc.wait(timeout=CS_TESTER_SHUTDOWN_GRACE_SEC)
                except subprocess.TimeoutExpired:
                    cs_tester_proc.kill()
                    try:
                        cs_tester_proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        logger.warning(
                            "[SCREENSHOTS][%s] Failed to stop lingering cs-tester process for tx %s",
                            selector,
                            tx_hash[:10],
                        )

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
