"""
Markdown formatting for ERC-7730 analyzer JSON output.

This module takes structured JSON data from the AI and formats it into
human-readable markdown reports. This separates content generation (AI)
from presentation (Python), improving performance and maintainability.

Performance Impact:
- AI generates ~60% fewer tokens (1.5k vs 4k)
- Response time reduced by ~55-65% (30-40s vs 90s)
- More reliable parsing (JSON vs regex)
"""

import json
import logging
from typing import Dict, List, Any, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ============================================================================
# Helper Functions
# ============================================================================

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


# ============================================================================
# Critical Report Formatter
# ============================================================================

def format_critical_report(data: Dict) -> str:
    """
    Generate critical issues markdown report from JSON data.

    This formats the "mini report" that provides a quick overview of
    critical issues and recommendations.

    Args:
        data: JSON object with:
            {
                "function_signature": str,
                "selector": str,
                "erc7730_format": dict,
                "critical_issues": list[dict],
                "recommendations": dict
            }

    Returns:
        Formatted markdown string
    """
    try:
        function_sig = data['function_signature']
        selector = data['selector']
        erc7730_format = data['erc7730_format']

        # Extract issues (plain text for mini report)
        critical_issues = data.get('critical_issues', [])
        issues = [issue.get('issue', '') for issue in critical_issues]

        recs = data.get('recommendations', {
            'fixes': [],
            'spec_limitations': [],
            'optional_improvements': []
        })

        md = f"## Critical Issues for `{function_sig}`\n\n"
        md += f"**Selector:** `{selector}`\n\n"
        md += "---\n\n"

        # ERC-7730 format (collapsible)
        md += "<details>\n"
        md += "<summary><strong>📋 ERC-7730 Format Definition</strong> (click to expand)</summary>\n\n"
        md += "This is the complete ERC-7730 metadata for this selector, including all referenced definitions and constants:\n\n"
        md += "```json\n"
        md += json.dumps(erc7730_format, indent=2)
        md += "\n```\n\n"
        md += "</details>\n\n"
        md += "---\n\n"

        # Issues section
        md += "### **Issues Found:**\n\n"
        if not critical_issues:
            md += "✅ No critical issues found\n\n"
        else:
            for idx, issue_obj in enumerate(critical_issues, 1):
                # Get issue summary (brief description)
                issue_summary = issue_obj.get('issue', '')
                details = issue_obj.get('details', {})

                if details:
                    # Structured format with collapsible details
                    md += f"**{idx}. {issue_summary}**\n\n"
                    md += "<details>\n"
                    md += "<summary><i>🔍 Click to see detailed analysis</i></summary>\n\n"

                    if details.get('what_descriptor_shows'):
                        md += f"**What descriptor shows:** {details['what_descriptor_shows']}\n\n"
                    if details.get('what_actually_happens'):
                        md += f"**What actually happens:** {details['what_actually_happens']}\n\n"
                    if details.get('why_critical'):
                        md += f"**Why this is critical:** {details['why_critical']}\n\n"
                    if details.get('evidence'):
                        md += f"**Evidence:** {details['evidence']}\n\n"

                    md += "</details>\n\n"
                else:
                    # Fallback to simple format for backward compatibility
                    md += f"- {issue_summary}\n"
            md += "\n"

        md += "---\n\n"

        # Recommendations section
        md += "### **Recommendations:**\n\n"

        has_any_recommendations = any([
            recs.get('fixes'),
            recs.get('spec_limitations'),
            recs.get('optional_improvements')
        ])

        if not has_any_recommendations:
            md += "**No additional recommendations - descriptor is comprehensive.**\n\n"
            return md

        # Fixes for critical issues
        if recs.get('fixes'):
            md += "#### 🔧 Fixes for Critical Issues\n\n"
            for idx, fix in enumerate(recs['fixes'], 1):
                title = fix.get('title', 'Fix')
                description = fix.get('description', '')
                md += f"**{idx}. {title}**\n\n"
                md += f"{description}\n\n"

                code_snippet = fix.get('code_snippet')
                if code_snippet:
                    # Convert to dict if it's a Pydantic model
                    if isinstance(code_snippet, BaseModel):
                        snippet_dict = code_snippet.model_dump(exclude_none=True)
                    else:
                        snippet_dict = code_snippet

                    # Parse and display each field separately for clarity
                    # Each field may be a JSON string that needs parsing
                    for field_name, field_label in [
                        ('field_to_add', 'Field to add'),
                        ('changes_to_make', 'Changes to make'),
                        ('full_example', 'Full example')
                    ]:
                        field_value = snippet_dict.get(field_name)
                        if field_value:
                            md += f"**{field_label}:**\n"
                            # Parse JSON string if needed
                            if isinstance(field_value, str):
                                try:
                                    parsed = json.loads(field_value)
                                    md += f"\n```json\n{json.dumps(parsed, indent=2, ensure_ascii=False)}\n```\n\n"
                                except Exception:
                                    # Not JSON or invalid, show as-is
                                    md += f"\n```\n{field_value}\n```\n\n"
                            else:
                                # Already an object
                                md += f"\n```json\n{json.dumps(field_value, indent=2, ensure_ascii=False)}\n```\n\n"

                md += "\n"

        # Spec limitations
        if recs.get('spec_limitations'):
            md += "#### ⚠️ Spec Limitations\n\n"
            for idx, lim in enumerate(recs['spec_limitations'], 1):
                param = lim.get('parameter', 'Parameter')
                explanation = lim.get('explanation', '')
                impact = lim.get('impact', '')
                detected_pattern = lim.get('detected_pattern')

                md += f"**{idx}. {param} cannot be clear signed**\n\n"
                md += f"**Explanation:** {explanation}\n\n"
                if impact:
                    md += f"**Impact:** {impact}\n\n"
                if detected_pattern:
                    md += f"**Detected pattern:** `{detected_pattern}`\n\n"

        # Optional improvements
        if recs.get('optional_improvements'):
            md += "#### 💡 Optional Improvements\n\n"
            for idx, opt in enumerate(recs['optional_improvements'], 1):
                title = opt.get('title', 'Improvement')
                description = opt.get('description', '')
                md += f"**{idx}. {title}**\n\n"
                md += f"{description}\n\n"

                code_snippet = opt.get('code_snippet')
                if code_snippet:
                    # Convert to dict if it's a Pydantic model
                    if isinstance(code_snippet, BaseModel):
                        snippet_dict = code_snippet.model_dump(exclude_none=True)
                    else:
                        snippet_dict = code_snippet

                    # Parse and display each field separately for clarity
                    # Each field may be a JSON string that needs parsing
                    for field_name, field_label in [
                        ('field_to_add', 'Field to add'),
                        ('changes_to_make', 'Changes to make'),
                        ('full_example', 'Full example')
                    ]:
                        field_value = snippet_dict.get(field_name)
                        if field_value:
                            md += f"**{field_label}:**\n"
                            # Parse JSON string if needed
                            if isinstance(field_value, str):
                                try:
                                    parsed = json.loads(field_value)
                                    md += f"\n```json\n{json.dumps(parsed, indent=2, ensure_ascii=False)}\n```\n\n"
                                except Exception:
                                    # Not JSON or invalid, show as-is
                                    md += f"\n```\n{field_value}\n```\n\n"
                            else:
                                # Already an object
                                md += f"\n```json\n{json.dumps(field_value, indent=2, ensure_ascii=False)}\n```\n\n"

                md += "\n"

        # Additional suggested snippets for optional improvements (if provided)
        optional_snippets = recs.get('suggested_code_snippets_for_optional_improvements') or []
        if optional_snippets:
            md += "\n**Suggested code snippets for optional improvements:**\n\n"
            for snippet in optional_snippets:
                desc = snippet.get('description', 'Optional improvement')
                md += f"- {desc}\n"

                for key, value in snippet.items():
                    if key == 'description':
                        continue
                    label = key.replace('_', ' ').title()
                    md += f"  - {label}:\n"
                    md += _format_code_snippet(value)

        md += "\n"
        return md

    except KeyError as e:
        logger.error(f"Missing required field in critical report data: {e}")
        return f"Error formatting critical report: Missing field {e}\n\n"
    except Exception as e:
        logger.error(f"Error formatting critical report: {e}")
        return f"Error formatting critical report: {str(e)}\n\n"


# ============================================================================
# Detailed Report Formatter
# ============================================================================

def format_detailed_report(data: Dict) -> str:
    """
    Generate detailed analysis markdown report from JSON data.

    This formats the comprehensive report with 6 sections:
    1. Intent Analysis
    2. Critical Issues (shared with mini report)
    3. Missing Parameters
    4. Display Issues
    5. Transaction Samples
    6. Overall Assessment

    Args:
        data: JSON object with all report data (unified structure)

    Returns:
        Formatted markdown string
    """
    try:
        md = ""  # No header - mini report already has the function info

        # Extract function signature from intent analysis
        intent_data = data.get('intent_analysis', {})
        declared_intent = intent_data.get('declared_intent', 'N/A')

        # 1. Intent Analysis
        md += _format_intent_analysis(intent_data)
        md += "---\n\n"

        # 2. Critical Issues (uses same data as mini report)
        md += _format_critical_issues_section(data.get('critical_issues', []))
        md += "---\n\n"

        # 3. Missing Parameters
        md += _format_missing_parameters(data.get('missing_parameters', []))
        md += "---\n\n"

        # 4. Display Issues
        md += _format_display_issues(data.get('display_issues', []))
        md += "---\n\n"

        # 5. Transaction Samples
        md += _format_transaction_samples(data.get('transaction_samples', []))
        md += "---\n\n"

        # 6. Overall Assessment (pass recommendations for Key Recommendations section)
        md += _format_overall_assessment(
            data.get('overall_assessment', {}),
            data.get('recommendations', {})
        )

        return md

    except Exception as e:
        logger.error(f"Error formatting detailed report: {e}")
        return f"## Error\n\nError formatting detailed report: {str(e)}\n\n"


def _format_intent_analysis(intent_data: Dict) -> str:
    """Format the Intent Analysis section."""
    md = "### 1️⃣ Intent Analysis\n\n"

    declared_intent = intent_data.get('declared_intent', 'N/A')
    assessment = intent_data.get('assessment', '')
    spelling_errors = intent_data.get('spelling_errors', [])

    md += f"> **Declared Intent:** *\"{declared_intent}\"*\n\n"

    if assessment:
        md += f"{assessment}\n\n"

    if spelling_errors:
        md += "**Spelling/Grammar Errors:**\n"
        for error in spelling_errors:
            md += f"- {error}\n"
        md += "\n"

    return md


def _format_critical_issues_section(critical_issues: List[Dict]) -> str:
    """Format the Critical Issues section."""
    md = "### 2️⃣ Critical Issues\n\n"
    md += "> 🔴 **CRITICAL** - Issues that could lead to users being deceived or losing funds\n\n"

    if not critical_issues:
        md += "**✅ No critical issues found**\n\n"
    else:
        for idx, issue_obj in enumerate(critical_issues, 1):
            issue_summary = issue_obj.get('issue', '')
            details = issue_obj.get('details', {})

            if details:
                # Structured format with collapsible details
                md += f"**{idx}. {issue_summary}**\n\n"
                md += "<details>\n"
                md += "<summary><i>🔍 Click to see detailed analysis</i></summary>\n\n"

                if details.get('what_descriptor_shows'):
                    md += f"**What descriptor shows:** {details['what_descriptor_shows']}\n\n"
                if details.get('what_actually_happens'):
                    md += f"**What actually happens:** {details['what_actually_happens']}\n\n"
                if details.get('why_critical'):
                    md += f"**Why this is critical:** {details['why_critical']}\n\n"
                if details.get('evidence'):
                    md += f"**Evidence:** {details['evidence']}\n\n"

                md += "</details>\n\n"
            else:
                # Fallback to simple format for backward compatibility
                md += f"- {issue_summary}\n"
        md += "\n"

    return md


def _format_missing_parameters(missing_params: List[Dict]) -> str:
    """Format the Missing Parameters section."""
    md = "### 3️⃣ Missing Parameters\n\n"
    md += "> ⚠️ *Parameters present in ABI but NOT shown to users in ERC-7730*\n\n"

    if not missing_params:
        md += "**✅ All parameters are covered**\n\n"
    else:
        md += "| Parameter | Why It's Important | Risk Level |\n"
        md += "|-----------|-------------------|:----------:|\n"

        for param in missing_params:
            param_name = param.get('parameter', 'Unknown')
            importance = param.get('importance', '')
            risk_level = param.get('risk_level', 'medium')
            emoji = _risk_emoji(risk_level)

            md += f"| `{param_name}` | {importance} | {emoji} {risk_level.title()} |\n"

        md += "\n"

    return md


def _format_display_issues(display_issues: List[Dict]) -> str:
    """Format the Display Issues section."""
    md = "### 4️⃣ Display Issues\n\n"

    if not display_issues:
        md += "> 🟡 **Issues with how information is presented to users (non-critical UX improvements)**\n\n"
        md += "**✅ No display issues found**\n\n"
        return md

    # Check if first issue is the no-transactions warning (severity: high)
    has_no_tx_warning = display_issues and display_issues[0].get('type') == 'no_historical_transactions'

    if has_no_tx_warning:
        # Format warning prominently at the top
        warning = display_issues[0]
        md += f"> ⚠️ **WARNING: {warning.get('type', '').replace('_', ' ').title()}**\n\n"
        md += f"{warning.get('description', '')}\n\n"
        md += "---\n\n"

        # Process remaining issues
        remaining_issues = display_issues[1:]
    else:
        remaining_issues = display_issues

    if remaining_issues:
        md += "> 🟡 **Issues with how information is presented to users (non-critical UX improvements)**\n\n"
        for issue in remaining_issues:
            issue_type = issue.get('type', 'unknown').replace('_', ' ').title()
            description = issue.get('description', '')
            severity = issue.get('severity', 'low')
            md += f"- **{issue_type}** ({severity}): {description}\n"
        md += "\n"

    return md


def _format_transaction_samples(samples: List[Dict]) -> str:
    """Format the Transaction Samples section with collapsible decoded parameters."""
    md = "### 5️⃣ Transaction Samples - What Users See\n\n"

    if not samples:
        md += "⚠️ **Warning: No Historical Transactions Found**\n\n"
        md += "This section is based ONLY on static source code review without real transaction data.\n\n"
        md += "**Impact:** The analysis cannot verify:\n"
        md += "- Actual on-chain behavior and token flows\n"
        md += "- Real-world parameter values and edge cases\n"
        md += "- Event emissions and receipt logs\n"
        md += "- Integration with other contracts\n\n"
        md += "**Recommendations:**\n"
        md += "1. Increase the `LOOKBACK_DAYS` environment variable to search a longer time period\n"
        md += "2. Provide manual sample transactions for this selector to enable dynamic analysis\n"
        md += "3. Verify this function is actually being used in production\n"
        md += "4. If this is a new/unused function, consider removing it from the ERC-7730 file until it's actively used\n\n"
        return md

    for i, sample in enumerate(samples, 1):
        # Get transaction hash if available
        tx_hash = sample.get('transaction_hash', '')
        if tx_hash:
            # Display full hash directly
            md += f"#### 📝 Transaction {i} - `{tx_hash}`\n\n"
        else:
            md += f"#### 📝 Transaction {i}\n\n"

        # User Intent table
        user_intent = sample.get('user_intent', [])
        if user_intent:
            md += "**What Users See (from ERC-7730):**\n\n"
            md += "| Field | ✅ Value Shown | ❌ Hidden/Missing |\n"
            md += "|-------|---------------|-------------------|\n"

            for intent in user_intent:
                field_label = intent.get('field_label', '')
                value_shown = intent.get('value_shown', '')
                hidden_missing = intent.get('hidden_missing', 'None')

                md += f"| **{field_label}** | {value_shown} | {hidden_missing} |\n"

            md += "\n"

        # Decoded parameters (collapsible with button)
        decoded_params = sample.get('decoded_parameters', {})
        if decoded_params:
            md += "<details>\n"
            md += "<summary><strong>📋 View Decoded Transaction Parameters</strong> (click to expand)</summary>\n\n"
            md += "```python\n"  # Python syntax highlighting for key: value pairs

            # Always show native value first (even if 0)
            native_value = sample.get('native_value', '0')
            md += f"native ETH sent: {native_value} wei\n"

            # Then show function parameters
            for param_name, param_value in decoded_params.items():
                md += f"{param_name}: {param_value}\n"
            md += "```\n\n"
            md += "</details>\n\n"

    return md


def _format_overall_assessment(assessment: Dict, recommendations: Dict) -> str:
    """Format the Overall Assessment section."""
    md = "### 6️⃣ Overall Assessment\n\n"

    # Coverage score and security risk table
    coverage = assessment.get('coverage_score', {})
    security = assessment.get('security_risk', {})

    coverage_score = coverage.get('score', 0)
    coverage_explanation = coverage.get('explanation', 'N/A')

    risk_level = security.get('level', 'unknown')
    risk_reasoning = security.get('reasoning', 'N/A')
    risk_emoji = _risk_emoji(risk_level)

    md += "| Metric | Score/Rating | Explanation |\n"
    md += "|--------|--------------|-------------|\n"
    md += f"| **Coverage Score** | {coverage_score}/10 | {coverage_explanation} |\n"
    md += f"| **Security Risk** | {risk_emoji} {risk_level.title()} | {risk_reasoning} |\n"
    md += "\n"

    # Key Recommendations (from shared recommendations object)
    fixes = recommendations.get('fixes', [])
    spec_limitations = recommendations.get('spec_limitations', [])
    optional_improvements = recommendations.get('optional_improvements', [])

    md += "#### 💡 Key Recommendations\n\n"

    has_any = any([fixes, spec_limitations, optional_improvements])

    if not has_any:
        md += "**No additional recommendations.**\n\n"
    else:
        # Fixes
        for fix in fixes:
            title = fix.get('title', 'Fix')
            description = fix.get('description', '')
            md += f"- **Fix:** {title} - {description}\n"

            code_snippet = fix.get('code_snippet')
            if code_snippet:
                md += _format_code_snippet(code_snippet)

        # Spec limitations
        for lim in spec_limitations:
            param = lim.get('parameter', 'Parameter')
            explanation = lim.get('explanation', '')
            md += f"- **Spec Limitation:** {param} - {explanation}\n"

        # Optional improvements
        for opt in optional_improvements:
            title = opt.get('title', 'Improvement')
            description = opt.get('description', '')
            prefix = "(Optional):"
            if title.lower().startswith('optional'):
                prefix = "(Optional)"
            md += f"- **{prefix}** {title} - {description}\n"

            code_snippet = opt.get('code_snippet')
            if code_snippet:
                md += _format_code_snippet(code_snippet)

        optional_snippets = recommendations.get('suggested_code_snippets_for_optional_improvements') or []
        if optional_snippets:
            md += "\n**Suggested code snippets for optional improvements:**\n\n"
            for snippet in optional_snippets:
                desc = snippet.get('description', 'Optional improvement')
                md += f"- {desc}\n"

                for key, value in snippet.items():
                    if key == 'description':
                        continue
                    label = key.replace('_', ' ').title()
                    md += f"  - {label}:\n"
                    md += _format_code_snippet(value)

        md += "\n"

    return md


# ============================================================================
# Public API
# ============================================================================

def format_audit_reports(report_data: Dict) -> tuple[str, str]:
    """
    Format both critical and detailed reports from JSON data.

    This is the main entry point for formatting AI-generated JSON into
    markdown reports.

    Args:
        report_data: Unified JSON object with all report data:
            {
                "function_signature": str,
                "selector": str,
                "erc7730_format": dict,
                "critical_issues": list,
                "recommendations": dict,
                "intent_analysis": dict,
                "missing_parameters": list,
                "display_issues": list,
                "transaction_samples": list,
                "overall_assessment": dict
            }

    Returns:
        Tuple of (critical_markdown, detailed_markdown)
    """
    try:
        # Both reports use the same unified data structure
        critical_markdown = format_critical_report(report_data)
        detailed_markdown = format_detailed_report(report_data)

        return critical_markdown, detailed_markdown

    except KeyError as e:
        logger.error(f"Missing required field in report data: {e}")
        error_msg = f"Error: Missing required field {e}\n\n"
        return error_msg, error_msg
    except Exception as e:
        logger.error(f"Error formatting audit reports: {e}")
        error_msg = f"Error formatting reports: {str(e)}\n\n"
        return error_msg, error_msg
