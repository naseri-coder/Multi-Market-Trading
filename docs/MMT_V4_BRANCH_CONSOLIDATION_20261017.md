# MMT v4 integration candidate — all-branch reconciliation (2026-10-17)

**Decision:** `INTEGRATED_SOURCE_CANDIDATE__NOT_RELEASE_READY`

**Scope:** GitHub source consolidation only. NO production, LIVE, broker/Telegram activity, secret access, server creation, or version tag.

## Verified Git lineage

- Repository: `naseri-coder/Multi-Market-Trading`; protected default branch `main`.
- 57 branch heads compared with `feature/mmt-r42v-pinned-python312-ruff-acceptance-v1`: **36 fully contained ancestor branches**, **20 divergent/independent branches**, and **one canonical R42V head**.
- Existing main at review: `51e0e4de04e184fe28b59b9db4b6a70fbd67dfe0` (nine new commits after the original common ancestor, PRs #341–#349).
- Canonical R42V at review: `1e6767b2be9fb5b2a35520b45af0b497596e45d1`.
- Nonproduction integration branch: `integration/v4.0.0-candidate-20261017`.
- **PR #350** merged `main` INTO the **integration branch**, not the reverse. Integration commit `31bc1ee57183ce91d601042b46ed4720132fb16e`.
- Independent compare: `main...integration` = **ahead 308 / behind 0**, `R42V...integration` = **ahead 10 / behind 0**. Both histories are preserved and no force-push occurred.
- Integrated Git tree 1,702 entries, `truncated=false`. The three R42V acceptance input blobs remain exactly pinned:
  - `scripts/mmt_r42_offline_market_account_evidence_v1.py`: `070c56bd8774372c40bb61f8316c92988e8c9b35`;
  - `tests/unit/test_mmt_r42_offline_market_account_evidence_v1.py`: `eab305facdc6ce9406f3a488a602f2b5b62a1b19`;
  - `tests/unit/test_mmt_r42v_pinned_runtime_acceptance_v1.py`: `ae7ec4f16caf89e9c2dcfc564f9faa9b75874a6a`.

## Branch disposition (all 57)

### Included through the original canonical R42V ancestry (36)

- `audit/stage17-21d-main-codeql-readonly-v1`
- `feature/stage18-futures-economics-reconciliation-v1`
- `feature/stage19-brooks-v5-causal-backtest-preflight-v1`
- `feature/stage20-frozen-walk-forward-preholdout-v1`
- `feature/stage21-brooks-trade-lifecycle-causal-preflight-v1`
- `feature/stage21b-real-source-funded-brooks-causal-audit-v1`
- `feature/stage21c-brooks-forward-precommit-custody-v1`
- `feature/stage21d-brooks-rfc3161-witness-verification-v1`
- `feature/stage21e-public-tsa-prospective-precommit-v1`
- `feature/stage21f-prospective-raw-candle-admission-v1`
- `feature/stage21g-brooks-readonly-source-custody-v1`
- `feature/mmt-r22-canonical-consolidation-preflight-v1`
- `feature/mmt-r23-termux-original-witness-forward-first-capture-v1`
- `feature/mmt-r24-sequential-forward-custody-and-gap-ledger-v1`
- `feature/mmt-r25-forward-source-governance-revision-review-v1`
- `feature/mmt-r26-brooks-causal-execution-parity-audit-v1`
- `feature/mmt-r27-independent-brooks-lifecycle-economics-crosscheck-v1`
- `feature/mmt-r28-unified-offline-runtime-recovery-fence-v1`
- `feature/mmt-r29-future-source-readonly-shadow-paper-v1`
- `feature/mmt-r30-offline-risk-order-evidence-gates-v1`
- `feature/mmt-r31-offline-private-admin-signal-observability-v1`
- `feature/mmt-r32-offline-review-package-and-recovery-gate-v1`
- `feature/mmt-r33-live-readiness-hard-deny-audit-v1`
- `feature/mmt-r34-offline-stack-acceptance-evidence-v1`
- `feature/mmt-r35-offline-wheel-easy-installer-v1`
- `feature/mmt-r36-offline-supply-chain-provenance-v1`
- `feature/mmt-r37-detached-release-manifest-verifier-v1`
- `feature/mmt-r38-signed-preview-install-failclosed-v1`
- `feature/mmt-r39-durable-synthetic-paper-authority-v1`
- `feature/mmt-r40-readonly-installed-paper-acceptance-v1`
- `feature/mmt-r41-readonly-rootless-gvisor-contract-audit-v1`
- `feature/mmt-r42-offline-market-account-evidence-gate-v1`
- `feature/mmt-r42-signed-offline-market-account-evidence-v1`
- `feature/mmt-r42c-canonical-synthetic-account-audit-v1`
- `feature/mmt-r42v-independent-acceptance-evidence-v1`
- `feature/mmt-r42vh-json-nesting-failclosed-v1`

No duplicate cherry-picks should be made from these branch heads.

### Mainline integrated after divergence (1)

- `main` — its nine FIX-01..05 and PAPER-07..09 commits were merged into this candidate through PR #350. The `main` ref itself did not move.

### Independent heads retained for separate acceptance (19)

1. `develop/v0.3.0`: legacy divergent history; freeze/retention and migration review required, no indiscriminate backport.
2. `audit/runtime-a1-data-a1-paper-contract-20261014`: audit documentation fork; compare against current runtime contracts before importing obsolete conclusions.
3. `cert-a19-independent-security-research` and `cert-a19-byte-audit-run`: security/OCI research with incomplete external-host certification; do not claim vulnerability closure or silently add build authority.
4. `feat/stage27-signed-public-intake`: independent publisher/core-intake implementation; permission and hostile-module isolation acceptance pending.
5. `feature/stage17-authentic-monthly-market-data-custody-v1` and `feature/stage18-primary-funding-mark-btcusdt-2024-01-v1`: independent historical-source/funding evidence paths; current canonical chain uses bounded provenance and forward gates; reconcile data identity before choosing a provider path.
6. `feature/stage21f-immutable-forward-source-intake-v1`: parallel admission design; canonical prospective RFC3161 implementation takes precedence pending adversarial review.
7. `feature/mmt-r26-brooks-decision-economic-parity-audit-v1`: alternative Brooks execution-economics auditor; independent cross-check, not unconditional engine replacement.
8. `feature/mmt-r38-signed-offline-preview-install-gate-v1`: superseded candidate for signed preview installer; canonical fail-closed R38 branch already contained.
9. `feature/mmt-r42-offline-feed-account-evidence-v1` and `feature/mmt-r42-signed-offline-market-account-audit-v1`: parallel R42 auditors; canonical R42C/V/VH selected, avoid conflicting duplicate trust authorities.
10. Seven Dependabot branches — `dependabot/github_actions/actions/setup-node-7.1.0`, `dependabot/github_actions/actions/upload-artifact-7.0.2`, `dependabot/pip/asyncpg-0.32.0`, `dependabot/pip/numpy-2.5.4`, `dependabot/pip/ruff-0.17.0`, `dependabot/pip/sqlalchemy-2.1.4`, `dependabot/pip/tzdata-2026.5`. Their dependency/lockfile or workflow changes require full reproducibility, lock-refresh, CI and behavioral-regression review, not auto-merge.

These heads have **not** been lost or deleted. Having independent commits is not evidence that they should all be compiled into one runtime.

## Existing version identity and release decision

- Root frozen legacy package: `crypto-price-action==0.3.2`.
- Separate installable platform preview: `multi-market-trading==0.4.0rc1`.
- `v4.0.0` is a proposed new major-version tag name, **not** an existing package version, validated semantic-version change, or published release.
- Do not rewrite the legacy `production_source/SHA256SUMS` or rename `0.4.0rc1` solely to make a desired tag appear. Define the release contract and migration strategy before an actual v4.0.0 tag.

## Evidentiary limits and required acceptance

Historical, branch-scoped results must not be misrepresented as tests of integration commit `31bc1ee`:
- mainline prior FIX-05 evidence: 5,882 passed, 36 skipped; prior PR #345 GitHub checks 22/22; subsequent PAPER07–09 patches were merged but this combined branch was not retested here.
- R42V independent Python 3.13.5 synthetic suite: 59/59 pass. **Python 3.12 runtime, actual Ruff, full repository/installed-wheel recovery and gVisor host acceptance remained pending.**
- Integration work in this change consisted of server-side merge, exact ref/ancestry/tree and three Git blob pin checks. **No new runtime tests, clean install, security scan, broker/account reconciliation, or release-signing verification were executed for the combined branch.**
- Do not spend GitHub Actions quota unnecessarily; future acceptance can use an approved isolated nonroot Linux/Python 3.12 test runner.

**Required before promoting stable v4.0.0:**
1. Verified Python 3.12, Ruff, full unit/integration/isolated-wheel tests; require real results for the final merged SHA.
2. Installed OFFLINE/PAPER multi-engine startup/shutdown and database recovery, idempotency, feed provenance, health checks, repeated crash/restore, zero unintended LIVE orders and Telegram sends.
3. Signed build/provenance, reproducible dependency closure, privacy/supply-chain/static/security results and explicit support/migration/rollback documentation.
4. Versioning and API/database compatibility review; authorized promotion to `main` with independent check of protected-branch policies.
5. Only then create a release commit and **actual** tag `v4.0.0` (not a substitute branch name), with explicit release notes and independent verification. Any LIVE activation remains a separate gated authorization.

**Status:** `BRANCHES_INVENTORIED_57__R42_MAIN_INTEGRATED__STABLE_V4_TAG_BLOCKED_PENDING_ACCEPTANCE`.
