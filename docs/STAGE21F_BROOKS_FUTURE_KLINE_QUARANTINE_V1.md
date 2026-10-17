# Stage21F — Signed Brooks Future Study: Strict Raw Kline Quarantine

**Research-only, source-claimed, no market connector, no operational PAPER.**

## What is already genuinely attested

The immutable Brooks V5 experiment plan for Binance USD-M BTCUSDT 15m, 2026-10-20 00:00Z to 2026-11-03 00:00Z, was signed by external RFC3161 FreeTSA on 2026-10-16 at 01:36:00 UTC. Original canonical plan SHA256 `c557e8792ff7f097ee483903e2e6702c622a20f3975af898ee9aca7e257ad94d`; original signed response SHA256 `2e36862213d0f32cffadf161b3edae2610b03eef32f49e3b368253b49f83cf75`. Root and signer PEM hashes are fixed to the genuine Stage21E source digests. A second unapproved timestamp from later CI is **not** accepted.

This stage embeds only the allowed byte SHA pins; it does not duplicate original signed binary files in Git. The signed originals remain available as the Stage21E artifact `12019181218`, downloaded as `STAGE21E_REAL_EXTERNAL_BROOKS_RFC3161_PRECOMMIT.zip`. The exact plan bytes are at `docs/evidence/STAGE21E_BROOKS_ORIGINAL_EXTERNALLY_TIMESTAMPED_PLAN_20261016.json`.

## New self-contained admission policy

`stage21f_admit_future_kline_batch_to_quarantine` is a **pure, offline research-only validator**:

1. Reject Production, unacknowledged research, altered frozen plan, altered original timestamp token or changed pinned signer CA; run actual Stage21D OpenSSL RFC3161 signature / plan message-imprint verification on each admission.
2. Accept only manually supplied **original raw 12-field Binance USD-M Kline API JSON response bytes** of 1–96 complete 15-minute candles. Require a precise, reviewed declared request URL at the specified HTTPS Binance host and one exact deterministic query for the batch's start timestamp, fixed symbol and interval. No network is performed by this module.
3. Verify every opened/closed UTC millisecond on the exact 15m grid and original payload's OHLCV geometry. Forbid gaps, duplicates, out-of-order, wrong price types, malformed CSV, already-sealed candles outside the pinned 14-day study and timestamps declared before candle close plus a five-second data-availability allowance.
4. Convert to deterministic canonical seven-field candle CSV and reuse Stage21C append-only hash chain. Later batches must start exactly where the prior verified batch ended; a corrupted prior chain fails. Store original raw-body SHA256, normalized CSV SHA256, plan token SHA and linked receipt SHA.
5. ALWAYS mark provider origin, declared TLS status, observation time, orderbook fill quality, external custody and TSA-policy independence **UNVERIFIED**; assert no actual OOS conclusion, PAPER service, exchange order, PnL or Production modification. The API URL and HTTPS claim are *operator-supplied assertions*, not an independent source signature.

This quarantine service deliberately does NOT parse Funding/Mark settlements, compute capital PnL, start a bot, issue orders, enroll accounts, touch Telegram, schedule polling, or connect to the exchange. Research results remain blocked unless source origin and timing are corroborated independently and historical contract/fee/mark/slippage/fill economics are certified.

## Security limitations

- The timestamp proves **the plan existed by the signed time under the pinned FreeTSA trust chain**, not that subsequent market data are unmodified or that FreeTSA's independence/accreditation is audited.
- An operator can fabricate Klines and their claimed HTTP metadata offline; the validator preserves these claims but never upgrades them to independently attested source truth.
- A local observed UTC time may be spoofed. Hash chaining protects byte relationships, not receiver clock accuracy or remote feed authenticity.
- This parser recognizes the 12-field Binance Kline shape, not markPriceKlines, historical archive ZIP, fundingRate rows or real broker fill receipts.
- Data from the **scheduled future window have not been collected or verified as of 2026-10-16**. Unit tests use purely synthetic October-2026 fixture bars after the planned study start; test fixture timestamps must not be represented as real observations.
- Real forward OOS must follow a pre-approved statistical analysis with sufficient closed trades and an audit of corrections/venue outages. This code doesn't implement any OOS performance scoring.

## Acceptance and deployment

Stage21F is built as a three-file PR stacked on Draft Stage21E #310. Execute full Public Test Corpus, Ruff and genuine GitHub Advanced Security CodeQL / Publication Safety on the exact final SHA, preferably via the existing read-only main-target security audit PR #309. Do not merge that audit umbrella; do not merge stacked overlapping source files without a reconciliation review. No connected PAPER, production, main or Stage22 activation.

**Verdict: `STAGE21F_CANONICAL_RFC3161_GATED_LOCAL_RAW_FUTURE_KLINE_QUARANTINE_CODE_ONLY`.**
