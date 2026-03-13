"""Static rule loading and system instruction construction for analyzer audits."""

import json
import logging
from importlib import resources
from pathlib import Path

from .. import audit_rules

logger = logging.getLogger(__name__)


def read_rule(filename: str) -> str:
    """Read a rule file from packaged audit_rules resources."""
    try:
        return resources.files(audit_rules).joinpath(filename).read_text(encoding="utf-8")
    except FileNotFoundError:
        # Fallback for environments where package-data was not bundled correctly.
        # This covers local runs and CI layout used by .github/workflows/analyze.yml.
        candidates = [
            Path(__file__).resolve().parents[1] / "audit_rules" / filename,
            Path.cwd() / "src" / "utils" / "audit_rules" / filename,
            Path.cwd() / "analyzer" / "src" / "utils" / "audit_rules" / filename,
        ]
        for candidate in candidates:
            if candidate.exists():
                logger.warning(f"Using filesystem fallback for rule file: {candidate}")
                return candidate.read_text(encoding="utf-8")
        raise


SYSTEM_INSTRUCTIONS = None


# Load audit rules that are always used in full (not optimized)
def load_validation_rules() -> dict:
    """Load validation rules from JSON file."""
    return json.loads(read_rule("validation_rules.json"))


def load_critical_issues() -> dict:
    """Load critical issues criteria from JSON file."""
    return json.loads(read_rule("critical_issues.json"))


def load_recommendations() -> dict:
    """Load recommendations format guidelines from JSON file."""
    return json.loads(read_rule("recommendations.json"))


def load_spec_limitations() -> dict:
    """Load spec limitations guidelines from JSON file."""
    return json.loads(read_rule("spec_limitations.json"))


def load_display_issues() -> dict:
    """Load display issues guidelines from JSON file."""
    return json.loads(read_rule("display_issues.json"))


# Cache these files to avoid reloading on every call
_VALIDATION_RULES = None
_CRITICAL_ISSUES = None
_RECOMMENDATIONS = None
_SPEC_LIMITATIONS = None
_DISPLAY_ISSUES = None


def get_validation_rules() -> dict:
    """Get cached validation rules."""
    global _VALIDATION_RULES
    if _VALIDATION_RULES is None:
        _VALIDATION_RULES = load_validation_rules()
    return _VALIDATION_RULES


def get_critical_issues() -> dict:
    """Get cached critical issues criteria."""
    global _CRITICAL_ISSUES
    if _CRITICAL_ISSUES is None:
        _CRITICAL_ISSUES = load_critical_issues()
    return _CRITICAL_ISSUES


def get_recommendations() -> dict:
    """Get cached recommendations format guidelines."""
    global _RECOMMENDATIONS
    if _RECOMMENDATIONS is None:
        _RECOMMENDATIONS = load_recommendations()
    return _RECOMMENDATIONS


def get_spec_limitations() -> dict:
    """Get cached spec limitations guidelines."""
    global _SPEC_LIMITATIONS
    if _SPEC_LIMITATIONS is None:
        _SPEC_LIMITATIONS = load_spec_limitations()
    return _SPEC_LIMITATIONS


def get_display_issues() -> dict:
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
    format_spec = json.loads(read_rule("erc7730_format_reference.json"))

    validation_rules = get_validation_rules()
    critical_issues = get_critical_issues()
    recommendations = get_recommendations()
    spec_limitations = get_spec_limitations()
    display_issues = get_display_issues()

    # Deterministic JSON serialization for stable caching
    # sort_keys=True ensures consistent key ordering
    # separators=(",", ":") ensures compact, consistent formatting
    json_opts = {"sort_keys": True, "separators": (",", ":"), "ensure_ascii": False}

    return f"""You are a clear signing security auditor for ERC-7730 v2 metadata.
**Goal:** Ensure users see all CRITICAL information they need BEFORE signing.

**What is ERC-7730 v2?**
ERC-7730 v2 is a standard for displaying blockchain transaction parameters in human-readable form on wallets. It adds explicit field coverage semantics (`visible`), grouped array display, interpolated intents, maps, and richer formatter support.

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
- `display.formats` keys are the schema identifiers themselves (full function signatures with parameter names, or EIP-712 encodeType strings)
- Check that the analyzed selector, `function_signature`, and descriptor binding key all describe the same function; a mismatch can mean the descriptor is attached to the wrong function entirely
- `context.contract.abi` and `context.eip712.schemas` may appear for compatibility, but they are deprecated and should not drive your primary reasoning

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
- {critical_issues.get("definition", "Critical issues prevent users from making informed decisions")}
- Review all {len(critical_issues.get("critical_criteria", []))} criteria
- v2 emphasizes explicit field coverage via `fields`, `visible`, field groups, and map-backed references

---

**VALIDATION RULES:**

```json
{json.dumps(validation_rules, **json_opts)}
```

**Key:**
- CRITICAL: {validation_rules.get("critical_validation", {}).get("critical_definition", "Misleading or hidden information")}
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
1. Follow the packaged rule files above and stay conservative when evidence is mixed.
2. Recommendations.fixes: Split into "description" (text) and "code_snippet" fields
   - code_snippet fields (field_to_add, changes_to_make, full_example) MUST be valid JSON strings (minified), not objects
   - Example: {{"field_to_add": "{{\\"display\\":{{\\"formats\\":[...]}}}}"}}
3. Spec limitations: Include all 4 parts (parameter, explanation, impact, detected_pattern)
4. Transaction samples: Limit to 3, use actual hashes from provided data
5. Use receipt logs to verify actual token transfers
""".strip()


# Build and cache system instructions at module load (after get_* functions defined)
SYSTEM_INSTRUCTIONS = build_system_instructions()

SCREENSHOT_INSTRUCTIONS = """

---

**LEDGER DEVICE SCREENSHOTS:**

The attached images are actual screenshots of a Ledger hardware device (Stax/Flex) displaying this transaction for user signing via Speculos emulator.

Analyze the screenshots for:
1. **Data consistency**: Verify values shown on device match the calldata parameters (amounts, addresses, token symbols)
2. **Truncation**: Check if any displayed value is truncated in a way that hides critical information (e.g., showing only the first few characters of an address)
3. **Formatting**: Verify numbers, addresses, and amounts are formatted correctly and human-readable
4. **Missing fields**: Check if any important transaction parameters are NOT shown on the device display
5. **Misleading display**: Check if the displayed information could mislead users about what they are signing

Report any screenshot-based findings as display_issues with appropriate severity. Reference the specific screen/step where the issue appears.
""".strip()
