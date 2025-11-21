# ERC-7730 Audit Rules

This directory contains all the JSON configuration files that define the rules, criteria, and guidelines for ERC-7730 clear signing security audits.

## Files Overview

### 1. `erc7730_format_reference.json`
**Purpose:** Complete ERC-7730 format specification reference

**Contains:**
- All supported format types (raw, amount, tokenAmount, date, enum, addressName, calldata, tokenId, nftName, unit)
- Format parameters and their requirements
- Field structure definitions
- Used by the AI to validate that descriptors use correct format types

---

### 2. `critical_issues.json`
**Purpose:** Defines what constitutes a CRITICAL issue in clear signing security

**Contains:**
- 12+ critical issue types (wrong amounts, inverted tokens, missing recipient, broken refs, etc.)
- Detailed criteria for each issue type
- Special cases and exceptions
- Native ETH handling rules for payable functions
- Format validation failures
- Human readability requirements

**Rule:** CRITICAL = USER LOSES MONEY OR GETS WRONG TOKENS/AMOUNTS IN FINAL OUTCOME

---

### 3. `validation_rules.json`
**Purpose:** Patterns that are NOT critical issues (helps AI avoid false positives)

**Contains:**
- Non-critical patterns (max/min amounts, slippage protection, optional parameters, etc.)
- Bitpacked parameters that cannot be meaningfully displayed
- Technical parameters that don't affect user outcome
- Reasons why each pattern is acceptable

---

### 4. `recommendations.json`
**Purpose:** Guidelines for writing the Recommendations section of audit reports

**Contains:**
- Formatting requirements (bullet points, complete sentences, no colons)
- Three types of recommendations:
  1. Fixes for critical issues (with specific code examples)
  2. Spec limitations (parameters that CAN'T be clear signed)
  3. Optional improvements (UX enhancements)
- Examples of good and bad recommendations
- Rules for always including recommendations even when no critical issues exist

---

### 5. `spec_limitations.json`
**Purpose:** Common ERC-7730 specification limitations (things that CAN'T be clear signed)

**Contains:**
- 5 common limitation types:
  1. Bitmask flags / Packed data
  2. Output token determined by pool/DEX
  3. Deeply nested arrays
  4. Dynamic/computed data
  5. Arbitrary low-level calls
- Source code patterns that indicate each limitation
- Required output format (3 parts: explanation, why it matters, detected pattern)
- Example outputs for each limitation type

**Key Rule:** Spec limitations go in Recommendations section, NOT in Critical Issues

---

### 6. `display_issues.json`
**Purpose:** Common display and formatting issues (non-critical UX problems)

**Contains:**
- 8 display issue types:
  1. Unclear parameter labels
  2. Missing context
  3. Format issues
  4. Spelling/grammar errors
  5. Coherence issues (broken $refs, orphaned definitions)
  6. metadata.token redundancy
  7. Missing senderAddress for zero-check fallback
  8. Display edge case (native ETH but trusts user input)
- Severity levels (low, medium, high)
- Examples and recommended actions for each type

---

## Usage

These JSON files are loaded by `src/utils/prompts.py` and included in the AI prompts to ensure consistent, accurate ERC-7730 security audits.

To modify audit criteria:
1. Edit the appropriate JSON file
2. Changes take effect immediately (files are loaded at runtime)
3. No code changes needed - all rules are data-driven

## Maintenance

- **Version:** Each file includes a `version` field for tracking changes
- **Schema:** Each file includes a `$schema` field for JSON Schema validation
- **Documentation:** Each file includes `title` and `description` fields explaining its purpose
