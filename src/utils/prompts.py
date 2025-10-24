"""
AI prompt generation for ERC-7730 audit reports.

This module handles generating prompts and calling OpenAI for audit report generation.
"""

import json
import logging
from typing import Dict, List
from openai import OpenAI

logger = logging.getLogger(__name__)


def generate_clear_signing_audit(
    selector: str,
    decoded_transactions: List[Dict],
    erc7730_format: Dict,
    function_signature: str,
    source_code: Dict = None
) -> str:
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
        Audit report as markdown
    """
    try:
        client = OpenAI()
        logger.info(f"Generating clear signing audit for selector {selector}")

        # Prepare source code section if available
        source_code_section = ""
        if source_code and source_code.get('function'):
            source_code_section = "\n\n**Contract Source Code:**\n\n"
            source_code_section += "You have access to the actual contract source code. Use this to understand the function's true behavior, identify hidden logic, and verify that ERC-7730 metadata accurately represents what the contract does.\n\n"

            if source_code.get('function_docstring'):
                source_code_section += f"```solidity\n{source_code['function_docstring']}\n```\n\n"

            if source_code.get('structs'):
                source_code_section += "**Structs used:**\n```solidity\n"
                source_code_section += "\n\n".join(source_code['structs'])
                source_code_section += "\n```\n\n"

            if source_code.get('enums'):
                source_code_section += "**Enums used:**\n```solidity\n"
                source_code_section += "\n\n".join(source_code['enums'])
                source_code_section += "\n```\n\n"

            if source_code.get('constants'):
                source_code_section += "**Constants used:**\n```solidity\n"
                source_code_section += "\n".join(source_code['constants'])
                source_code_section += "\n```\n\n"

            source_code_section += "**Main Function:**\n```solidity\n"
            source_code_section += source_code['function']
            source_code_section += "\n```\n\n"

            if source_code.get('internal_functions'):
                source_code_section += "**Internal Functions Called:**\n```solidity\n"
                source_code_section += "\n\n".join(source_code['internal_functions'])
                source_code_section += "\n```\n\n"

            if source_code.get('truncated'):
                source_code_section += "⚠️ **Note:** Source code was truncated to fit within limits. Focus on the main function.\n\n"

        # Prepare the prompt
        prompt = f"""You are validating that ERC-7730 display matches what actually happens on-chain.

You MUST produce TWO separate sections in your response:
1. **FIRST REPORT**: CRITICALS ONLY (ultra-strict, terse) - for the mini report
2. **SECOND REPORT**: Full detailed analysis - for the comprehensive report

REFERENCES:
- https://github.com/LedgerHQ/clear-signing-erc7730-registry/blob/master/specs/erc-7730.md
- https://github.com/LedgerHQ/clear-signing-erc7730-registry/blob/master/specs/erc7730-v1.schema.json
- https://github.com/LedgerHQ/clear-signing-erc7730-registry/tree/master


INPUTS:
**Function:** {function_signature}
**Selector:** {selector}{source_code_section}

**ERC-7730 Format Definition:**
```json
{json.dumps(erc7730_format, indent=2)}
```

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

FIRST REPORT: CRITICALS ONLY - BE ULTRA STRICT

**CRITICAL = USER LOSES MONEY OR GETS WRONG TOKENS/AMOUNTS IN FINAL OUTCOME**

You MUST be EXTREMELY conservative. Only flag if a normal user would be shocked by what actually happens.

**ONLY flag as CRITICAL if:**
1. **Final amount IN is WRONG** - User sends 100 USDC but ERC-7730 shows 50 USDC
2. **Final amount OUT is WRONG** - User receives 1 ETH but ERC-7730 shows 2 ETH
3. **Token addresses INVERTED** - ERC-7730 shows "USDC→DAI" but logs show "DAI→USDC"
4. **Completely WRONG token** - ERC-7730 shows user sends/receives USDC but they actually send/receive DAI
   - **IMPORTANT**: If the tokenPath points to a user-supplied parameter (e.g., sendingAssetId or receivingAssetId) but the contract's actual mechanism differs (e.g., sends native ETH from address(this).balance instead of the ERC20 specified in receivingAssetId), this is a DISPLAY ISSUE, NOT CRITICAL, because:
     * The user chose the token ID in their input parameters
     * The amount is still correct
     * The display is showing what the user specified in their input, not a fundamentally different token
     * Flag this in the detailed "Display Issues" section instead
   - **ONLY flag as CRITICAL if**: The displayed token is completely unrelated to any user input (e.g., hardcoded wrong address or pointing to wrong parameter)
5. **Missing RECIPIENT parameter** - If recipient is an INPUT parameter that receives funds and is NOT shown to user, this is CRITICAL
6. **Broken `$ref` references** - Format references non-existent definitions/constants (display will fail)
7. **Input parameter path mismatch** - ERC-7730 references a parameter path that doesn't exist in the ABI OR uses wrong path/name (e.g., format shows "_receiver" but ABI has "receiver", or shows "_tokens[0]" but should be "_swapData[0].token")
8. **Native ETH handling in payable functions (for what the user sends and all functions even non payable for what he receives)** (this is critical and nuanced):
  - **IMPORTANT**: These rules apply to BOTH what the user SENDS and what the user RECEIVES
  - **HOW TO CHECK**: For EACH field that displays a token amount, check if that field OR its $ref definition has native ETH support
  - **Understanding format types**:
    * `"format": "tokenAmount"` = Can display ANY ERC20 token + native ETH (if nativeCurrencyAddress specified)
    * `"format": "amount"` with `"path": "@.value"` = Shows msg.value (native ETH sent with tx)
  - If function uses native ETH (payable function OR receives native ETH output):
    * **Case 1 - Field with format "tokenAmount" and tokenPath to potential native ETH sentinel**:
      → Step 1: Look at the field showing the amount
      → Step 2a: If field has `"$ref"`, look up that definition in display.definitions
      → Step 2b: Check if the DEFINITION has `"nativeCurrencyAddress"` in its params
      → Step 3: If no $ref, check if the FIELD itself has `"nativeCurrencyAddress"` in its params
      → **CRITICAL if missing**: If NEITHER the field NOR its referenced definition has nativeCurrencyAddress, native ETH won't display correctly
      → **Example CORRECT (via $ref)**:
        Field: `{{"path": "_amount", "$ref": "$.display.definitions.tokenAmount", "params": {{"tokenPath": "_token"}}}}`
        Definition: `{{"tokenAmount": {{"format": "tokenAmount", "params": {{"nativeCurrencyAddress": ["$.metadata.constants.addressAsEth"]}}}}}}`
      → **Example CORRECT (direct)**:
        `{{"path": "_amount", "format": "tokenAmount", "params": {{"tokenPath": "_token", "nativeCurrencyAddress": ["$.metadata.constants.addressAsEth"]}}}}`
      → **Example WRONG**:
        `{{"path": "_amount", "format": "tokenAmount", "params": {{"tokenPath": "_token"}}}}` (no nativeCurrencyAddress anywhere)
    * **Case 2 - Field with path "@.value"**:
      → This directly shows msg.value (ETH sent with transaction)
      → Format is typically "amount", not "tokenAmount"
      → Example: `{{"path": "@.value", "label": "Amount", "format": "amount"}}`
    * **Case 3 - Token address is WETH but function is payable**:
      → Function does internal deposit to convert ETH→WETH
      → Do NOT require native ETH display (would be incorrect/duplicate)
  - Check source code and receipt_logs (if available) to determine which case applies. Sometimes even if sentinels exist, the code does not allow native transfer even if the function is payable.
  - **KEY**: When checking for nativeCurrencyAddress, follow $ref references to definitions - it can be in either place
  - Only flag as critical if native ETH is actually being transferred AND display cannot show it
8. **Amounts are displayed twice**
9. **Spelling/grammar errors** in labels or intent


**CRITICAL REQUIREMENT - Can it be fixed with available input parameters?**
- ONLY flag as CRITICAL if the missing/wrong information EXISTS in the function's input parameters
- Example: If ERC-7730 doesn't show recipient but recipient is an input parameter → CRITICAL
- Example: If showing max or min amount not actual amounts (which is computed on-chain, not in input) → NOT CRITICAL (that's how the function works)
- **Rule: If the information cannot be obtained from input parameters, it's NOT a critical issue - it's just the function's design**

**DO NOT FLAG (these are NOT critical):**
- ✅ Sentinel values like CONTRACT_BALANCE, ADDRESS_THIS - implementation details users don't see
- ✅ "Payer" logic or who sources tokens - as long as user gets right tokens/amounts
- ✅ Missing parameters like sqrtPriceLimit, deadline, slippage - technical stuff
- ✅ Intermediate approvals/transfers/hops - only final In/Out matters
- ✅ Recipient being a constant/sentinel value - as long as user receives tokens
- ✅ Contract balance logic - implementation detail
- ✅ Internal routing - users don't care HOW swap happens
- ✅ ANY parameter regular users wouldn't understand without reading Solidity
- ✅ Unused definitions/constants in metadata - cleanup issue, NOT critical (mention in detailed report)
- ✅ **Negative array indices** - this is part of the ERC-7730 spec to access last element and is REQUIRED to work
- ✅ **ERC-7730 spec features** - Do NOT flag spec-compliant features as "may not be supported" - they MUST be supported
- ✅ **Token type display uses user input but contract mechanism differs** - When the display uses a user-supplied parameter for token type (e.g., sendingAssetId or receivingAssetId) but the contract's internal logic uses a different mechanism (e.g., native ETH from address(this).balance instead of ERC20 transfer), this is a DISPLAY ISSUE for the detailed report, NOT critical. The user specified the token in their input, so the display is showing what they requested, even if the contract's internal implementation differs.

**KEY QUESTION:** "Would a regular user be shocked by the FINAL tokens/amounts sent and received, or WHO receives them?"
- NO → DO NOT flag
- YES → Flag as critical

**EXAMPLES NOT CRITICAL:**
- "amountIn uses sentinel CONTRACT_BALANCE" → NOT CRITICAL (implementation detail)
- "Payer not exposed" → NOT CRITICAL (users don't care about payer logic)
- "Recipient may be sentinel" → NOT CRITICAL (they still get tokens)
- "Missing sqrtPriceLimit parameter" → NOT CRITICAL (technical)
- "Showing a max or min amount rather than exact ones" → NOT CRITICAL (actual amount is computed on-chain, not available in inputs)
- "Missing actual spend amount for max-based swaps" → NOT CRITICAL (that's how max-based swaps work - you specify max, actual is computed)

BE STRICT. When in doubt, DO NOT flag as critical.

**FORMAT FOR FIRST REPORT:**

If NO critical issues found, output ONLY:
```
✅ No critical issues found.
```

If critical issues ARE found, output:
```
🔴 Critical Issues:
- [Issue 1 description - be specific and concise]
- [Issue 2 description - be specific and concise]

💡 Recommendations:
- [Recommendation 1 - be specific]
- [Recommendation 2 - be specific]
```

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

**Check for:**
- Token addresses shown are inverted/incorrect vs receipt_logs
- Amount values mapped to wrong tokens
- Critical parameters shown with misleading labels
- Hidden information in receipt_logs that should be shown
- Approvals not disclosed to users
- Mismatch between displayed intent and actual token movements in logs
- **Broken `$ref` references** - If format references `$.display.definitions.X` or `$.metadata.constants.Y` that don't exist, this is CRITICAL (display will fail)
- **Input parameter path mismatch** - ERC-7730 references parameter paths that don't match the ABI (wrong names, wrong nesting, non-existent fields)
- **Native ETH handling in payable functions (for what the user sends and all functions even non payable for what he receives)** (this is critical and nuanced):
  - **IMPORTANT**: These rules apply to BOTH what the user SENDS and what the user RECEIVES
  - **HOW TO CHECK**: For EACH field that displays a token amount, check if that field OR its $ref definition has native ETH support
  - **Understanding format types**:
    * `"format": "tokenAmount"` = Can display ANY ERC20 token + native ETH (if nativeCurrencyAddress specified)
    * `"format": "amount"` with `"path": "@.value"` = Shows msg.value (native ETH sent with tx)
  - If function uses native ETH (payable function OR receives native ETH output):
    * **Case 1 - Field with format "tokenAmount" and tokenPath to potential native ETH sentinel**:
      → Step 1: Look at the field showing the amount
      → Step 2a: If field has `"$ref"`, look up that definition in display.definitions
      → Step 2b: Check if the DEFINITION has `"nativeCurrencyAddress"` in its params
      → Step 3: If no $ref, check if the FIELD itself has `"nativeCurrencyAddress"` in its params
      → **CRITICAL if missing**: If NEITHER the field NOR its referenced definition has nativeCurrencyAddress, native ETH won't display correctly
      → **Example CORRECT (via $ref)**:
        Field: `{{"path": "_amount", "$ref": "$.display.definitions.tokenAmount", "params": {{"tokenPath": "_token"}}}}`
        Definition: `{{"tokenAmount": {{"format": "tokenAmount", "params": {{"nativeCurrencyAddress": ["$.metadata.constants.addressAsEth"]}}}}}}`
      → **Example CORRECT (direct)**:
        `{{"path": "_amount", "format": "tokenAmount", "params": {{"tokenPath": "_token", "nativeCurrencyAddress": ["$.metadata.constants.addressAsEth"]}}}}`
      → **Example WRONG**:
        `{{"path": "_amount", "format": "tokenAmount", "params": {{"tokenPath": "_token"}}}}` (no nativeCurrencyAddress anywhere)
    * **Case 2 - Field with path "@.value"**:
      → This directly shows msg.value (ETH sent with transaction)
      → Format is typically "amount", not "tokenAmount"
      → Example: `{{"path": "@.value", "label": "Amount", "format": "amount"}}`
    * **Case 3 - Token address is WETH but function is payable**:
      → Function does internal deposit to convert ETH→WETH
      → Do NOT require native ETH display (would be incorrect/duplicate)
  - Check source code and receipt_logs (if available) to determine which case applies. Sometimes even if sentinels exist, the code does not allow native transfer even if the function is payable.
  - **KEY**: When checking for nativeCurrencyAddress, follow $ref references to definitions - it can be in either place
  - Only flag as critical if native ETH is actually being transferred AND display cannot show it
- Amounts are displayed twice
- Spelling/grammar errors in labels or intent

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

> 🟡 **Issues with how information is presented to users**

List display/formatting issues. Examples:
- Parameter labels unclear or confusing
- Missing context (e.g., recipient not clearly identified)
- Format issues (decimals, addresses, etc.)
- **Spelling and grammar errors** in labels, intent, or field descriptions
- **Coherence issues** between metadata (definitions/constants) and selector format:
  - Check that `$ref` references point to existing definitions/constants
  - Verify definitions/constants referenced are actually used appropriately
  - Ensure label text matches the referenced definition's purpose
  - Check for orphaned definitions/constants that are declared but never used
  - Verify constant values (like native ETH address) are correct and consistent
  - **DISPLAY EDGE CASE - Function always inputs or outputs native ETH but trusts user input for display**:
    * If function name or code shows it ONLY inputs or outputs in native ETH (e.g., "ERC20ToNative", "NativeToERC20", or contract collects address(this).balance and sends ETH or only accepts ETH from user as input)
    * AND the ERC-7730 uses a user input parameter for tokenPath (e.g., `"tokenPath": "receivingAssetId" or "sendingAssetId"`)
    * Even if nativeCurrencyAddress is present, user might input WRONG address (ERC20 instead of sentinel)
    * Display will show wrong token (e.g., "100 USDC") while user actually receives or sends native ETH
    * **This is medium** - mismatch between what contract does vs what display shows based on user input
    * Solution: tokenPath should be hardcoded to a native sentinel constant OR use @.value, not trust user input

If none: **✅ No display issues found**

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
- Recommendation 1 (be specific)
- Recommendation 2 (be specific)
- Recommendation 3 (if needed)

---

**Use bold, italic, emojis, tables, blockquotes, and horizontal rules to make it visually appealing and easy to scan.**"""

        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[{"role": "user", "content": prompt}]
        )

        audit_report = response.choices[0].message.content
        logger.info(f"Successfully generated audit report for {selector}")
        return audit_report

    except Exception as e:
        logger.error(f"Failed to generate audit report: {e}")
        return f"Error generating audit: {str(e)}"
