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
