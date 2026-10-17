# MMT v0.4.0 — canonical merge and publication runbook

**Date:** 2026-10-17. **Status:** `DRAFT__NOT_RELEASE_READY`.

## 1. Immutable version decision

- The repository's current **published** release and immutable Git tag is `v0.3.2` (`672674fa5b8c52986b56f1929132d2558ec27a38`). Do not rewrite, move, delete or reissue it.
- The next **target stable** repository release is **`v0.4.0`** (NOT `v4.0.0`).
- The canonical Git prerelease format, if a GitHub prerelease is eventually authorized, is `v0.4.0-rc.1` (SemVer); the matching Python distribution metadata is `0.4.0rc1` (PEP 440). Subsequent candidates: `v0.4.0-rc.2` / `0.4.0rc2`, as required.
- The separate package `platform_release/pyproject.toml` currently declares `multi-market-trading==0.4.0rc1`. This is preview source metadata, **not an existing GitHub release or proof of acceptance**.
- The repository root `pyproject.toml` declares frozen `crypto-price-action==0.3.2`; its `production_source/SHA256SUMS` historical trust manifest must stay immutable. The v0.4.0 release is **the new `multi-market-trading` platform package**, not a retroactive rewrite of the legacy 0.3.2 package. Installation commands and release notes must explicitly identify the package/build location.
- Candidate source lineage: `release/0.4.0-candidate` forked from approved-integration *source* `58bd3203a366b9c101340f2223aa6cda4dda5a4c`. The earlier misleading `integration/v4.0.0-candidate-20261017` remains historical audit provenance only; its name does NOT define the release target.
- `main` baseline at creation: `51e0e4de04e184fe28b59b9db4b6a70fbd67dfe0`. Recheck main and compare immediately before every merge or tag.
- Neither `v0.4.0-rc.1` nor `v0.4.0` may be created until the corresponding release gates pass.

## 2. Branch selection / conflict policy

- The R17–R42V canonical lineage and FIX01–FIX05 plus PAPER07–09 mainline history are joined through PR #350, commit `31bc1ee57183ce91d601042b46ed4720132fb16e`. The full 57-branch inventory and exact divergence decisions are in `docs/MMT_V4_BRANCH_CONSOLIDATION_20261017.md`. Its *old document name* is a historical artifact, not a v4 release decision.
- 36 already-ancestral heads require **no** cherry-picks. The current `main` was imported into the candidate, not silently rewritten.
- 19 other divergent heads are not globally authorized for a bulk merge:
  - CERT-A19 research: preserve for independent security provenance and gVisor/rootless host qualification; do not report CVE fixed without evidence.
  - Alternative Stage17/18 original-market-data and Stage21F forward-source paths: independently evaluate provenance, timestamps and channel boundaries; use a single authoritative source intake.
  - R26 economic-parity and alternative R42, R38 auditors: compare contracts and tests first; pick one canonical runtime and use alternative code only as evidence or independently reviewed discrete backports.
  - Signed public-core intake / old develop: isolation, version alignment and private-core protection must pass.
  - Seven Dependabot heads: triage independently against lockfiles, full test matrix and security impact before selective acceptance.
- If a proposed change modifies a frozen source, changes a trust or LIVE gate, or lacks isolated reproducible tests, **reject or defer**, rather than force-merge.
- Keep unrelated experiments as separate PRs/issues. Closing or archiving a PR is not equal to incorporating its functionality. Never delete research/source branches as a shortcut.

## 3. Ordered merge-to-release stages with exit criteria

### 0 — Inventory and baseline pin (complete)

- All 57 heads inventoried; source-only consolidation PR #350 merged **into the integration branch**; `main` is untouched.
- `release/0.4.0-candidate` starts from exact integrated head.
- A Draft PR from this candidate to `main` is a review vehicle only.
- **Exit:** Git refs, previous stable tag, candidate blob pins and branch list documented; no tag.

### 1 — Target and compatibility freeze (source-scope review completed; runtime validation pending)

- Fix public platform scope: offline/PAPER product only; document supported APIs/CLIs and behaviors.
- Identify all user-facing contracts: `naseri-markets`, `naseri-custom`, `naseri-paper-demo`, `naseri-paper-pilot`, Brooks replay/admin entrypoints, provider abstraction, source/release verification and required Python 3.12.
- Diff startup, worker and database/ledger schema contracts between `v0.3.2`, current `main`, and merged candidate. Establish explicit migration-versus-side-by-side operation and rollback. Never migrate production DB in this release preparation.
- Define which 19 independent heads contain mandatory release fixes; handle each adopted change by separate scoped review with complete tests.
- **Exit:** API/breakage matrix, accepted/deferred branches, private-core exclusion proof, initial version ownership, release-feature freeze.

**Stage 1 evidence (2026-10-17):** See [`MMT_V0_4_0_STAGE1_COMPATIBILITY_AND_BRANCH_DISPOSITION.md`](MMT_V0_4_0_STAGE1_COMPATIBILITY_AND_BRANCH_DISPOSITION.md). This is a reviewed *source-scope freeze*: all 19 independent branch heads are classified; none was blindly merged. Critical findings are the 78 preview-version references across default-branch search results, 348-entry published-v0.3.2 versus 359-entry current legacy manifest, and the lack of operational rootless host accreditation. All runtime acceptance remains open; no release tag is authorized.

### 2 — Correctness, safety and test closure (partially implemented; acceptance still blocking)

**Current Stage 2 evidence (2026-10-17):** See [`MMT_V0_4_0_STAGE2_VERSION_IDENTITY_TEST_EVIDENCE.md`](MMT_V0_4_0_STAGE2_VERSION_IDENTITY_TEST_EVIDENCE.md). A strict exact-version helper now supports the `0.4.0rc1` → `0.4.0` offline runtime transition in three caller modules. The exact helper was verified against its Git blob, with 20 local Python 3.13.5 focused/AST checks passed; the **28 committed full-repo integration cases and real Python 3.12/Ruff suites were NOT run**. The installers and signed provenance still intentionally pin `0.4.0rc1`. **Neither stable-tag nor main-merge readiness is granted.**



**Packaging Stage 2b update (2026-10-17):** [`MMT_V0_4_0_STAGE2B_PACKAGING_AND_R38_REPAIR.md`](MMT_V0_4_0_STAGE2B_PACKAGING_AND_R38_REPAIR.md) records the real R38 syntax repair, metadata-bound A6/staging/development installer patch and 11 additional committed negative/compatibility cases. Direct GitHub source consistency checks 14/14 passed, **not full executed tests**. R35–R38 remain intentionally RC-only signed-artifact controls. Stable signed-wheel verification, Python3.12/Ruff, new test execution and final merge remain blocked.

**Stage 2C fail-closed security update (2026-10-17):** [`MMT_V0_4_0_STAGE2C_SIGNED_RELEASE_FAILCLOSED_HARDENING.md`](MMT_V0_4_0_STAGE2C_SIGNED_RELEASE_FAILCLOSED_HARDENING.md) documents the R35/R36/development-installer correction for any explicitly defined `MMT_PRODUCTION`, R37/R38 bounded JSON parser/encoder recursion refusal and **18 new committed but not yet executed pytest cases**. A standalone five-decision Bash guard check passed; Python3.13's deep JSON parser behavior was assessed. No full Python3.12/Ruff, real signed-wheel installation, R42V, PostgreSQL or final release acceptance was run. This is **not an authorization to merge or tag**.

**Stage 2D signed stable preflight (2026-10-17):** [`MMT_V0_4_0_STAGE2D_STABLE_ARTIFACT_SIGNATURE_PREFLIGHT.md`](MMT_V0_4_0_STAGE2D_STABLE_ARTIFACT_SIGNATURE_PREFLIGHT.md) records the newly committed, separately domain-separated and fail-closed `v0.4.0` *read-only stable Wheel signature/RECORD checker*. Its exact GitHub source and 32-case synthetic unit suite were byte-matched to an actual `32 passed` Python3.13.5 test run. This is **not** Python3.12, full-project installed-wheel, independent source-custody or authorized signer acceptance. RC metadata, protected `main` and stable-tag blockers remain unchanged.

**Stage 2E real-wheel metadata defect (2026-10-17):** [`MMT_V0_4_0_STAGE2E_REAL_WHEEL_METADATA_INTEROPERABILITY.md`](MMT_V0_4_0_STAGE2E_REAL_WHEEL_METADATA_INTEROPERABILITY.md) records the `setuptools`-generated Python-range order mismatch, a tested exact-equivalence fix and **38/38 real CPython3.13.5 unit tests** on exact GitHub-blob-matched files. A *partial synthetic module wheel* made by real `pip wheel` passed standalone ZIP/RECORD validation and test-only Ed25519 verification; forged signature was rejected. The genuine project Wheel, Python3.12 installation, full-suite checks, source provenance and signer key approval are **still outstanding**. Do not merge or tag.

**Stage 2F signed Git-source↔Wheel custody (2026-10-17):** [`MMT_V0_4_0_STAGE2F_SIGNED_SOURCE_WHEEL_CUSTODY.md`](MMT_V0_4_0_STAGE2F_SIGNED_SOURCE_WHEEL_CUSTODY.md) records a new read-only clean-Git-commit + exact-public-module-byte-to-signed-wheel verifier. Executed **47/47** tests on the exact GitHub-byte-matched Stage2D/E signed-artifact verifier (38) and new source-custody suite (9) using CPython3.13.5, plus genuine setuptools 3-module partial-fixture Wheel/signed-test-key evidence and a dirty-checkout refusal. **This does NOT attest the actual 226-module project Wheel, and Python3.12/Ruff remain unavailable**. The candidate's production-released root stays 0.3.2, platform package stays 0.4.0rc1, and final merge/tag blockers remain.

**Stage 2G complete source inventory audit (2026-10-17):** [`MMT_V0_4_0_STAGE2G_PUBLIC_SOURCE_LOCK_AND_WHEEL_REHEARSAL.md`](MMT_V0_4_0_STAGE2G_PUBLIC_SOURCE_LOCK_AND_WHEEL_REHEARSAL.md) records **226 real GitHub module paths/blobs/sizes (226/226 matching the actual Git tree, 2,501,524 bytes)** plus a separately SHA256-pinned `docs/MMT_V0_4_0_PUBLIC_MODULE_SNAPSHOT.json`, a read-only Git source lock auditor and 11 additional executed local Git regression cases. **58/58 combined isolated Python3.13.5 tests passed**, and a real `setuptools` **226-synthetic-module**, 231-ZIP-member Wheel passed stable test-key signature, complete custody and lock checks; intentionally dirty source was rejected. **This is not the actual-source 226-module Wheel**; real Python3.12/Ruff, full checkout, signer trust and PAPER acceptance remain blocking. No merge or tag.

**Stage 2H isolated stable build context (2026-10-17):** [`MMT_V0_4_0_STAGE2H_ISOLATED_STABLE_BUILD_CONTEXT.md`](MMT_V0_4_0_STAGE2H_ISOLATED_STABLE_BUILD_CONTEXT.md) documents a new exact-Git/snapshot-pinned **226-module RC→stable test-only staging utility**, which modifies `version` exclusively in a new private staging directory and never modifies the tracked RC package. **68/68 combined Python3.13.5 isolated suite tests passed**, including 10 new staging denial/copy cases. A real `setuptools` Wheel built from **synthetic** 226-module staged content contained 231 members, and all 226 Wheel source bytes and RECORD were verified. Actual GitHub 226-module source bodies, clean Python3.12/Ruff, production-safe signed stable source provenance, real full-project Wheel/installation/PAPER tests and signer approval are **NOT verified**. This staging proof does not authorize stable publication or merge.

**Stage 2I signed RC→stable overlay custody (2026-10-17):** [`MMT_V0_4_0_STAGE2I_SIGNED_RC_OVERLAY_CUSTODY.md`](MMT_V0_4_0_STAGE2I_SIGNED_RC_OVERLAY_CUSTODY.md) adds a read-only source-custody gate tying an independently signed *stable* Wheel to an externally pinned clean **RC Git commit**, the existing exact 226-module Git tree lock, and the single reviewed `0.4.0rc1` → `0.4.0` metadata transformation. The real GitHub packaging metadata was byte-matched to Git blob `8173a96d589e7d0e7ea9b9ba4a4b7a191b4ec877`; the exact staged metadata SHA256 is `11d87431c863a20514541d8c2eaf70e47555d0ca2e2dbd8d1ded11c994ac01d7`. **80/80** focused cases passed on CPython **3.13.5**, including 12 new RC overlay cases; a genuine setuptools-built 226-*synthetic*-module Wheel with detached test-key signature passed, but the actual **226 source bodies** and Python3.12/Ruff/full integration remain unavailable. This overlay is **not** an approved stable source commit or a release authorization; PR must remain Draft and the official tag absent.

**Stage 2J two-Wheel comparison (2026-10-17):** [`MMT_V0_4_0_STAGE2J_DUAL_WHEEL_REPRO_AND_GATES.md`](MMT_V0_4_0_STAGE2J_DUAL_WHEEL_REPRO_AND_GATES.md) commits a new fail-closed signed-overlay/clean-Git dual-Wheel byte-identity verifier and **16 executed** local regression cases. **96/96** combined focused tests passed in CPython3.13.5; two separate real setuptools builds of a 226-**synthetic**-module source fixture (231 ZIP members, 1,412,969 bytes per Wheel) gave byte-identical SHA256 `3dd8009c57e0c3bd37fb5d9872e60b04c9e0f4cf40668b952db1a2933983eff2`. This does **not** prove independent builders, a complete real-source Wheel, Python3.12, real trusted publisher signature, installed runtime or PAPER readiness. No `main` merge or official `v0.4.0` tag.

**Stage 2K actual GitHub source-body and Wheel description custody (2026-10-17):** [`MMT_V0_4_0_STAGE2K_REAL_SOURCE_BODY_AND_METADATA_CUSTODY.md`](MMT_V0_4_0_STAGE2K_REAL_SOURCE_BODY_AND_METADATA_CUSTODY.md) records **226/226 real source file bodies** individually retrieved from the immutable GitHub source commit and matched to Git blob hashes in the locked public inventory (no forbidden direct private-core import string found). A confirmed re-signed Wheel metadata provenance gap was closed by requiring **METADATA Summary, text/markdown and full README body equality** to the pinned Git packaging inputs. Three new forged-but-validly-signed negative tests passed; **100/100** focused tests passed in the isolated **Python3.13.5** runner, and exact edited GitHub file blobs match locally executed bytes. Full real-source Wheel build, Python3.12/Ruff, approved signer, installed nonroot/PAPER/rollback tests still **NOT RUN**. Keep Draft and no tag.

**Stage 2L REAL-SOURCE RELEASE BLOCKER (2026-10-17):** [`MMT_V0_4_0_STAGE2L_PRODUCTION_GUARD_HARDENING_AND_RELEASE_FENCE.md`](MMT_V0_4_0_STAGE2L_PRODUCTION_GUARD_HARDENING_AND_RELEASE_FENCE.md) documents a complete 226-module GitHub source inspection exposing dozens of `MMT_PRODUCTION == "1"` value-only guards that allow explicitly defined `MMT_PRODUCTION=0` to bypass nonproduction admission. **Six key installed/PAPER/Brooks/admin entrypoints were fixed** and the **226-source Git lock rebased** (new subtree `46bf28c689a886e02b149dd31e86ad2daa25234e`, lock SHA256 `affde088b2639e8b4820ab1a19abbb5797d3243720faf2b7c9e11f5f02991076`). An offline AST scanner now blocks ALL stable staging if any old value-only guard survives, before any output is created; **114/114 isolated Python3.13.5 tests PASS** (including a clean/re-pinned 226-module Git case proving fail closed). The new 56-case checkout-bound entrypoint suite was **not run**, nor real full Python3.12/Ruff/recovery acceptance. One Brooks subprocess explicitly sets `MMT_PRODUCTION=0`, so remaining runtime migrations require dependency-aware edits and actual tests; do NOT blanket-replace guards without reviewing such child environments. **Current stable build remains intentionally blocked; keep PR Draft and no tag.**

On the **exact candidate commit**, in an isolated approved nonroot Linux environment with real CPython 3.12 and Ruff:

- Full static/lint/type/import checks, test discovery and full unit + integration test suite, including PostgreSQL when required; record total passes/skips/fails and investigate critical skips.
- R42V 59-case pinned runtime tests, signed/canonical JSON recursion fail-closed regressions, synthetic R42 account/feed evidence and exact SHA guard; re-evaluate pin files if modified.
- Real packaged `multi-market-trading` wheel install (not `pip install .` of the frozen legacy root), clear dependency closure, CLI/help/packaging checks.
- Offline signed synthetic CLOSED-bar replay → **real pinned Brooks V5 decision** → independent risk gates → PAPER-only order-intent/ledger → inspect/restart/replay/dedup → stop.
- Crash-between-phases, UNKNOWN orders, kill switch, idempotence, duplicate funding/PnL defense, restore/rollback and 32-restart soak at minimum; no invented Brooks profitable signal.
- Separate bounded broker/Telegram/provider tests using local mocks only: no live order, real Telegram sending or external account tokens.
- **Exit:** zero unexplained critical fails, reproducible full-test transcript for exact SHA, explicit zero-live-send/order assertion, no skipped security-critical acceptance.

### 3 — Supply-chain and operator approval (pending; blocking)

- Isolated deterministic wheel build twice with SHA/RECORD compare, lockfile + dependency verification; signed manifest/checksum and trusted signer/revocation negative cases.
- Rootless/gVisor and external security advisories must be independently qualified or unavailable features explicitly excluded from v0.4.0 scope (fail closed).
- Review secret handling, network-deny-by-default, account eligibility, legal/provider restrictions, exposure of private NY First-Reversal code and any optional public engine plugin.
- Restore older installed data without modifying production; write operator install/rollback/backup documentation and release artifact inventory.
- **Exit:** source SHA → artifact hash → signature → installed wheel reproducible custody chain, signed-off critical security and rollback gates.

### 4 — Review and merge candidate into protected main (pending; blocking)

- Recompare candidate vs latest `main` with ahead/behind; incorporate any newly landed fixes and rerun changed-gate tests.
- Turn Draft PR ready only after stages 1–3; complete human-readable diff review, release-blocker checklist and branch protection policy.
- Prefer one **non-squash merge** for the historical 300+ commit reconciliation to preserve review and provenance, unless protected repository policy or independent review identifies a better safe merge method.
- Merge only if GitHub reports mergeable, approval and required checks pass; pin expected head SHA.
- **Exit:** verified exact merge commit on `main`, branch review closed, main unchanged by any unrelated writes during check.

### 5 — Pre-release packaging rehearsal (pending)

- Prepare `0.4.0rc1` metadata consistently; build candidate wheel from the merged/refrozen **tested commit**. If any change is needed, create `rc2` and repeat gates.
- Optional **GitHub prerelease** `v0.4.0-rc.1` only after acceptance; it must point to an unambiguous frozen commit with release assets, artifact checksums and the truthful OFFLINE/PAPER boundary.
- Rehearse `install -> configure -> offline replay -> PAPER -> restart -> inspect -> stop -> rollback` on clean Linux/Python 3.12. Confirm no legacy 0.3.2 corruption and no production migration.
- **Exit:** signed candidate artifacts, install/rollback report, all blocker gates green and independently checked.

### 6 — Final v0.4.0 promotion (pending; blocking)

- Create final metadata release commit on `main` with `platform_release/pyproject.toml: version = "0.4.0"`; synchronize any platform-reported version (CLI/build/docs/CHANGELOG) without changing frozen legacy version or 359-entry manifest.
- Build and independently test the **exact final commit** (not only an earlier RC); verify wheel metadata, SHA, signature, smoke tests, zero critical vulnerabilities and compatibility matrix.
- Create a **new annotated Git tag** `v0.4.0` pointing to that exact green `main` commit. Do **not** move existing tags or create tag on an unmerged temporary branch.
- Publish GitHub Release `v0.4.0` with wheel/source artifacts, SHA256 hashes, signature verification instructions, supported platforms, install instructions, migration/rollback, known limitations, and no unsupported earnings or LIVE claims.
- **Exit:** Git tag commit == tested source commit == published artifact provenance, downloadable valid artifacts and immutable release notes.

### 7 — Post-release verification (pending)

- Fresh nonroot verification using the public release artifact; repeat OFFLINE/PAPER mini-journey and rollback.
- Audit `v0.4.0` and `v0.3.2` coexistence; protect legacy users and publish follow-up `v0.4.1` only for fixes if necessary.
- Track separate later live-trading, authenticated provider, private-core isolation and Telegram-delivery authorization. Those are **not** implied by publishing `v0.4.0`.

## 4. Release denial policy

- In this repo, label a version 'stable' only if the stated *offline/PAPER* product scope is independently tested and documented. Stable versioning NEVER authorizes real-money/live trading.
- If critical integration tests, runtime Python 3.12, source custody, signing or migration/rollback are missing: **do not merge into main or tag stable**.
- GitHub Actions quota is constrained; test in independently approved disposable environments rather than relying on failed/skipped checks or consuming costly Actions speculatively.
- **No permanent server, Production migration, token handling, Telegram delivery or LIVE orders as part of this roadmap.**

## 5. Final decision matrix

| Gate | Current |
|---|---|
| Stable target chosen | **v0.4.0 / DONE** |
| Branch lineage consolidated | **DONE** |
| Main merged | **NO** |
| Separate divergent heads accepted | **PENDING per-branch** |
| CPython 3.12 + Ruff on combined head | **NOT RUN** |
| Full integration, installer and crash/restart on combined head | **NOT RUN** |
| Signed provenance, security and rollback | **NOT VERIFIED** |
| Official Git tag v0.4.0 | **NOT CREATED** |
| LIVE and Production | **DENIED / OUT OF SCOPE** |

**Overall:** `V0_4_0_RELEASE_CANDIDATE_BRANCH_PREPARED__MAIN_MERGE_AND_TAG_BLOCKED`.
