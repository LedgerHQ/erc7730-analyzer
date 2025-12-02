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

        # Prefer text before "**Your analysis:**"
        analysis_split = re.split(r'\*\*Your analysis:\*\*', section_text, flags=re.IGNORECASE)
        pre_analysis_text = analysis_split[0]
        extracted = _extract_issue_bullets(pre_analysis_text)

        # Fallback: include entire section (for legacy formats) if nothing found
        if not extracted:
            extracted = _extract_issue_bullets(section_text)

        critical.extend(extracted)

    # Extract recommendations (lines starting with - under "**Recommendations:**")
    rec_section = re.search(
        r'\*\*Recommendations:\*\*(.*?)(?=$)',
        audit_report,
        re.DOTALL | re.IGNORECASE
    )

    if rec_section:
        for line in rec_section.group(1).split('\n'):
            line = line.strip()
            # Skip empty lines
            if not line:
                continue
            # Skip markdown separators (---, - ---, etc.)
            if re.match(r'^[-*]+\s*[-*]*\s*$', line):
                continue
            # Extract bullet points
            if line.startswith('-'):
                rec_text = re.sub(r'^[-*]\s+', '', line).strip()
                # Remove bold markdown wrapper if present
                rec_text = re.sub(r'^\*\*(.*)\*\*$', r'\1', rec_text)
                if rec_text:
                    recommendations.append(rec_text)

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

            # Categorize by severity (no historical txs is a critical warning)
            has_ai_critical = len(critical_issues_from_ai) > 0

            if has_ai_critical:
                critical_issues_list.append(issue_data)
            else:
                # Always add a critical for no historical transactions
                issue_data['critical_issues'] = ['No historical transactions found for analysis']
                critical_issues_list.append(issue_data)

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

        # Add ERC-7730 format definition (collapsible) with expanded refs
        report += "<details>\n<summary><b>📋 ERC-7730 Format Definition</b></summary>\n\n"
        report += "```json\n"
        # Expand format to include referenced definitions and constants
        selector_format = selector_data.get('erc7730_format', {})
        full_erc7730 = results.get('erc7730_full', {})
        expanded_format = expand_erc7730_format_with_refs(selector_format, full_erc7730)
        report += json.dumps(expanded_format, indent=2)
        report += "\n```\n\n</details>\n\n"

        # Add source code section (collapsible) - only if there are critical issues
        audit_report_detailed = selector_data.get('audit_report_detailed', '')
        if not audit_report_detailed:
            audit_report_detailed = selector_data.get('audit_report', '')

        has_critical_issues = False
        if audit_report_detailed:
            critical_issues_from_ai = extract_critical_issues(audit_report_detailed)
            has_critical_issues = len(critical_issues_from_ai) > 0

        if has_critical_issues:
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

        func_data = {
            'selector': selector,
            'function_name': function_name,
            'function_sig': function_sig,
            'erc7730_format': selector_data.get('erc7730_format', {}),
            'contract_address': selector_data.get('contract_address', 'N/A'),
            'chain_id': selector_data.get('chain_id', 'N/A')
        }

        if audit_report_critical:
            # Parse FIRST REPORT section for critical issues and recommendations
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
            for issue in func['critical_issues']:
                # Add bullet point formatting
                report += f"- {issue}\n"

            report += "\n"
        else:
            # No critical issues
            report += "### ✅ No Critical Issues\n\n"
            report += "No critical issues found.\n\n"

        # Recommendations (always show, even when no critical issues)
        if func['recommendations']:
            report += "### 💡 Recommendations\n\n"
            for rec in func['recommendations']:
                # Add bullet point formatting
                report += f"- {rec}\n"

            report += "\n"

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
