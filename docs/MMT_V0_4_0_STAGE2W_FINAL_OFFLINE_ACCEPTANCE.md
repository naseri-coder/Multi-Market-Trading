# MMT v0.4.0 — Stage 2W final offline acceptance

**Recorded:** 2026-10-17. **Code commit:** `f8d3883c86b17b707d97fdd07253c645f4eb9886`. **Pull request:** #352 (Draft, open, unmerged).

**Decision:** `STAGE2W_OFFLINE_SOURCE_AND_RUFF_PASS__RELEASE_NOT_AUTHORIZED`.

## 1. Exact checkout and unchanged source custody

- A fresh, clean Git checkout pinned to the code commit above was tested in a disposable, nonroot (UID 1000) CPython 3.12.15 Linux container, with network disabled, read-only root filesystem and resource caps.
- The public 226-module source Git tree remains `511e9346d88280f3be7c80367f8822a8eaa24dd7`. Git Blob hashes and UTF-8 sizes: **226/226 PASS**, **2,501,079 bytes**.
- Manifest SHA-256: `c2554a8a1c3a46d1675e8e44429c017f6981758df012d5b5feecab353bcf9b9c`.
- R22 historical Stage18 original-source integrity remains checked by the reviewed reversible reconstruction, rather than silently overwriting its historical pin.
- R42V original Git Blob and SHA-256 pins remain immutable. The reviewed Ruff-only variant requires **exact known current hashes** and a byte-exact reversal to the unchanged historical pinned file; tampering fails closed.
- Stage2W post-R42V lint regression contained 17 `I001` import block findings, not new functional code. The final import-only commit removed these in 17 research/scripts files without touching any of the 226 public product modules.

## 2. Real Python 3.12 and lint acceptance

| Check | Outcome |
| --- | --- |
| Complete project pytest suite, exact code commit | **7,584 PASS, 0 FAIL, 76 SKIP**, 6 warnings, 2 subtests PASS; 273.57 seconds |
| Ruff 0.16.9 baseline-relative gate vs protected main `51e0e4de...` | **PASS** — baseline 1,345 findings; candidate 1,344; **0 new** |
| R42V bounded genuine CPython 3.12 runtime gate | **PASS** — 59 pinned R42 tests, nonrelease verdict |
| 226-module production guard AST and SHA-bound source checks | **PASS** in full suite; original 190 targeted checks also passed on the prior code commit |
| Clean checkout and nonproduction isolation | **PASS**; no broker, Telegram, production DB or LIVE order |

## 3. Genuine offline Wheel custody

- Official 226-source staging on the **exact candidate commit**: `V040_ISOLATED_226_SOURCE_STAGING_PASS_PUBLIC_RELEASE_DENIED`.
- Two independent clean staging directories and builds with pinned `SOURCE_DATE_EPOCH`: **byte-identical** Wheel files.
- Wheel: `multi_market_trading-0.4.0-py3-none-any.whl`, size **806,419 bytes**, SHA-256 `33316353c0dcf0c5c3cd5b8926d87b70cfdd589e1ea3d5061f8ee90e127825fc`.
- Zip membership, exact embedded Git Blob digests/byte lengths for all **226 modules**, and SHA-256/length in **231 RECORD rows**: **PASS**.
- Offline `pip install --no-index --no-deps` and all **9 installed console entry points** called with `--help`: **PASS**.
- No trusted software publisher signature was produced or verified. Wheel is **not an authorized publication or release**.

## 4. What the 76 skips actually mean

| Missing independent environment or approval | Skipped tests |
| --- | ---: |
| Real isolated PostgreSQL integration database | **38** |
| Genuine ephemeral GitHub-hosted runner | **32** |
| Explicitly opted-in CERT-A5 benign replay | **4** |
| Opted-in public market data smoke | **2** |
| **Total** | **76** |

**No skipped test is represented as a pass.** PostgreSQL migrations, real persistence/recovery and rollback, isolated restart/soak evidence, signer identity and host provenance require independent, approved coverage before official publication. An earlier attempt to stage PostgreSQL on the production-associated host was restricted; no production database was used.

## 5. Next controlled stage / release decision

**Stage 2W source/lint/offline Wheel work: CLOSED — PASS for its specified scope.**

**Stage 2X (required before release):** close skipped PostgreSQL and runner capability gaps on an independent ephemeral host, complete real install/restart/rollback and provenance/signed-release acceptance. Do not treat a disabled GitHub Actions quota as approval to skip required release tests. Preserve all original historical pins and signed custody evidence.

**Official release remains BLOCKED.** Keep PR #352 Draft/unmerged. Do not modify protected `main`, create tag `v0.4.0`, deploy to Telmivo, access production data, deliver real Telegram messages or permit LIVE trading.

Machine-readable companion evidence: `docs/evidence/MMT_V0_4_0_STAGE2W_FINAL_CANDIDATE_EVIDENCE.json`.
