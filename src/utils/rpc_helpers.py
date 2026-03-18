"""Lightweight RPC endpoint helpers used outside agentic tools."""

from __future__ import annotations

import os
from typing import Any

import requests

DEFAULT_RPC_URLS = {
    1: "https://eth.llamarpc.com",
    10: "https://mainnet.optimism.io",
    14: "https://flare-api.flare.network/ext/C/rpc",
    19: "https://songbird-api.flare.network/ext/C/rpc",
    56: "https://bsc-dataseed.binance.org",
    100: "https://rpc.gnosischain.com",
    137: "https://polygon-rpc.com",
    8453: "https://mainnet.base.org",
    1116: "https://rpc.coredao.org",
}

ETHERSCAN_CHAIN_COVERAGE_ERROR = "Free API access is not supported for this chain"
_ETHERSCAN_PROXY_ETH_CALL_UNSUPPORTED_CHAINS: set[int] = set()
_ETHERSCAN_TX_ENDPOINT_UNSUPPORTED_CHAINS: set[int] = set()


def resolve_rpc_url(chain_id: int) -> str | None:
    """Resolve the best RPC URL for a chain, preferring env overrides."""
    candidates = [
        os.getenv(f"RPC_URL_{chain_id}"),
        os.getenv(f"CHAIN_RPC_URL_{chain_id}"),
        os.getenv("RPC_URL") if chain_id == 1 else None,
        os.getenv("ETH_RPC_URL") if chain_id == 1 else None,
        DEFAULT_RPC_URLS.get(chain_id),
    ]
    for candidate in candidates:
        if candidate:
            return candidate
    return None


def etherscan_response_indicates_chain_unsupported(payload: object) -> bool:
    """Return True when an explorer response indicates free-tier chain coverage is unavailable."""
    if isinstance(payload, dict):
        parts: list[str] = []
        for key in ("message", "result"):
            value = payload.get(key)
            if value:
                parts.append(str(value))
        error = payload.get("error")
        if isinstance(error, dict) and error.get("message"):
            parts.append(str(error["message"]))
        elif error:
            parts.append(str(error))
        haystack = " ".join(parts)
    else:
        haystack = str(payload or "")
    return ETHERSCAN_CHAIN_COVERAGE_ERROR.lower() in haystack.lower()


def mark_etherscan_proxy_eth_call_unsupported(chain_id: int) -> None:
    """Remember that Etherscan proxy eth_call is not supported for this chain on this run."""
    _ETHERSCAN_PROXY_ETH_CALL_UNSUPPORTED_CHAINS.add(int(chain_id))


def is_etherscan_proxy_eth_call_unsupported(chain_id: int) -> bool:
    """Check whether Etherscan proxy eth_call is known unsupported for this chain."""
    return int(chain_id) in _ETHERSCAN_PROXY_ETH_CALL_UNSUPPORTED_CHAINS


def mark_etherscan_tx_endpoint_unsupported(chain_id: int) -> None:
    """Remember that Etherscan transaction-history endpoints are unsupported for this chain."""
    _ETHERSCAN_TX_ENDPOINT_UNSUPPORTED_CHAINS.add(int(chain_id))


def is_etherscan_tx_endpoint_unsupported(chain_id: int) -> bool:
    """Check whether Etherscan transaction-history endpoints are known unsupported for this chain."""
    return int(chain_id) in _ETHERSCAN_TX_ENDPOINT_UNSUPPORTED_CHAINS


def rpc_request(
    chain_id: int,
    method: str,
    params: list[Any],
    *,
    timeout: int = 10,
) -> tuple[Any | None, str | None, str | None]:
    """
    Perform a raw JSON-RPC request.

    Returns:
        tuple(result_or_none, error_message_or_none, rpc_url_or_none)
    """
    rpc_url = resolve_rpc_url(chain_id)
    if not rpc_url:
        return None, "No RPC URL configured", None

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }

    try:
        response = requests.post(rpc_url, json=payload, timeout=timeout)
        response.raise_for_status()
        rpc_data = response.json()
    except Exception as exc:  # pragma: no cover - network failures are environment-specific
        return None, str(exc), rpc_url

    if "error" in rpc_data:
        error = rpc_data["error"]
        if isinstance(error, dict):
            return None, error.get("message") or str(error), rpc_url
        return None, str(error), rpc_url

    if "result" not in rpc_data:
        return None, "Missing result field", rpc_url

    return rpc_data.get("result"), None, rpc_url


def rpc_eth_call(
    chain_id: int,
    to: str,
    data: str,
    *,
    timeout: int = 10,
) -> tuple[str | None, str | None, str | None]:
    """
    Perform a raw JSON-RPC eth_call.

    Returns:
        tuple(result_hex_or_none, error_message_or_none, rpc_url_or_none)
    """
    return rpc_request(
        chain_id,
        "eth_call",
        [{"to": to, "data": data}, "latest"],
        timeout=timeout,
    )


def rpc_get_transaction_by_hash(
    chain_id: int,
    tx_hash: str,
    *,
    timeout: int = 10,
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """
    Fetch a full transaction object via JSON-RPC eth_getTransactionByHash.

    Returns:
        tuple(transaction_dict_or_none, error_message_or_none, rpc_url_or_none)
    """
    result, error, rpc_url = rpc_request(chain_id, "eth_getTransactionByHash", [tx_hash], timeout=timeout)
    if error:
        return None, error, rpc_url
    if result is None:
        return None, None, rpc_url
    if not isinstance(result, dict):
        return None, f"Unexpected result type: {type(result).__name__}", rpc_url
    return result, None, rpc_url
