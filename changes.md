# ERC-7730 v2 Migration — Changes Log

## 1. Schema Changes (`specs/erc7730-v2.schema.json`)

### 1.1 `propertyNames` regex: tuple nesting depth (1 → 5 levels)

**File:** `testing/specs/erc7730-v2.schema.json` (line 353)

**Problem:** The `propertyNames` regex in `display.formats` only supported 1 level of tuple nesting inside function signatures. Real-world Solidity functions like Paraswap's `multiSwap` (4 levels) and `megaSwap` (5 levels) failed validation.

**Example that failed:**

```
multiSwap(tuple(... tuple(... tuple(... tuple(...)[] route)[] adapters)[] path ...) data)
```

**Before (1 level):**

```
tuple(?:\s*\((?:[^()]|\([^()]*\))*\))?
```

**After (5 levels):**

```
tuple(?:\s*\((?:[^()]|\((?:[^()]|\((?:[^()]|\((?:[^()]|\((?:[^()]|\([^()]*\))*\))*\))*\))*\))*\))?
```

**Limitation:** Regular expressions fundamentally cannot match arbitrarily nested parentheses. 5 levels covers all known real-world Solidity contracts, but a simpler permissive regex (e.g. `^[A-Za-z_][A-Za-z0-9_]*\(.*\)$`) could be considered as an alternative to avoid this ceiling entirely.

**Note:** The original `specs/erc7730-v2.schema.json` is untouched. This change is only applied in `testing/specs/erc7730-v2.schema.json`.

---

## 2. Migration Script Changes (`migrate-v1-to-v2.js`)

### 2.1 Added `js-sha3` dependency for Keccak-256 hashing

**Line:** 40

```javascript
const { keccak256 } = require("js-sha3");
```

**Why:** Node.js `crypto` module provides SHA-3 (FIPS 202), not Keccak-256 (pre-standardization). Ethereum uses Keccak-256 for function selectors. Without this, computed selectors didn't match the hex keys in v1 descriptors.

---

### 2.2 `canonicalParamType()` — recursive tuple expansion for canonical signatures

**Why:** `abiCanonicalSignature()` was using `extractParamType(input.type)` which returned the literal string `"tuple"` for tuple parameters instead of expanding to `(type1,type2,...)`. This caused Keccak-256 hashes to not match hex selectors.

**Before:**

```javascript
function abiCanonicalSignature(abiEntry) {
  const types = inputs.map((input) => extractParamType(input?.type || ""));
  return `${name}(${types.join(",")})`;
}
```

Produced: `func(tuple)` → wrong keccak hash

**After:**

```javascript
function canonicalParamType(param) {
  const type = param.type || "";
  if (type === "tuple" || type === "tuple[]") {
    const inner = (param.components || []).map(canonicalParamType).join(",");
    return type === "tuple[]" ? `(${inner})[]` : `(${inner})`;
  }
  return type;
}

function abiCanonicalSignature(abiEntry) {
  const types = inputs.map(canonicalParamType);
  return `${name}(${types.join(",")})`;
}
```

Produces: `func((address,uint256,...))` → correct keccak hash

---

### 2.3 `computeSelector()` + hex selector matching in `findAbiEntry()`

**Why:** v1 descriptors use hex selectors (e.g. `0x2298207a`) as format keys. The script had no way to match these against ABI entries. Files with inline ABIs and hex keys (Celo, Paraswap, LiFi) were left untransformed.

```javascript
function computeSelector(abiEntry) {
  const canonical = abiCanonicalSignature(abiEntry);
  if (!canonical) return null;
  return "0x" + keccak256(canonical).slice(0, 8);
}

function findAbiEntry(abi, formatKey) {
  // ... existing canonical + name matching ...

  // NEW: match by 4-byte hex selector
  if (/^0x[0-9a-fA-F]{8}$/.test(formatKey)) {
    const lowerKey = formatKey.toLowerCase();
    const match = abi.find(
      (entry) => entry.type === "function" && computeSelector(entry) === lowerKey
    );
    if (match) return match;
  }

  // ... fallback name matching ...
}
```

---

### 2.4 `formatParam()` — bare `(...)` for linter compatibility (reverted from `tuple(...)`)

**History:** Initially changed to `tuple(...)` to match the v2 schema `propertyNames` regex. **Reverted back to bare `(...)`** after discovering that the official `python-erc7730` linter (`erc7730 lint`) rejects `tuple(...)` as invalid.

**Root cause:** The linter's Lark grammar in `src/erc7730/common/abi.py` defines tuples as bare parentheses:

```
?tuple: "(" params ")"
named_tuple: tuple array* identifier?
```

This grammar has no `tuple` keyword — it expects `(type1 name1, type2 name2) paramName` directly. The `tuple` keyword is parsed as a type identifier, then the following `(...)` becomes unexpected input.

**Current (linter-compatible):**

```javascript
type = type === "tuple[]" ? `(${inner})[]` : `(${inner})`;
```

**Schema fix:** The `testing/specs/erc7730-v2.schema.json` `propertyNames` regex was updated to make `tuple` optional: `(?:tuple)?\\s*\\(NESTED\\)`, so both `tuple(...)` and bare `(...)` pass schema validation. The original `specs/erc7730-v2.schema.json` is untouched.

---

### 2.5 `fixInlineTupleSyntax()` / `fixParamTupleSyntax()` — post-processing for existing format keys

**Why:** Some v1 files may have `tuple(...)` syntax from previous migrations or manual edits. This post-processing step now **strips** the `tuple` keyword to produce the linter-compatible bare `(...)` format.

```javascript
function fixInlineTupleSyntax(key) {
  // Parses top-level params, strips "tuple" prefix from tuple params
  // Handles nested tuples recursively via fixParamTupleSyntax()
}

function fixParamTupleSyntax(param) {
  // If param starts with "tuple(", strips the "tuple" keyword
  // Recurses on inner params to strip nested "tuple" prefixes
  // Returns "(fixed_inner)suffix"
}
```

Applied as **step 5b** in `migrateFile()`, after key mapping (step 5) and before ABI removal (step 6).

---

### 2.6 `extractAbiLeafPaths()` / `extractEip712LeafPaths()` — complete field path extraction

**Why:** In v2, "Listing all paths of the function in the `fields` becomes mandatory" (`specs/changes.md`). v1 descriptors often only listed a subset of paths in `fields` — paths not in `required` or `excluded` were simply absent. The migration must add these missing paths.

```javascript
function extractAbiLeafPaths(abiEntry) {
  // Recursively walks ABI inputs, produces paths like:
  // "#.param", "#.param.component", "#.arr.[]", "#.tuple.field"
}

function extractEip712LeafPaths(schemas, primaryType) {
  // Recursively walks EIP-712 schema types, produces paths like:
  // "#.field", "#.nested.subfield", "#.array.[].field"
}
```

`transformFormatKeys()` now returns `{ keyMapping, leafPathsPerFormat }`, collecting all paths before ABI/schemas are deleted.

---

### 2.7 Step 9 update — add missing paths + ensure `visible` on all fields

**Why:** Three gaps in v1 → v2 field migration:

1. Fields in `required` got `visible: "always"` ✓
2. Fields in `excluded` got `visible: "never"` ✓
3. Fields in neither `required` nor `excluded` got **no `visible`** ✗
4. ABI/schema paths not in `fields` at all were **missing entirely** ✗

**Changes to step 9:**

```javascript
// After handling required → visible:"always" and excluded → visible:"never":

// A. Add missing ABI/schema paths that weren't in fields, required, or excluded
const allLeafPaths = leafPathsPerFormat[formatKey] || [];
if (allLeafPaths.length > 0) {
  const existingPaths = new Set(
    format.fields.filter((f) => typeof f === "object" && f.path).map((f) => f.path)
  );
  for (const leafPath of allLeafPaths) {
    if (!existingPaths.has(leafPath)) {
      format.fields.push({ path: leafPath, label: autoLabel, visible: "never" });
    }
  }
}

// B. Default any remaining field without visible to "always"
for (const field of format.fields) {
  if (typeof field === "object" && !field.visible && !field.fields) {
    field.visible = "always";
  }
}
```

**Note on default visibility for auto-added paths:** Fields not present in the v1 descriptor at all default to `visible: "never"`, not `"always"`. If a field wasn't displayed in v1, it was likely intentionally omitted (e.g. `path.[]` in UniswapV3Router02 is only referenced indirectly via `params.tokenPath` for first/last elements, never displayed as a full array).

### 2.8 Path normalization for duplicate detection

**Why:** v1 field paths use bare names (`amountIn`) while `extractAbiLeafPaths()` produces `#.`-prefixed paths (`#.amountIn`). Without normalization, the comparison missed existing fields and added duplicates.

```javascript
const normalizePath = (p) => p.replace(/^#\./, "");
const existingPaths = new Set(
  format.fields.filter((f) => typeof f === "object" && f.path).map((f) => normalizePath(f.path))
);
for (const leafPath of allLeafPaths) {
  if (!existingPaths.has(normalizePath(leafPath))) { ... }
}
```

---

## 3. Weird Cases & Edge Cases Discovered During Migration

### 3.1 Multi-facet proxy contracts (Paraswap AugustusSwapper)

**Contract:** `0xDEF171Fe48CF0115B1d80b88dc8eAB59176FEe57`

The proxy delegates calls to multiple implementation contracts via `getImplementation(bytes4)`. The proxy's own ABI only contains admin functions (`setImplementation`, `grantRole`, etc.) — none of the actual swap functions.

- `simpleBuy`, `simpleSwap` → `0x66C1c25d...` (SimpleSwap facet)
- `multiSwap`, `megaSwap` → `0xbD7b550d...` (MultiPath facet)
- `swapOnUniswap`, `buyOnUniswap` → `0x5172f030...` (UniswapProxy facet)
- `swapOnUniswapV2Fork` → `0x4FF0dEC5...` (UniswapV2 facet)
- `swapOnZeroXv2` → `0xC71781B5...` (ZeroX facet)
- `swapOnZeroXv4`, `swapOnZeroXv4WithPermit` → **NOT REGISTERED** (deprecated/removed from router)

**Impact:** The v1 descriptor's inline ABI is a **curated combined ABI** of all facets — it cannot be fetched from Etherscan for the proxy address alone. Verification required querying `getImplementation()` per selector and fetching each facet's ABI individually.

**Result:** 14/16 functions matched on-chain exactly. 2 functions (`swapOnZeroXv4`, `swapOnZeroXv4WithPermit`) are no longer registered — stale entries in the v1 descriptor.

---

### 3.2 `tuple(...)` vs `(...)` — schema vs linter vs ethers.js

Three components disagree on tuple syntax in function signatures:

| Component | Expected format | Example |
|-----------|----------------|---------|
| v2 JSON schema `propertyNames` regex | `tuple(...)` required | `exactInput(tuple(bytes path, ...) params)` |
| `python-erc7730` linter (`erc7730 lint`) | bare `(...)` required | `exactInput((bytes path, ...) params)` |
| `ethers.js` / Solidity source | bare `(...)` | `exactInput((bytes path, ...) params)` |

The schema regex explicitly matches `tuple(?:\s*\(...)` — requiring the `tuple` keyword. The linter's Lark grammar defines `?tuple: "(" params ")"` — a tuple is bare parentheses with no keyword.

**Resolution:** The migration script now produces bare `(...)` (linter-compatible). The testing schema regex was updated to make `tuple` optional: `(?:tuple)?\s*\(...)` — accepting both forms. The canonical `specs/erc7730-v2.schema.json` is untouched.

**Recommendation:** The spec schema regex should be updated to accept bare `(...)` as the standard form, matching both the linter and `ethers.js`. Using `(?:tuple)?` makes the `tuple` keyword optional and backward-compatible.

---

### 3.3 `memory`/`calldata`/`storage` in schema regex

The `propertyNames` regex includes `(?:\s+(?:memory|calldata|storage))?` — these are Solidity data location keywords, not ABI concepts. The ABI JSON has no data location info, so migration-generated signatures never include them. The regex allows them for manually written signatures from Solidity source.

---

### 3.4 Deeply nested tuple structs (Paraswap `megaSwap`)

`megaSwap` has **5 levels** of nested tuple structs:

```
megaSwap(
  tuple(                              -- level 1: MegaSwapSellData
    ...,
    tuple(                            -- level 2: MegaSwapPath
      ...,
      tuple(                          -- level 3: Path
        ...,
        tuple(                        -- level 4: Adapter
          ...,
          tuple(...)[] route          -- level 5: Route
        )[] adapters
      )[] path
    )[] path,
    ...
  ) data
)
```

The original schema regex only handled 1 level. Even with 5 levels, this is a hard ceiling — regex fundamentally cannot match arbitrary nesting. A permissive regex like `^[A-Za-z_][A-Za-z0-9_]*\(.*\)$` would avoid this limitation entirely but loses structural validation.

---

### 3.5 Array fields used only as indirect references (UniswapV3Router02 `path`)

In `swapExactTokensForTokens` and `swapTokensForExactTokens`, the `address[] path` parameter is **never displayed directly**. Only specific elements are referenced:

```json
{
  "path": "amountIn",
  "format": "tokenAmount",
  "params": { "tokenPath": "path.[0]" }
},
{
  "path": "amountOutMin",
  "format": "tokenAmount",
  "params": { "tokenPath": "path.[-1]" }
}
```

`path.[0]` (first token) and `path.[-1]` (last token) are used as formatting context for amounts, but `path` itself was never a displayed field. The migration's `extractAbiLeafPaths()` sees `path` as a leaf and adds `#.path.[]` — this must default to `visible: "never"`.

**This is the spec's intended behavior.** The v2 spec (`changes.md` line 251) states: *"Listing all paths of the function in the `fields` becomes mandatory"*. The example in the spec demonstrates this with:
- `"rfu"` → `visible: "never"` ("unused field that should never be displayed")
- `"legacy"` → `visible: {"mustBe": [0]}` ("unused field that must be zero or Tx is malformed")
- `"fee"` → `visible: {"ifNotIn": [0]}` ("display only if non-zero")

**Migration rule:** Any ABI/schema path absent from the v1 descriptor was intentionally not displayed. Auto-added paths default to `visible: "never"`, matching the spec's `rfu`/`legacy` pattern. A human reviewer should then decide per field whether to use `"never"`, `"optional"`, `{"mustBe": [...]}`, or `{"ifNotIn": [...]}` based on the field's semantic role.

**Sub-case: partial array / byte-slice references.** Two patterns found in UniswapV3Router02:

1. **Indexed array access** (`swapExactTokensForTokens`): `address[] path` is never displayed directly. Only `path.[0]` (first token) and `path.[-1]` (last token) are referenced via `params.tokenPath` to format `amountIn`/`amountOutMin` as token amounts. The array itself has no display entry.

2. **Byte slicing** (`exactInput`/`exactOutput`): `bytes path` is packed Uniswap V3 routing data. `params.path.[0:20]` and `params.path.[-20:]` extract the first/last 20-byte token address from packed bytes. This isn't even a standard array — it's raw byte-level extraction.

In both cases, the field is not "displayed" but is **consumed as formatting context** by other fields. The v2 spec requires listing it in `fields` anyway (all paths mandatory), so it gets `visible: "never"`. However, the spec has no concept of "field exists only as a reference source" — it's either displayed or not. This is a potential spec gap: a wallet needs to know that `path` must still be available for `tokenPath` resolution even though it's not shown to the user.

---

### 3.6 URL-based ABIs in v1 descriptors

Some v1 files reference ABIs via URL rather than inline arrays:

```json
"abi": "https://github.com/LedgerHQ/ledger-asset-dapps/blob/.../0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45.abi.json"
```

The migration script resolves these via `curl` at migration time (normalizing GitHub blob URLs to raw, Etherscan v1 to v2, etc.). If the URL is unreachable, the ABI is unavailable and:
- Hex selectors remain unconverted
- No leaf path extraction occurs
- No human-readable signature is generated

**Files affected:** Any v1 descriptor using `context.contract.abi` as a URL string.

---

### 3.7 Common/include files without ABI context

Files like `common-AggregationRouterV6.json` are shared include files — they define display formats but have no `context.contract.abi` of their own. The ABI is provided by the including file.

**Impact on migration:**
- `transformFormatKeys()` cannot rebuild signatures from ABI → keys stay as-is from v1
- `extractAbiLeafPaths()` returns nothing → no missing paths are detected
- Pre-existing bare `(...)` tuple syntax must be fixed via text-level `fixInlineTupleSyntax()` since ABI-based `buildHumanReadableSignature()` is unavailable

---

### 3.8 `#.` prefix inconsistency in field paths

v1 descriptors use bare paths (`amountIn`, `to`) while the ABI-based path extractor produces `#.`-prefixed paths (`#.amountIn`, `#.to`). Both refer to the same field — `#` is the root of the calldata/message.

Without normalization, the script failed to detect that `amountIn` and `#.amountIn` are the same field, creating duplicates.

---

### 3.9 Deprecated/stale selectors in v1 descriptors

Some v1 descriptors reference function selectors that are no longer registered in the proxy:
- Paraswap `swapOnZeroXv4` (`0x64466805`) — `getImplementation()` reverts
- Paraswap `swapOnZeroXv4WithPermit` (`0x6b4109d3`) — `getImplementation()` reverts

These functions were likely removed from the router in a contract upgrade. The migration script processes them normally (the inline ABI still has the entries), but they represent dead code in the descriptor.

---

### 3.10 `payable` and `returns(...)` in function signatures

`ethers.js` full format includes state mutability (`payable`, `view`, `pure`) and return types (`returns (uint256)`):

```
simpleSwap((...) data) payable returns (uint256 receivedAmount)
```

The migration script and v2 schema only include the function name and input parameters — no mutability or return types. This is consistent with how selectors are computed (only name + input types).

---

## Summary of Impact

| Change | Scope | Why |
|--------|-------|-----|
| Tuple nesting regex (1→5) | Schema | Real Solidity functions have deep struct nesting |
| `js-sha3` for Keccak-256 | Script | Ethereum uses Keccak-256, not NIST SHA-3 |
| `canonicalParamType()` | Script | Tuple expansion needed for correct selector hashing |
| `computeSelector()` + hex matching | Script | v1 files use hex selectors as format keys |
| `formatParam()` bare `(...)` | Script | Linter expects bare `(...)`, not `tuple(...)` |
| `fixInlineTupleSyntax()` | Script | Strip `tuple` keyword from pre-existing `tuple(...)` keys |
| `extractAbiLeafPaths()` / `extractEip712LeafPaths()` | Script | v2 requires all paths listed in fields |
| Step 9: missing paths (visible "never") | Script | Auto-added paths default to hidden |
| Path normalization (`#.` prefix) | Script | Prevent duplicates from bare vs prefixed paths |

## Recommendations

1. **Use `ethers.js` or `viem`** for ABI handling in the migration script instead of hand-rolled functions. This would replace `canonicalParamType`, `computeSelector`, `buildHumanReadableSignature`, `fixInlineTupleSyntax`, and `formatParam` with battle-tested library code.

2. **Simplify the `propertyNames` regex** to validate general shape only (e.g. `^[A-Za-z_][A-Za-z0-9_]*\(.*\)$`), and move deep structural validation to the analyzer tool. This eliminates the nesting depth ceiling.

3. **Align `tuple` keyword convention** — the spec schema, the `python-erc7730` linter, and `ethers.js` must agree. Currently the schema requires `tuple(...)` but the linter rejects it. The linter and ethers.js both expect bare `(...)`. The schema should be updated to accept bare `(...)` (see section 3.2).

4. **Flag stale selectors** — descriptors referencing deprecated/unregistered selectors should be detected and warned about during migration or analysis.
