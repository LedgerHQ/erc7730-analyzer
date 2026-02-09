"""Shared helper utilities for analyzer flows."""

from typing import Any


def truncate_byte_arrays(obj: Any, max_bytes_length: int = 100):
    """
    Recursively truncate byte array representations in decoded parameters.

    Only truncates nested calldata (hex strings that look like encoded function calls).
    Keeps normal parameters (addresses, amounts, etc.) unchanged.

    Args:
        obj: The object to process (dict, list, tuple, str, bytes, or primitive)
        max_bytes_length: Maximum length for nested calldata hex representations

    Returns:
        Processed object with truncated nested calldata
    """
    if isinstance(obj, dict):
        return {k: truncate_byte_arrays(v, max_bytes_length) for k, v in obj.items()}
    if isinstance(obj, list):
        return [truncate_byte_arrays(item, max_bytes_length) for item in obj]
    if isinstance(obj, tuple):
        return tuple(truncate_byte_arrays(item, max_bytes_length) for item in obj)
    if isinstance(obj, bytes):
        if len(obj) > max_bytes_length:
            preview = obj[:max_bytes_length].hex()
            return f"0x{preview}... (truncated {len(obj)} bytes total)"
        return f"0x{obj.hex()}"
    if isinstance(obj, str):
        if obj.startswith("0x") and len(obj) > 200:
            bytes_count = (len(obj) - 2) // 2
            preview_chars = min(100, len(obj) - 2)
            return f"{obj[:preview_chars + 2]}... (truncated {bytes_count} bytes total)"
        return obj
    return obj
