# 📊 Clear Signing Audit Report

**Contract ID:** Uniswap v3 Router 2
**Total Deployments Analyzed:** 1
**Chain IDs:** 1

---

## Summary Table

| Function | Selector | Severity | Issues | Coverage | Link |
|----------|----------|----------|--------|----------|------|
| `exactInput` | `0xb858183f` | 🔴 Critical | However, there is a **practical critical risk** if the UI or... | 75% | [View](#selector-b858183f) |
| `exactInputSingle` | `0x04e45aaf` | 🔴 Critical | **Typo in `required` array:** `"params.amountOutMininimum"` ... | 57% | [View](#selector-04e45aaf) |
| `exactOutput` | `0x09b81346` | 🔴 Critical | **Token mapping appears inverted for exactOutput:** The sche... | 75% | [View](#selector-09b81346) |
| `exactOutputSingle` | `0x5023b4df` | 🔴 Critical | **❗ Token addresses are not exposed as display fields.** The... | 57% | [View](#selector-5023b4df) |
| `swapExactTokensForTokens` | `0x472b43f3` | 🔴 Critical | **Recipient ("to") is not displayed.** The ERC‑7730 format o... | 50% | [View](#selector-472b43f3) |
| `swapTokensForExactTokens` | `0x42712a67` | 🔴 Critical | **Recipient ("to") is not exposed.** The ERC‑7730 schema doe... | 50% | [View](#selector-42712a67) |

---

## 📈 Statistics

| Metric | Count |
|--------|-------|
| 🔴 Critical | 6 |
| 🟡 Major | 0 |
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

### Transaction 1: `0x068860fc1f49ce1b8a55dcd6a48d64cf1e6262cb76a84e5fd072881c998fc001`

**Block:** 23539113 | **From:** 0x2766be7d41479e8cf315f8bf27ca1511f515e137 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `path` | `0xb5d730d442e1d5b119fb4e5c843c48...b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `recipient` | `0x2766be7d41479e8cf315f8bf27ca1511f515e137` | **Beneficiary**<br/>Format: `addressName` |
| `amountIn` | `2207940223520325291033` | **Amount to Send**<br/>Format: `tokenAmount` |
| `amountOutMinimum` | `3409584156940987` | **Minimum amount to Receive**<br/>Format: `tokenAmount` |

### Transaction 2: `0x3425faaa39b843d2c3503ccef96a3997bbc4620d077c885092dc3829dc2843c8`

**Block:** 23539088 | **From:** 0x2766be7d41479e8cf315f8bf27ca1511f515e137 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `path` | `0xb5d730d442e1d5b119fb4e5c843c48...b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `recipient` | `0x2766be7d41479e8cf315f8bf27ca1511f515e137` | **Beneficiary**<br/>Format: `addressName` |
| `amountIn` | `2062749301605948697294` | **Amount to Send**<br/>Format: `tokenAmount` |
| `amountOutMinimum` | `3186441072039250` | **Minimum amount to Receive**<br/>Format: `tokenAmount` |

### Transaction 3: `0xe91fb6bff41bfd63bc1a36d5df5aa002451bf36876992f09901b324027c68037`

**Block:** 23539037 | **From:** 0xc0fb1c01de1148fa7b1f151a1740e52b375c47f1 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `path` | `0xb5d730d442e1d5b119fb4e5c843c48...b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `recipient` | `0xc0fb1c01de1148fa7b1f151a1740e52b375c47f1` | **Beneficiary**<br/>Format: `addressName` |
| `amountIn` | `1361507076310741424364` | **Amount to Send**<br/>Format: `tokenAmount` |
| `amountOutMinimum` | `2103758557896739` | **Minimum amount to Receive**<br/>Format: `tokenAmount` |

### Transaction 4: `0xe4e3dba8255da531d47486010adae36be68da84db04dc84a04867a557f352362`

**Block:** 23538960 | **From:** 0xeb9e34ff307922ab860cddead51de158c8497190 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `path` | `0xdac17f958d2ee523a2206206994597...f664d76c69d2eea607cd793565af42b8` | ⚠️ Not shown |
| `recipient` | `0xcb3e61fc9f8c5b09f75b1b4b41a2c2fdbbb9ba01` | **Beneficiary**<br/>Format: `addressName` |
| `amountIn` | `9506439244` | **Amount to Send**<br/>Format: `tokenAmount` |
| `amountOutMinimum` | `5599657689933634600960` | **Minimum amount to Receive**<br/>Format: `tokenAmount` |

### Transaction 5: `0xa4153c7892b3bf037cbe259e1f551e65e7ffab35f749444517b3c6d0047ca507`

**Block:** 23538949 | **From:** 0x2973a0da0cbd8a3bd7a6aeab4b62a1365a22139c | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `path` | `0xdac17f958d2ee523a2206206994597...1f9092167fcfe0ea60f5ce053ab39a1e` | ⚠️ Not shown |
| `recipient` | `0xd2ffbca352c1757ec223f7c7e8d48db402722c66` | **Beneficiary**<br/>Format: `addressName` |
| `amountIn` | `500000000` | **Amount to Send**<br/>Format: `tokenAmount` |
| `amountOutMinimum` | `22503680712761989350962` | **Minimum amount to Receive**<br/>Format: `tokenAmount` |

</details>

---

## 🔍 Clear Signing Audit Report

### 📋 Function: `exactInput((bytes,address,uint256,uint256))`  
**Selector:** `0xb858183f`

---

### 1️⃣ Intent Analysis

> **Declared Intent:** *"Swap"*

The intent *"Swap"* is accurate and clear — this call performs a token-swap style routed/exact-input operation.

---

### 2️⃣ Critical Issues

> 🔴 **CRITICAL** - Issues that could lead to users being deceived or losing funds

- **✅ No outright critical mapping errors found** in the provided ERC-7730 metadata: the metadata maps the input amount to the first token in the path and the minimum receive amount to the last token in the path, which is the expected mapping for an exactInput swap.
- However, there is a **practical critical risk** if the UI or metadata engine fails to correctly extract token addresses from `params.path` (see display issues below). If the extracted token address is wrong or unresolved, users may see amounts with the wrong token symbol or no symbol at all — that can lead to losing funds by approving/sending the wrong token.

If the path parsing is robust then: **✅ No critical parameter mislabelling detected.**

---

### 3️⃣ Missing Parameters

> ⚠️ *Parameters present in ABI but NOT shown to users in ERC-7730*

| Parameter | Why It's Important | Risk Level |
|-----------|-------------------:|:---------:|
| `params.path` (full route / intermediate hops) | Shows the intermediate tokens and pools used by the swap — important to detect malicious token hops or unexpected route detours that can steal value via sandwich/coordinated pools. | 🟡 Medium |
| `params` raw bytes / explicit token addresses fallback | If token symbol/decimals lookup fails, user needs the raw address to confirm which tokens are involved. | 🔴 High |
| `params` fee hops (if encoded in path) / route summary | Fees and intermediate pools affect execution price and slippage; absence hides where value is routed. | 🟡 Medium |

Note: The ABI given here omits a `deadline` field (some Uniswap variants include one). If a deadline exists in other contract variants it should also be shown. Based on the provided signature, there is no `deadline` to show.

If the UI already exposes the raw path address list elsewhere, state: **If not, include raw token addresses.**

---

### 4️⃣ Display Issues

> 🟡 **Issues with how information is presented to users**

- Labeling is correct but **ambiguous** if token resolution fails: “Amount to Send” / “Minimum amount to Receive” depend on successful token lookup for symbol and decimals. If that lookup fails the numeric values alone are dangerous.
- The metadata only extracts *first* and *last* token addresses — **no route/hops summary** (intermediates and fees) is provided. Users cannot tell if the swap routes through unexpected tokens (malicious bridge tokens, inflated-fee pools).
- No explicit display of the **token contract addresses** as a fallback. UIs must show the raw addresses (or at least a link) when symbol/ENS/local name resolution fails.
- No indication of **slippage percentage** or how `amountOutMinimum` compares to the current quoted estimate — users may not understand how tight/loose the slippage tolerance is.
- The `tokenPath` slice expressions rely on correct byte offsets; if the UI’s slicing logic treats hex strings incorrectly (e.g., miscounting the 0x prefix or misinterpreting fee bytes), the displayed token could be wrong.

---

### 5️⃣ Transaction Samples - What Users See

I analyze three representative transactions from the provided samples. Each row shows what the ERC-7730 fields would present versus what is hidden.

#### 📝 Transaction 1: 0x068860fc…c001

| Field | ✅ User Sees (from ERC-7730) | ❌ Hidden / Missing |
|-------|-----------------------------|---------------------|
| Amount to Send | 2207940223520325291033 (formatted as tokenAmount using token at path first 20 bytes) | If token lookup fails: raw integer only; no explicit token address shown by metadata |
| Minimum amount to Receive | 3409584156940987 (formatted as tokenAmount using token at path last 20 bytes) | No slippage percentage or quoted expected receive shown |
| Beneficiary | recipient address shown/resolved via local/ENS | Route hops / intermediate tokens and pool fees not shown |

#### 📝 Transaction 2: 0xe91fb6bf…8037

| Field | ✅ User Sees | ❌ Hidden / Missing |
|-------|-------------|-------------------|
| Amount to Send | 1,361,507,076,310,741,424 (raw: 1361507076310741424364) — shown as tokenAmount for first token | No per-hop detail: user can't see if route uses a suspicious wrapped token |
| Minimum amount to Receive | 2,103,758,557,896,739 (raw) — shown as tokenAmount for last token | No token contract addresses shown if symbol lookup fails |
| Beneficiary | recipient address (matches tx.from here) | No deadline/slippage summary |

#### 📝 Transaction 3: 0xa4153c78…a507

| Field | ✅ User Sees | ❌ Hidden / Missing |
|-------|-------------|-------------------|
| Amount to Send | 500,000,000 (tokenAmount for first token in long path) | Long path present: intermediate tokens and fees are hidden |
| Minimum amount to Receive | 22,503,680,712,761,989,350,962 (raw) — shown as tokenAmount for final token | No route visualization or intermediate token symbols shown |
| Beneficiary | recipient address shown/resolved | No explicit link to token addresses or fee values per hop |

---

### 6️⃣ Overall Assessment

| Metric | Score/Rating | Explanation |
|--------|--------------:|-------------|
| **Coverage Score** | 7 / 10 | Covers the three core parameters (amount in, min out, recipient) which are the most critical, but omits full route visibility and an explicit fallback to raw token addresses. |
| **Security Risk** | 🟡 Medium | Core values are covered, but lack of visible route/intermediate token addresses and reliance on token resolution creates medium risk of user confusion or being tricked via route manipulation. |

#### 💡 Key Recommendations
- Include a **route summary**: list all token addresses (or symbols) and show intermediate fees/hops extracted from `params.path`, not only first and last addresses. This prevents hidden malicious hops.
- Always display **raw token contract addresses** (clickable) as a fallback whenever symbol/decimals resolution fails — mark unresolved tokens conspicuously (e.g., ⚠️ Unknown token).
- Show a **slippage/quote context**: present the quoted expected output and the slippage % implied by `amountOutMinimum` so users can see how tight the tolerance is.
- Validate byte-slicing logic in the UI: ensure correct offset handling (ignore 0x prefix, fee bytes handling) and test against multi-hop paths of various lengths.
- Optionally: surface the transaction sender (`from`) and a gas summary, and — if applicable in other ABI variants — the `deadline` field.

---

If implemented exactly as given and the UI reliably extracts token addresses from `params.path`, the metadata is adequate for basic confirmations; strengthening route visibility and explicit token-address fallbacks will materially reduce user risk.

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

### Transaction 1: `0xdda0565c0666fc1da390b099f7317c0c96277079cdaf562fba1c4e12bfffc482`

**Block:** 23539117 | **From:** 0x4c5f6ad6628d205259443ebcf6cc4cdd7d6cbf81 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `tokenIn` | `0x3c3a81e81dc49a522a592e7622a7e711c06bf354` | ⚠️ Not shown |
| `tokenOut` | `0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `fee` | `3000` | **Uniswap fee**<br/>Format: `unit` |
| `recipient` | `0x4c5f6ad6628d205259443ebcf6cc4cdd7d6cbf81` | **Beneficiary**<br/>Format: `addressName` |
| `amountIn` | `108255625170000000000` | **Send**<br/>Format: `tokenAmount` |
| `amountOutMinimum` | `64586100000000000` | **Receive Minimum**<br/>Format: `tokenAmount` |
| `sqrtPriceLimitX96` | `0` | ⚠️ Not shown |

### Transaction 2: `0xcbd8dfaafdc2ff6814eb4a67f1dfcb315ff021e5d6fc6eb5f4fb068827874c89`

**Block:** 23539110 | **From:** 0x4c5f6ad6628d205259443ebcf6cc4cdd7d6cbf81 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `tokenIn` | `0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `tokenOut` | `0xe6fd75ff38adca4b97fbcd938c86b98772431867` | ⚠️ Not shown |
| `fee` | `3000` | **Uniswap fee**<br/>Format: `unit` |
| `recipient` | `0x4c5f6ad6628d205259443ebcf6cc4cdd7d6cbf81` | **Beneficiary**<br/>Format: `addressName` |
| `amountIn` | `138629320000000000` | **Send**<br/>Format: `tokenAmount` |
| `amountOutMinimum` | `342452588340000000000` | **Receive Minimum**<br/>Format: `tokenAmount` |
| `sqrtPriceLimitX96` | `0` | ⚠️ Not shown |

### Transaction 3: `0xaf48d82d83997e3adf91d52172d1520cdd1fb4a892d24fae5d04ea2bded5b355`

**Block:** 23539104 | **From:** 0xdd66684b87f8568fe86853fb9f852444bf6edcd7 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `tokenIn` | `0x553f4cb7256d8fc038e91d36cb63fa7c13b624ab` | ⚠️ Not shown |
| `tokenOut` | `0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48` | ⚠️ Not shown |
| `fee` | `100` | **Uniswap fee**<br/>Format: `unit` |
| `recipient` | `0xdd66684b87f8568fe86853fb9f852444bf6edcd7` | **Beneficiary**<br/>Format: `addressName` |
| `amountIn` | `10000000000000000` | **Send**<br/>Format: `tokenAmount` |
| `amountOutMinimum` | `0` | **Receive Minimum**<br/>Format: `tokenAmount` |
| `sqrtPriceLimitX96` | `0` | ⚠️ Not shown |

### Transaction 4: `0x5ece178d986fa4cf49693271274c5188e5658f1a2e0d7b06983b16d3f28c69d2`

**Block:** 23539102 | **From:** 0xdd66684b87f8568fe86853fb9f852444bf6edcd7 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `tokenIn` | `0x553f4cb7256d8fc038e91d36cb63fa7c13b624ab` | ⚠️ Not shown |
| `tokenOut` | `0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48` | ⚠️ Not shown |
| `fee` | `100` | **Uniswap fee**<br/>Format: `unit` |
| `recipient` | `0xdd66684b87f8568fe86853fb9f852444bf6edcd7` | **Beneficiary**<br/>Format: `addressName` |
| `amountIn` | `10000000000000000` | **Send**<br/>Format: `tokenAmount` |
| `amountOutMinimum` | `0` | **Receive Minimum**<br/>Format: `tokenAmount` |
| `sqrtPriceLimitX96` | `0` | ⚠️ Not shown |

### Transaction 5: `0xd0bae23d021764a118e604b2e9a0dd9aab21898579c57b38fd54fcc969fbd56b`

**Block:** 23539093 | **From:** 0xdd66684b87f8568fe86853fb9f852444bf6edcd7 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `tokenIn` | `0x553f4cb7256d8fc038e91d36cb63fa7c13b624ab` | ⚠️ Not shown |
| `tokenOut` | `0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48` | ⚠️ Not shown |
| `fee` | `100` | **Uniswap fee**<br/>Format: `unit` |
| `recipient` | `0xdd66684b87f8568fe86853fb9f852444bf6edcd7` | **Beneficiary**<br/>Format: `addressName` |
| `amountIn` | `10000000000000000` | **Send**<br/>Format: `tokenAmount` |
| `amountOutMinimum` | `0` | **Receive Minimum**<br/>Format: `tokenAmount` |
| `sqrtPriceLimitX96` | `0` | ⚠️ Not shown |

</details>

---

## 🔍 Clear Signing Audit Report

### 📋 Function: `exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))`
**Selector:** `0x04e45aaf`

---

### 1️⃣ Intent Analysis

> **Declared Intent:** *"swap"*

The declared intent *swap* is accurate and clear — this function performs a single-hop token swap (exact input).

---

### 2️⃣ Critical Issues

> 🔴 **CRITICAL** - Issues that could lead to users being deceived or losing funds

- **Typo in `required` array:** `"params.amountOutMininimum"` is misspelled. Tooling that relies on the `required` list may fail to treat `amountOutMinimum` as required/important, causing wallets to omit or deprioritize the minimum-received protection — this is a high-risk metadata bug.
- **Recipient type restriction too narrow:** `recipient` `types` only lists `"eoa"`; the recipient may be a contract (or other special address). If the UI assumes only EOAs, users may not be warned when funds are routed to a contract — this can lead to loss or unexpected behavior.
- **Key parameter omitted from fields:** `sqrtPriceLimitX96` (a limit on allowed price movement) is not presented. A non-zero limit can dramatically change swap execution; omission can hide an important execution constraint (see Missing Parameters).

---

### 3️⃣ Missing Parameters

> ⚠️ Parameters present in ABI but NOT shown to users in ERC-7730

| Parameter | Why It's Important | Risk Level |
|-----------|--------------------|:----------:|
| `sqrtPriceLimitX96` | Sets a price boundary (limits how far the price can move during the swap). A non‑zero limit can cause partial fills, revert, or different pricing behavior. | 🟡 Medium |
| `tokenIn` / `tokenOut` (explicit fields) | Although referenced via `tokenPath` inside `tokenAmount`, the tokens are not declared as explicit top-level fields in `fields` and are not required — explicit token pair display improves clarity and avoids accidental token inversion confusion. | 🟡 Medium |
| `recipient` type coverage | Not a missing ABI param but the metadata restricts recognized recipient types to `"eoa"`; wallets may not surface when recipient is a contract address. | 🟡 Medium |

If these are not shown or enforced, users can miss important constraints (price limit) or misinterpret where tokens are going.

---

### 4️⃣ Display Issues

> 🟡 Issues with how information is presented to users

- **`required` typo** (amountOutMininimum) may cause UIs to treat the minimum-received check as optional/low-priority — misleading.
- **Recipient label/typing:** Label “Beneficiary” is fine, but the `addressName` types only include `eoa` and sources `local`, `ens` — this may fail to identify or warn about contract recipients or ENS-less addresses.
- **Token pair presentation:** The format relies on `tokenAmount` with `tokenPath`, but no explicit “From → To” pair summary is present; users benefit from a clear token-pair header (e.g., “Sell X TOKEN → Buy Y TOKEN”).
- **Fee formatting clarity:** `decimals: 4` with base `%` will show values like `0.3000%`; consider trimming insignificant zeros or adding explanatory text (“Pool fee”). Not a security bug but a UX nit.
- **No explicit display for `sqrtPriceLimitX96` when non-zero:** Missing context for what the limit means (could be shown only when non-zero with an explanation).

If none of the UI/tooling shows `sqrtPriceLimitX96`, users won’t be aware of an execution guard that might cause swaps to revert or behave unexpectedly.

---

### 5️⃣ Transaction Samples - What Users See

Analyzed transactions use the provided fields (Send, Receive Minimum, Uniswap fee, Beneficiary). I show what *should* be displayed from the ERC‑7730 fields and what remains hidden.

#### 📝 Transaction 1: 0xdda0565c0666fc...c482

| Field | ✅ User Sees | ❌ Hidden / Missing |
|-------|-------------|---------------------|
| **Send** (params.amountIn / tokenIn) | 108.25562517 <tokenIn symbol> (formatted token amount) | — (token amount displayed via tokenPath) |
| **Receive Minimum** (params.amountOutMinimum / tokenOut) | 0.06458610 WETH (formatted) | — (min shown) |
| **Uniswap fee** (params.fee) | 0.3000% | — |
| **Beneficiary** (params.recipient) | 0x4c5f6a... (resolved via ENS/local if available) | May not be flagged as *contract* recipient (metadata restricts to EOA types) |
| **Hidden** | — | `sqrtPriceLimitX96` = 0 (not shown) |

#### 📝 Transaction 2: 0xcbd8dfaa...4c89

| Field | ✅ User Sees | ❌ Hidden / Missing |
|-------|-------------|---------------------|
| **Send** | 0.13862932 WETH | — |
| **Receive Minimum** | 342.45258834 <tokenOut symbol> | — |
| **Uniswap fee** | 0.3000% | — |
| **Beneficiary** | 0x4c5f6a... | As above, no explicit contract detection via metadata |
| **Hidden** | — | `sqrtPriceLimitX96` = 0 (not shown) |

#### 📝 Transaction 3: 0xaf48d82d...b355

| Field | ✅ User Sees | ❌ Hidden / Missing |
|-------|-------------|---------------------|
| **Send** | 0.010000000000000? Wait — amountIn = 0.01 token? (shown as amount with token symbol) | — |
| **Receive Minimum** | 0 (explicitly shown) | — |
| **Uniswap fee** | 0.0100% (fee = 100 → 0.01%) | May be unclear to some users unless labeled “pool fee” |
| **Beneficiary** | 0xdd6668... | No contract-warning if recipient is contract |
| **Hidden** | — | `sqrtPriceLimitX96` = 0 (not shown) |

(Notes: token amounts above are the decoded integer amounts interpreted as 18-decimal tokens — the `tokenAmount` formatter is expected to resolve decimals and symbols; exact visual depends on wallet.)

---

### 6️⃣ Overall Assessment

| Metric | Score/Rating | Explanation |
|--------|--------------|-------------|
| **Coverage Score** | 7 / 10 | Fields cover the main economic parameters (amount in, min out, fee, recipient) and token mapping is present via `tokenPath`, but metadata omissions/typos and missing price limit reduce completeness. |
| **Security Risk** | 🟡 Medium | The typo in `required` and omission of `sqrtPriceLimitX96`/recipient-type detection can cause important execution constraints or routing targets to be overlooked; not immediately catastrophic in most cases, but can lead to surprising behavior or loss in edge cases. |

#### 💡 Key Recommendations
- Fix the **typo in `required`**: change `"params.amountOutMininimum"` → `"params.amountOutMinimum"` so tooling treats the minimum received as required/critical.
- **Add `sqrtPriceLimitX96` to `fields`** and display it (or show it only when non-zero) with a short explanatory tooltip: “Price limit guard — non‑zero value restricts allowed execution price.”
- Explicitly include `tokenIn` and `tokenOut` as top-level displayed fields (or add a single “Sell → Buy” pair line) so users clearly see the token pair and direction.
- Broaden `recipient` `types` and `sources` to include contract detection (e.g., `"contract"`) and display a clear warning when recipient is a contract address.
- Slight UX improvement: show the fee as “Pool fee: 0.3000% (Uniswap v3 pool fee tier)” and consider trimming insignificant zeros in the display.

---

If you want, I can produce a corrected ERC‑7730 JSON (with the fixes applied) so wallets/tools can adopt it immediately.

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

### Transaction 1: `0x14f424b68ed502764f17a8549f8a26cfecc7ef9b35a41c97f3cd9aa3364fa407`

**Block:** 23539016 | **From:** 0xc0fb1c01de1148fa7b1f151a1740e52b375c47f1 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `path` | `0xb5d730d442e1d5b119fb4e5c843c48...b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `recipient` | `0xc0fb1c01de1148fa7b1f151a1740e52b375c47f1` | **Beneficiary**<br/>Format: `addressName` |
| `amountOut` | `438638368777997845508` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMaximum` | `686008405560869` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |

### Transaction 2: `0x7fdf1c91d12e07cabc7f5ec0fe092b03429c0eadc0066e7728e72fe1de0ab8f0`

**Block:** 23538737 | **From:** 0x2766be7d41479e8cf315f8bf27ca1511f515e137 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `path` | `0xb5d730d442e1d5b119fb4e5c843c48...b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `recipient` | `0x2766be7d41479e8cf315f8bf27ca1511f515e137` | **Beneficiary**<br/>Format: `addressName` |
| `amountOut` | `2071513712387236056203` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMaximum` | `3239676720325398` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |

### Transaction 3: `0x5d96baed8e8b1ef1edc0d9cef294a83aadcd542f611d78ff48105b0e3eae7309`

**Block:** 23538734 | **From:** 0xc0fb1c01de1148fa7b1f151a1740e52b375c47f1 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `path` | `0xb5d730d442e1d5b119fb4e5c843c48...b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `recipient` | `0xc0fb1c01de1148fa7b1f151a1740e52b375c47f1` | **Beneficiary**<br/>Format: `addressName` |
| `amountOut` | `357368060859137711965` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMaximum` | `558818881734135` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |

### Transaction 4: `0x23e89e554733c3296eb70d06a06749c843854b40a695467f8130ca9b3a47f665`

**Block:** 23538653 | **From:** 0x2766be7d41479e8cf315f8bf27ca1511f515e137 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `path` | `0xb5d730d442e1d5b119fb4e5c843c48...b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `recipient` | `0x2766be7d41479e8cf315f8bf27ca1511f515e137` | **Beneficiary**<br/>Format: `addressName` |
| `amountOut` | `2262466042022813797723` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMaximum` | `3537105158025885` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |

### Transaction 5: `0xe58fb8992b703c443648378bc5fa9caed17b8700237d312fb6c53dc09761e633`

**Block:** 23538601 | **From:** 0xc0fb1c01de1148fa7b1f151a1740e52b375c47f1 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `path` | `0xb5d730d442e1d5b119fb4e5c843c48...b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `recipient` | `0xc0fb1c01de1148fa7b1f151a1740e52b375c47f1` | **Beneficiary**<br/>Format: `addressName` |
| `amountOut` | `2307154107687936715021` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMaximum` | `3605674579604660` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |

</details>

---

## 🔍 Clear Signing Audit Report

### 📋 Function: `exactOutput((bytes,address,uint256,uint256))`  
**Selector:** `0x09b81346`

---

### 1️⃣ Intent Analysis

> **Declared Intent:** *"Swap"*

The intent *"Swap"* is accurate and clear — this is an on‑chain swap where the caller requests an exact output amount and supplies a maximum input amount.

---

### 2️⃣ Critical Issues

> 🔴 **CRITICAL** - Issues that could lead to users being deceived or losing funds

- **Token mapping appears inverted for exactOutput:** The schema maps
  - `params.amountInMaximum` → token at `params.path.[0:20]`
  - `params.amountOut` → token at `params.path.[-20:]`
  but for Uniswap‑style `exactOutput` the encoded `path` is typically in *reverse* (output → input). That means the format will show the wrong token next to each amount (labels "Maximum Amount to Send" and "Amount to Receive" could be swapped vs actual tokens), which is a high‑risk UI deception and can cause users to confirm sending the wrong asset.
- **Route (path) hidden / insufficiently exposed:** Only first/last 20 bytes are used to infer tokens; intermediate hops and pool fees are not surfaced. Multi‑hop details and fees materially affect outcome and risk (front‑running, slippage, unexpected pools).
- **No explicit indicator that `path` is reversed for exactOutput:** UX must highlight encoding direction; otherwise frontends will mislabel tokens when reusing the same parsing logic for exactInput/exactOutput.

---

### 3️⃣ Missing Parameters

> ⚠️ *Parameters present in ABI but NOT shown to users in ERC-7730*

| Parameter | Why It's Important | Risk Level |
|-----------|-------------------:|:----------:|
| `params.path` (full routing + fees) | Shows route (intermediate tokens) and pool fees; affects slippage and expected execution path | 🔴 High |
| Intermediate fees in `path` (3‑byte fee steps) | Different pools/fees change price and front‑run risk; users should know if route uses unusual fees | 🟡 Medium |
| Token addresses (explicit) | Token symbol lookup can fail or be ambiguous; showing addresses lets advanced users verify | 🟡 Medium |
| `from` / payer identity (if different than recipient) | If recipient ≠ sender, funds may go to someone else — must be clear | 🟡 Medium |

If these are intentionally omitted to simplify UX, make them available via an "advanced details" view.

---

### 4️⃣ Display Issues

> 🟡 **Issues with how information is presented to users**

- Label mapping risk: current mapping suggests **Maximum Amount to Send** is tied to the path start — but for exactOutput the path start is generally the *output token*; this label will therefore be mismatched unless encoding direction is handled.
- **No explicit “route direction” or “path encoding” note** — users and wallets need a guardrail indicating whether path is input→output or output→input.
- **Token amount formatting depends on correct token decimals/symbols** — tokenSymbol/decimals lookup must use the extracted token address; if that fails the amount could appear raw/ambiguous.
- **Recipient formatting restricted to EOA sources only** — `types: ["eoa"]` excludes contract recipients; contract recipients can be legitimate (e.g., vaults) and should be resolvable or at least shown as contract (name/address).
- **No slippage or effective price shown** — showing only raw amounts omits the implied price and slippage vs market, which is important for decisions.

---

### 5️⃣ Transaction Samples - What Users See

I analyze three transactions and show what the current ERC‑7730 format will present (given the schema as written). Important: because of the path reversal issue, the shown token labels are likely swapped relative to the real on‑chain meaning.

#### 📝 Transaction 1: `0x14f424b68ed5…a407`

| Field | ✅ User Sees (per ERC‑7730) | ❌ Hidden / Missing |
|-------|----------------------------|---------------------|
| **Maximum Amount to Send** | `686008405560869` — token at `path[0:20]` (first token from path bytes) | The actual input token may be the *last* token in the encoded path for exactOutput; so token shown may be wrong. |
| **Amount to Receive** | `438638368777997845508` — token at `path[-20:]` (last token from path bytes) | Real received token likely corresponds to path start (reversed). Route/fees not shown. |

#### 📝 Transaction 2: `0x7fdf1c91d12e…b8f0`

| Field | ✅ User Sees | ❌ Hidden / Missing |
|-------|--------------|--------------------|
| **Amount to Receive** | `2071513712387236056203` — token from `path[-20:]` | If path is reversed for exactOutput, this shows the wrong token for received asset. |
| **Beneficiary** | `0x2766be7d41479e8c…` (displayed via addressName lookup) | No indicator if the beneficiary is a contract vs EOA beyond lookup; contract names/sources excluded. |

#### 📝 Transaction 3: `0x5d96baed8e8b…7309`

| Field | ✅ User Sees | ❌ Hidden / Missing |
|-------|-------------|--------------------|
| **Maximum Amount to Send** | `558818881734135` — token at `path[0:20]` | No route/fees; token likely incorrect if path reversed. |
| **Beneficiary** | `0xc0fb1c01de1148f…` | No slippage/price shown; intermediate hops not visible. |

---

### 6️⃣ Overall Assessment

| Metric | Score / Rating | Explanation |
|--------|----------------|-------------|
| **Coverage Score** | **5 / 10** | Schema captures the three core fields (max in, exact out, recipient) but misses full route, fee steps, and — critically — misinterprets token positions for exactOutput causing token/amount mismatch. |
| **Security Risk** | **🔴 High** | Wrong token labels for amounts can directly lead to users approving swaps on the wrong asset and losing funds; hidden route/fees increases risk. |

#### 💡 Key Recommendations
- For this selector (exactOutput), **reverse the tokenPath mapping**:
  - Map **Amount to Receive** → `params.path.[0:20]` (first token in encoded path for exactOutput)
  - Map **Maximum Amount to Send** → `params.path.[-20:]` (last token)
  - Or better: detect per‑function whether path is encoded input→output or output→input and adapt mapping.
- **Expose the full route (path)** including intermediate token addresses and 3‑byte fee steps in an “advanced details” view so users can verify pools and fees.
- **Show token addresses + symbols + decimals** (fallback to address if lookup fails), and surface a clear warning when recipient ≠ sender or recipient is a contract.
- **Add an explicit label/tooltip:** “Path is encoded output→input for exactOutput; tokens shown reflect that” (or automate the mapping so the user sees intuitive labels).
- **Test vectors:** include sample parsed displays for representative exactInput and exactOutput transactions to ensure frontends show correct token/amount pairing.

---

If you want, I can produce a corrected ERC‑7730 JSON snippet (fixing tokenPath indexes and adding a route field + fee parsing) and example UI renderings for one of the sample transactions.

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

### Transaction 1: `0x4d2c7dfc2865ea18732f8c4d6dc81d38b5dbd8ed8c180ab3fd75d6578ffc77eb`

**Block:** 23539018 | **From:** 0x096329d1b79ccbc76847ea62395cdb7156dfb958 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `tokenIn` | `0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `tokenOut` | `0x690f1eef8acead09ac695d9111af081045c6d5b7` | ⚠️ Not shown |
| `fee` | `10000` | **Uniswap fee**<br/>Format: `unit` |
| `recipient` | `0x096329d1b79ccbc76847ea62395cdb7156dfb958` | **Beneficiary**<br/>Format: `addressName` |
| `amountOut` | `4000000000000000000000` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMaximum` | `95664180092120796` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |
| `sqrtPriceLimitX96` | `0` | ⚠️ Not shown |

### Transaction 2: `0x2c95619adeba3876f3a77e120d0bc84251b5a2586d6016786dca94d4db29433b`

**Block:** 23538954 | **From:** 0xb1b2d032aa2f52347fbcfd08e5c3cc55216e8404 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `tokenIn` | `0xdac17f958d2ee523a2206206994597c13d831ec7` | ⚠️ Not shown |
| `tokenOut` | `0x52a8845df664d76c69d2eea607cd793565af42b8` | ⚠️ Not shown |
| `fee` | `3000` | **Uniswap fee**<br/>Format: `unit` |
| `recipient` | `0x06435b9bab75b85baaaa75b86b25dcaae2319610` | **Beneficiary**<br/>Format: `addressName` |
| `amountOut` | `1242208843959750400000` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMaximum` | `2131748831` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |
| `sqrtPriceLimitX96` | `0` | ⚠️ Not shown |

### Transaction 3: `0xc76b4b45f9d467d635547adf2fde2a32ae93aceb734491302c8884181f415aa8`

**Block:** 23538929 | **From:** 0x096329d1b79ccbc76847ea62395cdb7156dfb958 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `tokenIn` | `0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `tokenOut` | `0x690f1eef8acead09ac695d9111af081045c6d5b7` | ⚠️ Not shown |
| `fee` | `10000` | **Uniswap fee**<br/>Format: `unit` |
| `recipient` | `0x096329d1b79ccbc76847ea62395cdb7156dfb958` | **Beneficiary**<br/>Format: `addressName` |
| `amountOut` | `4000000000000000000000` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMaximum` | `94973858236756587` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |
| `sqrtPriceLimitX96` | `0` | ⚠️ Not shown |

### Transaction 4: `0x08eb21ab750e12f9859affcfc2b4c88ad4339b0c19857c866bb57743d9c4e713`

**Block:** 23538925 | **From:** 0x096329d1b79ccbc76847ea62395cdb7156dfb958 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `tokenIn` | `0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `tokenOut` | `0x690f1eef8acead09ac695d9111af081045c6d5b7` | ⚠️ Not shown |
| `fee` | `10000` | **Uniswap fee**<br/>Format: `unit` |
| `recipient` | `0x096329d1b79ccbc76847ea62395cdb7156dfb958` | **Beneficiary**<br/>Format: `addressName` |
| `amountOut` | `4000000000000000000000` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMaximum` | `95100843337601555` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |
| `sqrtPriceLimitX96` | `0` | ⚠️ Not shown |

### Transaction 5: `0xb047e6b3b3a3c2270dad91f381d8e78e9c707c591bd4fdbbdbe40e7e3e52d15f`

**Block:** 23538905 | **From:** 0x096329d1b79ccbc76847ea62395cdb7156dfb958 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `tokenIn` | `0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2` | ⚠️ Not shown |
| `tokenOut` | `0x690f1eef8acead09ac695d9111af081045c6d5b7` | ⚠️ Not shown |
| `fee` | `10000` | **Uniswap fee**<br/>Format: `unit` |
| `recipient` | `0x096329d1b79ccbc76847ea62395cdb7156dfb958` | **Beneficiary**<br/>Format: `addressName` |
| `amountOut` | `4000000000000000000000` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMaximum` | `94416599208197967` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |
| `sqrtPriceLimitX96` | `0` | ⚠️ Not shown |

</details>

---

## 🔍 Clear Signing Audit Report

### 📋 Function: `exactOutputSingle((address,address,uint24,address,uint256,uint256,uint160))`  
**Selector:** `0x5023b4df`

---

### 1️⃣ Intent Analysis

> **Declared Intent:** *"Swap"*  
The declared intent *Swap* is accurate: this function performs an exact-output token swap (you receive a specified amountOut and may spend up to amountInMaximum).

---

### 2️⃣ Critical Issues

> 🔴 **CRITICAL** - Issues that could lead to users being deceived or losing funds

- **❗ Token addresses are not exposed as display fields.** The format shows amounts using `tokenAmount` and references `params.tokenIn` / `params.tokenOut` in formatting params, but it does not include explicit fields that display the token symbols/addresses to the user. If a client ignores `tokenPath` or token resolution fails, users may not see *which* token they are sending vs receiving — this is high risk (wrong-token / wrong-direction confusion).
- **❗ Recipient display is constrained to EOA types only.** The `addressName` params restrict `types: ["eoa"]`; if the recipient is a contract (common for routers, dex aggregators, vaults), the UI might hide/obscure that fact and the user could be sending proceeds to a contract rather than their own wallet — potentially dangerous.
- **❗ Price-limit parameter (`sqrtPriceLimitX96`) is not displayed.** A non-zero sqrtPriceLimitX96 imposes a price limit; hiding it can conceal a subtle but important execution constraint that may alter expected price/slippage behavior (medium–high risk when non-zero).

---

### 3️⃣ Missing Parameters

> ⚠️ *Parameters present in ABI but NOT shown to users in ERC-7730*

| Parameter | Why It's Important | Risk Level |
|-----------|--------------------|:----------:|
| `params.tokenIn` (not displayed) | Identifies the token being spent; required to map amountInMaximum to a recognizable token symbol/address. If omitted, users may wrongly assume which asset is being taken. | 🔴 High |
| `params.tokenOut` (not displayed) | Identifies the token being received; required to map amountOut to a recognizable token symbol/address. | 🔴 High |
| `params.sqrtPriceLimitX96` | Sets a price bound for the swap; non-zero value can block or change execution price — important for understanding slippage/limits. | 🟡 Medium |
| Transaction `value` (ETH sent) / `from` (caller) — not part of this metadata | Native ETH value or caller identity can matter (wrapping/unwrapping WETH flows, unexpected native ETH transfer). | 🟡 Medium |

If these parameters are intentionally omitted because token metadata will be resolved from `tokenPath`, the UI must still explicitly show the resolved token symbol/address and indicate when resolution fails.

---

### 4️⃣ Display Issues

> 🟡 **Issues with how information is presented to users**

- Labeling: **"Uniswap fee"** is acceptable but could be clearer as **"Pool fee (Uniswap V3)"** — indicates that this is the pool tick fee (e.g., 0.3%) rather than a platform or service fee.
- Fee formatting: `decimals: 4` / `base: "%"`, `prefix: false` will show `10000` as `1.0000%` — consider trimming insignificant trailing zeros for readability (e.g., `1%` instead of `1.0000%`).
- Recipient type limits: restricting `types` to `["eoa"]` will not surface if the recipient is a contract; recommend allowing contract detection and explicitly labeling contract recipients (e.g., "Contract: 0x... (Uniswap Router)").
- Missing explicit token labels/addresses in the displayed field list — even if amounts are formatted with token metadata, the UI should still list `Token In` and `Token Out` as visible lines.
- No explicit indication that `amountOut` is *exactly* what will be received and `amountInMaximum` is a cap that may not be fully consumed; wording should clarify "Receive (exact):" vs "Spend (max):".

If no fixes: **✅ No additional presentation bugs beyond the above.**

---

### 5️⃣ Transaction Samples - What Users See

(Showing most relevant fields from the provided ERC-7730 mapping; hidden/missing columns note what the format does NOT explicitly show.)

#### 📝 Transaction 1: `0x4d2c7d…77eb`

| Field | ✅ User Sees (per ERC‑7730) | ❌ Hidden / Missing |
|-------|----------------------------|---------------------|
| Maximum Amount to Send | 0.095664180092120796 WETH (formatted from `amountInMaximum` using `params.tokenIn`) | Explicit `tokenIn` address or label field (if unresolved, user might not know token is WETH) |
| Amount to Receive | 4,000 (assumes 18 decimals) tokenOut symbol (formatted from `amountOut` using `params.tokenOut`) | Explicit `tokenOut` symbol/address; if token metadata not resolved, symbol missing |
| Uniswap fee | 1.0000% (from `fee = 10000`) | — |
| Beneficiary | 0x0963…b958 (resolved as EOA if possible) | Whether recipient is EOA vs contract (format restricts to `eoa` only) |
| Price limit | Not shown | `sqrtPriceLimitX96 = 0` (implicitly "no limit") — not displayed |

#### 📝 Transaction 2: `0x2c9561…9433b`

| Field | ✅ User Sees | ❌ Hidden / Missing |
|-------|-------------|--------------------|
| Maximum Amount to Send | 2,131.748831 USDT (amountInMaximum = 2,131,748,831 with USDT decimals=6) | Explicit `tokenIn` label/address (USDT should be shown explicitly) |
| Amount to Receive | ~1,242.208844 tokenOut (amountOut / 1e18) | Explicit `tokenOut` label/address |
| Uniswap fee | 0.3000% (fee = 3000) | — |
| Beneficiary | 0x0643…9610 | Whether recipient is contract vs EOA (contract would be hidden) |
| Price limit | Not shown | `sqrtPriceLimitX96 = 0` not displayed |

#### 📝 Transaction 3: `0xc76b4b…15aa8`

| Field | ✅ User Sees | ❌ Hidden / Missing |
|-------|-------------|--------------------|
| Maximum Amount to Send | 0.094973858236756587 WETH | tokenIn explicit label/address |
| Amount to Receive | 4,000 tokenOut (assumes 18 decimals) | tokenOut explicit label/address |
| Uniswap fee | 1.0000% | — |
| Beneficiary | 0x0963…b958 | Contract detection for recipient |
| Price limit | Not shown | `sqrtPriceLimitX96 = 0` not displayed |

---

### 6️⃣ Overall Assessment

| Metric | Score / Rating | Explanation |
|--------|----------------|-------------|
| **Coverage Score** | 7 / 10 | The format covers the most security‑critical numeric parameters (amountOut, amountInMaximum, fee, recipient) and provides tokenPath hooks for formatting, but it omits explicit token fields and the price-limit parameter which meaningfully affect user understanding. |
| **Security Risk** | 🟡 Medium | Core amounts and fee are shown, reducing basic risk, but missing explicit token labels/addresses and limited recipient type detection create a high-risk vector for mistaken asset or destination confusion. |

#### 💡 Key Recommendations
- **Add explicit token fields:** include `params.tokenIn` and `params.tokenOut` as displayed fields (label them "Token to Spend" / "Token to Receive" and show symbol + contract address). This removes ambiguity even if token resolution fails.
- **Expose price limit when present:** add a `sqrtPriceLimitX96` display field (or a computed human label like "Price limit: none" / "Price bound set") and only hide when clearly zero — users must know if a hard price constraint exists.
- **Allow/indicate contract recipients:** change `addressName` `types` to include contract detection and explicitly label recipient type (e.g., "Beneficiary (contract): 0x..." or "Beneficiary (EOA): 0x...").
- **Clarify semantics:** label amounts explicitly as "Receive (exact)" and "Spend (maximum)" to reduce misunderstandings about exact vs cap semantics.
- **Improve fee display:** consider trimming redundant trailing zeros (show `1%` instead of `1.0000%`) while preserving precision on hover/details.

---

If implemented, these changes will substantially reduce user confusion and the risk of sending the wrong token or sending proceeds to an unexpected contract.

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

### Transaction 2: `0x9cf4f039ac234011fee38d5f9360030e63cb0a0772f6125f0d3745d471bc1ee5`

**Block:** 23513689 | **From:** 0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `amountIn` | `5000000000000000000000` | **Amount to Send**<br/>Format: `tokenAmount` |
| `amountOutMin` | `129013461` | **Minimum amount to Receive**<br/>Format: `tokenAmount` |
| `path` | `('0x5f474906637bdcda05f29c74653f...2ee523a2206206994597c13d831ec7')` | ⚠️ Not shown |
| `to` | `0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c` | ⚠️ Not shown |

### Transaction 3: `0x853431d49b256338fd356cca5d6e0736bbd6f7d1ac934699b0a3740e2e78b04d`

**Block:** 23512094 | **From:** 0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `amountIn` | `5000000000000000000000` | **Amount to Send**<br/>Format: `tokenAmount` |
| `amountOutMin` | `128867534` | **Minimum amount to Receive**<br/>Format: `tokenAmount` |
| `path` | `('0x5f474906637bdcda05f29c74653f...2ee523a2206206994597c13d831ec7')` | ⚠️ Not shown |
| `to` | `0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c` | ⚠️ Not shown |

### Transaction 4: `0xa19eed9d48d25badab773658785b346d93e22dd943b6abf28a7c8bb127fec6dd`

**Block:** 23510300 | **From:** 0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `amountIn` | `5000000000000000000000` | **Amount to Send**<br/>Format: `tokenAmount` |
| `amountOutMin` | `128315810` | **Minimum amount to Receive**<br/>Format: `tokenAmount` |
| `path` | `('0x5f474906637bdcda05f29c74653f...2ee523a2206206994597c13d831ec7')` | ⚠️ Not shown |
| `to` | `0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c` | ⚠️ Not shown |

### Transaction 5: `0x5a64685153528e93c45a33a14b1ab6d70b61f9f75a47f6be2d038aaea434e165`

**Block:** 23509506 | **From:** 0x0f2a7cf7eb9ac27487c0595b50a2b69ff0345d92 | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `amountIn` | `5000000` | **Amount to Send**<br/>Format: `tokenAmount` |
| `amountOutMin` | `94137490355594896` | **Minimum amount to Receive**<br/>Format: `tokenAmount` |
| `path` | `('0xdac17f958d2ee523a22062069945...c28e8ece4512bfe46f1f33687424ce')` | ⚠️ Not shown |
| `to` | `0x0f2a7cf7eb9ac27487c0595b50a2b69ff0345d92` | ⚠️ Not shown |

</details>

---

## 🔍 Clear Signing Audit Report

### 📋 Function: `swapExactTokensForTokens(uint256,uint256,address[],address)`  
**Selector:** `0x472b43f3`

---

### 1️⃣ Intent Analysis

> **Declared Intent:** *"Swap"*

The declared intent "Swap" is accurate and concise — this function is a token-for-token swap.

---

### 2️⃣ Critical Issues

> 🔴 **CRITICAL** - Issues that could lead to users being deceived or losing funds

- **Recipient ("to") is not displayed.** The ERC‑7730 format omits the `to` parameter; the swaped output may be sent to an address different from the signer, which is a high-risk omission.  
- **Full token route (`path`) is not shown.** Only using `path` to resolve token types for amounts hides intermediary tokens (and any malicious/wrap/fee tokens) in the route that can materially change the swap outcome.  
- **Potential ambiguity in tokenPath indexing (`path.[-1]`).** If the renderer does not support negative indices, the wrong token could be used to label amounts (i.e., amountOutMin could be associated with the wrong token), causing severe user confusion and loss.  
- **No explicit display of token addresses for each step.** If token symbol/decimals metadata is missing or spoofed, users cannot verify which exact contracts are involved.

---

### 3️⃣ Missing Parameters

> ⚠️ *Parameters present in ABI but NOT shown to users in ERC-7730*

| Parameter | Why It's Important | Risk Level |
|-----------|-------------------|:----------:|
| `to` | Identifies who will receive the output tokens; if different from signer this can be used to steal funds | 🔴 High |
| `path` (full route / list) | Shows intermediary tokens and the full trade route; intermediates can introduce unexpected tokens/fees | 🔴 High |

If the implementation relies on `path.[-1]` and that syntax is not supported, this is an additional implementation risk (medium).

---

### 4️⃣ Display Issues

> 🟡 **Issues with how information is presented to users**

- Labeling is generally clear ("Amount to Send" / "Minimum amount to Receive") but the format depends on token metadata being resolved (symbol & decimals); absence of that metadata will make numbers ambiguous.  
- The spec references `path.[-1]` (negative index) — many templating systems do not support negative indices; use explicit last-element notation (`path.[length-1]`) instead.  
- Intermediary tokens in the `path` are not shown — user loses context about routing and potential MEV/fee implications.  
- No explicit display of token contract addresses beside symbols; safe UIs should show both symbol + contract link.  
- No explicit notice that `amountOutMin` is a minimum (not a guaranteed final amount) or the implied slippage / expected amount.

---

### 5️⃣ Transaction Samples - What Users See

I analyze three representative transactions (values shown both raw and with likely human units where token decimals are known).

#### 📝 Transaction 1: 0xae115d5b84ef...cbf9

| Field | ✅ User Sees | ❌ Hidden/Missing |
|-------|-------------|-------------------|
| **Amount to Send** | 10,000 [token @ 0x5f4749…] (10000000000000000000000 wei → assuming 18 decimals = 10,000 tokens) | Full token address prominently shown & verified link (only implied by tokenAmount) |
| **Minimum amount to Receive** | 256.603634 USDT (256603634 units → USDT has 6 decimals) | Recipient (`to`) — tokens could be routed to a different address |
| **Route / Intermediates** | *Not shown by format* | WETH intermediate (0xC02a… ) — user cannot see that the path is token → WETH → USDT |

#### 📝 Transaction 2: 0x9cf4f039ac23...1ee5

| Field | ✅ User Sees | ❌ Hidden/Missing |
|-------|-------------|-------------------|
| **Amount to Send** | 5,000 [token @ 0x5f4749…] (5000000000000000000000 → ≈ 5,000 if 18d) | `to` recipient |
| **Minimum amount to Receive** | 129.013461 USDT (129013461 → 129.013461 USDT) | Full token route and addresses |

#### 📝 Transaction 3: 0x5a6468515352...4165

| Field | ✅ User Sees | ❌ Hidden/Missing |
|-------|-------------|-------------------|
| **Amount to Send** | 5.000000 USDT (5000000 units → USDT 6 decimals → 5 USDT) | Full route token addresses and final-token symbol confirmation (path ends at 0x95af4a… — unknown symbol) |
| **Minimum amount to Receive** | 0.094137490355594896 [token @ 0x95af4a…]? (94137490355594896 raw; assuming 18 decimals → ~0.09414) | Confirmation of decimals/symbol for final token, and `to` |

Notes: I used known token contracts to interpret decimals: 0xdac17f… = USDT (6 decimals), 0xC02a… = WETH (18). The first path token 0x5f47… and 0x95af4a… may be unknown; when unknown, the renderer must show contract address and decimals or the human-readable conversion may be wrong.

---

### 6️⃣ Overall Assessment

| Metric | Score/Rating | Explanation |
|--------|--------------|-------------|
| **Coverage Score** | 6 / 10 | amountIn and amountOutMin are covered and mapped to tokens, but critical fields (recipient & full path) and robust indexing are missing. |
| **Security Risk** | 🟡 Medium | Missing recipient and absent route details can enable deception or confusing UX; if token indexing/metadata fails the user may sign an unintended swap. |

#### 💡 Key Recommendations
- **Add `to` as a displayed field (High priority).** Clearly show recipient address and label if recipient ≠ signer (e.g., "Recipient: 0xABC… (different from signer)").  
- **Show the full `path` (route) and token addresses.** Display each hop with symbol + contract link + decimals so users can verify intermediates and detect suspicious tokens.  
- **Avoid negative indexing; use explicit last-element resolution.** Replace `path.[-1]` with a canonical expression (e.g., `path.[path.length-1]`) and ensure the renderer supports it.  
- **Always show symbol + contract address + humanized amount.** If metadata is missing, fall back to raw units and prominently show the token contract.  
- **Add an explicit slippage/notice field.** Display that amountOutMin is the minimum accepted and show implied slippage % relative to expected output when possible.

---

If you'd like, I can produce a suggested revised ERC‑7730 JSON schema that includes `to` and an explicit `path` listing and uses safe index notation (example fields and labels).

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

### Transaction 2: `0x61641f03c85ee1b8756d273eef3900590c5e3263e51ab1ff720654619edf02c3`

**Block:** 23532794 | **From:** 0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `amountOut` | `10000000000000000000000` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMax` | `255366619` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |
| `path` | `('0xdac17f958d2ee523a22062069945...7bdcda05f29c74653f6962bb0f8eda')` | ⚠️ Not shown |
| `to` | `0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c` | ⚠️ Not shown |

### Transaction 3: `0x219941ea0a7bf7feb68807b4af83458a4e2317ef645644c5313bdc079d28d801`

**Block:** 23532788 | **From:** 0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `amountOut` | `10000000000000000000000` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMax` | `253503688` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |
| `path` | `('0xdac17f958d2ee523a22062069945...7bdcda05f29c74653f6962bb0f8eda')` | ⚠️ Not shown |
| `to` | `0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c` | ⚠️ Not shown |

### Transaction 4: `0x55b9d84e26840ed5aea8ecbd1d0f6acce5d61cf801c698b41fad221fe0ba0a48`

**Block:** 23532780 | **From:** 0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `amountOut` | `25000000000000000000000` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMax` | `625719703` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |
| `path` | `('0xdac17f958d2ee523a22062069945...7bdcda05f29c74653f6962bb0f8eda')` | ⚠️ Not shown |
| `to` | `0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c` | ⚠️ Not shown |

### Transaction 5: `0x3388168f08c8198599d44b8e2a058375684d2a181e5f13a38675c1abc9def011`

**Block:** 23532478 | **From:** 0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c | **Value:** 0

| Parameter | ABI-Decoded (Raw) | ERC-7730 (User Sees) |
|-----------|-------------------|----------------------|
| `amountOut` | `7385000000000000000000` | **Amount to Receive**<br/>Format: `tokenAmount` |
| `amountInMax` | `178582246` | **Maximum Amount to Send**<br/>Format: `tokenAmount` |
| `path` | `('0xdac17f958d2ee523a22062069945...7bdcda05f29c74653f6962bb0f8eda')` | ⚠️ Not shown |
| `to` | `0x0c05a5fd317a07e9cec05bb0beb3c31d23ab470c` | ⚠️ Not shown |

</details>

---

## 🔍 Clear Signing Audit Report

### 📋 Function: `swapTokensForExactTokens(uint256,uint256,address[],address)`  
**Selector:** `0x42712a67`

---

### 1️⃣ Intent Analysis

> **Declared Intent:** *"Swap"*  
The declared intent *Swap* is accurate and clear — this is a token swap call (buy exact output tokens by spending up to a maximum input).

---

### 2️⃣ Critical Issues

> 🔴 **CRITICAL** - Issues that could lead to users being deceived or losing funds

- **Recipient ("to") is not exposed.** The ERC‑7730 schema does not surface the `to` parameter (final recipient of the output tokens). If `to` differs from the signer, users can inadvertently route purchased tokens to a third party. This can directly cause fund loss.  
- **Full route (path) not shown.** Only using `path.[0]` and `path.[-1]` for amount formatting hides intermediate hops — a malicious or unexpected routing could change price impact or route through tokens/contracts with transfer hooks. This is a material risk for UX/security (confuses users about which tokens/contracts are involved).
- **Reliance on negative-index tokenPath (`path.[-1]`) semantics.** If tooling does not support negative indexing consistently, the last token could be resolved incorrectly (token mapping inversion), leading to mismatched token labels/amounts.

---

### 3️⃣ Missing Parameters

> ⚠️ *Parameters present in ABI but NOT shown to users in ERC-7730*

| Parameter | Why It's Important | Risk Level |
|-----------|-------------------|:----------:|
| `to` | Final recipient of the output tokens — must be shown so users can confirm tokens are sent to their own address and not an attacker-controlled address. | 🔴 High |
| `path` (full array / intermediate hops) | Shows which token contracts and intermediates are used; intermediate hops can change price, fees, or route through malicious tokens. | 🟡 Medium |
| `deadline` (not part of this signature, but commonly present in other variants) | If present in other similar functions, missing deadline would matter; for this signature it's not present, but flag for related variants. | 🟢 Low |

If the UI/tool resolves token addresses to symbols/decimals, that should be indicated; otherwise the schema alone doesn't guarantee human-readable tokens.  

---

### 4️⃣ Display Issues

> 🟡 **Issues with how information is presented to users**

- Labels are reasonably clear, but additional explicit labels would help: e.g., **"Token to Receive (path last)"** and **"Token to Send (path first)"** to remove any ambiguity.
- No explicit display of token addresses or clickable links — users may need to verify token contract addresses (especially for less-known tokens).
- The label *"Maximum Amount to Send"* is correct but could be misread as an exact amount; add a small qualifier like "*Maximum (may spend less)*".
- If token metadata (decimals/symbol) cannot be resolved, numeric values may be misleading — the schema should require fallback to raw values and show token address.
- If tooling does not support negative indexing (`path.[-1]`), the last token may be misidentified — that should be normalized to an explicit `path[last]` mapping.

---

### 5️⃣ Transaction Samples - What Users See

Selected transactions: 3 examples (formatted assuming token metadata available; path[0] resolves to USDT (6 decimals), path[-1] resolves to token at 0x5f47... with 18 decimals)

#### 📝 Transaction 1: 0x2910d05b89260e249fdd26fea53d0a53b235793ae15dd02a9f60c9d9d5b0775d

| Field | ✅ User Sees | ❌ Hidden/Missing |
|-------|-------------|-------------------|
| **Amount to Receive** | 10,000 (10000000000000000000000 with 18 decimals) of token 0x5f47... | Full token address shown? (should be) |
| **Maximum Amount to Send** | 257.143507 USDT (257143507 with 6 decimals) | Recipient (`to`) — 0x0c05... (not shown by schema) |

#### 📝 Transaction 2: 0x55b9d84e26840ed5aea8ecbd1d0f6acce5d61cf801c698b41fad221fe0ba0a48

| Field | ✅ User Sees | ❌ Hidden/Missing |
|-------|-------------|-------------------|
| **Amount to Receive** | 25,000 (25000000000000000000000 with 18 decimals) of token 0x5f47... | Full route (['USDT','WETH','0x5f47...']) — intermediate hops not displayed |
| **Maximum Amount to Send** | 625.719703 USDT | Recipient (`to`) |

#### 📝 Transaction 3: 0x3388168f08c8198599d44b8e2a058375684d2a181e5f13a38675c1abc9def011

| Field | ✅ User Sees | ❌ Hidden/Missing |
|-------|-------------|-------------------|
| **Amount to Receive** | 7,385 (7385000000000000000000 with 18 decimals) of token 0x5f47... | Path details / intermediate tokens (WETH) |
| **Maximum Amount to Send** | 178.582246 USDT | Recipient (`to`) |

Notes:
- The schema would correctly associate the input token as USDT (path[0]) and the output token as the last path element, if token metadata resolution works.
- In all samples `to` equals the sender, but the schema would not surface if it were different — a high-risk omission.

---

### 6️⃣ Overall Assessment

| Metric | Score/Rating | Explanation |
|--------|--------------|-------------|
| **Coverage Score** | 7/10 | Amounts and their token contexts (input/output) are covered, but recipient and full route are omitted; fragile reliance on negative-index tokens and external token metadata resolution lowers score. |
| **Security Risk** | 🟡 Medium | Missing recipient and hidden route can lead to confusion or misdirected funds — critical if attacker modifies `to` or route, but remedied by adding a few explicit fields in metadata/UI. |

#### 💡 Key Recommendations
- Add an explicit **Recipient** field:
  - path: `to`
  - label: "Recipient" or "Recipient (to)"
  - format: `address` (show resolved ENS/name if available)
  - Rationale: users must confirm destination of the tokens.
- Expose the full route (path) or at minimum list intermediate hops:
  - path: `path` (array)
  - label: "Route / Path"
  - format: `tokenList` (show token symbols + addresses)
  - Rationale: users can verify unexpected intermediates or malicious tokens/contracts.
- Avoid fragile negative-indexing assumptions or document them explicitly:
  - Provide both `path[0]` and `path[last]` fields explicitly in the schema, or require tooling to support `path.[-1]` consistently.
- Improve labels and contextual hints:
  - Clarify that "Maximum Amount to Send" is a limit (may be spent less).
  - Show token symbols, decimals, raw integer fallback, and token contract links.
- UI hardening:
  - If recipient != signer, visually emphasize (e.g., warning banner).
  - If token metadata cannot be resolved, show token addresses prominently and warn about unresolved metadata.

---

If implemented, the above additions will reduce phishing/misclick risk substantially by ensuring users can verify *who* receives tokens and *which* exact route/contracts are involved in the swap.

---

