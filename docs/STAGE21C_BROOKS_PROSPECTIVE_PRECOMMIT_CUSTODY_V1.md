# Stage21C — Brooks V5 Prospective Research Precommitment and Local Custody

**NONPRODUCTION PREPARATION ONLY. NO ONLINE FEED, BROKER, CONNECTED PAPER OR VERIFIED FORWARD RETURNS.**

This Stage21C-Brooks protocol is distinct from the existing KuCoin-oriented `public_forward_capture_stage21c_v1.py` (fixture-core two-symbol flow). Neither KuCoin's illustrated core results nor retrospectively inspected BTCUSDT 2024 months can establish Brooks V5 prospective OOS edge.

## Freeze the experiment before newly arriving data

`naseri_markets/brooks_prospective_forward_custody_stage21c_v1.py` exposes:
- `BrooksProspectivePlan`: exact SHA-256 of the frozen 359-file Brooks V5 manifest, **approved immutable Stage21B implementation** and fixed contract economics assumptions, BTCUSDT Binance USD-M 15m identity, precise future study start/end, fixed 60-bar warmup, maximum 96 newly observed bars per custody receipt, strict refusal to fill missing funding, stop-priority if the same OHLC candle crosses both stop and TP, and `paper_market_access=false`.
- `freeze_brooks_prospective_plan(...)`: validates the future start is at least 24 hours after operator registration and 7–90 days of observation, with a local operator-supplied clock within 5 minutes of claimed registration time, then creates canonical immutable JSON and SHA-256 receipt. **These local timestamps cannot prove the plan was genuinely registered at that moment.** SHA-256 proves only *content*, not pre-existing authorship or timing.
- `review_brooks_forward_candle_receipt(...)`: accepts strictly canonical original future 15m candle CSV in batches of 1–96 bars (operator-supplied, no network); rejects missing, duplicated, out-of-order, future unclosed/early-available, cross-window and malformed prices. Forces first batch to start at the predeclared study boundary; subsequent batches continue exactly where the cryptographically chained previous receipt ended. A newly appended source CSV's original SHA-256 is preserved alongside local observation time and previous receipt hash.
- Neither function evaluates a trade, opens a holdout, runs a broker, writes to an operational DB, pulls live data, starts a scheduler or sends Telegram.

## Mandatory independent steps *not* automated or claimed here

1. Before the study begins, an authorized operator must publish the plan hash into an independently timestamped, reviewable append-only channel, where witness public keys, timestamp and non-repudiation can later be independently verified. The current module DOES NOT verify such an external witness. GitHub commit dates or manually asserted timestamps alone are not a cryptographic proof.
2. An independent intake mechanism must capture **future** market events only after they have occurred and preserve source response bytes, signed time/transport evidence, outages and corrections. This module accepts local CSV and cannot prove the claimed source was Binance; a local hash chain is not a signed data feed.
3. Independent exchange contract/fee/funding/mark custody and validated Brooks ordertype/fill/exit semantics must be accepted before even a nonproduction connected PAPER activation.
4. A genuinely blind OOS evaluation requires a sufficient span and set of closed trades, safe data handling and no parameter changes, with a bounded risk policy/kill switch and separately approved release. No claimed PnL or OOS readiness is conferred here.
5. The protected `Publication Safety` and genuine GitHub Advanced Security CodeQL checks must PASS on the final exact commit. Prior stacked PR #306 passed 11 workflows, but Publication Safety FAILED because CodeQL was absent for that stacked branch. Do not forge, rename, skip or weaken the mandatory check.

## Usage (only after choosing your own actual future study dates)

In an isolated research-only environment with `MMT_NONPRODUCTION=1`, create a `BrooksProspectivePlan` that pins the approved Stage21B source blob digest, research economics contract SHA and an actual future study window (7–90 days). Call `freeze_brooks_prospective_plan(plan, operator_recorded_at_utc=datetime.now(UTC), operator_ack=True)`, then store its raw bytes and hash in a reviewable, independent custody register BEFORE the future start. The module does NOT publish the plan or independently confirm any witness.

After that future start, a separate authorized data collector could supply fully closed and source-pinned 15m candle CSVs. Call `review_brooks_forward_candle_receipt` with the immutable plan bytes/hash, the original CSV and UTC observed time; provide the previous immutable receipt for each successive chunk. Retain original bytes; do not overwrite old records. The output **always** declares independent timestamp, issuer signature, verified prospective OOS, worker execution, PAPER enablement, actual filled PnL and live authorization **false**.

## Tests and restrictions

Unit tests inject **fictional future 2027 timestamps and synthetic candles**. They verify fixed strategy SHA, future study horizon, timestamp readiness, continuity, missing bars, tampering, immutable chain links, no forged provider-authenticity status and refusal under Production. They cannot and must not be used as evidence of real 2027 results.

This branch is stacked on Draft PR #306, which is stacked on #305 and earlier Stage17–20 work. No merge with `main`, live server, Telegram, account, runner deployment, or Stage22 authorized.

**Status: STAGE21C_BROOKS_FUTURE_PROTOCOL_CODE_ONLY_EXTERNAL_PRECOMMIT_AND_DATA_NOT_YET_PRESENT.**
