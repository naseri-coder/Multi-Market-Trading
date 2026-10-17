# Multi-Market-Trading — post-FIX-05 product readiness decision

**Snapshot:** 2026-10-17; `main@7ea741e678b9eeaf524e7ef9e06abe006a050ced`
**Scope:** public repository, existing CI evidence and disposable read-only source checks.
**Decision:** `OFFLINE_PAPER_PREVIEW_VALIDATED__INTEGRATED_PRODUCT_NOT_READY`

## What was actually checked

- The five merged corrections are traceable as PRs #341–#345, each committed to `main`.
- PR #345: 22/22 successful GitHub check runs on its tested PR head
  `44bb06aafd20dfa00158fb8d99a8c6011322837d`, including CodeQL,
  publication safety and both full PostgreSQL corpora. The scoped clean-wheel
  Stage-15 job also completed successfully.
- The independent MMT-FIX-05 regression evidence was 5,882 passed, zero
  failed, 36 skipped, 3 warnings and 2 passed subtests. This is evidence for
  the evaluated test environment, NOT proof of each skipped capability.
- On the new `main`: `bash scripts/verify.sh` PASS; the frozen legacy
  `SHA256SUMS` still has 359 entries plus three separately pinned historical
  public cold-start Python modules. Brooks historical runtime untouched.
- `python3 scripts/a6_release_preflight.py`: isolated `0.4.0rc1` preview
  identity PASS; no database migration, production activation or private-core
  source inclusion.
- `MMT_NONPRODUCTION=1 python3 -m scripts.mmt_stage15_readiness
  --repository . --ack-source-audit`: `SOURCE_PREFLIGHT_PASS` with
  `PRODUCT_NOT_READY_FOR_PUBLIC_OR_LIVE_RELEASE`. This is a **source-only**
  read; it does not execute an installed worker.

## Capability decision matrix

| Capability | Status / evidence | What it does NOT prove |
| --- | --- | --- |
| Root `crypto-price-action==0.3.2` | Preserved frozen legacy source | New v0.4 runtime upgraded or migrated |
| `multi-market-trading==0.4.0rc1` install | Isolated preview wheel and CLI accepted | General production installer or release authority |
| `naseri-paper-demo` | Installed bundled toy, SHA/CAS enable, replay dedup, restart/disable, local ledger guards | Real strategy, third-party code isolation or live fills |
| `naseri-paper-pilot` | Installed Stage10 synthetic **two-binding** Stage20 PAPER and read-only five-ledger reopen | Actual Brooks-to-Stage20 integrated trading service |
| Brooks V5 offline | Pinned genuine engine can be called through explicit offline replay, with source and PAPER scan receipts | Continuous authenticated market feed, profitability or broker orders |
| Product Telegram panel | Development `/engines`/`/custom` controls, offline tested; effective publication disabled | Real channel delivery or private send reconciliation |
| Futures provider selector | Official public metadata is separable from trading entitlement; Iran-resident verified allowlist currently empty per Stage2 contract | Verified residency/account access or futures trading permission |
| PAPER PnL | Modeled economics, ledger consistency, corrupt exit refusal | Broker-attested position/PnL or a profitable strategy |
| External strategy plugins | Metadata/opt-in local *trusted* source demonstrations exist | Hostile third-party executable containment |
| Live deployment / LIVE orders | All release permission fields remain false | Production readiness or compliance |

## Interpretation: reconcile the old Stage15 blocker text

Stage15 was originally authored before the Stage10 two-binding and later
MMT-FIX-05 installed-wheel acceptance. Its source-only finding should not
claim that *no* clean installed PAPER journey exists. There **are** limited
installed offline demonstrations; however the complete authenticated,
operator-configurable multi-market product journey is still unverified.
The updated blocker explanations retain the original stable gate codes
and fail-closed release verdict; there is **no automatic entitlement grant**.

## Decision: three bounded engineering steps to a stronger offline PAPER MVP

### MMT-PAPER-07 — one authoritative installed offline Brooks PAPER path (P0)

Re-use existing `mmt-dev` operator controls, the pinned Brooks V5 offline
replay, Stage20 orchestrator and Stage8/9 risk/order receipts. Select **one**
documented state authority/ledger contract and avoid a second independent
database or engine. Start with signed-off, synthetic **closed bars**,
explicit OFF/PAPER and never automatic LIVE or Telegram sending.
Acceptance: independent installed wheel; operator config changes the
effective timeframe/symbol in actual processing; genuine V5 `NO_SIGNAL`
becomes a scan rather than an invented trade; any real V5 signal yields
exactly one accepted or risk-refused PAPER intent, with the correct identity;
revocation, mismatched instrument and duplicate replay reject without new
execution or PnL rows. Do not fabricate a successful Brooks signal to pass.

### MMT-PAPER-08 — crash/restart and operator observability (P0)

Add no new supervisor: use one supported installed operator surface to
query desired/effective state, scan/decision/rejection reasons, PAPER
positions, modeled fees, realized/unrealized PnL and next permitted action.
Acceptance: deterministic offline restart and deliberate crash/replay
scenarios, stop/kill-switch, no duplicate order-intent or double-release,
retained immutable evidence IDs, bounded errors, clear UNKNOWN/quarantine.
An interrupted ambiguous action must stay blocked pending explicit review.

### MMT-PAPER-09 — release candidate rehearsal for *offline* use only (P0)

Fresh non-root install into a disposable environment, test with Python
3.12, pin dependency closure, read-only reopens, export/backup/restore
rehearsal, interrupted upgrade rollback and bounded concurrency/soak.
Acceptance: a repeatable `install -> configure -> offline replay -> PAPER
-> restart -> inspect -> stop` test, CI evidence artifact and operator
guide; no production server, automatic publication or broker attachment.
The 0.3.2 PostgreSQL migration is **not** implied or permitted.

These are **three planned nonproduction delivery milestones**, not a
countdown to live trading. Each stage requires genuine tests and explicit
approval before proceeding to the next.

## Independent later gates (not included in the three-step PAPER program)

- Provider selection: independent authenticated, up-to-date futures
  eligibility by actual residency/account/instrument and quality-checked
  live provider feed; a public metadata endpoint alone is not permission.
- Telegram: real private-channel permissions, delivery acknowledgments,
  safe UNKNOWN handling, retry/idempotency and revocation tests.
- Third-party engines: independently accepted isolation/custody, publisher
  permission and protection of owner-private NY First-Reversal.
- Operations: incident/revoke recovery, secrets, real broker position
  reconciliation, migration plan, security advisories and a controlled
  release/rollback decision. Historical October 14 container vulnerability
  counts require fresh independent re-triage; do not mark them fixed.
- Performance: point-in-time real data, fees/slippage/funding, holdout and
  walk-forward validation before any claimed trading edge.
- LIVE orders and Production remain forbidden until separately authorized
  and independently accepted; do not treat PAPER CI results as permission.

## Hard invariants

Do not edit the frozen 359-file legacy manifest, merge private NYFR
source into the public repository, weaken hard-coded release refusals,
contact trading/Telegram endpoints during this stage, create a server,
or touch the existing Production database. This decision record is not a
license, investment advice, profitability claim or deployment authorization.
