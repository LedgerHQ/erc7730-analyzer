"""
AI prompt generation for ERC-7730 audit reports.

This module handles generating prompts and calling OpenAI for audit report generation.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple
from openai import OpenAI

logger = logging.getLogger(__name__)

# Load audit rules that are always used in full (not optimized)
def load_validation_rules() -> Dict:
    """Load validation rules from JSON file."""
    rules_path = Path(__file__).parent / "audit_rules" / "validation_rules.json"
    with open(rules_path, 'r') as f:
        return json.load(f)

def load_critical_issues() -> Dict:
    """Load critical issues criteria from JSON file."""
    critical_path = Path(__file__).parent / "audit_rules" / "critical_issues.json"
    with open(critical_path, 'r') as f:
        return json.load(f)

def load_recommendations() -> Dict:
    """Load recommendations format guidelines from JSON file."""
    recs_path = Path(__file__).parent / "audit_rules" / "recommendations.json"
    with open(recs_path, 'r') as f:
        return json.load(f)

def load_spec_limitations() -> Dict:
    """Load spec limitations guidelines from JSON file."""
    spec_lim_path = Path(__file__).parent / "audit_rules" / "spec_limitations.json"
    with open(spec_lim_path, 'r') as f:
        return json.load(f)

def load_display_issues() -> Dict:
    """Load display issues guidelines from JSON file."""
    display_path = Path(__file__).parent / "audit_rules" / "display_issues.json"
    with open(display_path, 'r') as f:
        return json.load(f)

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


def generate_clear_signing_audit(
    selector: str,
    decoded_transactions: List[Dict],
    erc7730_format: Dict,
    function_signature: str,
    source_code: Dict = None,
    use_smart_referencing: bool = True
) -> Tuple[str, str, Dict]:
    """
    Use AI to generate a clear signing audit report comparing decoded transactions
    with ERC-7730 format definitions.

    Args:
        selector: Function selector
        decoded_transactions: List of decoded transactions with receipt logs
        erc7730_format: ERC-7730 format definition for this selector
        function_signature: Function signature
        source_code: Optional dictionary with extracted source code

    Returns:
        Tuple of (critical_report, detailed_report) as markdown strings
    """
    try:
        client = OpenAI()
        logger.info(f"Generating clear signing audit for selector {selector}")

        # Prepare source code section if available
        source_code_section = ""
        if source_code and source_code.get('function'):
            source_code_section = "\n\n**Contract Source Code:**\n\n"
            source_code_section += "You have access to the actual contract source code (Solidity or Vyper). Use this to understand the function's true behavior, identify hidden logic, and verify that ERC-7730 metadata accurately represents what the contract does.\n\n"
            source_code_section += "**Note:** Vyper contracts use decorators (@external, @internal, @view, @payable) for function visibility instead of Solidity keywords. Vyper does not have structs or enums in the same way as Solidity.\n\n"

            if source_code.get('function_docstring'):
                source_code_section += f"```\n{source_code['function_docstring']}\n```\n\n"

            if source_code.get('custom_types'):
                source_code_section += "**Custom Types:**\n```\n"
                source_code_section += "\n".join(source_code['custom_types'])
                source_code_section += "\n```\n\n"

            if source_code.get('using_statements'):
                source_code_section += "**Using Statements:**\n```\n"
                source_code_section += "\n".join(source_code['using_statements'])
                source_code_section += "\n```\n\n"

            if source_code.get('structs'):
                source_code_section += "**Structs used:**\n```\n"
                source_code_section += "\n\n".join(source_code['structs'])
                source_code_section += "\n```\n\n"

            if source_code.get('enums'):
                source_code_section += "**Enums used:**\n```\n"
                source_code_section += "\n\n".join(source_code['enums'])
                source_code_section += "\n```\n\n"

            if source_code.get('constants'):
                source_code_section += "**Constants used:**\n```\n"
                source_code_section += "\n".join(source_code['constants'])
                source_code_section += "\n```\n\n"

            source_code_section += "**Main Function:**\n```\n"
            source_code_section += source_code['function']
            source_code_section += "\n```\n\n"

            if source_code.get('internal_functions'):
                source_code_section += "**Internal Functions Called:**\n"
                for internal_func_data in source_code['internal_functions']:
                    # Add docstring if available
                    if internal_func_data.get('docstring'):
                        source_code_section += f"```\n{internal_func_data['docstring']}\n```\n\n"
                    # Add function body
                    source_code_section += f"```\n{internal_func_data['body']}\n```\n\n"

            if source_code.get('libraries'):
                source_code_section += "**Libraries used:**\n"
                for library in source_code['libraries']:
                    source_code_section += f"```\n{library}\n```\n\n"

            if source_code.get('truncated'):
                source_code_section += "⚠️ **Note:** Source code was truncated to fit within limits. Focus on the main function.\n\n"

        # Extract enums from ERC-7730 descriptor for context
        erc7730_enums_section = "\n\n**ERC-7730 Enum Definitions (from descriptor):**\n\n"
        if erc7730_format.get('metadata', {}).get('enums'):
            erc7730_enums_section += "The descriptor defines these enum mappings for displaying parameters:\n\n"
            for enum_name, enum_values in erc7730_format['metadata']['enums'].items():
                erc7730_enums_section += f"**{enum_name}:**\n```json\n"
                erc7730_enums_section += json.dumps(enum_values, indent=2)
                erc7730_enums_section += "\n```\n\n"
        else:
            erc7730_enums_section += "⚠️ **No enum definitions found in descriptor.** If any fields use `\"format\": \"enum\"`, the $ref will be broken.\n\n"

        # Load optimized format specification (smart optimization applied here)
        from .smart_rules import analyze_descriptor_features, load_optimized_format_spec, format_optimization_note

        descriptor_features = analyze_descriptor_features(erc7730_format)
        format_spec, metadata = load_optimized_format_spec(descriptor_features, use_smart_referencing)

        # Load audit rules directly (always used in full)
        validation_rules = get_validation_rules()
        critical_issues = get_critical_issues()
        recommendations = get_recommendations()
        spec_limitations = get_spec_limitations()
        display_issues = get_display_issues()

        # Format optimization note for prompt
        optimization_note = format_optimization_note(metadata)

        # Prepare the prompt
        prompt = f"""You are a clear signing security auditor for ERC-7730 clear signing metadata. Your job is to ensure users see all CRITICAL information they need BEFORE signing.


**What is ERC-7730?**
ERC-7730 is a standard for displaying blockchain transaction parameters in human-readable form on hardware wallets (like Ledger). The goal is to show users what they're signing WITHOUT overwhelming them.

**Contract Languages Supported:**
This analysis supports both Solidity and Vyper contracts. Vyper uses Python-like syntax with decorators (@external, @internal, @view, @payable) for function visibility, while Solidity uses keywords (public, external, internal, private). The core ERC-7730 validation logic is the same for both languages.

INPUTS:
**Function:** {function_signature}
**Selector:** {selector}{source_code_section}

**ERC-7730 Format Definition:**
```json
{json.dumps(erc7730_format, indent=2)}
```{erc7730_enums_section}

**Decoded Transaction Samples (may be empty):**

Each transaction includes:
- **decoded_input**: Parameters extracted from transaction calldata (what user intended to send)
- **receipt_logs**: Events emitted during transaction execution (what actually happened on-chain)
  - Transfer events show actual token movements
  - Approval events show permission grants
  - Other events show state changes

```json
{json.dumps(decoded_transactions, indent=2)}
```

{f'''**⚠️ NOTE:** No historical transaction data available. Perform the same analysis using the ERC-7730 format and source code, but you cannot verify actual on-chain behavior, receipt logs, or token flows.
''' if not decoded_transactions else '''**Important:** Pay special attention to receipt_logs! They reveal the ACTUAL token transfers and approvals that occurred.
Compare these with what the user sees in ERC-7730 to ensure nothing is hidden or misleading.'''}

---

**IMPORTANT - FILE STRUCTURE:**

The ERC-7730 format you receive has already been preprocessed:
- **Includes are merged**: If the original file had `"includes": "common-file.json"`, the common file has been automatically merged into the format you see
- **All definitions available**: `$.display.definitions.*` references point to definitions that exist in the merged format
- **All constants available**: `$.metadata.constants.*` references point to constants that exist in the merged format
- **All formats available**: Multiple function formats may come from both the main file and included common files

When you see `$ref` references like `$.display.definitions.sendAmount`, you can find the definition in the `display.definitions` section of the format provided. You do NOT need to worry about missing includes.

---

**IMPORTANT ERC-7730 CONCEPTS:**

**Swap Functions - What to Display:**
- **ONLY show**: First amount IN and final amount OUT
- **DO NOT show**: Intermediate swap amounts, intermediate tokens, or intermediate hops
- **WHY**: Users only care about what they send and what they receive, not the routing path
- **Approvals**: Do NOT flag approval events UNLESS the function is specifically `approve()` or `permit()` - swap functions will have approval events as part of their execution, which is normal
- Multi-hop swaps displaying only first/last amounts is CORRECT and should NOT be flagged as missing information

---

**ERC-7730 FORMAT TYPES SPECIFICATION:**

The complete ERC-7730 format specification is loaded from a reference file and provided below:

```json
{json.dumps(format_spec, indent=2)}
```

Use this specification to validate all format types, required/optional parameters, XOR constraints, special paths, array indexing, and type casting rules

**REQUIRED AND EXCLUDED FIELDS:**
- `"required"` array: Lists field paths that SHOULD be displayed to users
- `"excluded"` array: Lists field paths that are intentionally hidden
- **Check**: If a function parameter exists in decoded_input but has NO field formatter AND is NOT in the `excluded` array → This may indicate missing display information (mention in detailed report, not critical unless it's an amount/recipient/token)

---

{optimization_note}

---

The complete criteria for CRITICAL issues are provided below in JSON format:

```json
{json.dumps(critical_issues, indent=2)}
```

**Summary of critical criteria:**
- {critical_issues['definition']}
- {critical_issues['rule']}
- Review all {len(critical_issues['critical_criteria'])} critical criteria above
- Pay special attention to native ETH handling (criterion #8) - it's nuanced and has 4 cases
- Check additional requirements: array indexing validation, can it be fixed, human readability

**VALIDATION RULES:**

The complete validation rules are provided below in JSON format. These define what is CRITICAL vs NOT CRITICAL:

```json
{json.dumps(validation_rules, indent=2)}
```

**Key Points:**
- **CRITICAL DEFINITION**: {validation_rules['critical_validation']['critical_definition']}
- **KEY QUESTION**: {validation_rules['critical_validation']['key_question']}
- Review all `not_critical_patterns` - these are common false positives to avoid
- Review all `spec_limitations` - parameters that cannot be clear signed due to ERC-7730 limitations
- When in doubt, DO NOT flag as critical

---

**RECOMMENDATIONS FORMAT GUIDELINES:**

The complete recommendations format guidelines are provided below in JSON format:

```json
{json.dumps(recommendations, indent=2)}
```

---

**SPEC LIMITATIONS DETECTION:**

The complete spec limitations detection guidelines are provided below in JSON format:

```json
{json.dumps(spec_limitations, indent=2)}
```

---

**DISPLAY ISSUES DETECTION:**

The complete display issues detection guidelines are provided below in JSON format:

```json
{json.dumps(display_issues, indent=2)}
```

---

**OUTPUT FORMAT:**

You MUST output a SINGLE JSON object (no markdown, no extra text before or after). The JSON will be formatted into markdown reports by Python code.

```json
{{
  "function_signature": "{function_signature}",
  "selector": "{selector}",
  "erc7730_format": <the erc7730_format object provided above>,

  "critical_issues": [
    {{
      "issue": "Brief 1-2 sentence summary of what's wrong and user impact",
      "details": {{
        "what_descriptor_shows": "What users currently see in the descriptor",
        "what_actually_happens": "What actually happens in the contract code",
        "why_critical": "Why this misleads users or causes loss",
        "evidence": "Code snippets, transaction examples, or field paths that prove this"
      }}
    }}
  ],

  "recommendations": {{
    "fixes": [
      {{
        "title": "Brief title (e.g., 'Add msg.value display', 'Fix inverted token addresses')",
        "description": "Human-readable explanation of what to change and why. Keep this concise (1-2 sentences). DO NOT embed JSON here.",
        "code_snippet": {{
          "field_to_add": {{"path": "fieldname", "label": "Label", "format": "formatType"}},
          "OR_changes_to_make": {{"field": "amountOut", "change": "tokenPath from 'srcToken' to 'dstToken'"}},
          "OR_full_example": {{"format": {{"fields": [...], "required": [...]}}}}
        }}
      }}
    ],
    "spec_limitations": [
      {{
        "parameter": "Parameter name",
        "explanation": "Why it cannot be clear signed",
        "impact": "Why this matters to users",
        "detected_pattern": "Code pattern detected"
      }}
    ],
    "optional_improvements": [
      {{
        "title": "Brief title",
        "description": "Optional improvement description (1-2 sentences)",
        "code_snippet": {{"field_or_change": "descriptor JSON if applicable"}}
      }}
    ]
  }},

  "intent_analysis": {{
    "declared_intent": "{erc7730_format.get('format', {}).get('intent', 'N/A')}",
    "assessment": "One sentence assessing if intent is accurate and clear",
    "spelling_errors": ["List any spelling/grammar errors found"]
  }},

  "missing_parameters": [
    {{
      "parameter": "parameter_name",
      "importance": "Why it's important",
      "risk_level": "high|medium|low"
    }}
  ],

  "display_issues": [
    {{
      "type": "issue_type",
      "description": "Issue description",
      "severity": "high|medium|low"
    }}
  ],

  "transaction_samples": [
    {{
      "transaction_hash": "0xabc123...",
      "user_intent": [
        {{
          "field_label": "Label from ERC-7730",
          "value_shown": "Actual formatted value from this transaction",
          "hidden_missing": "What's hidden or not shown"
        }}
    }}
  ],

  "overall_assessment": {{
    "coverage_score": {{
      "score": 7,
      "explanation": "Brief reasoning"
    }},
    "security_risk": {{
      "level": "high|medium|low",
      "reasoning": "One sentence why"
    }}
  }}
}}
```

**IMPORTANT RULES:**
1. Output ONLY the JSON (no markdown formatting, no extra text)
2. **Critical issues**:
   - DO NOT include spec limitations here - only fixable issues
   - Each issue must be DETAILED: what's wrong + why critical + supporting evidence
   - Include examples: code snippets, field paths, transaction hashes, specific values
   - Make it easy for a reviewer to understand without reading the whole descriptor
3. **Recommendations.fixes**:
   - Split content into TWO fields: "description" (human explanation) and "code_snippet" (JSON to add/modify)
   - description: Keep concise (1-2 sentences), explain WHAT and WHY, NO embedded JSON
   - code_snippet: Put the actual descriptor JSON here for proper code block formatting
   - Example: description="Add a field to display the recipient address", code_snippet={{"path":"recipient","label":"Recipient","format":"addressName"}}
4. **Spec limitations**: Always include in recommendations.spec_limitations with all 4 parts (parameter, explanation, impact, detected_pattern)
5. **Missing parameters**: Only list if risk is medium/high AND not in excluded array
6. **Transaction samples**: {f"Empty array (no transactions available)" if not decoded_transactions else f"Analyze up to 3 transactions"}
7. Use actual values from the descriptor and transactions provided above

**VALIDATION:**
- critical_issues array: DETAILED descriptions with evidence, no "CRITICAL:" prefix
- recommendations.fixes: Must include exact descriptor code changes to make
- recommendations.spec_limitations: Must include detected_pattern when found in source code
- Be consistent: Same patterns across functions get same assessment

{f"⚠️ **NO HISTORICAL TRANSACTIONS FOUND** - This selector has no transaction history. Set transaction_samples to empty array and add display issue noting this." if not decoded_transactions else ""}"""

        response = client.chat.completions.create(
            model="gpt-5.1",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        logger.info(f"AI raw response {response}")
        json_response = response.choices[0].message.content
        logger.info(f"Successfully received JSON response for {selector}")

        # Parse JSON response
        try:
            report_data = json.loads(json_response)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.error(f"Response content: {json_response[:500]}...")
            raise Exception(f"Invalid JSON from AI: {e}")

        # Enrich transaction samples with actual decoded data
        # The AI provides transaction_hash and user_intent, we add decoded_parameters and native_value
        if 'transaction_samples' in report_data and decoded_transactions:
            for sample in report_data['transaction_samples']:
                tx_hash = sample.get('transaction_hash', '')
                # Find matching transaction in decoded_transactions
                matching_tx = next((tx for tx in decoded_transactions if tx.get('hash') == tx_hash), None)
                if matching_tx:
                    # Add native value (msg.value)
                    sample['native_value'] = matching_tx.get('value', '0')
                    # Add decoded parameters directly from transaction data
                    sample['decoded_parameters'] = matching_tx.get('decoded_input', {})

        # Format using markdown_formatter
        from .markdown_formatter import format_audit_reports

        critical_report, detailed_report = format_audit_reports(report_data)
        logger.info(f"Successfully formatted reports: Critical ({len(critical_report)} chars), Detailed ({len(detailed_report)} chars)")

        # Return both markdown strings and raw structured JSON
        return critical_report, detailed_report, report_data

    except Exception as e:
        logger.error(f"Failed to generate audit report: {e}")
        error_msg = f"Error generating audit: {str(e)}"
        return error_msg, error_msg, {}
