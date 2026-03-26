"""Snowflake-backed transaction history retrieval."""

import base64
import binascii
import logging
import re
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)
logging.getLogger("snowflake.connector").setLevel(logging.CRITICAL)
logging.getLogger("snowflake.connector.connection").setLevel(logging.CRITICAL)
logging.getLogger("snowflake.connector.network").setLevel(logging.CRITICAL)

_HEX_ADDRESS_RE = re.compile(r"^0x[a-f0-9]{40}$")
_HEX_SELECTOR_RE = re.compile(r"^0x[a-f0-9]{8}$")
_HEX_TX_HASH_RE = re.compile(r"^0x[a-f0-9]{64}$")
_SNOWFLAKE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")


class TransactionFetcherCoreSnowflakeMixin:
    def _snowflake_row_value(self, row: dict[str, Any], *names: str) -> Any:
        """Read a Snowflake row value using any of several case variants."""
        for name in names:
            if name in row:
                return row[name]
            upper_name = name.upper()
            if upper_name in row:
                return row[upper_name]
            lower_name = name.lower()
            if lower_name in row:
                return row[lower_name]
        return None

    def _fetch_transactions_from_snowflake(
        self,
        contract_address: str,
        selectors: list[str],
        chain_id: int,
        per_selector: int,
        payable_selectors: set | None,
    ) -> dict[str, list[dict[str, Any]]] | None:
        """Query Snowflake for recent transaction samples before explorer fallback."""
        if not self._snowflake_tx_history_enabled():
            return None

        database = self._get_snowflake_database_for_chain(chain_id)
        if not database:
            logger.debug("Snowflake tx history has no configured database for chain %s", chain_id)
            return None

        address = (contract_address or "").lower()
        normalized_selectors = [selector.lower() for selector in selectors]
        if not _HEX_ADDRESS_RE.match(address):
            logger.warning("Skipping Snowflake tx history for invalid address %r", contract_address)
            return {selector: [] for selector in normalized_selectors}

        valid_selectors = [selector for selector in normalized_selectors if _HEX_SELECTOR_RE.match(selector)]
        if not valid_selectors:
            logger.warning("Skipping Snowflake tx history because no valid selectors were provided")
            return {selector: [] for selector in normalized_selectors}

        limit_per_selector = self._tx_sample_candidate_limit(per_selector)
        logger.info(
            "Trying Snowflake tx history on chain %s via %s.%s.%s",
            chain_id,
            database,
            self._snowflake_schema,
            self._snowflake_transactions_table,
        )

        result = {selector: [] for selector in normalized_selectors}
        pending_selectors = list(valid_selectors)
        for window_days in self._snowflake_query_windows():
            if not pending_selectors:
                break
            query = self._build_snowflake_selector_history_query(
                database=database,
                schema=self._snowflake_schema,
                table=self._snowflake_transactions_table,
                contract_address=address,
                selectors=pending_selectors,
                limit_per_selector=limit_per_selector,
                lookback_days=window_days,
            )
            try:
                logger.info(
                    "Snowflake tx history window: last %s day(s) for %s selector(s) on chain %s",
                    window_days,
                    len(pending_selectors),
                    chain_id,
                )
                rows = self._run_snowflake_query(database, query)
            except Exception as exc:
                logger.warning(
                    "Snowflake tx history query failed for chain %s after %s day window: %s",
                    chain_id,
                    window_days,
                    exc,
                )
                return None

            self._cache_snowflake_transaction_rows(chain_id, rows)
            window_result = self._bucket_snowflake_transactions(
                rows=rows,
                selectors=pending_selectors,
                per_selector=per_selector,
                payable_selectors=payable_selectors,
            )
            result = self._merge_selector_transaction_results(result, window_result, per_selector=per_selector)
            pending_selectors = [
                selector for selector in pending_selectors if len(result.get(selector, [])) < per_selector
            ]

        total_matches = sum(len(txs) for txs in result.values())
        if total_matches:
            logger.info("Snowflake returned %s transaction sample(s) across %s selector(s)", total_matches, len(result))
        else:
            logger.info("Snowflake returned no matching transaction samples for chain %s", chain_id)
        return result

    def _fetch_transactions_from_snowflake_for_addresses(
        self,
        *,
        contract_addresses: list[str],
        selectors: list[str],
        chain_id: int,
        per_selector: int,
        payable_selectors: set | None,
    ) -> dict[str, dict[str, list[dict[str, Any]]]] | None:
        """Query Snowflake once for multiple deployments on the same chain."""
        if not self._snowflake_tx_history_enabled():
            return None

        database = self._get_snowflake_database_for_chain(chain_id)
        if not database:
            logger.debug("Snowflake tx history has no configured database for chain %s", chain_id)
            return None

        normalized_addresses = []
        for contract_address in contract_addresses:
            address = (contract_address or "").lower()
            if not _HEX_ADDRESS_RE.match(address):
                logger.warning("Skipping Snowflake batched tx history for invalid address %r", contract_address)
                continue
            if address not in normalized_addresses:
                normalized_addresses.append(address)

        normalized_selectors = [selector.lower() for selector in selectors]
        valid_selectors = [selector for selector in normalized_selectors if _HEX_SELECTOR_RE.match(selector)]
        if not normalized_addresses:
            return None
        if not valid_selectors:
            logger.warning("Skipping Snowflake batched tx history because no valid selectors were provided")
            return {address: {selector: [] for selector in normalized_selectors} for address in normalized_addresses}

        limit_per_selector = self._tx_sample_candidate_limit(per_selector)
        logger.info(
            "Trying batched Snowflake tx history on chain %s via %s.%s.%s for %s deployment(s)",
            chain_id,
            database,
            self._snowflake_schema,
            self._snowflake_transactions_table,
            len(normalized_addresses),
        )

        result = {address: {selector: [] for selector in normalized_selectors} for address in normalized_addresses}
        pending_selectors = list(valid_selectors)
        for window_days in self._snowflake_query_windows():
            if not pending_selectors:
                break
            query = self._build_snowflake_multi_address_selector_history_query(
                database=database,
                schema=self._snowflake_schema,
                table=self._snowflake_transactions_table,
                contract_addresses=normalized_addresses,
                selectors=pending_selectors,
                limit_per_selector=limit_per_selector,
                lookback_days=window_days,
            )
            try:
                logger.info(
                    "Snowflake tx history window: last %s day(s) for %s selector(s) across %s deployment(s) on chain %s",
                    window_days,
                    len(pending_selectors),
                    len(normalized_addresses),
                    chain_id,
                )
                rows = self._run_snowflake_query(database, query)
            except Exception as exc:
                logger.warning(
                    "Snowflake batched tx history query failed for chain %s after %s day window: %s",
                    chain_id,
                    window_days,
                    exc,
                )
                return None

            self._cache_snowflake_transaction_rows(chain_id, rows)
            window_result = self._bucket_snowflake_transactions_by_address(
                rows=rows,
                contract_addresses=normalized_addresses,
                selectors=pending_selectors,
                per_selector=per_selector,
                payable_selectors=payable_selectors,
            )
            for address, address_result in window_result.items():
                result[address] = self._merge_selector_transaction_results(
                    result.get(address, {}),
                    address_result,
                    per_selector=per_selector,
                )
            pending_selectors = [
                selector
                for selector in pending_selectors
                if any(
                    len(result.get(address, {}).get(selector, [])) < per_selector for address in normalized_addresses
                )
            ]

        total_matches = sum(len(txs) for address_result in result.values() for txs in address_result.values())
        if total_matches:
            logger.info(
                "Snowflake returned %s transaction sample(s) across %s deployment(s)",
                total_matches,
                len(result),
            )
        else:
            logger.info("Snowflake returned no matching transaction samples for chain %s", chain_id)
        return result

    def _build_snowflake_selector_history_query(
        self,
        *,
        database: str,
        schema: str,
        table: str,
        contract_address: str,
        selectors: list[str],
        limit_per_selector: int,
        lookback_days: int,
    ) -> str:
        """Build a selector-sampled Snowflake query against Allium raw transactions."""
        database_sql = self._quote_snowflake_identifier(database)
        schema_sql = self._quote_snowflake_identifier(schema)
        table_sql = self._quote_snowflake_identifier(table)
        selectors_sql = ", ".join(f"'{selector}'" for selector in selectors)
        selector_expr = "LOWER(SUBSTR(input, 1, 10))"
        return f"""
WITH recent_matches AS (
    SELECT
        {selector_expr} AS selector,
        to_address AS contract_address,
        hash,
        block_number,
        block_timestamp,
        transaction_index,
        from_address,
        to_address,
        value AS tx_value,
        input AS input_data,
        gas,
        gas_price,
        receipt_gas_used,
        receipt_status
    FROM {database_sql}.{schema_sql}.{table_sql}
    WHERE to_address = '{contract_address}'
      AND block_timestamp >= DATEADD(day, -{int(lookback_days)}, CURRENT_TIMESTAMP())
      AND (receipt_status = 1 OR receipt_status IS NULL)
      AND input IS NOT NULL
      AND {selector_expr} IN ({selectors_sql})
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY to_address, {selector_expr}
        ORDER BY block_number DESC, transaction_index DESC
    ) <= {int(limit_per_selector)}
)
SELECT
    selector,
    contract_address,
    hash,
    block_number,
    block_timestamp,
    transaction_index,
    from_address,
    to_address,
    tx_value,
    input_data,
    gas,
    gas_price,
    receipt_gas_used,
    receipt_status
FROM recent_matches
ORDER BY block_number DESC, transaction_index DESC
""".strip()

    def _build_snowflake_multi_address_selector_history_query(
        self,
        *,
        database: str,
        schema: str,
        table: str,
        contract_addresses: list[str],
        selectors: list[str],
        limit_per_selector: int,
        lookback_days: int,
    ) -> str:
        """Build one Snowflake query for multiple deployments on the same chain."""
        database_sql = self._quote_snowflake_identifier(database)
        schema_sql = self._quote_snowflake_identifier(schema)
        table_sql = self._quote_snowflake_identifier(table)
        addresses_sql = ", ".join(f"'{address}'" for address in contract_addresses)
        selectors_sql = ", ".join(f"'{selector}'" for selector in selectors)
        selector_expr = "LOWER(SUBSTR(input, 1, 10))"
        return f"""
WITH recent_matches AS (
    SELECT
        {selector_expr} AS selector,
        to_address AS contract_address,
        hash,
        block_number,
        block_timestamp,
        transaction_index,
        from_address,
        to_address,
        value AS tx_value,
        input AS input_data,
        gas,
        gas_price,
        receipt_gas_used,
        receipt_status
    FROM {database_sql}.{schema_sql}.{table_sql}
    WHERE to_address IN ({addresses_sql})
      AND block_timestamp >= DATEADD(day, -{int(lookback_days)}, CURRENT_TIMESTAMP())
      AND (receipt_status = 1 OR receipt_status IS NULL)
      AND input IS NOT NULL
      AND {selector_expr} IN ({selectors_sql})
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY to_address, {selector_expr}
        ORDER BY block_number DESC, transaction_index DESC
    ) <= {int(limit_per_selector)}
)
SELECT
    selector,
    contract_address,
    hash,
    block_number,
    block_timestamp,
    transaction_index,
    from_address,
    to_address,
    tx_value,
    input_data,
    gas,
    gas_price,
    receipt_gas_used,
    receipt_status
FROM recent_matches
ORDER BY block_number DESC, transaction_index DESC
""".strip()

    def _fetch_transaction_receipt_from_snowflake(self, tx_hash: str, chain_id: int) -> dict[str, Any] | None:
        """Load a receipt-like structure from Allium RAW.TRANSACTIONS + RAW.LOGS."""
        chain_id = int(chain_id)
        database = self._get_snowflake_database_for_chain(chain_id)
        if not database:
            return None

        tx_hash = (tx_hash or "").lower()
        if not _HEX_TX_HASH_RE.match(tx_hash):
            return None

        cached_tx_row = self._snowflake_transaction_row_cache.get((chain_id, tx_hash))
        try:
            if cached_tx_row is None:
                tx_query = self._build_snowflake_receipt_transaction_query(
                    database=database,
                    schema=self._snowflake_schema,
                    table=self._snowflake_transactions_table,
                    tx_hash=tx_hash,
                )
                tx_rows = self._run_snowflake_query(database, tx_query)
                if not tx_rows:
                    logger.debug(
                        "Snowflake receipt lookup found no transaction row for %s on chain %s", tx_hash, chain_id
                    )
                    return None
                cached_tx_row = tx_rows[0]
                self._snowflake_transaction_row_cache[(chain_id, tx_hash)] = cached_tx_row

            block_number = int(self._snowflake_row_value(cached_tx_row, "block_number") or 0) or None
            log_query = self._build_snowflake_receipt_logs_query(
                database=database,
                schema=self._snowflake_schema,
                table=self._snowflake_logs_table,
                tx_hash=tx_hash,
                block_number=block_number,
            )
            log_rows = self._run_snowflake_query(database, log_query)
        except Exception as exc:
            logger.warning("Snowflake receipt lookup failed for %s on chain %s: %s", tx_hash, chain_id, exc)
            return None

        tx_row = cached_tx_row
        receipt_status = tx_row.get("RECEIPT_STATUS", tx_row.get("receipt_status"))
        try:
            is_success = receipt_status is None or int(receipt_status) == 1
        except (TypeError, ValueError):
            is_success = str(receipt_status).strip() in {"", "1"}

        receipt = {
            "transactionHash": str(tx_row.get("HASH", tx_row.get("hash")) or tx_hash),
            "blockNumber": hex(int(tx_row.get("BLOCK_NUMBER", tx_row.get("block_number")) or 0)),
            "transactionIndex": hex(int(tx_row.get("TRANSACTION_INDEX", tx_row.get("transaction_index")) or 0)),
            "from": str(tx_row.get("FROM_ADDRESS", tx_row.get("from_address")) or ""),
            "to": str(tx_row.get("TO_ADDRESS", tx_row.get("to_address")) or ""),
            "gasUsed": hex(int(tx_row.get("RECEIPT_GAS_USED", tx_row.get("receipt_gas_used")) or 0)),
            "status": "0x1" if is_success else "0x0",
            "logs": [
                {
                    "address": str(log.get("ADDRESS", log.get("address")) or ""),
                    "topics": [
                        topic
                        for topic in [
                            str(log.get("TOPIC0", log.get("topic0")) or ""),
                            str(log.get("TOPIC1", log.get("topic1")) or ""),
                            str(log.get("TOPIC2", log.get("topic2")) or ""),
                            str(log.get("TOPIC3", log.get("topic3")) or ""),
                        ]
                        if topic
                    ],
                    "data": str(log.get("DATA", log.get("data")) or "0x"),
                    "logIndex": hex(int(log.get("LOG_INDEX", log.get("log_index")) or 0)),
                }
                for log in log_rows
            ],
        }
        logger.debug("Loaded receipt for %s from Snowflake with %d log(s)", tx_hash, len(receipt.get("logs", [])))
        return receipt

    def _build_snowflake_receipt_transaction_query(
        self,
        *,
        database: str,
        schema: str,
        table: str,
        tx_hash: str,
    ) -> str:
        """Build the exact-hash transaction lookup query for receipt reconstruction."""
        database_sql = self._quote_snowflake_identifier(database)
        schema_sql = self._quote_snowflake_identifier(schema)
        table_sql = self._quote_snowflake_identifier(table)
        return f"""
SELECT
    hash,
    block_number,
    transaction_index,
    from_address,
    to_address,
    receipt_gas_used,
    receipt_status
FROM {database_sql}.{schema_sql}.{table_sql}
WHERE hash = '{tx_hash}'
  AND block_timestamp >= DATEADD(day, -{int(self.lookback_days)}, CURRENT_TIMESTAMP())
LIMIT 1
""".strip()

    def _build_snowflake_receipt_logs_query(
        self,
        *,
        database: str,
        schema: str,
        table: str,
        tx_hash: str,
        block_number: int | None = None,
    ) -> str:
        """Build the exact-hash logs lookup query for receipt reconstruction."""
        database_sql = self._quote_snowflake_identifier(database)
        schema_sql = self._quote_snowflake_identifier(schema)
        table_sql = self._quote_snowflake_identifier(table)
        block_filter = f"\n  AND block_number = {int(block_number)}" if block_number is not None else ""
        return f"""
SELECT
    log_index,
    address,
    data,
    topic0,
    topic1,
    topic2,
    topic3
FROM {database_sql}.{schema_sql}.{table_sql}
WHERE transaction_hash = '{tx_hash}'
{block_filter}
ORDER BY log_index ASC
""".strip()

    def _run_snowflake_query(self, database: str, query: str) -> list[dict[str, Any]]:
        """Execute one query, reusing a cached connection when possible."""
        return self._run_snowflake_queries(database, [query])[0]

    def _run_snowflake_queries(self, database: str, queries: list[str]) -> list[list[dict[str, Any]]]:
        """Execute multiple queries on a single (cached) Snowflake connection."""
        connection = self._get_or_open_snowflake_connection(database)
        try:
            results: list[list[dict[str, Any]]] = []
            with connection.cursor() as cursor:
                for query in queries:
                    cursor.execute(query)
                    columns = [getattr(column, "name", column[0]) for column in cursor.description or []]
                    results.append([dict(zip(columns, row, strict=False)) for row in cursor.fetchall()])
            return results
        except Exception:
            self._discard_snowflake_connection(database)
            raise

    # ---- connection pool (one connection per database) ----

    def _get_or_open_snowflake_connection(self, database: str) -> Any:
        """Return a cached connection or open a new one."""
        import time as _time

        cache: dict[str, Any] = getattr(self, "_snowflake_conn_cache", None) or {}
        self._snowflake_conn_cache = cache

        db_key = database.upper()
        conn = cache.get(db_key)
        if conn is not None:
            try:
                if not conn.is_closed():
                    return conn
            except Exception:
                pass
            cache.pop(db_key, None)

        t0 = _time.monotonic()
        conn = self._open_snowflake_connection(database)
        elapsed = _time.monotonic() - t0
        logger.info("Snowflake connection opened for %s in %.1fs", db_key, elapsed)
        cache[db_key] = conn
        return conn

    def _discard_snowflake_connection(self, database: str) -> None:
        """Close and remove a cached connection (on error)."""
        cache: dict[str, Any] = getattr(self, "_snowflake_conn_cache", None) or {}
        db_key = database.upper()
        conn = cache.pop(db_key, None)
        if conn is not None:
            with suppress(Exception):
                conn.close()

    def close_snowflake_connections(self) -> None:
        """Close all cached Snowflake connections (call at end of analysis)."""
        cache: dict[str, Any] = getattr(self, "_snowflake_conn_cache", None) or {}
        for db_key, conn in list(cache.items()):
            try:
                conn.close()
                logger.debug("Closed Snowflake connection for %s", db_key)
            except Exception:
                pass
        cache.clear()

    def _open_snowflake_connection(self, database: str) -> Any:
        """Build and open a Snowflake connection for the requested database."""
        import snowflake.connector
        from cryptography.hazmat.primitives import serialization

        connect_kwargs: dict[str, Any] = {
            "account": self._snowflake_account,
            "user": self._snowflake_user,
            "database": database.upper(),
            "role": self._snowflake_role,
            "warehouse": self._snowflake_warehouse,
            "client_session_keep_alive": True,
            "session_parameters": {
                "QUERY_TAG": "erc7730-analyzer tx history",
            },
        }
        if self._snowflake_login_timeout is not None:
            connect_kwargs["login_timeout"] = self._snowflake_login_timeout
        if self._snowflake_network_timeout is not None:
            connect_kwargs["network_timeout"] = self._snowflake_network_timeout
        if self._snowflake_socket_timeout is not None:
            connect_kwargs["socket_timeout"] = self._snowflake_socket_timeout

        private_key_content = self._normalize_multiline_secret(self._snowflake_private_key)
        private_key_password = self._normalize_multiline_secret(self._snowflake_private_key_password)
        if private_key_content:
            private_key = self._load_snowflake_private_key(
                serialization=serialization,
                private_key_content=private_key_content,
                private_key_password=private_key_password,
            )
            connect_kwargs["authenticator"] = "snowflake"
            connect_kwargs["private_key"] = private_key
        else:
            connect_kwargs["authenticator"] = "externalbrowser"
        return snowflake.connector.connect(**connect_kwargs)

    def _load_snowflake_private_key(
        self,
        *,
        serialization: Any,
        private_key_content: str,
        private_key_password: str | None,
    ) -> bytes:
        """Load a PEM or base64-encoded DER private key into DER PKCS8 bytes."""
        password_bytes = private_key_password.encode() if private_key_password else None
        key_bytes = private_key_content.encode()

        try:
            if "BEGIN OPENSSH PRIVATE KEY" in private_key_content:
                private_key_obj = serialization.load_ssh_private_key(key_bytes, password=password_bytes)
            else:
                private_key_obj = serialization.load_pem_private_key(key_bytes, password=password_bytes)
        except TypeError as exc:
            raise ValueError("Snowflake private key appears encrypted but no valid passphrase was provided") from exc
        except ValueError:
            try:
                decoded = base64.b64decode(private_key_content)
            except (ValueError, binascii.Error) as exc:
                raise ValueError("Snowflake private key is not valid PEM or base64 DER data") from exc
            private_key_obj = serialization.load_der_private_key(decoded, password=password_bytes)

        return private_key_obj.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

    def _bucket_snowflake_transactions(
        self,
        *,
        rows: list[dict[str, Any]],
        selectors: list[str],
        per_selector: int,
        payable_selectors: set | None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Apply the same selector bucketing strategy used by explorer fetches."""
        selectors = [selector.lower() for selector in selectors]
        selector_candidates = {selector: [] for selector in selectors}

        if payable_selectors is None:
            payable_selectors = set()
        else:
            payable_selectors = {selector.lower() for selector in payable_selectors}
        payable_selectors = {selector for selector in payable_selectors if selector in selector_candidates}

        total_rows = 0
        for row in rows:
            tx = self._convert_snowflake_row_to_etherscan_format(row)
            if tx.get("isError") != "0":
                continue

            tx_selector = (tx.get("input", "")[:10] or "").lower()
            if tx_selector not in selector_candidates:
                continue

            total_rows += 1
            selector_candidates[tx_selector].append(tx)

        selector_txs = self._finalize_selector_transaction_samples(
            selector_candidates,
            per_selector=per_selector,
            payable_selectors=payable_selectors,
        )

        logger.info("Scanned %s Snowflake transaction row(s)", total_rows)
        for selector, tx_list in selector_txs.items():
            if selector in payable_selectors:
                native_count = sum(1 for tx in tx_list if int(tx.get("value", "0")) > 0)
                erc20_count = len(tx_list) - native_count
                logger.info(
                    "Selector %s (payable): found %s/%s transactions (%s native ETH, %s ERC20)",
                    selector,
                    len(tx_list),
                    per_selector,
                    native_count,
                    erc20_count,
                )
            else:
                logger.info("Selector %s: found %s/%s transactions", selector, len(tx_list), per_selector)
        return selector_txs

    def _bucket_snowflake_transactions_by_address(
        self,
        *,
        rows: list[dict[str, Any]],
        contract_addresses: list[str],
        selectors: list[str],
        per_selector: int,
        payable_selectors: set | None,
    ) -> dict[str, dict[str, list[dict[str, Any]]]]:
        """Bucket Snowflake rows first by deployment address, then by selector."""
        normalized_addresses = [address.lower() for address in contract_addresses]
        rows_by_address = {address: [] for address in normalized_addresses}
        for row in rows:
            address = str(self._snowflake_row_value(row, "contract_address", "to_address") or "").lower()
            if address in rows_by_address:
                rows_by_address[address].append(row)

        return {
            address: self._bucket_snowflake_transactions(
                rows=rows_by_address.get(address, []),
                selectors=selectors,
                per_selector=per_selector,
                payable_selectors=payable_selectors,
            )
            for address in normalized_addresses
        }

    def _convert_snowflake_row_to_etherscan_format(self, row: dict[str, Any]) -> dict[str, str]:
        """Normalize a Snowflake raw transaction row into the explorer-like structure used downstream."""
        receipt_status = self._snowflake_row_value(row, "receipt_status")
        try:
            is_success = receipt_status is None or int(receipt_status) == 1
        except (TypeError, ValueError):
            is_success = str(receipt_status).strip() in {"", "1"}

        return {
            "hash": str(self._snowflake_row_value(row, "hash") or ""),
            "blockNumber": str(int(self._snowflake_row_value(row, "block_number") or 0)),
            "timeStamp": str(self._snowflake_timestamp_to_unix(self._snowflake_row_value(row, "block_timestamp"))),
            "transactionIndex": str(int(self._snowflake_row_value(row, "transaction_index") or 0)),
            "from": str(self._snowflake_row_value(row, "from_address") or ""),
            "to": str(self._snowflake_row_value(row, "to_address") or ""),
            "value": str(int(self._snowflake_row_value(row, "tx_value") or 0)),
            "input": str(self._snowflake_row_value(row, "input_data") or "0x"),
            "gas": str(int(self._snowflake_row_value(row, "gas") or 0)),
            "gasPrice": str(int(self._snowflake_row_value(row, "gas_price") or 0)),
            "gasUsed": str(int(self._snowflake_row_value(row, "receipt_gas_used") or 0)),
            "isError": "0" if is_success else "1",
            "txreceipt_status": "1" if is_success else "0",
            "source": "snowflake",
        }

    def _cache_snowflake_transaction_rows(self, chain_id: int, rows: list[dict[str, Any]]) -> None:
        """Remember Snowflake transaction rows so later receipt lookups can reuse block metadata."""
        chain_id = int(chain_id)
        for row in rows:
            tx_hash = str(self._snowflake_row_value(row, "hash") or "").lower()
            if _HEX_TX_HASH_RE.match(tx_hash):
                self._snowflake_transaction_row_cache[(chain_id, tx_hash)] = row

    def _snowflake_query_windows(self) -> list[int]:
        """Try only the one-month Snowflake window."""
        windows = [30]
        return list(dict.fromkeys(windows))

    def _merge_selector_transaction_results(
        self,
        base: dict[str, list[dict[str, Any]]],
        extra: dict[str, list[dict[str, Any]]],
        *,
        per_selector: int,
    ) -> dict[str, list[dict[str, Any]]]:
        """Merge Snowflake selector batches while keeping order and removing duplicates."""
        merged: dict[str, list[dict[str, Any]]] = {selector: list(txs) for selector, txs in base.items()}
        for selector, txs in extra.items():
            existing = merged.setdefault(selector, [])
            seen = {str(tx.get("hash") or "").lower() for tx in existing}
            for tx in txs:
                tx_hash = str(tx.get("hash") or "").lower()
                if tx_hash and tx_hash in seen:
                    continue
                if tx_hash:
                    seen.add(tx_hash)
                existing.append(tx)
                if len(existing) >= per_selector:
                    break
        return merged

    def _snowflake_timestamp_to_unix(self, value: Any) -> int:
        """Convert a Snowflake timestamp value into a Unix timestamp."""
        if value is None:
            return 0
        if isinstance(value, datetime):
            dt = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
            return int(dt.timestamp())
        if isinstance(value, (int, float)):
            return int(value)

        text = str(value).strip()
        if not text:
            return 0
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return 0
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return int(parsed.timestamp())

    def _quote_snowflake_identifier(self, value: str) -> str:
        """Validate and quote a Snowflake identifier to prevent malformed dynamic SQL."""
        if not _SNOWFLAKE_IDENTIFIER_RE.match(value):
            raise ValueError(f"Unsafe Snowflake identifier: {value!r}")
        return value
