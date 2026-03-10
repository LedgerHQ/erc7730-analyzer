"""LLM backend implementations: OpenAI, Anthropic, and Cursor CLI."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, ValidationError

if TYPE_CHECKING:
    from .config import LLMConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# OpenAI backend (LangChain ChatOpenAI + structured output)
# ---------------------------------------------------------------------------


async def invoke_openai(
    config: LLMConfig,
    system_prompt: str,
    user_content: str,
    output_schema: type[BaseModel],
) -> BaseModel:
    """Invoke OpenAI via LangChain with structured output."""
    from langchain_openai import ChatOpenAI

    if not config.api_key:
        raise ValueError("OpenAI backend requires an API key. Set OPENAI_API_KEY or pass --api-key.")

    logger.info(f"[OpenAI] model={config.model}, endpoint={config.api_url}")

    llm = ChatOpenAI(
        model=config.model,
        temperature=0,
        api_key=config.api_key,
        base_url=config.api_url,
    )
    structured_llm = llm.with_structured_output(output_schema)

    messages = [
        ("system", system_prompt),
        ("human", user_content),
    ]
    return await structured_llm.ainvoke(messages)


# ---------------------------------------------------------------------------
# Anthropic backend (LangChain ChatAnthropic + structured output)
# ---------------------------------------------------------------------------


async def invoke_anthropic(
    config: LLMConfig,
    system_prompt: str,
    user_content: str,
    output_schema: type[BaseModel],
) -> BaseModel:
    """Invoke Anthropic via LangChain with structured output."""
    from langchain_anthropic import ChatAnthropic

    if not config.api_key:
        raise ValueError("Anthropic backend requires an API key. Set ANTHROPIC_API_KEY or pass --api-key.")

    logger.info(f"[Anthropic] model={config.model}")

    opts: dict = {
        "model": config.model,
        "temperature": 0,
        "api_key": config.api_key,
    }
    default_url = "https://api.anthropic.com"
    if config.api_url and config.api_url != default_url:
        opts["anthropic_api_url"] = config.api_url

    llm = ChatAnthropic(**opts)
    structured_llm = llm.with_structured_output(output_schema)

    messages = [
        ("system", system_prompt),
        ("human", user_content),
    ]
    return await structured_llm.ainvoke(messages)


# ---------------------------------------------------------------------------
# Cursor CLI backend (subprocess + JSON parse)
# ---------------------------------------------------------------------------

_CURSOR_TMP_DIR = os.path.join(tempfile.gettempdir(), "erc7730-analyzer")


async def invoke_cursor(
    config: LLMConfig,
    system_prompt: str,
    user_content: str,
    output_schema: type[BaseModel],
) -> BaseModel:
    """Invoke Cursor agent CLI and parse JSON response into a Pydantic model."""
    schema_json = json.dumps(output_schema.model_json_schema(), indent=2)

    combined_prompt = "\n".join(
        [
            "# System Instructions",
            "",
            system_prompt,
            "",
            "# User Input",
            "",
            user_content,
            "",
            "# Output Requirements",
            "",
            "Output ONLY a valid JSON object matching the schema below.",
            "Do NOT include any markdown fences, commentary, or explanation.",
            "Do NOT add any extra fields beyond what the schema specifies.",
            "Every required field must be present. Use null for optional fields you cannot fill.",
            "",
            "JSON Schema:",
            "",
            schema_json,
        ]
    )

    os.makedirs(_CURSOR_TMP_DIR, exist_ok=True)
    tmp_file = Path(_CURSOR_TMP_DIR) / f"prompt-{id(combined_prompt)}-{asyncio.get_event_loop().time():.0f}.md"
    tmp_file.write_text(combined_prompt, encoding="utf-8")

    logger.info(f"[Cursor] Wrote prompt to {tmp_file} ({len(combined_prompt)} chars)")

    args = [
        "cursor",
        "agent",
        "--mode",
        "ask",
        "--print",
        "--output-format",
        "text",
        "--trust",
    ]
    if config.model:
        args.extend(["--model", config.model])
    args.append(
        f"Read the file at {tmp_file} and follow all instructions in it. Output ONLY the requested JSON, no extra text."
    )

    logger.info(f"[Cursor] Running: {' '.join(args)}")

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await proc.communicate()
    finally:
        with contextlib.suppress(OSError):
            tmp_file.unlink()

    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")

    if proc.returncode != 0:
        raise RuntimeError(f"Cursor agent exited with code {proc.returncode}" + (f": {stderr[:500]}" if stderr else ""))
    if not stdout.strip():
        raise RuntimeError("Cursor agent returned empty output")

    logger.info(f"[Cursor] Response: {len(stdout)} chars")

    return _parse_json_response(stdout, output_schema)


def _extract_json_string(text: str) -> str:
    """Best-effort extraction of a JSON object from free-form LLM text."""
    cleaned = text.strip()

    # Strip markdown code fences (```json ... ``` or ``` ... ```)
    fenced = re.search(r"```(?:json)?\s*\n(.*?)```", cleaned, re.DOTALL)
    if fenced:
        cleaned = fenced.group(1).strip()

    # If it already looks like a JSON object, return as-is
    if cleaned.startswith("{"):
        return cleaned

    # Try to find the first { ... last } span
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        return cleaned[first_brace : last_brace + 1]

    return cleaned


def _parse_json_response(text: str, schema: type[BaseModel]) -> BaseModel:
    """Extract and validate JSON from raw LLM text output.

    Strips unknown fields recursively since the cursor backend cannot enforce
    schema at the API level like OpenAI/Anthropic can.
    """
    json_str = _extract_json_string(text)

    # First try strict parsing (fast path if cursor got it exactly right)
    try:
        return schema.model_validate_json(json_str)
    except ValidationError:
        pass

    # Parse raw JSON
    try:
        raw = json.loads(json_str)
    except json.JSONDecodeError as e:
        _log_parse_failure(text, f"Not valid JSON: {e}")
        raise

    # Normalize: strip unknown fields and fill missing required fields with defaults
    normalized = _normalize_for_schema(raw, schema)
    try:
        return schema.model_validate(normalized)
    except ValidationError as e:
        _log_parse_failure(text, str(e))
        raise


# Default values used to fill required fields the LLM omitted
_TYPE_DEFAULTS: dict[type, object] = {
    str: "",
    int: 0,
    float: 0.0,
    bool: False,
}


def _resolve_annotation(annotation: type) -> tuple:
    """Unwrap Optional/Union and return (inner_type, origin, args, is_optional)."""
    origin = getattr(annotation, "__origin__", None)
    args = getattr(annotation, "__args__", ())

    is_optional = False
    # typing.Union (covers Optional[X] = Union[X, None])
    if origin is type(None) or str(origin) == "typing.Union":
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            is_optional = True
            annotation = non_none[0]
            origin = getattr(annotation, "__origin__", None)
            args = getattr(annotation, "__args__", ())

    return annotation, origin, args, is_optional


def _normalize_for_schema(data: object, model: type[BaseModel]) -> object:
    """Recursively strip unknown keys and fill missing required fields."""
    if not isinstance(data, dict):
        return data

    known_fields = model.model_fields
    result = {}

    # Copy and recurse into known fields present in data
    for key, value in data.items():
        if key not in known_fields:
            continue
        field_info = known_fields[key]
        annotation, origin, args, _ = _resolve_annotation(field_info.annotation)

        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            result[key] = _normalize_for_schema(value, annotation) if isinstance(value, dict) else value
        elif origin is list and args and isinstance(args[0], type) and issubclass(args[0], BaseModel):
            if isinstance(value, list):
                result[key] = [_normalize_for_schema(item, args[0]) for item in value]
            else:
                result[key] = value
        else:
            result[key] = value

    # Fill missing required fields with sensible defaults
    for field_name, field_info in known_fields.items():
        if field_name in result:
            continue

        if not field_info.is_required():
            continue

        annotation, origin, _args, is_optional = _resolve_annotation(field_info.annotation)

        if is_optional:
            result[field_name] = None
        elif origin is list:
            result[field_name] = []
        elif isinstance(annotation, type) and issubclass(annotation, BaseModel):
            result[field_name] = _build_default(annotation)
        elif annotation in _TYPE_DEFAULTS:
            result[field_name] = _TYPE_DEFAULTS[annotation]

    return result


def _build_default(model: type[BaseModel]) -> dict:
    """Build a minimal default dict for a BaseModel with all required fields filled."""
    result = {}
    for field_name, field_info in model.model_fields.items():
        if not field_info.is_required():
            continue

        annotation, origin, _args, is_optional = _resolve_annotation(field_info.annotation)

        if is_optional:
            result[field_name] = None
        elif origin is list:
            result[field_name] = []
        elif isinstance(annotation, type) and issubclass(annotation, BaseModel):
            result[field_name] = _build_default(annotation)
        elif annotation in _TYPE_DEFAULTS:
            result[field_name] = _TYPE_DEFAULTS[annotation]

    return result


def _log_parse_failure(raw_text: str, reason: str) -> None:
    """Print parse failure details to stderr for visibility."""
    preview = raw_text[:500].replace("\n", "\\n")
    sys.stderr.write(f"        [cursor] JSON parse failed: {reason}\n")
    sys.stderr.write(f"        [cursor] Response preview: {preview}...\n")
    sys.stderr.flush()
    logger.error(f"[Cursor] Parse failed: {reason}")
    logger.error(f"[Cursor] Full response ({len(raw_text)} chars): {raw_text[:2000]}")
