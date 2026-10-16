# MMT-R24 — Sequential Forward Candle Custody and Gap Ledgers

**Research-only candidate, no network used to develop this stage; no automatic execution, PAPER, orders, main merge or production changes.**

## Frozen study baseline

- Signed original FreeTSA plan SHA256: c557e8792ff7f097ee483903e2e6702c622a20f3975af898ee9aca7e257ad94d.
- Original signed timestamp response SHA256: 2e36862213d0f32cffadf161b3edae2610b03eef32f49e3b368253b49f83cf75.
- Oct 16 2026 01:36 UTC genuine signed plan, original study Oct 20 00:00 through Nov 3 00:00 UTC.
- BTCUSDT Binance USD-M, 15m candles, frozen Brooks V5. Neither strategy source nor fee assumptions nor signed timestamp changed in R24.

## Implementation

Module: naseri_markets/brooks_sequential_forward_custody_mmt_r24_v1.py

The operator supplies ALL prior accepted source folders in chronological order, beginning with the one actual first-batch folder produced by Stage21G/R23. Before making any public request, R24 walks every prior folder and refuses missing/reordered/duplicate/linked/unexpected/failed files. It reopens the original provider JSON body and re-runs exact canonical twelve-column Stage21F OHLCV normalization and full original RFC3161 signed plan and Stage21C receipt-chain validation, checks each original body SHA256, canonical CSV bytes, receipt bytes, original claimed HTTPS Date, status, TLS certificate digest, local capture window and transport receipt. It refuses any tampering or discontinuous 15m rows.

Each continuation adds stage24-previous-batch-link.json to bind all original files of the preceding batch, plus the prior inner and outer receipt digests. This is **local hash evidence**, not an independently signed exchange market dataset or reliable third-party UTC receiver clock. If a malicious actor coherently replaces ALL local evidence, only an independently entrusted external receipt could detect it.

The collector reuses exactly the existing single direct-HTTPS, no-proxy, no-secrets, CA-verified, no-redirect, no-retry Stage21G GET and source admission. No second parallel HTTP implementation. Only the next contiguous 1, 4, 16, 32 or 96 closed bars can be accepted under explicit new manual authorization. In general, the next complete source response must arrive between five seconds and one hour after the chosen last candle closes.

A missed response window creates attempt.json plus gap-ledger.json **without any network call**. The incomplete span cannot be skipped or backdated in the continuous prospective receipt chain. A failed attempt yields attempt.json, any actually obtained original response bytes and failure-ledger.json, with zero automatic retries. Such failures do not prove any outage occurred at Binance, because local clock, networking, region or device factors remain possible.

A maximum 128 accepted prior batches is supported; 96-bar daily batches over 14 days fit, while continuous 1-bar captures for the whole 14-day study do not. No background or scheduled job is created.

## Example Termux operator actions AFTER FIRST GENUINE R23 batch exists

Research code branch: feature/mmt-r24-sequential-forward-custody-and-gap-ledger-v1

First check the complete prior chain, offline:

    cd "$HOME/mmt-r24-source"
    MMT_NONPRODUCTION=1 MMT_PRODUCTION=0 \
    python scripts/mmt_r24_manual_sequential_forward_custody_v1.py \
      --ack-research-only \
      --witness-dir "$HOME/mmt-r23-research/original-witness" \
      --prior-batch-dir "$HOME/mmt-r23-research/first-real-capture-20261020" \
      inspect --bars 4

Only if the preceding first source batch contains exactly the first Oct20 00:00-00:15 UTC candle, the next four candles close at 01:15 UTC. A manually authorized ONE public read-only GET for this second batch may be performed from **Oct20 01:15:05 to Oct20 02:15:00 UTC**, never before or after:

    cd "$HOME/mmt-r24-source"
    MMT_NONPRODUCTION=1 MMT_PRODUCTION=0 \
    python scripts/mmt_r24_manual_sequential_forward_custody_v1.py \
      --ack-research-only \
      --witness-dir "$HOME/mmt-r23-research/original-witness" \
      --prior-batch-dir "$HOME/mmt-r23-research/first-real-capture-20261020" \
      capture --bars 4 \
      --output-dir "$HOME/mmt-r23-research/next-four-real-candles" \
      --confirm-one-readonly-public-get I_APPROVE_ONE_NEXT_READONLY_BINANCE_GET

For a third batch, repeat --prior-batch-dir for both previous *successful* folders oldest first. Never pass a failure/gap-ledger folder or remove the original raw body. Do not retry automatically, and never silently treat a late backfill as a prospective first observation.

## Provenance and release boundaries

The tests use **synthetic** 2026 future OHLCV fixtures and fake external TSA tokens strictly scoped to tests. The genuine FreeTSA RSA/X.509 witness was already reverified independently in R23 (original CI run Oct16) and is rechecked when actual imported source files are admitted. No real future Oct20 Binance candle, signed origin from Binance, timestamped first receiver observation, true OOS trading score, fee/funding settlement or actual executed position has been collected or claimed.

R24 is stacked on R23 Draft PR #315; all dependent PRs remain unmerged. The read-only CodeQL main-target audit PR #309 must **NEVER BE MERGED**. Full public test corpus/Ruff, genuine GitHub Advanced Security CodeQL and unmodified Publication Safety must all pass on the final exact commit.

**Acceptance target: MMT_R24_CONTIGUOUS_RAW_BATCH_REPLAY_AND_MISSED_WINDOW_LEDGER_CODE_PASS — REAL_PROSPECTIVE_SOURCE_PENDING.**
