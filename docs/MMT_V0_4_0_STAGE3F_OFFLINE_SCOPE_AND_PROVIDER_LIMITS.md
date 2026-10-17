# MMT v0.4.0 — Stage 3F strict OFFLINE/PAPER release-scope boundary

**Decision:** `OFFLINE_REPLAY_PAPER_SCOPE_DRAFT__LIVE_FEEDS_UNVERIFIED__RELEASE_BLOCKED`.

## Verified upstream event

User approved two public **unauthenticated and read-only GET** tests. The real GitHub-hosted run [39062296330](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/39062296330), job 117482570405, executed the original two byte-identical integration test functions using the exact already-accepted candidate Git SHA `77a0b19f89485d1e8b7a4cb43caa01eed123af47`.

- Binance USD-M Futures BTCUSDT 15m endpoint: **HTTP 451**, failure before any valid candle snapshot.
- Bybit Spot BTCUSDT 15m endpoint: **HTTP 403**, failure before any valid candle snapshot.
- **0 passed, 2 failed.** Neither provider's usable public-data stream was validated. This is a recorded upstream denial, not a pass, nor proof of a product parsing bug. Do not evade geographical, eligibility or provider policy restrictions.

The probe ran on separate CI branch `ci/stage3e-public-market-smoke-20261017`, with only a CI workflow file added. It did not modify PR #352. The same original candidate head had previously completed **79/79 PR CI jobs SUCCESS**, but that corpus intentionally skipped these two opt-in network tests. These are separate, non-contradictory statements.

## Stage 3F scope under proposal — NOT an automatically approved waiver

The minimum defensible *claimed* distribution lane is **offline historical replay and disposable simulated PAPER demonstration**. It does not assert that all packaged CLI entrypoints are physically disabled or that unified installed PAPER product readiness is complete.

The **only listed entrypoints eligible for documentation in this limited scope** are `naseri-brooks-replay` and `naseri-paper-demo`, and only with approved local/offline inputs and benign nonproduction workflows. The PEP 440 candidate remains `0.4.0rc1`, target stable `0.4.0`, Python 3.12. The frozen root `crypto-price-action==0.3.2` remains a distinct historical product and is not rewritten.

Excluded/not independently accepted:
- Network-backed Binance/Bybit polling as a validated release feature, automatic exchange selection, provider data eligibility and guarantees of fresh live market feed.
- Every real order/LIVE route, financial services production, user-account authentication and account reconciliation.
- Telegram publication/real messaging, production/Telmivo deployment, host isolation for marketplace plugins, general third-party binary execution and owner's private NY First-Reversal engine.
- Automatic commercial release approval, independent operator/publisher identity, and protected-main review.

**Important nuance:** other preview CLI names are still present in the Wheel metadata. Stage3F is an *evidence and public-claim clamp*, **not a feature-disable switch or a complete runtime safety certificate**. Before distribution to end users, separately demonstrate that unsupported features cannot be unintentionally invoked in the intended installation path. Until then, no install/package publication is authorized.

## Machine-readable refusal

- `docs/evidence/MMT_V0_4_0_STAGE3E_PROVIDER_RESULTS.json`: canonical historical event (real GitHub run and HTTP statuses).
- `docs/MMT_V0_4_0_STAGE3F_SCOPE_CONTRACT.json`: exact supported-claims draft, external-review and signing status **PENDING**, `release_authorized=false`.
- `scripts/mmt_v040_stage3f_scope_gate.py`: accepts only exact safe scope/evidence fields; checks package identity, preview version, pinned empty base dependencies and exact offline CLI entrypoints; returns an explicitly unapproved verdict. It rejects deleting a failure, claiming live connection or signer approval, an altered package version, symlinked evidence and duplicate/noncanonical JSON.
- `tests/unit/test_mmt_v040_stage3f_scope_gate.py`: isolated fail-closed regression tests.
- `.github/workflows/stage3f-offline-paper-scope.yml`: isolated Python3.12 CI without network or private keys.

## Non-automatable admission (still blocking)

Independent human review must decide whether this restricted scope is actually acceptable, and approved packaging must not quietly ship reachable LIVE features as though disabled. Real publisher/operator Ed25519 public-key identities and independently signed manifests, protected-main human PR reviews, and the final exact-SHA reproducible stable metadata checks also remain mandatory.

**No `main` merge, official `v0.4.0` tag, LIVE orders, production/Telmivo deployment, signing key uploads, Telegram sends, or false green label for the two provider smokes.** Keep PR #352 Draft and issue #354 open.
