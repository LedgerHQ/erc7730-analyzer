"""Run cs-tester CLI to capture Ledger device screenshots for transactions."""

import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, TypedDict

from .raw_tx import fetch_raw_transaction_async

logger = logging.getLogger(__name__)

DEFAULT_CS_TESTER_ROOT = os.path.expanduser("~/Desktop/clear_sign/device-sdk-ts")
DEFAULT_COIN_APPS_PATH = os.path.expanduser("~/Desktop/clear_sign/coin-apps")
MAX_TXS_PER_SELECTOR = 2
CS_TESTER_MAX_RETRIES = 3
CS_TESTER_RETRY_DELAY = 3
TRIM_HEAD = 3
TRIM_TAIL = 3


class TxScreenshots(TypedDict):
    tx_hash: str
    screenshots: list[str]


class ScreenshotRunner:
    """Generate Ledger device screenshots using cs-tester + Speculos."""

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
        self.device = os.getenv("CS_TESTER_DEVICE", device)

    def is_available(self) -> bool:
        """Check that cs-tester root, coin-apps, pnpm, and Docker are all present."""
        if not (self.cs_tester_root / "apps" / "clear-signing-tester").is_dir():
            logger.warning("[SCREENSHOTS] cs-tester not found at %s", self.cs_tester_root)
            return False
        if not self.coin_apps_path.is_dir():
            logger.warning("[SCREENSHOTS] coin-apps not found at %s", self.coin_apps_path)
            return False
        if not shutil.which("pnpm") and not shutil.which("proto"):
            logger.warning("[SCREENSHOTS] pnpm not found on PATH")
            return False
        if not shutil.which("docker"):
            logger.warning("[SCREENSHOTS] docker not found on PATH")
            return False
        return True

    # ------------------------------------------------------------------
    # Async entry point
    # ------------------------------------------------------------------

    async def capture_for_selector_async(
        self,
        *,
        selector: str,
        chain_id: int,
        transactions: list[dict[str, Any]],
        erc7730_file: Path,
    ) -> list[TxScreenshots]:
        """
        Capture screenshots for up to MAX_TXS_PER_SELECTOR transactions.

        Runs each transaction through cs-tester individually so screenshots
        can be cleanly associated with their tx hash, and trims the
        non-meaningful boot/confirm frames (first TRIM_HEAD, last TRIM_TAIL).
        """
        txs_to_process = transactions[:MAX_TXS_PER_SELECTOR]
        if not txs_to_process:
            return []

        # Fetch all raw transactions concurrently
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

        # Run all txs concurrently, then retry failures as a batch
        pending = list(raw_entries)
        completed: list[TxScreenshots] = []

        for attempt in range(CS_TESTER_MAX_RETRIES):
            if not pending:
                break

            coros = [
                asyncio.to_thread(
                    self._run_cs_tester_once,
                    selector,
                    tx_hash,
                    raw_tx,
                    erc7730_file,
                    attempt,
                )
                for tx_hash, raw_tx in pending
            ]
            batch_results = await asyncio.gather(*coros, return_exceptions=True)

            next_pending: list[tuple[str, str]] = []
            for (tx_hash, raw_tx), result in zip(pending, batch_results):
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
        """
        Run screenshot capture for all selectors concurrently.

        Returns:
            Map of selector (lowercase) -> list of TxScreenshots.
        """

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
        """Run cs-tester for a single transaction (one attempt), then trim.

        Returns a TxScreenshots dict.  An empty ``screenshots`` list signals
        failure so the caller can schedule a retry.
        """
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

        cmd = [
            "pnpm",
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
        ]

        env = {**os.environ, "COIN_APPS_PATH": str(self.coin_apps_path)}

        if attempt == 0:
            logger.info(
                "[SCREENSHOTS][%s] Running cs-tester for tx %s device=%s",
                selector,
                tx_hash[:10],
                self.device,
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

        # Collect and trim
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
