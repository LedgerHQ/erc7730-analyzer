"""Base analyzer state and shared configuration."""

from collections.abc import Callable
from typing import ClassVar

from web3 import Web3

from ..clients.transactions import TransactionFetcher
from ..extraction.source_code import SourceCodeExtractor


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
        lookback_days: int = 7,
        enable_source_code: bool = True,
        use_smart_referencing: bool = True,
        max_concurrent_api_calls: int = 2,
        max_api_retries: int = 3,
        analysis_mode: str = "single",
        max_selector_tool_rounds: int = 1,
        max_tool_requests_per_round: int = 1,
        llm_model: str = "gpt-5.4-nano",
        llm_reasoning_effort: str = "low",
        enable_screenshots: bool = False,
        screenshot_device: str = "stax",
        cs_tester_root: str | None = None,
        coin_apps_path: str | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ):
        self.etherscan_api_key = etherscan_api_key
        self.coredao_api_key = coredao_api_key
        self.lookback_days = lookback_days
        self.enable_source_code = enable_source_code
        self.use_smart_referencing = use_smart_referencing
        self.max_concurrent_api_calls = max_concurrent_api_calls
        self.max_api_retries = max_api_retries
        self.analysis_mode = analysis_mode
        self.max_selector_tool_rounds = max_selector_tool_rounds
        self.max_tool_requests_per_round = max_tool_requests_per_round
        self.llm_model = llm_model
        self.llm_reasoning_effort = llm_reasoning_effort
        self.enable_screenshots = enable_screenshots
        self.screenshot_device = screenshot_device
        self.cs_tester_root = cs_tester_root
        self.coin_apps_path = coin_apps_path
        self.progress_callback = progress_callback

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

    def report_progress(self, message: str) -> None:
        """Publish a coarse-grained progress update for external polling clients."""
        if self.progress_callback:
            self.progress_callback(message)
