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

# Load ERC-7730 format specification from JSON
def load_format_spec() -> Dict:
    """Load ERC-7730 format specification from JSON file."""
    spec_path = Path(__file__).parent / "audit_rules" / "erc7730_format_reference.json"
    with open(spec_path, 'r') as f:
        return json.load(f)

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
    """Load recommendations format from JSON file."""
    recs_path = Path(__file__).parent / "audit_rules" / "recommendations.json"
    with open(recs_path, 'r') as f:
        return json.load(f)

def load_spec_limitations() -> Dict:
    """Load spec limitations from JSON file."""
    spec_lim_path = Path(__file__).parent / "audit_rules" / "spec_limitations.json"
    with open(spec_lim_path, 'r') as f:
        return json.load(f)

def load_display_issues() -> Dict:
    """Load display issues from JSON file."""
    display_path = Path(__file__).parent / "audit_rules" / "display_issues.json"
    with open(display_path, 'r') as f:
        return json.load(f)

# Cache all JSON files to avoid reloading on every call
_FORMAT_SPEC = None
_VALIDATION_RULES = None
_CRITICAL_ISSUES = None
_RECOMMENDATIONS = None
_SPEC_LIMITATIONS = None
_DISPLAY_ISSUES = None

def get_format_spec() -> Dict:
    """Get cached format specification."""
    global _FORMAT_SPEC
    if _FORMAT_SPEC is None:
        _FORMAT_SPEC = load_format_spec()
    return _FORMAT_SPEC

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
    """Get cached recommendations format."""
    global _RECOMMENDATIONS
    if _RECOMMENDATIONS is None:
        _RECOMMENDATIONS = load_recommendations()
    return _RECOMMENDATIONS

def get_spec_limitations() -> Dict:
    """Get cached spec limitations."""
    global _SPEC_LIMITATIONS
    if _SPEC_LIMITATIONS is None:
        _SPEC_LIMITATIONS = load_spec_limitations()
    return _SPEC_LIMITATIONS

def get_display_issues() -> Dict:
    """Get cached display issues."""
    global _DISPLAY_ISSUES
    if _DISPLAY_ISSUES is None:
        _DISPLAY_ISSUES = load_display_issues()
    return _DISPLAY_ISSUES


def generate_clear_signing_audit(
    selector: str,
    decoded_transactions: List[Dict],
    erc7730_format: Dict,
    function_signature: str,
    source_code: Dict = None
) -> Tuple[str, str]:
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

        # Load all JSON specifications
        format_spec = get_format_spec()
        validation_rules = get_validation_rules()
        critical_issues = get_critical_issues()
        recommendations = get_recommendations()
        spec_limitations = get_spec_limitations()
        display_issues = get_display_issues()

        # Prepare the prompt
        prompt = f"""You are a clear signing security auditor for ERC-7730 clear signing metadata. Your job is to ensure users see all CRITICAL information they need BEFORE signing.


**What is ERC-7730?**
ERC-7730 is a standard for displaying blockchain transaction parameters in human-readable form on hardware wallets (like Ledger). The goal is to show users what they're signing WITHOUT overwhelming them.

**Contract Languages Supported:**
This analysis supports both Solidity and Vyper contracts. Vyper uses Python-like syntax with decorators (@external, @internal, @view, @payable) for function visibility, while Solidity uses keywords (public, external, internal, private). The core ERC-7730 validation logic is the same for both languages.

You MUST produce TWO separate sections in your response:
1. **FIRST REPORT**: CRITICALS ONLY (ultra-strict, terse) - for the mini report
2. **SECOND REPORT**: Full detailed analysis - for the comprehensive report


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

FIRST REPORT: CRITICALS ONLY - BE ULTRA STRICT

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
- **CRITICAL DEFINITION**: {validation_rules['critical_definition']}
- **KEY QUESTION**: {validation_rules['key_question']}
- Review all `not_critical_patterns` - these are common false positives to avoid
- Review all `spec_limitations` - parameters that cannot be clear signed due to ERC-7730 limitations
- When in doubt, DO NOT flag as critical

**CRITICAL REQUIREMENTS:**
1. **Array indexing validation**: When ERC-7730 uses array indexing, verify the index points to actual data relevant to the user (not sentinel values)
2. **Can it be fixed?**: ONLY flag as CRITICAL if the issue EXISTS in function inputs AND can be displayed with ERC-7730 spec AND can be shown in human-readable format
3. **Human readability**: Parameters that can ONLY be shown as incomprehensible raw data (packed bits, liquidity numbers, technical params) are NOT critical to hide

---

**FORMAT FOR FIRST REPORT:**

Output the EXACT markdown structure shown below. Start with the ## header.

## Critical Issues for `{function_signature}`

**Selector:** `{selector}`

---

<details>
<summary><strong>📋 ERC-7730 Format Definition</strong> (click to expand)</summary>

This is the complete ERC-7730 metadata for this selector, including all referenced definitions and constants:

```json
{json.dumps(erc7730_format, indent=2)}
```

</details>

---

### **Issues Found:**

List critical issues directly as bullet points below. Be specific and concise. Do NOT use question format.
Use the exact criteria from the "ONLY flag as CRITICAL if:" section above.

**IMPORTANT - DO NOT include spec limitations here:**
- Parameters that CANNOT be clear signed due to ERC-7730 spec limitations (e.g., bitmask flags) should NOT be listed as critical issues
- Spec limitations go ONLY in the Recommendations section with explanation
- This section is ONLY for issues that CAN be fixed by updating the ERC-7730 descriptor

If NO critical issues exist, write only: "✅ No critical issues found"

**Your analysis:**

[Write your bullet points here]

---

### **Recommendations:**

**Recommendation guidelines are provided in recommendations.json. Key points:**

- **⚠️ ALWAYS INCLUDE THIS SECTION** - Even if no critical issues found!
- **Formatting**: {recommendations['formatting_requirements']['bullet_format']}, {recommendations['formatting_requirements']['complete_sentences']}, {recommendations['formatting_requirements']['end_with_period']}
- **Three types**: Fixes for critical issues, Spec limitations (ALWAYS include), Optional improvements
- **Spec limitations format**: See {len(recommendations['spec_limitations']['common_limitations'])} common limitations in JSON
- **If truly no recommendations**: {recommendations['always_provide_recommendations']['if_truly_no_recommendations']}

Refer to recommendations.json for examples and full formatting requirements.

---

SECOND REPORT: FULL DETAILED ANALYSIS

## 🔍 Clear Signing Audit Report

### 📋 Function: `{function_signature}`

**Selector:** `{selector}`

---

### 1️⃣ Intent Analysis

> **Declared Intent:** *"{erc7730_format.get('intent', 'N/A')}"*

IMPORTANT: Keep the `>` blockquote format above. Then write one sentence assessing if this intent is accurate and clear. Also check for spelling/grammar errors.

---

### 2️⃣ Critical Issues

> 🔴 **CRITICAL** - Issues that could lead to users being deceived or losing funds

IMPORTANT: Keep the `>` blockquote format above.

**CRITICAL ISSUE CRITERIA:**

Use the same critical issues criteria as defined in the first report (see critical_issues.json). The criteria include:
- {len(critical_issues['critical_criteria'])} critical issue types
- Native ETH handling (4 cases)
- Format validation failures
- Missing recipient parameter (3 cases)
- And all other criteria from the critical_issues.json

**DO NOT include spec limitations here:**
- Parameters that CANNOT be clear signed due to ERC-7730 spec limitations (e.g., bitmask flags) should NOT be listed as critical issues
- Spec limitations go in the "Key Recommendations" section under "Overall Assessment" (section 6)
- This section is ONLY for issues that CAN be fixed by updating the ERC-7730 descriptor

{f"⚠️ **NO HISTORICAL TRANSACTIONS FOUND** - This selector has no transaction history. Analysis is based on source code and function signature only. Validation of actual on-chain behavior is not possible without transaction data.\n\n" if not decoded_transactions else ""}

List critical issues as bullet points. If none: **✅ No critical issues found**

---

### 3️⃣ Missing Parameters

> ⚠️ *Parameters present in ABI but NOT shown to users in ERC-7730*

| Parameter | Why It's Important | Risk Level |
|-----------|-------------------|:----------:|
| `parameter_name` | Brief explanation | 🔴 High / 🟡 Medium / 🟢 Low |

If no parameters are missing, write: **✅ All parameters are covered**

---

### 4️⃣ Display Issues

> 🟡 **{display_issues['section_description']}**

**Common display/formatting issues to check:**

{json.dumps([{
    'type': issue['type'],
    'description': issue['description'],
    'severity': issue['severity'],
    'examples': issue.get('examples', []),
    'action': issue['action']
} for issue in display_issues['common_display_issues']], indent=2)}

If none: {display_issues['when_none_found']}

---

### 5️⃣ Transaction Samples - What Users See vs What Actually Happens

Analyze up to 3 transactions (not all 5).

**IMPORTANT:** Do NOT include transaction hash, block, from, or value in your analysis - these are already displayed in the Side-by-Side Comparison section above.

#### 📝 Transaction 1

**User Intent (from ERC-7730):**

| Field | ✅ User Sees | ❌ Hidden/Missing |
|-------|-------------|-------------------|
| **Label from ERC-7730** | *Formatted value* | *What's not shown* |

Add 2-3 rows showing the most important fields.

**Actual Effects (from receipt_logs):**

| Event | Details | Disclosed? |
|-------|---------|:----------:|
| Transfer/Approval | Token, From, To, Amount | ✅ Yes / ❌ No |

Add 2-3 rows showing the most important events.

Repeat for 2-3 more transactions with the same format.

---

### 6️⃣ Overall Assessment

| Metric | Score/Rating | Explanation |
|--------|--------------|-------------|
| **Coverage Score** | X/10 | Brief reasoning |
| **Security Risk** | 🔴 High / 🟡 Medium / 🟢 Low | One sentence why |

#### 💡 Key Recommendations

**Include two types of recommendations:**
1. **Fixes for critical issues** - Specific actionable fixes for issues listed in section 2
2. **Spec limitations** - Parameters that CANNOT be clear signed (DO NOT list these in section 2)

- Recommendation 1 (be specific about how to fix critical issues)
- Recommendation 2 (be specific about parameter additions/corrections)
- Recommendation 3 (if needed)

**IMPORTANT - SPEC LIMITATIONS SECTION:**

{spec_limitations['when_to_include']['rule']}

**Format for spec-limited parameters (always include these 3 parts):**
{json.dumps(spec_limitations['formatting_requirements']['always_include_three_parts'], indent=2)}

**Common spec limitations to detect:**
{json.dumps([{
    'type': lim['type'],
    'description': lim['description'],
    'why_limitation': lim['why_limitation'],
    'examples': lim.get('examples', [])
} for lim in spec_limitations['common_spec_limitations']], indent=2)}

**Example output:**
{spec_limitations['common_spec_limitations'][0]['example_output']}

---

**Use bold, italic, emojis, tables, blockquotes, and horizontal rules to make it visually appealing and easy to scan.**"""

        response = client.chat.completions.create(
            model="gpt-5-mini-2025-08-07",
            messages=[{"role": "user", "content": prompt}]
        )

        full_report = response.choices[0].message.content
        logger.info(f"Successfully generated audit report for {selector}")

        # Split the report based on section headers
        critical_report = ""
        detailed_report = ""

        # Look for the two distinct section markers
        critical_marker = "## Critical Issues for"
        detailed_marker = "## 🔍 Clear Signing Audit Report"

        # Check if AI generated the expected markers
        has_critical_marker = critical_marker in full_report
        has_detailed_marker = detailed_marker in full_report

        if has_critical_marker and has_detailed_marker:
            # Both markers present - normal case
            parts = full_report.split(detailed_marker, 1)
            critical_report = parts[0].strip()
            detailed_report = detailed_marker + "\n\n" + parts[1].strip()
            logger.info(f"Successfully split report: Critical ({len(critical_report)} chars), Detailed ({len(detailed_report)} chars)")
        else:
            # Fallback - return full report in both
            logger.warning("Could not find expected section markers in AI response")
            critical_report = full_report
            detailed_report = full_report

        return critical_report, detailed_report

    except Exception as e:
        logger.error(f"Failed to generate audit report: {e}")
        error_msg = f"Error generating audit: {str(e)}"
        return error_msg, error_msg
