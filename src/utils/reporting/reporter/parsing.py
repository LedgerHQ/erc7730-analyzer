"""Regex/text parsing helpers for legacy markdown report sections."""

import re
from typing import List

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

