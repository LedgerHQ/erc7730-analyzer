"""LLM backend configuration and defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal

Backend = Literal["openai", "anthropic", "cursor"]

VALID_BACKENDS: list[Backend] = ["openai", "anthropic", "cursor"]

BACKEND_DEFAULTS: dict[str, dict] = {
    "openai": {
        "model": "gpt-4o",
        "url": "https://api.openai.com/v1",
        "env_key": "OPENAI_API_KEY",
    },
    "anthropic": {
        "model": "claude-sonnet-4-20250514",
        "url": "https://api.anthropic.com",
        "env_key": "ANTHROPIC_API_KEY",
    },
    "cursor": {
        "model": "opus-4.6",
    },
}


@dataclass
class LLMConfig:
    """Resolved LLM configuration ready for use."""

    backend: Backend = "openai"
    model: str | None = None
    api_key: str | None = None
    api_url: str | None = None

    # Populated after resolve()
    _resolved: bool = field(default=False, repr=False)

    def resolve(self) -> LLMConfig:
        """Fill in defaults from BACKEND_DEFAULTS and environment variables."""
        if self.backend not in VALID_BACKENDS:
            raise ValueError(f"Unknown backend '{self.backend}'. Valid backends: {', '.join(VALID_BACKENDS)}")

        defaults = BACKEND_DEFAULTS[self.backend]
        self.model = self.model or defaults.get("model")

        if self.backend != "cursor":
            self.api_url = self.api_url or defaults.get("url")
            env_key = defaults.get("env_key", "")
            self.api_key = self.api_key or os.environ.get(env_key, "")

        self._resolved = True
        return self
