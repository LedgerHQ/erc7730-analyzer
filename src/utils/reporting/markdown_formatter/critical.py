"""Critical report markdown rendering."""

import json
import logging
from typing import Dict

from pydantic import BaseModel

from .helpers import _format_code_snippet

logger = logging.getLogger(__name__)

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
                    md += "<br>\n\n"  # Add visual spacing after collapsible section
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
