# ERC-7730 Display Constraints and Hardware Wallet Limitations

This fragment defines hardware wallet display limitations and best practices for ERC-7730 metadata.

## Label Length Constraints

### Character Limits
Hardware wallets have small screens with strict display limits:

- **Ledger Nano S**: ~12-16 characters per line
- **Ledger Nano X**: ~20-25 characters per line
- **Trezor**: ~16-20 characters per line

### Best Practices for Labels
1. **Keep labels short**: 8-15 characters maximum
2. **Use abbreviations**: "Amt" instead of "Amount", "Rcpt" instead of "Recipient"
3. **Avoid redundancy**: Don't repeat info that's obvious from context
4. **Use title case**: "Token Address" not "TOKEN ADDRESS"

### Examples

**GOOD Labels**:
```json
"label": "To"
"label": "Amount"
"label": "Spender"
"label": "Min Received"
"label": "Token Out"
```

**BAD Labels** (too long):
```json
"label": "Recipient Address for Transfer"  // ❌ Too long
"label": "Minimum Amount of Tokens to Receive"  // ❌ Too long
"label": "The spender who will be approved"  // ❌ Too long
```

**BETTER Alternatives**:
```json
"label": "Recipient"      // ✅ Clear and concise
"label": "Min Received"   // ✅ Abbreviated
"label": "Approved To"    // ✅ Short and clear
```

## Intent Field

### Purpose
The `intent` field provides a user-friendly description of the transaction's purpose.

### Best Practices
1. **Use clear action verbs**: "Send", "Approve", "Swap", "Stake"
2. **Keep it short**: 2-4 words maximum
3. **User perspective**: What the user is doing, not technical function name
4. **Avoid jargon**: "Swap Tokens" not "Execute Multi-Hop Router Swap"

### Examples

| Function Name | ❌ Bad Intent | ✅ Good Intent |
|---------------|---------------|----------------|
| `transfer()` | "Transfer ERC20" | "Send" |
| `approve()` | "Set Approval" | "Approve Token" |
| `swapExactTokensForTokens()` | "Swap Exact Input" | "Swap Tokens" |
| `multicall()` | "Execute Multicall" | "Batch Actions" |
| `depositETH()` | "Deposit Ether" | "Deposit" |

## Field Order

### Display Priority
Fields are displayed **in the order they appear in the `fields` array**.

### Recommended Order
1. **Intent/Action** (shown as header)
2. **Primary amounts** (what user is sending)
3. **Primary addresses** (to/from)
4. **Secondary amounts** (min received, max slippage)
5. **Token addresses** (if not obvious from amount display)
6. **Optional parameters** (deadline, etc.)

### Example Order
```json
"fields": [
  // 1. What you're sending
  {
    "path": "amountIn",
    "label": "Pay",
    "format": "tokenAmount",
    "params": {"tokenPath": "$.tokenIn"}
  },
  // 2. What you're receiving
  {
    "path": "amountOutMin",
    "label": "Receive (min)",
    "format": "tokenAmount",
    "params": {"tokenPath": "$.tokenOut"}
  },
  // 3. Who receives it
  {
    "path": "@.from",
    "label": "Recipient",
    "format": "addressName"
  }
]
```

## Hardware Wallet Specific Constraints

### Screen Real Estate
- **Maximum fields to show**: 5-7 fields recommended
- **More than 10 fields**: Consider splitting into multiple transactions or using `excluded`
- **Scrolling**: Users must scroll through fields - keep count manageable

### Address Display
- **Checksummed format**: Always display addresses with checksum (0xAbC...)
- **ENS resolution**: MAY show ENS name if available, but MUST show address too
- **Truncation**: Long addresses may be truncated (0xAbc...xyz)

### Amount Display
- **Decimals**: Show appropriate precision (2-4 decimals for currencies, 8+ for crypto)
- **Large numbers**: Use scientific notation or abbreviations (1.5M, 2.3K)
- **Zero amounts**: MUST still be displayed if in `required` array

## metadata.token Field

### When to Use
The `metadata.token` field provides token information for single-token contracts (like ERC-20).

### Example
```json
"metadata": {
  "token": {
    "address": "@.to",
    "decimals": 6,
    "symbol": "USDT"
  }
}
```

### Validation Rule: No Calls in Contract
**CRITICAL**: If the contract being described has multiple functions (contract calls), `metadata.token` SHOULD NOT exist.

**Reason**: `metadata.token` implies this is a simple token contract. If there are multiple transaction types (approve, transfer, swap, etc.), token information should be specified per-field using `tokenPath` parameters.

**Exception**: If ALL functions in the contract deal with the same single token, `metadata.token` is acceptable.

## Critical Validation Rules

1. **Label length**: SHOULD be under 15 characters
2. **Intent**: MUST be present and user-friendly (not technical function name)
3. **Field count**: More than 10 fields → WARNING (consider reducing)
4. **metadata.token**: SHOULD NOT exist if contract has multiple function types
5. **Field order**: Most important fields (amounts, recipients) SHOULD come first
