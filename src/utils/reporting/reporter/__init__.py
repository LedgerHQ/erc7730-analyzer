"""Report generation package split by concern."""

from .expansion import expand_erc7730_format_with_refs
from .generators import generate_criticals_report, generate_summary_file, save_json_results
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

__all__ = [
    "expand_erc7730_format_with_refs",
    "generate_criticals_report",
    "generate_summary_file",
    "save_json_results",
    "extract_coverage_score",
    "extract_critical_issues",
    "extract_display_issues",
    "extract_missing_parameters",
    "extract_recommendations",
    "extract_risk_level",
    "extract_second_report",
    "parse_first_report",
]
