# MMT-R29 — Original-Source Brooks Manual Shadow Decisions

**Draft only. Stacked on R28 PR #321; NOT main. No server, live orders, Telegram, connected PAPER, network or scheduler.**

## Temporal scientific gate

The real, original FreeTSA witnessed prospective BTCUSDT Binance USD-M 15m plan is SHA256 c557e8792ff7f097ee483903e2e6702c622a20f3975af898ee9aca7e257ad94d, and covers Oct 20 through Nov 3, 2026 UTC. On Oct 16, prospective candles do not yet exist. First qualifying real-origin shadow decision requires the first **60 original, fully closed, R24-verified 15m bars**, whose earliest close is **2026-10-20 15:00 UTC**. Synthetic/2024 historical bytes must never be relabeled as genuine prospective OOS results.

## R29 implementation

- naseri_markets/brooks_future_shadow_paper_mmt_r29_v1.py takes the **complete** saved original Stage21G/R24 source batch directory sequence and original fixed R23 witness; calls genuine R24/Stage21F authenticated-plan/full local original-byte revalidation and independently checks contiguous CSV chronology.
- Every one-shot decision starts at bar index 60, then strictly 61, 62, etc. A canonical, SHA256-chained previous receipt for the same exact original data prefix is required. That local hash is not an independent time witness, authenticated venue feed or tamper-proof archive.
- The existing frozen Stage15/Brooks V5 worker receives only data CLOSED before or at the current decision cutoff. No future candle enters the worker. Original 359-file source manifest, internal snapshot and rule evidence are checked.
- The output contains an inert research decision, evidence digests and explicitly false flags for real sends, externally authenticated data, fills, verified PnL, connected PAPER, LIVE or independently proven edge.
- Outputs can be saved as exclusive private 0600 files in an existing 0700 directory, with no overwrite.
- scripts/mmt_r29_manual_future_shadow.py is an explicitly approved *manual*, one-bar Android/Termux CLI, not a scheduled runner or downloader.
- tests/unit/test_mmt_r29_real_source_shadow_paper_v1.py uses FAKE custody/worker fixtures to test closed-bar/causality, index sequence, tamper/future refusal, production fence and private append-only receipts. Test fixtures do not certify real-source operation.

## Manual operator invocation (only after the actual future source exists)

Use a disposable checkout of the stacked Draft branch and valid original R23 witness / saved R24 source folders. These are **example paths, not claims that these files exist**.

    export MMT_NONPRODUCTION=1
    unset MMT_PRODUCTION
    mkdir -m 700 -p "$HOME/mmt-r29-shadow-receipts"
    python -m scripts.mmt_r29_manual_future_shadow \
      --witness-dir "$HOME/mmt-witness/original" \
      --batch-dir "$HOME/mmt-original-batch01" \
      --frozen-source "$PWD/production_source" \
      --decision-bar-index 60 \
      --output-dir "$HOME/mmt-r29-shadow-receipts" \
      --ack-nonproduction-no-order

If the source was captured across more than one batch, supply --batch-dir once for EACH saved folder in oldest-to-newest order. To evaluate bar 61, explicitly supply --decision-bar-index 61 and --previous-receipt pointing to the exact private r29-shadow-bar-0060.json. Continue one sealed bar at a time. No automatic reattempt, polling or exchange request occurs on invocation. Do not use R29 to collect any data before the signed R23 study begins.

## Blockers and acceptance

1. Real after-Oct20 R24-authenticated local source still unavailable on Oct16; prospective results must stay pending.
2. No independently authenticated market provider signature / independently attested capture clock; externally witnessed plan is not a signature on returned candle prices.
3. Manual per-bar journaling is implemented but unattended multi-day collection, automated stable metrics, restart fault injection and comprehensive chronological tests are **not** complete.
4. No modeled realized futures PnL: account fee tier, Mark/funding settlements, slippage and fills are not certified; R27 arithmetic is modeled separately, not executed orders.
5. Full checkout pytest, Ruff, genuine independent CodeQL and Publication Safety and real frozen worker smoke are not yet run on final SHA. No passing outcomes may be inferred from synthetic unit tests alone.
6. Stage R30–R33 remains unopened: no order routing, connected PAPER, Telegram sending, production installation or LIVE authorization.

**Provisional R29 status:** MMT_R29_MANUAL_SHADOW_IMPLEMENTED_NOT_OOS_ACCEPTED.
