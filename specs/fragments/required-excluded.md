# ERC-7730 Required and Excluded Fields

This fragment defines the `required` and `excluded` arrays that control which ABI parameters MUST be shown.

## Purpose

- **`required`**: Array of parameter names that MUST appear in `fields` array
- **`excluded`**: Array of parameter names that SHOULD NOT appear in `fields` array

## Schema Definition

```json
{
  "required": ["param1", "param2"],  // These MUST be in fields[]
  "excluded": ["param3", "param4"]   // These SHOULD NOT be in fields[]
}
```

## Required Array

### Purpose
Explicitly marks which ABI parameters MUST be displayed to the user for security.

### Example
```json
{
  "intent": "Approve Token",
  "required": ["spender", "amount"],
  "fields": [
    {
      "path": "spender",
      "label": "Spender",
      "format": "addressName"
    },
    {
      "path": "amount",
      "label": "Amount",
      "format": "tokenAmount",
      "params": {
        "tokenPath": "@.to"
      }
    }
  ]
}
```

### Validation Rules
1. Every parameter in `required` array MUST appear in `fields` array
2. If required parameter is missing from `fields` → **CRITICAL ERROR**
3. Common required parameters:
   - **Approval functions**: `spender`, `amount`
   - **Transfer functions**: `to`/`recipient`, `amount`/`value`
   - **Swap functions**: input token, input amount, output token (or use `[-1]`), minimum output
   - **Governance**: `proposalId`, `support`

## Excluded Array

### Purpose
Marks technical/internal parameters that should NOT be shown to users to reduce clutter.

### Example
```json
{
  "intent": "Swap Tokens",
  "excluded": ["deadline", "sqrtPriceLimitX96", "data"],
  "fields": [
    {
      "path": "tokenIn",
      "label": "Pay",
      "format": "addressName"
    },
    {
      "path": "amountIn",
      "label": "Amount In",
      "format": "tokenAmount",
      "params": {
        "tokenPath": "$.tokenIn"
      }
    },
    {
      "path": "path[-1]",
      "label": "Receive",
      "format": "addressName"
    },
    {
      "path": "amountOutMinimum",
      "label": "Minimum Received",
      "format": "tokenAmount",
      "params": {
        "tokenPath": "$.path[-1]"
      }
    }
  ]
}
```

### Validation Rules
1. Parameters in `excluded` array SHOULD NOT appear in `fields`
2. If excluded parameter appears in `fields` → **WARNING** (not critical, but raises question)
3. Common excluded parameters:
   - `deadline` - Transaction validity timestamp
   - `data` / `extraData` - Low-level call data
   - `sqrtPriceLimitX96` - DEX internal price calculation
   - `referralCode` - Tracking codes
   - `permitData` - Gasless approval signatures

## Combined Usage

### Full Example
```json
{
  "swapExactTokensForTokens(uint256,uint256,address[],address,uint256)": {
    "intent": "Swap Tokens",
    "required": ["amountIn", "amountOutMin", "path"],
    "excluded": ["to", "deadline"],
    "fields": [
      {
        "path": "path[0]",
        "label": "Pay Token",
        "format": "addressName"
      },
      {
        "path": "amountIn",
        "label": "Amount",
        "format": "tokenAmount",
        "params": {
          "tokenPath": "$.path[0]"
        }
      },
      {
        "path": "path[-1]",
        "label": "Receive Token",
        "format": "addressName"
      },
      {
        "path": "amountOutMin",
        "label": "Minimum Received",
        "format": "tokenAmount",
        "params": {
          "tokenPath": "$.path[-1]"
        }
      }
    ]
  }
}
```

**Note**: `to` is excluded because recipient is always `msg.sender` in this example. If showing receiver is critical, add it to `fields` with `@.from`.

## Critical Validation Rules

1. All parameters in `required` array MUST be in `fields` array
2. Missing required parameter → **CRITICAL ERROR**
3. Parameters in `excluded` appearing in `fields` → **WARNING**
4. If neither `required` nor `excluded` is specified, all parameters are optional
5. Security-critical parameters (amounts, recipients, approvals) SHOULD be in `required`
