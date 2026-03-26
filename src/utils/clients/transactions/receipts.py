"""Receipt/log decoding and token metadata helpers."""

import logging
import time
from typing import Any

import requests

from ...rpc_helpers import (
    etherscan_response_indicates_chain_unsupported,
    is_etherscan_tx_endpoint_unsupported,
    mark_etherscan_tx_endpoint_unsupported,
    rpc_eth_call,
    rpc_get_transaction_receipt,
)
from .constants import BLOCKSCOUT_URLS

logger = logging.getLogger(__name__)


class TransactionFetcherReceiptMixin:
    def fetch_transaction_receipt(self, tx_hash: str, chain_id: int = 1) -> dict[str, Any] | None:
        """
        Fetch transaction receipt from Etherscan or Blockscout.

        Args:
            tx_hash: Transaction hash
            chain_id: Chain ID for the transaction

        Returns:
            Transaction receipt or None if error
        """
        chain_id = int(chain_id)  # Ensure it's an int
        t0 = time.monotonic()

        if self._snowflake_chain_available(chain_id):
            snowflake_receipt = self._fetch_transaction_receipt_from_snowflake(tx_hash, chain_id)
            if snowflake_receipt:
                logger.info("Fetched receipt for %s from Snowflake in %.1fs", tx_hash, time.monotonic() - t0)
                return snowflake_receipt

        has_blockscout = chain_id in BLOCKSCOUT_URLS and chain_id != 1116
        can_use_etherscan = chain_id == 1116 or bool(self.etherscan_api_key)
        skip_etherscan = chain_id != 1116 and is_etherscan_tx_endpoint_unsupported(chain_id)
        if not can_use_etherscan and not has_blockscout:
            logger.warning("No supported receipt source configured for chain %s", chain_id)
            return None

        preferred_api = self.api_type_per_chain.get(chain_id)
        attempts: list[str] = []
        if preferred_api in {"Blockscout", "Snowflake"} and has_blockscout:
            attempts.append("blockscout")
        elif can_use_etherscan and not skip_etherscan:
            attempts.append("etherscan")

        if has_blockscout and "blockscout" not in attempts:
            attempts.append("blockscout")
        if can_use_etherscan and not skip_etherscan and "etherscan" not in attempts:
            attempts.append("etherscan")

        for attempt in attempts:
            if attempt == "blockscout":
                try:
                    base_url = BLOCKSCOUT_URLS[chain_id]
                    url = f"{base_url}/api/v2/transactions/{tx_hash}"
                    response = requests.get(url, timeout=10)
                    response.raise_for_status()
                    data = response.json()

                    if data:
                        receipt = {
                            "transactionHash": data.get("hash", ""),
                            "blockNumber": hex(data.get("block", 0)),
                            "from": data.get("from", {}).get("hash", ""),
                            "to": data.get("to", {}).get("hash", "") if data.get("to") else "",
                            "gasUsed": hex(int(data.get("gas_used", "0"))),
                            "status": "0x1" if data.get("status") == "ok" else "0x0",
                            "logs": [],
                        }

                        if "logs" in data:
                            for log in data["logs"]:
                                receipt["logs"].append(
                                    {
                                        "address": log.get("address", {}).get("hash", "")
                                        if isinstance(log.get("address"), dict)
                                        else log.get("address", ""),
                                        "topics": log.get("topics", []),
                                        "data": log.get("data", "0x"),
                                    }
                                )

                        logger.info("Fetched receipt for %s from Blockscout in %.1fs", tx_hash, time.monotonic() - t0)
                        return receipt
                except Exception as exc:
                    logger.warning("Blockscout receipt lookup failed for %s on chain %s: %s", tx_hash, chain_id, exc)
                continue

            params = {
                "module": "proxy",
                "action": "eth_getTransactionReceipt",
                "txhash": tx_hash,
            }

            if chain_id == 1116:
                import os

                from dotenv import load_dotenv

                load_dotenv(override=True)
                coredao_api_key = os.getenv("COREDAO_API_KEY", "")
                if coredao_api_key:
                    params["apikey"] = coredao_api_key
            elif self.etherscan_api_key:
                params["apikey"] = self.etherscan_api_key
            else:
                continue

            try:
                base_url = self._get_api_base_url(chain_id, False)
                response = requests.get(base_url, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()

                if chain_id != 1116 and etherscan_response_indicates_chain_unsupported(data):
                    mark_etherscan_tx_endpoint_unsupported(chain_id)
                    logger.info(
                        "Etherscan receipt lookup unsupported on chain %s; falling back to alternate explorer if available",
                        chain_id,
                    )
                    continue

                if data.get("result"):
                    result = data["result"]
                    if isinstance(result, dict):
                        logger.info("Fetched receipt for %s from Etherscan in %.1fs", tx_hash, time.monotonic() - t0)
                        return result
                    logger.warning("Etherscan returned non-dict receipt for %s: %r", tx_hash, result)
                else:
                    logger.warning("No receipt found for %s via Etherscan-style API", tx_hash)
            except Exception as exc:
                logger.warning("Etherscan-style receipt lookup failed for %s on chain %s: %s", tx_hash, chain_id, exc)

        # Final fallback: direct JSON-RPC via public/configured RPC endpoint
        receipt, rpc_error, rpc_url = rpc_get_transaction_receipt(chain_id, tx_hash, timeout=15)
        if receipt:
            logger.info(
                "Fetched receipt for %s via RPC fallback (%s) in %.1fs", tx_hash, rpc_url, time.monotonic() - t0
            )
            return receipt
        if rpc_error:
            logger.debug("RPC receipt fallback failed for %s: %s", tx_hash, rpc_error)

        return None

    def decode_log_event(self, log: dict[str, Any], chain_id: int = 1) -> dict[str, Any] | None:
        """
        Decode a log event, with special handling for common token events.

        Args:
            log: Log entry from transaction receipt
            chain_id: Chain ID for RPC calls

        Returns:
            Decoded event data or None
        """
        try:
            topics = log.get("topics", [])
            if not topics:
                return None

            event_signature = topics[0]

            # ERC-20 Transfer event
            if event_signature == "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef":
                if len(topics) >= 3:
                    from_address = "0x" + topics[1][-40:]
                    to_address = "0x" + topics[2][-40:]
                    value_hex = log.get("data", "0x0")
                    value = int(value_hex, 16) if value_hex != "0x" else 0

                    return {
                        "event": "Transfer",
                        "token": log.get("address", "unknown"),
                        "from": from_address,
                        "to": to_address,
                        "value": str(value),
                        "value_formatted": self.format_token_amount(value, log.get("address"), chain_id),
                    }

            # ERC-20 Approval event
            elif (
                event_signature == "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925"
                and len(topics) >= 3
            ):
                owner = "0x" + topics[1][-40:]
                spender = "0x" + topics[2][-40:]
                value_hex = log.get("data", "0x0")
                value = int(value_hex, 16) if value_hex != "0x" else 0

                return {
                    "event": "Approval",
                    "token": log.get("address", "unknown"),
                    "owner": owner,
                    "spender": spender,
                    "value": str(value),
                    "value_formatted": self.format_token_amount(value, log.get("address"), chain_id),
                }

            # For other events, return basic info
            return {
                "event": "Unknown",
                "signature": event_signature,
                "address": log.get("address", "unknown"),
                "topics": topics,
                "data": log.get("data", "0x"),
            }

        except Exception as e:
            logger.warning(f"Failed to decode log event: {e}")
            return None

    def _decode_string_result(self, result_hex: str) -> str | None:
        """Decode an ABI-encoded string return value (dynamic or bytes32)."""
        result_hex = result_hex[2:] if result_hex.startswith("0x") else result_hex
        if not result_hex:
            return None
        try:
            if len(result_hex) > 128:
                length = int(result_hex[64:128], 16)
                symbol_hex = result_hex[128 : 128 + length * 2]
            else:
                symbol_hex = result_hex
            return bytes.fromhex(symbol_hex).decode("utf-8").rstrip("\x00") or None
        except Exception:
            return None

    def get_token_symbol(self, token_address: str, chain_id: int = 1) -> str | None:
        """
        Fetch token symbol from the contract, trying Etherscan then direct RPC.

        Args:
            token_address: Token contract address
            chain_id: Chain ID for the token

        Returns:
            Token symbol or None if unable to fetch
        """
        cache_key = f"{chain_id}:{token_address.lower()}"
        if cache_key in self.token_symbol_cache:
            return self.token_symbol_cache[cache_key]

        call_data = "0x95d89b41"

        if self.etherscan_api_key:
            try:
                params = {
                    "module": "proxy",
                    "action": "eth_call",
                    "to": token_address,
                    "data": call_data,
                    "tag": "latest",
                    "apikey": self.etherscan_api_key,
                }
                base_url = f"https://api.etherscan.io/v2/api?chainid={chain_id}"
                response = requests.get(base_url, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                if data.get("result") and data["result"] != "0x":
                    symbol = self._decode_string_result(data["result"])
                    if symbol:
                        self.token_symbol_cache[cache_key] = symbol
                        logger.debug("Fetched symbol for %s: %s (Etherscan)", token_address, symbol)
                        time.sleep(0.1)
                        return symbol
            except Exception as e:
                logger.debug("Etherscan symbol fetch failed for %s: %s", token_address, e)

        result_hex, rpc_err, _ = rpc_eth_call(chain_id, token_address, call_data, timeout=10)
        if result_hex and result_hex != "0x":
            symbol = self._decode_string_result(result_hex)
            if symbol:
                self.token_symbol_cache[cache_key] = symbol
                logger.debug("Fetched symbol for %s: %s (RPC fallback)", token_address, symbol)
                return symbol
        if rpc_err:
            logger.debug("RPC symbol fallback failed for %s: %s", token_address, rpc_err)

        return None

    def get_token_decimals(self, token_address: str, chain_id: int = 1) -> int | None:
        """
        Fetch token decimals from the contract, trying Etherscan then direct RPC.

        Args:
            token_address: Token contract address
            chain_id: Chain ID for the token

        Returns:
            Number of decimals or None if unable to fetch
        """
        cache_key = f"{chain_id}:{token_address.lower()}"
        if cache_key in self.token_decimals_cache:
            return self.token_decimals_cache[cache_key]

        call_data = "0x313ce567"

        if self.etherscan_api_key:
            try:
                params = {
                    "module": "proxy",
                    "action": "eth_call",
                    "to": token_address,
                    "data": call_data,
                    "tag": "latest",
                    "apikey": self.etherscan_api_key,
                }
                base_url = f"https://api.etherscan.io/v2/api?chainid={chain_id}"
                response = requests.get(base_url, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                if data.get("result") and data["result"] != "0x":
                    decimals = int(data["result"], 16)
                    self.token_decimals_cache[cache_key] = decimals
                    logger.debug("Fetched decimals for %s: %s (Etherscan)", token_address, decimals)
                    time.sleep(0.1)
                    return decimals
            except Exception as e:
                logger.debug("Etherscan decimals fetch failed for %s: %s", token_address, e)

        result_hex, rpc_err, _ = rpc_eth_call(chain_id, token_address, call_data, timeout=10)
        if result_hex and result_hex != "0x":
            try:
                decimals = int(result_hex, 16)
                self.token_decimals_cache[cache_key] = decimals
                logger.debug("Fetched decimals for %s: %s (RPC fallback)", token_address, decimals)
                return decimals
            except ValueError:
                logger.debug("Failed to parse RPC decimals result for %s: %s", token_address, result_hex)
        if rpc_err:
            logger.debug("RPC decimals fallback failed for %s: %s", token_address, rpc_err)

        return None

    def format_token_amount(self, value: int, token_address: str, chain_id: int = 1) -> str:
        """
        Format token amount using actual decimals and symbol from contract.

        Args:
            value: Raw token amount
            token_address: Token contract address
            chain_id: Chain ID for the token

        Returns:
            Formatted token amount string
        """
        token_short = token_address[:10] + "..." if len(token_address) > 10 else token_address

        symbol = self.get_token_symbol(token_address, chain_id)
        decimals = self.get_token_decimals(token_address, chain_id)

        if decimals is not None:
            formatted = value / (10**decimals)
            amount_str = f"{formatted:.6f}".rstrip("0").rstrip(".")

            if symbol:
                return f"{amount_str} {symbol}"
            else:
                return f"{amount_str} ({token_short})"
        else:
            if symbol:
                return f"{value} (raw) {symbol}"
            else:
                return f"{value} (raw, {token_short})"
