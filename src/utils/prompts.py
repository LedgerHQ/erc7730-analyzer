"""
AI prompt generation for ERC-7730 audit reports.

This module handles generating prompts and calling OpenAI for audit report generation.
Supports both synchronous and asynchronous (batch) API calls for improved performance.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from functools import partial
from importlib import resources
from typing import Callable, Dict, List, Literal, Optional

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field

from utils import audit_rules

logger = logging.getLogger(__name__)

Severity = Literal["high", "medium", "low"]
RiskLevel = Literal["high", "medium", "low"]

read_rule: Callable[[str], str] = partial(resources.read_text, audit_rules)


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


# Placeholder - will be built after get_* functions are defined
SYSTEM_INSTRUCTIONS = None

# Load audit rules that are always used in full (not optimized)
def load_validation_rules() -> Dict:
    """Load validation rules from JSON file."""
    return json.loads(read_rule('validation_rules.json'))

def load_critical_issues() -> Dict:
    """Load critical issues criteria from JSON file."""
    return json.loads(read_rule('critical_issues.json'))

def load_recommendations() -> Dict:
    """Load recommendations format guidelines from JSON file."""
    return json.loads(read_rule('recommendations.json'))

def load_spec_limitations() -> Dict:
    """Load spec limitations guidelines from JSON file."""
    return json.loads(read_rule('spec_limitations.json'))

def load_display_issues() -> Dict:
    """Load display issues guidelines from JSON file."""
    return json.loads(read_rule('display_issues.json'))

# Cache these files to avoid reloading on every call
_VALIDATION_RULES = None
_CRITICAL_ISSUES = None
_RECOMMENDATIONS = None
_SPEC_LIMITATIONS = None
_DISPLAY_ISSUES = None

def get_validation_rules() -> Dict:
    """Get cached validation rules."""
    global _VALIDATION_RULES
    if _VALIDATION_RULES is None:
        _VALIDATION_RULES = load_validation_rules()
    return _VALIDATION_RULES

def get_critical_issues() -> Dict:
    """Get cached critical issues criteria."""
    global _CRITICAL_ISSUES
    if _CRITICAL_ISSUES is None:
        _CRITICAL_ISSUES = load_critical_issues()
    return _CRITICAL_ISSUES

def get_recommendations() -> Dict:
    """Get cached recommendations format guidelines."""
    global _RECOMMENDATIONS
    if _RECOMMENDATIONS is None:
        _RECOMMENDATIONS = load_recommendations()
    return _RECOMMENDATIONS

def get_spec_limitations() -> Dict:
    """Get cached spec limitations guidelines."""
    global _SPEC_LIMITATIONS
    if _SPEC_LIMITATIONS is None:
        _SPEC_LIMITATIONS = load_spec_limitations()
    return _SPEC_LIMITATIONS

def get_display_issues() -> Dict:
    """Get cached display issues guidelines."""
    global _DISPLAY_ISSUES
    if _DISPLAY_ISSUES is None:
        _DISPLAY_ISSUES = load_display_issues()
    return _DISPLAY_ISSUES


def build_system_instructions() -> str:
    """
    Build comprehensive system instructions with all static audit rules.
    This enables prompt caching - the system message stays constant across all selectors.

    Uses deterministic JSON serialization (sort_keys=True, separators) to ensure
    byte-for-byte stability for OpenAI's prompt caching.
    """
    # Load the FULL format specification (no optimization)
    format_spec = json.loads(read_rule('erc7730_format_reference.json'))

    validation_rules = get_validation_rules()
    critical_issues = get_critical_issues()
    recommendations = get_recommendations()
    spec_limitations = get_spec_limitations()
    display_issues = get_display_issues()

    # Deterministic JSON serialization for stable caching
    # sort_keys=True ensures consistent key ordering
    # separators=(",", ":") ensures compact, consistent formatting
    json_opts = {"sort_keys": True, "separators": (",", ":"), "ensure_ascii": False}

    return f"""You are a clear signing security auditor for ERC-7730 metadata.
**Goal:** Ensure users see all CRITICAL information they need BEFORE signing.

**What is ERC-7730?**
ERC-7730 is a standard for displaying blockchain transaction parameters in human-readable form on hardware wallets (like Ledger).

**Contract Languages:**
Supports both Solidity and Vyper contracts. Vyper uses decorators (@external, @internal, @view, @payable), Solidity uses keywords (public, external, internal, private).

---

**KEY CONCEPTS:**

**Swap Functions:**
- ONLY show: First amount IN + final amount OUT
- DO NOT show: Intermediate hops, intermediate tokens
- Approvals in swaps are normal - DO NOT flag unless function is approve()/permit()

**File Structure:**
- Includes are pre-merged - all $ref point to merged definitions
- All definitions, constants, formats are available in the provided format

**Transaction Decoding:**
- Most transactions are automatically decoded from raw calldata
- If a transaction includes "_raw_fallback", it contains:
  - "_raw_fallback.raw_calldata": The original hex calldata
  - "_raw_fallback.function_abi": The function ABI for decoding
  - "_raw_fallback.note": Explanation (complex types detected OR decoding failed)
- You may use the decoded parameters directly in most cases
- Only reference _raw_fallback if:
  1. Decoded values look suspicious or malformed
  2. You need to verify complex nested structures
  3. The note indicates decoding failed
- If present, _raw_fallback is provided for verification only - decoded parameters are still the primary data source

---

**ERC-7730 FORMAT SPECIFICATION:**

```json
{json.dumps(format_spec, **json_opts)}
```

---

**CRITICAL ISSUES CRITERIA:**

```json
{json.dumps(critical_issues, **json_opts)}
```

**Summary:**
- {critical_issues.get('definition', 'Critical issues prevent users from making informed decisions')}
- Review all {len(critical_issues.get('critical_criteria', []))} criteria
- Native ETH handling (criterion #8) has 4 cases

---

**VALIDATION RULES:**

```json
{json.dumps(validation_rules, **json_opts)}
```

**Key:**
- CRITICAL: {validation_rules.get('critical_validation', {}).get('critical_definition', 'Misleading or hidden information')}
- When in doubt, DO NOT mark as critical

---

**RECOMMENDATIONS FORMAT:**

```json
{json.dumps(recommendations, **json_opts)}
```

---

**SPEC LIMITATIONS:**

```json
{json.dumps(spec_limitations, **json_opts)}
```

---

**DISPLAY ISSUES:**

```json
{json.dumps(display_issues, **json_opts)}
```

---

**OUTPUT REQUIREMENTS:**

Return valid JSON matching AuditReport schema.

**Rules:**
1. Critical issues: FIXABLE only, with detailed evidence
2. Recommendations.fixes: Split into "description" (text) and "code_snippet" fields
   - code_snippet fields (field_to_add, changes_to_make, full_example) MUST be valid JSON strings (minified), not objects
   - Example: {{"field_to_add": "{{\\"display\\":{{\\"formats\\":[...]}}}}"}}
3. Spec limitations: Include all 4 parts (parameter, explanation, impact, detected_pattern)
4. Transaction samples: Limit to 3, use actual hashes from provided data
5. Use receipt logs to verify actual token transfers
6. Missing parameters: Only if medium/high risk AND not in excluded array
""".strip()


# Build and cache system instructions at module load (after get_* functions defined)
SYSTEM_INSTRUCTIONS = build_system_instructions()


# ============================================================================
# ASYNC BATCH PROCESSING
# ============================================================================
# Note: Old synchronous generate_clear_signing_audit() has been removed.
# All processing now uses the async batch API below for better performance.

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


def prepare_audit_task(
    selector: str,
    decoded_transactions: List[Dict],
    erc7730_format: Dict,
    function_signature: str,
    source_code: Dict = None,
    use_smart_referencing: bool = True,
    erc4626_context: Dict = None,
    erc20_context: Dict = None,
    protocol_name: str = None
) -> AuditTask:
    """
    Prepare an audit task with ONLY dynamic data for optimal prompt caching.
    Static rules are in SYSTEM_INSTRUCTIONS and cached by OpenAI.

    Args:
        selector: Function selector
        decoded_transactions: List of decoded transactions with receipt logs
        erc7730_format: ERC-7730 format definition for this selector
        function_signature: Function signature
        source_code: Optional dictionary with extracted source code
        use_smart_referencing: Whether to use smart rule referencing
        erc4626_context: Optional ERC4626 vault context
        erc20_context: Optional ERC20 token context
        protocol_name: Optional protocol name from descriptor ($id, owner, or legalname)

    Returns:
        AuditTask with minimal payload (only dynamic data)
    """
    # Build minimal payload with ONLY dynamic data
    # Static rules (validation_rules, critical_issues, etc.) are in SYSTEM_INSTRUCTIONS
    # NOTE: We include ALL source code fields (docstrings, libraries, parent_functions, etc.)
    # because they provide critical context for accurate analysis
    audit_payload = {
        "function_signature": function_signature,
        "selector": selector,
        "erc7730_format": erc7730_format,
        "decoded_transactions": decoded_transactions if decoded_transactions else [],  # Empty list if no txs
        "source_code": source_code if source_code else {},  # Include ALL source code fields
        "erc4626_context": erc4626_context if erc4626_context else {},
        "erc20_context": erc20_context if erc20_context else {},
    }

    # Add protocol_name only if it exists (optional field)
    if protocol_name:
        audit_payload["protocol_name"] = protocol_name

    return AuditTask(
        selector=selector,
        function_signature=function_signature,
        decoded_transactions=decoded_transactions,
        erc7730_format=erc7730_format,
        source_code=source_code,
        use_smart_referencing=use_smart_referencing,
        erc4626_context=erc4626_context,
        erc20_context=erc20_context,
        audit_payload=audit_payload,
        optimization_note=None  # Not needed anymore
    )


async def generate_clear_signing_audit_async(
    task: AuditTask,
    client: AsyncOpenAI,
    semaphore: asyncio.Semaphore,
    max_retries: int = 3
) -> AuditResult:
    """
    Async version of generate_clear_signing_audit with retry logic.
    Uses a semaphore to limit concurrent API calls.

    Args:
        task: Pre-prepared AuditTask with payload
        client: AsyncOpenAI client (shared across all calls)
        semaphore: Semaphore to limit concurrency
        max_retries: Maximum number of retry attempts (default: 3)

    Returns:
        AuditResult with the API response or error
    """
    async with semaphore:
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                if attempt == 0:
                    logger.info(f"[ASYNC] Starting API call for selector {task.selector}")
                else:
                    logger.warning(f"[ASYNC] Retry {attempt}/{max_retries} for selector {task.selector}")

                PROMPT_CACHE_KEY = "erc7730_audit_v1"

                # Deterministic JSON for user payload (ensures cache hits)
                user_payload = json.dumps(
                    task.audit_payload,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False
                )

                response = await client.responses.parse(
                    model="gpt-5.2",
                    input=[
                        {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                        {"role": "user", "content": user_payload}
                    ],
                    text_format=AuditReport,
                    reasoning={"effort": "medium"},
                    text={"verbosity": "low"},
                    store=False,
                    prompt_cache_key=PROMPT_CACHE_KEY
                )

                # Log successful response with usage stats
                logger.info(f"[ASYNC] ✅ Received response for {task.selector}")
                if hasattr(response, 'usage') and response.usage:
                    usage = response.usage
                    # Extract cached tokens from input_tokens_details
                    cached_tokens = 0
                    if hasattr(usage, 'input_tokens_details') and usage.input_tokens_details:
                        cached_tokens = getattr(usage.input_tokens_details, 'cached_tokens', 0)

                    # Extract reasoning tokens from output_tokens_details
                    reasoning_tokens = 0
                    if hasattr(usage, 'output_tokens_details') and usage.output_tokens_details:
                        reasoning_tokens = getattr(usage.output_tokens_details, 'reasoning_tokens', 0)

                    logger.info(f"[ASYNC]   Input tokens: {getattr(usage, 'input_tokens', 0):,}")
                    logger.info(f"[ASYNC]   Cached tokens: {cached_tokens:,}")
                    logger.info(f"[ASYNC]   Output tokens: {getattr(usage, 'output_tokens', 0):,}")
                    if reasoning_tokens > 0:
                        logger.info(f"[ASYNC]   Reasoning tokens: {reasoning_tokens:,}")
                    logger.info(f"[ASYNC]   Total tokens: {getattr(usage, 'total_tokens', 0):,}")

                report_data = response.output_parsed.model_dump()

                # Force key identifiers back into the structured output
                report_data["function_signature"] = task.function_signature
                report_data["selector"] = task.selector
                report_data["erc7730_format"] = task.erc7730_format

                # Enrich transaction samples with actual decoded data
                if 'transaction_samples' in report_data and task.decoded_transactions:
                    for sample in report_data['transaction_samples']:
                        tx_hash = sample.get('transaction_hash', '')
                        matching_tx = next(
                            (tx for tx in task.decoded_transactions if tx.get('hash') == tx_hash),
                            None
                        )
                        if matching_tx:
                            sample['native_value'] = matching_tx.get('value', '0')
                            sample['decoded_parameters'] = matching_tx.get('decoded_input', {})

                # Format using markdown_formatter
                from .markdown_formatter import format_audit_reports
                critical_report, detailed_report = format_audit_reports(report_data)

                return AuditResult(
                    selector=task.selector,
                    function_signature=task.function_signature,
                    critical_report=critical_report,
                    detailed_report=detailed_report,
                    report_data=report_data,
                    success=True
                )

            except Exception as e:
                last_error = e
                error_type = type(e).__name__

                # Detailed error logging
                logger.error(f"[ASYNC] Attempt {attempt + 1} failed for {task.selector}")
                logger.error(f"[ASYNC]   Error Type: {error_type}")
                logger.error(f"[ASYNC]   Error Message: {str(e)}")

                # Log additional details based on error type
                if hasattr(e, 'status_code'):
                    logger.error(f"[ASYNC]   HTTP Status Code: {e.status_code}")
                if hasattr(e, 'response'):
                    logger.error(f"[ASYNC]   Response: {e.response}")
                if hasattr(e, 'body'):
                    logger.error(f"[ASYNC]   Response Body: {e.body}")

                # Log request details for debugging
                logger.error(f"[ASYNC]   Payload size: ~{len(user_payload):,} chars")
                logger.error(f"[ASYNC]   Model: gpt-5.2")
                logger.error(f"[ASYNC]   Transactions in payload: {len(task.decoded_transactions or [])}")

                # Log stack trace for non-network errors
                import traceback
                if error_type not in ['ConnectionError', 'Timeout', 'TimeoutError', 'APIConnectionError']:
                    logger.error(f"[ASYNC]   Stack trace:\n{traceback.format_exc()}")

                # If this is not the last attempt, wait before retrying with exponential backoff
                if attempt < max_retries:
                    wait_time = min(2 ** attempt, 30)  # Exponential backoff, max 30s
                    logger.info(f"[ASYNC] Waiting {wait_time}s before retry...")
                    await asyncio.sleep(wait_time)
                else:
                    # All retries exhausted
                    logger.error(f"[ASYNC] ❌ All {max_retries + 1} attempts failed for {task.selector}")
                    logger.error(f"[ASYNC]   Final error: {error_type} - {str(e)}")

        # If we get here, all retries failed
        error_msg = f"Error generating audit after {max_retries + 1} attempts: {str(last_error)}"
        return AuditResult(
            selector=task.selector,
            function_signature=task.function_signature,
            critical_report=error_msg,
            detailed_report=error_msg,
            report_data={},
            success=False,
            error=str(last_error)
        )


async def generate_clear_signing_audits_batch_async(
    tasks: List[AuditTask],
    max_concurrent: int = 6,
    max_retries: int = 3
) -> List[AuditResult]:
    """
    Execute multiple audit API calls concurrently with retry logic.

    Args:
        tasks: List of pre-prepared AuditTasks
        max_concurrent: Maximum number of concurrent API calls (default: 10)
        max_retries: Maximum number of retry attempts per task (default: 3)

    Returns:
        List of AuditResults in the same order as input tasks
    """
    if not tasks:
        return []

    import time
    start_time = time.time()

    logger.info(f"[BATCH] ═══════════════════════════════════════════════════════")
    logger.info(f"[BATCH] Starting batch processing of {len(tasks)} audit tasks")
    logger.info(f"[BATCH] Max concurrent calls: {max_concurrent}")
    logger.info(f"[BATCH] Max retries per task: {max_retries}")
    logger.info(f"[BATCH] ═══════════════════════════════════════════════════════")

    # Use async context manager to properly manage client resources
    async with AsyncOpenAI() as client:
        semaphore = asyncio.Semaphore(max_concurrent)

        # Create coroutines for all tasks
        coroutines = [
            generate_clear_signing_audit_async(task, client, semaphore, max_retries)
            for task in tasks
        ]

        # Execute all concurrently and gather results
        results = await asyncio.gather(*coroutines, return_exceptions=True)

    # Convert any exceptions to AuditResult with error
    final_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"[BATCH] Task {i} raised unexpected exception: {result}")
            final_results.append(AuditResult(
                selector=tasks[i].selector,
                function_signature=tasks[i].function_signature,
                critical_report=f"Error: {str(result)}",
                detailed_report=f"Error: {str(result)}",
                report_data={},
                success=False,
                error=str(result)
            ))
        else:
            final_results.append(result)

    # Log detailed summary
    elapsed_time = time.time() - start_time
    successful = sum(1 for r in final_results if r.success)
    failed = len(final_results) - successful

    logger.info(f"[BATCH] ═══════════════════════════════════════════════════════")
    logger.info(f"[BATCH] Batch processing completed in {elapsed_time:.1f}s")
    logger.info(f"[BATCH] ✅ Successful: {successful}/{len(tasks)} ({successful/len(tasks)*100:.1f}%)")
    logger.info(f"[BATCH] ❌ Failed: {failed}/{len(tasks)} ({failed/len(tasks)*100:.1f}%)")

    if successful > 0:
        logger.info(f"[BATCH] Average time per successful task: {elapsed_time/successful:.1f}s")

    if failed > 0:
        logger.warning(f"[BATCH] ⚠️  Failed selectors and errors:")
        for r in final_results:
            if not r.success:
                logger.warning(f"[BATCH]   • {r.selector}: {r.error}")

    logger.info(f"[BATCH] ═══════════════════════════════════════════════════════")

    return final_results


def generate_clear_signing_audits_batch(
    tasks: List[AuditTask],
    max_concurrent: int = 6,
    max_retries: int = 3
) -> List[AuditResult]:
    """
    Synchronous wrapper for batch processing with retry logic.
    Runs the async batch function using asyncio.run().

    Args:
        tasks: List of pre-prepared AuditTasks
        max_concurrent: Maximum number of concurrent API calls (default: 10)
        max_retries: Maximum number of retry attempts per task (default: 3)

    Returns:
        List of AuditResults in the same order as input tasks
    """
    return asyncio.run(generate_clear_signing_audits_batch_async(tasks, max_concurrent, max_retries))
