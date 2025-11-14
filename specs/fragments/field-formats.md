# ERC-7730 Field Format Types

This fragment contains the official format types supported by ERC-7730 for field display formatting.

## Supported Format Types

### 1. **raw** - Display as-is
- Shows the value without any transformation
- Default format if none specified

### 2. **addressName** - EVM Address
- **Type**: bytes20, string, or bytes
- Displays as checksummed address with optional ENS resolution
- Wallets MAY resolve to human-readable name

### 3. **calldata** - Function Call Data
- **Type**: bytes
- Decodes and displays nested function calls with parameters

### 4. **amount** - Generic Numeric Amount
- **Type**: uint*, int*
- **REQUIRED PARAMS**:
  - `"base"` (string) - Unit symbol (e.g., "ETH", "BTC", "USD")
- **OPTIONAL PARAMS**:
  - `"decimals"` (uint8) - Number of decimals (default: 0)

### 5. **tokenAmount** - Token Amount with Metadata
- **Type**: uint*, int*
- **REQUIRED PARAMS**:
  - `"tokenPath"` (string) - Path to token address field
- Wallet MUST fetch token decimals and symbol from blockchain
- If token address is native currency (0xEeee...eeee), use chain's native symbol

### 6. **nftName** - NFT Display
- **Type**: uint*, bytes
- **REQUIRED PARAMS**:
  - `"collectionPath"` (string) - Path to NFT collection address
- Displays as "Collection Name #tokenId"

### 7. **date** - Unix Timestamp
- **Type**: uint*
- **ENCODING**: MUST be Unix timestamp (seconds since epoch)
- **Display**: Human-readable date/time (e.g., "2024-01-15 14:30:00 UTC")

### 8. **duration** - Time Duration
- **Type**: uint*
- Displays as human-readable duration (e.g., "2 days 5 hours")

### 9. **percentage** - Percentage Value
- **Type**: uint*, int*
- **REQUIRED PARAM**:
  - `"base"` (string) - MUST be "%"
- **OPTIONAL PARAMS**:
  - `"decimals"` (uint8) - Number of decimals

### 10. **unit** - Custom Unit Value
- **Type**: uint*, int*
- **REQUIRED PARAM**:
  - `"base"` (string) - Unit symbol (SI unit, "bps", etc.)
- **OPTIONAL PARAMS**:
  - `"decimals"` (uint8) - Number of decimals

### 11. **enum** - Enumeration Value
- **Type**: uint8
- **REQUIRED PARAMS**:
  - `"$ref"` (string) - Reference to enum definition
- Maps integer to human-readable enum label

## Format Parameter Requirements

### tokenAmount Parameters
```json
{
  "format": "tokenAmount",
  "params": {
    "tokenPath": "@.to"  // Container path (@.to, @.from) or field path
  }
}
```

### amount Parameters
```json
{
  "format": "amount",
  "params": {
    "base": "USD",
    "decimals": 2
  }
}
```

### nftName Parameters
```json
{
  "format": "nftName",
  "params": {
    "collectionPath": "$.collection"
  }
}
```

## Critical Validation Rules

1. **tokenAmount** MUST have `tokenPath` parameter
2. **amount** MUST have `base` parameter
3. **nftName** MUST have `collectionPath` parameter
4. **date** values MUST be Unix timestamps (seconds, not milliseconds)
5. **percentage** and **unit** MUST have `base` parameter
6. If format requires parameters but they're missing → CRITICAL ERROR
