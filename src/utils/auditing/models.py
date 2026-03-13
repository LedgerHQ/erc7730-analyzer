"""Structured models used by the analyzer audit pipeline."""

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["high", "medium", "low"]
RiskLevel = Literal["high", "medium", "low"]


class CriticalIssueDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    what_descriptor_shows: str
    what_actually_happens: str
    why_critical: str
    evidence: str


class CriticalIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    issue: str
    details: CriticalIssueDetails


class CodeSnippet(BaseModel):
    """
    Code snippet containing JSON strings (not objects).
    These are descriptor modifications as minified JSON strings.
    Using strings avoids OpenAI's additionalProperties schema restriction.
    """

    model_config = ConfigDict(extra="forbid")
    field_to_add: str | None = None  # JSON string
    changes_to_make: str | None = None  # JSON string
    full_example: str | None = None  # JSON string


class Fix(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    description: str
    code_snippet: CodeSnippet | None = None


class SpecLimitation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    parameter: str
    explanation: str
    impact: str
    detected_pattern: str


class OptionalImprovement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    description: str
    code_snippet: CodeSnippet | None = None


class Recommendations(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fixes: list[Fix] = Field(default_factory=list)
    spec_limitations: list[SpecLimitation] = Field(default_factory=list)
    optional_improvements: list[OptionalImprovement] = Field(default_factory=list)


class IntentAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    declared_intent: str
    assessment: str
    spelling_errors: list[str] = Field(default_factory=list)


class MissingParameter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    parameter: str
    importance: str
    risk_level: RiskLevel


class DisplayIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    description: str
    severity: Severity


class UserIntentField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field_label: str
    value_shown: str
    hidden_missing: str


class TxSample(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transaction_hash: str
    user_intent: list[UserIntentField] = Field(default_factory=list)


class CoverageScore(BaseModel):
    model_config = ConfigDict(extra="forbid")
    score: int
    explanation: str


class SecurityRisk(BaseModel):
    model_config = ConfigDict(extra="forbid")
    level: RiskLevel
    reasoning: str


class OverallAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    coverage_score: CoverageScore
    security_risk: SecurityRisk


class AuditReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    function_signature: str
    selector: str
    critical_issues: list[CriticalIssue] = Field(default_factory=list)
    recommendations: Recommendations
    intent_analysis: IntentAnalysis
    missing_parameters: list[MissingParameter] = Field(default_factory=list)
    display_issues: list[DisplayIssue] = Field(default_factory=list)
    transaction_samples: list[TxSample] = Field(default_factory=list)
    overall_assessment: OverallAssessment


class ToolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: Literal[
        "get_related_source_context",
        "search_cached_source",
        "get_other_selector_descriptor",
        "get_previous_selector_analysis",
        "get_external_contract_source_context",
        "anvil_read_storage",
        "anvil_call_view",
    ]
    rationale: str
    arguments_json: str


class ValidatorChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["accepted", "rejected", "modified", "added"]
    subject: str
    explanation: str


class PrimaryAuditorOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["need_tools", "ready"]
    summary: str
    tool_requests: list[ToolRequest] = Field(default_factory=list)
    draft_report: AuditReport | None = None


class ValidatorOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["need_tools", "ready"]
    summary: str
    changes: list[ValidatorChange] = Field(default_factory=list)
    tool_requests: list[ToolRequest] = Field(default_factory=list)
    validated_report: AuditReport | None = None


@dataclass
class AuditTask:
    """
    Holds all pre-processed data needed for an audit API call.
    This allows separating preparation from execution for batch processing.
    """

    selector: str
    function_signature: str
    decoded_transactions: list[dict]
    erc7730_format: dict
    source_code: dict | None
    use_smart_referencing: bool
    erc4626_context: dict | None
    erc20_context: dict | None
    descriptor_context: dict | None
    source_resolution: dict | None
    analysis_mode: str
    # Pre-computed payload (built during preparation)
    audit_payload: dict | None = None
    optimization_note: str | None = None
    tool_context: dict[str, Any] | None = None
    # List of {"tx_hash": str, "screenshots": [str, ...]} per transaction
    screenshot_data: list[dict[str, Any]] | None = None
    llm_model: str = "gpt-5.4"
    llm_reasoning_effort: str = "high"


@dataclass
class AuditResult:
    """
    Holds the result of an audit API call.
    """

    selector: str
    function_signature: str
    critical_report: str
    detailed_report: str
    report_data: dict
    success: bool
    error: str | None = None
