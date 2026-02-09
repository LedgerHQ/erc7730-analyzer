"""Top-level markdown/json report generators."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from .formatting import (
    _format_text_with_json_blocks,
    _render_critical_issue,
    _render_recommendations_from_json,
    format_source_code_section,
)
from .expansion import expand_erc7730_format_with_refs
from .parsing import (
    extract_coverage_score,
    extract_critical_issues,
    extract_display_issues,
    extract_missing_parameters,
    extract_recommendations,
    extract_risk_level,
    extract_second_report,
    parse_first_report,
)

logger = logging.getLogger(__name__)

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

        report += f"| `{issue['function_name']}` | `{issue['selector']}` | {severity} | {quick_desc} | [View](#{issue['selector']}) |\n"

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
        # Use selector as header for GitHub-compatible anchor links
        report += f"## {selector}\n\n"
        report += f"### {function_name}\n\n"
        report += f"**Signature:** `{function_sig}`\n\n"
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
        expanded_format = expand_erc7730_format_with_refs(selector_format, full_erc7730, selector)
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
            link = f"[View](#{func['selector']})"
        else:
            status = "✅ No Critical Issues"
            link = f"[View](#{func['selector']})"  # Link to section even if no issues

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
    # Use selector as header for GitHub-compatible anchor links
    for func in all_functions:
        if func.get('has_critical'):
            report += f"## {func['selector']}\n\n"
            report += f"### 🔴 {func['function_sig']}\n\n"
        else:
            report += f"## {func['selector']}\n\n"
            report += f"### ✅ {func['function_sig']}\n\n"

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
        expanded_format = expand_erc7730_format_with_refs(selector_format, full_erc7730, func['selector'])
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
