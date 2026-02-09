"""Structured models used by the analyzer audit pipeline."""

from dataclasses import dataclass
from typing import Dict, List, Literal, Optional

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
    field_to_add: Optional[str] = None       # JSON string
    changes_to_make: Optional[str] = None    # JSON string
    full_example: Optional[str] = None       # JSON string


class Fix(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    description: str
    code_snippet: Optional[CodeSnippet] = None


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
    code_snippet: Optional[CodeSnippet] = None


class Recommendations(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fixes: List[Fix] = Field(default_factory=list)
    spec_limitations: List[SpecLimitation] = Field(default_factory=list)
    optional_improvements: List[OptionalImprovement] = Field(default_factory=list)


class IntentAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    declared_intent: str
    assessment: str
    spelling_errors: List[str] = Field(default_factory=list)


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
    user_intent: List[UserIntentField] = Field(default_factory=list)


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
    critical_issues: List[CriticalIssue] = Field(default_factory=list)
    recommendations: Recommendations
    intent_analysis: IntentAnalysis
    missing_parameters: List[MissingParameter] = Field(default_factory=list)
    display_issues: List[DisplayIssue] = Field(default_factory=list)
    transaction_samples: List[TxSample] = Field(default_factory=list)
    overall_assessment: OverallAssessment


@dataclass
class AuditTask:
    """
    Holds all pre-processed data needed for an audit API call.
    This allows separating preparation from execution for batch processing.
    """
    selector: str
    function_signature: str
    decoded_transactions: List[Dict]
    erc7730_format: Dict
    source_code: Optional[Dict]
    use_smart_referencing: bool
    erc4626_context: Optional[Dict]
    erc20_context: Optional[Dict]
    # Pre-computed payload (built during preparation)
    audit_payload: Optional[Dict] = None
    optimization_note: Optional[str] = None


@dataclass
class AuditResult:
    """
    Holds the result of an audit API call.
    """
    selector: str
    function_signature: str
    critical_report: str
    detailed_report: str
    report_data: Dict
    success: bool
    error: Optional[str] = None

