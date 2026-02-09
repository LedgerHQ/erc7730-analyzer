"""Shared constants/logging for source-code extraction flow."""

import logging

from ...clients.transactions.constants import BLOCKSCOUT_URLS

logger = logging.getLogger(__name__)

RPC_URLS = {
    1: "https://eth.llamarpc.com",
    14: "https://flare-api.flare.network/ext/C/rpc",
    19: "https://songbird-api.flare.network/ext/C/rpc",  # Songbird Network
    8453: "https://mainnet.base.org",
    10: "https://mainnet.optimism.io",
    137: "https://polygon-rpc.com",
    100: "https://rpc.gnosischain.com",
    1116: "https://rpc.coredao.org",  # Core DAO Mainnet
}
