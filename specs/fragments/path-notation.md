# ERC-7730 Path Notation Reference

This fragment defines the path notation syntax for referencing data in ERC-7730 metadata.

## Path Types

### 1. Field Paths (Direct ABI Parameters)
Reference function parameters directly by name.

**Syntax**: `"parameterName"`

**Examples**:
```json
"path": "to"           // References 'to' parameter
"path": "amount"       // References 'amount' parameter
"path": "recipient"    // References 'recipient' parameter
```

### 2. Container Paths (Transaction Metadata)
Reference transaction-level data using `@.` prefix.

**Syntax**: `"@.field"`

**Available Container Fields**:
- `@.to` - Transaction recipient address (contract being called)
- `@.from` - Transaction sender address (msg.sender)
- `@.value` - Native currency amount sent (msg.value)

**Examples**:
```json
"path": "@.to"         // The contract address being called
"path": "@.from"       // The sender's address (msg.sender)
"path": "@.value"      // ETH/native currency sent
```

### 3. Nested Field Paths
Access fields within structs using dot notation.

**Syntax**: `"structName.fieldName"`

**Example**:
```json
"path": "order.maker"          // order struct's maker field
"path": "swapData.recipient"   // swapData struct's recipient field
```

## Array Indexing

### Positive Indices
**Syntax**: `"arrayName[index]"`

- `[0]` - First element
- `[1]` - Second element
- etc.

**Examples**:
```json
"path": "tokens[0]"      // First token in array
"path": "amounts[1]"     // Second amount in array
```

### Negative Indices (VALID)
**Syntax**: `"arrayName[-index]"`

- `[-1]` - **Last element** in array
- `[-2]` - Second to last element
- etc.

**Examples**:
```json
"path": "tokens[-1]"     // Last token in array (final output token)
"path": "path[-1]"       // Last element in path array
```

**IMPORTANT**: Negative indices are STANDARD and VALID in ERC-7730. Do NOT flag as errors.

### Array Slicing
**Syntax**: `"arrayName[start:end]"`

- `[:]` - All elements
- `[1:]` - From second element to end
- `[:2]` - First two elements
- `[1:3]` - Elements at index 1 and 2

**Examples**:
```json
"path": "intermediateTokens[1:-1]"  // All middle tokens (exclude first and last)
"path": "amounts[:]"                // All amounts
```

## Special Path Use Cases

### Using @.from for Implied Recipients
When function doesn't have explicit recipient parameter but receiver is always `msg.sender`:

```json
{
  "path": "@.from",
  "label": "Recipient",
  "format": "addressName"
}
```

**When to use**: Swap/mint/transfer functions where output goes to caller.

### Using @.to as Token Address
For token-specific contracts where contract address IS the token address:

```json
{
  "path": "amount",
  "label": "Amount",
  "format": "tokenAmount",
  "params": {
    "tokenPath": "@.to"  // Contract being called is the token
  }
}
```

### Using @.value for Native Currency
Display native ETH/MATIC/etc sent with transaction:

```json
{
  "path": "@.value",
  "label": "Amount",
  "format": "tokenAmount",
  "params": {
    "tokenPath": "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"
  }
}
```

## Path Resolution Priority

1. **Field paths** - Check function ABI parameters first
2. **Container paths** - If `@.` prefix, resolve from transaction metadata
3. **Nested/Array paths** - Parse dot notation and array indices
4. **Invalid path** - If path doesn't resolve → CRITICAL ERROR

## Critical Validation Rules

1. All `path` fields MUST resolve to actual data
2. Array indices (positive or negative) MUST be within bounds
3. Container paths (`@.to`, `@.from`, `@.value`) are always valid
4. Nested paths MUST match struct definition
5. If path references non-existent field → CRITICAL ERROR
