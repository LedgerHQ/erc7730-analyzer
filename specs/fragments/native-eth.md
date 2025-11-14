# ERC-7730 Native Currency Handling

This fragment defines how to handle native currency (ETH, MATIC, etc.) in ERC-7730 metadata.

## nativeCurrencyAddress

The special address **0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE** represents the chain's native currency.

### Purpose
Used in `tokenPath` parameters to indicate native currency amounts (ETH on Ethereum, MATIC on Polygon, etc.)

### Usage Example
```json
{
  "path": "msg.value",
  "label": "Amount",
  "format": "tokenAmount",
  "params": {
    "tokenPath": "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"
  }
}
```

### Wallet Behavior
When `tokenPath` resolves to `0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE`:
- Use chain's native symbol (ETH, MATIC, BNB, etc.)
- Use chain's native decimals (typically 18)
- DO NOT attempt to fetch token metadata from blockchain

## msg.value Field

The `msg.value` field represents native currency sent with the transaction.

### Path Notation
- **Field path**: `"msg.value"`
- **Container path**: `"@.value"`

### Required Display
If transaction includes `msg.value > 0`, metadata MUST include a field displaying it:

```json
{
  "path": "msg.value",
  "label": "Amount Sent",
  "format": "tokenAmount",
  "params": {
    "tokenPath": "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"
  }
}
```

### Alternative: Using @.value
```json
{
  "path": "@.value",
  "label": "ETH Amount",
  "format": "tokenAmount",
  "params": {
    "tokenPath": "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"
  }
}
```

## ETH/WETH Wrapping Detection

### DO NOT Flag as Missing
When metadata describes WETH wrapping/unwrapping operations:
- `deposit()` with msg.value → minting WETH
- `withdraw(uint256)` → burning WETH for ETH

These are NOT missing native currency fields - they are intentional conversions.

### Characteristics of Wrapping Functions
- Function name: `deposit`, `withdraw`, `wrap`, `unwrap`
- No explicit token transfer parameters
- Uses `msg.value` (deposit) or returns ETH (withdraw)

## Critical Validation Rules

1. If `msg.value` path is used, `tokenPath` SHOULD reference native currency address
2. If function accepts native currency (payable), metadata MUST show `msg.value` or `@.value`
3. Exception: Wrapping functions (deposit/withdraw/wrap/unwrap) may omit display if intent is clear
4. NEVER flag wrapping/unwrapping as missing amount field
