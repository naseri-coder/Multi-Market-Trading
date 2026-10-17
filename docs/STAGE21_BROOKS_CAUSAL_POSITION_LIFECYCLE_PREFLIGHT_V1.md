# Stage 21A — Actual Brooks V5 Geometry → Broker-Free Modeled Trade Lifecycle

**Status:** RESEARCH PREFLIGHT ONLY. This is NOT a live or forward-connected PAPER worker; no authenticated fill evidence; no broker/Telegram account; no PnL claim about actual executions or OOS.

## Why the existing Stages 15–20 were insufficient

The existing Stage15 frozen Brooks subprocess already emits and internally reviews actual entry/stop/targets as well as a complete source manifest, snapshot hash and rule evidence. For safety it returns only decision and cryptographic proof to the outside research report. A naked LONG/SHORT cannot be treated as a trade. Also the existing Stage16 modeled cashflow calculator accepts **caller-chosen** scenarios, not causally observed Brooks trades. Stage20 kept the holdout unopened.

Stage21A introduces `naseri_markets/brooks_causal_lifecycle_stage21_preflight_v1.py`, using only existing frozen source and validated components, without modifying any source strategy, 359-file manifest, existing PAPER journal, risk manager, panel or operational deployment:

- Take only an explicitly supplied 60–224-bar, UTC 15-minute CLOSED-candle `binance_replay` payload and an absolute, SHA-frozen source checkout. Invoke the **genuine** Stage15 isolated subprocess once, then use the **original** Stage15 `_review` to verify engine version, rule/config identity, snapshot hash and authentic computed entry/stop/targets. Refuse unverified geometry.
- Only **after** engine evaluation, supply a separate sequence of 1–32 later complete, continuous candles. Re-run the original strict replay parser across the concatenation. Verify that the first continuation candle opens exactly at the decision cutoff. None of the continuation bars are included in the original worker payload.
- If NO_SIGNAL, no trade exists. Otherwise use a clearly **hypothetical market entry at the next bar's open**, not Brooks's proven actual order execution. Skip a model entry when the next open differs by over 2% from Brooks's original entry anchor or when the entry is on the wrong side of the stop/target geometry.
- Fix a single, non-optimized exit convention **nearest TP1** plus protective stop. If stop and target could both occur inside the same bar, choose the stop (worst case); on a subsequent adverse opening gap beyond the stop, exit at the *worse opening price*. Never award a favourable target gap better than TP1. If neither occurs, close hypothetically at the last provided bar's close (maximum 32 bars / 8h).
- Apply a SHA-pinned operator-defined USDT-linear metadata document, contract tick rounding adverse to the hypothetical position, and the existing Stage16 model for explicit taker fees, funding mark assumptions and adverse slippage. Require event-by-event equality against a caller-supplied declared funding-time inventory for every modeled position. **The schedule itself has no independent time-source attestation.** A missing expected event refuses.
- Record source manifest, original decision and future-input hashes, precise hypothetical lifecycle outcome and Stage16 cashflow receipt; always set `broker_fill_verified=false`, `actual_realized_pnl=false`, `paper_trading_enabled=false`, `live_trading_authorized=false`.

## What this does NOT certify

No actual signed fill, tick-by-tick bid/ask, order queue, real short/long borrow, contract leverage tier, liquidation insurance, account-specific fee discount, funding settlement exact Mark, causal ordertype equivalence or statistical strategy performance. A next-open market fill is **a research assumption** and should NOT be conflated with Al Brooks engine entry price or stop/limit intent. Intrabar stop/TP order is unobservable with only OHLC, so the adverse stop convention is deliberate; other execution orders are untestable with this material. An 8-hour forced horizon is only a bounded research simplification, not a V5 exit rule.

New Stage18 PR #304 acquired genuine primary-source January 2024 funding and mark archives and produced SHA-consistent settlement-proxy CSVs. Those are separate and **not yet joined or semantically accepted in this Stage21A modeled-cashflow study**. Its output requires operator-supplied metadata and funding inventory, which remain untrusted. Do not promote that input to verified historical economics.

The historical 2024 month is **retrospectively** available in 2026. It cannot be relabeled as a pristine prospective OOS interval. To pursue truly forward PAPER research, the user must independently lock a time-ordered protocol before unseen future candles accrue, separately prove the stream's origin/clock, provider fee/contract/funding coverage, and approve a disposable never-live deployment. Stage20's unopened holdout does not become verified OOS by preparing this module.

## Required checks and preservation

- Run Public Test Corpus with genuine frozen V5 on synthetic close-only replay and adversarial model fixtures for stop-first simultaneous target/stop, favourable/adverse gaps, missing funding evidence, duplicate/future-open candle, price grid, NO_SIGNAL, and the Production fence.
- Run CodeQL and Publication Safety on the final exact head and keep Draft until all protected security checks pass.
- No production source files, risk policies, licensed custom NYFR code, database schema, subscriber settings, Telegram channels, live trading accounts, paper daemons or main branch modifications.
- No Stage21 Forward/PAPER activation or Stage22 before the separate acceptance gates. An offline callable is not a deployed task.

**Verdict target:** `STAGE21_BROOKS_CAUSAL_TRADE_MODEL_PREFLIGHT_CODE_READY_ONLY`. This is an incremental implementation of Stage21 prerequisites, NOT Stage21 empirical forward-test completion.
