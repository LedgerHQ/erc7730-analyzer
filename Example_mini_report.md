# 🔴 Critical Issues Report

**Generated:** 2025-10-24 20:54:19
**Contract ID:** Uniswap v3 Router 2
**Chain IDs:** 1

---

## Critical Issues Summary

| Function | Selector | Status | Link |
|----------|----------|--------|------|
| `exactInput` | `0xb858183f` | ✅ No Critical Issues | [View](#critical-b858183f) |
| `exactInputSingle` | `0x04e45aaf` | 🔴 Format's "required" array references a non-existent path "params.amountOutMinini... | [View](#critical-04e45aaf) |
| `exactOutput` | `0x09b81346` | 🔴 amountInMaximum is labeled with tokenPath params.path.[0:20] (first address in p... | [View](#critical-09b81346) |
| `exactOutputSingle` | `0x5023b4df` | ✅ No Critical Issues | [View](#critical-5023b4df) |
| `swapExactTokensForTokens` | `0x472b43f3` | 🔴 Missing recipient ("to") in display: the function's `to` parameter receives the ... | [View](#critical-472b43f3) |
| `swapTokensForExactTokens` | `0x42712a67` | 🔴 Missing recipient display: ERC-7730 format does NOT display the `to` input param... | [View](#critical-42712a67) |

---

## 📋 Detailed Analysis

Found **4 function(s)** with critical issues that require immediate attention.

---

## <a id="critical-b858183f"></a> ✅ exactInput((bytes,address,uint256,uint256))

**Selector:** `0xb858183f`

**Contract Address:** `0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45` | **Chain ID:** 1

<details>
<summary><b>📋 ERC-7730 Format Definition</b></summary>

```json
{
  "format": {
    "$id": "exactInput",
    "intent": "Swap",
    "fields": [
      {
        "path": "params.amountIn",
        "label": "Amount to Send",
        "format": "tokenAmount",
        "params": {
          "tokenPath": "params.path.[0:20]"
        }
      },
      {
        "path": "params.amountOutMinimum",
        "label": "Minimum amount to Receive",
        "format": "tokenAmount",
        "params": {
          "tokenPath": "params.path.[-20:]"
        }
      },
      {
        "path": "params.recipient",
        "label": "Beneficiary",
        "format": "addressName",
        "params": {
          "types": [
            "eoa"
          ],
          "sources": [
            "local",
            "ens"
          ]
        }
      }
    ],
    "required": [
      "params.amountIn",
      "params.amountOutMinimum",
      "params.recipient"
    ]
  }
}
```

</details>

### ✅ No Critical Issues

No critical issues found.

---

## <a id="critical-04e45aaf"></a> 🔴 exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))

**Selector:** `0x04e45aaf`

**Contract Address:** `0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45` | **Chain ID:** 1

<details>
<summary><b>📋 ERC-7730 Format Definition</b></summary>

```json
{
  "format": {
    "$id": "exactInputSingle",
    "intent": "swap",
    "fields": [
      {
        "path": "params.amountIn",
        "label": "Send",
        "format": "tokenAmount",
        "params": {
          "tokenPath": "params.tokenIn"
        }
      },
      {
        "path": "params.amountOutMinimum",
        "label": "Receive Minimum",
        "format": "tokenAmount",
        "params": {
          "tokenPath": "params.tokenOut"
        }
      },
      {
        "path": "params.fee",
        "label": "Uniswap fee",
        "format": "unit",
        "params": {
          "decimals": 4,
          "base": "%",
          "prefix": false
        }
      },
      {
        "path": "params.recipient",
        "label": "Beneficiary",
        "format": "addressName",
        "params": {
          "types": [
            "eoa"
          ],
          "sources": [
            "local",
            "ens"
          ]
        }
      }
    ],
    "required": [
      "params.amountIn",
      "params.amountOutMininimum",
      "params.fee",
      "params.recipient"
    ]
  }
}
```

</details>

### 🔴 Critical Issues

1. Format's "required" array references a non-existent path "params.amountOutMininimum" (typo). This is a parameter path mismatch / broken reference and can cause the display/validation to fail or mis-report that a required field is missing.

### 💡 Recommendations

1. Correct the required entry to "params.amountOutMinimum".
2. Re-run metadata validation and UI rendering tests to ensure the format no longer fails schema/validation checks.
3. ---

---

## <a id="critical-09b81346"></a> 🔴 exactOutput((bytes,address,uint256,uint256))

**Selector:** `0x09b81346`

**Contract Address:** `0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45` | **Chain ID:** 1

<details>
<summary><b>📋 ERC-7730 Format Definition</b></summary>

```json
{
  "format": {
    "$id": "exactOutput",
    "intent": "Swap",
    "fields": [
      {
        "path": "params.amountInMaximum",
        "label": "Maximum Amount to Send",
        "format": "tokenAmount",
        "params": {
          "tokenPath": "params.path.[0:20]"
        }
      },
      {
        "path": "params.amountOut",
        "label": "Amount to Receive",
        "format": "tokenAmount",
        "params": {
          "tokenPath": "params.path.[-20:]"
        }
      },
      {
        "path": "params.recipient",
        "label": "Beneficiary",
        "format": "addressName",
        "params": {
          "types": [
            "eoa"
          ],
          "sources": [
            "local",
            "ens"
          ]
        }
      }
    ],
    "required": [
      "params.amountInMaximum",
      "params.amountOut",
      "params.recipient"
    ]
  }
}
```

</details>

### 🔴 Critical Issues

1. amountInMaximum is labeled with tokenPath params.path.[0:20] (first address in path) but the contract treats the first address as tokenOut — this displays the input token as the output token (IN/OUT inverted).
2. amountOut is labeled with tokenPath params.path.[-20:] (last address in path) but the contract treats the last address as tokenIn — this displays the output token as the input token (IN/OUT inverted).

### 💡 Recommendations

1. Swap the tokenPath indices: show params.amountInMaximum using params.path.[-20:] (input token) and show params.amountOut using params.path.[0:20] (output token).
2. Add a unit test / sample rendering to verify displayed token addresses and symbols match receipt_logs for a real swap path.

---

## <a id="critical-5023b4df"></a> ✅ exactOutputSingle((address,address,uint24,address,uint256,uint256,uint160))

**Selector:** `0x5023b4df`

**Contract Address:** `0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45` | **Chain ID:** 1

<details>
<summary><b>📋 ERC-7730 Format Definition</b></summary>

```json
{
  "format": {
    "$id": "exactOutputSingle",
    "intent": "Swap",
    "fields": [
      {
        "path": "params.amountInMaximum",
        "label": "Maximum Amount to Send",
        "format": "tokenAmount",
        "params": {
          "tokenPath": "params.tokenIn"
        }
      },
      {
        "path": "params.amountOut",
        "label": "Amount to Receive",
        "format": "tokenAmount",
        "params": {
          "tokenPath": "params.tokenOut"
        }
      },
      {
        "path": "params.fee",
        "label": "Uniswap fee",
        "format": "unit",
        "params": {
          "decimals": 4,
          "base": "%",
          "prefix": false
        }
      },
      {
        "path": "params.recipient",
        "label": "Beneficiary",
        "format": "addressName",
        "params": {
          "types": [
            "eoa"
          ],
          "sources": [
            "local",
            "ens"
          ]
        }
      }
    ]
  }
}
```

</details>

### ✅ No Critical Issues

No critical issues found.

---

## <a id="critical-472b43f3"></a> 🔴 swapExactTokensForTokens(uint256,uint256,address[],address)

**Selector:** `0x472b43f3`

**Contract Address:** `0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45` | **Chain ID:** 1

<details>
<summary><b>📋 ERC-7730 Format Definition</b></summary>

```json
{
  "format": {
    "$id": "swapExactTokensForTokens",
    "intent": "Swap",
    "fields": [
      {
        "path": "amountIn",
        "label": "Amount to Send",
        "format": "tokenAmount",
        "params": {
          "tokenPath": "path.[0]"
        }
      },
      {
        "path": "amountOutMin",
        "label": "Minimum amount to Receive",
        "format": "tokenAmount",
        "params": {
          "tokenPath": "path.[-1]"
        }
      }
    ]
  }
}
```

</details>

### 🔴 Critical Issues

1. Missing recipient ("to") in display: the function's `to` parameter receives the final output tokens but ERC-7730 format does not show the recipient; users may be surprised about where received tokens are sent (including sentinel values that resolve to msg.sender or address(this)).
2. No handling/display for sentinel recipient values (MSG_SENDER / ADDRESS_THIS) — UI could show a different resolved recipient than the literal address input, which is not communicated.

### 💡 Recommendations

1. Add a "Recipient" field mapped to `to` (format: address) in the ERC-7730 format.
2. Display resolved recipient when `to` equals sentinel constants (e.g., show "Your address" for MSG_SENDER, "This contract" for ADDRESS_THIS) and indicate sentinel behaviour.
3. Optionally expose a note if `amountIn == 0` (CONTRACT_BALANCE sentinel) so users know "Uses contract balance" rather than a numeric input.
4. ---

---

## <a id="critical-42712a67"></a> 🔴 swapTokensForExactTokens(uint256,uint256,address[],address)

**Selector:** `0x42712a67`

**Contract Address:** `0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45` | **Chain ID:** 1

<details>
<summary><b>📋 ERC-7730 Format Definition</b></summary>

```json
{
  "format": {
    "$id": "swapTokensForExactTokens",
    "intent": "Swap",
    "fields": [
      {
        "path": "amountOut",
        "label": "Amount to Receive",
        "format": "tokenAmount",
        "params": {
          "tokenPath": "path.[-1]"
        }
      },
      {
        "path": "amountInMax",
        "label": "Maximum Amount to Send",
        "format": "tokenAmount",
        "params": {
          "tokenPath": "path.[0]"
        }
      }
    ]
  }
}
```

</details>

### 🔴 Critical Issues

1. Missing recipient display: ERC-7730 format does NOT display the `to` input parameter (recipient). `to` is an input that receives the final tokens (possibly after sentinel substitution), so hiding it is a critical omission.

### 💡 Recommendations

1. Add a field for the recipient: e.g. {"path":"to","label":"Recipient","format":"address"}.
2. When `to` equals sentinel constants (Constants.MSG_SENDER, Constants.ADDRESS_THIS), resolve to friendly labels (e.g. "You" / "This contract") or show both the sentinel and resolved address so user isn't surprised.
3. ---

---

