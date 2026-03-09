"""LLM client with backend routing."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from .backends import invoke_anthropic, invoke_cursor, invoke_openai

if TYPE_CHECKING:
    from pydantic import BaseModel

    from .config import LLMConfig

logger = logging.getLogger(__name__)


class LLMClient:
    """Thin wrapper that routes invocations to the configured backend."""

    def __init__(self, config: LLMConfig) -> None:
        if not config._resolved:
            config.resolve()
        self.config = config

    async def invoke(
        self,
        system_prompt: str,
        user_content: str,
        output_schema: type[BaseModel],
    ) -> BaseModel:
        """Send a system+user prompt to the configured backend and return structured output."""
        backend = self.config.backend
        logger.info(f"[LLM] Invoking [{backend}] (system: {len(system_prompt)} chars, user: {len(user_content)} chars)")

        start = time.monotonic()

        dispatch = {
            "openai": invoke_openai,
            "anthropic": invoke_anthropic,
            "cursor": invoke_cursor,
        }
        handler = dispatch.get(backend)
        if handler is None:
            raise ValueError(f"Unknown backend: {backend}")

        result = await handler(self.config, system_prompt, user_content, output_schema)

        elapsed = time.monotonic() - start
        logger.info(f"[LLM] Response from [{backend}] in {elapsed:.1f}s")

        return result
