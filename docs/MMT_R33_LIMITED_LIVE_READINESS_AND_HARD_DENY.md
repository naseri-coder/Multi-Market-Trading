# MMT-R33 — Restricted LIVE **Readiness Review**, Hard Deny (no execution)

**2026-10-16; DRAFT only; directly stacked on R32 PR #325, not main.**

R33 is the roadmap's restricted LIVE milestone, but the upstream scientific,
security, capital and operational gates are not accepted. This contribution
**does not begin LIVE, create a venue adapter, import exchange credentials,
request API access, deploy a server, enable Telegram sending, publish a signal,
send a real/PAPER order, remove a kill switch, or authorize a real trade**.

The only honest executable artifact at this stage is a deterministic
**read-only blocker inventory + clearly hypothetical one-position risk example**.

## Verified prior PR dependency state (snapshot, not a future live lookup)

As of the GitHub review on 2026-10-16 all of these are open, Draft, unmerged:

| Gate | Draft PR | last observed HEAD |
|---|---:|---|
| R28 offline unified route/restart | #321 | 03a878b7c7f0d5955427efb2f32e3f5611afc919 |
| R29 original-source forward study | #322 | 6031385a463adb9f544dc9250c158b23fdd2a087 |
| R30 pre-order portfolio/risk check | #323 | 19f93e500ef4bc6e1854bb1efd02adebfebb4c22 |
| R31 private operator control panel | #324 | 9658949fa2bb8d22c6ca6012e9af1bc45e6b460c |
| R32 non-installer review/restore research | #325 | f857dc66d91bffee022715fa1a00f0f5ba662f3e |

**No HEAD/PR snapshot is a substitute for checking the official source again at the time of approval.**

The independent prospective Brooks BTCUSDT 15-minute study is scheduled for
2026-10-20 00:00 UTC through 2026-11-03 00:00 UTC. The first possible 60-bar
decision cutoff is 2026-10-20 15:00 UTC, provided complete real admitted
original source has arrived. None of that future data can genuinely be
certified on October 16. Historical simulation must not be substituted for a
prospective OOS trade-performance record.

## New implementation

- naseri_markets/mmt_r33_live_hard_deny_readiness_v1.py implements strict,
  typed immutable observations and one deterministic
  `review_r33_live_readiness` which always outputs `LIVE_HARD_DENY` and
  `can_route_order=false`. Even if a local adversary forges all PRs as merged
  and all evidence booleans as True after November 3, the module still
  generates the two unconditional hard blockers
  `R33_NO_INDEPENDENT_LIVE_RELEASE_AUTHORITY_IMPLEMENTED` and
  `R33_NO_LIVE_ORDER_ROUTE_IN_THIS_STAGE`. An operator's claimed positive
  report is **not an independently attested proof**.
- `R33ReferencePilotEnvelope` and `simulate_r33_reference_position` only
  demonstrate conservative hypothetical linear order exposure caps. The
  placeholder reference profile is **up to 0.25% assumed equity stop risk per
  trade, 0.5% assumed equity daily stop, 10% assumed-equity notional, 1x
  maximum leverage, and only one open position**. These numbers are a
  starting point for future discussion, NOT a live account/trading mandate.
  The model includes operator-assumed round-trip friction and adverse
  slippage; it neither knows exchange contract semantics, maker/taker fee
  tier, funding, Mark price, maintenance margin, realized PnL, liquidation,
  quantity step, actual balance, nor live fill quality. A modeled cap check
  is never an order permission.
- scripts/mmt_r33_manual_live_denial_review_v1.py accepts **only** an explicitly
  operator-provided bounded owner-private 0600 JSON from a private 0700
  folder, requires a clean `MMT_NONPRODUCTION=1` context and explicit
  `--ack-deny-only-review` flag, and returns the hard deny report or safe
  refusal without revealing account, token or path. The file contains only
  operator declarations and is *not* an independently verified readiness
  certificate.
- tests/unit/test_mmt_r33_live_hard_deny_readiness_v1.py contains synthetic
  tests for the real observed five Draft PRs, 2026-10-16 time bar, missing
  risk/security/OOS gates, all-TRUE forged future payload still hard denied,
  strict UTC and JSON validation, private-file safety, reference notional,
  maximum leverage, stop-risk and daily-loss caps, and absence of any live
  order API.

## Manual Termux / desktop local *deny-only* review

Create a new private directory. A **dated public example** is provided at
`docs/evidence/MMT_R33_OPERATOR_CLAIMS_BASELINE_20261016.json`.
It records the five actual observed Draft PR HEADs and sixteen explicitly
FALSE proof flags as of October 16. Copy the sample **out of the repository**
and protect it before using the command; never put account credentials or
tokens into that file. This is a historical template, not current GitHub proof.
Update it from separately inspected records on any future date.

    export MMT_NONPRODUCTION=1
    unset MMT_PRODUCTION
    mkdir -m 700 -p "$HOME/mmt-r33"
    cp docs/evidence/MMT_R33_OPERATOR_CLAIMS_BASELINE_20261016.json \
      "$HOME/mmt-r33/operator-claims.json"
    chmod 600 "$HOME/mmt-r33/operator-claims.json"
    python -m scripts.mmt_r33_manual_live_denial_review_v1 \
      --private-evidence-json "$HOME/mmt-r33/operator-claims.json" \
      --ack-deny-only-review

**There is no supplied pre-approved production configuration.** Even successful
execution will return `LIVE_HARD_DENY`; no broker credentials or real account
details should appear in the JSON.

## Required future R33 LIVE release conditions (no shortcut)

1. Individually review, test and accept prior R28–R32 changes, agree an
   integration plan, and merge only after required branch-policy checks.
2. Collect and independently attest the scheduled R29 original market source;
   establish a sufficient, predefined OOS sample, time-aware causality,
   realistic fees, financing and risk metrics. Merely reaching November 3
   does not establish profitable strategy performance.
3. Run full repository pytest, Ruff, independent CodeQL/security review,
   dependency supply-chain verification and security failure injection;
   record exact reviewed SHAs and test artifacts.
4. Demonstrate reproducible release packaging, signature/publisher custody,
   backup inventory, isolated cold restore, upgrade and rollback rehearsal.
5. Verify exact jurisdiction/residency-specific service eligibility and
   permitted **futures API trading** from official venue terms; a public
   market feed does not constitute permission to trade or bypass restrictions.
6. Independently reconcile broker exchange account balances, existing
   positions, unsettled orders and recover all UNKNOWN side effects; obtain
   genuine fee/funding/Mark/contract quantity/margin metadata. A local
   Stage3/4/17 fixture can **never** be substituted for a live account.
7. Prove a separately reviewed live adapter, a one-way kill switch, no-blind-
   retry idempotency and explicit stop/alerting behavior under process crash,
   network partition, order-ack uncertainty, stale market data, partial fill
   and exchange maintenance.
8. Obtain a fresh, explicit, **specific** operator authorization defining
   exchange, account, instrument, maximum position size, permitted time,
   order type, spend/risk limits and independent monitoring. A generic
   "continue next stage" is not real-order approval.

**Zero of these steps is declared passed by this PR. No connected PAPER/LIVE
trading or production deployment is attempted.**

## Validation needed on the exact final R33 SHA

Without GitHub Actions while its quota is constrained:

    export MMT_NONPRODUCTION=1
    unset MMT_PRODUCTION
    python -m pytest -q tests/unit/test_mmt_r33_live_hard_deny_readiness_v1.py
    python -m pytest -q tests/unit/test_mmt_r32_offline_review_kit_and_recovery_v1.py
    python -m pytest -q tests/unit
    ruff check naseri_markets/mmt_r33_live_hard_deny_readiness_v1.py \
      scripts/mmt_r33_manual_live_denial_review_v1.py \
      tests/unit/test_mmt_r33_live_hard_deny_readiness_v1.py

The release candidate remains blocked until exact-SHA integration tests and
independent risk, provenance, venue, account and real lifecycle checks are
actually completed. Nothing in a static read-only preflight establishes a
profitability track record.

**Disposition:** `MMT_R33_LIVE_HARD_DENY_READINESS_CODE_DRAFT`.
No order, no merger into main, no production installation.
