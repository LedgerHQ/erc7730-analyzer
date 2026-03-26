"""Shared constants/logging for source-code extraction flow."""

import logging

from ...rpc_helpers import DEFAULT_RPC_URLS, resolve_rpc_url, rpc_eth_call

logger = logging.getLogger(__name__)

BLOCKSCOUT_URLS = {
    56: "https://api.bscscan.com/api",  # BNB Smart Chain
    97: "https://api-testnet.bscscan.com/api",  # BNB Testnet
    42220: "https://explorer.celo.org/api",  # Celo Mainnet
    44787: "https://explorer.celo.org/alfajores/api",  # Celo Alfajores Testnet
    14: "https://flare-explorer.flare.network",  # Flare Mainnet
    19: "https://songbird-explorer.flare.network",  # Songbird Network
    8453: "https://base.blockscout.com",  # Base Mainnet
    84532: "https://base-sepolia.blockscout.com",  # Base Sepolia
    10: "https://explorer.optimism.io",  # Optimism Mainnet
    11155420: "https://testnet-explorer.optimism.io",  # Optimism Sepolia
    100: "https://gnosis.blockscout.com",  # Gnosis Chain
    137: "https://polygon.blockscout.com",  # Polygon PoS
    1116: "https://openapi.coredao.org/api",  # Core DAO Mainnet
}

RPC_URLS = DEFAULT_RPC_URLS

__all__ = [
    "BLOCKSCOUT_URLS",
    "RPC_URLS",
    "logger",
    "resolve_rpc_url",
    "rpc_eth_call",
]
