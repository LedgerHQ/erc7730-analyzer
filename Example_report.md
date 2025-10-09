# 📊 Clear Signing Audit Report

**Contract ID:** Uniswap v3 Router 2
**Total Deployments Analyzed:** 1
**Chain IDs:** 1

---

## Summary Table

| Function | Selector | Severity | Issues | Coverage | Link |
|----------|----------|----------|--------|----------|------|
| `exactInput` | `0xb858183f` | 🔴 Critical | 🔴 **Hidden route hops & fees:** ERC‑7730 only exposes the en... | 75% | [View](#selector-b858183f) |
| `exactInputSingle` | `0x04e45aaf` | 🔴 Critical | **Required-field typo**: the schema's `required` list contai... | 57% | [View](#selector-04e45aaf) |
| `exactOutput` | `0x09b81346` | 🔴 Critical | **Token mapping is inverted:** The ERC‑7730 format maps `amo... | 75% | [View](#selector-09b81346) |
| `swapExactTokensForTokens` | `0x472b43f3` | 🔴 Critical | **❗ Approval not disclosed:** Receipt logs consistently show... | 50% | [View](#selector-472b43f3) |
| `swapTokensForExactTokens` | `0x42712a67` | 🔴 Critical | **❗ Missing recipient disclosure:** The metadata does not di... | 50% | [View](#selector-42712a67) |
| `exactOutputSingle` | `0x5023b4df` | 🟡 Major | Missing: sqrtPriceLimitX96 | 57% | [View](#selector-5023b4df) |

---

## 📈 Statistics

| Metric | Count |
|--------|-------|
| 🔴 Critical | 5 |
| 🟡 Major | 1 |
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
```

</details>

<details>
<summary><b>🔍 Side-by-Side Comparison (ABI vs ERC-7730)</b></summary>

### Transaction 1: `0xcdf59f4f7b24ea8de46a414813e38eb3f434363700f20adefe0987f283027381`

**Block:** 23540953 | **From:** 0x2973a0da0cbd8a3bd7a6aeab4b62a1365a22139c | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `path` | `0xdac17f958d2ee523a2206206994597...0cc12f31ae18ef51216a223ba4063092` | ⚠️ Not shown |
| `recipient` | `0xd2ffbca352c1757ec223f7c7e8d48db402722c66` | **Beneficiary**<br/>Format: `addressName` |
| `amountIn` | `500000000` | **Amount to Send**<br/>Format: `tokenAmount` |
| `amountOutMinimum` | `33700402503745309937669` | **Minimum amount to Receive**<br/>Format: `tokenAmount` |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xc02aaa39...` | From: `0x11b815ef...`<br/>To: `0x68b34658...` | 0.11473 WETH |
| 🔄 Transfer | `0xdac17f95...` | From: `0x2973a0da...`<br/>To: `0x11b815ef...` | 500 USDT |
| ❓ Unknown | `0x11b815ef...` | Signature: `0xc42079f94a6350d7...` | - |
| 🔄 Transfer | `0x94482429...` | From: `0x9c0df79f...`<br/>To: `0xd2ffbca3...` | 34605.248629 MASA |
| 🔄 Transfer | `0xc02aaa39...` | From: `0x68b34658...`<br/>To: `0x9c0df79f...` | 0.11473 WETH |
| ❓ Unknown | `0x9c0df79f...` | Signature: `0xc42079f94a6350d7...` | - |

### Transaction 2: `0xdc867e84ae55bf51ffe1e91458c43aff88337820e6253553bbb4d03892376767`

**Block:** 23540949 | **From:** 0x1d15024c9d51dd9aae2a890f4187775c1ec4ec58 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `path` | `0xc02aaa39b223fe8d0a0e5c4f27ead9...57de7e0162b7a386bec253844b5e07a5` | ⚠️ Not shown |
| `recipient` | `0x1d15024c9d51dd9aae2a890f4187775c1ec4ec58` | **Beneficiary**<br/>Format: `addressName` |
| `amountIn` | `2294362064099887` | **Amount to Send**<br/>Format: `tokenAmount` |
| `amountOutMinimum` | `613316310931891916469` | **Minimum amount to Receive**<br/>Format: `tokenAmount` |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xbd8fdda0...` | From: `0xdda881d7...`<br/>To: `0x1d15024c...` | 615.161796 JARVIS |
| 🔄 Transfer | `0xc02aaa39...` | From: `0x1d15024c...`<br/>To: `0xdda881d7...` | 0.002294 WETH |
| ❓ Unknown | `0xdda881d7...` | Signature: `0xc42079f94a6350d7...` | - |

### Transaction 3: `0x6dc7bcbb3a7e3997dc2bbfaab7b8bc565cd93ecf98d349d8a2ed9699cf210f2d`

**Block:** 23540945 | **From:** 0xc0fb1c01de1148fa7b1f151a1740e52b375c47f1 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `path` | `0xb5d730d442e1d5b119fb4e5c843c48...b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `recipient` | `0xc0fb1c01de1148fa7b1f151a1740e52b375c47f1` | **Beneficiary**<br/>Format: `addressName` |
| `amountIn` | `655211274856476071233` | **Amount to Send**<br/>Format: `tokenAmount` |
| `amountOutMinimum` | `1007728215519373` | **Minimum amount to Receive**<br/>Format: `tokenAmount` |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xc02aaa39...` | From: `0x4633afa7...`<br/>To: `0xc0fb1c01...` | 0.001011 WETH |
| 🔄 Transfer | `0xb5d730d4...` | From: `0xc0fb1c01...`<br/>To: `0x4633afa7...` | 655.211275 SABAI |
| ❓ Unknown | `0x4633afa7...` | Signature: `0xc42079f94a6350d7...` | - |

### Transaction 4: `0x2d6051d94e76d5bd0219bec0db47b28453bbce3fd3ec726513e97faaa4f0507a`

**Block:** 23540933 | **From:** 0x2766be7d41479e8cf315f8bf27ca1511f515e137 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `path` | `0xb5d730d442e1d5b119fb4e5c843c48...b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `recipient` | `0x2766be7d41479e8cf315f8bf27ca1511f515e137` | **Beneficiary**<br/>Format: `addressName` |
| `amountIn` | `2016110712026054962498` | **Amount to Send**<br/>Format: `tokenAmount` |
| `amountOutMinimum` | `3101466969644653` | **Minimum amount to Receive**<br/>Format: `tokenAmount` |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xc02aaa39...` | From: `0x4633afa7...`<br/>To: `0x2766be7d...` | 0.003111 WETH |
| 🔄 Transfer | `0xb5d730d4...` | From: `0x2766be7d...`<br/>To: `0x4633afa7...` | 2016.110712 SABAI |
| ❓ Unknown | `0x4633afa7...` | Signature: `0xc42079f94a6350d7...` | - |

### Transaction 5: `0xee82f42efec6b9041b9e4b0ddb5df223919e7309fd6a94f4fcbc6dc640027dd1`

**Block:** 23540895 | **From:** 0xc0fb1c01de1148fa7b1f151a1740e52b375c47f1 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `path` | `0xb5d730d442e1d5b119fb4e5c843c48...b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `recipient` | `0xc0fb1c01de1148fa7b1f151a1740e52b375c47f1` | **Beneficiary**<br/>Format: `addressName` |
| `amountIn` | `3584020139182082882817` | **Amount to Send**<br/>Format: `tokenAmount` |
| `amountOutMinimum` | `5515862794208190` | **Minimum amount to Receive**<br/>Format: `tokenAmount` |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xc02aaa39...` | From: `0x4633afa7...`<br/>To: `0xc0fb1c01...` | 0.005532 WETH |
| 🔄 Transfer | `0xb5d730d4...` | From: `0xc0fb1c01...`<br/>To: `0x4633afa7...` | 3584.020139 SABAI |
| ❓ Unknown | `0x4633afa7...` | Signature: `0xc42079f94a6350d7...` | - |

</details>

---

## 🔍 Clear Signing Audit Report

### 📋 Function: `exactInput((bytes,address,uint256,uint256))`  
**Selector:** `0xb858183f`

---

### 1️⃣ Intent Analysis

> **Declared Intent:** *"Swap"*

The declared intent "Swap" is accurate as this call performs a token swap, but it is incomplete because it does not communicate routing details (intermediate hops/fees) that materially affect the swap.

---

### 2️⃣ Critical Issues

> 🔴 **CRITICAL** - Issues that could lead to users being deceived or losing funds

- ✅ The shown "Amount to Send" (params.amountIn) and "Minimum amount to Receive" (params.amountOutMinimum) map to the first and last token addresses in the provided samples — they are not inverted in these examples.  
- 🔴 **Hidden route hops & fees:** ERC‑7730 only exposes the endpoints (first and last token) via tokenPath slicing ([0:20] and [-20:]) and omits intermediate tokens and per-hop fees encoded in the Uniswap V3-style `path` bytes. A route can include intermediate tokens or pools (and fee tiers) that change expected outcome or introduce counterparty/tax behavior; hiding them can deceive users about where funds actually flow.  
- 🔴 **No disclosure of intermediate token behaviors (taxes, transfer hooks, wrappers):** If an intermediate token charges transfer fees or triggers hooks, the user is not informed. This can reduce received amounts below expectations even if minAmount is shown.  
- 🔴 **Approvals / pull semantics not disclosed:** The format does not show that tokens will be pulled from the user's account (transferFrom) or if an approval is being consumed/required. Users may not realize the contract will move funds from their address. (Receipt logs show transfers from the user.)  
- 🟠 **Path slicing fragility / parser correctness risk:** Using simple byte slices like [0:20] and [-20:] assumes a specific layout; if the path encoding changes (e.g., different fee encoding or nested formats) this can pick incorrect addresses, causing displayed tokens to be wrong. This is a practical risk for UniswapV3-style encoded paths (addresses & 3-byte fee fields interleaved).  
- 🟡 **No slippage context / percentage displayed:** Only absolute minimum is shown; users cannot see slippage % or a reference expected output. This makes it harder to judge if the minOut is reasonable.

If none of the above were present, we'd report no critical issues — but the route/fee hiding and lack of approval disclosure are high‑impact.

---

### 3️⃣ Missing Parameters

> ⚠️ Parameters present in ABI but NOT shown to users in ERC-7730

| Parameter | Why It's Important | Risk Level |
|-----------|-------------------|:----------:|
| `params.path` (full decoded) | Contains intermediate token addresses and per-hop fee tiers that determine routing, counterparty pools, and potential token behaviors (taxes, hooks). Hiding it prevents users from seeing intermediate tokens and fees. | 🔴 High |
| `router/pool addresses` (implicit in route) | Which pools/contracts will touch funds (router or pool addresses) matters for trust and security; not shown. | 🟡 Medium |
| `approval/pull information` | Whether the router will call transferFrom (i.e., pull tokens) or user sent tokens directly, and whether an approval is consumed or set — this affects persistence of allowances and attack surface. | 🔴 High |
| `estimated output / quoted price` | Shows expected amount before slippage; without it users only see a minimum bound which is less informative. | 🟡 Medium |

(ABI fields amountIn, amountOutMinimum, recipient are shown — but the path details are missing.)

---

### 4️⃣ Display Issues

> 🟡 **Issues with how information is presented to users**

- Labeling is OK but minimal: "Amount to Send" / "Minimum amount to Receive" are acceptable, but do not indicate token symbols unless token resolution succeeds.  
- Token extraction logic (tokenPath: "params.path.[0:20]" and "[-20:]") is fragile — it assumes the path is laid out as plain addresses at exact offsets and does not explicitly decode UniswapV3-style fee bytes between addresses. This can produce wrong token labels in edge cases.  
- No explicit statement that tokens will be pulled by the router (transferFrom) versus ETH value-in behavior.  
- No display of intermediate hops, fee tiers, or route length — a significant omission for multihop swaps.  
- No slippage percent or reference expected-amount shown (only min).  
- Recipient label is generic ("Beneficiary") — it does not show if recipient equals the tx sender or some third party, and it does not warn about uncommon recipient addresses.

If parsing reliably decodes endpoints in all cases, many basic display items are fine — but the missing route/fee and pull behavior disclosures are the main UX failures.

---

### 5️⃣ Transaction Samples - What Users See vs What Actually Happens

I analyze three representative transactions.

#### 📝 Transaction 1: 0xcdf59f4f7b24ea8de46a414813e38eb3f434363700f20adefe0987f283027381

**User Intent (from ERC-7730):**
| Field | ✅ User Sees | ❌ Hidden/Missing |
|-------|-------------|-------------------|
| Amount to Send | 500 USDT (params.amountIn → tokenPath first address) | That the router will call transferFrom and the intermediate pools/fees |
| Minimum amount to Receive | 33700402503745309937669 MASA (params.amountOutMinimum → last token) | Full route (intermediate hops & fees), slippage % / quoted expected output |
| Beneficiary | 0xd2ffbca3… (recipient) | Which contract addresses (pools/routers) will touch tokens |

**Actual Effects (from receipt_logs):**
| Event | Details | Disclosed? |
|-------|---------|:----------:|
| Transfer | USDT — from user 0x2973… → pool 0x11b8… — amount 500 USDT | ✅ Yes (amount & token endpoint shown) |
| Transfer | MASA — from pool 0x9c0d… → recipient 0xd2ff… — amount 34,605.248629 MASA (actual received) | ✅ Partially (min shown; actual final amount not pre-disclosed) |
| Transfer | WETH movements between router/pools (0.11473 WETH) | ❌ No — intermediate WETH hop and pool/router involvement not surfaced |

Notes: The ERC‑7730 fields correctly list the endpoint tokens and amounts, but hide the intermediate WETH hop and pool addresses.

---

#### 📝 Transaction 2: 0xdc867e84ae55bf51ffe1e91458c43aff88337820e6253553bbb4d03892376767

**User Intent (from ERC-7730):**
| Field | ✅ User Sees | ❌ Hidden/Missing |
|-------|-------------|-------------------|
| Amount to Send | 0.002294 WETH | Whether the pool/router charges fees / route details |
| Minimum amount to Receive | 613.316310931891916469 JARVIS | Intermediate hops/fees and expected quoted output |
| Beneficiary | 0x1d15024c… | Which pool address receives/sends tokens |

**Actual Effects (from receipt_logs):**
| Event | Details | Disclosed? |
|-------|---------|:----------:|
| Transfer | WETH — from user → pool/contract — 0.002294 WETH | ✅ Yes (amount & token endpoint shown) |
| Transfer | JARVIS — pool → recipient — 615.161796 JARVIS (actual) | ✅ Partially (min shown; actual final amount differs but was not pre-disclosed) |
| Router internal events | Unknown internal swap events emitted by pool/router | ❌ No — not shown to user |

Notes: Endpoint mapping is correct; route internals remain hidden.

---

#### 📝 Transaction 3: 0x6dc7bcbb3a7e3997dc2bbfaab7b8bc565cd93ecf98d349d8a2ed9699cf210f2d

**User Intent (from ERC-7730):**
| Field | ✅ User Sees | ❌ Hidden/Missing |
|-------|-------------|-------------------|
| Amount to Send | 655.211275 SABAI | Intermediate tokens/fees in path |
| Minimum amount to Receive | 0.001007728215519373 WETH | Slippage context and route pool addresses |
| Beneficiary | 0xc0fb1c01… | Whether any intermediate token has fee-on-transfer behavior |

**Actual Effects (from receipt_logs):**
| Event | Details | Disclosed? |
|-------|---------|:----------:|
| Transfer | SABAI — user → pool — 655.211275 SABAI | ✅ Yes |
| Transfer | WETH — pool → recipient — 0.001010760497010404 WETH (actual) | ✅ Partially (min shown; actual final amount not shown pre-sign) |
| Router/pool internal events | Unknown swap events, possible multi-hop with fee tiers | ❌ No |

Notes: The user sees endpoints, but not the route or interim tokens.

---

### 6️⃣ Overall Assessment

| Metric | Score/Rating | Explanation |
|--------|--------------|-------------|
| **Coverage Score** | 7/10 | ERC‑7730 exposes the three primary ABI parameters (amountIn, amountOutMinimum, recipient) and maps token endpoints correctly in these samples, but it hides route details and approval/pull semantics which are security‑relevant. |
| **Security Risk** | 🟡 Medium | Missing route/fee disclosure and lack of approval/pull visibility can mislead users about where funds go and which contracts interact with their tokens; these are moderate-to-high impact depending on route complexity and token behavior. |

#### 💡 Key Recommendations
- 1) **Decode and display the full `path`:** Show all token addresses in the path in-order, and decode per-hop fee tiers (e.g., Uniswap V3 3‑byte fees) so users can see each intermediate token and fee. Mark each hop explicitly (TokenA → fee → TokenB).  
- 2) **Surface pull/approval behavior:** Explicitly state that the router will call transferFrom (i.e., tokens are pulled from the user) and show any approvals that will be consumed or required; if possible, show the router/pool addresses that will move funds.  
- 3) **Show slippage context and quoted expected output:** In addition to minimum amount, display the quoted expected amount and the implied slippage % between quote and min; this helps users judge if min is reasonable.  
- 4) **Harden tokenPath parsing:** Use a canonical decoder for the `path` bytes (respecting 20-byte addresses & 3-byte fee fields) rather than naive [0:20] slices; validate for malformed/unsupported path encodings and show a warning if parsing fails.  
- 5) **Warn about intermediate token behaviors:** If any intermediate token is known to be fee-on-transfer or has nonstandard hooks, surface a clear warning pre-signing.

---

If implemented, the above changes will reduce surprise behaviors and materially improve the user's ability to consent to exactly what will happen on-chain.

---

---

## <a id="selector-04e45aaf"></a> exactInputSingle

**Selector:** `0x04e45aaf` | **Signature:** `exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))`

**Contract Address:** `0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45` | **Chain ID:** 1

<details>
<summary><b>📋 ERC-7730 Format Definition</b></summary>

```json
{
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
```

</details>

<details>
<summary><b>🔍 Side-by-Side Comparison (ABI vs ERC-7730)</b></summary>

### Transaction 1: `0x43c3f46b9f6ce918e5e185885709cf949dee0d86b1402039b2cbe242627aa40c`

**Block:** 23540961 | **From:** 0x4c5f6ad6628d205259443ebcf6cc4cdd7d6cbf81 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `tokenIn` | `0xae6e307c3fe9e922e5674dbd7f830ed49c014c6b` | ⚠️ Not shown |
| `tokenOut` | `0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `fee` | `10000` | **Uniswap fee**<br/>Format: `unit` |
| `recipient` | `0x4c5f6ad6628d205259443ebcf6cc4cdd7d6cbf81` | **Beneficiary**<br/>Format: `addressName` |
| `amountIn` | `14182265995560000000000` | **Send**<br/>Format: `tokenAmount` |
| `amountOutMinimum` | `13171090000000000` | **Receive Minimum**<br/>Format: `tokenAmount` |
| `sqrtPriceLimitX96` | `0` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xc02aaa39...` | From: `0xab26d209...`<br/>To: `0x4c5f6ad6...` | 0.013184 WETH |
| 🔄 Transfer | `0xae6e307c...` | From: `0x4c5f6ad6...`<br/>To: `0xab26d209...` | 14182.265996 CREDI |
| ❓ Unknown | `0xab26d209...` | Signature: `0xc42079f94a6350d7...` | - |

### Transaction 2: `0x1bf5da3a5264c65609bd3108075611f95c4e8d7bab3e0705195e8cfa847c3cc6`

**Block:** 23540960 | **From:** 0xb1b2d032aa2f52347fbcfd08e5c3cc55216e8404 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `tokenIn` | `0x944824290cc12f31ae18ef51216a223ba4063092` | ⚠️ Not shown |
| `tokenOut` | `0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `fee` | `10000` | **Uniswap fee**<br/>Format: `unit` |
| `recipient` | `0xb1b2d032aa2f52347fbcfd08e5c3cc55216e8404` | **Beneficiary**<br/>Format: `addressName` |
| `amountIn` | `8421571965878273000000` | **Send**<br/>Format: `tokenAmount` |
| `amountOutMinimum` | `22982146767631368` | **Receive Minimum**<br/>Format: `tokenAmount` |
| `sqrtPriceLimitX96` | `0` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xc02aaa39...` | From: `0x9c0df79f...`<br/>To: `0xb1b2d032...` | 0.023051 WETH |
| 🔄 Transfer | `0x94482429...` | From: `0xb1b2d032...`<br/>To: `0x9c0df79f...` | 8421.571966 MASA |
| ❓ Unknown | `0x9c0df79f...` | Signature: `0xc42079f94a6350d7...` | - |

### Transaction 3: `0x688a6c79a7ebd09da8dda1792b738c84e9bb780e05068f1fca3bc89ee1b0aacb`

**Block:** 23540959 | **From:** 0xb1b2d032aa2f52347fbcfd08e5c3cc55216e8404 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `tokenIn` | `0x06450dee7fd2fb8e39061434babcfc05599a6fb8` | ⚠️ Not shown |
| `tokenOut` | `0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `fee` | `10000` | **Uniswap fee**<br/>Format: `unit` |
| `recipient` | `0xb1b2d032aa2f52347fbcfd08e5c3cc55216e8404` | **Beneficiary**<br/>Format: `addressName` |
| `amountIn` | `15366491575944171000000000000` | **Send**<br/>Format: `tokenAmount` |
| `amountOutMinimum` | `144587344624638368` | **Receive Minimum**<br/>Format: `tokenAmount` |
| `sqrtPriceLimitX96` | `0` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xc02aaa39...` | From: `0x2a9d2ba4...`<br/>To: `0xb1b2d032...` | 0.145022 WETH |
| 🔄 Transfer | `0x06450dee...` | From: `0xb1b2d032...`<br/>To: `0x2a9d2ba4...` | 15366491575.944172 XEN |
| ❓ Unknown | `0x2a9d2ba4...` | Signature: `0xc42079f94a6350d7...` | - |

### Transaction 4: `0x8b5d958212b9beaa69b090d603d4cef8b6dbea6840b863a03b20d1bc4f44740f`

**Block:** 23540959 | **From:** 0xb1b2d032aa2f52347fbcfd08e5c3cc55216e8404 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `tokenIn` | `0x944824290cc12f31ae18ef51216a223ba4063092` | ⚠️ Not shown |
| `tokenOut` | `0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `fee` | `10000` | **Uniswap fee**<br/>Format: `unit` |
| `recipient` | `0xb1b2d032aa2f52347fbcfd08e5c3cc55216e8404` | **Beneficiary**<br/>Format: `addressName` |
| `amountIn` | `8370914640524002000000` | **Send**<br/>Format: `tokenAmount` |
| `amountOutMinimum` | `22982146767631372` | **Receive Minimum**<br/>Format: `tokenAmount` |
| `sqrtPriceLimitX96` | `0` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xc02aaa39...` | From: `0x9c0df79f...`<br/>To: `0xb1b2d032...` | 0.023051 WETH |
| 🔄 Transfer | `0x94482429...` | From: `0xb1b2d032...`<br/>To: `0x9c0df79f...` | 8370.914641 MASA |
| ❓ Unknown | `0x9c0df79f...` | Signature: `0xc42079f94a6350d7...` | - |

### Transaction 5: `0x5e5cfb0f601113ae03ef6ce1736bc775bacae0b928c4f631a078b788422c049d`

**Block:** 23540957 | **From:** 0xb1b2d032aa2f52347fbcfd08e5c3cc55216e8404 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `tokenIn` | `0x944824290cc12f31ae18ef51216a223ba4063092` | ⚠️ Not shown |
| `tokenOut` | `0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `fee` | `10000` | **Uniswap fee**<br/>Format: `unit` |
| `recipient` | `0xb1b2d032aa2f52347fbcfd08e5c3cc55216e8404` | **Beneficiary**<br/>Format: `addressName` |
| `amountIn` | `15958148179442218000000` | **Send**<br/>Format: `tokenAmount` |
| `amountOutMinimum` | `45964293535262736` | **Receive Minimum**<br/>Format: `tokenAmount` |
| `sqrtPriceLimitX96` | `0` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xc02aaa39...` | From: `0x9c0df79f...`<br/>To: `0xb1b2d032...` | 0.046418 WETH |
| 🔄 Transfer | `0x94482429...` | From: `0xb1b2d032...`<br/>To: `0x9c0df79f...` | 15958.148179 MASA |
| ❓ Unknown | `0x9c0df79f...` | Signature: `0xc42079f94a6350d7...` | - |

</details>

---

## 🔍 Clear Signing Audit Report

### 📋 Function: `exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))`
**Selector:** `0x04e45aaf`

---

### 1️⃣ Intent Analysis

> **Declared Intent:** *"swap"*

The declared intent "swap" is accurate — the call performs a single-hop token swap (sending tokenIn and receiving tokenOut).

---

### 2️⃣ Critical Issues

> 🔴 **CRITICAL** - Issues that could lead to users being deceived or losing funds

- **Required-field typo**: the schema's `required` list contains a misspelling `"params.amountOutMininimum"` (extra "ni"). That can cause wallets/validators to *not enforce* presence of the amountOutMinimum field and silently omit showing the user the minimum receive value — this is a high-risk bug.  
- **Missing sqrtPriceLimitX96 in display**: the ABI parameter `sqrtPriceLimitX96` (price limit guard) is not surfaced; if set non-zero it materially changes trade execution and should be shown/flagged. Omitting it can hide important slippage/price-limit behavior.  
- **Actual received output not shown (only minimum shown)**: ERC-7730 exposes "Receive Minimum" but not the *expected* or *actual* output amount; pre-signing this can be confusing and users may misread the minimum as guaranteed. Post-execution, the receipt shows the actual received amount in logs but that is not part of clear signing. This is user-impacting (medium-high).  
- **Token addresses not explicitly listed**: tokenIn/tokenOut are only referenced indirectly via tokenAmount tokenPath. If symbol resolution fails or is spoofed, users may not see the raw addresses. That can lead to interacting with wrong tokens (medium risk).

No undisclosed approvals were found in the sample receipt_logs (no Approval events); token transfer directions in logs match intent.

---

### 3️⃣ Missing Parameters

> ⚠️ *Parameters present in ABI but NOT shown to users in ERC-7730*

| Parameter | Why It's Important | Risk Level |
|-----------|-------------------|:----------:|
| `params.sqrtPriceLimitX96` | Controls a price bound for the swap; non-zero values can prevent trades past a price threshold or enforce an unexpected limit. Must be shown so users know if a price guard is set. | 🔴 High |
| `params.tokenIn` (explicit address) | Token symbol may be resolved, but the explicit address should be displayed (or easily inspectable) so users can confirm the exact token contract. | 🟡 Medium |
| `params.tokenOut` (explicit address) | Same as tokenIn — explicit address reduces phishing/spoof risk if symbol resolution is wrong. | 🟡 Medium |

If no parameters are missing: **(not applicable — see table above).**

---

### 4️⃣ Display Issues

> 🟡 **Issues with how information is presented to users**

- **Typo in required list** can lead wallets to not enforce showing amountOutMinimum — must be fixed.  
- **"Receive Minimum" label could be misread** as expected or guaranteed amount; suggest adding a clarifying suffix: e.g., "*Receive (minimum guaranteed)*" or show slippage tolerance/expected quote.  
- **No explicit token addresses displayed** — rely on symbol resolution that can fail/spoof; show raw addresses with a small icon/button to expand.  
- **No explicit disclosure of counterparty/pool address** (the recipient of tokenIn in logs); users may want to know which pool contract will receive funds.  
- **No indication when sqrtPriceLimitX96 != 0** — when non-zero, it should be flagged as a price limit and translated into an approximate price bound or labelled prominently.

If none: **✅ No display issues found** (not the case here).

---

### 5️⃣ Transaction Samples - What Users See vs What Actually Happens

I analyze 3 sample transactions below.

#### 📝 Transaction 1: 0x43c3f46b9f6ce9...

**User Intent (from ERC-7730):**
| Field | ✅ User Sees | ❌ Hidden/Missing |
|-------|-------------|-------------------|
| **Send** | 14182.265996 CREDI (params.amountIn, tokenIn) | tokenIn raw address visible only if UI shows it explicitly |
| **Receive Minimum** | 0.01317109 WETH (params.amountOutMinimum) | expected/estimated receive amount (not shown); final amount (only visible in logs) |
| **Uniswap fee** | 1.0000% (params.fee = 10000) | — |
| **Beneficiary** | 0x4c5f6a... (recipient) | pool/counterparty & sqrtPriceLimitX96 (0 present) |

**Actual Effects (from receipt_logs):**
| Event | Details | Disclosed? |
|-------|---------|:----------:|
| Transfer | tokenOut WETH → recipient: **0.013184279656047437 WETH** | ❌ Final received amount not disclosed pre-signing (only minimum was shown) |
| Transfer | tokenIn CREDI from user → pool: **14182.265996 CREDI** | ✅ Send amount was shown |
| Unknown (swap event) | Pool contract emitted swap event (contains exact amounts, pool address) | ❌ Not shown to user pre-signing |

---

#### 📝 Transaction 2: 0x1bf5da3a5264c6...

**User Intent (from ERC-7730):**
| Field | ✅ User Sees | ❌ Hidden/Missing |
|-------|-------------|-------------------|
| **Send** | 8421.571966 MASA | tokenIn raw address not explicitly shown by format |
| **Receive Minimum** | 0.022982146767631368 WETH | expected/estimated receive amount & final amount not shown |
| **Uniswap fee** | 1.0000% | — |
| **Beneficiary** | 0xb1b2d0... | pool/counterparty & sqrtPriceLimitX96 |

**Actual Effects (from receipt_logs):**
| Event | Details | Disclosed? |
|-------|---------|:----------:|
| Transfer | WETH → user: **0.023051300669640287 WETH** (actual > minimum) | ❌ Not disclosed pre-signing |
| Transfer | MASA → pool: **8421.571966 MASA** | ✅ Send amount shown |
| Unknown (swap event) | Pool address present in event topics | ❌ Not surfaced in ERC-7730 fields |

---

#### 📝 Transaction 3: 0x688a6c79a7ebd0...

**User Intent (from ERC-7730):**
| Field | ✅ User Sees | ❌ Hidden/Missing |
|-------|-------------|-------------------|
| **Send** | 15366491575944171000000000000 (15366491575.944172 XEN) | raw token address not explicit unless UI shows it |
| **Receive Minimum** | 0.144587344624638368 WETH | expected output & exact received amount not shown |
| **Uniswap fee** | 1.0000% | — |
| **Beneficiary** | 0xb1b2d0... | sqrtPriceLimitX96 & pool address |

**Actual Effects (from receipt_logs):**
| Event | Details | Disclosed? |
|-------|---------|:----------:|
| Transfer | WETH → user: **0.145022411860219044 WETH** | ❌ Final amount not shown pre-signing |
| Transfer | XEN → pool: **15366491575.944172 XEN** | ✅ Send amount shown |
| Unknown (swap event) | Swap event emitted by pool | ❌ Not disclosed pre-signing |

---

### 6️⃣ Overall Assessment

| Metric | Score/Rating | Explanation |
|--------|--------------|-------------|
| **Coverage Score** | 7 / 10 | ERC-7730 captures the core fields users care about (amountIn, amountOutMinimum, fee, recipient) and formats token amounts, but misses some ABI parameters and explicit addresses and has a critical schema typo. |
| **Security Risk** | 🟡 Medium | Missing sqrtPriceLimitX96 and the required-field typo create notable UX/clarity risks; not immediately catastrophic in samples, but could enable misleading displays or omitted critical info in other cases. |

#### 💡 Key Recommendations
- **Fix the schema bug now:** correct `"params.amountOutMininimum"` → `"params.amountOutMinimum"` in `required`. This is critical so implementations reliably require and display the minimum receive amount.  
- **Surface sqrtPriceLimitX96 (conditionally):** add a field "Price limit" that is displayed whenever `sqrtPriceLimitX96 != 0`, and translate the value into an approximate price bound (or at minimum label it clearly as a price guard).  
- **Show token addresses and counterparty/pool**: add explicit, collapsible fields for `tokenIn` and `tokenOut` addresses and for the pool/counterparty contract (or make them easy to inspect). This defends against symbol resolution failures or malicious token names.  
- **Make "Receive Minimum" wording explicit:** display it as "*Receive (minimum guaranteed)*" and, if possible, also show the expected quote or estimated receive amount so users understand the difference.  
- **If UI supports it, surface slippage/expected output** (from the quoting source) and show any approvals/allowances associated with the token before signing.

---

If you want, I can produce a patched ERC-7730 JSON schema with the fixes (required key corrected, added fields for token addresses and sqrtPriceLimitX96 with display rules) that you can drop into your wallet UI.

---

## <a id="selector-09b81346"></a> exactOutput

**Selector:** `0x09b81346` | **Signature:** `exactOutput((bytes,address,uint256,uint256))`

**Contract Address:** `0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45` | **Chain ID:** 1

<details>
<summary><b>📋 ERC-7730 Format Definition</b></summary>

```json
{
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
```

</details>

<details>
<summary><b>🔍 Side-by-Side Comparison (ABI vs ERC-7730)</b></summary>

### Transaction 1: `0xb477200ab789141adf9962b3419cad4f0882db525879d2e8562de4d9cc9dd16e`

**Block:** 23540941 | **From:** 0x450ce91417c7aafb687b1e906de96334443b9374 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `path` | `0xdac17f958d2ee523a2206206994597...d29f223bce8043b84e8c8b282827790f` | ⚠️ Not shown |
| `recipient` | `0x026efa10261b8e057d6caeb74e6fbf25b2c211b7` | **Beneficiary**<br/>Format: `addressName` |
| `amountOut` | `7735694` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMaximum` | `194790` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xdac17f95...` | From: `0xc7bbec68...`<br/>To: `0x026efa10...` | 7.735694 USDT |
| 🔄 Transfer | `0xc02aaa39...` | From: `0xf359492d...`<br/>To: `0xc7bbec68...` | 0.001776 WETH |
| 🔄 Transfer | `0x467bccd9...` | From: `0x450ce914...`<br/>To: `0xf359492d...` | 1928.87 TEL |
| ❓ Unknown | `0xf359492d...` | Signature: `0xc42079f94a6350d7...` | - |
| ❓ Unknown | `0xc7bbec68...` | Signature: `0xc42079f94a6350d7...` | - |

### Transaction 2: `0x953f0f73ab5177b8f121e9b7b6b6e7f48bb68b76ef69a3c6f4bc9ab9afc60bca`

**Block:** 23540747 | **From:** 0xc0fb1c01de1148fa7b1f151a1740e52b375c47f1 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `path` | `0xb5d730d442e1d5b119fb4e5c843c48...b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `recipient` | `0xc0fb1c01de1148fa7b1f151a1740e52b375c47f1` | **Beneficiary**<br/>Format: `addressName` |
| `amountOut` | `1012443205289499244769` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMaximum` | `1579539542881894` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xb5d730d4...` | From: `0x4633afa7...`<br/>To: `0xc0fb1c01...` | 1012.443205 SABAI |
| 🔄 Transfer | `0xc02aaa39...` | From: `0xc0fb1c01...`<br/>To: `0x4633afa7...` | 0.001575 WETH |
| ❓ Unknown | `0x4633afa7...` | Signature: `0xc42079f94a6350d7...` | - |

### Transaction 3: `0xee6fbc2e89bbb9120cc29bd4fb189e40e516d62a8cfaf785dc3bf8606d9151d6`

**Block:** 23540699 | **From:** 0xc0fb1c01de1148fa7b1f151a1740e52b375c47f1 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `path` | `0xb5d730d442e1d5b119fb4e5c843c48...b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `recipient` | `0xc0fb1c01de1148fa7b1f151a1740e52b375c47f1` | **Beneficiary**<br/>Format: `addressName` |
| `amountOut` | `1286464045747231288294` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMaximum` | `2006684489586534` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xb5d730d4...` | From: `0x4633afa7...`<br/>To: `0xc0fb1c01...` | 1286.464046 SABAI |
| 🔄 Transfer | `0xc02aaa39...` | From: `0xc0fb1c01...`<br/>To: `0x4633afa7...` | 0.002001 WETH |
| ❓ Unknown | `0x4633afa7...` | Signature: `0xc42079f94a6350d7...` | - |

### Transaction 4: `0x846f4755f86b8de292660651a0851b48d39ba8a536bd83f92ed247fe21690555`

**Block:** 23540517 | **From:** 0x2766be7d41479e8cf315f8bf27ca1511f515e137 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `path` | `0xb5d730d442e1d5b119fb4e5c843c48...b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `recipient` | `0x2766be7d41479e8cf315f8bf27ca1511f515e137` | **Beneficiary**<br/>Format: `addressName` |
| `amountOut` | `2688376572226011727048` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMaximum` | `4194253396564214` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xb5d730d4...` | From: `0x4633afa7...`<br/>To: `0x2766be7d...` | 2688.376572 SABAI |
| 🔄 Transfer | `0xc02aaa39...` | From: `0x2766be7d...`<br/>To: `0x4633afa7...` | 0.004182 WETH |
| ❓ Unknown | `0x4633afa7...` | Signature: `0xc42079f94a6350d7...` | - |

### Transaction 5: `0x36f55eb49a706a288f23785c91492cf88f34544f1502ab3e210dfad2c3e40626`

**Block:** 23540446 | **From:** 0xc0fb1c01de1148fa7b1f151a1740e52b375c47f1 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `path` | `0xb5d730d442e1d5b119fb4e5c843c48...b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `recipient` | `0xc0fb1c01de1148fa7b1f151a1740e52b375c47f1` | **Beneficiary**<br/>Format: `addressName` |
| `amountOut` | `830201095827041941173` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMaximum` | `1295446791149595` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xb5d730d4...` | From: `0x4633afa7...`<br/>To: `0xc0fb1c01...` | 830.201096 SABAI |
| 🔄 Transfer | `0xc02aaa39...` | From: `0xc0fb1c01...`<br/>To: `0x4633afa7...` | 0.001292 WETH |
| ❓ Unknown | `0x4633afa7...` | Signature: `0xc42079f94a6350d7...` | - |

</details>

---

## 🔍 Clear Signing Audit Report

### 📋 Function: `exactOutput((bytes,address,uint256,uint256))`  
**Selector:** `0x09b81346`

---

### 1️⃣ Intent Analysis

> **Declared Intent:** *"Swap"*

The declared intent "Swap" is accurate — the call performs a token swap (exact output style) where the user specifies the amount to receive and a maximum amount to send.

---

### 2️⃣ Critical Issues

> 🔴 **CRITICAL** - Issues that could lead to users being deceived or losing funds

- **Token mapping is inverted:** The ERC‑7730 format maps `amountInMaximum` → token at `params.path.[0:20]` and `amountOut` → token at `params.path.[-20:]`, but in these samples the encoded path is ordered tokenOut → ... → tokenIn (first element = token being *received*, last element = token being *sent*). That causes the UI to label the *maximum to send* with the received token and the *amount to receive* with the sent token — a dangerous inversion that can mislead users about which token they are spending vs receiving.  
  - Example: Tx 0xb477… shows ERC‑7730 would display USDT as "Maximum Amount to Send" while the logs show the user actually sent TEL and received USDT.
- **Actual spent amount vs displayed maximum not emphasized or reconciled:** The UI only shows a maximum (good) but does not (and cannot at signing time) show that the *actual* input amount may be smaller; receipt_logs show a different actual input amount in these samples — users should be warned that the final spent amount may vary. Lack of clarity can cause misunderstanding about how much will leave their wallet.
- **Routing / intermediates and fees hidden:** The format does not surface the swap route (intermediate tokens such as WETH) nor pool fees encoded in the path — these are material for risk/baU understanding and could hide multi-hop behavior.
- **No disclosure about approvals (if any):** While these samples show no Approval events in the same transaction, the format does not call out whether the call will rely on pre-existing approvals or will require an approval flow — omission can be surprising if approval is required beforehand (not observed here but possible).
- **Unknown / contract internal events not explained:** The receipt_logs include non‑standard events representing swap internals; the user display should at least surface token transfers (it does) and route information (it does not).

If unaddressed, the token inversion alone is a high‑risk issue because users may approve/confirm spending the wrong token or expect receiving/sending the wrong asset.

---

### 3️⃣ Missing Parameters

> ⚠️ *Parameters present in ABI but NOT shown to users in ERC-7730*

| Parameter | Why It's Important | Risk Level |
|-----------|-------------------|:----------:|
| `params.path` (display of full route + fees) | Shows exact token route and pool fees (intermediates like WETH). Users need this to know if there are hidden hops or wrapped tokens involved. | 🔴 High |
| `actualAmountSpent` (post‑execution; not in ABI but critical to reconcile) | Receipt logs show actual token in transfers can be less than `amountInMaximum`; users may want clear messaging that the shown value is a maximum and final spend may differ. | 🟡 Medium |
| `approvalDisclosure` (whether an allowance/approval is required or used) | Approvals can lead to long‑lived token access; the UI should present whether this action depends on prior approvals. | 🟡 Medium |

If no parameters are missing from the ABI itself, the above are *presentation*/context parameters that should be surfaced or clarified to users.  

---

### 4️⃣ Display Issues

> 🟡 **Issues with how information is presented to users**

- **Token/amount pairing is ambiguous and currently wrong** because mapping uses wrong bytes of the path; labels will show amounts with the wrong tokens.
- **“Maximum Amount to Send” needs stronger qualifier** — show explicitly: *"Maximum — actual amount may be less"* and (where possible) show historical/expected actual or slippage.
- **No route visualization** — users cannot see the intermediate hop(s) (e.g., WETH) and pool fees embedded in the path.
- **Recipient label OK but could be clearer** — “Beneficiary” is fine; add an explicit statement if recipient ≠ sender.
- **No explicit indication of token direction** (which token is being debited vs credited) beyond amount labels — with the current inversion this is particularly hazardous.
- **Lack of approval visibility** — the UI should show if the router will use previously granted allowance or if a separate approval call is required.

---

### 5️⃣ Transaction Samples - What Users See vs What Actually Happens

(Illustrating the token inversion and actual transfer behavior. Showing 3 representative txs.)

#### 📝 Transaction 1: 0xb477200ab78914…d9cc9dd16e

**User Intent (from ERC-7730):**

| Field | ✅ User Sees | ❌ Hidden/Missing |
|-------|-------------|-------------------|
| Maximum Amount to Send | 194,790 (token: from params.path.[0:20]) — *displayed as if USDT* | Actually the user sent 192,887 TEL (token at path end) |
| Amount to Receive | 7,735,694 (token: from params.path.[-20:]) — *displayed as TEL* | Actually the user received 7,735,694 USDT (token at path start) |
| Beneficiary | 0x026efa10… (addressName) | — |

**Actual Effects (from receipt_logs):**

| Event | Details | Disclosed? |
|-------|---------|:----------:|
| Transfer | Token: 0xdac17f… (USDT), From: pool, To: 0x026efa10…, Amount: 7,735,694 (7.735694 USDT) | ❌ Shown as “Amount to Receive” but token mapping would be wrong in current format → **misleading** |
| Transfer | Token: 0x467bcc… (TEL), From: user 0x450c…, To: pool, Amount: 192,887 (1,928.87 TEL) | ❌ Should be shown as the token being sent; ERC‑7730 currently maps this to the receive token → **critical mismatch** |
| Swap internals | Unknown swap events (pool details, fees) | ❌ Not shown |

---

#### 📝 Transaction 2: 0x953f0f73ab5177b8…afc60bca

**User Intent (from ERC-7730):**

| Field | ✅ User Sees | ❌ Hidden/Missing |
|-------|-------------|-------------------|
| Maximum Amount to Send | 1,579,539,542,881,894 (raw) — token: params.path.[0:20] — *displayed as if SABAI* | Actually the user sent WETH (token at path end), ~0.001574 WETH |
| Amount to Receive | 1,012,443,205,289,499,244,769 (SABAI) — token: params.path.[-20:] | Correct amount received is SABAI — token mapping inverted in current format so could be wrong |
| Beneficiary | 0xc0fb1c01… | — |

**Actual Effects (from receipt_logs):**

| Event | Details | Disclosed? |
|-------|---------|:----------:|
| Transfer | Token: 0xb5d730… (SABAI), From: pool, To: 0xc0fb1c0…, Amount: 1,012.443205 SABAI | ✅ AmountOut shown but token mapping may be incorrect as implemented |
| Transfer | Token: 0xc02aaa… (WETH), From: user, To: pool, Amount: 0.001574 WETH | ❌ This is the input token user actually paid; ERC‑7730 would label maximum with the other token if mapping not fixed → **misleading** |

---

#### 📝 Transaction 3: 0x846f4755f86b8de2…169055

**User Intent (from ERC-7730):**

| Field | ✅ User Sees | ❌ Hidden/Missing |
|-------|-------------|-------------------|
| Maximum Amount to Send | 4,194,253,396,564,214 (raw) — token: params.path.[0:20] | Actually user sent ~0.004182 WETH (token at path end) |
| Amount to Receive | 2,688,376,572,226,011,727,048 (SABAI) | Actually received SABAI — mapping risk same as above |
| Beneficiary | 0x2766be7d… | — |

**Actual Effects (from receipt_logs):**

| Event | Details | Disclosed? |
|-------|---------|:----------:|
| Transfer | Token: SABAI to recipient (2,688.376572 SABAI) | ✅ AmountOut present but mapping must be correct |
| Transfer | Token: WETH from user to pool (0.004182 WETH) | ❌ Input token not correctly shown in current mapping |

---

### 6️⃣ Overall Assessment

| Metric | Score/Rating | Explanation |
|--------|--------------|-------------|
| **Coverage Score** | 5/10 | The format captures the core fields (amountOut, amountInMaximum, recipient) but misassigns tokens (inversion), hides route/fees and does not clarify actual vs maximum spend or approval requirements. |
| **Security Risk** | 🔴 High | Token/address inversion can actively mislead users about which asset they will send vs receive — this is a high‑severity UX→security issue. Lack of route + fee visibility increases the risk. |

#### 💡 Key Recommendations
- **Fix token mapping immediately:** For `exactOutput` (path encoded tokenOut → ... → tokenIn) map:
  - `amountOut` → token at `params.path.[0:20]` (first 20 bytes)
  - `amountInMaximum` → token at `params.path.[-20:]` (last 20 bytes)
  This corrects the send/receive token pairing and eliminates the critical inversion.
- **Show route and fees:** Display the full decoded path (token sequence and pool fee tiers). At minimum list intermediate tokens (e.g., WETH) and indicate this is a multi‑hop swap.
- **Clarify "Maximum" vs "Actual":** Add explicit text: *"Maximum Amount to Send — actual spent amount will be ≤ this; final amount determined at execution."* If the UI can, show expected or historical typical spend and final executed amount after the transaction completes.
- **Surface approval dependency:** Indicate whether this transaction will require prior token approval (or whether an approval call will be done), and the allowance token involved.
- **Log reconciliation (post‑execution):** When displaying historical/completed transactions, show both signed intention (max / amountOut) and actual receipt_logs (actual token transfer amounts) so users can reconcile what they approved vs what occurred.
- **Add warnings for non‑EOA recipients or exotic tokens:** Highlight if recipient is a contract or if any involved tokens are nonstandard (fee‑on‑transfer, rebasing, wrappers).

---

If you want, I can produce a small patch example (pseudo‑logic) showing how to extract the correct token addresses from the path for exactOutput and how to display the route and fee tiers for the user.

---

## <a id="selector-5023b4df"></a> exactOutputSingle

**Selector:** `0x5023b4df` | **Signature:** `exactOutputSingle((address,address,uint24,address,uint256,uint256,uint160))`

**Contract Address:** `0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45` | **Chain ID:** 1

<details>
<summary><b>📋 ERC-7730 Format Definition</b></summary>

```json
{
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
```

</details>

<details>
<summary><b>🔍 Side-by-Side Comparison (ABI vs ERC-7730)</b></summary>

### Transaction 1: `0x73517d686a6fc9a3390088ffbb9c412742b5bb75fa0d2fab508b62a97dd3cd70`

**Block:** 23540962 | **From:** 0xb1b2d032aa2f52347fbcfd08e5c3cc55216e8404 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `tokenIn` | `0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `tokenOut` | `0x944824290cc12f31ae18ef51216a223ba4063092` | ⚠️ Not shown |
| `fee` | `10000` | **Uniswap fee**<br/>Format: `unit` |
| `recipient` | `0x06435b9bab75b85baaaa75b86b25dcaae2319610` | **Beneficiary**<br/>Format: `addressName` |
| `amountOut` | `34118202154797750000000` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMaximum` | `92297407881239779` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |
| `sqrtPriceLimitX96` | `0` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0x94482429...` | From: `0x9c0df79f...`<br/>To: `0x06435b9b...` | 34118.202155 MASA |
| 🔄 Transfer | `0xc02aaa39...` | From: `0xb1b2d032...`<br/>To: `0x9c0df79f...` | 0.090793 WETH |
| ❓ Unknown | `0x9c0df79f...` | Signature: `0xc42079f94a6350d7...` | - |

### Transaction 2: `0xf4be9b67ce643cf2fcbd7dba902288172426b0c134f5d36ed2a5abf33538f215`

**Block:** 23540934 | **From:** 0xa10355775e0b1b167fe13453576bd360fd171fb3 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `tokenIn` | `0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48` | ⚠️ Not shown |
| `tokenOut` | `0xbdf43ecadc5cef51b7d1772f722e40596bc1788b` | ⚠️ Not shown |
| `fee` | `3000` | **Uniswap fee**<br/>Format: `unit` |
| `recipient` | `0xa10355775e0b1b167fe13453576bd360fd171fb3` | **Beneficiary**<br/>Format: `addressName` |
| `amountOut` | `7000000000000000000000` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMaximum` | `1965126820` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |
| `sqrtPriceLimitX96` | `0` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xbdf43eca...` | From: `0xf8e349d1...`<br/>To: `0xa1035577...` | 7000 SEI |
| 🔄 Transfer | `0xa0b86991...` | From: `0xa1035577...`<br/>To: `0xf8e349d1...` | 1947.040949 USDC |
| ❓ Unknown | `0xf8e349d1...` | Signature: `0xc42079f94a6350d7...` | - |

### Transaction 3: `0x6bc87ba5d0a26b492fe01cca5034fb45d2afa2f12285e51771e1acc4687a34b1`

**Block:** 23540908 | **From:** 0xa10355775e0b1b167fe13453576bd360fd171fb3 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `tokenIn` | `0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48` | ⚠️ Not shown |
| `tokenOut` | `0xbdf43ecadc5cef51b7d1772f722e40596bc1788b` | ⚠️ Not shown |
| `fee` | `3000` | **Uniswap fee**<br/>Format: `unit` |
| `recipient` | `0xa10355775e0b1b167fe13453576bd360fd171fb3` | **Beneficiary**<br/>Format: `addressName` |
| `amountOut` | `7000000000000000000000` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMaximum` | `1961589874` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |
| `sqrtPriceLimitX96` | `0` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xbdf43eca...` | From: `0xf8e349d1...`<br/>To: `0xa1035577...` | 7000 SEI |
| 🔄 Transfer | `0xa0b86991...` | From: `0xa1035577...`<br/>To: `0xf8e349d1...` | 1940.195346 USDC |
| ❓ Unknown | `0xf8e349d1...` | Signature: `0xc42079f94a6350d7...` | - |

### Transaction 4: `0x42fc05938d19e82bba655fa3b5c9e0e88d1adef57846e04133f760be6322fc22`

**Block:** 23540882 | **From:** 0xa10355775e0b1b167fe13453576bd360fd171fb3 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `tokenIn` | `0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48` | ⚠️ Not shown |
| `tokenOut` | `0xbdf43ecadc5cef51b7d1772f722e40596bc1788b` | ⚠️ Not shown |
| `fee` | `3000` | **Uniswap fee**<br/>Format: `unit` |
| `recipient` | `0xa10355775e0b1b167fe13453576bd360fd171fb3` | **Beneficiary**<br/>Format: `addressName` |
| `amountOut` | `7000000000000000000000` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMaximum` | `1953808595` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |
| `sqrtPriceLimitX96` | `0` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xbdf43eca...` | From: `0xf8e349d1...`<br/>To: `0xa1035577...` | 7000 SEI |
| 🔄 Transfer | `0xa0b86991...` | From: `0xa1035577...`<br/>To: `0xf8e349d1...` | 1936.241683 USDC |
| ❓ Unknown | `0xf8e349d1...` | Signature: `0xc42079f94a6350d7...` | - |

### Transaction 5: `0x9eec3b9f12b638846985573e870ff771c1e6a89dd3444f658a8dfe10c2b99975`

**Block:** 23540822 | **From:** 0xa10355775e0b1b167fe13453576bd360fd171fb3 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `tokenIn` | `0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48` | ⚠️ Not shown |
| `tokenOut` | `0xbdf43ecadc5cef51b7d1772f722e40596bc1788b` | ⚠️ Not shown |
| `fee` | `3000` | **Uniswap fee**<br/>Format: `unit` |
| `recipient` | `0xa10355775e0b1b167fe13453576bd360fd171fb3` | **Beneficiary**<br/>Format: `addressName` |
| `amountOut` | `7000000000000000000000` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMaximum` | `1950271649` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |
| `sqrtPriceLimitX96` | `0` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xbdf43eca...` | From: `0xf8e349d1...`<br/>To: `0xa1035577...` | 7000 SEI |
| 🔄 Transfer | `0xa0b86991...` | From: `0xa1035577...`<br/>To: `0xf8e349d1...` | 1929.039534 USDC |
| ❓ Unknown | `0xf8e349d1...` | Signature: `0xc42079f94a6350d7...` | - |

</details>

---

## 🔍 Clear Signing Audit Report

### 📋 Function: `exactOutputSingle((address,address,uint24,address,uint256,uint256,uint160))`  
**Selector:** `0x5023b4df`

---

### 1️⃣ Intent Analysis

> **Declared Intent:** *"Swap"*

The intent *"Swap"* is accurate and clear — this function performs a single-pool exact-output token swap (user requests a specific amount out and permits up to a maximum amount in).

---

### 2️⃣ Critical Issues

> 🔴 **CRITICAL** - Issues that could lead to users being deceived or losing funds

- **✅ No critical issues found.**

Explanation: The provided ERC-7730 fields map correctly to the core economic parameters (token amounts, fee, recipient) and there are no inverted token mappings or mislabeled numeric fields in these samples that would directly cause loss. Receipt logs show the expected tokenOut transfer to recipient and tokenIn transfer from the sender/payer (i.e., no hidden draining approval observed in these samples).

---

### 3️⃣ Missing Parameters

> ⚠️ Parameters present in ABI but NOT shown to users in ERC-7730

| Parameter | Why It's Important | Risk Level |
|-----------|--------------------|:----------:|
| `sqrtPriceLimitX96` | Acts as a price bound for the swap — non‑zero values can force a strict price limit or cause failed execution; can affect whether the swap executes and at what implied price. Users may want to know if a non‑default limit is set. | 🟡 Medium |
| (implicit) Pool / Route info | exactOutputSingle uses a single pool but the actual pool address (or counterparty) and whether a pool exists at the specified fee is not shown — helpful for transparency and auditing slippage/path. | 🟢 Low |
| Recipient type/contract indicator (ERC-7730 restricts recipient name source to "eoa") | If recipient is a contract, restricting name resolution to EOA may hide that destination is a contract (could change safety assumptions). | 🟡 Medium |

If no parameters are missing, write: **✅ All parameters are covered** — (not applicable here; see above).

---

### 4️⃣ Display Issues

> 🟡 Issues with how information is presented to users

- **Recipient resolver restricted to "eoa" only.** The format's `types: ["eoa"]` will not surface contract names or label contract recipients — this can mislead users into assuming the beneficiary is a simple wallet when it may be a contract.
- **No explicit token labels for "Sending" vs "Receiving".** The tokenAmount format references token paths, but the UI should explicitly label which token is being spent vs received (e.g., "Send (max) — WETH" and "Receive — MASA") to avoid confusion.
- **AmountInMaximum semantics not emphasized.** The label *"Maximum Amount to Send"* is correct but UIs should explicitly state that the *actual* amount taken may be lower (and the remainder refunded), otherwise users may think the maximum will always be debited.
- **Fee formatting could be misread if UI does not render percent symbol clearly.** The format uses decimals=4 and base="%" — if rendered poorly, a raw numeric (e.g., `3000`) could be confusing; ensure display shows `0.3000%` for `3000`.
- **No indication of pool/counterparty or swap event details.** Receipt logs include an Unknown swap event with pool address/topics; those details are not surfaced in metadata and could aid transparency (which pool and exact route executed).
- **No upfront disclosure of possible approvals/transferFrom patterns.** While approvals may not occur in these samples, the user should be warned that the router will call transferFrom on tokenIn and thus prior allowance is required (or a permit might be used).

---

---

### 5️⃣ Transaction Samples - What Users See vs What Actually Happens

(I analyze 3 representative transactions)

#### 📝 Transaction 1: 0x73517d68...cd70

**User Intent (from ERC-7730):**

| Field (Label) | ✅ User Sees | ❌ Hidden / Missing |
|--------------:|-------------:|--------------------:|
| **Maximum Amount to Send** | 0.090793 WETH (amountInMaximum) | Exact amount actually debited (0.090793... vs possibly lower) — *actual* spent not pre-known |
| **Amount to Receive** | 34,118.202155 MASA (amountOut) | Pool/address that will deliver MASA; post-exec swaps/events |
| **Uniswap fee** | 1.0000% (fee=10000 → 1.0000%) | Confirmation of which specific Uniswap v3 pool (fee tier) was used (pool address) |
| **Beneficiary** | 0x06435b9b...9610 | Whether recipient is EOA or contract (resolver restricted to EOA only) |

**Actual Effects (from receipt_logs):**

| Event | Details | Disclosed? |
|------:|---------|:----------:|
| Transfer (tokenOut) | 34,118.202155 MASA transferred from pool to 0x06435b9b...9610 | ✅ Token and amount shown as Amount to Receive |
| Transfer (tokenIn) | 0.090793017937683785 WETH transferred from sender to pool | ❌ Only max is shown; actual spent amount not explicitly shown in pre-signing UI (user saw maximum) |
| Swap/Pool event (Unknown) | Swap event emitted by pool (pool address present in topics) with internal accounting | ❌ Not surfaced in metadata (pool address & swap details hidden) |

---

#### 📝 Transaction 2: 0xf4be9b67...8215

**User Intent (from ERC-7730):**

| Field (Label) | ✅ User Sees | ❌ Hidden / Missing |
|--------------:|-------------:|--------------------:|
| **Maximum Amount to Send** | 1,965.126820 USDC (amountInMaximum) | Exact USDC debited (receipt shows 1,947.040949 USDC actually transferred) |
| **Amount to Receive** | 7,000 SEI (amountOut) | Which pool/contract delivered SEI |
| **Uniswap fee** | 0.3000% (fee=3000 → 0.3000%) | Pool address / counterparty |
| **Beneficiary** | 0xa10355...1fb3 | Contract vs EOA status not confirmed by resolver |

**Actual Effects (from receipt_logs):**

| Event | Details | Disclosed? |
|------:|---------|:----------:|
| Transfer (tokenOut) | 7,000 SEI to 0xa10355...1fb3 | ✅ Matches Amount to Receive |
| Transfer (tokenIn) | 1,947.040949 USDC from sender to pool | ❌ Pre-sign UI only displayed maximum (1,965.126820 USDC); actual spent not provided |
| Swap/Pool event (Unknown) | Swap emitted by pool (swap topics include router and recipient) | ❌ Not shown |

---

#### 📝 Transaction 3: 0x6bc87ba5...34b1

**User Intent (from ERC-7730):**

| Field (Label) | ✅ User Sees | ❌ Hidden / Missing |
|--------------:|-------------:|--------------------:|
| **Maximum Amount to Send** | 1,961.589874 USDC | Exact USDC debited (receipt: 1,940.195346 USDC actually transferred) |
| **Amount to Receive** | 7,000 SEI | Pool/counterparty details |
| **Uniswap fee** | 0.3000% | Pool address / swap id |
| **Beneficiary** | 0xa10355...1fb3 | Contract vs EOA status ambiguous |

**Actual Effects (from receipt_logs):**

| Event | Details | Disclosed? |
|------:|---------|:----------:|
| Transfer (tokenOut) | 7,000 SEI to user | ✅ Yes (amountOut shown) |
| Transfer (tokenIn) | 1,940.195346 USDC from user to pool | ❌ No — pre-sign shows only maximum |
| Swap/Pool event (Unknown) | Pool emitted swap event (internal details) | ❌ Hidden from metadata |

---

### 6️⃣ Overall Assessment

| Metric | Score/Rating | Explanation |
|--------|--------------|-------------|
| **Coverage Score** | 8 / 10 | Core economic parameters are presented (token in max, token out, fee, recipient). Missing non-critical but useful details (sqrtPriceLimitX96, pool address, recipient type) bring score down slightly. |
| **Security Risk** | 🟡 Medium | No immediate deceptive or fund‑draining issues in samples, but omission of certain fields and subtle UX caveats (recipient type, max vs actual) could mislead less‑experienced users. |

#### 💡 Key Recommendations
1. **Add `sqrtPriceLimitX96` to clear signing metadata** — display it (or explicitly show "no price limit set") so users know if a price cap is in effect. Mark non-zero values prominently as a risk/limit.
2. **Explicitly label tokens as "Send (max) — [TOKEN]" and "Receive — [TOKEN]"** — ensure tokenIn/tokenOut are shown with clear roles; show token symbols and decimals next to the amounts.
3. **Improve recipient resolution and labeling** — allow contract name/address resolution (not only EOA), and indicate *if the recipient is a contract* (big UX flag).
4. **Emphasize "Maximum" semantics and expected refund behavior** — display a short note: "Only up to this amount may be taken; actual spent may be less and remainder will be returned/refunded." Optionally show an estimated expected spend if available.
5. **Surface pool / route info (pool address or fee-tier confirmation)** — at minimum show the fee tier and optionally the pool address or a "single-pool swap" tag, so users know the counterparty.
6. **Ensure fee is shown as percent** (e.g., `0.3000%`) — avoid showing raw integers that may confuse users.

---

If you want, I can produce a suggested improved ERC-7730 JSON that adds sqrtPriceLimitX96, explicit token role labels, recipient contract indicator, and a "note" field explaining amountInMaximum semantics.

---

## <a id="selector-472b43f3"></a> swapExactTokensForTokens

**Selector:** `0x472b43f3` | **Signature:** `swapExactTokensForTokens(uint256,uint256,address[],address)`

**Contract Address:** `0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45` | **Chain ID:** 1

<details>
<summary><b>📋 ERC-7730 Format Definition</b></summary>

```json
{
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
```

</details>

<details>
<summary><b>🔍 Side-by-Side Comparison (ABI vs ERC-7730)</b></summary>

### Transaction 1: `0xae115d5b84ef67462646f8af2cddd14a024e279b112638e23d9611d909dbcbf9`

**Block:** 23513693 | **From:** 0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `amountIn` | `10000000000000000000000` | **Amount to Send**<br/>Format: `tokenAmount` |
| `amountOutMin` | `256603634` | **Minimum amount to Receive**<br/>Format: `tokenAmount` |
| `path` | `('0x5f474906637bdcda05f29c74653f...2ee523a2206206994597c13d831ec7')` | ⚠️ Not shown |
| `to` | `0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0x5f474906...` | From: `0x0c05a5fd...`<br/>To: `0xbdee9c99...` | 10000 DEFX |
| ✅ Approval | `0x5f474906...` | Owner: `0x0c05a5fd...`<br/>Spender: `0x68b34658...` | 115792089237316203707617735395386539918674240093853421928448 DEFX |
| 🔄 Transfer | `0xc02aaa39...` | From: `0xbdee9c99...`<br/>To: `0x0d4a11d5...` | 0.057125 WETH |
| ❓ Unknown | `0xbdee9c99...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0xbdee9c99...` | Signature: `0xd78ad95fa46c994b...` | - |
| 🔄 Transfer | `0xdac17f95...` | From: `0x0d4a11d5...`<br/>To: `0x0c05a5fd...` | 256.731675 USDT |
| ❓ Unknown | `0x0d4a11d5...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0x0d4a11d5...` | Signature: `0xd78ad95fa46c994b...` | - |

### Transaction 2: `0x9cf4f039ac234011fee38d5f9360030e63cb0a0772f6125f0d3745d471bc1ee5`

**Block:** 23513689 | **From:** 0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `amountIn` | `5000000000000000000000` | **Amount to Send**<br/>Format: `tokenAmount` |
| `amountOutMin` | `129013461` | **Minimum amount to Receive**<br/>Format: `tokenAmount` |
| `path` | `('0x5f474906637bdcda05f29c74653f...2ee523a2206206994597c13d831ec7')` | ⚠️ Not shown |
| `to` | `0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0x5f474906...` | From: `0x0c05a5fd...`<br/>To: `0xbdee9c99...` | 5000 DEFX |
| ✅ Approval | `0x5f474906...` | Owner: `0x0c05a5fd...`<br/>Spender: `0x68b34658...` | 115792089237316203707617735395386539918674240093853421928448 DEFX |
| 🔄 Transfer | `0xc02aaa39...` | From: `0xbdee9c99...`<br/>To: `0x0d4a11d5...` | 0.028721 WETH |
| ❓ Unknown | `0xbdee9c99...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0xbdee9c99...` | Signature: `0xd78ad95fa46c994b...` | - |
| 🔄 Transfer | `0xdac17f95...` | From: `0x0d4a11d5...`<br/>To: `0x0c05a5fd...` | 129.079137 USDT |
| ❓ Unknown | `0x0d4a11d5...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0x0d4a11d5...` | Signature: `0xd78ad95fa46c994b...` | - |

### Transaction 3: `0x853431d49b256338fd356cca5d6e0736bbd6f7d1ac934699b0a3740e2e78b04d`

**Block:** 23512094 | **From:** 0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `amountIn` | `5000000000000000000000` | **Amount to Send**<br/>Format: `tokenAmount` |
| `amountOutMin` | `128867534` | **Minimum amount to Receive**<br/>Format: `tokenAmount` |
| `path` | `('0x5f474906637bdcda05f29c74653f...2ee523a2206206994597c13d831ec7')` | ⚠️ Not shown |
| `to` | `0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0x5f474906...` | From: `0x0c05a5fd...`<br/>To: `0xbdee9c99...` | 5000 DEFX |
| ✅ Approval | `0x5f474906...` | Owner: `0x0c05a5fd...`<br/>Spender: `0x68b34658...` | 115792089237316203707617735395386539918674240093853421928448 DEFX |
| 🔄 Transfer | `0xc02aaa39...` | From: `0xbdee9c99...`<br/>To: `0x0d4a11d5...` | 0.028461 WETH |
| ❓ Unknown | `0xbdee9c99...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0xbdee9c99...` | Signature: `0xd78ad95fa46c994b...` | - |
| 🔄 Transfer | `0xdac17f95...` | From: `0x0d4a11d5...`<br/>To: `0x0c05a5fd...` | 128.953858 USDT |
| ❓ Unknown | `0x0d4a11d5...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0x0d4a11d5...` | Signature: `0xd78ad95fa46c994b...` | - |

### Transaction 4: `0xa19eed9d48d25badab773658785b346d93e22dd943b6abf28a7c8bb127fec6dd`

**Block:** 23510300 | **From:** 0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `amountIn` | `5000000000000000000000` | **Amount to Send**<br/>Format: `tokenAmount` |
| `amountOutMin` | `128315810` | **Minimum amount to Receive**<br/>Format: `tokenAmount` |
| `path` | `('0x5f474906637bdcda05f29c74653f...2ee523a2206206994597c13d831ec7')` | ⚠️ Not shown |
| `to` | `0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0x5f474906...` | From: `0x0c05a5fd...`<br/>To: `0xbdee9c99...` | 5000 DEFX |
| ✅ Approval | `0x5f474906...` | Owner: `0x0c05a5fd...`<br/>Spender: `0x68b34658...` | 115792089237316203707617735395386539918674240093853421928448 DEFX |
| 🔄 Transfer | `0xc02aaa39...` | From: `0xbdee9c99...`<br/>To: `0x0d4a11d5...` | 0.027973 WETH |
| ❓ Unknown | `0xbdee9c99...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0xbdee9c99...` | Signature: `0xd78ad95fa46c994b...` | - |
| 🔄 Transfer | `0xdac17f95...` | From: `0x0d4a11d5...`<br/>To: `0x0c05a5fd...` | 128.374769 USDT |
| ❓ Unknown | `0x0d4a11d5...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0x0d4a11d5...` | Signature: `0xd78ad95fa46c994b...` | - |

### Transaction 5: `0x5a64685153528e93c45a33a14b1ab6d70b61f9f75a47f6be2d038aaea434e165`

**Block:** 23509506 | **From:** 0x0f2a7cf7eb9ac27487c0595b50a2b69ff0345d92 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `amountIn` | `5000000` | **Amount to Send**<br/>Format: `tokenAmount` |
| `amountOutMin` | `94137490355594896` | **Minimum amount to Receive**<br/>Format: `tokenAmount` |
| `path` | `('0xdac17f958d2ee523a22062069945...c28e8ece4512bfe46f1f33687424ce')` | ⚠️ Not shown |
| `to` | `0x0f2a7cf7eb9ac27487c0595b50a2b69ff0345d92` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xdac17f95...` | From: `0x0f2a7cf7...`<br/>To: `0x0d4a11d5...` | 5 USDT |
| 🔄 Transfer | `0xc02aaa39...` | From: `0x0d4a11d5...`<br/>To: `0xc4704f13...` | 0.001091 WETH |
| ❓ Unknown | `0x0d4a11d5...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0x0d4a11d5...` | Signature: `0xd78ad95fa46c994b...` | - |
| 🔄 Transfer | `0x95af4af9...` | From: `0xc4704f13...`<br/>To: `0x0f2a7cf7...` | 95087422.656596 MANYU |
| ❓ Unknown | `0xc4704f13...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0xc4704f13...` | Signature: `0xd78ad95fa46c994b...` | - |

</details>

---

## 🔍 Clear Signing Audit Report

### 📋 Function: `swapExactTokensForTokens(uint256,uint256,address[],address)`  
**Selector:** `0x472b43f3`

---

### 1️⃣ Intent Analysis

> **Declared Intent:** *"Swap"*  

This is accurate and clear — the transaction is a token swap operation.

---

### 2️⃣ Critical Issues

> 🔴 **CRITICAL** - Issues that could lead to users being deceived or losing funds

- **❗ Approval not disclosed:** Receipt logs consistently show an Approval event granting a (practically) unlimited allowance of the input token to the router/spender (`0x68b3...c45`). ERC‑7730 format does not show approvals; users are not warned that an approval is being created or updated.  
  Risk: a large/unexpected allowance to a contract is a common attack surface (malicious router/compromised contract, or future exploit).
- **❗ Recipient ("to") omitted from UI:** The `to` parameter (recipient address) is not surfaced. If `to` is different from the signer, funds could be routed to a third party without the user being informed. Receipt logs show the final Transfer goes to the decoded `to` — but the user would not see that at signing time.
- **❗ Route / intermediate tokens hidden:** ERC‑7730 only shows amount in/out with tokens derived from the path ends; it does not show the full `path` (intermediate hops such as WETH). Intermediary swaps or wrapping/unwrapping (e.g., via WETH) are visible in logs but not in the signing UI — hiding the route can hide additional fees, slippage points, or interaction with unexpected contracts.
- **❗ Actual vs shown amounts:** ERC‑7730 displays only the minimum to receive (`amountOutMin`) — it does not show the expected/estimated output or make clear that the *actual* received amount may differ; the receipt_logs show the actual amounts. Not showing both min and an expected/estimate can be misleading about slippage and expected outcome.

If any of the above are present in your UI flow, they should be considered critical to disclose at signing. Otherwise:

✅ No other token-address inversion or token-amount mapping errors were observed in the provided samples.

---

### 3️⃣ Missing Parameters

> ⚠️ *Parameters present in ABI but NOT shown to users in ERC-7730*

| Parameter | Why It's Important | Risk Level |
|-----------|--------------------|:----------:|
| `path` (full array) | Shows the swap route and intermediate tokens/contracts (e.g., WETH). Intermediate hops affect counterparty contracts, fees and slippage. | 🔴 High |
| `to` (recipient) | Identifies who will receive the output tokens — could be different than signer. Critical to verify destination. | 🔴 High |
| `router/spender` (derived from Approval logs) | Shows which contract will be approved to spend your input token — very important when approval occurs. | 🔴 High |
| `approval details` (if emitted during tx) | Approval amount and token — unlimited approvals should be highlighted. | 🔴 High |

If you intentionally limit ERC‑7730 to a minimal view, note the above omissions are high-risk for user deception.

---

### 4️⃣ Display Issues

> 🟡 **Issues with how information is presented to users**

- **Labels are minimal:** "Amount to Send" / "Minimum amount to Receive" are OK but lack context such as token symbol (should show symbol + address) and whether the amount is the exact sent or just the input to the router.
- **No route visualization:** The swap path (e.g., DEFX → WETH → USDT) is not shown; users cannot see intermediate hops or which pools/contracts are used.
- **No spender/router identification:** The UI should display the router contract address that will be approved/used.
- **No approval warning:** Unlimited approval events are not surfaced or highlighted with explicit risk text (e.g., "This grants unlimited allowance to X").
- **No estimated output / slippage info:** Showing only amountOutMin can be confusing — users should see estimated output and slippage tolerance implied by the min.
- **Formatting/clarity:** Addresses and token symbols should be shown together (symbol + shortened address), decimals should be formatted and units made explicit (e.g., 10000 DEFX).

If none of these are shown in the signing UX, consider them actionable display improvements.

---

### 5️⃣ Transaction Samples - What Users See vs What Actually Happens

I analyze 3 representative samples.

#### 📝 Transaction 1: 0xae115d5b84ef6746...bcbf9

**User Intent (from ERC-7730):**

| Field | ✅ User Sees | ❌ Hidden/Missing |
|-------|-------------|-------------------|
| **Amount to Send** | 10000 DEFX (amountIn mapped to path[0]) | Approval to router (unlimited) not shown |
| **Minimum amount to Receive** | 256.603634 USDT (amountOutMin mapped to path[-1]) | Actual received: 256.731675 USDT (post-exec) |
| — | — | Swap route: DEFX → WETH → USDT (intermediate WETH hop not shown) |
| — | — | Recipient `to` present in calldata but not shown |

**Actual Effects (from receipt_logs):**

| Event | Details | Disclosed? |
|-------|---------|:----------:|
| Transfer | DEFX: from user → intermediary (0xbdee9c...1776) value 10000 DEFX | ❌ No (only amount to send shown; transfer destination not shown) |
| Approval | DEFX: owner user → spender 0x68b3...c45, value ≈ uint256_max | ❌ No (not shown) |
| Transfer | WETH: intermediary → pool, value ~0.057125 WETH | ❌ No (intermediate hop hidden) |
| Transfer | USDT: pool → user, value 256.731675 USDT (actual received) | ❌ Partially (min shown, actual received not shown at signing) |

---

#### 📝 Transaction 2: 0x9cf4f039ac234011...c1ee5

**User Intent (from ERC-7730):**

| Field | ✅ User Sees | ❌ Hidden/Missing |
|-------|-------------|-------------------|
| **Amount to Send** | 5000 DEFX | Approval to router (unlimited) |
| **Minimum amount to Receive** | 129.013461 USDT | Actual received: 129.079137 USDT |
| — | — | Route: DEFX → WETH → USDT |
| — | — | Recipient `to` |

**Actual Effects (from receipt_logs):**

| Event | Details | Disclosed? |
|-------|---------|:----------:|
| Transfer | DEFX from user → intermediary 5000 DEFX | ❌ No |
| Approval | DEFX owner→spender router, value ≈ uint256_max | ❌ No |
| Transfer | WETH intermediary → pool ~0.028721 WETH | ❌ No |
| Transfer | USDT pool → user 129.079137 USDT | ❌ Partially (only min shown) |

---

#### 📝 Transaction 3: 0x5a64685153528e93...34e165 (different path)

**User Intent (from ERC-7730):**

| Field | ✅ User Sees | ❌ Hidden/Missing |
|-------|-------------|-------------------|
| **Amount to Send** | 5 USDT (amountIn mapped to path[0]) | Approval(s) & spender not shown |
| **Minimum amount to Receive** | 94.137490355594896 MANYU (!) | Actual received: 95.087422.656596 MANYU |
| **Path ends** | USDT → MANYU (UI will show token mapping for ends) | Full path includes WETH intermediate (USDT → WETH → MANYU) not shown |

**Actual Effects (from receipt_logs):**

| Event | Details | Disclosed? |
|-------|---------|:----------:|
| Transfer | USDT: user → pool/intermediate 5 USDT | ❌ No |
| Transfer | WETH: intermediate → pool 0.001091 WETH | ❌ No |
| Transfer | MANYU: pool → user 95,087,422.656596 MANYU | ❌ Partially (only min shown) |

---

### 6️⃣ Overall Assessment

| Metric | Score/Rating | Explanation |
|--------|--------------|-------------|
| **Coverage Score** | 6 / 10 | amountIn and amountOutMin are correctly mapped to path[0]/path[-1], but important parameters (full path, recipient, and approval info) are omitted. |
| **Security Risk** | 🟡 Medium | The missing disclosures (especially approvals and recipient) create a meaningful risk of deception or unintended allowances, but the swap intent and basic amounts are correct. |

#### 💡 Key Recommendations
- **Show the full `path` (route) before signing.** Display intermediate tokens and the sequence (e.g., DEFX → WETH → USDT) and highlight any wrapped/unwrapped hops.
- **Surface recipient (`to`) prominently.** Show whether the output goes to the signer or another address; require explicit confirmation if recipient ≠ signer.
- **Detect and display approval events / allowance changes.** If an Approval is emitted in the same transaction, show: token, spender (address & ENS if available), and approval amount (highlight uint256_max as "Unlimited allowance"). Require an explicit warning for unlimited approvals.
- **Show estimated output + slippage alongside amountOutMin.** Present both an estimated/quoted output and the amountOutMin, and compute implied slippage percentage so user knows how much they tolerate.
- **Identify the router/spender contract.** Show the contract name/address that will receive approvals or execute the swap (e.g., 0x68b3...c45) and a short risk message if it is unfamiliar.
- **Post-execution confirmation (optional):** Where possible, show actual receipt amounts after execution or include an out-of-band TX result screen that proves what happened on-chain.

---

If you want, I can produce a suggested improved ERC‑7730 JSON schema that includes the missing fields (path, to, router/spender, approval flag, estimated output/slippage) and example UI strings for each field.

---

## <a id="selector-42712a67"></a> swapTokensForExactTokens

**Selector:** `0x42712a67` | **Signature:** `swapTokensForExactTokens(uint256,uint256,address[],address)`

**Contract Address:** `0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45` | **Chain ID:** 1

<details>
<summary><b>📋 ERC-7730 Format Definition</b></summary>

```json
{
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
```

</details>

<details>
<summary><b>🔍 Side-by-Side Comparison (ABI vs ERC-7730)</b></summary>

### Transaction 1: `0x2910d05b89260e249fdd26fea53d0a53b235793ae15dd02a9f60c9d9d5b0775d`

**Block:** 23532837 | **From:** 0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `amountOut` | `10000000000000000000000` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMax` | `257143507` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |
| `path` | `('0xdac17f958d2ee523a22062069945...7bdcda05f29c74653f6962bb0f8eda')` | ⚠️ Not shown |
| `to` | `0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xdac17f95...` | From: `0x0c05a5fd...`<br/>To: `0x0d4a11d5...` | 257.015263 USDT |
| 🔄 Transfer | `0xc02aaa39...` | From: `0x0d4a11d5...`<br/>To: `0xbdee9c99...` | 0.057053 WETH |
| ❓ Unknown | `0x0d4a11d5...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0x0d4a11d5...` | Signature: `0xd78ad95fa46c994b...` | - |
| 🔄 Transfer | `0x5f474906...` | From: `0xbdee9c99...`<br/>To: `0x0c05a5fd...` | 10000.000024 DEFX |
| ❓ Unknown | `0xbdee9c99...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0xbdee9c99...` | Signature: `0xd78ad95fa46c994b...` | - |

### Transaction 2: `0x61641f03c85ee1b8756d273eef3900590c5e3263e51ab1ff720654619edf02c3`

**Block:** 23532794 | **From:** 0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `amountOut` | `10000000000000000000000` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMax` | `255366619` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |
| `path` | `('0xdac17f958d2ee523a22062069945...7bdcda05f29c74653f6962bb0f8eda')` | ⚠️ Not shown |
| `to` | `0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xdac17f95...` | From: `0x0c05a5fd...`<br/>To: `0x0d4a11d5...` | 255.239495 USDT |
| 🔄 Transfer | `0xc02aaa39...` | From: `0x0d4a11d5...`<br/>To: `0xbdee9c99...` | 0.056635 WETH |
| ❓ Unknown | `0x0d4a11d5...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0x0d4a11d5...` | Signature: `0xd78ad95fa46c994b...` | - |
| 🔄 Transfer | `0x5f474906...` | From: `0xbdee9c99...`<br/>To: `0x0c05a5fd...` | 10000.000018 DEFX |
| ❓ Unknown | `0xbdee9c99...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0xbdee9c99...` | Signature: `0xd78ad95fa46c994b...` | - |

### Transaction 3: `0x219941ea0a7bf7feb68807b4af83458a4e2317ef645644c5313bdc079d28d801`

**Block:** 23532788 | **From:** 0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `amountOut` | `10000000000000000000000` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMax` | `253503688` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |
| `path` | `('0xdac17f958d2ee523a22062069945...7bdcda05f29c74653f6962bb0f8eda')` | ⚠️ Not shown |
| `to` | `0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xdac17f95...` | From: `0x0c05a5fd...`<br/>To: `0x0d4a11d5...` | 253.377161 USDT |
| 🔄 Transfer | `0xc02aaa39...` | From: `0x0d4a11d5...`<br/>To: `0xbdee9c99...` | 0.056221 WETH |
| ❓ Unknown | `0x0d4a11d5...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0x0d4a11d5...` | Signature: `0xd78ad95fa46c994b...` | - |
| 🔄 Transfer | `0x5f474906...` | From: `0xbdee9c99...`<br/>To: `0x0c05a5fd...` | 10000.00001 DEFX |
| ❓ Unknown | `0xbdee9c99...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0xbdee9c99...` | Signature: `0xd78ad95fa46c994b...` | - |

### Transaction 4: `0x55b9d84e26840ed5aea8ecbd1d0f6acce5d61cf801c698b41fad221fe0ba0a48`

**Block:** 23532780 | **From:** 0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `amountOut` | `25000000000000000000000` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMax` | `625719703` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |
| `path` | `('0xdac17f958d2ee523a22062069945...7bdcda05f29c74653f6962bb0f8eda')` | ⚠️ Not shown |
| `to` | `0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xdac17f95...` | From: `0x0c05a5fd...`<br/>To: `0x0d4a11d5...` | 625.407422 USDT |
| 🔄 Transfer | `0xc02aaa39...` | From: `0x0d4a11d5...`<br/>To: `0xbdee9c99...` | 0.138772 WETH |
| ❓ Unknown | `0x0d4a11d5...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0x0d4a11d5...` | Signature: `0xd78ad95fa46c994b...` | - |
| 🔄 Transfer | `0x5f474906...` | From: `0xbdee9c99...`<br/>To: `0x0c05a5fd...` | 25000.000029 DEFX |
| ❓ Unknown | `0xbdee9c99...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0xbdee9c99...` | Signature: `0xd78ad95fa46c994b...` | - |

### Transaction 5: `0x3388168f08c8198599d44b8e2a058375684d2a181e5f13a38675c1abc9def011`

**Block:** 23532478 | **From:** 0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `amountOut` | `7385000000000000000000` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMax` | `178582246` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |
| `path` | `('0xdac17f958d2ee523a22062069945...7bdcda05f29c74653f6962bb0f8eda')` | ⚠️ Not shown |
| `to` | `0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c` | ⚠️ Not shown |

#### 📋 Transaction Events (from receipt)

| Event | Token | Details | Amount |
|-------|-------|---------|--------|
| 🔄 Transfer | `0xdac17f95...` | From: `0x0c05a5fd...`<br/>To: `0x0d4a11d5...` | 178.492951 USDT |
| 🔄 Transfer | `0xc02aaa39...` | From: `0x0d4a11d5...`<br/>To: `0xbdee9c99...` | 0.039692 WETH |
| ❓ Unknown | `0x0d4a11d5...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0x0d4a11d5...` | Signature: `0xd78ad95fa46c994b...` | - |
| 🔄 Transfer | `0x5f474906...` | From: `0xbdee9c99...`<br/>To: `0x0c05a5fd...` | 7385.000036 DEFX |
| ❓ Unknown | `0xbdee9c99...` | Signature: `0x1c411e9a96e07124...` | - |
| ❓ Unknown | `0xbdee9c99...` | Signature: `0xd78ad95fa46c994b...` | - |

</details>

---

## 🔍 Clear Signing Audit Report

### 📋 Function: `swapTokensForExactTokens(uint256,uint256,address[],address)`  
**Selector:** `0x42712a67`

---

### 1️⃣ Intent Analysis

> **Declared Intent:** *"Swap"*  

The declared intent "Swap" is accurate and appropriate for this function — it initiates a token-for-token swap.

---

### 2️⃣ Critical Issues

> 🔴 **CRITICAL** - Issues that could lead to users being deceived or losing funds

- **❗ Missing recipient disclosure:** The metadata does not display the `to` parameter (recipient). The recipient may differ from the sender and is security‑critical (funds can be routed to another address).
- **❗ Actual vs displayed amounts not shown:** ERC-7730 shows the requested values (amountOut, amountInMax) but does **not** show the *actual* token amounts transferred (receipt_logs show actual amountIn and actual amountOut differing slightly). Users can be misled about exact value exchanged and slippage.
- **❗ Hidden routing / intermediate hops:** The metadata only formats the endpoints (path[0] and path[-1]) but does not show the full `path` / intermediate tokens used (e.g., USDT → WETH → DEFX). The choice of hops affects price and counterparty exposure.
- **❗ Swap executor / counterparty not shown:** The contract(s) or pair addresses that perform the swap (router / pair) are not surfaced. Receipt logs show transfers involving pair/router addresses — that is important for trust/forensics.
- **✅ Approvals in these samples are not present, but not disclosed if they occur:** The schema does not include an approvals field; if a swap includes an on‑chain approval or permit, it would not be signaled by the metadata.

If exploited (e.g., different `to`, unexpected hops, hidden router), a user could send value to an unexpected address or suffer unexpected slippage.

---

### 3️⃣ Missing Parameters

> ⚠️ *Parameters present in ABI but NOT shown to users in ERC-7730*

| Parameter | Why It's Important | Risk Level |
|-----------|-------------------:|:----------:|
| `path` | Shows intermediate tokens/hops used in swap (affects price, MEV exposure, counterparty) | 🔴 High |
| `to` | Recipient of the output tokens — may not be the caller | 🔴 High |

**Note:** The schema maps tokens for formatting using `path.[0]` and `path.[-1]`, but it does not *display* the path array or the `to` address. Also, the schema omits display of the *actual executed amounts* (derivable from receipt_logs), which is critical but not an ABI parameter — still recommended to display.

If no parameters are missing, write: **✅ All parameters are covered**

---

### 4️⃣ Display Issues

> 🟡 **Issues with how information is presented to users**

- Label clarity: *"Amount to Receive"* is ambiguous — for this function it is an exact requested amount (not a minimum). Label should say **"Exact amount to receive (requested)"**.
- Label should explicitly distinguish *Maximum* vs *Actual*: currently shows **"Maximum Amount to Send"** (amountInMax) but does not show **actual amount spent**; consider showing both.
- Missing recipient: `to` (recipient) is absent from display — users cannot confirm where final tokens will land.
- Missing path detail: intermediate hops (and count of hops) are not shown; users should see the full token path and token symbols/names, not just endpoints.
- Missing executor info: router / pair addresses performing swap are not shown; useful for trust decisions.
- Formatting: do not rely on raw integers — always show formatted amounts with token symbol and decimals, and show both requested and executed values when available.
- No explicit slippage or price impact shown (should be derived/displayed: amountInMax vs actual amountIn and amountOut requested vs actual).

If none: **✅ No display issues found**

---

### 5️⃣ Transaction Samples - What Users See vs What Actually Happens

I analyzed three representative transactions.

#### 📝 Transaction 1: `0x2910d05b...0775d`

**User Intent (from ERC-7730):**
| Field | ✅ User Sees | ❌ Hidden / Missing |
|-------|-------------:|--------------------|
| Amount to Receive (amountOut → path[-1]) | 10,000 DEFX (10000000000000000000000) | Actual received: **10,000.000024 DEFX** (receipt transfer: 10000000024063903059643) |
| Maximum Amount to Send (amountInMax → path[0]) | 257.143507 USDT (257143507 raw) | Actual spent: **257.015263 USDT** (transfer: 257015263) |
| Recipient (`to`) | **Not shown** | Recipient is the user address (0x0c05...) — would be critical if different |
| Path / hops | Only endpoint tokens are used for formatting | Actual path was USDT → WETH → DEFX (intermediate WETH transfer present in logs) |

**Actual Effects (from receipt_logs):**
| Event | Details | Disclosed? |
|-------|---------|:----------:|
| Transfer | USDT: from user → pair/router = **257.015263 USDT** | ❌ No (ERC-7730 only showed amountInMax, not actual transfer) |
| Transfer | WETH: intermediate transfer (pair → intermediary) = **0.057053 WETH** | ❌ No (intermediate hops hidden) |
| Transfer | DEFX: to user = **10,000.000024 DEFX** | ❌ No (user saw requested 10000 DEFX but not actual on‑chain value) |

---

#### 📝 Transaction 2: `0x55b9d84e...a0a48` (larger swap)

**User Intent (from ERC-7730):**
| Field | ✅ User Sees | ❌ Hidden / Missing |
|-------|-------------:|--------------------|
| Amount to Receive | 25,000 DEFX | Actual received: **25,000.000029 DEFX** |
| Maximum Amount to Send | 625.719703 USDT | Actual spent: **625.407422 USDT** |
| Path / hops | Only endpoint formatting | Actual: USDT → WETH → DEFX (intermediate WETH) |
| Recipient | **Not shown** | On-chain transfer goes to user (but not explicitly displayed) |

**Actual Effects (from receipt_logs):**
| Event | Details | Disclosed? |
|-------|---------|:----------:|
| Transfer | USDT: **625.407422 USDT** debited from user | ❌ No |
| Transfer | WETH: **0.138772 WETH** intermediate | ❌ No |
| Transfer | DEFX: **25,000.000029 DEFX** credited to user | ❌ No |

---

#### 📝 Transaction 3: `0x3388168f...ef011`

**User Intent (from ERC-7730):**
| Field | ✅ User Sees | ❌ Hidden / Missing |
|-------|-------------:|--------------------|
| Amount to Receive | 7,385 DEFX | Actual received: **7,385.000036 DEFX** |
| Maximum Amount to Send | 178.582246 USDT | Actual spent: **178.492951 USDT** |
| Path / hops | Endpoint tokens only | Actual path includes WETH intermediate |
| Recipient | **Not shown** | On-chain transfer goes to user |

**Actual Effects (from receipt_logs):**
| Event | Details | Disclosed? |
|-------|---------|:----------:|
| Transfer | USDT: **178.492951 USDT** debited | ❌ No |
| Transfer | WETH: **0.039692 WETH** intermediate | ❌ No |
| Transfer | DEFX: **7,385.000036 DEFX** credited | ❌ No |

---

### 6️⃣ Overall Assessment

| Metric | Score / Rating | Explanation |
|--------|----------------|-------------|
| **Coverage Score** | 5 / 10 | Displays the two key numeric ABI fields and maps them to token endpoints correctly, but omits several high‑importance fields (full path, recipient) and does not show actual on‑chain amounts or executor info. |
| **Security Risk** | 🟡 Medium | Missing recipient and hidden intermediary hops / actual amounts can mislead users about destination and true cost; this is a medium risk (can lead to confusion, unexpected slippage or misdirected funds if recipient differs). |

#### 💡 Key Recommendations
- **Display the `to` (recipient) explicitly.** Show address, ENS if available, and whether `to` equals the signer. This is high priority.
- **Show full token path (all hops) with symbols and addresses.** Clearly list intermediary tokens and number of hops so users can reason about routing and counterparty exposure.
- **Show both requested and actual executed amounts (when available).** After execution (or in post‑execution view), display the actual token transfers from receipt_logs (actual amountIn, actual amountOut) and highlight differences vs requested/specified amounts (slippage). For pre‑sign display, present estimated actuals and clear slippage bounds (amountInMax vs expected amount).
- **Surface the swap executor / pair/router addresses.** Indicate which contract(s) will perform the swap (router, pair). This helps users avoid unexpected third‑party contracts.
- **Improve labels and context:** Use precise labels like *"Exact amount requested to receive"*, *"Maximum amount allowed to send (slippage cap)"*, and show explicit disclaimers about potential minor rounding differences.
- **If approvals/permits occur or are required, include them in the display.** Show any approvals or permit uses, with spender address and allowance amount.

---

If you want, I can produce a patched ERC-7730 JSON proposal that adds the missing fields (path display, `to`, and an estimated/actual-amount section) with suggested labels and formatting.

---

