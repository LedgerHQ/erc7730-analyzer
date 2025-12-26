"""
Report generation for ERC-7730 analyzer.

This module handles generating markdown and JSON reports from analysis results.
"""

import json
import re
import logging
from typing import Dict, Any, List
from pathlib import Path
from datetime import datetime
import json as json_lib  # avoid shadowing json module import

logger = logging.getLogger(__name__)


def extract_risk_level(audit_report: str) -> str:
    """Extract risk level from AI audit report."""
    high_pattern = r'(🔴|High)'
    medium_pattern = r'(🟡|Medium)'
    low_pattern = r'(🟢|Low)'

    if re.search(high_pattern, audit_report, re.IGNORECASE):
        return 'High'
    elif re.search(medium_pattern, audit_report, re.IGNORECASE):
        return 'Medium'
    elif re.search(low_pattern, audit_report, re.IGNORECASE):
        return 'Low'
    return 'Unknown'


def extract_coverage_score(audit_report: str) -> str:
    """Extract coverage score from AI audit report."""
    match = re.search(r'Coverage Score[:\s]*(\d+/10)', audit_report, re.IGNORECASE)
    if match:
        return match.group(1)
    return 'N/A'


def expand_erc7730_format_with_refs(selector_format: Dict[str, Any], full_erc7730: Dict[str, Any]) -> Dict[str, Any]:
    """
    Expand ERC-7730 format to include referenced definitions, constants, and enums.

    Args:
        selector_format: The format definition for a specific selector
        full_erc7730: The complete ERC-7730 data with metadata and display sections

    Returns:
        Expanded format with inline definitions, constants, and enums
    """
    result = {}

    # Collect referenced definitions
    referenced_defs = set()
    referenced_constants = set()
    referenced_enums = set()

    def find_refs(obj):
        """Recursively find $ref references in the format"""
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key == '$ref' and isinstance(value, str):
                    # Extract definition name from $.display.definitions._minAmountOut
                    if value.startswith('$.display.definitions.'):
                        def_name = value.replace('$.display.definitions.', '')
                        referenced_defs.add(def_name)
                    # Extract enum name from $.metadata.enums.interestRateMode
                    elif value.startswith('$.metadata.enums.'):
                        enum_name = value.replace('$.metadata.enums.', '')
                        referenced_enums.add(enum_name)
                elif isinstance(value, (dict, list)):
                    find_refs(value)
        elif isinstance(obj, list):
            for item in obj:
                find_refs(item)

    def find_constant_refs(obj):
        """Recursively find references to $.metadata.constants"""
        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(value, str) and '$.metadata.constants.' in value:
                    # Extract constant name
                    const_name = value.replace('$.metadata.constants.', '')
                    referenced_constants.add(const_name)
                elif isinstance(value, (dict, list)):
                    find_constant_refs(value)
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, str) and '$.metadata.constants.' in item:
                    const_name = item.replace('$.metadata.constants.', '')
                    referenced_constants.add(const_name)
                else:
                    find_constant_refs(item)

    # Find all references
    find_refs(selector_format)
    find_constant_refs(selector_format)

    # Also check definitions for enum and constant references
    if referenced_defs and 'display' in full_erc7730 and 'definitions' in full_erc7730['display']:
        for def_name in referenced_defs:
            if def_name in full_erc7730['display']['definitions']:
                # Check for both enum and constant references in definitions
                find_refs(full_erc7730['display']['definitions'][def_name])
                find_constant_refs(full_erc7730['display']['definitions'][def_name])

    # Build result with metadata (constants and enums) if any are referenced
    if referenced_constants or referenced_enums:
        result['metadata'] = {}

        # Add referenced constants
        if referenced_constants and 'metadata' in full_erc7730 and 'constants' in full_erc7730['metadata']:
            result['metadata']['constants'] = {}
            for const_name in referenced_constants:
                if const_name in full_erc7730['metadata']['constants']:
                    result['metadata']['constants'][const_name] = full_erc7730['metadata']['constants'][const_name]

        # Add referenced enums
        if referenced_enums and 'metadata' in full_erc7730 and 'enums' in full_erc7730['metadata']:
            result['metadata']['enums'] = {}
            for enum_name in referenced_enums:
                if enum_name in full_erc7730['metadata']['enums']:
                    result['metadata']['enums'][enum_name] = full_erc7730['metadata']['enums'][enum_name]

    # Build result with display definitions if any are referenced
    if referenced_defs:
        result['display'] = {'definitions': {}}
        if 'display' in full_erc7730 and 'definitions' in full_erc7730['display']:
            for def_name in referenced_defs:
                if def_name in full_erc7730['display']['definitions']:
                    result['display']['definitions'][def_name] = full_erc7730['display']['definitions'][def_name]

    # Add the selector format itself
    result['format'] = selector_format

    return result


def extract_second_report(audit_report: str) -> str:
    """
    Extract SECOND REPORT section (detailed analysis) from audit report.

    Returns:
        str: The SECOND REPORT section content
    """
    # Extract SECOND REPORT section (skip "SECOND REPORT:" header line)
    second_report_match = re.search(
        r'SECOND REPORT:.*?\n\n(.*)',
        audit_report,
        re.DOTALL | re.IGNORECASE
    )

    if second_report_match:
        return second_report_match.group(1)

    # Fallback: if no sections found, return entire report
    return audit_report


def parse_first_report(audit_report: str) -> tuple:
    """
    Extract critical issues and recommendations from critical report.

    The critical report has the format:
    ## Critical Issues for `function_signature`
    **Selector:** `selector`
    ---
    <details>...</details>
    ---
    ### **Issues Found:**
    - Issue 1
    - Issue 2
    [or "✅ No critical issues found"]
    ---
    **Recommendations:**
    - Recommendation 1

    Returns:
        tuple: (critical_issues: list, recommendations: list)
    """
    critical = []
    recommendations = []

    def _extract_issue_bullets(section_text: str) -> List[str]:
        """Helper to pull bullet lines from a section."""
        issues = []
        for line in section_text.split('\n'):
            line = line.strip()
            # Stop when we hit the "Your analysis:" marker
            if line.lower().startswith('**your analysis'):
                break
            # Skip empty lines (don't break, just continue)
            if not line:
                continue
            # Skip markdown separators (---, - ---, etc.)
            if re.match(r'^[-*]+\s*[-*]*\s*$', line):
                continue
            # Extract bullet points
            if line.startswith(('-', '*')):
                issue_text = re.sub(r'^[-*]\s+', '', line).strip()
                # Remove bold markdown wrapper if present
                issue_text = re.sub(r'^\*\*(.*)\*\*$', r'\1', issue_text)
                if issue_text:
                    issues.append(issue_text)
        return issues

    # Extract critical issues under "### **Issues Found:**"
    critical_section = re.search(
        r'###\s*\*\*Issues Found:\*\*(.*?)(?=###|\*\*Recommendations:\*\*|---|$)',
        audit_report,
        re.DOTALL | re.IGNORECASE
    )

    if critical_section:
        section_text = critical_section.group(1)

        # Remove content inside <details> tags (new structured format)
        # This prevents extracting Evidence bullets as separate issues
        section_without_details = re.sub(r'<details>.*?</details>', '', section_text, flags=re.DOTALL)

        # Prefer text before "**Your analysis:**"
        analysis_split = re.split(r'\*\*Your analysis:\*\*', section_without_details, flags=re.IGNORECASE)
        pre_analysis_text = analysis_split[0]
        extracted = _extract_issue_bullets(pre_analysis_text)

        # Fallback: include entire section (for legacy formats) if nothing found
        if not extracted:
            extracted = _extract_issue_bullets(section_without_details)

        critical.extend(extracted)

    # Extract recommendations (multi-line bullets under "### **Recommendations:**")
    # Use ### to match section header, not inline recommendations
    # Stop at duplicate "Issues Found" section (AI bug) or end of string
    rec_section = re.search(
        r'###\s*\*\*Recommendations:\*\*(.*?)(?=###\s*\*\*Issues Found:\*\*|$)',
        audit_report,
        re.DOTALL | re.IGNORECASE
    )

    if rec_section:
        # Parse multi-line bullet points
        current_bullet = []
        lines = rec_section.group(1).split('\n')

        for line in lines:
            stripped = line.strip()

            # Skip markdown separators (---, - ---, etc.)
            if re.match(r'^[-*]+\s*[-*]*\s*$', stripped):
                continue

            # New bullet point starts
            if stripped.startswith('-'):
                # Save previous bullet if any
                if current_bullet:
                    bullet_text = '\n'.join(current_bullet)
                    recommendations.append(bullet_text)

                # Start new bullet (remove the leading dash but preserve markdown formatting)
                rec_text = re.sub(r'^[-*]\s+', '', stripped).strip()
                current_bullet = [rec_text] if rec_text else []

            # Continuation of current bullet (indented content or regular lines)
            elif stripped and current_bullet:
                current_bullet.append(line.rstrip())  # Keep original indentation

        # Don't forget the last bullet
        if current_bullet:
            bullet_text = '\n'.join(current_bullet)
            recommendations.append(bullet_text)

    return critical, recommendations


def extract_critical_issues(audit_report: str) -> list:
    """Extract critical issues from SECOND REPORT section (for detailed report)."""
    critical = []
    crit_section = re.search(r'2️⃣ Critical Issues(.*?)(?=3️⃣|---)', audit_report, re.DOTALL | re.IGNORECASE)
    if crit_section:
        section_text = crit_section.group(1)

        # First check if the section explicitly says "No critical issues found"
        no_issue_patterns = [
            r'✅\s*No critical issues',
            r'✅\s*no critical issues',
            r'No critical issues found',
            r'no critical issues found'
        ]

        for pattern in no_issue_patterns:
            if re.search(pattern, section_text, re.IGNORECASE):
                return []  # Return empty list if no critical issues

        # Only extract bullet points if NOT preceded by "No critical issues"
        # Look for actual critical issue markers
        if '🔴' in section_text or 'CRITICAL:' in section_text.upper():
            for line in section_text.split('\n'):
                line = line.strip()
                if line.startswith('-') or line.startswith('*'):
                    issue_text = re.sub(r'^[-*]\s+', '', line).strip()

                    # Skip explanation bullets (they typically mention "Receipt logs", "There is no evidence", etc.)
                    explanation_indicators = [
                        'receipt logs',
                        'there is no evidence',
                        'no evidence',
                        'sentinel/internal',
                        'implementation details',
                        'may alter runtime',
                    ]

                    is_explanation = any(indicator in issue_text.lower() for indicator in explanation_indicators)

                    if issue_text and not is_explanation:
                        critical.append(issue_text)

    return critical


def extract_missing_parameters(audit_report: str) -> list:
    """Extract missing parameters from AI audit report."""
    missing = []
    matches = re.findall(r'\|\s*`([^`]+)`\s*\|[^|]+\|[^|]+\|', audit_report)
    if matches:
        missing.extend(matches)
    return missing


def extract_display_issues(audit_report: str) -> list:
    """Extract display issues from AI audit report."""
    display = []
    display_section = re.search(r'4️⃣ Display Issues(.*?)(?=5️⃣|---)', audit_report, re.DOTALL | re.IGNORECASE)
    if display_section:
        section_text = display_section.group(1)
        for line in section_text.split('\n'):
            line = line.strip()
            if line.startswith('-') or line.startswith('*'):
                issue_text = re.sub(r'^[-*]\s+', '', line).strip()
                no_issue_indicators = [
                    '✅',
                    'no display issues',
                    'none observed',
                    'if none:',
                    'none:',
                    'not observed',
                ]
                is_no_issue = any(indicator in issue_text.lower() for indicator in no_issue_indicators)

                if issue_text and not is_no_issue:
                    display.append(issue_text)
    return display


def extract_recommendations(audit_report: str) -> list:
    """Extract recommendations from AI audit report."""
    recommendations = []
    rec_section = re.search(r'Key Recommendations[:\s]*(.*?)(?=---|\Z)', audit_report, re.DOTALL | re.IGNORECASE)
    if rec_section:
        bullets = re.findall(r'[-*]\s+(.+)', rec_section.group(1))
        recommendations.extend([b.strip() for b in bullets if b.strip()])
    return recommendations[:3]


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
    return line.count('{') - line.count('}') + line.count('[') - line.count(']')


def _format_text_with_json_blocks(text: str) -> str:
    """
    Look for JSON-like blocks in freeform text and render them as fenced code blocks.
    """
    if not text:
        return ""

    lines = text.splitlines()
    output: List[str] = []
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
        if stripped.startswith('{') or stripped.startswith('['):
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
        brace_pos = line.find('{')
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


def _render_recommendations_from_json(recs: Dict[str, Any]) -> str:
    """
    Format recommendations from structured JSON into markdown, preserving
    code snippets and optional improvements.
    """
    if not recs:
        return ""

    lines: List[str] = []

    # Fixes
    for fix in recs.get('fixes', []):
        title = fix.get('title', 'Fix')
        description = fix.get('description', '')
        formatted_desc = _format_text_with_json_blocks(description)
        lines.append(f"- **{title}:** {formatted_desc}")
        if fix.get('code_snippet'):
            lines.append(_format_code_snippet(fix['code_snippet']))

    # Spec limitations
    for lim in recs.get('spec_limitations', []):
        param = lim.get('parameter', 'Parameter')
        explanation = lim.get('explanation', '')
        impact = lim.get('impact', '')
        detected = lim.get('detected_pattern')
        line = f"- **{param} cannot be clear signed:** {explanation}"
        if impact:
            line += f" **Why this matters:** {impact}"
        if detected:
            line += f" **Detected pattern:** {detected}"
        lines.append(line)

    # Optional improvements
    for opt in recs.get('optional_improvements', []):
        title = opt.get('title', 'Improvement')
        description = opt.get('description', '')
        prefix = "(Optional) "
        if title.lower().startswith('optional'):
            prefix = ""
        formatted_desc = _format_text_with_json_blocks(description)
        lines.append(f"- **{prefix}{title}:** {formatted_desc}")
        if opt.get('code_snippet'):
            lines.append(_format_code_snippet(opt['code_snippet']))

    # Additional suggested snippets for optional improvements
    optional_snippets = recs.get('suggested_code_snippets_for_optional_improvements') or []
    if optional_snippets:
        lines.append("**Suggested code snippets for optional improvements:**")
        for snippet in optional_snippets:
            desc = snippet.get('description', 'Optional improvement')
            lines.append(f"- {desc}")
            for key, value in snippet.items():
                if key == 'description':
                    continue
                label = key.replace('_', ' ').title()
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

    summary = issue_obj.get('issue', f'Issue {index}')
    details = issue_obj.get('details', {})
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

    md_nonlocal: List[str] = []
    add_detail("What descriptor shows", "what_descriptor_shows")
    add_detail("What actually happens", "what_actually_happens")
    add_detail("Why this is critical", "why_critical")
    add_detail("Evidence", "evidence")

    md += "\n".join(md_nonlocal) + "\n"
    md += "</details>\n\n"  # Extra newline for spacing between issues
    return md


def format_source_code_section(source_code: Dict) -> str:
    """
    Format source code dictionary into a markdown collapsible section.

    Args:
        source_code: Dictionary with extracted source code components

    Returns:
        Formatted markdown string for source code section
    """
    if not source_code or not source_code.get('function'):
        return ""

    code_block = ""

    # Add custom types if available (HIGHEST PRIORITY - needed for bitpacked params)
    if source_code.get('custom_types'):
        code_block += "// Custom types:\n"
        for custom_type in source_code['custom_types']:
            code_block += f"{custom_type}\n"
        code_block += "\n"

    # Add using statements if available
    if source_code.get('using_statements'):
        code_block += "// Using statements:\n"
        for using_stmt in source_code['using_statements']:
            code_block += f"{using_stmt}\n"
        code_block += "\n"

    # Add function docstring if available
    if source_code.get('function_docstring'):
        code_block += f"// Docstring:\n{source_code['function_docstring']}\n\n"

    # Add constants if available
    if source_code.get('constants'):
        code_block += "// Constants:\n"
        for constant in source_code['constants']:
            code_block += f"{constant}\n"
        code_block += "\n"

    # Add structs if available
    if source_code.get('structs'):
        code_block += "// Structs:\n"
        for struct in source_code['structs']:
            code_block += f"{struct}\n"
        code_block += "\n"

    # Add enums if available
    if source_code.get('enums'):
        code_block += "// Enums:\n"
        for enum in source_code['enums']:
            code_block += f"{enum}\n"
        code_block += "\n"

    # Add main function
    code_block += "// Main function:\n"
    code_block += source_code['function']

    # Add internal functions if available
    if source_code.get('internal_functions'):
        code_block += "\n\n// Internal functions called:\n"
        for internal_func in source_code['internal_functions']:
            if internal_func.get('docstring'):
                code_block += f"{internal_func['docstring']}\n"
            code_block += f"{internal_func['body']}\n\n"

    # Add parent functions (from super. calls) if available
    if source_code.get('parent_functions'):
        code_block += "\n\n// Parent contract implementations (from super. calls):\n"
        for parent_func in source_code['parent_functions']:
            parent_name = parent_func.get('parent_contract', 'Unknown')
            func_name = parent_func.get('function_name', 'unknown')
            code_block += f"// From {parent_name}.{func_name}():\n"
            code_block += f"{parent_func['body']}\n\n"

    # Add libraries if available (LOWEST PRIORITY - shown last)
    if source_code.get('libraries'):
        code_block += "\n// Libraries:\n"
        for library in source_code['libraries']:
            code_block += f"{library}\n\n"

    # Add truncation warning if needed
    if source_code.get('truncated'):
        code_block += "\n// ⚠️ Note: Code was truncated to fit within line limit\n"

    return code_block


def generate_summary_file(results: Dict, summary_file: Path):
    """
    Generate a single comprehensive report file with summary table and detailed sections.

    Args:
        results: Analysis results dictionary
        summary_file: Path to summary file
    """
    # Get contract info
    deployments = results.get('deployments', [])
    context_id = results.get('context', {}).get('$id', 'N/A')

    # Get unique chain IDs
    chain_ids = sorted(set(d['chainId'] for d in deployments))
    chain_ids_str = ', '.join(str(cid) for cid in chain_ids)

    # Generate timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    report = f"""# 📊 Clear Signing Audit Report

**Generated:** {timestamp}

**Contract ID:** {context_id}

**Total Deployments Analyzed:** {len(deployments)}

**Chain IDs:** {chain_ids_str}

---

## Summary Table

"""

    critical_issues_list = []
    major_issues_list = []
    minor_issues_list = []
    no_issues_list = []

    for selector, selector_data in results.get('selectors', {}).items():
        function_name = selector_data.get('function_name', 'unknown')
        audit_file = f"audit_{selector}_{function_name}.md"

        # Get detailed report for extraction (with backward compatibility)
        audit_report_detailed = selector_data.get('audit_report_detailed', '')
        if not audit_report_detailed:
            audit_report_detailed = selector_data.get('audit_report', '')

        # Extract coverage and missing parameters info
        transactions = selector_data.get('transactions', [])

        # Process selectors with OR without transactions
        if transactions:
            tx = transactions[0]
            decoded_input = tx.get('decoded_input', {})
            erc7730_format = selector_data.get('erc7730_format', {})
            erc7730_fields = {field.get('path', '').replace('params.', ''): field
                             for field in (erc7730_format.get('fields') or [])}
            excluded_fields = [e.replace('params.', '') for e in (erc7730_format.get('excluded') or [])]

            total_params = len(decoded_input)
            shown_count = len([p for p in decoded_input.keys() if p in erc7730_fields])
            excluded_count = len([p for p in decoded_input.keys() if p in excluded_fields])
            missing_count = total_params - shown_count - excluded_count
            coverage_pct = (shown_count / total_params * 100) if total_params > 0 else 0

            missing_params = [p for p in decoded_input.keys()
                            if p not in erc7730_fields and p not in excluded_fields]

            # Extract key information from AI audit report (using detailed report)
            if audit_report_detailed:
                risk_level = extract_risk_level(audit_report_detailed)
                coverage_score = extract_coverage_score(audit_report_detailed)
                critical_issues_from_ai = extract_critical_issues(audit_report_detailed)
                ai_missing_params = extract_missing_parameters(audit_report_detailed)
                display_issues_from_ai = extract_display_issues(audit_report_detailed)
                recommendations = extract_recommendations(audit_report_detailed)
            else:
                risk_level = 'Unknown'
                coverage_score = 'N/A'
                critical_issues_from_ai = []
                ai_missing_params = []
                display_issues_from_ai = []
                recommendations = []

            issue_data = {
                'selector': selector,
                'function_name': function_name,
                'audit_file': audit_file,
                'coverage_pct': coverage_pct,
                'missing_count': missing_count,
                'missing_params': missing_params,
                'shown_count': shown_count,
                'excluded_count': excluded_count,
                'total_params': total_params,
                'risk_level': risk_level,
                'coverage_score': coverage_score,
                'critical_issues': critical_issues_from_ai,
                'ai_missing_params': ai_missing_params,
                'display_issues': display_issues_from_ai,
                'recommendations': recommendations
            }

            # Categorize by severity
            has_ai_critical = len(critical_issues_from_ai) > 0
            has_missing_params = len(ai_missing_params) > 0

            if has_ai_critical:
                critical_issues_list.append(issue_data)
            elif has_missing_params or len(display_issues_from_ai) > 2:
                major_issues_list.append(issue_data)
            elif len(display_issues_from_ai) > 0 or coverage_pct < 100:
                minor_issues_list.append(issue_data)
            else:
                no_issues_list.append(issue_data)
        else:
            # Selector without transactions - still include in report
            # Extract information from AI audit report only
            if audit_report_detailed:
                risk_level = extract_risk_level(audit_report_detailed)
                coverage_score = extract_coverage_score(audit_report_detailed)
                critical_issues_from_ai = extract_critical_issues(audit_report_detailed)
                ai_missing_params = extract_missing_parameters(audit_report_detailed)
                display_issues_from_ai = extract_display_issues(audit_report_detailed)
                recommendations = extract_recommendations(audit_report_detailed)
            else:
                risk_level = 'Unknown'
                coverage_score = 'N/A'
                critical_issues_from_ai = []
                ai_missing_params = []
                display_issues_from_ai = []
                recommendations = []

            # Provide a default warning so no-transaction selectors surface as a minor issue
            if not display_issues_from_ai:
                display_issues_from_ai = ["⚠️ No historical transactions - static analysis only"]

            issue_data = {
                'selector': selector,
                'function_name': function_name,
                'audit_file': audit_file,
                'coverage_pct': 0,  # No transactions to calculate coverage
                'missing_count': 0,
                'missing_params': [],
                'shown_count': 0,
                'excluded_count': 0,
                'total_params': 0,
                'risk_level': risk_level,
                'coverage_score': coverage_score,
                'critical_issues': critical_issues_from_ai,
                'ai_missing_params': ai_missing_params,
                'display_issues': display_issues_from_ai,
                'recommendations': recommendations,
                'no_historical_txs': True  # Flag to indicate no transactions
            }

            # Categorize by severity (no historical txs should be a warning, not a critical)
            has_ai_critical = len(critical_issues_from_ai) > 0
            has_missing_params = len(ai_missing_params) > 0
            has_display_issues = len(display_issues_from_ai) > 0

            if has_ai_critical:
                critical_issues_list.append(issue_data)
            elif has_missing_params:
                major_issues_list.append(issue_data)
            elif has_display_issues:
                minor_issues_list.append(issue_data)
            else:
                no_issues_list.append(issue_data)

    # Build summary table
    all_issues = critical_issues_list + major_issues_list + minor_issues_list + no_issues_list

    report += "| Function | Selector | Severity | Issues | Link |\n"
    report += "|----------|----------|----------|--------|------|\n"

    for issue in all_issues:
        has_critical = len(issue['critical_issues']) > 0
        has_missing = len(issue['ai_missing_params']) > 0
        has_display = len(issue['display_issues']) > 0
        no_historical_txs = issue.get('no_historical_txs', False)

        if has_critical:
            severity = "🔴 Critical"
            # Show first issue text instead of "Critical"
            first_issue = issue['critical_issues'][0]
            quick_desc = first_issue[:100] + "..." if len(first_issue) > 100 else first_issue
            # Special handling for no historical transactions
            if no_historical_txs and 'No historical transactions' in first_issue:
                quick_desc = "⚠️ No historical transactions - static analysis only"
        elif has_missing:
            severity = "🟡 Major"
            quick_desc = f"Missing: {', '.join(issue['ai_missing_params'][:2])}"
            if len(issue['ai_missing_params']) > 2:
                quick_desc += f" (+{len(issue['ai_missing_params']) - 2} more)"
        elif has_display:
            severity = "🟢 Minor"
            quick_desc = issue['display_issues'][0][:80] + "..." if len(issue['display_issues'][0]) > 80 else issue['display_issues'][0]
        else:
            severity = "✅ None"
            quick_desc = "No critical issues found"

        report += f"| `{issue['function_name']}` | `{issue['selector']}` | {severity} | {quick_desc} | [View](#selector-{issue['selector'][2:]}) |\n"

    report += "\n---\n\n## 📈 Statistics\n\n"
    report += f"| Metric | Count |\n"
    report += f"|--------|-------|\n"
    report += f"| 🔴 Critical | {len(critical_issues_list)} |\n"
    report += f"| 🟡 Major | {len(major_issues_list)} |\n"
    report += f"| 🟢 Minor | {len(minor_issues_list)} |\n"
    report += f"| ✅ No Issues | {len(no_issues_list)} |\n"
    report += f"| **Total** | **{len(all_issues)}** |\n\n"

    report += "---\n\n# Detailed Analysis\n\n"

    # Add detailed sections for each selector
    for selector, selector_data in results.get('selectors', {}).items():
        function_name = selector_data.get('function_name', 'unknown')
        function_sig = selector_data.get('function_signature', 'N/A')

        contract_addr = selector_data.get('contract_address', 'N/A')
        chain_id = selector_data.get('chain_id', 'N/A')
        report += f"## <a id=\"selector-{selector[2:]}\"></a> {function_name}\n\n"
        report += f"**Selector:** `{selector}` | **Signature:** `{function_sig}`\n\n"
        report += f"**Contract Address:** `{contract_addr}` | **Chain ID:** {chain_id}\n\n"

        # Add ERC4626 context if available
        erc4626_context = results.get('erc4626_context')
        if erc4626_context and erc4626_context.get('is_erc4626_vault'):
            report += "**🏦 ERC4626 Tokenized Vault Detected**\n\n"
            if erc4626_context.get('underlying_token'):
                report += f"- **Underlying Asset (metadata):** `{erc4626_context['underlying_token']}`\n"
            if erc4626_context.get('asset_from_chain'):
                report += f"- **Asset Token (on-chain asset()):** `{erc4626_context['asset_from_chain']}`\n"
            if erc4626_context.get('detection_source'):
                report += f"- **Detection:** {erc4626_context['detection_source']}\n"
            report += "\n"

        # Add ERC-7730 format definition (collapsible) with expanded refs
        report += "<details>\n<summary><b>📋 ERC-7730 Format Definition</b></summary>\n\n"
        report += "```json\n"
        # Expand format to include referenced definitions and constants
        selector_format = selector_data.get('erc7730_format', {})
        full_erc7730 = results.get('erc7730_full', {})
        expanded_format = expand_erc7730_format_with_refs(selector_format, full_erc7730)
        report += json.dumps(expanded_format, indent=2)
        report += "\n```\n\n</details>\n\n"

        # Add source code section (collapsible) - always show if available
        source_code = selector_data.get('source_code')
        if source_code:
            formatted_code = format_source_code_section(source_code)
            if formatted_code:
                report += "<details>\n<summary><b>📝 Source Code</b></summary>\n\n"
                report += "```solidity\n"
                report += formatted_code
                # Ensure there's a newline before closing the code fence
                if not formatted_code.endswith('\n'):
                    report += "\n"
                report += "```\n\n</details>\n\n"

        # Add decoded transaction parameters (collapsible sections per transaction)
        # transactions = selector_data.get('transactions', [])
        # if transactions:
        #     for i, tx in enumerate(transactions, 1):
        #         report += f"#### 📝 Transaction {i}\n\n"
        #         report += "**User Intent (from ERC-7730):**\n\n"
        #         report += "| Field | ✅ User Sees | ❌ Hidden/Missing |\n"
        #         report += "|-------|-------------|-------------------|\n"
        #         report += "| **Label from ERC-7730** | *Formatted value* | *What's not shown* |\n\n"

        #         # Add decoded parameters in collapsible section
        #         decoded_input = tx.get('decoded_input', {})
        #         if decoded_input:
        #             report += "<details>\n"
        #             report += "<summary><strong>📋 View Decoded Transaction Parameters</strong> (click to expand)</summary>\n\n"
        #             report += "```python\n"

        #             for param_name, param_value in decoded_input.items():
        #                 report += f"{param_name}: {param_value}\n"

        #             report += "```\n\n"
        #             report += "</details>\n\n"

        # Add AI audit report (use detailed report directly)
        audit_report_detailed = selector_data.get('audit_report_detailed', '')
        if not audit_report_detailed:
            # Fallback: extract from combined report
            audit_report_content = selector_data.get('audit_report', '')
            if audit_report_content:
                audit_report_detailed = extract_second_report(audit_report_content)

        if audit_report_detailed:
            report += "---\n\n"
            report += audit_report_detailed
            report += "\n\n---\n\n"
        else:
            report += "---\n\n*No audit report available for this selector.*\n\n---\n\n"

    # Write report file
    with open(summary_file, 'w') as f:
        f.write(report)

    logger.info(f"Comprehensive report saved to {summary_file}")


def generate_criticals_report(results: Dict, criticals_file: Path):
    """
    Generate a mini report containing ONLY critical issues and recommendations.

    Args:
        results: Analysis results dictionary
        criticals_file: Path to criticals report file
    """
    # Get contract info
    deployments = results.get('deployments', [])
    context_id = results.get('context', {}).get('$id', 'N/A')

    # Get unique chain IDs
    chain_ids = sorted(set(d['chainId'] for d in deployments))
    chain_ids_str = ', '.join(str(cid) for cid in chain_ids)

    # Generate timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    report = f"""# 🔴 Critical Issues Report

**Generated:** {timestamp}

**Contract ID:** {context_id}

**Chain IDs:** {chain_ids_str}

---

## Critical Issues Summary

"""

    # Collect all functions with critical issues and all functions analyzed
    critical_functions = []
    all_functions = []

    for selector, selector_data in results.get('selectors', {}).items():
        function_name = selector_data.get('function_name', 'unknown')
        function_sig = selector_data.get('function_signature', 'N/A')

        # Get critical report directly (with backward compatibility)
        audit_report_critical = selector_data.get('audit_report_critical', '')
        if not audit_report_critical:
            # Fallback: extract from combined report
            audit_report_critical = selector_data.get('audit_report', '')

        audit_report_json = selector_data.get('audit_report_json')

        func_data = {
            'selector': selector,
            'function_name': function_name,
            'function_sig': function_sig,
            'erc7730_format': selector_data.get('erc7730_format', {}),
            'contract_address': selector_data.get('contract_address', 'N/A'),
            'chain_id': selector_data.get('chain_id', 'N/A'),
            'critical_issues': [],
            'recommendations': [],
            'recommendations_rendered': "",
            'critical_issues_rendered': ""
        }

        if audit_report_json:
            # Prefer structured JSON when available
            crits = audit_report_json.get('critical_issues', [])
            func_data['critical_issues'] = [
                c.get('issue', c) if isinstance(c, dict) else str(c) for c in crits
            ]
            rendered_criticals = []
            for idx, crit in enumerate(crits, 1):
                rendered_criticals.append(_render_critical_issue(crit, idx))
            func_data['critical_issues_rendered'] = "\n".join(rendered_criticals)

            func_data['recommendations_rendered'] = _render_recommendations_from_json(
                audit_report_json.get('recommendations', {})
            )
            func_data['recommendations'] = []  # keep legacy field empty
            func_data['has_critical'] = len(func_data['critical_issues']) > 0

            all_functions.append(func_data)
            if func_data['has_critical']:
                critical_functions.append(func_data)

        elif audit_report_critical:
            # Parse FIRST REPORT section for critical issues and recommendations (legacy)
            critical_issues, recommendations = parse_first_report(audit_report_critical)

            func_data['critical_issues'] = critical_issues
            func_data['recommendations'] = recommendations
            func_data['has_critical'] = len(critical_issues) > 0

            all_functions.append(func_data)

            if critical_issues:  # Only include in critical_functions if there are actual critical issues
                critical_functions.append(func_data)

    # Summary table showing all functions with their status
    report += "| Function | Selector | Status | Link |\n"
    report += "|----------|----------|--------|------|\n"

    for func in all_functions:
        if func.get('has_critical'):
            # Show first critical issue instead of count
            first_issue = func['critical_issues'][0]
            status_text = first_issue[:80] + "..." if len(first_issue) > 80 else first_issue
            status = f"🔴 {status_text}"
            link = f"[View](#critical-{func['selector'][2:]})"
        else:
            status = "✅ No Critical Issues"
            link = f"[View](#critical-{func['selector'][2:]})"  # Link to section even if no issues

        report += f"| `{func['function_name']}` | `{func['selector']}` | {status} | {link} |\n"

    report += "\n---\n\n"

    # Show detailed sections for ALL functions
    report += f"## 📋 Detailed Analysis\n\n"

    if critical_functions:
        report += f"Found **{len(critical_functions)} function(s)** with critical issues that require immediate attention.\n\n"
    else:
        report += "All analyzed functions appear to properly display transaction parameters to users.\n\n"

    report += "---\n\n"

    # Detailed sections for ALL functions (with and without critical issues)
    for func in all_functions:
        if func.get('has_critical'):
            report += f"## <a id=\"critical-{func['selector'][2:]}\"></a> 🔴 {func['function_sig']}\n\n"
        else:
            report += f"## <a id=\"critical-{func['selector'][2:]}\"></a> ✅ {func['function_sig']}\n\n"

        report += f"**Selector:** `{func['selector']}`\n\n"
        report += f"**Contract Address:** `{func['contract_address']}` | **Chain ID:** {func['chain_id']}\n\n"

        # Add ERC4626 context if available
        erc4626_context = results.get('erc4626_context')
        if erc4626_context and erc4626_context.get('is_erc4626_vault'):
            report += "**🏦 ERC4626 Tokenized Vault Detected**\n\n"
            if erc4626_context.get('underlying_token'):
                report += f"- **Underlying Asset (metadata):** `{erc4626_context['underlying_token']}`\n"
            if erc4626_context.get('asset_from_chain'):
                report += f"- **Asset Token (on-chain asset()):** `{erc4626_context['asset_from_chain']}`\n"
            if erc4626_context.get('detection_source'):
                report += f"- **Detection:** {erc4626_context['detection_source']}\n"
            report += "\n"

        # Add ERC-7730 Format Definition (collapsible) with expanded refs
        report += "<details>\n<summary><b>📋 ERC-7730 Format Definition</b></summary>\n\n"
        report += "```json\n"
        # Expand format to include referenced definitions and constants
        selector_format = func['erc7730_format']
        full_erc7730 = results.get('erc7730_full', {})
        expanded_format = expand_erc7730_format_with_refs(selector_format, full_erc7730)
        report += json.dumps(expanded_format, indent=2)
        report += "\n```\n\n</details>\n\n"

        # Add source code section (collapsible) - always show, not just for critical issues
        # Get source code from results
        selector_data = results.get('selectors', {}).get(func['selector'], {})
        source_code = selector_data.get('source_code')
        if source_code:
            formatted_code = format_source_code_section(source_code)
            if formatted_code:
                report += "<details>\n<summary><b>📝 Source Code</b></summary>\n\n"
                report += "```solidity\n"
                report += formatted_code
                # Ensure there's a newline before closing the code fence
                if not formatted_code.endswith('\n'):
                    report += "\n"
                report += "```\n\n</details>\n\n"

        if func.get('has_critical'):
            # Critical Issues
            report += "### 🔴 Critical Issues\n\n"
            if func.get('critical_issues_rendered'):
                report += func['critical_issues_rendered'] + "\n"
            else:
                for issue in func['critical_issues']:
                    report += f"- {issue}\n"
                report += "\n"
        else:
            # No critical issues
            report += "### ✅ No Critical Issues\n\n"
            report += "No critical issues found.\n\n"

        # Recommendations (always show, even when no critical issues)
        if func.get('recommendations_rendered'):
            report += "### 💡 Recommendations\n\n"
            report += func['recommendations_rendered']
            report += "\n"
        elif func['recommendations']:
            report += "### 💡 Recommendations\n\n"
            for rec in func['recommendations']:
                # Multi-line recommendations are already formatted with newlines
                # Just add the leading dash and preserve all internal formatting
                report += f"- {rec}\n\n"

        report += "---\n\n"

    # Write report file
    with open(criticals_file, 'w') as f:
        f.write(report)

    logger.info(f"Critical issues report saved to {criticals_file}")


def save_json_results(results: Dict[str, Any], json_output: Path):
    """
    Save analysis results to JSON file.

    Args:
        results: Analysis results dictionary
        json_output: Path to JSON output file
    """
    logger.info(f"Saving JSON results to {json_output}")
    with open(json_output, 'w') as f:
        json.dump(results, f, indent=2)
