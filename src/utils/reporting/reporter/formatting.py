"""Markdown rendering helpers for report generator output."""

import json as json_lib
import os
import shutil
from pathlib import Path
from typing import Any


def _format_code_snippet(snippet: Any) -> str:
    """
    Render a code snippet (dict/str) as a fenced JSON block for readability.
    Handles JSON strings within dicts (e.g., {"field_to_add": "{\\"key\\": \\"value\\"}"})
    """
    if snippet is None:
        return ""

    try:
        if isinstance(snippet, str):
            candidate = snippet.strip()
            try:
                parsed = json_lib.loads(candidate)
                snippet_str = json_lib.dumps(parsed, indent=2, ensure_ascii=False)
            except Exception:
                snippet_str = candidate
        elif isinstance(snippet, dict):
            # Parse JSON strings within the dict
            formatted_dict = {}
            for key, value in snippet.items():
                if isinstance(value, str):
                    # Try to parse as JSON
                    try:
                        formatted_dict[key] = json_lib.loads(value)
                    except Exception:
                        formatted_dict[key] = value
                else:
                    formatted_dict[key] = value
            snippet_str = json_lib.dumps(formatted_dict, indent=2, ensure_ascii=False)
        elif isinstance(snippet, list):
            snippet_str = json_lib.dumps(snippet, indent=2, ensure_ascii=False)
        else:
            snippet_str = str(snippet)
    except Exception:
        snippet_str = str(snippet)

    return f"\n```json\n{snippet_str}\n```\n"


def _brace_delta(line: str) -> int:
    """Approximate brace balance to group JSON-like blocks."""
    return line.count("{") - line.count("}") + line.count("[") - line.count("]")


def _format_text_with_json_blocks(text: str) -> str:
    """
    Look for JSON-like blocks in freeform text and render them as fenced code blocks.
    """
    if not text:
        return ""

    lines = text.splitlines()
    output: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        # Skip if already in a fenced block
        if stripped.startswith("```"):
            output.append(line)
            i += 1
            continue

        # Multi-line block starting with brace on its own line
        if stripped.startswith("{") or stripped.startswith("["):
            balance = _brace_delta(stripped)
            block_lines = [line]
            j = i + 1
            while balance > 0 and j < len(lines):
                block_lines.append(lines[j])
                balance += _brace_delta(lines[j])
                j += 1

            block_text = "\n".join(block_lines)
            try:
                parsed = json_lib.loads(block_text)
                pretty = json_lib.dumps(parsed, indent=2)
                output.append(f"```json\n{pretty}\n```")
                i = j
                continue
            except Exception:
                # Fall through to treat lines normally
                pass

        # Inline JSON fragment on the same line (e.g., "1) Change ... {\"intent\": \"X\"}")
        brace_pos = line.find("{")
        if brace_pos != -1:
            prefix = line[:brace_pos].rstrip()
            candidate = line[brace_pos:].strip()
            try:
                parsed = json_lib.loads(candidate)
                pretty = json_lib.dumps(parsed, indent=2)
                if prefix:
                    output.append(prefix)
                output.append(f"```json\n{pretty}\n```")
                i += 1
                continue
            except Exception:
                pass

        output.append(line)
        i += 1

    return "\n".join(output)


def _render_recommendations_from_json(recs: dict[str, Any]) -> str:
    """
    Format recommendations from structured JSON into markdown, preserving
    code snippets and optional improvements.
    """
    if not recs:
        return ""

    lines: list[str] = []

    # Fixes
    for fix in recs.get("fixes", []):
        title = fix.get("title", "Fix")
        description = fix.get("description", "")
        formatted_desc = _format_text_with_json_blocks(description)
        lines.append(f"- **{title}:** {formatted_desc}")
        if fix.get("code_snippet"):
            lines.append(_format_code_snippet(fix["code_snippet"]))

    # Spec limitations
    for lim in recs.get("spec_limitations", []):
        param = lim.get("parameter", "Parameter")
        explanation = lim.get("explanation", "")
        impact = lim.get("impact", "")
        detected = lim.get("detected_pattern")
        line = f"- **{param} cannot be clear signed:** {explanation}"
        if impact:
            line += f" **Why this matters:** {impact}"
        if detected:
            line += f" **Detected pattern:** {detected}"
        lines.append(line)

    # Optional improvements
    for opt in recs.get("optional_improvements", []):
        title = opt.get("title", "Improvement")
        description = opt.get("description", "")
        prefix = "(Optional) "
        if title.lower().startswith("optional"):
            prefix = ""
        formatted_desc = _format_text_with_json_blocks(description)
        lines.append(f"- **{prefix}{title}:** {formatted_desc}")
        if opt.get("code_snippet"):
            lines.append(_format_code_snippet(opt["code_snippet"]))

    # Additional suggested snippets for optional improvements
    optional_snippets = recs.get("suggested_code_snippets_for_optional_improvements") or []
    if optional_snippets:
        lines.append("**Suggested code snippets for optional improvements:**")
        for snippet in optional_snippets:
            desc = snippet.get("description", "Optional improvement")
            lines.append(f"- {desc}")
            for key, value in snippet.items():
                if key == "description":
                    continue
                label = key.replace("_", " ").title()
                lines.append(f"  - {label}:")
                lines.append(_format_code_snippet(value))

    if not lines:
        return ""

    # Join with double newlines to keep spacing around code fences
    return "\n\n".join(lines) + "\n"


def _render_critical_issue(issue_obj: Any, index: int) -> str:
    """
    Render a critical issue with details into markdown (with collapsible section).
    """
    if not isinstance(issue_obj, dict):
        return f"- {issue_obj}"

    summary = issue_obj.get("issue", f"Issue {index}")
    details = issue_obj.get("details", {})
    if not details:
        return f"- {summary}"

    md = f"**{index}. {summary}**\n\n"
    md += "<details>\n"
    md += "<summary><i>🔍 Click to see detailed analysis</i></summary>\n\n"

    def add_detail(label: str, key: str):
        value = details.get(key)
        if value:
            md_part = _format_text_with_json_blocks(str(value))
            md_nonlocal.append(f"**{label}:** {md_part}\n")

    md_nonlocal: list[str] = []
    add_detail("What descriptor shows", "what_descriptor_shows")
    add_detail("What actually happens", "what_actually_happens")
    add_detail("Why this is critical", "why_critical")
    add_detail("Evidence", "evidence")

    md += "\n".join(md_nonlocal) + "\n"
    md += "</details>\n\n"
    md += "<br>\n\n"  # Add visual spacing after collapsible section
    return md


def format_source_code_section(source_code: dict) -> str:
    """
    Format source code dictionary into a markdown collapsible section.

    Args:
        source_code: Dictionary with extracted source code components

    Returns:
        Formatted markdown string for source code section
    """
    if not source_code or not source_code.get("function"):
        return ""

    code_block = ""

    # Add custom types if available (HIGHEST PRIORITY - needed for bitpacked params)
    if source_code.get("custom_types"):
        code_block += "// Custom types:\n"
        for custom_type in source_code["custom_types"]:
            code_block += f"{custom_type}\n"
        code_block += "\n"

    # Add using statements if available
    if source_code.get("using_statements"):
        code_block += "// Using statements:\n"
        for using_stmt in source_code["using_statements"]:
            code_block += f"{using_stmt}\n"
        code_block += "\n"

    # Add function docstring if available
    if source_code.get("function_docstring"):
        code_block += f"// Docstring:\n{source_code['function_docstring']}\n\n"

    # Add constants if available
    if source_code.get("constants"):
        code_block += "// Constants:\n"
        for constant in source_code["constants"]:
            code_block += f"{constant}\n"
        code_block += "\n"

    # Add modifiers if available
    if source_code.get("modifiers"):
        code_block += "// Modifiers:\n"
        for modifier in source_code["modifiers"]:
            code_block += f"{modifier}\n\n"

    # Add structs if available
    if source_code.get("structs"):
        code_block += "// Structs:\n"
        for struct in source_code["structs"]:
            code_block += f"{struct}\n"
        code_block += "\n"

    # Add enums if available
    if source_code.get("enums"):
        code_block += "// Enums:\n"
        for enum in source_code["enums"]:
            code_block += f"{enum}\n"
        code_block += "\n"

    # Add main function
    code_block += "// Main function:\n"
    code_block += source_code["function"]

    # Add internal functions if available
    if source_code.get("internal_functions"):
        code_block += "\n\n// Internal functions called:\n"
        for internal_func in source_code["internal_functions"]:
            if internal_func.get("docstring"):
                code_block += f"{internal_func['docstring']}\n"
            code_block += f"{internal_func['body']}\n\n"

    # Add parent functions (from super. calls) if available
    if source_code.get("parent_functions"):
        code_block += "\n\n// Parent contract implementations (from super. calls):\n"
        for parent_func in source_code["parent_functions"]:
            parent_name = parent_func.get("parent_contract", "Unknown")
            func_name = parent_func.get("function_name", "unknown")
            code_block += f"// From {parent_name}.{func_name}():\n"
            code_block += f"{parent_func['body']}\n\n"

    # Add libraries if available (LOWEST PRIORITY - shown last)
    if source_code.get("libraries"):
        code_block += "\n// Libraries:\n"
        for library in source_code["libraries"]:
            code_block += f"{library}\n\n"

    # Add truncation warning if needed
    if source_code.get("truncated"):
        code_block += "\n// ⚠️ Note: Code was truncated to fit within line limit\n"

    return code_block


def _truncate_value(val: Any, max_len: int = 120) -> str:
    """Truncate a parameter value for display, preserving readability."""
    val_str = str(val)
    if len(val_str) > max_len:
        return val_str[: max_len - 3] + "..."
    return val_str


def _format_short_tx_hash(tx_hash: str) -> str:
    """Return a shortened tx hash for headers, e.g. ``0x021c...4b``."""
    if len(tx_hash) > 16:
        return f"{tx_hash[:6]}...{tx_hash[-4:]}"
    return tx_hash


def render_screenshots_section(
    screenshot_data: list[dict[str, Any]],
    report_dir: Path,
    decoded_transactions: list[dict[str, Any]] | None = None,
) -> str:
    """
    Build a collapsible markdown section with Ledger device screenshots grouped by tx.

    Each transaction gets its own sub-section showing the tx hash, a collapsible
    decoded-parameters block (matching the transaction-samples format), and the
    meaningful clear-signing screenshots.

    Args:
        screenshot_data: List of {"tx_hash": str, "screenshots": [path, ...]}.
        report_dir: Directory where the report file lives.
        decoded_transactions: Optional list of decoded tx dicts to show params.

    Returns:
        Markdown string (empty if no screenshots).
    """
    if not screenshot_data:
        return ""

    # Build lookup: tx_hash -> decoded params
    tx_params: dict[str, dict[str, Any]] = {}
    for tx in decoded_transactions or []:
        h = tx.get("hash", "")
        if h:
            tx_params[h.lower()] = tx

    screenshots_dir = report_dir / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    tx_sections: list[str] = []
    for idx, entry in enumerate(screenshot_data, 1):
        tx_hash = entry.get("tx_hash", "")
        paths = entry.get("screenshots", [])
        if not paths:
            continue

        images_md: list[str] = []
        for src_path_str in paths:
            src = Path(src_path_str)
            if not src.exists() or src.suffix.lower() != ".png":
                continue
            dst_name = f"{tx_hash[2:10]}_{src.name}"
            dst = screenshots_dir / dst_name
            if not dst.exists():
                shutil.copy2(src, dst)
            rel = os.path.relpath(dst, report_dir)
            images_md.append(f"![{src.stem}]({rel})")

        if not images_md:
            continue

        tx_block = f"#### Transaction {idx} — `{tx_hash}`\n\n"

        # Collapsible decoded parameters (same style as transaction samples)
        tx_info = tx_params.get(tx_hash.lower())
        if tx_info:
            decoded = tx_info.get("decoded_input", {})
            tx_value = tx_info.get("value")

            param_lines: list[str] = []
            if tx_value and str(tx_value) != "0":
                param_lines.append(f"native ETH sent: {tx_value} wei")

            for key, val in decoded.items():
                if key.startswith("_"):
                    continue
                param_lines.append(f"{key}: {_truncate_value(val)}")

            if param_lines:
                tx_block += "```python\n"
                tx_block += "\n".join(param_lines) + "\n"
                tx_block += "```\n\n"

        tx_block += " | ".join(images_md) + "\n"
        tx_sections.append(tx_block)

    if not tx_sections:
        return ""

    section = "<details>\n<summary><b>📸 Ledger Device Screenshots</b></summary>\n\n"
    section += "\n---\n\n".join(tx_sections)
    section += "\n</details>\n\n"
    return section
