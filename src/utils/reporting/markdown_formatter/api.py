"""Public formatting API combining critical and detailed markdown outputs."""

import logging
from typing import Dict

from .critical import format_critical_report
from .detailed import format_detailed_report

logger = logging.getLogger(__name__)

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

