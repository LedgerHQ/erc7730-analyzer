"""Base fetching mixin: cache/state and Vyper detection helpers."""

import re
from typing import Optional

from ..shared import logger


class SourceCodeFetchingBaseMixin:
    def __init__(self, etherscan_api_key: str, coredao_api_key: Optional[str] = None):
        """
        Initialize the extractor.

        Args:
            etherscan_api_key: Etherscan API key
            coredao_api_key: Core DAO API key (optional)
        """
        import threading
        self.etherscan_api_key = etherscan_api_key
        self.coredao_api_key = coredao_api_key
        self.code_cache = {}  # Cache: contract_address -> extracted code dict
        self._cache_lock = threading.Lock()  # Thread-safe cache access


    def clear_cache(self):
        """Clear the source code cache to force fresh extraction."""
        with self._cache_lock:
            cache_size = len(self.code_cache)
            self.code_cache = {}
            logger.info(f"🧹 CLEARED source code cache ({cache_size} entries) - will extract fresh")


    def is_vyper_code(self, source_code: str) -> bool:
        """
        Detect if source code is Vyper.

        Args:
            source_code: The source code to check

        Returns:
            True if Vyper, False if Solidity
        """
        # Vyper-specific patterns
        vyper_patterns = [
            r'@external',
            r'@internal',
            r'@view',
            r'@pure',
            r'@payable',
            r'def\s+__init__\(',  # Vyper constructor
            r':\s*constant\(',     # Vyper constant
        ]

        for pattern in vyper_patterns:
            if re.search(pattern, source_code):
                return True

        return False

