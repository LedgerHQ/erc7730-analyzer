"""
AI prompt generation for ERC-7730 audit reports.

This module handles generating prompts and calling OpenAI for audit report generation.
"""

import json
import logging
from typing import Dict, List, Tuple
from openai import OpenAI

logger = logging.getLogger(__name__)


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
        erc7730_enums_section = ""
        if erc7730_format.get('metadata', {}).get('enums'):
            erc7730_enums_section = "\n\n**ERC-7730 Enum Definitions (from descriptor):**\n\n"
            erc7730_enums_section += "The descriptor defines these enum mappings for displaying parameters:\n\n"
            for enum_name, enum_values in erc7730_format['metadata']['enums'].items():
                erc7730_enums_section += f"**{enum_name}:**\n```json\n"
                erc7730_enums_section += json.dumps(enum_values, indent=2)
                erc7730_enums_section += "\n```\n\n"

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

**Array Index Notation:**
- `[0]` - First element in an array
- `[-1]` - **Last element in an array** (negative indices are VALID and standard in ERC-7730)

**Swap Functions - What to Display:**
- **ONLY show**: First amount IN and final amount OUT
- **DO NOT show**: Intermediate swap amounts, intermediate tokens, or intermediate hops
- **WHY**: Users only care about what they send and what they receive, not the routing path
- **Approvals**: Do NOT flag approval events UNLESS the function is specifically `approve()` or `permit()` - swap functions will have approval events as part of their execution, which is normal
- Multi-hop swaps displaying only first/last amounts is CORRECT and should NOT be flagged as missing information

---

**ERC-7730 FORMAT TYPES SPECIFICATION:**

All "format" fields in ERC-7730 MUST use one of these values:

1. **"raw"** - Raw UINT parameter that cannot be linked to any specific type below
   - Use when value is just a number with no special meaning

2. **"amount"** - Amount in native currency (ETH)
   - Use ONLY when you are CERTAIN the currency is Native ETH
   - Commonly used with `"path": "@.value"` to show msg.value

3. **"tokenAmount"** - Amount in ERC20 Token
   - **REQUIRED PARAM** (choose one): MUST have `token` XOR `tokenPath`
     * **Option A - Dynamic token (from input parameter)**: Use `"tokenPath"` pointing to the parameter name
       - Example: `{{"path": "amount", "format": "tokenAmount", "params": {{"tokenPath": "token"}}}}`
     * **Option B - Fixed token (hardcoded address)**: Use `"token"` with the hardcoded address
       - Example: `{{"path": "amount", "format": "tokenAmount", "params": {{"token": "0x1234..."}}}}`
       - Use this for migration contracts or functions that ONLY operate on a specific token
   - **CRITICAL if NEITHER tokenPath NOR token is present** UNLESS one of these exceptions applies:
     * Exception 1: Function ONLY supports native ETH (no other token possible) AND has `nativeCurrencyAddress`
     * Exception 2: Token address is NOT available in function inputs (e.g. computed on-chain from pool/DEX) AND has `nativeCurrencyAddress` for native transfers only
   - **OPTIONAL PARAMS**:
     * `nativeCurrencyAddress`: Address(es) interpreted as native currency (ETH) - can be string OR array
     * `threshold`: Amount threshold above which `message` is displayed instead of actual amount
     * `message`: Message to display for amounts above threshold (e.g., "Unlimited" for max allowances)
   - Example with threshold: `{{"path": "amount", "format": "tokenAmount", "params": {{"tokenPath": "token", "threshold": "115792089237316195423570985008687907853269984665640564039457584007913129639935", "message": "Unlimited"}}}}`

4. **"nftName"** - ID of the NFT in the collection
   - **REQUIRED PARAM**: MUST have `"collectionPath"` in params pointing to the NFT collection address
   - Example: `{{"path": "_tokenId", "format": "nftName", "params": {{"collectionPath": "_collection"}}}}`

5. **"addressName"** - Address parameter
   - Use this format for ALL address parameters
   - **OPTIONAL PARAMS**:
     * `senderAddress`: For conditional fallback to sender (@.from)
       - If the address value equals one of the addresses in `senderAddress` array (typically `["0x0000000000000000000000000000000000000000"]`), the wallet displays `@.from` (msg.sender) instead
       - Common pattern: `dstReceiver = (param == address(0)) ? msg.sender : param`
       - Example: `{{"path": "_recipient", "format": "addressName", "params": {{"senderAddress": ["0x0000000000000000000000000000000000000000"]}}}}`
     * `types`: Array restricting address types - `["wallet", "eoa", "contract", "token", "collection"]` - This restricts name sources and may trigger additional wallet checks
     * `sources`: Array of trusted name sources in order of preference (wallet manufacturer specific, e.g., `["local", "ens"]`)
   - Example: `{{"path": "_recipient", "format": "addressName"}}`

6. **"date"** - UINT representing a timestamp/date
   - **REQUIRED PARAM**: MUST have `"encoding"` parameter set to either `"timestamp"` or `"blockheight"`
   - Use when parameter is a Unix timestamp or block height
   - Example: `{{"path": "_deadline", "format": "date", "params": {{"encoding": "timestamp"}}}}`

7. **"duration"** - UINT representing a time duration
   - Use when parameter represents a time period (seconds, days, etc.)
   - Value interpreted as seconds, displayed as HH:MM:ss
   - Example: `{{"path": "_lockPeriod", "format": "duration"}}`

8. **"unit"** - UINT representing a value with custom unit
   - **REQUIRED PARAM**: MUST have `"base"` parameter with unit symbol (SI unit, "%", "bps", etc.)
   - Optional: `"decimals"` (default 0), `"prefix"` (boolean for SI prefix like k, M, G)
   - Example: `{{"path": "_fee", "format": "unit", "params": {{"base": "%", "decimals": 2}}}}`
   - Example: `{{"path": "_time", "format": "unit", "params": {{"base": "h"}}}}`

9. **"enum"** - Value converted using referenced enumeration
   - **REQUIRED PARAM**: MUST have `$ref` path to enumeration in metadata.constants OR metadata.enums
   - Both `$.metadata.constants.*` and `$.metadata.enums.*` are valid
   - Path starts with root node `$.`
   - Enums can be static (object with key-value pairs) OR dynamic (URL string returning JSON)
   - Example (constants): `{{"path": "_swapType", "format": "enum", "params": {{"$ref": "$.metadata.constants.swapTypes"}}}}`
   - Example (enums): `{{"path": "_rateMode", "format": "enum", "params": {{"$ref": "$.metadata.enums.interestRateMode"}}}}`

10. **"calldata"** - Embedded calldata for nested/recursive calls
   - **REQUIRED PARAM**: MUST have `callee` OR `calleePath` (exactly one, mutually exclusive)
     * `callee`: Fixed address string (e.g., `"0x123..."`)
     * `calleePath`: JSON path to address in structured data (e.g., `"@.to"`, `"target"`)
   - **OPTIONAL PARAMS**:
     * `selector` OR `selectorPath`: Function selector if not in calldata (mutually exclusive)
     * `amount` OR `amountPath`: Associated native currency amount (mutually exclusive)
     * `spender` OR `spenderPath`: Associated spender address (mutually exclusive)
   - The nested calldata is decoded using another ERC-7730 descriptor and shown on SUBSEQUENT screens
   - If no descriptor available, wallet MAY display hash of calldata instead
   - Example: `{{"path": "action", "label": "Action", "format": "calldata", "params": {{"calleePath": "@.to"}}}}`
   - This enables multi-screen clear signing for wrapper functions like `permitAndCall`, `multicall`, `execute`

**MUTUALLY EXCLUSIVE CONSTRAINTS (XOR):**
These parameter pairs CANNOT both be present - you must use exactly one:
- Field: `path` XOR `value` (either extract from data OR use literal value)
- addressName: `senderAddress` can be string OR array (not both, but can omit)
- tokenAmount: `token` XOR `tokenPath` (fixed address OR dynamic path)
- tokenAmount: `nativeCurrencyAddress` can be string OR array
- nftName: `collection` XOR `collectionPath` (fixed address OR dynamic path)
- calldata: `callee` XOR `calleePath` (fixed address OR dynamic path)
- calldata: `selector` XOR `selectorPath` (fixed selector OR dynamic path)
- calldata: `amount` XOR `amountPath` (fixed amount OR dynamic path)
- calldata: `spender` XOR `spenderPath` (fixed spender OR dynamic path)

**ALTERNATIVE FIELD VALUE:**
- Instead of `"path": "fieldName"`, you can use `"value": "literal"` to display a fixed string/number
- Example: `{{"value": "Swap", "label": "Action", "format": "raw"}}` - displays literal "Swap" text
- `path` and `value` are mutually exclusive - cannot have both

**CRITICAL VALIDATION RULES:**
1. **Format-specific requirements:**
   - If format is "tokenAmount" → MUST have "token" XOR "tokenPath" in params
     * **EXCEPTION**: If function ONLY supports native ETH (check source code) OR token is not in inputs (encoded/computed) OR cannot be determined from inputs AND has nativeCurrencyAddress → NOT CRITICAL, add WARNING in detailed report
   - If format is "nftName" → MUST have "collection" XOR "collectionPath" in params
   - If format is "date" → MUST have "encoding" parameter ("timestamp" or "blockheight")
   - If format is "unit" → MUST have "base" parameter (unit symbol)
   - If format is "enum" → MUST have "$ref" in params pointing to $.metadata.constants.* or $.metadata.enums.*
   - If format is "calldata" → MUST have "callee" XOR "calleePath" in params

2. **XOR (Mutually Exclusive) violations:**
   - Field has BOTH "path" and "value" → CRITICAL ERROR (must have exactly one)
   - tokenAmount has BOTH "token" and "tokenPath" → CRITICAL ERROR
   - nftName has BOTH "collection" and "collectionPath" → CRITICAL ERROR
   - calldata has BOTH "callee" and "calleePath" → CRITICAL ERROR
   - calldata has BOTH "selector" and "selectorPath" → CRITICAL ERROR
   - calldata has BOTH "amount" and "amountPath" → CRITICAL ERROR
   - calldata has BOTH "spender" and "spenderPath" → CRITICAL ERROR

3. **Other validations:**
   - Token addresses should be excluded from display when amount is shown with tokenPath reference
   - Always check both field params AND $ref definition params for required fields like nativeCurrencyAddress
   - If a field references `$ref` but overrides params, the override takes precedence

**CONTAINER STRUCTURE VALUES (Transaction Fields):**
These special paths reference the enclosing transaction/message, not the function parameters:
- `@.from` - The sender/signer address (who is calling the function)
- `@.to` - The destination contract address (where the transaction is sent)
- `@.value` - The native currency amount sent with the transaction (msg.value in Solidity)
Example uses:
- `{{"path": "@.value", "format": "amount"}}` - Shows ETH/native currency being sent
- `{{"path": "@.from", "format": "addressName"}}` - Shows sender as beneficiary
- `{{"tokenPath": "@.to"}}` - Uses the contract's own address as token reference

**REQUIRED AND EXCLUDED FIELDS:**
- `"required"` array: Lists field paths that SHOULD be displayed to users
- `"excluded"` array: Lists field paths that are intentionally hidden
- **Check**: If a function parameter exists in decoded_input but has NO field formatter AND is NOT in the `excluded` array → This may indicate missing display information (mention in detailed report, not critical unless it's an amount/recipient/token)

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
5. **Missing RECIPIENT parameter** - Three cases:
   - **Case A**: If recipient IS an INPUT parameter that receives funds and is NOT shown → CRITICAL
   - **Case B**: If recipient is NOT in ABI inputs (because it's always msg.sender) BUT is important to show:
     * Check if function always sends tokens/ETH to the sender (e.g., withdraw(), claimRewards(), unwrap())
     * If YES and NO recipient field exists → Recommend using `{{"path": "@.from", "label": "Beneficiary", "format": "addressName"}}`
     * This shows the user they're receiving funds to their own address
   - **Case C**: If recipient IS an INPUT parameter BUT code shows conditional fallback to msg.sender (e.g., `recipient = (param == address(0)) ? msg.sender : param`):
     * Check source code for pattern: `(param == address(0))` or similar zero-check
     * If recipient field exists WITHOUT `senderAddress` param → Add WARNING in detailed report (not critical, but should recommend adding `"senderAddress": ["0x0000000000000000000000000000000000000000"]`)
     * This allows wallet to display `@.from` when user passes zero address
   - **Special transaction fields**: `@.from` = sender address, `@.value` = native currency value sent with tx
6. **Broken `$ref` references** - Format references non-existent definitions/constants (display will fail)
7. **Input parameter path mismatch** - ERC-7730 references a parameter path that doesn't exist in the ABI OR uses wrong path/name (e.g., format shows "_receiver" but ABI has "receiver", or shows "_tokens[0]" but should be "_swapData[0].token")
7b. **Format validation failures**:
   - **tokenAmount without token specification**: Field has `"format": "tokenAmount"` but missing BOTH `"tokenPath"` AND `"token"` in params
     * → Token can be specified in TWO ways:
       1. **Dynamic (from parameter)**: `"tokenPath": "paramName"` - token address comes from function input
       2. **Fixed (hardcoded)**: `"token": "0x..."` - for migration contracts or functions operating on single specific token
     * → CRITICAL if NEITHER is present **UNLESS** one of these exceptions applies:
       1. Function ONLY supports native ETH (check source code: no ERC20 support, hardcoded ETH) AND has `nativeCurrencyAddress`
       2. Token address is NOT in function inputs (computed from pool/DEX, encoded in bytes, determined on-chain) AND has `nativeCurrencyAddress`
     * → If exception 2 applies (token determined by pool): This is a **SPEC LIMITATION** - Add to "Parameters that cannot be clear signed" section, NOT to critical issues. Example: "Output token cannot be clear signed because it is determined by the pool/DEX and not an explicit function input"
   - **nftName without collectionPath**: Field has `"format": "nftName"` but missing `"collectionPath"` in params → CRITICAL
   - **enum without reference**: Field has `"format": "enum"` but missing `$ref` to metadata.constants OR metadata.enums → CRITICAL
   - **Wrong format type**: Using wrong format (e.g., "amount" for ERC20 token, or "tokenAmount" without tokenPath)
     * **EXCEPTION - Type casting uint256/bytes32 ↔ address**: Using `"addressName"` format on `uint256`, `bytes32`, or `bytes20` ABI type is VALID (casting is supported by taking 20 bytes). Similarly, using `"raw"` or numeric formats on `address` type is valid. These are NOT critical type mismatches.
     * **EXCEPTION - Token amount as "raw" when token cannot be determined**: If a field displays a token amount (e.g., amountOut, minReceive) but uses `"format": "raw"` instead of `"tokenAmount"`, this is ACCEPTABLE if the token address cannot be determined from function inputs (e.g., output token is computed from pool addresses/routes). This is NOT critical - it's a known concession. Only mention in recommendations: "User will see raw amount without token symbol/decimals because output token cannot be determined from inputs."
   - Check BOTH the field params AND any $ref definition params for these requirements
8. **Native ETH handling in payable functions (for what the user sends and all functions even non payable for what he receives)** (this is critical and nuanced):
  - **CRITICAL PRE-CHECK - Function payability**: Check if the MAIN function (the one being clear signed) is marked `payable` in the ABI
    * If the main function is NOT payable → `msg.value` is ALWAYS 0, even if it calls internal payable functions
    * Example: `uniswapV3SwapToWithPermit()` is NOT payable but calls `uniswapV3SwapTo()` which is payable
    * In this case, the internal function's payable logic will NEVER execute because `msg.value == 0`
    * **Do NOT flag missing @.value if the main function is not payable**
  - **IMPORTANT - Non-payable function showing ETH as option**: If a function is NOT payable but the descriptor includes `nativeCurrencyAddress` (showing ETH as possible input):
    * This is NOT CRITICAL - it's a UX improvement recommendation only
    * The transaction will revert if user tries to send ETH to a non-payable function (no funds lost)
    * The UI/frontend likely prevents this anyway
    * Add to RECOMMENDATIONS: "Function is not payable but descriptor shows ETH as possible input. Consider removing nativeCurrencyAddress for better UX to prevent users from selecting ETH which would cause transaction to revert."
    * Do NOT add to critical issues
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
    * **Case 3 - Payable function that accepts native ETH (especially WETH deposit or similar)**:
      → **CRITICAL CHECK**: Does the ERC-7730 display the ETH amount being sent?
      → **If fields array is EMPTY or has NO amount fields** → CRITICAL (nothing is shown to user)
      → **If function ONLY accepts native ETH (no token parameter) and no @.value field exists** → CRITICAL
      → **If function accepts both tokens and ETH**: Only NOT critical if another amount field displays the same value (e.g., deposit(uint256 amount) where amount must equal msg.value)
      → Example FIX for payable functions with no inputs: `{{"path": "@.value", "label": "Amount", "format": "amount"}}`
    * **Case 4 - WRAPPER/FORWARDING PATTERN (INFORMATIONAL, not CRITICAL)**:
      → **Pattern detection**: If a payable function meets ALL these conditions:
        1. Function body does NOT manipulate `msg.value` in its own logic (no validation, no splitting, no storing)
        2. Function forwards the ENTIRE value via one of these patterns:
           - `delegatecall(...)` - automatically forwards msg.value
           - `.call{{value: msg.value}}(...)` - explicitly forwards full msg.value
           - `.call{{value: address(this).balance}}(...)` - forwards all received ETH
        3. Function does NOT display `@.value` in ERC-7730
      → **Why this is NOT critical**:
        * The value is forwarded entirely to a nested call
        * The nested call (typically decoded from a `bytes calldata` parameter like `action`, `data`, or `calls`) will have its own ERC-7730 descriptor
        * That nested descriptor SHOULD display `@.value`
        * Users see multiple clear signing screens: one for the wrapper, one for the nested call
        * The value is shown on the nested call's screen, not the wrapper's screen
        * Wallet UI also shows total transaction value regardless
      → **Example wrapper patterns**:
        ```solidity
        // Pattern A: delegatecall (auto-forwards value)
        function permitAndCall(bytes calldata action) external payable {{
            doPermit();
            assembly {{ delegatecall(gas(), address(), ...) }}  // ✓ Auto-forwards
        }}

        // Pattern B: explicit value forwarding
        function executeWithValue(bytes calldata data) external payable {{
            target.call{{value: msg.value}}(data);  // ✓ Explicitly forwards
        }}
        ```
      → **Counter-example (CRITICAL)**:
        ```solidity
        function swapWithFee(SwapData calldata desc) external payable {{
            require(msg.value == desc.amount);  // ❌ Uses msg.value in logic
            executor.call{{value: msg.value}}(data);
        }}
        // This IS critical because function validates msg.value
        ```
      → **Action to take**: Mark as INFORMATIONAL (not CRITICAL) with note: "This appears to be a wrapper function that forwards execution and value entirely. Verify that nested call descriptors display @.value."
      → **DO NOT flag as critical** if this pattern is detected
  - Check source code and receipt_logs (if available) to determine which case applies. Sometimes even if sentinels exist, the code does not allow native transfer even if the function is payable.
  - **KEY**: When checking for nativeCurrencyAddress, follow $ref references to definitions - it can be in either place
  - Only flag as critical if native ETH is actually being transferred AND display cannot show it
8. **Amounts are displayed twice**
9. **Spelling/grammar errors** in labels or intent
10. Labels and intents must not be longer than 20 characters
11. **msg.value representation** - WHEN to use each approach:
   - **Use `@.value`**: When function ONLY accepts native ETH 
   - **Use input parameter**: When function has an amount parameter that EQUALS msg.value and can be also used for other tokens
   - **CRITICAL**: If payable function has no parameters AND no `@.value` field → user can't see amount being sent

**CRITICAL REQUIREMENT - Array indexing validation:**
- When ERC-7730 uses array indexing (like `"tokenPath": "route.[-1]"` or `"tokens.[2]"`), verify the index points to actual data relevant to the user
- **Common issue**: Fixed-size arrays where unused slots contain `0x0000...` or other sentinels
- **How to check**: Look at source code and decoded transaction parameters and verify array indices reference real data, not empty/sentinel slots
- **CRITICAL if**: The indexed element is a sentinel (0x00) while real data exists elsewhere in the array

**CRITICAL REQUIREMENT - Can it be fixed with available input parameters?**
- ONLY flag as CRITICAL if the missing/wrong information EXISTS in the function's input parameters AND can be displayed with current ERC-7730 spec AND can be shown in a HUMAN-READABLE format
- Example CRITICAL: ERC-7730 doesn't show recipient but recipient is an input parameter → CRITICAL (can be fixed)
- Example NOT CRITICAL: Showing max/min amount not actual amounts (computed on-chain, not in inputs) → NOT CRITICAL (that's how the function works)
- **Rule: If the information cannot be obtained from input parameters OR cannot be displayed with ERC-7730 spec OR cannot be shown in human-readable format, it's NOT a critical issue - it's a SPEC LIMITATION (add to section 6️⃣, not section 2)**

**CRITICAL DISTINCTION - Human Readability:**
- **Can be clear signed in READABLE format** (address, token amount, date) → If missing, this IS critical
- **Can only be shown as RAW/incomprehensible data** (packed bits, raw bytes32, complex flags, large computed values like liquidity) → If missing, this is NOT critical
- **Key question**: "Would displaying this as 'raw' format help the user understand what they're signing?"
  - YES (e.g., address as hex, token amount as number) → Critical if missing
  - NO (e.g., `0x000000000000001a4` for packed traits, arbitrary bytes, `1582938471982347` for liquidity) → NOT critical
- **Example NOT CRITICAL #1**: Bitpacked parameter (e.g., `traits`, `flags`, `options`) controlling operation mode but can only display as `0x1a2b3c4d...` (incomprehensible)
  - AI might recommend: "Add {{"path": "traits", "format": "raw"}}"
  - Reality: Raw hex like `0x00000000000000000000000000000000000000000000000000000000000001a4` tells user NOTHING
  - Conclusion: NOT critical to hide - users cannot understand it anyway
- **Example NOT CRITICAL #2**: `liquidity` or `sqrtPriceX96` parameter with large computed value
  - AI might recommend: "Add {{"path": "liquidity", "format": "raw"}}"
  - Reality: Raw number like `1582938471982347` is meaningless without formula/context
  - Users cannot interpret: Is this good? Is this the right amount? What does it mean?
  - Similar examples: `sqrtPriceX96`, `tick`, `feeGrowthGlobal0X128` - all require mathematical context
  - Conclusion: NOT critical to hide - displaying raw value doesn't help users verify correctness
- **Example CRITICAL**: `recipient` address hidden
  - Can display as: `0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb` (readable address)
  - Users understand: "My tokens go to this address"
  - Conclusion: CRITICAL to hide
- **Rule**: Do NOT recommend displaying parameters as "raw" format unless the raw value is meaningful to users. If the only way to show something is incomprehensible, it's acceptable to hide it.

**Examples of SPEC LIMITATIONS (NOT critical issues):**
1. **Packed/bitflag parameters** - Bitpacked uint256 parameters (e.g., `traits`, `flags`, `options`, `config`) with packed data requiring bitwise operations → Cannot display with ERC-7730
2. **Parameters only displayable as incomprehensible raw hex/numbers** - Even if technically possible to show as "raw" format, if the value is meaningless to users, it's NOT critical to hide:
   - Example: Bitpacked parameter as `0x00000000000000000000000000000000000000000000000000000000000001a4` (packed bits)
   - Example: `liquidity` as `1582938471982347` (large computed value requiring mathematical context)
   - Example: `sqrtPriceX96`, `tick`, `feeGrowthGlobal0X128` (Uniswap V3 technical parameters)
   - Users cannot verify correctness from raw values without deep protocol knowledge
3. **Output token from pool** - `minReturn` where output token determined by pool/DEX address → Cannot reliably map to specific ERC20
4. **Arbitrary calldata** - Multicall/delegatecall functions with arbitrary actions → Not necessary to decode, users understand these are generic execution
5. **Values computed on-chain** - Actual swap amounts, slippage-adjusted amounts → Only max/min available in inputs

**DO NOT FLAG (these are NOT critical):**
- ✅ Sentinel values like CONTRACT_BALANCE, ADDRESS_THIS - implementation details users don't see
- ✅ "Payer" logic or who sources tokens - as long as user gets right tokens/amounts
- ✅ Missing parameters like sqrtPriceLimit, deadline, slippage - technical stuff
- ✅ **Amount capped to user's available balance/debt (repay/withdraw functions)** - If a function:
  1. Takes an amount parameter from user
  2. Caps the actual transferred amount to user's balance/debt/limit (using min() or similar)
  3. Code shows patterns like `amount = min(amount, userBalance)` or `if (amount > debt) amount = debt`
  4. User CANNOT lose more than they have/owe - the cap protects them
  → This is NOT CRITICAL - showing raw input amount is acceptable
  → The cap is a PROTECTIVE mechanism, not a risk
  → User cannot be charged more than they owe or lose more than they have
  → **Common patterns**: `repay()` (capped to debt), `withdraw()` (capped to balance), `redeem()` (capped to shares)
  → **How to detect**: Look in source code for:
    * `paybackAmount = amount < debt ? amount : debt` or `min(amount, debt)`
    * `actualAmount = min(amount, userBalance)`
    * Amount compared to user's state and capped
    * Final transfer uses the capped amount, not raw input
  → **Example**:
    ```solidity
    function repay(uint256 amount) external {{
        uint256 debt = getUserDebt(msg.sender);
        uint256 paybackAmount = amount < debt ? amount : debt;  // ✓ Capped
        token.safeTransferFrom(msg.sender, address(this), paybackAmount);
    }}
    // NOT critical - user cannot pay more than they owe
    ```
  → **Action**: Mark as NOT CRITICAL but add to RECOMMENDATIONS:
    * "Amount may be capped to user's outstanding debt/balance. This protects user from overpaying."
    * "Consider updating label: {{"label": "Amount to repay (max, capped to debt)"}}"
    * "Or add description: {{"description": "Final amount capped to outstanding balance"}}"
    * This improves clarity but is not security-critical (cap protects user)
  → **Counter-example (CRITICAL)**: If user can be charged MORE than they specify (amount multiplied/increased) → CRITICAL
- ✅ **Funds always sent to msg.sender (withdraw/claim/redeem functions)** - If a function:
  1. Has no recipient parameter OR recipient parameter defaults to msg.sender
  2. Transfers tokens/ETH exclusively to msg.sender (the transaction signer)
  3. Code shows patterns like `transfer(msg.sender, amount)` or `recipient = msg.sender`
  → This is NOT CRITICAL to hide the recipient - user ALWAYS receives funds themselves
  → There is no risk of funds going to wrong address - hardcoded to caller
  → **Common patterns**: `withdraw()`, `claim()`, `claimRewards()`, `redeem()`, `unwrap()`, `unstake()`
  → **How to detect**: Look in source code for:
    * `transfer(msg.sender, ...)` or `safeTransfer(msg.sender, ...)`
    * `recipient = msg.sender` or `to = msg.sender`
    * No recipient parameter in function signature
    * Recipient parameter exists but code always uses msg.sender
  → **Example**:
    ```solidity
    function withdraw(uint256 amount) external {{
        balances[msg.sender] -= amount;
        token.transfer(msg.sender, amount);  // ✓ Always to caller
    }}
    // NOT critical - user always receives their own funds
    ```
  → **Action**: Mark as NOT CRITICAL but add to RECOMMENDATIONS:
    * "Function sends funds to msg.sender (caller). No recipient risk."
    * "Consider adding field: {{"path": "@.from", "label": "Beneficiary", "format": "addressName"}} for clarity"
    * This shows user they will receive funds to their own address (good UX)
  → **Counter-example (CRITICAL)**: If recipient CAN be different from msg.sender (user-supplied parameter) → CRITICAL to show
- ✅ **Cryptographically protected parameters (signed orders/meta-transactions)** - If a parameter:
  1. Is part of a struct that is hashed and signature-verified (e.g., EIP-712 signed orders)
  2. Cannot be changed by an attacker without making the signature validation fail and reverting the transaction
  3. Is validated via `ECDSA.recover()`, `isValidSignature()`, or similar cryptographic check
  → This is NOT CRITICAL to hide - the parameter is tamper-proof
  → An attacker cannot modify it without the private key that created the signature
  → **Common patterns**: Limit orders (0x, 1inch, CoW), meta-transactions, signed permits
  → **How to detect**: Look for signature validation in the code:
    * `orderHash = order.hash()` or similar EIP-712 hashing
    * `isValidSignature(signer, hash, signature)` or `ECDSA.recover(hash, signature) == signer`
    * If validation fails, transaction reverts with signature error
  → **Example**:
    ```solidity
    struct Order {{
        address maker;      // ✓ Protected by signature
        address receiver;   // ✓ Protected by signature
        uint256 amount;     // ✓ Protected by signature
        // ...
    }}

    function fillOrder(Order calldata order, bytes calldata signature) external {{
        bytes32 orderHash = order.hash();
        if (!isValidSignature(order.maker, orderHash, signature)) revert BadSignature();
        // If attacker changes order.receiver, hash changes → signature invalid → reverts
    }}
    // NOT critical to hide order.maker or order.receiver - they're signed
    ```
  → **Action**: Mark as NOT CRITICAL but add to RECOMMENDATIONS:
    * "Parameter is cryptographically protected by signature validation and cannot be tampered with"
    * "Consider adding informational field showing this is a signed order for better UX"
  → **Counter-example (CRITICAL)**: If the parameter is NOT signature-verified OR can be modified after signature check → CRITICAL
- ✅ **Bundled permit/approval parameters** - If a function:
  1. Has a `permit` or `approval` parameter that is excluded from display
  2. Executes permit/approval logic (e.g., `tryPermit()`, `permit()`, `approve()`)
  3. Performs OTHER actions beyond just approval (swap, deposit, stake, etc.)
  4. The approval is consumed atomically in the SAME transaction
  → This is NOT critical - the permit is an implementation detail for the main action
  → Users care about the MAIN ACTION (swap, deposit), not the approval mechanism
  → The approval scope is limited to this transaction and consumed immediately
  → Common patterns: `permitAndCall()`, `swapWithPermit()`, `depositWithPermit()`
  → **Example**:
    ```solidity
    function permitAndCall(bytes calldata permit, bytes calldata action) external {{
        IERC20(address(bytes20(permit))).tryPermit(permit[20:]);  // ✓ Hidden permit
        // ... then execute main action (swap, deposit, etc.)
    }}
    // NOT critical - permit is bundled with main action
    ```
  → **Counter-example (CRITICAL)**: Standalone `approve()` or `permit()` function with no other action → MUST show token/spender/amount
  → Only flag as critical if permit/approval is the SOLE purpose of the function
- ✅ **Bitmask flags parameters** - If source code shows bitwise AND operations (e.g., `flags & _SHOULD_CLAIM != 0`), ERC-7730 spec CANNOT display these (enum format doesn't support bitwise operations or multi-flag combinations). This is a SPEC LIMITATION, NOT critical. Add to "Parameters that cannot be clear signed" section with explanation and detected pattern.
- ✅ **ETH/WETH wrapping scenarios** - When transaction `value` is non-zero (user sends ETH) but `tokenIn` parameter is WETH, this is VALID if the function automatically wraps ETH→WETH. Common in DEX functions like swapExactETHForTokens. The user KNOWS they're sending ETH (shown in wallet UI), and seeing WETH in the clear signing is correct because that's what the contract receives after wrapping
- ✅ Internal approvals/transfers done BY the protocol during execution (if not triggered by user params)
- ✅ Recipient being a constant/sentinel value - as long as user receives tokens
- ✅ Contract balance logic - implementation detail
- ✅ Internal routing - users don't care HOW swap happens
- ✅ ANY parameter regular users wouldn't understand without reading contract source code (Solidity/Vyper)
- ✅ State changes that cannot be predicted from function parameters alone
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
- "Amount parameter may exceed actual transfer (capped to user's debt/balance)" → NOT CRITICAL. Example: Aave `repay(amount)` where `paybackAmount = min(amount, userDebt)` and transfer uses `paybackAmount`. User signs 1000 USDC repay but only owes 500 USDC - contract caps to 500 USDC. This PROTECTS user from overpaying. User cannot lose MORE than they owe/have. The cap is beneficial. Add to RECOMMENDATIONS: "Amount may be capped to outstanding debt/balance. Consider updating label to {{"label": "Amount to repay (max, capped to debt)"}} for clarity." NOT in critical issues. Similar for: capped `withdraw()`, capped `redeem()`, any max-based amount.
- "No beneficiary field but function sends to msg.sender" → NOT CRITICAL. Example: `migrate()` function that burns user's CHSB tokens and mints BORG tokens to msg.sender. Code shows `token.mint(msg.sender, amount)` - user ALWAYS receives funds to their own address, no recipient parameter exists or needed. No risk of funds going elsewhere. Add to RECOMMENDATIONS: "Function sends output to msg.sender (caller). Consider adding {{"path": "@.from", "label": "Beneficiary", "format": "addressName"}} for clarity." NOT in critical issues. Similar for: `withdraw()`, `claim()`, `unwrap()`, `redeem()`, `unstake()`.
- "order.maker or order.receiver hidden but validated by signature" → NOT CRITICAL. Example: `fillOrder(Order calldata order, bytes signature)` where order struct is EIP-712 hashed and signature validated. If attacker modifies order.maker or order.receiver, the hash changes and signature validation fails, reverting the transaction. These parameters are cryptographically tamper-proof. Add to RECOMMENDATIONS: "Parameters are signature-protected and cannot be tampered with. Consider adding informational field for UX." NOT in critical issues.
- "Missing sqrtPriceLimit parameter" → NOT CRITICAL (technical)
- "Missing liquidity parameter" → NOT CRITICAL if can only be shown as incomprehensible large number. Example: displaying `liquidity` as `1582938471982347` is meaningless - users cannot verify if this is correct without knowing the formula, pool state, and price ranges. Similar for `sqrtPriceX96`, `tick`, `feeGrowthGlobal0X128` - these are COMPREHENSION LIMITATIONS, add to spec limitations section.
- "Showing a max or min amount rather than exact ones" → NOT CRITICAL (actual amount is computed on-chain, not available in inputs)
- "Missing actual spend amount for max-based swaps" → NOT CRITICAL (that's how max-based swaps work - you specify max, actual is computed)
- "Bitpacked/flags parameters excluded but control behavior" → NOT CRITICAL if can only be shown as incomprehensible raw hex. **General pattern**: Any parameter that uses bitpacking (bit shifts, bit masks, flags) to control multiple behaviors in a single uint256 cannot be meaningfully displayed to users. **Example**: `cancelOrders(traits[], orderHashes[])` where `traits` parameter controls operation mode (e.g., single item vs batch/mass operation, using bit flags like `useBitInvalidator()`). AI might say: "traits excluded but controls whether X or Y mode is used - critical behavior difference". BUT: displaying as `{{"path": "traits.[]", "format": "raw"}}` would show `0x00000000000000000000000000000000000000000000000000000000000001a4` - users CANNOT understand what this hex means or determine operation mode from it. Showing raw value does NOT help users verify the behavior. This applies to ANY bitpacked parameter. This is a COMPREHENSION LIMITATION - add to spec limitations section with explanation: "[Parameter name] bitpacked parameter controls [behavior description] but cannot be meaningfully displayed. Users cannot determine [specific modes/options] from raw hex." NOT in critical issues.
- "tokenAmount uses 'token' parameter instead of 'tokenPath'" → NOT CRITICAL. Using `"token": "0x..."` is valid for hardcoded token addresses (e.g., migration contracts that only operate on one specific token like CHSB). This is an alternative to `"tokenPath"` for fixed-token functions.
- "tokenAmount without tokenPath when token address cannot be determined from inputs" → NOT CRITICAL if function ONLY supports native ETH OR destination token is not in inputs (computed on-chain) OR the tokena ddress cannot be determined from the inputs dur to a 7730 limitation AND has nativeCurrencyAddress (add WARNING in detailed report explaining the limitation)
- "Token amount displayed as raw format instead of tokenAmount" → NOT CRITICAL if the token address cannot be determined from function inputs (e.g., output token computed from pools/routes). This is an acceptable concession. Only mention in recommendations: "User will see raw amount without token symbol/decimals because output token cannot be determined from inputs."
- "Type mismatch: uint256 displayed as addressName" → NOT CRITICAL (valid casting, e.g., pools.[-1] as uint256 can be cast to address by taking 20 bytes)
- "Type mismatch: bytes32 displayed as addressName" → NOT CRITICAL (valid casting, bytes32 can be interpreted as address)
- "Bitmask flags parameter not displayed" → NOT CRITICAL if source code shows bitwise AND operations (e.g., `flags & _SHOULD_CLAIM`) because ERC-7730 spec cannot display bitmasks (add to "Parameters that cannot be clear signed" section with explanation)
- "Output token determined by pool/DEX not shown" → NOT CRITICAL (SPEC LIMITATION). Example: `minReturn` in `ethUnoswap` where DEX/pool determines output token. Cannot reliably map to specific ERC20 address. Add to spec limitations section.
- "Arbitrary low-level call details not shown" → NOT CRITICAL. Multicall/delegatecall to self with arbitrary actions - users understand these are generic execution functions, no need to decode arbitrary calldata.
- "Nested calldata parameter excluded or shown as raw" → NOT CRITICAL. **MULTI-SCREEN CLEAR SIGNING**: When a function contains nested calldata (e.g., `action` bytes passed to delegatecall/call), the nested call gets decoded on SUBSEQUENT screens using its own ERC-7730 descriptor. Example: `permitAndCall(permit, action)` shows "Execute with permit" on screen 1, then the decoded swap/transfer from action bytes on screens 2-3. Whether the outer descriptor uses `{{"format": "calldata", "calleePath": "@.to"}}` or excludes the calldata parameter entirely is fine - users WILL see the nested call details on later screens. DO NOT flag as critical. The outer function only needs to show what's relevant at its level.
- "Recipient field without senderAddress param when source code has zero-check fallback" → NOT CRITICAL but add WARNING in detailed report recommending `"senderAddress": ["0x0000000000000000000000000000000000000000"]` to handle zero address fallback to msg.sender (e.g., when code shows `recipient = (param == address(0)) ? msg.sender : param`)
- "Non-payable function shows ETH as possible input (nativeCurrencyAddress present)" → NOT CRITICAL (UX improvement only). Transaction will revert if user tries to send ETH to non-payable function - no funds lost. UI/frontend likely prevents this. Add to RECOMMENDATIONS: "Consider removing nativeCurrencyAddress for better UX" but do NOT flag as critical.
- "Enum references $.metadata.enums instead of $.metadata.constants" → NOT CRITICAL. Both `$.metadata.enums.*` and `$.metadata.constants.*` are valid paths for enum $ref. Example: `"$ref": "$.metadata.enums.interestRateMode"` is correct.

BE STRICT. When in doubt, DO NOT flag as critical.

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

**⚠️ ALWAYS INCLUDE THIS SECTION - Even if no critical issues found!**

**CRITICAL FORMATTING REQUIREMENTS - READ CAREFULLY:**

✅ **USE BULLET POINTS with dashes (-), NOT numbered lists**
✅ **Each recommendation must be a COMPLETE, STANDALONE sentence**
✅ **Each bullet point must END with a period (.)**
✅ **DO NOT use colons (:) at the end of recommendations**
✅ **DO NOT start with numbers like "1.", "2.", "3."**

**How to write recommendations:**

**Three types of recommendations (include ALL that apply):**
1. **Fixes for critical issues** - For each critical issue from "Issues Found" section, write ONE bullet point that:
   - States the fix clearly
   - Includes the specific code/field to add or change
   - Is a complete sentence ending with a period

2. **Spec limitations** - For parameters that CANNOT be clear signed due to ERC-7730 limitations (e.g., bitmask flags):
   - These do NOT go in "Issues Found" section
   - List them here in Recommendations with full explanation
   - Follow the "ERC-7730 SPEC LIMITATIONS" format below
   - **ALWAYS include these even when no critical issues exist**

3. **Optional improvements** - Even when descriptor is correct, suggest UX enhancements:
   - Adding senderAddress parameter for zero-check fallbacks
   - Better label wording
   - Additional helpful fields
   - **Include these even when no critical issues exist**

**GOOD EXAMPLES (with critical issues):**
```markdown
- **Add msg.value display:** Include a field with `"path": "@.value"`, `"label": "Fee Amount"`, and `"format": "amount"` in the fields array to show the native ETH fee being sent.
- **Fix inverted token addresses:** Swap the tokenPath values so `fromAmount` references `#.tokenIn` and `toAmount` references `#.tokenOut`.
- **Show recipient address:** Add a field with `"path": "#.recipient"`, `"label": "Recipient"`, and `"format": "addressName"` to display where tokens are sent.
```

**GOOD EXAMPLES (no critical issues, but still recommendations):**
```markdown
- **Output token cannot be clear signed:** The `minReturn` field displays the minimum amount to receive, but the output token is determined by the pool/DEX address and not available as a function input, so ERC-7730 cannot reliably map this to a specific ERC20 address with tokenPath.
- **(Optional) Add senderAddress parameter:** Consider adding `"senderAddress": ["0x0000000000000000000000000000000000000000"]` to the recipient field to handle the zero-address fallback pattern detected in the source code where `recipient == address(0) ? msg.sender : recipient`.
- **(Optional) Improve label clarity:** Consider changing the label from "To" to "Recipient Address" for better user clarity.
```

**BAD EXAMPLES (DO NOT DO THIS):**
```markdown
1. Add an explicit field showing msg.value:
2. Example snippet to include in fields:
3. (Optional) If maintainers want...
4. ---
```

**For optional/advanced recommendations:**
- Still use bullet points (-)
- Mark them as "(Optional)" at the start
- Keep them complete sentences

**⚠️ CRITICAL - ERC-7730 SPEC LIMITATIONS:**

If a critical parameter **CANNOT be clear signed** using the current ERC-7730 specification, you **MUST** explicitly state this with a complete explanation.

**Common spec limitations to detect:**
1. **Bitmask flags** - Parameter used with bitwise AND operations (e.g., `flags & _SHOULD_CLAIM != 0`)
   - Source code pattern: `if (param & CONSTANT != 0)` or `param & MASK`
   - ERC-7730's enum format only supports simple 1:1 value→label mappings
   - Cannot test individual bits or display multiple flag combinations
   - Example: `flags = 0x06` = REQUIRES_EXTRA_ETH + SHOULD_CLAIM cannot be shown as "REQUIRES_EXTRA_ETH, SHOULD_CLAIM"
2. **Deeply nested arrays** - Arrays of structs containing arrays (e.g., `path[].orders[].amounts[]`)
3. **Dynamic data structures** - Data computed on-chain, not in inputs
4. **Complex tuples** - Multi-level struct nesting beyond ERC-7730 path capabilities

**Required format for unsupported parameters:**
- **[Parameter name] cannot be clear signed:** This parameter cannot be displayed with current ERC-7730 spec because [explain the specific limitation, e.g., "it is a bitmask with bitwise operations, and ERC-7730's enum format only supports simple value→label mappings without bitwise AND support"].
- **Why this matters:** [Explain what information the user is missing and the security implications, e.g., "Users cannot see which behavior flags are enabled (SHOULD_CLAIM, REQUIRES_EXTRA_ETH, PARTIAL_FILL), affecting token routing and ETH requirements"]
- **Detected pattern:** [If applicable, show the code pattern that proves it's a bitmask, e.g., "Source code shows: `if (flags & _SHOULD_CLAIM != 0)` and `if (flags & _REQUIRES_EXTRA_ETH != 0)`"]

**IMPORTANT - ALWAYS PROVIDE RECOMMENDATIONS:**

Even if there are **NO critical issues**, you MUST still provide recommendations in this section. Include:
- **Spec limitations**: Parameters that cannot be clear signed (bitmask flags, output tokens from pools, packed data, etc.)
- **Optional improvements**: Better labels, adding senderAddress parameter, display enhancements, etc.
- **Best practices**: Suggestions that improve UX even if not critical

**If truly no recommendations exist** (rare), write only:

**No additional recommendations - descriptor is comprehensive.**

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

**DO NOT include spec limitations here:**
- Parameters that CANNOT be clear signed due to ERC-7730 spec limitations (e.g., bitmask flags) should NOT be listed as critical issues
- Spec limitations go in the "Key Recommendations" section under "Overall Assessment" (section 6)
- This section is ONLY for issues that CAN be fixed by updating the ERC-7730 descriptor

{f"⚠️ **NO HISTORICAL TRANSACTIONS FOUND** - This selector has no transaction history. Analysis is based on source code and function signature only. Validation of actual on-chain behavior is not possible without transaction data.\n\n" if not decoded_transactions else ""}**Check for:**
- Token addresses shown are inverted/incorrect vs receipt_logs
- Amount values mapped to wrong tokens
- Critical parameters shown with misleading labels
- Hidden information in receipt_logs that should be shown
- Approvals not disclosed to users
- Mismatch between displayed intent and actual token movements in logs
- **Broken `$ref` references** - If format references `$.display.definitions.X` or `$.metadata.constants.Y` that don't exist, this is CRITICAL (display will fail)
- **Input parameter path mismatch** - ERC-7730 references parameter paths that don't match the ABI (wrong names, wrong nesting, non-existent fields)
- **Format validation failures**:
  * **tokenAmount without token specification**: Field has `"format": "tokenAmount"` but missing BOTH `"tokenPath"` AND `"token"` in params
    - → Token can be specified in TWO ways:
      1. **Dynamic (from parameter)**: `"tokenPath": "paramName"` - token address comes from function input
      2. **Fixed (hardcoded)**: `"token": "0x..."` - for migration contracts or functions operating on single specific token
    - → CRITICAL if NEITHER is present **UNLESS** one of these exceptions applies:
      1. Function ONLY supports native ETH (check source code: no ERC20 support, hardcoded ETH) AND has `nativeCurrencyAddress`
      2. Token address is NOT in function inputs (computed from pool/DEX on-chain) AND has `nativeCurrencyAddress`
    - → If exception 2 applies (token determined by pool): This is a **SPEC LIMITATION** - add to "Parameters that cannot be clear signed" section, NOT to critical issues
  * **nftName without collectionPath**: Field has `"format": "nftName"` but missing `"collectionPath"` in params → CRITICAL
  * **enum without reference**: Field has `"format": "enum"` but missing `$ref` to metadata.constants OR metadata.enums → CRITICAL
  * **Wrong format type**: Using wrong format (e.g., "amount" for ERC20 token, or "tokenAmount" without tokenPath)
    - **EXCEPTION - Type casting uint256/bytes32 ↔ address**: Using `"addressName"` format on `uint256`, `bytes32`, or `bytes20` ABI type is VALID (casting is supported). Similarly, using numeric formats on `address` type is valid. These are NOT critical type mismatches.
    - **EXCEPTION - Token amount as "raw" when token cannot be determined**: If a field displays a token amount (e.g., amountOut, minReceive) but uses `"format": "raw"` instead of `"tokenAmount"`, this is ACCEPTABLE if the token address cannot be determined from function inputs (e.g., output token is computed from pool addresses/routes). This is NOT critical - it's a known concession. Only mention in recommendations: "User will see raw amount without token symbol/decimals because output token cannot be determined from inputs."
  * Check BOTH the field params AND any $ref definition params for these requirements
- **Native ETH handling in payable functions (for what the user sends and all functions even non payable for what he receives)** (this is critical and nuanced):
  - **CRITICAL PRE-CHECK - Function payability**: Check the ABI signature to see if the MAIN function is `payable`
    * If the main function is NOT payable → `msg.value` is ALWAYS 0, even if it calls internal payable functions
    * Example: `uniswapV3SwapToWithPermit()` is NOT payable but calls `uniswapV3SwapTo()` which is payable
    * The internal payable function's ETH logic will NEVER execute because `msg.value == 0` always
    * **Do NOT flag missing @.value if the main function is not payable**
  - **IMPORTANT - Non-payable function showing ETH as option**: If a function is NOT payable but the descriptor includes `nativeCurrencyAddress` (showing ETH as possible input):
    * This is NOT CRITICAL - it's a UX improvement recommendation only
    * The transaction will revert if user tries to send ETH to a non-payable function (no funds lost)
    * The UI/frontend likely prevents this anyway
    * Add to RECOMMENDATIONS under "Display Issues": "Function is not payable but descriptor shows ETH as possible input. Consider removing nativeCurrencyAddress for better UX to prevent users from selecting ETH which would cause transaction to revert."
    * Do NOT add to critical issues
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
    * **Case 3 - Payable function that accepts native ETH (especially WETH deposit or similar)**:
      → **CRITICAL CHECK**: Does the ERC-7730 display the ETH amount being sent?
      → **If fields array is EMPTY or has NO amount fields** → CRITICAL (nothing is shown to user)
      → **If function ONLY accepts native ETH (no token parameter) and no @.value field exists** → CRITICAL
      → **If function accepts both tokens and ETH**: Only NOT critical if another amount field displays the same value (e.g., deposit(uint256 amount) where amount must equal msg.value)
      → Example FIX for payable functions with no inputs: `{{"path": "@.value", "label": "Amount", "format": "amount"}}`
    * **Case 4 - WRAPPER/FORWARDING PATTERN (INFORMATIONAL, not CRITICAL)**:
      → **Pattern detection**: If a payable function meets ALL these conditions:
        1. Function body does NOT manipulate `msg.value` in its own logic (no validation, no splitting, no storing)
        2. Function forwards the ENTIRE value via one of these patterns:
           - `delegatecall(...)` - automatically forwards msg.value
           - `.call{{value: msg.value}}(...)` - explicitly forwards full msg.value
           - `.call{{value: address(this).balance}}(...)` - forwards all received ETH
        3. Function does NOT display `@.value` in ERC-7730
      → **Why this is NOT critical**:
        * The value is forwarded entirely to a nested call
        * The nested call (typically decoded from a `bytes calldata` parameter like `action`, `data`, or `calls`) will have its own ERC-7730 descriptor
        * That nested descriptor SHOULD display `@.value`
        * Users see multiple clear signing screens: one for the wrapper, one for the nested call
        * The value is shown on the nested call's screen, not the wrapper's screen
        * Wallet UI also shows total transaction value regardless
      → **Example wrapper patterns**:
        ```solidity
        // Pattern A: delegatecall (auto-forwards value)
        function permitAndCall(bytes calldata action) external payable {{
            doPermit();
            assembly {{ delegatecall(gas(), address(), ...) }}  // ✓ Auto-forwards
        }}

        // Pattern B: explicit value forwarding
        function executeWithValue(bytes calldata data) external payable {{
            target.call{{value: msg.value}}(data);  // ✓ Explicitly forwards
        }}
        ```
      → **Counter-example (CRITICAL)**:
        ```solidity
        function swapWithFee(SwapData calldata desc) external payable {{
            require(msg.value == desc.amount);  // ❌ Uses msg.value in logic
            executor.call{{value: msg.value}}(data);
        }}
        // This IS critical because function validates msg.value
        ```
      → **Action to take**: Mark as INFORMATIONAL (not CRITICAL) with note: "This appears to be a wrapper function that forwards execution and value entirely. Verify that nested call descriptors display @.value."
      → **DO NOT flag as critical** if this pattern is detected
  - Check source code and receipt_logs (if available) to determine which case applies. Sometimes even if sentinels exist, the code does not allow native transfer even if the function is payable.
  - **KEY**: When checking for nativeCurrencyAddress, follow $ref references to definitions - it can be in either place
  - Only flag as critical if native ETH is actually being transferred AND display cannot show it
- Amounts are displayed twice
- Spelling/grammar errors in labels or intent
- **msg.value representation** - WHEN to use each approach:
   - **Use `@.value`**: When function ONLY accepts native ETH 
   - **Use input parameter**: When function has an amount parameter that EQUALS msg.value and can be also used for other tokens
   - **CRITICAL**: If payable function has no parameters AND no `@.value` field → user can't see amount being sent
- Labels and intents must not be longer than 20 characters

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
- **metadata.token redundancy** - If `metadata.token` exists BUT the contract has `name()`, `symbol()`, and `decimals()` functions in the ABI/source code, the metadata.token is redundant (wallets can fetch this info directly from the contract). Note this as a minor cleanup suggestion, not critical.
- **Missing senderAddress for zero-check fallback** - If source code shows conditional fallback pattern like `recipient = (param == address(0)) ? msg.sender : param` BUT the addressName field lacks `"senderAddress": ["0x0000000000000000000000000000000000000000"]` param, the wallet cannot properly display `@.from` when user passes zero address. Recommend adding `senderAddress` parameter.
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

**Include two types of recommendations:**
1. **Fixes for critical issues** - Specific actionable fixes for issues listed in section 2
2. **Spec limitations** - Parameters that CANNOT be clear signed (DO NOT list these in section 2)

- Recommendation 1 (be specific about how to fix critical issues)
- Recommendation 2 (be specific about parameter additions/corrections)
- Recommendation 3 (if needed)

**IMPORTANT - SPEC LIMITATIONS SECTION:**

If any parameter CANNOT be clear signed using the current ERC-7730 specification (e.g., bitmask flags), add them here (NOT in section 2 "Critical Issues"):

**Format for spec-limited parameters:**
- **Parameter [name] cannot be clear signed:** This parameter cannot be displayed with current ERC-7730 spec because [specific limitation].
- **Why this matters:** [What information the user is missing and security implications]
- **Detected pattern:** [Code evidence, e.g., "Source code shows bitwise operations: `if (flags & _SHOULD_CLAIM != 0)`"]

**Common spec limitations to detect:**
1. **Bitmask flags / Packed data** - Source code shows `param & CONSTANT` operations or bitwise shifts → ERC-7730 enum cannot display multiple flag combinations or extract packed values. Example: Bitpacked parameters like `traits`, `flags`, `options` with packed nonce/epoch/flags data
2. **Output token determined by pool/DEX** - Output token computed from pool address, not explicit in inputs → Cannot reliably map to specific ERC20 address. Example: `minReturn` in Uniswap pool swaps where pool determines output token
3. **Deeply nested arrays** - Path like `orders[].amounts[]` beyond spec capabilities
4. **Dynamic/computed data** - Values calculated on-chain, not in function inputs
5. **Arbitrary low-level calls** - Functions that execute arbitrary calldata (multicall, delegatecall to self) → Not necessary to decode arbitrary actions, users understand these are generic execution functions

**Example output:**
- **desc.flags cannot be clear signed:** This parameter is a bitmask combining multiple boolean flags (SHOULD_CLAIM=0x04, REQUIRES_EXTRA_ETH=0x02, PARTIAL_FILL=0x01). ERC-7730's enum format only supports simple 1:1 value→label mappings and cannot perform bitwise AND operations or display multiple flags simultaneously.
- **Why this matters:** Users cannot see which behavior flags are enabled, affecting token routing (SHOULD_CLAIM changes recipient), ETH requirements (REQUIRES_EXTRA_ETH allows extra msg.value), and partial fill logic.
- **Detected pattern:** Source code shows: `if (flags & _SHOULD_CLAIM != 0)`, `if (flags & _REQUIRES_EXTRA_ETH != 0)`, and `if (flags & _PARTIAL_FILL != 0)`

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
