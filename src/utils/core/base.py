"""Base analyzer state and shared configuration."""

from __future__ import annotations

from typing import ClassVar

from web3 import Web3

from ..clients.transactions import TransactionFetcher
from ..extraction.source_code import SourceCodeExtractor
from ..llm import LLMConfig


class AnalyzerBase:
    """Base class for analyzer runtime state."""

    ERC4626_INCLUDE_PATTERNS: ClassVar[list[str]] = [
        "erc4626",
        "erc-4626",
        "4626-vault",
        "4626vault",
    ]

    ERC4626_SOURCE_PATTERNS: ClassVar[list[str]] = [
        r"ERC4626",
        r"IERC4626",
        r"function\\s+asset\\s*\\(\\s*\\)",
        r"function\\s+deposit\\s*\\([^)]*\\)\\s*(?:public|external)",
        r"function\\s+mint\\s*\\([^)]*\\)\\s*(?:public|external)",
        r"function\\s+withdraw\\s*\\([^)]*\\)\\s*(?:public|external)",
        r"function\\s+redeem\\s*\\([^)]*\\)\\s*(?:public|external)",
    ]

    def __init__(
        self,
        etherscan_api_key: str | None = None,
        coredao_api_key: str | None = None,
        lookback_days: int = 20,
        enable_source_code: bool = True,
        use_smart_referencing: bool = True,
        max_concurrent_api_calls: int = 8,
        max_api_retries: int = 3,
        backend: str = "openai",
        model: str | None = None,
        api_key: str | None = None,
        api_url: str | None = None,
    ):
        self.etherscan_api_key = etherscan_api_key
        self.coredao_api_key = coredao_api_key
        self.lookback_days = lookback_days
        self.enable_source_code = enable_source_code
        self.use_smart_referencing = use_smart_referencing
        self.max_concurrent_api_calls = max_concurrent_api_calls
        self.max_api_retries = max_api_retries

        self.llm_config = LLMConfig(
            backend=backend,
            model=model,
            api_key=api_key,
            api_url=api_url,
        ).resolve()

        self.w3 = Web3()
        self.abi_helper = None
        self.tx_fetcher = TransactionFetcher(etherscan_api_key, lookback_days)
        self.source_extractor = SourceCodeExtractor(etherscan_api_key, coredao_api_key) if enable_source_code else None

        self.selector_to_format_key = {}
        self.selector_sources = {}
        self.extracted_codes = {}
        self.erc4626_context = None
        self.erc20_context = None
        self.protocol_name = None
