"""Core setup and chain-level API metadata helpers."""

import json
import logging
import os
from typing import Any

import requests
from web3 import Web3

from ....rpc_helpers import (
    etherscan_response_indicates_chain_unsupported,
    is_etherscan_tx_endpoint_unsupported,
    mark_etherscan_tx_endpoint_unsupported,
    rpc_request,
)
from ..constants import BLOCKSCOUT_URLS, SNOWFLAKE_ALLIUM_DATABASES

logger = logging.getLogger(__name__)


class TransactionFetcherCoreBaseMixin:
    def __init__(self, etherscan_api_key: str | None = None, lookback_days: int = 20):
        """
        Initialize the transaction fetcher.

        Args:
            etherscan_api_key: Etherscan API key for fetching data
            lookback_days: Number of days to look back for transaction history
        """
        self.etherscan_api_key = etherscan_api_key
        self.lookback_days = lookback_days
        self.w3 = Web3()
        self.token_decimals_cache = {}
        self.token_symbol_cache = {}
        self.api_type_per_chain = {}  # Track which API worked for each chain
        self._snowflake_transaction_row_cache: dict[tuple[int, str], dict[str, Any]] = {}
        self._snowflake_enabled = self._read_bool_env("SNOWFLAKE_ENABLED", default=True)
        self._snowflake_account = self._read_first_env("SNOWFLAKE_ACCOUNT", "SNOWFLAKE_INSTANCE")
        self._snowflake_user = os.getenv("SNOWFLAKE_USER", "").strip()
        self._snowflake_role = os.getenv("SNOWFLAKE_ROLE", "").strip()
        self._snowflake_warehouse = os.getenv("SNOWFLAKE_WAREHOUSE", "").strip()
        self._snowflake_database = os.getenv("SNOWFLAKE_DATABASE", "").strip()
        self._snowflake_schema = os.getenv("SNOWFLAKE_SCHEMA", "RAW").strip() or "RAW"
        self._snowflake_transactions_table = (
            os.getenv("SNOWFLAKE_TRANSACTIONS_TABLE", "TRANSACTIONS").strip() or "TRANSACTIONS"
        )
        self._snowflake_logs_table = os.getenv("SNOWFLAKE_LOGS_TABLE", "LOGS").strip() or "LOGS"
        self._snowflake_private_key = self._read_first_env("SNOWFLAKE_PRIVATE_KEY", "PRIVATE_KEY")
        self._snowflake_private_key_password = self._read_first_env(
            "SNOWFLAKE_PRIVATE_KEY_PASSWORD",
            "SNOWFLAKE_PRIVATE_KEY_PASSPHRASE",
            "PRIVATE_KEY_PASSPHRASE",
            "PRIVATE_KEY_PASSWORD",
        )
        self._snowflake_public_key = self._read_first_env("SNOWFLAKE_PUBLIC_KEY", "PUBLIC_KEY")
        self._snowflake_fingerprint = self._read_first_env("SNOWFLAKE_FINGERPRINT", "FINGERPRINT")
        self._snowflake_key_type = self._read_first_env("SNOWFLAKE_KEY_TYPE", "KEY_TYPE")
        self._snowflake_database_map = self._load_snowflake_database_map()
        self._tx_sample_rows_per_selector = self._read_int_env(
            "TX_SAMPLE_ROWS_PER_SELECTOR",
            self._read_int_env("SNOWFLAKE_SAMPLE_ROWS_PER_SELECTOR", 25),
        )
        self._snowflake_sample_rows_per_selector = self._tx_sample_rows_per_selector
        self._snowflake_login_timeout = self._read_optional_int_env("SNOWFLAKE_LOGIN_TIMEOUT_SECONDS")
        self._snowflake_network_timeout = self._read_optional_int_env("SNOWFLAKE_NETWORK_TIMEOUT_SECONDS")
        self._snowflake_socket_timeout = self._read_optional_int_env("SNOWFLAKE_SOCKET_TIMEOUT_SECONDS")

        if self._snowflake_tx_history_enabled():
            logger.info(
                "Snowflake transaction source enabled (schema=%s, table=%s)",
                self._snowflake_schema,
                self._snowflake_transactions_table,
            )

    def _read_first_env(self, *names: str) -> str:
        """Return the first non-empty environment variable from the provided names."""
        for name in names:
            value = os.getenv(name)
            if value and value.strip():
                return value.strip()
        return ""

    def _read_bool_env(self, name: str, *, default: bool) -> bool:
        """Parse a permissive boolean environment variable."""
        value = os.getenv(name)
        if value is None:
            return default
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        return default

    def _read_int_env(self, name: str, default: int) -> int:
        """Parse an integer environment variable with a safe fallback."""
        value = os.getenv(name)
        if value is None:
            return default
        try:
            return int(value.strip())
        except ValueError:
            logger.warning("Invalid integer for %s: %r. Using default %s.", name, value, default)
            return default

    def _read_optional_int_env(self, name: str) -> int | None:
        """Parse an optional integer environment variable, returning None when unset."""
        value = os.getenv(name)
        if value is None or not value.strip():
            return None
        try:
            parsed = int(value.strip())
        except ValueError:
            logger.warning("Invalid integer for %s: %r. Ignoring it.", name, value)
            return None
        if parsed <= 0:
            return None
        return parsed

    def _normalize_multiline_secret(self, value: str | None) -> str | None:
        """Expand escaped newlines commonly used in environment-stored PEM values."""
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        return normalized.replace("\\n", "\n")

    def _load_snowflake_database_map(self) -> dict[int, str]:
        """Load optional per-chain Snowflake database overrides from the environment."""
        raw_value = self._read_first_env("SNOWFLAKE_DATABASES_JSON", "SNOWFLAKE_DATABASE_MAP")
        if not raw_value:
            return {}

        try:
            if raw_value.lstrip().startswith("{"):
                parsed = json.loads(raw_value)
                items = parsed.items()
            else:
                items = []
                for entry in raw_value.split(","):
                    entry = entry.strip()
                    if not entry:
                        continue
                    if "=" not in entry:
                        raise ValueError(f"expected CHAIN_ID=DATABASE pair, got {entry!r}")
                    key, value = entry.split("=", 1)
                    items.append((key.strip(), value.strip()))
        except Exception as exc:
            logger.warning("Failed to parse Snowflake database mapping: %s", exc)
            return {}

        database_map: dict[int, str] = {}
        for key, value in items:
            try:
                chain_id = int(str(key).strip())
            except ValueError:
                logger.warning("Ignoring Snowflake database mapping with non-integer chain id: %r", key)
                continue
            if not value:
                continue
            database_map[chain_id] = str(value).strip()
        return database_map

    def _snowflake_tx_history_enabled(self) -> bool:
        """Return whether Snowflake transaction history is enabled and minimally configured."""
        if not self._snowflake_enabled:
            return False
        required = [
            self._snowflake_account,
            self._snowflake_user,
            self._snowflake_role,
            self._snowflake_warehouse,
        ]
        return all(required)

    def _get_snowflake_database_for_chain(self, chain_id: int) -> str | None:
        """Resolve the Snowflake database for a chain using env overrides then built-in defaults."""
        if self._snowflake_database:
            return self._snowflake_database
        chain_id = int(chain_id)
        return self._snowflake_database_map.get(chain_id) or SNOWFLAKE_ALLIUM_DATABASES.get(chain_id)

    def _snowflake_chain_available(self, chain_id: int) -> bool:
        """Return whether Snowflake is enabled and a database is configured for the chain."""
        return self._snowflake_tx_history_enabled() and bool(self._get_snowflake_database_for_chain(chain_id))

    def _tx_sample_candidate_limit(self, per_selector: int) -> int:
        """Return how many candidate rows to gather before final sampling."""
        return max(int(per_selector), int(self._tx_sample_rows_per_selector))

    def _transaction_identity_key(self, tx: dict[str, Any]) -> str:
        """Build a stable dedupe key for a transaction-like dictionary."""
        tx_hash = str(tx.get("hash") or "").strip().lower()
        if tx_hash:
            return f"hash:{tx_hash}"
        return (
            "fallback:"
            f"{tx.get('input', '')}|{tx.get('value', '')}|{tx.get('blockNumber', '')}|"
            f"{tx.get('timeStamp', '')}|{tx.get('from', '')}|{tx.get('to', '')}"
        )

    def _transaction_origin_key(self, tx: dict[str, Any]) -> str:
        """Return the best available transaction origin/sender key for diversity sampling."""
        origin = (
            str(tx.get("tx_origin") or tx.get("txOrigin") or tx.get("origin") or tx.get("from") or "").strip().lower()
        )
        return origin

    def _select_diverse_transactions(
        self,
        candidates: list[dict[str, Any]],
        limit: int,
        *,
        used_identity_keys: set[str] | None = None,
        used_origins: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Prefer unseen origins first, then fill remaining slots with any candidates."""
        if limit <= 0:
            return []

        seen_keys = set(used_identity_keys or set())
        blocked_origins = {origin for origin in (used_origins or set()) if origin}
        selected: list[dict[str, Any]] = []

        for tx in candidates:
            identity_key = self._transaction_identity_key(tx)
            origin_key = self._transaction_origin_key(tx)
            if identity_key in seen_keys:
                continue
            if origin_key and origin_key in blocked_origins:
                continue
            selected.append(tx)
            seen_keys.add(identity_key)
            if origin_key:
                blocked_origins.add(origin_key)
            if len(selected) >= limit:
                return selected

        for tx in candidates:
            identity_key = self._transaction_identity_key(tx)
            if identity_key in seen_keys:
                continue
            selected.append(tx)
            seen_keys.add(identity_key)
            if len(selected) >= limit:
                break

        return selected

    def _finalize_selector_transaction_samples(
        self,
        candidates_by_selector: dict[str, list[dict[str, Any]]],
        *,
        per_selector: int,
        payable_selectors: set[str] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Finalize selector samples with sender diversity and payable value balancing."""
        payable_selector_set = {selector.lower() for selector in (payable_selectors or set())}
        finalized: dict[str, list[dict[str, Any]]] = {}

        for selector, candidates in candidates_by_selector.items():
            selector_lower = selector.lower()
            if selector_lower not in payable_selector_set:
                finalized[selector] = self._select_diverse_transactions(candidates, per_selector)
                continue

            native_candidates = [tx for tx in candidates if int(str(tx.get("value", "0") or "0")) > 0]
            zero_value_candidates = [tx for tx in candidates if int(str(tx.get("value", "0") or "0")) <= 0]

            selected: list[dict[str, Any]] = []
            used_identity_keys: set[str] = set()
            used_origins: set[str] = set()

            for bucket in (native_candidates, zero_value_candidates):
                bucket_pick = self._select_diverse_transactions(
                    bucket,
                    1,
                    used_identity_keys=used_identity_keys,
                    used_origins=used_origins,
                )
                if not bucket_pick:
                    continue
                selected.extend(bucket_pick)
                used_identity_keys.update(self._transaction_identity_key(tx) for tx in bucket_pick)
                used_origins.update(
                    origin for origin in (self._transaction_origin_key(tx) for tx in bucket_pick) if origin
                )

            if len(selected) < per_selector:
                remaining = self._select_diverse_transactions(
                    candidates,
                    per_selector - len(selected),
                    used_identity_keys=used_identity_keys,
                    used_origins=used_origins,
                )
                selected.extend(remaining)

            finalized[selector] = selected[:per_selector]

        return finalized

    def _get_api_base_url(self, chain_id: int, use_blockscout: bool = False) -> str:
        """
        Get the appropriate API base URL for a chain.

        Args:
            chain_id: Chain ID
            use_blockscout: Force use of Blockscout API

        Returns:
            Base URL for API requests
        """
        chain_id = int(chain_id)  # Ensure it's an int
        if use_blockscout and chain_id in BLOCKSCOUT_URLS:
            return BLOCKSCOUT_URLS[chain_id]
        return f"https://api.etherscan.io/v2/api?chainid={chain_id}"

    def _get_current_block_number(self, chain_id: int, use_blockscout: bool = False) -> int | None:
        """
        Get the current block number using eth_blockNumber.

        Args:
            chain_id: Chain ID
            use_blockscout: Use Blockscout API instead of Etherscan

        Returns:
            Current block number or None if error
        """
        chain_id = int(chain_id)

        # Special handling for Core DAO (chain 1116) - uses Etherscan-style API
        if chain_id == 1116 and use_blockscout:
            return self._get_coredao_block_number()

        # Use Blockscout v2 API if available
        if use_blockscout and chain_id in BLOCKSCOUT_URLS:
            stats = self._fetch_blockscout_v2_stats(chain_id)
            if stats and "total_blocks" in stats:
                try:
                    # total_blocks is a string like "60681962"
                    block_number = int(stats["total_blocks"])
                    return block_number
                except (ValueError, TypeError):
                    logger.debug("Failed to parse block number from Blockscout v2 stats")
            return None

        params = {
            "module": "proxy",
            "action": "eth_blockNumber",
        }

        # Etherscan requires API key
        if not use_blockscout:
            if is_etherscan_tx_endpoint_unsupported(chain_id):
                logger.debug(
                    "Skipping Etherscan eth_blockNumber on chain %s: endpoint already marked unsupported", chain_id
                )
                return None
            if not self.etherscan_api_key:
                return None
            params["apikey"] = self.etherscan_api_key

        try:
            base_url = self._get_api_base_url(chain_id, use_blockscout)
            response = requests.get(base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if not use_blockscout and etherscan_response_indicates_chain_unsupported(data):
                mark_etherscan_tx_endpoint_unsupported(chain_id)
                logger.debug("Marked Etherscan tx endpoints unsupported for chain %s after eth_blockNumber", chain_id)
                return None

            if data.get("result"):
                block_number = int(data["result"], 16)
                return block_number
        except Exception as e:
            logger.debug(f"Failed to get current block number via explorer: {e}")

        result, rpc_err, rpc_url = rpc_request(chain_id, "eth_blockNumber", [], timeout=10)
        if result:
            try:
                block_number = int(result, 16)
                logger.debug("Fetched block number %d via RPC fallback (%s)", block_number, rpc_url)
                return block_number
            except (ValueError, TypeError):
                pass
        if rpc_err:
            logger.debug("RPC blockNumber fallback failed for chain %s: %s", chain_id, rpc_err)

        return None

    def _get_coredao_block_number(self) -> int | None:
        """
        Get current block number from Core DAO API.

        Returns:
            Current block number or None if error
        """
        try:
            import os

            from dotenv import load_dotenv

            load_dotenv(override=True)
            coredao_api_key = os.getenv("COREDAO_API_KEY", "")

            base_url = BLOCKSCOUT_URLS[1116]
            params = {"module": "proxy", "action": "eth_blockNumber"}

            if coredao_api_key:
                params["apikey"] = coredao_api_key

            response = requests.get(base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get("result"):
                # Result is in hex format (0x...)
                block_number = int(data["result"], 16)
                logger.info(f"Core DAO current block number: {block_number}")
                return block_number
            return None
        except Exception as e:
            logger.debug(f"Failed to get Core DAO block number: {e}")
            return None

    def _fetch_blockscout_v2_stats(self, chain_id: int) -> dict[str, Any] | None:
        """
        Fetch stats from Blockscout v2 API to get current block number.

        Args:
            chain_id: Chain ID

        Returns:
            Stats dictionary or None if error
        """
        chain_id = int(chain_id)
        if chain_id not in BLOCKSCOUT_URLS:
            return None

        try:
            base_url = BLOCKSCOUT_URLS[chain_id]
            response = requests.get(f"{base_url}/api/v2/stats", timeout=10)
            response.raise_for_status()
            data = response.json()
            return data
        except Exception as e:
            logger.debug(f"Failed to fetch Blockscout v2 stats: {e}")
            return None
