"""Shared formatting helpers for markdown report rendering."""

import json
from typing import Any

from pydantic import BaseModel

def _risk_emoji(level: str) -> str:
    """
    Convert risk level string to emoji.

    Args:
        level: Risk level ("high", "medium", "low")

    Returns:
        Emoji string
    """
    return {
        'high': '🔴',
        'medium': '🟡',
        'low': '🟢'
    }.get(level.lower(), '⚪')

def _format_code_snippet(snippet: Any) -> str:
    """
    Render a code snippet object/string as a JSON code block.
    Handles both Pydantic models (CodeSnippet with JSON string fields) and raw strings.
    """
    if snippet is None:
        return ""

    # Try to pretty print JSON-like content; otherwise fall back to plain string
    try:
        # Convert Pydantic models to dict first, then parse JSON string fields
        if isinstance(snippet, BaseModel):
            snippet_dict = snippet.model_dump(exclude_none=True)
            # Parse JSON strings in the dict
            formatted_dict = {}
            for key, value in snippet_dict.items():
                if isinstance(value, str):
                    # Try to parse as JSON
                    try:
                        formatted_dict[key] = json.loads(value)
                    except Exception:
                        formatted_dict[key] = value
                else:
                    formatted_dict[key] = value
            snippet_str = json.dumps(formatted_dict, indent=2, ensure_ascii=False)
        elif isinstance(snippet, dict):
            # If it's a dict, recursively format nested JSON strings
            formatted_dict = {}
            for key, value in snippet.items():
                if isinstance(value, str):
                    # Always try to parse strings as JSON (not just ones starting with {)
                    try:
                        parsed = json.loads(value)
                        formatted_dict[key] = parsed
                    except Exception:
                        formatted_dict[key] = value
                else:
                    formatted_dict[key] = value
            snippet_str = json.dumps(formatted_dict, indent=2, ensure_ascii=False)
        elif isinstance(snippet, str):
            # String input - try to parse as JSON
            candidate = snippet.strip()
            try:
                parsed = json.loads(candidate)
                snippet_str = json.dumps(parsed, indent=2, ensure_ascii=False)
            except Exception:
                # Not JSON, return as-is
                snippet_str = candidate
        elif isinstance(snippet, list):
            snippet_str = json.dumps(snippet, indent=2, ensure_ascii=False)
        else:
            snippet_str = str(snippet)
    except Exception:
        snippet_str = str(snippet)

    return f"\n```json\n{snippet_str}\n```\n"

def _severity_emoji(severity: str) -> str:
    """
    Convert severity level to emoji.

    Args:
        severity: Severity level ("critical", "high", "medium", "low")

    Returns:
        Emoji string
    """
    return {
        'critical': '🔴',
        'high': '🟠',
        'medium': '🟡',
        'low': '🟢'
    }.get(severity.lower(), '⚪')

def _bool_emoji(value: bool) -> str:
    """
    Convert boolean to Yes/No emoji.

    Args:
        value: Boolean value

    Returns:
        Emoji string
    """
    return '✅ Yes' if value else '❌ No'

