# R42-VH — bounded JSON recursion fail-closed repair and executable evidence

**Date:** 2026-10-16  
**Scope:** standalone offline/synthetic R42 evidence auditor only; no release authority, no production or market connection.  
**Parent:** R42-V Draft PR #338 exact reviewed head \`7069c1663a9f81735a1071acd8c7e9878d43600f\`.  
**Stage:** bounded continuation of R42-V, **not R43**; no Merge, GitHub Actions or operational server used.

## Actual defect

The exact previously reviewed R42 script (Git blob SHA-1 \`1bf038ae05616b3871df575bf5516b798a6bcde3\`) takes an **external SHA256-pinned JSON file** as input. Its \`_read()\` previously handled \`ValueError\`, \`TypeError\`, and \`UnicodeError\` from JSON decoding but **not \`RecursionError\`**. An attacker-controlled, correctly pinned 24–32 KB JSON body with 12,000+ nested arrays can cause a raw Python \`RecursionError\`, bypassing the tool's promised structured \`R42Refused\` / command-line \`R42_EVIDENCE_REFUSED\` contract. JSON re-serialization during canonical checks can also raise \`RecursionError\` or \`OverflowError\` without conversion to the safe denial type.

This is a *robustness/availability* and fail-closed diagnostics bug. It **does not** itself enable real provider authentication, market orders, secrets access or release permission. Independently supplied hashes alone do not make attacker content trusted.

## Fix and tests

- Decode branch now catches \`RecursionError\` and raises \`R42Refused("R42_EVIDENCE_INVALID_JSON")\`.
- Canonical re-serialization is inside a separate guarded \`try\` that converts \`ValueError\`, \`TypeError\`, \`RecursionError\` and \`OverflowError\` into the same fixed safe refusal.
- Existing distinct duplicate-field and noncanonical JSON diagnostics remain unchanged. No input schema, network route or trading code changed.
- Two regression parameter cases at 12,000 and 16,000 nested arrays, using exact SHA256-pinned bounded-size original bytes, demand structured refusal from \`audit()\` **and** exit code 2 plus JSON \`R42_EVIDENCE_REFUSED\` from \`main()\`.
- A third regression forces recursion **after decoding**, during canonical encoding, to ensure that path cannot escape with an exception.

## Exact source and test provenance

Paths are those from the **new R42-VH code and tests**, not a reconstructed mock. Both were locally created from exact pinned R42-C GitHub bytes, amended and unit-tested; GitHub update responses reported these exact blob identities (verified against local Git blob calculations):

| Path | Git blob SHA-1 | SHA256 |
| --- | --- | --- |
| \`scripts/mmt_r42_offline_market_account_evidence_v1.py\` | \`070c56bd8774372c40bb61f8316c92988e8c9b35\` | \`d4d1aebca64bf81977f5ee5f60cfc1d3833fa2008551378ec8e86916ffdd953d\` |
| \`tests/unit/test_mmt_r42_offline_market_account_evidence_v1.py\` | \`eab305facdc6ce9406f3a488a602f2b5b62a1b19\` | \`89eda2c803415e129deaf705cbf5ca60c2053b287b801c0735783568165d420f\` |

## Executed tests

Test environment: isolated Debian 13 ephemeral assistant container, CPython 3.13.5, pytest 9.0.2, no real market providers/accounts, no user credentials, no Telmivo operations.

1. **Unmodified exact prior R42-C code + three new regression tests:** \`48 passed, 3 failed\` as expected, exit code 1. The failures were **three escaped RecursionErrors**, independently proving the old bug (not unrelated test failures).
2. **Corrected new R42-VH code + same exact tests**, under \`MMT_NONPRODUCTION=1\`, \`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1\`, \`-X dev -W error\`, \`--noconftest\`: **51 passed in 0.15s**, no failures.
3. **Nonroot UID 1000** on the unchanged patched files, same strict options: **51 passed in 0.14s**, no failures.
4. Branch-aware targeted coverage: **51 passed in 0.20s** and **89% measured statement/branch combined coverage** for this R42 module (202 statements, 19 missing, 92 branches, 13 partial). This is not whole-project coverage.
5. Both corrected files passed Python 3.12 **grammar-only** AST parsing on installed CPython 3.13.5. This is NOT proof of actual Python3.12 runtime compatibility.

## Boundaries and unresolved acceptance

| Gate | Result |
| --- | --- |
| JSON recursion denial regression | **PASS 51/51, negative control proves bug** |
| GitHub blob identity for patch and tests | **PASS** |
| Nonroot Python 3.13.5 isolated tests | **PASS 51/51** |
| Real Python 3.12 interpreter / pytest | **PENDING** — only Python 3.13.5 available in assistant sandbox |
| Ruff executable and full-repository regression | **PENDING** — unavailable in approved offline sandbox |
| Independent installed Wheel nonroot end-to-end | **PENDING** |
| R41 hostile rootless/gVisor host assessment | **PENDING** |
| Real authenticated market and account provenance | **NOT VERIFIED** |
| Stage15 nine P0 plus one P1 | **OPEN** |
| Public Telegram / real PAPER / LIVE / Production / main Merge | **HARD DENY / NOT PERFORMED** |

**Verdict:** \`R42VH_PATHOLOGICAL_JSON_FIXED_PY313_TESTED_R42V_PY312_ACCEPTANCE_OPEN\`. Keep branch and PR Draft. Do not move to R43 operational acceptance until independent real Python3.12 and broader installed tests are available.
