"""Reconstruct raw signed transactions from explorer or RPC transaction fields."""

import asyncio
import logging
import time
from typing import Any

import requests
import rlp

from ..rpc_helpers import (
    etherscan_response_indicates_chain_unsupported,
    is_etherscan_tx_endpoint_unsupported,
    mark_etherscan_tx_endpoint_unsupported,
    rpc_get_transaction_by_hash,
)

logger = logging.getLogger(__name__)

RAW_TX_MAX_RETRIES = 3
RAW_TX_RETRY_DELAY = 1.5


def _int_to_bytes(val: int) -> bytes:
    if val == 0:
        return b""
    return val.to_bytes((val.bit_length() + 7) // 8, "big")


def _hex_to_int(hex_str: str) -> int:
    return int(hex_str, 16)


def _encode_access_list(access_list: list) -> list:
    """RLP-encode an EIP-2930 access list."""
    encoded = []
    for entry in access_list:
        address = bytes.fromhex(entry["address"][2:])
        keys = [bytes.fromhex(k[2:]) for k in entry.get("storageKeys", [])]
        encoded.append([address, keys])
    return encoded


def _rlp_encode_type2(tx: dict[str, Any]) -> str:
    """EIP-1559 (type 2) → 0x02 || rlp([chainId, nonce, maxPriorityFee, maxFee, gas, to, value, data, accessList, v, r, s])."""
    payload = rlp.encode(
        [
            _int_to_bytes(_hex_to_int(tx["chainId"])),
            _int_to_bytes(_hex_to_int(tx["nonce"])),
            _int_to_bytes(_hex_to_int(tx["maxPriorityFeePerGas"])),
            _int_to_bytes(_hex_to_int(tx["maxFeePerGas"])),
            _int_to_bytes(_hex_to_int(tx["gas"])),
            bytes.fromhex(tx["to"][2:]),
            _int_to_bytes(_hex_to_int(tx["value"])),
            bytes.fromhex(tx["input"][2:]),
            _encode_access_list(tx.get("accessList", [])),
            _int_to_bytes(_hex_to_int(tx.get("yParity", tx.get("v", "0x0")))),
            _int_to_bytes(_hex_to_int(tx["r"])),
            _int_to_bytes(_hex_to_int(tx["s"])),
        ]
    )
    return "0x02" + payload.hex()


def _rlp_encode_type1(tx: dict[str, Any]) -> str:
    """EIP-2930 (type 1) → 0x01 || rlp([chainId, nonce, gasPrice, gas, to, value, data, accessList, v, r, s])."""
    payload = rlp.encode(
        [
            _int_to_bytes(_hex_to_int(tx["chainId"])),
            _int_to_bytes(_hex_to_int(tx["nonce"])),
            _int_to_bytes(_hex_to_int(tx["gasPrice"])),
            _int_to_bytes(_hex_to_int(tx["gas"])),
            bytes.fromhex(tx["to"][2:]),
            _int_to_bytes(_hex_to_int(tx["value"])),
            bytes.fromhex(tx["input"][2:]),
            _encode_access_list(tx.get("accessList", [])),
            _int_to_bytes(_hex_to_int(tx["v"])),
            _int_to_bytes(_hex_to_int(tx["r"])),
            _int_to_bytes(_hex_to_int(tx["s"])),
        ]
    )
    return "0x01" + payload.hex()


def _rlp_encode_legacy(tx: dict[str, Any]) -> str:
    """Legacy (type 0) → rlp([nonce, gasPrice, gas, to, value, data, v, r, s])."""
    payload = rlp.encode(
        [
            _int_to_bytes(_hex_to_int(tx["nonce"])),
            _int_to_bytes(_hex_to_int(tx["gasPrice"])),
            _int_to_bytes(_hex_to_int(tx["gas"])),
            bytes.fromhex(tx["to"][2:]),
            _int_to_bytes(_hex_to_int(tx["value"])),
            bytes.fromhex(tx["input"][2:]),
            _int_to_bytes(_hex_to_int(tx["v"])),
            _int_to_bytes(_hex_to_int(tx["r"])),
            _int_to_bytes(_hex_to_int(tx["s"])),
        ]
    )
    return "0x" + payload.hex()


def reconstruct_raw_transaction(tx_fields: dict[str, Any]) -> str:
    """
    RLP-encode a signed transaction from its JSON-RPC fields.

    Supports legacy (type 0), EIP-2930 (type 1), and EIP-1559 (type 2).

    Args:
        tx_fields: Transaction object from eth_getTransactionByHash.

    Returns:
        Hex-encoded raw signed transaction string.
    """
    tx_type = _hex_to_int(tx_fields.get("type", "0x0"))

    if tx_type == 2:
        return _rlp_encode_type2(tx_fields)
    elif tx_type == 1:
        return _rlp_encode_type1(tx_fields)
    else:
        return _rlp_encode_legacy(tx_fields)


def _fetch_tx_fields(
    tx_hash: str,
    chain_id: int,
    etherscan_api_key: str,
) -> dict[str, Any] | None:
    """Fetch transaction fields with explorer-first behavior and RPC fallback."""
    use_explorer = bool(etherscan_api_key) and not is_etherscan_tx_endpoint_unsupported(chain_id)
    if use_explorer:
        url = f"https://api.etherscan.io/v2/api?chainid={chain_id}"
        params = {
            "module": "proxy",
            "action": "eth_getTransactionByHash",
            "txhash": tx_hash,
            "apikey": etherscan_api_key,
        }

        for attempt in range(RAW_TX_MAX_RETRIES):
            try:
                resp = requests.get(url, params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json()
                result = data.get("result")
                if result and isinstance(result, dict):
                    return result

                if etherscan_response_indicates_chain_unsupported(data):
                    mark_etherscan_tx_endpoint_unsupported(chain_id)
                    logger.info(
                        "[RAW_TX] Etherscan tx endpoints unsupported on chain %d, falling back to direct RPC",
                        chain_id,
                    )
                    break

                if attempt < RAW_TX_MAX_RETRIES - 1:
                    logger.debug(
                        "[RAW_TX] Attempt %d/%d returned null for %s on chain %d, retrying...",
                        attempt + 1,
                        RAW_TX_MAX_RETRIES,
                        tx_hash,
                        chain_id,
                    )
                    time.sleep(RAW_TX_RETRY_DELAY * (attempt + 1))
                else:
                    logger.warning(
                        "[RAW_TX] eth_getTransactionByHash returned no result for %s on chain %d after %d attempts",
                        tx_hash,
                        chain_id,
                        RAW_TX_MAX_RETRIES,
                    )
            except Exception as exc:
                if attempt < RAW_TX_MAX_RETRIES - 1:
                    logger.debug("[RAW_TX] Attempt %d failed for %s: %s", attempt + 1, tx_hash, exc)
                    time.sleep(RAW_TX_RETRY_DELAY * (attempt + 1))
                else:
                    logger.warning(
                        "[RAW_TX] Failed to fetch tx %s after %d attempts: %s",
                        tx_hash,
                        RAW_TX_MAX_RETRIES,
                        exc,
                    )
    elif not etherscan_api_key:
        logger.debug("[RAW_TX] No explorer API key for %s on chain %d, using direct RPC fallback", tx_hash, chain_id)
    else:
        logger.debug(
            "[RAW_TX] Skipping explorer tx lookup for %s on chain %d: endpoint already marked unsupported",
            tx_hash,
            chain_id,
        )

    for attempt in range(RAW_TX_MAX_RETRIES):
        result, error_msg, rpc_url = rpc_get_transaction_by_hash(chain_id, tx_hash, timeout=15)
        if result:
            logger.info("[RAW_TX] Loaded tx %s via RPC fallback %s", tx_hash, rpc_url)
            return result
        if attempt < RAW_TX_MAX_RETRIES - 1:
            logger.debug(
                "[RAW_TX] RPC attempt %d/%d returned %s for %s on chain %d, retrying...",
                attempt + 1,
                RAW_TX_MAX_RETRIES,
                error_msg or "no result",
                tx_hash,
                chain_id,
            )
            time.sleep(RAW_TX_RETRY_DELAY * (attempt + 1))
        else:
            logger.warning(
                "[RAW_TX] RPC fallback failed for %s on chain %d after %d attempts: %s",
                tx_hash,
                chain_id,
                RAW_TX_MAX_RETRIES,
                error_msg or "no result",
            )
    return None


def fetch_raw_transaction(
    tx_hash: str,
    chain_id: int,
    etherscan_api_key: str,
) -> str | None:
    """
    Fetch a transaction by hash and return its raw RLP-encoded form.

    Args:
        tx_hash: Transaction hash (0x-prefixed).
        chain_id: Chain ID.
        etherscan_api_key: Explorer API key, used before RPC fallback when supported.

    Returns:
        Raw signed transaction hex string, or None on failure.
    """
    result = _fetch_tx_fields(tx_hash, chain_id, etherscan_api_key)
    if not result:
        return None

    try:
        raw_tx = reconstruct_raw_transaction(result)
        logger.info(
            "[RAW_TX] Reconstructed raw tx for %s (%d bytes)",
            tx_hash,
            len(raw_tx) // 2,
        )
        return raw_tx
    except Exception as exc:
        logger.warning("[RAW_TX] Failed to RLP-encode tx %s: %s", tx_hash, exc)
        return None


async def fetch_raw_transaction_async(
    tx_hash: str,
    chain_id: int,
    etherscan_api_key: str,
) -> str | None:
    """Async wrapper — offloads blocking HTTP + RLP to a thread."""
    return await asyncio.to_thread(fetch_raw_transaction, tx_hash, chain_id, etherscan_api_key)
