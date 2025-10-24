# 📊 Clear Signing Audit Report

**Generated:** 2025-10-24 20:54:19

**Contract ID:** Uniswap v3 Router 2

**Total Deployments Analyzed:** 1

**Chain IDs:** 1

---

## Summary Table

| Function | Selector | Severity | Issues | Link |
|----------|----------|----------|--------|------|
| `exactInputSingle` | `0x04e45aaf` | 🔴 Critical | Format metadata contains a broken/incorrect parameter path in the "required" array: "params.amountOu... | [View](#selector-04e45aaf) |
| `exactOutput` | `0x09b81346` | 🔴 Critical | The ERC-7730 format maps the displayed tokens for amountInMaximum and amountOut to the wrong positio... | [View](#selector-09b81346) |
| `swapExactTokensForTokens` | `0x472b43f3` | 🔴 Critical | Missing recipient ("to") in ERC-7730 display: the function has an input parameter `to` which receive... | [View](#selector-472b43f3) |
| `swapTokensForExactTokens` | `0x42712a67` | 🔴 Critical | Missing recipient display: The provided ERC-7730 format only shows: | [View](#selector-42712a67) |
| `exactInput` | `0xb858183f` | 🟢 Minor | If a user intentionally supplies amountIn = 0 to indicate "use contract balance"... | [View](#selector-b858183f) |
| `exactOutputSingle` | `0x5023b4df` | 🟢 Minor | The format shows "Maximum Amount to Send" (params.amountInMaximum) rather than t... | [View](#selector-5023b4df) |

---

## 📈 Statistics

| Metric | Count |
|--------|-------|
| 🔴 Critical | 4 |
| 🟡 Major | 2 |
| 🟢 Minor | 0 |
| ✅ No Issues | 0 |
| **Total** | **6** |

---

# Detailed Analysis

## <a id="selector-b858183f"></a> exactInput

**Selector:** `0xb858183f` | **Signature:** `exactInput((bytes,address,uint256,uint256))`

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

<details>
<summary><b>🔍 Side-by-Side Comparison (ABI vs ERC-7730)</b></summary>

### Transaction 1: `0xb89631ea1751f1d079e92ba8a24216e12abd37c6a3920fa80a7e505b56d47c72`

**Block:** 23649163 | **From:** 0xb7b78a8a908acf3c72a9c30c4e0a413c6b020611 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `path` | `0xb5d730d442e1d5b119fb4e5c843c48...b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `recipient` | `0xb7b78a8a908acf3c72a9c30c4e0a413c6b020611` | **Beneficiary**<br/>Format: `addressName` |
| `amountIn` | `25552053708942264952298` | **Amount to Send**<br/>Format: `tokenAmount` |
| `amountOutMinimum` | `38872308556642232` | **Minimum amount to Receive**<br/>Format: `tokenAmount` |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xc02aaa39...` | From: `0x4633afa7...`<br/>To: `0xb7b78a8a...` | 0.038989 WETH |
| 🔄 Transfer | `0xb5d730d4...` | From: `0xb7b78a8a...`<br/>To: `0x4633afa7...` | 25552.053709 SABAI |
| ❓ Unknown | `0x4633afa7...` | Signature: `0xc42079f94a6350d7...` | - |

### Transaction 2: `0xcbdbf9a924407a27afa2a22e7b3f6158863c862936ab83e20dfcfed168660a92`

**Block:** 23649154 | **From:** 0x622661ab4b6ab93c659e751f47ebb0c6e6ad9f48 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `path` | `0xa0b86991c6218b36c1d19d4a2e9eb0...0e9a08d4fbb5ec7bac80b691be27f21d` | ⚠️ Not shown |
| `recipient` | `0x622661ab4b6ab93c659e751f47ebb0c6e6ad9f48` | **Beneficiary**<br/>Format: `addressName` |
| `amountIn` | `100000000` | **Amount to Send**<br/>Format: `tokenAmount` |
| `amountOutMinimum` | `2357046447861347600000` | **Minimum amount to Receive**<br/>Format: `tokenAmount` |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xc02aaa39...` | From: `0xe0554a47...`<br/>To: `0x68b34658...` | 0.02559 WETH |
| 🔄 Transfer | `0xa0b86991...` | From: `0x622661ab...`<br/>To: `0xe0554a47...` | 100 USDC |
| ❓ Unknown | `0xe0554a47...` | Signature: `0xc42079f94a6350d7...` | - |
| 🔄 Transfer | `0xdd66781d...` | From: `0x7b3ed3a3...`<br/>To: `0x622661ab...` | 2483.905663 AXGT |
| 🔄 Transfer | `0xc02aaa39...` | From: `0x68b34658...`<br/>To: `0x7b3ed3a3...` | 0.02559 WETH |
| ❓ Unknown | `0x7b3ed3a3...` | Signature: `0xc42079f94a6350d7...` | - |

### Transaction 3: `0x03eab0465c54625b903c08ea7e02d49f92c1022c775866812ec49197c2633c84`

**Block:** 23649151 | **From:** 0x622661ab4b6ab93c659e751f47ebb0c6e6ad9f48 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `path` | `0xa0b86991c6218b36c1d19d4a2e9eb0...0e9a08d4fbb5ec7bac80b691be27f21d` | ⚠️ Not shown |
| `recipient` | `0x622661ab4b6ab93c659e751f47ebb0c6e6ad9f48` | **Beneficiary**<br/>Format: `addressName` |
| `amountIn` | `150000000` | **Amount to Send**<br/>Format: `tokenAmount` |
| `amountOutMinimum` | `3540941647853773000000` | **Minimum amount to Receive**<br/>Format: `tokenAmount` |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xc02aaa39...` | From: `0xe0554a47...`<br/>To: `0x68b34658...` | 0.038352 WETH |
| 🔄 Transfer | `0xa0b86991...` | From: `0x622661ab...`<br/>To: `0xe0554a47...` | 150 USDC |
| ❓ Unknown | `0xe0554a47...` | Signature: `0xc42079f94a6350d7...` | - |
| 🔄 Transfer | `0xdd66781d...` | From: `0x7b3ed3a3...`<br/>To: `0x622661ab...` | 3728.867585 AXGT |
| 🔄 Transfer | `0xc02aaa39...` | From: `0x68b34658...`<br/>To: `0x7b3ed3a3...` | 0.038352 WETH |
| ❓ Unknown | `0x7b3ed3a3...` | Signature: `0xc42079f94a6350d7...` | - |

### Transaction 4: `0xc806623ad090df70bac4059045d437f41decbd736c77958208c940a80a7c92a3`

**Block:** 23649148 | **From:** 0x622661ab4b6ab93c659e751f47ebb0c6e6ad9f48 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `path` | `0xa0b86991c6218b36c1d19d4a2e9eb0...0e9a08d4fbb5ec7bac80b691be27f21d` | ⚠️ Not shown |
| `recipient` | `0x622661ab4b6ab93c659e751f47ebb0c6e6ad9f48` | **Beneficiary**<br/>Format: `addressName` |
| `amountIn` | `150000000` | **Amount to Send**<br/>Format: `tokenAmount` |
| `amountOutMinimum` | `3684240923626008000000` | **Minimum amount to Receive**<br/>Format: `tokenAmount` |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xc02aaa39...` | From: `0xe0554a47...`<br/>To: `0x68b34658...` | 0.03834 WETH |
| 🔄 Transfer | `0xa0b86991...` | From: `0x622661ab...`<br/>To: `0xe0554a47...` | 150 USDC |
| ❓ Unknown | `0xe0554a47...` | Signature: `0xc42079f94a6350d7...` | - |
| 🔄 Transfer | `0xdd66781d...` | From: `0x7b3ed3a3...`<br/>To: `0x622661ab...` | 3735.077304 AXGT |
| 🔄 Transfer | `0xc02aaa39...` | From: `0x68b34658...`<br/>To: `0x7b3ed3a3...` | 0.03834 WETH |
| ❓ Unknown | `0x7b3ed3a3...` | Signature: `0xc42079f94a6350d7...` | - |

### Transaction 5: `0x1ea2da14dd4c0596ced4c2a1c2a542e2393c0cbc6279163da3f9e5fe71456491`

**Block:** 23649095 | **From:** 0x622661ab4b6ab93c659e751f47ebb0c6e6ad9f48 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `path` | `0xa0b86991c6218b36c1d19d4a2e9eb0...b510427baac4e267bea62e800b247173` | ⚠️ Not shown |
| `recipient` | `0x622661ab4b6ab93c659e751f47ebb0c6e6ad9f48` | **Beneficiary**<br/>Format: `addressName` |
| `amountIn` | `100000000` | **Amount to Send**<br/>Format: `tokenAmount` |
| `amountOutMinimum` | `1589097506960062200000` | **Minimum amount to Receive**<br/>Format: `tokenAmount` |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xc02aaa39...` | From: `0xe0554a47...`<br/>To: `0x68b34658...` | 0.025573 WETH |
| 🔄 Transfer | `0xa0b86991...` | From: `0x622661ab...`<br/>To: `0xe0554a47...` | 100 USDC |
| ❓ Unknown | `0xe0554a47...` | Signature: `0xc42079f94a6350d7...` | - |
| 🔄 Transfer | `0xb17548c7...` | From: `0x1becf1ac...`<br/>To: `0x622661ab...` | 1596.311534 SMT |
| 🔄 Transfer | `0xc02aaa39...` | From: `0x68b34658...`<br/>To: `0x1becf1ac...` | 0.025573 WETH |
| ❓ Unknown | `0x1becf1ac...` | Signature: `0xc42079f94a6350d7...` | - |

</details>

---

## 🔍 Clear Signing Audit Report

### 📋 Function: `exactInput((bytes,address,uint256,uint256))`  
Selector: `0xb858183f`

### 1️⃣ Intent Analysis

> Declared Intent: "N/A"

The intent label is missing/empty; given the function behavior a concise intent should be "Swap" — current declaration is not informative but not dangerous.

---

### 2️⃣ Critical Issues

> 🔴 **CRITICAL** - Issues that could lead to users being deceived or losing funds

✅ No critical issues found

Rationale (concise):
- The ERC-7730 format fields map to actual input parameters that exist (params.path, params.amountIn, params.amountOutMinimum, params.recipient).
- The format uses the first 20 bytes of params.path for token-in and the last 20 bytes for token-out; this matches decodeFirstPool and Uniswap-style path encoding used by the contract.
- Receipt logs for sample transactions show the same input token transfers and final output transfers that the display would indicate (amounts and token directions match).
- No broken $ref, missing fields that exist in inputs, or mismatches between displayed token addresses and the actual tokens moved in logs.
- Although function is payable, it does not use msg.value in the shown code to determine token amounts; samples show ERC20 transfers only — no undisplayed native ETH movement.

---

### 3️⃣ Missing Parameters

> ⚠️ Parameters present in ABI but NOT shown to users in ERC-7730

✅ All parameters required by the display are covered (params.amountIn, params.amountOutMinimum, params.recipient, params.path are available and used).

Notes: The contract has internal sentinels (CONTRACT_BALANCE = 0, MSG_SENDER = address(1), ADDRESS_THIS = address(2)) and uses them to change runtime behavior. Those sentinels are not special-cased in the display but are input-taken values — their existence is an implementation detail (see Display Issues below). Not critical per rules.

---

### 4️⃣ Display Issues (non-critical)

> 🟡 **Issues with how information is presented to users**

1. Amount sentinel CONTRACT_BALANCE (0)
   - If a user intentionally supplies amountIn = 0 to indicate "use contract balance", the ERC-7730 display will show "Amount to Send: 0 <token>" which is potentially confusing (it won't communicate "use contract's balance"). This is a display UX issue (medium) not a correctness/critical issue.
   - Recommendation: Detect amountIn == 0 and display "Use contract token balance" or similar.

2. Recipient sentinel values (MSG_SENDER / ADDRESS_THIS)
   - The contract accepts recipient values that can be sentinel addresses (address(1)/address(2)) and remaps them internally. The current display will show the raw address unless the UI maps those two sentinel addresses to readable labels like "Caller" or "This contract".
   - Recommendation: Map address(1) → "Caller (msg.sender)" and address(2) → "This contract" in the UI when encountered.

3. Native ETH representation (payable function)
   - exactInput is payable but the format's tokenAmount fields do not include a nativeCurrencyAddress param. If a UI/flow ever lets users send native ETH and the intended token in the path is an ETH sentinel (rather than WETH), the current format has no explicit native sentinel mapping and may not display native ETH correctly.
   - In the provided samples, swaps use ERC20s (WETH token contract), not native ETH, so no mismatch occurred. Still recommend supporting nativeCurrencyAddress in tokenAmount definitions or explicitly documenting that the UI must treat WETH vs native ETH cases properly.
   - Recommendation: Add nativeCurrencyAddress to tokenAmount definition or ensure UI uses @.value for msg.value cases and a native sentinel if contract can accept ETH semantically.

4. UX: Negative-index path extraction is used (params.path.[-20:])
   - This is spec-valid, but implementers must ensure their parser correctly resolves the last 20 bytes as the final token address. (Not an error here, just a caution.)

5. Labels / Intent
   - The top-level intent in the provided format is missing (shown as N/A). Suggest explicitly setting intent to "Swap" for clarity.

---

### 5️⃣ Transaction Samples — What Users See vs What Actually Happens

(Analysing 3 samples from receipts; fields shown are those present in the ERC-7730 format: Amount to Send (params.amountIn token), Minimum amount to Receive (params.amountOutMinimum token), Beneficiary (params.recipient).)

#### 📝 Transaction Sample A (single-hop SABAI → WETH)
User Intent (from ERC-7730):
- Amount to Send: 25552053708942264952298 SABAI (token at params.path.[0:20])
- Minimum to Receive: 38872308556642232 WETH (token at params.path.[-20:])
- Beneficiary: user EOA (params.recipient)

Actual Effects (receipt_logs):
- Transfer: SABAI transferred from user → pool for 25,552.053709 SABAI — matches displayed Amount to Send ✔️
- Transfer: WETH transferred from pool → user for 0.038989 WETH — matches displayed receiving token and is >= amountOutMinimum ✔️
- Swap callback / pool internal events present — internal, not required to display.

Disclosed? Yes — tokens and amounts line up with display.

#### 📝 Transaction Sample B (multi-hop USDC → WETH → AXGT)
User Intent (from ERC-7730):
- Amount to Send: 100 USDC (params.path.[0:20] = USDC)
- Minimum to Receive: 2357046447861347600000 AXGT (params.path.[-20:] = AXGT)
- Beneficiary: user EOA

Actual Effects (receipt_logs):
- Transfer: USDC from user → pool (100 USDC) — matches displayed Amount to Send ✔️
- Transfer: final token AXGT from pool → user (≈2483.905663 AXGT) — matches displayed receiving token and >= minimum ✔️
- Intermediate transfers and internal pool swaps occurred (WETH passes through) — intermediate hops are implementation details and not required to be shown.

Disclosed? Yes.

#### 📝 Transaction Sample C (USDC → WETH → SMT)
User Intent:
- Amount to Send: 100 USDC
- Minimum to Receive: 1589097506960062200000 SMT
- Beneficiary: user EOA

Actual Effects (receipt_logs):
- Transfer: USDC from user → pool (100 USDC) — matches display ✔️
- Transfer: SMT from pool → user (≈1596.311534 SMT) — matches display and >= min ✔️

Disclosed? Yes.

Summary: For the sample transactions, display tokens, amounts, and final recipient align with on-chain transfers.

---

### 6️⃣ Overall Assessment

| Metric | Score / Rating | Explanation |
|---|---:|---|
| Coverage Score | 9 / 10 | Display maps to actual input parameters and the path extraction matches decodeFirstPool; sample receipts confirm correctness. Minor UX/display gaps prevent a perfect score. |
| Security Risk | 🟢 Low | No mismatched tokens/amounts or hidden recipient behaviors found in samples. Issues are UX/display only, not fund-stealing or misdirection. |

#### 💡 Key Recommendations
- Add explicit handling for sentinel values:
  - Display a human-friendly label when params.amountIn == 0 (CONTRACT_BALANCE) — e.g., "Use contract token balance".
  - Display labels for params.recipient == address(1) and address(2) (e.g., "Caller (msg.sender)" and "This contract").
- If you want to support native ETH cases robustly, add nativeCurrencyAddress to the tokenAmount display definition (or otherwise instruct UI to show msg.value with an "amount" field). This ensures ETH displays correctly when relevant.
- Set the top-level intent in metadata to "Swap" and ensure labels are explicit (improves user clarity).
- Ensure implementers parse negative-index tokenPath extraction correctly (params.path.[-20:]) — spec-compliant but easy to get wrong in parsers.

---

If you want, I can produce suggested ERC-7730 JSON snippets to:
- detect and render amountIn == 0 special case,
- map sentinel recipient addresses to human-friendly names,
- add nativeCurrencyAddress handling for tokenAmount.

---

## <a id="selector-04e45aaf"></a> exactInputSingle

**Selector:** `0x04e45aaf` | **Signature:** `exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))`

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

<details>
<summary><b>🔍 Side-by-Side Comparison (ABI vs ERC-7730)</b></summary>

### Transaction 1: `0xeb323d521f249d8e5bd45a0e69f9822faa3abb5a206c954b796d9c3a165c22c8`

**Block:** 23649198 | **From:** 0x4c5f6ad6628d205259443ebcf6cc4cdd7d6cbf81 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `tokenIn` | `0x7ff7fa94b8b66ef313f7970d4eebd2cb3103a2c0` | ⚠️ Not shown |
| `tokenOut` | `0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `fee` | `500` | **Uniswap fee**<br/>Format: `unit` |
| `recipient` | `0x4c5f6ad6628d205259443ebcf6cc4cdd7d6cbf81` | **Beneficiary**<br/>Format: `addressName` |
| `amountIn` | `118488342980000000000` | **Send**<br/>Format: `tokenAmount` |
| `amountOutMinimum` | `78274030000000000` | **Receive Minimum**<br/>Format: `tokenAmount` |
| `sqrtPriceLimitX96` | `0` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xc02aaa39...` | From: `0x7f3c5ab7...`<br/>To: `0x4c5f6ad6...` | 0.078352 WETH |
| 🔄 Transfer | `0x7ff7fa94...` | From: `0x4c5f6ad6...`<br/>To: `0x7f3c5ab7...` | 118.488343 VANA |
| ❓ Unknown | `0x7f3c5ab7...` | Signature: `0xc42079f94a6350d7...` | - |

### Transaction 2: `0x4fef698018d763e398eca874e4b109a8ae993021ba827dbb8231102e7b7dd141`

**Block:** 23649186 | **From:** 0x3bc9f80576021cf44a704b6314c1db86ee5284b2 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `tokenIn` | `0x04c17b9d3b29a78f7bd062a57cf44fc633e71f85` | ⚠️ Not shown |
| `tokenOut` | `0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `fee` | `3000` | **Uniswap fee**<br/>Format: `unit` |
| `recipient` | `0x3bc9f80576021cf44a704b6314c1db86ee5284b2` | **Beneficiary**<br/>Format: `addressName` |
| `amountIn` | `67421762050175730000000` | **Send**<br/>Format: `tokenAmount` |
| `amountOutMinimum` | `50056539059069137` | **Receive Minimum**<br/>Format: `tokenAmount` |
| `sqrtPriceLimitX96` | `0` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xc02aaa39...` | From: `0x1a89ae3b...`<br/>To: `0x3bc9f805...` | 0.071509 WETH |
| 🔄 Transfer | `0x04c17b9d...` | From: `0x3bc9f805...`<br/>To: `0x1a89ae3b...` | 67421.76205 IMPT |
| ❓ Unknown | `0x1a89ae3b...` | Signature: `0xc42079f94a6350d7...` | - |

### Transaction 3: `0x74b26d9127d522ad67512624df73830d5532fc91c6b7320f46b4ff140fe67459`

**Block:** 23649183 | **From:** 0x4c5f6ad6628d205259443ebcf6cc4cdd7d6cbf81 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `tokenIn` | `0xaaa9214f675316182eaa21c85f0ca99160cc3aaa` | ⚠️ Not shown |
| `tokenOut` | `0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `fee` | `3000` | **Uniswap fee**<br/>Format: `unit` |
| `recipient` | `0x4c5f6ad6628d205259443ebcf6cc4cdd7d6cbf81` | **Beneficiary**<br/>Format: `addressName` |
| `amountIn` | `13976398320860000000000` | **Send**<br/>Format: `tokenAmount` |
| `amountOutMinimum` | `92217000000000000` | **Receive Minimum**<br/>Format: `tokenAmount` |
| `sqrtPriceLimitX96` | `0` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xc02aaa39...` | From: `0x09117bff...`<br/>To: `0x4c5f6ad6...` | 0.092309 WETH |
| 🔄 Transfer | `0xaaa9214f...` | From: `0x4c5f6ad6...`<br/>To: `0x09117bff...` | 13976.398321 QANX |
| ❓ Unknown | `0x09117bff...` | Signature: `0xc42079f94a6350d7...` | - |

### Transaction 4: `0x14badd83002d27a349599027a6c3de331e048bab46f084d5005b72e48b9b7199`

**Block:** 23649174 | **From:** 0x4fcf369f63ad85e95994ebfe1f5e4287f005d550 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `tokenIn` | `0xadd290d9262768c039ca8ce6013c7f2f20dd24c0` | ⚠️ Not shown |
| `tokenOut` | `0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `fee` | `500` | **Uniswap fee**<br/>Format: `unit` |
| `recipient` | `0x4fcf369f63ad85e95994ebfe1f5e4287f005d550` | **Beneficiary**<br/>Format: `addressName` |
| `amountIn` | `3169926322500000000` | **Send**<br/>Format: `tokenAmount` |
| `amountOutMinimum` | `784390033282785` | **Receive Minimum**<br/>Format: `tokenAmount` |
| `sqrtPriceLimitX96` | `0` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xc02aaa39...` | From: `0x92eda77b...`<br/>To: `0x4fcf369f...` | 0.000826 WETH |
| 🔄 Transfer | `0xadd290d9...` | From: `0x4fcf369f...`<br/>To: `0x92eda77b...` | 3.169926 goUSD |
| ❓ Unknown | `0x92eda77b...` | Signature: `0xc42079f94a6350d7...` | - |

### Transaction 5: `0xf09db3e7d59630a796bad8c0c60add416e5591d3ec9947c238a613f1b31fbb64`

**Block:** 23649164 | **From:** 0x50da42031b75497b27fd172032c03daab759dfdf | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `tokenIn` | `0xcf3c8be2e2c42331da80ef210e9b1b307c03d36a` | ⚠️ Not shown |
| `tokenOut` | `0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `fee` | `3000` | **Uniswap fee**<br/>Format: `unit` |
| `recipient` | `0x50da42031b75497b27fd172032c03daab759dfdf` | **Beneficiary**<br/>Format: `addressName` |
| `amountIn` | `500000000000000000000000` | **Send**<br/>Format: `tokenAmount` |
| `amountOutMinimum` | `11869725519415519` | **Receive Minimum**<br/>Format: `tokenAmount` |
| `sqrtPriceLimitX96` | `0` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xc02aaa39...` | From: `0x695b30d6...`<br/>To: `0x50da4203...` | 0.012107 WETH |
| 🔄 Transfer | `0xcf3c8be2...` | From: `0x50da4203...`<br/>To: `0x695b30d6...` | 500000 BEPRO |
| ❓ Unknown | `0x695b30d6...` | Signature: `0xc42079f94a6350d7...` | - |

</details>

---

## 🔍 Clear Signing Audit Report

### 📋 Function: exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))
Selector: 0x04e45aaf

> **Declared Intent:** *"N/A"*

Assessment: The contract implements a Uniswap-style single-pool swap ("swap") and the intent "swap" would be appropriate; the template's declared intent shown as "N/A" is unclear and should be set to "swap" (minor clarity issue).

---

### 1️⃣ Intent Analysis
> **Declared Intent:** *"N/A"*

Sentence: The function performs a token swap (single-pool exact-input) — the intent field should read "swap" instead of "N/A" for clarity; no grammar errors besides the placeholder.

---

### 2️⃣ Critical Issues
> 🔴 **CRITICAL** - Issues that could lead to users being deceived or losing funds

- Format metadata contains a broken/incorrect parameter path in the "required" array: "params.amountOutMininimum" (misspelling). This references a non-existent input path and will break validation or cause the UI to treat a legitimately provided parameter as missing.
  - Why critical: broken required paths can make the display/validation layer fail to render or incorrectly mark the transaction metadata as invalid — impacting user understanding and possibly blocking signing flows.

✅ No other critical issues found:
- Final tokens/amounts in the provided receipt_logs match the displayed fields (amountIn → tokenIn, amountOutMinimum → tokenOut min, recipient shown). There is no evidence in the provided logs of token inversion or completely wrong tokens.
- The function is payable but the shown transactions use ERC20 flows; no evidence of native ETH being sent/received in these samples that would make tokenAmount display incapable of showing ETH. Therefore no missing ETH display criticality.

---

### 3️⃣ Missing Parameters
> ⚠️ *Parameters present in ABI but NOT shown to users in ERC-7730*

| Parameter | Why It's Important | Risk Level |
|-----------|--------------------|:----------:|
| sqrtPriceLimitX96 | Affects swap price bounds; not shown to user in metadata | 🟢 Low |

Notes: All user-facing economic parameters (amountIn, amountOutMinimum, fee, recipient, tokenIn, tokenOut via tokenPath) are represented. sqrtPriceLimitX96 is an internal limit — low-risk to omit.

If no parameters are missing, write: **✅ All parameters are covered**

(Above: sqrtPriceLimitX96 intentionally omitted from display — low risk.)

---

### 4️⃣ Display Issues
> 🟡 **Issues with how information is presented to users**

- Required-path typo: "params.amountOutMininimum" — will break schema validation and should be corrected to "params.amountOutMinimum".
- Payable function nuance: exactInputSingle is payable but the format's tokenAmount fields do not specify a nativeCurrencyAddress. In the provided transactions swaps use ERC20 tokens (including WETH). If a UI wants to display native ETH when appropriate, the tokenAmount definition should include a nativeCurrencyAddress sentinel. Currently there is no native ETH sentinel in the format — not critical for supplied samples but could misrepresent ETH in other contexts.
- Sentinel values not surfaced meaningfully:
  - amountIn sentinel (CONTRACT_BALANCE == 0) is supported by contract (amountIn==0 triggers use of contract balance). If a user intentionally inputs 0 to mean "use contract balance", the UI will display "Send 0" which is misleading. This is an implementation detail but a display clarity issue (medium-low).
  - recipient sentinel remapping: recipient can be the special addresses Constants.MSG_SENDER (address(1)) or Constants.ADDRESS_THIS (address(2)) and the contract maps them to msg.sender or address(this). The metadata shows the raw address value; the UI should map those sentinel constants to human-friendly labels (e.g., "sender" or "this contract") to avoid confusion.
- Intent field is "N/A" in the template; should be explicit "swap".
- Minor: no explicit field showing tokenIn/tokenOut addresses separately — they are implied by tokenAmount tokenPath params. This is acceptable but making token symbols/addresses explicit can improve clarity.
- Spelling/grammar: the only notable typo is in required path ("amountOutMininimum").

Display edge-case note (medium): If the contract were to always use native ETH or always output native ETH while the format trusts a user-supplied ERC20 token path, the display could show the wrong token. In this contract and sample logs, that mismatch does not occur — but for robustness consider adding a native sentinel or using @.value when msg.value should be shown.

---

### 5️⃣ Transaction Samples - What Users See vs What Actually Happens

(Analyzed 3 sample transactions from the provided list.)

#### 📝 Transaction A (first sample)
User Intent (from ERC-7730):
| Field | ✅ User Sees | ❌ Hidden / Not Shown |
|-------|-------------|-----------------------|
| Send | 118.48834298... (params.amountIn, tokenPath tokenIn = VANA) | payer logic (who provided tokens) — hidden implementation detail |
| Receive Minimum | 0.07827403 WETH (params.amountOutMinimum) | actual exact amount will be computed on-chain |
| Beneficiary | user address (params.recipient) | recipient sentinel mapping not used here |

Actual Effects (from receipt_logs):
| Event | Details | Disclosed? |
|-------|---------|:----------:|
| Transfer | TokenOut: WETH → to recipient: 0.07835239095690408 WETH | ✅ Matches (user receives WETH, amount >= min) |
| Transfer | TokenIn: VANA from user → pool: 118.48834298... VANA | ✅ Matches (user sent VANA) |
| Swap event (pool) | Pool swap internal event present | ✅ Not shown in simple fields (but not required) |

Conclusion: The UI fields correspond to actual token movements; user got slightly more WETH than the minimum shown. No critical mismatch.

#### 📝 Transaction B (second sample)
User Intent (from ERC-7730):
| Field | ✅ User Sees | ❌ Hidden / Not Shown |
|-------|-------------|-----------------------|
| Send | 67,421.76205 IMPT (params.amountIn) | payer/approval steps hidden |
| Receive Minimum | 0.050056539059069137 WETH | actual exact amount computed on-chain |
| Fee | 3000 (0.3%) | — |

Actual Effects (from receipt_logs):
| Event | Details | Disclosed? |
|-------|---------|:----------:|
| Transfer | WETH → recipient: 0.07150934151295591 WETH | ✅ User received WETH (exceeds min) |
| Transfer | IMPT from user → pool: 67421762050175730000000 | ✅ Matches displayed send |
| Swap event (pool) | Pool emitted swap event data | ✅ Not shown in fields |

Conclusion: Displayed send/receive minimum align with actual transfers.

#### 📝 Transaction C (fifth sample)
User Intent (from ERC-7730):
| Field | ✅ User Sees | ❌ Hidden / Not Shown |
|-------|-------------|-----------------------|
| Send | 500,000 BEPRO (params.amountIn) | — |
| Receive Minimum | 0.011869725519415519 WETH | — |

Actual Effects (from receipt_logs):
| Event | Details | Disclosed? |
|-------|---------|:----------:|
| Transfer | WETH → recipient: 0.012107120029803830 WETH | ✅ Actual > min |
| Transfer | BEPRO → pool: 500,000 | ✅ Matches |
| Swap event (pool) | Pool swap log present | ✅ Not shown |

Conclusion: Good correspondence between displayed fields and actual on-chain transfers.

---

### 6️⃣ Overall Assessment

| Metric | Score/Rating | Explanation |
|--------|--------------|-------------|
| Coverage Score | 8/10 | Key economic fields (send amount, receive-min, fee, recipient, token paths) are present and correspond to on-chain transfers. Minor metadata issues reduce score. |
| Security Risk | 🟢 Low | No evidence of inverted tokens, wrong-amount display, or undisclosed transfers in provided samples. The single critical issue is a metadata typo affecting validation, not a funds-loss bug in the contract. |

#### 💡 Key Recommendations
- Fix the required-path typo: change "params.amountOutMininimum" → "params.amountOutMinimum". Re-validate metadata and UI testing pipelines.
- Set intent explicitly to "swap" (not "N/A") to improve clarity.
- Improve display for sentinel values:
  - Map known sentinel addresses (Constants.MSG_SENDER, Constants.ADDRESS_THIS) to readable labels ("sender", "this contract") in addressName logic.
  - If amountIn==0 is used as a sentinel to mean "use contract balance", display a clear label (e.g., "Use contract balance" or "Max available") instead of "0".
- Consider adding nativeCurrencyAddress support in the tokenAmount definition (or a robust token-sentinel mapping) so UIs can correctly render native ETH when applicable. This avoids edge-case mismatches if future calls use native ETH flows.
- Add an explicit field (or tooltip) documenting that amountIn may be replaced with contract balance when supplied as 0, and that payer may be msg.sender or the contract — improves transparency though not strictly critical.

---

If you want, I can:
- produce a corrected ERC-7730 JSON snippet with the required fix and recommended nativeCurrencyAddress addition, or
- run a quick template change that maps the sentinel addresses to labels for display.

---

## <a id="selector-09b81346"></a> exactOutput

**Selector:** `0x09b81346` | **Signature:** `exactOutput((bytes,address,uint256,uint256))`

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

<details>
<summary><b>🔍 Side-by-Side Comparison (ABI vs ERC-7730)</b></summary>

### Transaction 1: `0x1d62e283a185132e365528cc800aa7b5e475159a74ad22633362d8c6d2c9f9c2`

**Block:** 23648953 | **From:** 0xc4fc3d4da2ec5aa2d4fc7ad41eccb7b86b13a821 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `path` | `0xb5d730d442e1d5b119fb4e5c843c48...b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `recipient` | `0xc4fc3d4da2ec5aa2d4fc7ad41eccb7b86b13a821` | **Beneficiary**<br/>Format: `addressName` |
| `amountOut` | `2320895195145511318096` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMaximum` | `3581331051623358` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xb5d730d4...` | From: `0x4633afa7...`<br/>To: `0xc4fc3d4d...` | 2320.895195 SABAI |
| 🔄 Transfer | `0xc02aaa39...` | From: `0xc4fc3d4d...`<br/>To: `0x4633afa7...` | 0.003571 WETH |
| ❓ Unknown | `0x4633afa7...` | Signature: `0xc42079f94a6350d7...` | - |

### Transaction 2: `0x3909d6f5d84d8bf3552c7aeb94911c591736c0705788989d7373b9580caf7f77`

**Block:** 23648814 | **From:** 0x2766be7d41479e8cf315f8bf27ca1511f515e137 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `path` | `0xb5d730d442e1d5b119fb4e5c843c48...b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `recipient` | `0x2766be7d41479e8cf315f8bf27ca1511f515e137` | **Beneficiary**<br/>Format: `addressName` |
| `amountOut` | `1820083363442087105063` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMaximum` | `2809450982355626` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xb5d730d4...` | From: `0x4633afa7...`<br/>To: `0x2766be7d...` | 1820.083363 SABAI |
| 🔄 Transfer | `0xc02aaa39...` | From: `0x2766be7d...`<br/>To: `0x4633afa7...` | 0.002801 WETH |
| ❓ Unknown | `0x4633afa7...` | Signature: `0xc42079f94a6350d7...` | - |

### Transaction 3: `0x84b80ef20750a68b67bb0ebafd5816c7724209f74b21921e0bebf0789b365cce`

**Block:** 23648757 | **From:** 0xc4fc3d4da2ec5aa2d4fc7ad41eccb7b86b13a821 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `path` | `0xb5d730d442e1d5b119fb4e5c843c48...b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `recipient` | `0xc4fc3d4da2ec5aa2d4fc7ad41eccb7b86b13a821` | **Beneficiary**<br/>Format: `addressName` |
| `amountOut` | `416340847481757887013` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMaximum` | `642544695721295` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xb5d730d4...` | From: `0x4633afa7...`<br/>To: `0xc4fc3d4d...` | 416.340847 SABAI |
| 🔄 Transfer | `0xc02aaa39...` | From: `0xc4fc3d4d...`<br/>To: `0x4633afa7...` | 0.000641 WETH |
| ❓ Unknown | `0x4633afa7...` | Signature: `0xc42079f94a6350d7...` | - |

### Transaction 4: `0xe948ac17654a93a4469b02064a1e9728e631d2bf949b76d57daeed255670f80a`

**Block:** 23648713 | **From:** 0xc4fc3d4da2ec5aa2d4fc7ad41eccb7b86b13a821 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `path` | `0xb5d730d442e1d5b119fb4e5c843c48...b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `recipient` | `0xc4fc3d4da2ec5aa2d4fc7ad41eccb7b86b13a821` | **Beneficiary**<br/>Format: `addressName` |
| `amountOut` | `1069956917634324745026` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMaximum` | `1651087932006845` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xb5d730d4...` | From: `0x4633afa7...`<br/>To: `0xc4fc3d4d...` | 1069.956918 SABAI |
| 🔄 Transfer | `0xc02aaa39...` | From: `0xc4fc3d4d...`<br/>To: `0x4633afa7...` | 0.001646 WETH |
| ❓ Unknown | `0x4633afa7...` | Signature: `0xc42079f94a6350d7...` | - |

### Transaction 5: `0x57e6dcde13e377065914170c82170e5b47a20074ccb4fd00f40ecdea84695829`

**Block:** 23648551 | **From:** 0x2766be7d41479e8cf315f8bf27ca1511f515e137 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `path` | `0xb5d730d442e1d5b119fb4e5c843c48...b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `recipient` | `0x2766be7d41479e8cf315f8bf27ca1511f515e137` | **Beneficiary**<br/>Format: `addressName` |
| `amountOut` | `3554596314033120897661` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMaximum` | `5484186307854903` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xb5d730d4...` | From: `0x4633afa7...`<br/>To: `0x2766be7d...` | 3554.596314 SABAI |
| 🔄 Transfer | `0xc02aaa39...` | From: `0x2766be7d...`<br/>To: `0x4633afa7...` | 0.005468 WETH |
| ❓ Unknown | `0x4633afa7...` | Signature: `0xc42079f94a6350d7...` | - |

</details>

---

## 🔍 Clear Signing Audit Report

### 📋 Function: exactOutput((bytes,address,uint256,uint256))
Selector: 0x09b81346

### 1️⃣ Intent Analysis

> Declared Intent: "N/A"

The intent is missing from the metadata; adding "Swap" or "ExactOutput Swap" would make the purpose clear and there's no spelling/grammar issue besides being blank.

---

### 2️⃣ Critical Issues

> 🔴 **CRITICAL** - Issues that could lead to users being deceived or losing funds

- The ERC-7730 format maps the displayed tokens for amountInMaximum and amountOut to the wrong positions in the encoded path:
  - amountInMaximum uses tokenPath: params.path.[0:20] — this picks the first address in the path (tokenOut in the contract) but amountInMaximum is the maximum input token amount (should be tokenIn).
  - amountOut uses tokenPath: params.path.[-20:] — this picks the last address in the path (tokenIn in the contract) but amountOut is the output amount (should be tokenOut).
- Practical effect: the UI would show the wrong token next to "Maximum Amount to Send" and "Amount to Receive" (labels/tokens inverted). Receipt_logs show users actually received the first-path token and spent the last-path token — opposite of what's shown.

Why this is critical:
- A normal user could be shocked/misled: e.g., the display could say "sending 0.0035 WETH → receiving 2320 SABAI" but because of inversion it might instead show those tokens swapped, making them think they're sending/receiving the opposite asset.
- The information to correct the display (the encoded path bytes) is present in the function inputs, so this is a fixable metadata error and therefore critical per the policy.

✅ No other critical issues found:
- The recipient field exists and is shown.
- There are no broken $ref paths in the provided format fragment.
- Native ETH handling is present in the function signature (payable) but receipt_logs show ERC20 WETH transfers; no native ETH transfers occurred in samples, so lack of nativeCurrencyAddress is not critical here.

---

### 3️⃣ Missing Parameters

> ⚠️ *Parameters present in ABI but NOT shown to users in ERC-7730*

✅ All required parameters (params.amountInMaximum, params.amountOut, params.recipient) are declared in the format.

No other ABI parameters appear to be omitted from the provided format fragment.

---

### 4️⃣ Display Issues

> 🟡 **Issues with how information is presented to users**

- IN/OUT token mapping inverted (see Critical Issues). Fix: swap tokenPath indices.
  - amountInMaximum should use tokenPath: params.path.[-20:]
  - amountOut should use tokenPath: params.path.[0:20]
- Missing declared intent string — currently "N/A". Suggest setting intent: "Swap" (or "ExactOutput Swap").
- Function is payable but metadata does not include any nativeCurrencyAddress sentinel. Current transaction samples use WETH (ERC20), so this is not critical — but if the router ever accepted native ETH (msg.value) and displayed token amounts based on user-supplied token addresses, the metadata should include nativeCurrencyAddress or use @.value where appropriate to avoid misleading displays. Recommendation: if native ETH is intended to be supported, add nativeCurrencyAddress to tokenAmount definition or use a sentinel constant for native ETH.
- No spelling/grammar errors in labels provided, but the label "Beneficiary" (recipient) is fine; consider adding clarification that recipient may be a sentinel (MSG_SENDER or ADDRESS_THIS) which are resolved in-contract.
- Confirm negative-index behavior (params.path.[-20:]) is supported by renderer — this is valid per ERC-7730 spec and is correctly used here.

---

### 5️⃣ Transaction Samples - What Users See vs What Actually Happens

(Analyzing 3 samples from provided list)

#### 📝 Transaction 1 (sample A)

User Intent (from ERC-7730):

| Field | ✅ User Sees (per metadata) | ❌ Hidden/Missing |
|-------|-----------------------------|-------------------|
| Maximum Amount to Send | 3581331051623358 shown as token from params.path.[0:20] (first address — 0xb5d730...) | The actual token spent is WETH (0xc02aaa...), which is params.path.[-20:] |
| Amount to Receive | 2320895195145511318096 shown as token from params.path.[-20:] (last address — 0xc02aaa...) | The actual token received is 0xb5d730... (first address) |
| Beneficiary (recipient) | displayed as params.recipient (user address) | Contract resolves recipient sent to that address — disclosed |

Actual Effects (from receipt_logs):

| Event | Details | Disclosed? |
|-------|---------|:----------:|
| Transfer (tokenOut → recipient) | Token 0xb5d730... transferred to recipient, value 2320895195145511318096 (SABAI) | ❌ Mislabelled by format (format would show last-path token) |
| Transfer (payer → pool) | WETH (0xc02aaa...) 3570619194041235 transferred from user to pool | ❌ Mislabelled by format (format shows first-path token as the one being sent) |

Conclusion: Display swaps the token symbols for send/receive relative to actual transfers.

#### 📝 Transaction 2 (sample B)

User Intent:

| Field | ✅ User Sees | ❌ Hidden/Missing |
|-------|-------------|-------------------|
| Maximum Amount to Send | 2809450982355626 shown with token params.path.[0:20] (0xb5d730...) | Actually spent token is WETH (0xc02aaa...) |
| Amount to Receive | 1820083363442087105063 shown with token params.path.[-20:] (0xc02aaa...) | Actually received token is 0xb5d730... |

Actual Effects:

| Event | Details | Disclosed? |
|-------|---------|:----------:|
| Transfer | 0xb5d730... → recipient 1820083363442087105063 (SABAI) | ❌ Mislabelled |
| Transfer | 0xc02aaa... user → pool 2801047838839109 (WETH) | ❌ Mislabelled |

#### 📝 Transaction 3 (sample C)

User Intent:

| Field | ✅ User Sees | ❌ Hidden/Missing |
|-------|-------------|-------------------|
| Maximum Amount to Send | 642544695721295 shown with token params.path.[0:20] (0xb5d730...) | Actually spent token is WETH (0xc02aaa...) |
| Amount to Receive | 416340847481757887013 shown with token params.path.[-20:] (0xc02aaa...) | Actually received token is 0xb5d730... |

Actual Effects:

| Event | Details | Disclosed? |
|-------|---------|:----------:|
| Transfer | 0xb5d730... → recipient 416340847481757887013 | ❌ Mislabelled |
| Transfer | 0xc02aaa... user → pool 640622827239577 | ❌ Mislabelled |

Summary: In all examples the UI would show the wrong token next to each amount; receipt_logs confirm actual transfers are the opposite.

---

### 6️⃣ Overall Assessment

| Metric | Score/Rating | Explanation |
|--------|--------------|-------------|
| Coverage Score | 6/10 | The format exposes the three required fields and uses the path bytes, but token index mapping is incorrect causing misleading displays. |
| Security Risk | 🔴 Medium | Misleading token labels can cause user confusion or wrong consent (user might approve/send the wrong asset), though the contract behavior itself appears correct and no extra funds are stolen by logic — the risk is user confusion and potentially approving/transferring the wrong token if they rely solely on the metadata display. |

#### 💡 Key Recommendations
- Fix the token index mapping immediately:
  - amountInMaximum -> tokenPath: params.path.[-20:]
  - amountOut -> tokenPath: params.path.[0:20]
- Add a clear intent string: e.g., "Swap" or "ExactOutput Swap".
- Add a rendering/unit test that decodes a real path and compares displayed token addresses/symbols to on-chain receipt_logs to ensure UI matches real transfers.
- If the function is intended to accept native ETH, or if there are codepaths that do, include nativeCurrencyAddress (or use @.value) in the tokenAmount definition so native ETH renders correctly. If not intended, consider removing payable or documenting why payable is present to avoid confusion.
- Consider labeling that the path is encoded as (tokenOut, ... , tokenIn) in documentation or metadata so renderers are less likely to invert indexes.

---

If you want, I can:
- Provide the exact JSON patch for the ERC-7730 format (swap the two tokenPath expressions).
- Generate a unit test snippet that verifies display vs receipt_logs for a sample tx.

---

## <a id="selector-5023b4df"></a> exactOutputSingle

**Selector:** `0x5023b4df` | **Signature:** `exactOutputSingle((address,address,uint24,address,uint256,uint256,uint160))`

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

<details>
<summary><b>🔍 Side-by-Side Comparison (ABI vs ERC-7730)</b></summary>

### Transaction 1: `0x1195bb07c6138073d8f7535efa31c46165730e33738831b7ba973bd4f4d015ad`

**Block:** 23649185 | **From:** 0xd9521aaeb5764e36284adf602d284f0f5430a021 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `tokenIn` | `0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `tokenOut` | `0x04c17b9d3b29a78f7bd062a57cf44fc633e71f85` | ⚠️ Not shown |
| `fee` | `3000` | **Uniswap fee**<br/>Format: `unit` |
| `recipient` | `0xd9521aaeb5764e36284adf602d284f0f5430a021` | **Beneficiary**<br/>Format: `addressName` |
| `amountOut` | `64870771721105324000000` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMaximum` | `89985412891839446` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |
| `sqrtPriceLimitX96` | `0` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0x04c17b9d...` | From: `0x1a89ae3b...`<br/>To: `0xd9521aae...` | 64870.771721 IMPT |
| 🔄 Transfer | `0xc02aaa39...` | From: `0xd9521aae...`<br/>To: `0x1a89ae3b...` | 0.06922 WETH |
| ❓ Unknown | `0x1a89ae3b...` | Signature: `0xc42079f94a6350d7...` | - |

### Transaction 2: `0xa6d13de3641ba87cecacbf031bf07950ec17d87ca406c2be10010947a4f90fe2`

**Block:** 23649163 | **From:** 0x50da42031b75497b27fd172032c03daab759dfdf | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `tokenIn` | `0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `tokenOut` | `0xcf3c8be2e2c42331da80ef210e9b1b307c03d36a` | ⚠️ Not shown |
| `fee` | `3000` | **Uniswap fee**<br/>Format: `unit` |
| `recipient` | `0x50da42031b75497b27fd172032c03daab759dfdf` | **Beneficiary**<br/>Format: `addressName` |
| `amountOut` | `500000000000000000000000` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMaximum` | `12180009383328576` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |
| `sqrtPriceLimitX96` | `0` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xcf3c8be2...` | From: `0x695b30d6...`<br/>To: `0x50da4203...` | 500000 BEPRO |
| 🔄 Transfer | `0xc02aaa39...` | From: `0x50da4203...`<br/>To: `0x695b30d6...` | 0.01218 WETH |
| ❓ Unknown | `0x695b30d6...` | Signature: `0xc42079f94a6350d7...` | - |

### Transaction 3: `0xc25c8e5ab0632515559a386cd721ed4a2a78f28b00796fdf08486b3a35415e13`

**Block:** 23649161 | **From:** 0x50da42031b75497b27fd172032c03daab759dfdf | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `tokenIn` | `0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `tokenOut` | `0xcf3c8be2e2c42331da80ef210e9b1b307c03d36a` | ⚠️ Not shown |
| `fee` | `3000` | **Uniswap fee**<br/>Format: `unit` |
| `recipient` | `0x50da42031b75497b27fd172032c03daab759dfdf` | **Beneficiary**<br/>Format: `addressName` |
| `amountOut` | `500000000000000000000000` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMaximum` | `12179846060790137` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |
| `sqrtPriceLimitX96` | `0` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xcf3c8be2...` | From: `0x695b30d6...`<br/>To: `0x50da4203...` | 500000 BEPRO |
| 🔄 Transfer | `0xc02aaa39...` | From: `0x50da4203...`<br/>To: `0x695b30d6...` | 0.01218 WETH |
| ❓ Unknown | `0x695b30d6...` | Signature: `0xc42079f94a6350d7...` | - |

### Transaction 4: `0x7b599bdd837a8e3f6dc3abd62e7497d55fbf71cfd6f006f87e6a5f49bf7be60e`

**Block:** 23649159 | **From:** 0x50da42031b75497b27fd172032c03daab759dfdf | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `tokenIn` | `0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `tokenOut` | `0xcf3c8be2e2c42331da80ef210e9b1b307c03d36a` | ⚠️ Not shown |
| `fee` | `3000` | **Uniswap fee**<br/>Format: `unit` |
| `recipient` | `0x50da42031b75497b27fd172032c03daab759dfdf` | **Beneficiary**<br/>Format: `addressName` |
| `amountOut` | `500000000000000000000000` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMaximum` | `12179682741536682` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |
| `sqrtPriceLimitX96` | `0` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xcf3c8be2...` | From: `0x695b30d6...`<br/>To: `0x50da4203...` | 500000 BEPRO |
| 🔄 Transfer | `0xc02aaa39...` | From: `0x50da4203...`<br/>To: `0x695b30d6...` | 0.01218 WETH |
| ❓ Unknown | `0x695b30d6...` | Signature: `0xc42079f94a6350d7...` | - |

### Transaction 5: `0x948336cf4605fc588e18686adce4b32a72f70150b748c37f0d995893e6a749ee`

**Block:** 23649157 | **From:** 0x50da42031b75497b27fd172032c03daab759dfdf | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `tokenIn` | `0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `tokenOut` | `0xcf3c8be2e2c42331da80ef210e9b1b307c03d36a` | ⚠️ Not shown |
| `fee` | `3000` | **Uniswap fee**<br/>Format: `unit` |
| `recipient` | `0x50da42031b75497b27fd172032c03daab759dfdf` | **Beneficiary**<br/>Format: `addressName` |
| `amountOut` | `500000000000000000000000` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMaximum` | `12179519425568121` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |
| `sqrtPriceLimitX96` | `0` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xcf3c8be2...` | From: `0x695b30d6...`<br/>To: `0x50da4203...` | 500000 BEPRO |
| 🔄 Transfer | `0xc02aaa39...` | From: `0x50da4203...`<br/>To: `0x695b30d6...` | 0.01218 WETH |
| ❓ Unknown | `0x695b30d6...` | Signature: `0xc42079f94a6350d7...` | - |

</details>

---

## 🔍 Clear Signing Audit Report

### 📋 Function: `exactOutputSingle((address,address,uint24,address,uint256,uint256,uint160))`
**Selector:** `0x5023b4df`

---

### 1️⃣ Intent Analysis

> **Declared Intent:** "N/A"

The declared intent is missing (shows "N/A"); this is not incorrect for functionality but is not helpful — recommend setting intent to "Swap" (or "ExactOutput Swap") for clarity. No spelling/grammar errors beyond omission.

---

### 2️⃣ Critical Issues

> 🔴 **CRITICAL** - Issues that could lead to users being deceived or losing funds

✅ No critical issues found

Rationale (concise):
- The ERC-7730 format fields map to real input parameters: amountInMaximum → params.tokenIn, amountOut → params.tokenOut, fee → params.fee, recipient → params.recipient. These correspond to what the user supplies.
- Receipt logs show the expected tokenOut transfer to recipient and tokenIn transfer from the sender (actual amounts are consistent with standard exact-output swaps where the actual in <= amountInMaximum).
- No token inversion, no entirely wrong token displayed, recipient is included in metadata, and no broken $ref paths appear in the provided format fragment.
- Transactions show WETH (ERC20) transfers, not raw ETH, so native-ETH display pitfalls are not triggered in the samples.

---

### 3️⃣ Missing Parameters

> ⚠️ *Parameters present in ABI but NOT shown to users in ERC-7730*

| Parameter | Why It's Important | Risk Level |
|-----------|-------------------:|:---------:|
| sqrtPriceLimitX96 | Controls price bound of swap; could affect whether the full amountOut is guaranteed. Advanced but not typically needed by retail users. | 🟢 Low |

Notes:
- tokenIn and tokenOut are not listed as separate labeled fields but are referenced by tokenAmount formatting (so token symbols/addresses will normally be inferred via tokenPath). That is acceptable coverage.
- All other user-facing params (amountOut, amountInMaximum, fee, recipient) are present.

If no parameters are missing, write: **✅ All parameters are covered** — but here sqrtPriceLimitX96 is omitted from display (low-risk).

---

### 4️⃣ Display Issues

> 🟡 **Issues with how information is presented to users**

1. amountIn vs amountInMaximum
   - The format shows "Maximum Amount to Send" (params.amountInMaximum) rather than the final actual amountIn consumed by the swap.
   - This is NOT critical (expected for exact-output max-based swaps), but it can surprise users who expect to see the exact spent amount pre-execution. Suggest clarifying label/help text: "Maximum Amount to Send (actual amount may be lower)".

2. Native ETH display capability not included in provided snippet
   - The provided ERC-7730 format fields use "tokenAmount" with tokenPath references, but the snippet does not include any nativeCurrencyAddress parameter or reference to a display definition that sets nativeCurrencyAddress.
   - Impact: if callers use the native ETH sentinel (or the router accepts ETH and wraps/unwarps) the UI may not display ETH vs WETH correctly unless the full display.definitions include nativeCurrencyAddress. In the provided transaction samples the tokenIn is WETH (ERC20) and receipt logs show ERC20 transfers, so this mismatch does not appear in samples. Still, recommend adding nativeCurrencyAddress (or ensuring definitions include it) to avoid mislabeling native ETH in other cases.

3. Recipient sentinels not mapped to human labels
   - The contract has special recipient sentinels (Constants.MSG_SENDER == address(1) and Constants.ADDRESS_THIS == address(2)) which the contract replaces with msg.sender or address(this).
   - If a user supplies such sentinels, the UI may display raw sentinel addresses (e.g., 0x000...01) instead of showing "Sender" or "This contract" unless the metadata maps these sentinel constants to friendly names. Recommend mapping these constants in definitions/local resolution so the UI can show "Caller" / "This contract".

4. sqrtPriceLimitX96 omitted
   - Advanced parameter controlling price limit is not shown; low user impact but could be useful for power users. Not critical.

5. Fee formatting detail
   - Format uses decimals: 4 and base "%", prefix false — ensure UI presents 3000 as 0.3000% or 0.3% (depending on desired precision). This is a UX nit.

6. Missing intent label
   - Declared intent is "N/A"; set to "Swap" or "ExactOutput Swap" for clarity.

---

### 5️⃣ Transaction Samples - What Users See vs What Actually Happens

(Analyzed 3 representative samples)

#### 📝 Transaction 1 (IMPT ← WETH swap)

User Intent (from ERC-7730):

| Field (ERC-7730) | ✅ User Sees |
|------------------|-------------:|
| Maximum Amount to Send (params.amountInMaximum, tokenIn=WETH) | 89,985,412,891,839,446 (displayed as tokenAmount for WETH) |
| Amount to Receive (params.amountOut, tokenOut=IMPT) | 64,870.771721 IMPT |
| Beneficiary (params.recipient) | user's address (shown via addressName) |

Hidden / Not Shown:
- The actual amountIn spent is not shown in the input metadata (only maximum). Actual amountIn is determined on-chain during swap.

Actual Effects (from receipt_logs):

| Event | Details | Disclosed? |
|-------|---------|:----------:|
| Transfer (tokenOut IMPT) | From pool -> recipient: 64,870.771721 IMPT | ✅ Yes (amountOut shown) |
| Transfer (tokenIn WETH) | From sender -> pool: 0.069219548378338036 WETH | ❌ Not pre-disclosed (only maximum displayed) |
| Pool-specific Swap Event | Internal swap event present | ❌ Not shown in ERC-7730 but not required |

Notes: amountOut matches requested amountOut (requirement in code when sqrtPriceLimitX96 == 0). Actual WETH spent (0.06922) is less than amountInMaximum (0.089985), which is expected behavior.

---

#### 📝 Transaction 2 (BEPRO ← WETH swap)

User Intent (from ERC-7730):

| Field | ✅ User Sees |
|-------|-------------:|
| Maximum Amount to Send (WETH) | 0.012180093833328576 (displayed as tokenAmount) |
| Amount to Receive (BEPRO) | 500,000 BEPRO |
| Beneficiary | user's address |

Actual Effects (from receipt_logs):

| Event | Details | Disclosed? |
|-------|---------|:----------:|
| Transfer (BEPRO) | From pool -> recipient: 500,000 BEPRO | ✅ Yes |
| Transfer (WETH) | From sender -> pool: 0.012180093383328576 WETH (actual) | ❌ Only maximum shown pre-execution |

Notes: consistent with exact-output semantics; actual spent is slightly different per swap execution but ≤ maximum.

---

#### 📝 Transaction 3 (another BEPRO ← WETH sample)

Same pattern as Transaction 2: requested 500k BEPRO, actual WETH transfer ~0.012179..., amountOut matches requested, actual amountIn ≤ amountInMaximum.

---

### 6️⃣ Overall Assessment

| Metric | Score/Rating | Explanation |
|--------|--------------:|-------------|
| **Coverage Score** | 8/10 | Input fields for recipient, amountOut, amountInMaximum and fee are present and map correctly to contract inputs. Advanced param sqrtPriceLimitX96 is omitted but low priority. Native-ETH sentinel handling not surfaced in the snippet. |
| **Security Risk** | 🟢 Low | No mismatches between displayed tokens/amount direction and on-chain transfers in the samples. The only potential UX pitfalls are display of max vs actual and native-ETH labeling if used — these are not security-critical. |

#### 💡 Key Recommendations
- Show an explicit clarification/tooltip for "Maximum Amount to Send" stating: "Actual amount spent will be computed by the swap; final amount ≤ maximum." Consider showing actual amountIn post-execution if UI supports reading receipt logs.
- Ensure display.definitions include nativeCurrencyAddress (or equivalent) so tokenAmount can render native ETH when the router accepts native ETH; or otherwise detect WETH vs ETH logic and label appropriately.
- Map sentinel constants (Constants.MSG_SENDER and ADDRESS_THIS) to friendly names in the display metadata so users see "Sender" or "This contract" instead of raw sentinel addresses if those sentinels are used.
- Add sqrtPriceLimitX96 to advanced/details view (low priority) so power users can confirm price bound settings.
- Set a clear intent string in ERC-7730 metadata (e.g., "Swap" or "ExactOutput Swap") for clarity.

---

If you want, I can:
- Produce a suggested patch to the ERC-7730 JSON (small edits) to add nativeCurrencyAddress and a tooltip for amountInMaximum.
- Generate the exact text labels for sentinel mappings and the tooltip language.

---

## <a id="selector-472b43f3"></a> swapExactTokensForTokens

**Selector:** `0x472b43f3` | **Signature:** `swapExactTokensForTokens(uint256,uint256,address[],address)`

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

<details>
<summary><b>🔍 Side-by-Side Comparison (ABI vs ERC-7730)</b></summary>

### Transaction 1: `0x82cb9d3efc91de033c46a46fe2d3f3bf45d6ba1f15dc794fbb1ca7d624714678`

**Block:** 23622994 | **From:** 0x21ae10d8d941cc293552ca493ce3ca88046bb13a | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `amountIn` | `265609043350584154226394` | **Amount to Send**<br/>Format: `tokenAmount` |
| `amountOutMin` | `1173251042746804692` | **Minimum amount to Receive**<br/>Format: `tokenAmount` |
| `path` | `('0x43fff7662becc6c986d9142d21fc...23fe8d0a0e5c4f27ead9083c756cc2')` | ⚠️ Not shown |
| `to` | `0x21ae10d8d941cc293552ca493ce3ca88046bb13a` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0x43fff766...` | From: `0x21ae10d8...`<br/>To: `0x1b0d2f50...` | 265609.043351 HMM |
| ✅ Approval | `0x43fff766...` | Owner: `0x21ae10d8...`<br/>Spender: `0x68b34658...` | 115792089237316203707617735395386539918674240093853421928448 HMM |
| 🔄 Transfer | `0xc02aaa39...` | From: `0x1b0d2f50...`<br/>To: `0x21ae10d8...` | 1.197195 WETH |
| ❓ Unknown | `0x1b0d2f50...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0x1b0d2f50...` | Signature: `0xd78ad95fa46c994b...` | - |

### Transaction 2: `0xa2731c10ff8c384fa919ab762c5528d50b5c42bc9b60d403380eba48f2047cb6`

**Block:** 23622991 | **From:** 0x21ae10d8d941cc293552ca493ce3ca88046bb13a | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `amountIn` | `1200892558425482011` | **Amount to Send**<br/>Format: `tokenAmount` |
| `amountOutMin` | `265608088792912544484401` | **Minimum amount to Receive**<br/>Format: `tokenAmount` |
| `path` | `('0xc02aaa39b223fe8d0a0e5c4f27ea...ecc6c986d9142d21fc2723412de288')` | ⚠️ Not shown |
| `to` | `0x21ae10d8d941cc293552ca493ce3ca88046bb13a` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xc02aaa39...` | From: `0x21ae10d8...`<br/>To: `0x1b0d2f50...` | 1.200893 WETH |
| 🔄 Transfer | `0x43fff766...` | From: `0x1b0d2f50...`<br/>To: `0x21ae10d8...` | 265608.088793 HMM |
| ❓ Unknown | `0x1b0d2f50...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0x1b0d2f50...` | Signature: `0xd78ad95fa46c994b...` | - |

### Transaction 3: `0xd0430a2b4de6c9d9a3648b53ce815ab69858e972b494c435df8f6a33ac4eae6d`

**Block:** 23612562 | **From:** 0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `amountIn` | `15000000000000000000000` | **Amount to Send**<br/>Format: `tokenAmount` |
| `amountOutMin` | `371465174` | **Minimum amount to Receive**<br/>Format: `tokenAmount` |
| `path` | `('0x5f474906637bdcda05f29c74653f...2ee523a2206206994597c13d831ec7')` | ⚠️ Not shown |
| `to` | `0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0x5f474906...` | From: `0x0c05a5fd...`<br/>To: `0xbdee9c99...` | 15000 DEFX |
| ✅ Approval | `0x5f474906...` | Owner: `0x0c05a5fd...`<br/>Spender: `0x68b34658...` | 115792089237316203707617735395386539918674240093853421928448 DEFX |
| 🔄 Transfer | `0xc02aaa39...` | From: `0xbdee9c99...`<br/>To: `0x0d4a11d5...` | 0.09348 WETH |
| ❓ Unknown | `0xbdee9c99...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0xbdee9c99...` | Signature: `0xd78ad95fa46c994b...` | - |
| 🔄 Transfer | `0xdac17f95...` | From: `0x0d4a11d5...`<br/>To: `0x0c05a5fd...` | 371.600063 USDT |
| ❓ Unknown | `0x0d4a11d5...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0x0d4a11d5...` | Signature: `0xd78ad95fa46c994b...` | - |

### Transaction 4: `0x628d175d9accd4196c3effac2b0ff9c3765339c04cbf341c8e0c1b652986039b`

**Block:** 23606749 | **From:** 0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `amountIn` | `10000000000000000000000` | **Amount to Send**<br/>Format: `tokenAmount` |
| `amountOutMin` | `233879002` | **Minimum amount to Receive**<br/>Format: `tokenAmount` |
| `path` | `('0x5f474906637bdcda05f29c74653f...2ee523a2206206994597c13d831ec7')` | ⚠️ Not shown |
| `to` | `0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0x5f474906...` | From: `0x0c05a5fd...`<br/>To: `0xbdee9c99...` | 10000 DEFX |
| ✅ Approval | `0x5f474906...` | Owner: `0x0c05a5fd...`<br/>Spender: `0x68b34658...` | 115792089237316203707617735395386539918674240093853421928448 DEFX |
| 🔄 Transfer | `0xc02aaa39...` | From: `0xbdee9c99...`<br/>To: `0x0d4a11d5...` | 0.060313 WETH |
| ❓ Unknown | `0xbdee9c99...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0xbdee9c99...` | Signature: `0xd78ad95fa46c994b...` | - |
| 🔄 Transfer | `0xdac17f95...` | From: `0x0d4a11d5...`<br/>To: `0x0c05a5fd...` | 233.99619 USDT |
| ❓ Unknown | `0x0d4a11d5...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0x0d4a11d5...` | Signature: `0xd78ad95fa46c994b...` | - |

### Transaction 5: `0x551ae45aa8dc8a9f3477651ecf99b59117b8510f627ada755689dc6bd9efa4d2`

**Block:** 23605420 | **From:** 0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `amountIn` | `10000000000000000000000` | **Amount to Send**<br/>Format: `tokenAmount` |
| `amountOutMin` | `228470707` | **Minimum amount to Receive**<br/>Format: `tokenAmount` |
| `path` | `('0x5f474906637bdcda05f29c74653f...2ee523a2206206994597c13d831ec7')` | ⚠️ Not shown |
| `to` | `0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0x5f474906...` | From: `0x0c05a5fd...`<br/>To: `0xbdee9c99...` | 10000 DEFX |
| ✅ Approval | `0x5f474906...` | Owner: `0x0c05a5fd...`<br/>Spender: `0x68b34658...` | 115792089237316203707617735395386539918674240093853421928448 DEFX |
| 🔄 Transfer | `0xc02aaa39...` | From: `0xbdee9c99...`<br/>To: `0x0d4a11d5...` | 0.059274 WETH |
| ❓ Unknown | `0xbdee9c99...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0xbdee9c99...` | Signature: `0xd78ad95fa46c994b...` | - |
| 🔄 Transfer | `0xdac17f95...` | From: `0x0d4a11d5...`<br/>To: `0x0c05a5fd...` | 228.582333 USDT |
| ❓ Unknown | `0x0d4a11d5...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0x0d4a11d5...` | Signature: `0xd78ad95fa46c994b...` | - |

</details>

---

## 🔍 Clear Signing Audit Report

### 📋 Function: swapExactTokensForTokens(uint256,uint256,address[],address)
Selector: 0x472b43f3

> **Declared Intent:** *"N/A"*

The metadata intent in the provided ERC-7730 snippet actually sets "intent": "Swap" — that is accurate and clear for this function, but the required block above is shown as "N/A". (Intent wording has no spelling errors.)

---

### 1️⃣ Intent Analysis

> **Declared Intent:** *"N/A"*

Assessment: The function is a Uniswap-style token swap (metadata "intent": "Swap" is appropriate); the one-line intent is clear. No spelling/grammar issues in the supplied format snippet.

---

### 2️⃣ Critical Issues

> 🔴 **CRITICAL** - Issues that could lead to users being deceived or losing funds

- Missing recipient ("to") in ERC-7730 display: the function has an input parameter `to` which receives the final output tokens, but the provided format shows only amountIn and amountOutMin. Per the spec rules, omitting an input recipient that receives funds is a critical display omission — a user can be shocked about who receives the output tokens.
- Sentinel recipient resolution not shown: contract accepts special sentinel addresses (Constants.MSG_SENDER and Constants.ADDRESS_THIS). The UI currently has no field to indicate that `to` may resolve to msg.sender or address(this), so users won't be warned that an input address could be replaced by one of those constants at runtime.

No other critical issues found (no inverted token paths, amounts in logs match decoded inputs, no broken $ref usage in the supplied format snippet, no evidence of native ETH transfers in the provided receipt_logs that are hidden by the display).

✅ No broken $ref references detected in the snippet provided.

---

### 3️⃣ Missing Parameters

> ⚠️ *Parameters present in ABI but NOT shown to users in ERC-7730*

| Parameter | Why It's Important | Risk Level |
|-----------|--------------------|:----------:|
| to | Final recipient of swapped tokens (the contract sends the final output to this address, and it can be replaced by sentinel values) | 🔴 High |

Explanation: `to` is an explicit input parameter and determines who receives the final tokens. Not showing it to users is a critical omission per the rules.

If no other parameters are missing: All other ABI parameters used in display (amountIn → path.[0], amountOutMin → path.[-1]) are present in the format.

---

### 4️⃣ Display Issues

> 🟡 **Issues with how information is presented to users**

- Missing "Recipient" field (see Critical). This is the main display deficiency.
- Sentinel values / special constants:
  - `amountIn == Constants.CONTRACT_BALANCE` (zero) is used as a sentinel to mean "use contract's token balance". The format doesn't communicate this possibility. Not critical per rules, but confusing.
  - `to == Constants.MSG_SENDER` and `to == Constants.ADDRESS_THIS` are resolved in the code to msg.sender or address(this) — UI should surface that the provided `to` might be a sentinel and show the effective recipient.
- Native ETH handling: function is payable and the internal pay() will deposit native ETH into WETH if token == WETH9 and contract balance >= value. The provided format fields do not include any explicit `nativeCurrencyAddress` metadata. Without the display.definitions (not provided here) we cannot confirm whether native ETH will be shown correctly. Based on the supplied format alone, there's no nativeCurrencyAddress; if the broader metadata lacks nativeCurrencyAddress, native ETH could be displayed incorrectly. (In the sampled receipts, only ERC20 transfers are present — no direct native ETH transfers.)
- No explicit field to communicate "uses contract balance" when amountIn == 0. Suggested as UX improvement: show "Use contract balance" instead of zero.
- The format uses tokenPath: "path.[0]" and "path.[-1]" which is correct and leverages negative index semantics — good. Ensure consumer supports negative indices.

Summary: user-visible amounts (amountIn, amountOutMin) will be shown correctly, but recipient and sentinel behavior are not surfaced.

---

### 5️⃣ Transaction Samples - What Users See vs What Actually Happens

(Analyzed 3 samples from the provided list. Omitted hashes/blocks as requested.)

#### 📝 Transaction 1 (first sample)

User Intent (from ERC-7730):
| Field | ✅ User Sees (per format) | ❌ Hidden / Not shown |
|-------|--------------------------|----------------------|
| Amount to Send (amountIn) | 265,609.043351 HMM (token path[0]) | — |
| Minimum to Receive (amountOutMin) | 1.173251042746804692 WETH (token path[-1]) | — |
| Recipient (to) | NOT SHOWN by ERC-7730 format | Decoded input includes recipient 0x21ae...; UI won't show it unless added |

Actual Effects (from receipt_logs):
| Event | Details | Disclosed by current ERC-7730 |
|-------|---------|:----------------------------:|
| Transfer (input token) | From user → pair: 265,609.043351 HMM | ✅ Amount & token shown (amountIn) |
| Transfer (output token) | From pair → user: 1.197195 WETH | ❌ Recipient not shown in display; user sees min but not final recipient field |
| Approval | Approval for router to spend user HMM | ✅ Approval is part of on-chain logs but not surfaced by this format (not required) |

Comment: amounts match logs; the only disclosure gap is the recipient.

#### 📝 Transaction 2 (second sample: reverse direction)

User Intent (from ERC-7730):
| Field | ✅ User Sees | ❌ Hidden / Not shown |
|-------|-------------|----------------------|
| Amount to Send | 1.200893 WETH | — |
| Minimum to Receive | 265,608.088793 HMM | — |
| Recipient | NOT SHOWN | Decoded input `to` is user address (not surfaced) |

Actual Effects (from receipt_logs):
| Event | Details | Disclosed? |
|-------|---------|:----------:|
| Transfer (input token) | From user → pair: 1.200893 WETH | ✅ amountIn displayed |
| Transfer (output token) | From pair → user: 265,608.088793 HMM | ❌ recipient not shown in display |

Comment: amounts match; missing recipient disclosure remains.

#### 📝 Transaction 3 (multi-hop sample)

User Intent (from ERC-7730):
| Field | ✅ User Sees | ❌ Hidden / Not shown |
|-------|-------------|----------------------|
| Amount to Send | 15,000 DEFX (path[0]) | — |
| Minimum to Receive | 371.465174 USDT (path[-1]) | — |
| Recipient | NOT SHOWN | Decoded input `to` is user address (not surfaced) |

Actual Effects (from receipt_logs):
| Event | Details | Disclosed? |
|-------|---------|:----------:|
| Transfer (DEFX → pair) | From user → pair: 15,000 DEFX | ✅ amountIn displayed |
| Intermediate swaps/Pair swaps | Internal events / swaps on pairs | ✅ (not shown in format, but not necessary) |
| Transfer (USDT → user) | Final from pair → user: 371.600063 USDT | ❌ recipient not shown in display |

Comment: Multi-hop swap behaved as expected; final amounts meet/exceed min. Recipient remains unshown.

---

### 6️⃣ Overall Assessment

| Metric | Score / Rating | Explanation |
|--------|----------------|-------------|
| Coverage Score | 6/10 | The display correctly shows the two numeric inputs (amountIn, amountOutMin) and uses correct tokenPath references, but it omits the critical "to" recipient field and doesn't surface sentinel behaviors. |
| Security Risk | 🔴 High | Omitting the recipient (and sentinel resolution) is a user-facing omission that can shock users about who receives the output tokens; per the audit rules this is critical. Amount and token correctness for these samples are fine, but recipient omission is high risk for user trust. |

#### 💡 Key Recommendations
- Add a "Recipient" field (path: "to") to the ERC-7730 format. Label it clearly (e.g., "Recipient") and format as an address.
- Detect sentinel recipient addresses and display resolved meaning:
  - If `to == Constants.MSG_SENDER` show something like: "Recipient: Your address (resolved from MSG_SENDER sentinel)".
  - If `to == Constants.ADDRESS_THIS` show: "Recipient: This contract (address(this))".
  - If consumer UI cannot resolve sentinel constants, at minimum show the literal address and a tooltip/note: "This address may be a sentinel that resolves to msg.sender or contract."
- Surface CONTRACT_BALANCE sentinel usage: if `amountIn == Constants.CONTRACT_BALANCE` (0), display "Amount to Send: use contract token balance" (or similar) instead of "0".
- Ensure native ETH display support: if display.definitions or tokenAmount definitions are used elsewhere, confirm `nativeCurrencyAddress` is configured so UI can show native ETH correctly when WETH wrapping occurs. If not present, add nativeCurrencyAddress mapping for the chain's native currency sentinel.
- Minor UX: show both "Minimum to Receive" (amountOutMin) and — when available from logs — actual amountOut after execution. (This is post-execution; for pre-sign display keep min and explain final may vary.)
- Add a short explanatory note for users: "This function can replace the provided recipient with sentinel values and may use contract balance for input when amountIn==0."

---

If you want, I can produce an updated ERC-7730 JSON snippet that:
- Adds a Recipient field for `to`,
- Adds a boolean-style note field for sentinel resolution,
- Adds a sample tokenAmount definition with nativeCurrencyAddress support.

Which would you prefer next?

---

## <a id="selector-42712a67"></a> swapTokensForExactTokens

**Selector:** `0x42712a67` | **Signature:** `swapTokensForExactTokens(uint256,uint256,address[],address)`

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

<details>
<summary><b>🔍 Side-by-Side Comparison (ABI vs ERC-7730)</b></summary>

### Transaction 1: `0x843363ab1cc24de9a7e0b5566305daf7ac2c4d728fe2363699ce22dee328db65`

**Block:** 23638234 | **From:** 0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `amountOut` | `20000000000000000000000` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMax` | `372654234` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |
| `path` | `('0xdac17f958d2ee523a22062069945...7bdcda05f29c74653f6962bb0f8eda')` | ⚠️ Not shown |
| `to` | `0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xdac17f95...` | From: `0x0c05a5fd...`<br/>To: `0x0d4a11d5...` | 372.468408 USDT |
| 🔄 Transfer | `0xc02aaa39...` | From: `0x0d4a11d5...`<br/>To: `0xbdee9c99...` | 0.096862 WETH |
| ❓ Unknown | `0x0d4a11d5...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0x0d4a11d5...` | Signature: `0xd78ad95fa46c994b...` | - |
| 🔄 Transfer | `0x5f474906...` | From: `0xbdee9c99...`<br/>To: `0x0c05a5fd...` | 20000.000037 DEFX |
| ❓ Unknown | `0xbdee9c99...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0xbdee9c99...` | Signature: `0xd78ad95fa46c994b...` | - |

### Transaction 2: `0xd33378bf653432507cc7cbd3d79b209faabf4f94b316c0d612c87e8b4ea85b14`

**Block:** 23592694 | **From:** 0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `amountOut` | `8000000000000000000000` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMax` | `150752338` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |
| `path` | `('0xdac17f958d2ee523a22062069945...7bdcda05f29c74653f6962bb0f8eda')` | ⚠️ Not shown |
| `to` | `0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xdac17f95...` | From: `0x0c05a5fd...`<br/>To: `0x0d4a11d5...` | 150.677017 USDT |
| 🔄 Transfer | `0xc02aaa39...` | From: `0x0d4a11d5...`<br/>To: `0xbdee9c99...` | 0.039124 WETH |
| ❓ Unknown | `0x0d4a11d5...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0x0d4a11d5...` | Signature: `0xd78ad95fa46c994b...` | - |
| 🔄 Transfer | `0x5f474906...` | From: `0xbdee9c99...`<br/>To: `0x0c05a5fd...` | 8000.000004 DEFX |
| ❓ Unknown | `0xbdee9c99...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0xbdee9c99...` | Signature: `0xd78ad95fa46c994b...` | - |

### Transaction 3: `0xa1b46d19415dd3653c9ba7f302d617e68328431133415658d0d554bdf38615ba`

**Block:** 23581350 | **From:** 0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `amountOut` | `12500000000000000000000` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMax` | `250174024` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |
| `path` | `('0xdac17f958d2ee523a22062069945...7bdcda05f29c74653f6962bb0f8eda')` | ⚠️ Not shown |
| `to` | `0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xdac17f95...` | From: `0x0c05a5fd...`<br/>To: `0x0d4a11d5...` | 250.049079 USDT |
| 🔄 Transfer | `0xc02aaa39...` | From: `0x0d4a11d5...`<br/>To: `0xbdee9c99...` | 0.06099 WETH |
| ❓ Unknown | `0x0d4a11d5...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0x0d4a11d5...` | Signature: `0xd78ad95fa46c994b...` | - |
| 🔄 Transfer | `0x5f474906...` | From: `0xbdee9c99...`<br/>To: `0x0c05a5fd...` | 12500.000039 DEFX |
| ❓ Unknown | `0xbdee9c99...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0xbdee9c99...` | Signature: `0xd78ad95fa46c994b...` | - |

### Transaction 4: `0x4d211055500abef2591eaa4626bc05f139fbc6bb61d892af8e944a901d2c1cbb`

**Block:** 23561904 | **From:** 0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `amountOut` | `5000000000000000000000` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMax` | `104429188` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |
| `path` | `('0xdac17f958d2ee523a22062069945...7bdcda05f29c74653f6962bb0f8eda')` | ⚠️ Not shown |
| `to` | `0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xdac17f95...` | From: `0x0c05a5fd...`<br/>To: `0x0d4a11d5...` | 104.376631 USDT |
| 🔄 Transfer | `0xc02aaa39...` | From: `0x0d4a11d5...`<br/>To: `0xbdee9c99...` | 0.02716 WETH |
| ❓ Unknown | `0x0d4a11d5...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0x0d4a11d5...` | Signature: `0xd78ad95fa46c994b...` | - |
| 🔄 Transfer | `0x5f474906...` | From: `0xbdee9c99...`<br/>To: `0x0c05a5fd...` | 5000.00001 DEFX |
| ❓ Unknown | `0xbdee9c99...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0xbdee9c99...` | Signature: `0xd78ad95fa46c994b...` | - |

### Transaction 5: `0x29da4871ecd02ae22562925e3cb2540f86af28d368538893fdda62d697ae512e`

**Block:** 23561133 | **From:** 0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `amountOut` | `8600000000000000000000` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMax` | `179304607` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |
| `path` | `('0xdac17f958d2ee523a22062069945...7bdcda05f29c74653f6962bb0f8eda')` | ⚠️ Not shown |
| `to` | `0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xdac17f95...` | From: `0x0c05a5fd...`<br/>To: `0x0d4a11d5...` | 179.215455 USDT |
| 🔄 Transfer | `0xc02aaa39...` | From: `0x0d4a11d5...`<br/>To: `0xbdee9c99...` | 0.046692 WETH |
| ❓ Unknown | `0x0d4a11d5...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0x0d4a11d5...` | Signature: `0xd78ad95fa46c994b...` | - |
| 🔄 Transfer | `0x5f474906...` | From: `0xbdee9c99...`<br/>To: `0x0c05a5fd...` | 8600.000013 DEFX |
| ❓ Unknown | `0xbdee9c99...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0xbdee9c99...` | Signature: `0xd78ad95fa46c994b...` | - |

</details>

---

## 🔍 Clear Signing Audit Report

### 📋 Function: swapTokensForExactTokens(uint256,uint256,address[],address)
Selector: 0x42712a67

> **Declared Intent:** *"Swap"*

This intent is accurate and concise. No spelling/grammar issues.

---

### 1️⃣ Intent Analysis
The metadata's intent "Swap" correctly describes the function purpose: user supplies a maximum input and a desired output and the function performs a multi-hop Uniswap-style swap to obtain that exact output.

---

### 2️⃣ Critical Issues

> 🔴 **CRITICAL** - Issues that could lead to users being deceived or losing funds

- Missing recipient display: The provided ERC-7730 format only shows:
  - amountOut (token = path[-1])
  - amountInMax (token = path[0])
  It does NOT show the `to` input parameter. `to` is an input that ultimately receives the final output tokens (subject to sentinel substitution to msg.sender or address(this)). Hiding this input is critical because a regular user would reasonably expect to see who will receive the resulting tokens. (This meets the rule: recipient is an ABI input and not shown.)

No other critical issues found:
- Tokens shown by tokenPath (path[0] as input token, path[-1] as output token) match the actual transfers in receipt_logs (USDT -> WETH -> DEFX in samples).
- Amount fields correspond to ABI inputs (amountOut and amountInMax). The contract computes actual amountIn on-chain; showing amountInMax rather than the computed amountIn is expected and not critical.
- No evidence in provided transactions of native ETH being used (txs have value=0); native-ETH handling is implemented in the contract but does not appear in the sample txs, so no critical ETH-display issue here.
- There are no broken $ref references in the provided format snippet.

---

### 3️⃣ Missing Parameters

> ⚠️ Parameters present in ABI but NOT shown to users in ERC-7730

| Parameter | Why It's Important | Risk Level |
|-----------|-------------------:|:---------:|
| to        | The recipient of the final swapped tokens; user needs to verify who receives the tokens (sentinel substitution can redirect to msg.sender or the contract) | 🔴 High |

✅ All other ABI inputs used in the format (amountOut, amountInMax, path) are represented.

---

### 4️⃣ Display Issues

> 🟡 **Issues with how information is presented to users**

- Recipient not shown (critical, already listed).
- No explicit indication that amountIn shown is the "maximum" and that actual amount taken will be computed on-chain; the format label "Maximum Amount to Send" is present but it's helpful to emphasize that actual spend ≤ amountInMax.
- Sentinel values resolution: contract substitutes `to == Constants.MSG_SENDER` → msg.sender and `to == Constants.ADDRESS_THIS` → address(this). The format should document/resolve these sentinels (or at least display both the raw param and resolved meaning) so users are not surprised. Right now there is no guidance in the format about sentinel resolution.
- Native ETH edge-case: function is payable and has logic to deposit native ETH into WETH when token == WETH9 and contract balance covers value. The current format has no nativeCurrencyAddress or other ETH sentinel handling. If a user were to supply a native ETH sentinel (or the display relied on user-supplied token address to represent ETH), the metadata should include nativeCurrencyAddress in the tokenAmount definition (or otherwise document ETH handling). In provided txs there's no ETH usage, so this is a display issue (medium) rather than critical.
- Minor clarity: format uses negative index path.[-1] which is correct ERC-7730 usage, but viewers must support it (not a problem here).

Suggested display fixes (non-critical except recipient):
- Add recipient field and show resolved sentinel text where relevant.
- Consider adding a tooltip or small note: "Actual amount spent will be computed on-chain and may be ≤ Maximum Amount to Send".
- If supporting native ETH flows, ensure tokenAmount definitions include nativeCurrencyAddress mapping so ETH displays as ETH (not WETH address).

---

### 5️⃣ Transaction Samples — What Users See vs What Actually Happens

We analyze three representative transactions.

#### 📝 Transaction A (first sample)
User supplied (decoded_input):
- Amount to Receive: 20000000000000000000000 (20,000 DEFX) — ERC-7730 shows this as Amount to Receive (token = path[-1] = DEFX).
- Maximum Amount to Send: 372654234 (372.654234 USDT) — ERC-7730 shows this as Maximum Amount to Send (token = path[0] = USDT).
- Recipient (`to`): 0x0c05... (input) — NOT SHOWN by ERC-7730 (critical).

Actual effects (receipt_logs):
- Transfer: USDT 372,468,408 (372.468408 USDT) from user → pair (actual amountIn pulled) — Disclosed? ❌ Not fully (format shows only amountInMax, not actual amountIn).
- Intermediate: WETH transfer between pairs (internal routing) — Disclosed? ✅ (token tokens are visible in logs) but not shown by metadata.
- Final Transfer: DEFX 20000000036942524878814 (≈ 20,000.000037 DEFX) to 0x0c05... (user) — Disclosed? ❌ Recipient not shown by metadata (amount and token shown, recipient missing).

Notes: actual input spent (372.468408 USDT) is slightly less than amountInMax (372.654234 USDT). Final DEFX amount is extremely close to amountOut requested (tiny dust). ERC-7730 shows requested amountOut and max input, but not the actual input or recipient.

#### 📝 Transaction B (second sample)
User supplied:
- Amount to Receive: 8,000 DEFX
- Maximum Amount to Send: 150,752,338 (150.752338 USDT)
- Recipient `to`: 0x0c05... — NOT SHOWN.

Actual effects:
- USDT Transfer: 150,677,017 USDT from user → pair (actual amountIn).
- WETH intermediate transfer.
- DEFX Transfer: 8000000004421149836593 (≈ 8000.000004 DEFX) to 0x0c05... — Recipient not shown.

ERC-7730 displays tokens and requested amounts but omits recipient and actual amountIn.

#### 📝 Transaction C (third sample)
User supplied:
- Amount to Receive: 12,500 DEFX
- Maximum Amount to Send: 250,174,024 (250.174024 USDT)
- Recipient `to`: 0x0c05... — NOT SHOWN.

Actual effects:
- USDT Transfer: 250,049,079 USDT from user → pair.
- Intermediate WETH transfer.
- DEFX Transfer: 12500000039428067833985 (≈ 12,500.000039 DEFX) to 0x0c05... — Recipient not shown.

Summary across samples:
- ERC-7730 correctly maps token types using path[0] and path[-1], and shows amountOut and amountInMax as provided inputs.
- Missing recipient display is consistent across samples; logs show the recipient (the input `to`) receives final tokens. Users cannot confirm recipient from the display.

---

### 6️⃣ Overall Assessment

| Metric | Score/Rating | Explanation |
|--------|--------------|-------------|
| **Coverage Score** | 7/10 | Amounts and token types (input/output) are covered, but recipient is omitted; some ETH display edge-cases not fully addressed. |
| **Security Risk** | 🟡 Medium | The actual token flows match user inputs in these samples, so direct fund loss risk is low; however hiding the recipient is a critical UX risk — users could be surprised if `to` was set to a contract or sentinel and they aren't shown that. |

#### 💡 Key Recommendations
1. Add recipient field to ERC-7730 format:
   - {"path":"to","label":"Recipient","format":"address"} (or a more descriptive format that resolves sentinel constants).
   - If the metadata system supports conditional labels, show resolution for sentinels: if to == Constants.MSG_SENDER → "You (msg.sender)"; if to == Constants.ADDRESS_THIS → "This contract (address(this))".
2. Add a short explanatory note near amounts: "Maximum Amount to Send is the upper bound; actual amount withdrawn will be computed on-chain and may be lower." Consider showing actual amountIn when available (if the UI can infer it from logs), but absence of actual amountIn in inputs is not a metadata bug.
3. If the system aims to display ETH properly in cases where native ETH may be used, include nativeCurrencyAddress in the tokenAmount definition or in a referenced definition so tokenAmount can display ETH instead of WETH when appropriate. Alternatively, hardcode or detect the WETH sentinel vs ETH sentinel and provide clear text (e.g., "ETH (wrapped => WETH)").
4. Display sentinel behavior clearly: document in UI/tooltip that `to` may be replaced with msg.sender or address(this) by the contract, and show the resolved address when possible.

---

If you want, I can:
- Produce a suggested ERC-7730 JSON snippet that adds a resolved-recipient field and optional nativeCurrencyAddress handling; or
- Draft UI text/tooltips for sentinel resolution and for explaining amountInMax vs actual amountIn.

---

