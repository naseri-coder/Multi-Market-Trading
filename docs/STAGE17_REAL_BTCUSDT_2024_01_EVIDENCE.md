# Stage 17 — Empirical Original Binance Vision BTCUSDT USD-M 15m Evidence

**Mode:** NONPRODUCTION HISTORICAL RESEARCH, not authenticated as-of-2024 truth, not a trading strategy backtest.

## Primary-origin download (actual bytes, not a fixture)

A disposable GitHub Actions runner successfully fetched the **official Binance Vision historical USD-M futures BTCUSDT January 2024 15m ZIP** and the sibling CHECKSUM directly over native verified HTTPS/TLS. Neither file was committed to the repository. The GitHub run `38800537476` passed an exact 12-column, complete-month UTC 15-minute grid and checksum self-consistency check.

- Official URL: https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/15m/BTCUSDT-15m-2024-01.zip
- CHECKSUM URL: https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/15m/BTCUSDT-15m-2024-01.zip.CHECKSUM
- Original ZIP SHA-256: `76953983fcd4cc35ac181c4a1c69d28cbb4ef8b983021aac84a111ea4e82ef69`
- Original CHECKSUM file SHA-256: `f645b8f4d035eda9f9198399415bb6361e8fcff4f3b91e2d5250936f0b20d73c`
- Original rows: **2976** consecutive, 15m UTC, after recognized header.
- Interval: 2024-01-01 00:00:00Z to 2024-02-01 00:00:00Z.
- Zero gaps, zero duplicate opens, zero invalid local OHLC/volume rows in independently repeated inspection.

## Full original project validation (not a synthetic test)

GitHub Actions run `38801424413` independently re-fetched the **same exact original ZIP digest**, checked out the actual project code and installed reviewed dependencies, then executed:

1. `import_stage17_vision_month_offline()` to validate the actual raw ZIP + CHECKSUM using the original Stage16 full-month parser. No exchange API keys or live broker connections.
2. `persist_research_capture()` on private isolated CI temporary storage, invoking the **original real Stage12 file-backed historical PIT quality gate**, not a mock.
3. `select_reviewed_brooks_window()` on first 72 contiguous real closed candles with preserved parent ZIP and full-month SHA lineage.

Result: **PASS**, genuine source bytes observed and locally validated.

- Full-month canonical DATA-A1 CSV SHA256: `f73afbda93a9c8e2fcde3eee15f1da31a05b5fa1c403ff1c975e858e88413ff2`
- Stage12 full-file PIT quality evidence SHA256: `0e44358bf86ec3f9b473afe426042398cb43754969ee06336aa9f8726d79a113`
- First 72 closed-bar canonical CSV SHA256: `16250da93ded88c74102d4114c775304c1673f1f52817cd9b5e0b4f6430b644a`
- Original source acquisition artifact id: `12004950855` (GitHub Actions short-lived, not long-term custody).

The original ZIP is also preserved in the output package supplied to the user, with the exact source checksum, normalized research CSV and Stage12 evidence receipt.

## Crucial acceptance limitations

- HTTPS plus companion `.CHECKSUM` demonstrates the data bytes received from a TLS-verified official endpoint and matches that endpoint's posted checksum. **No Binance-signed archival statement is available; publisher-authenticated digital signature=false.**
- The files reflect **the revision downloaded in October 2026**. They do not prove these exact bytes were the venue's published data during January 2024. Independent historical version attestation, correction history and trusted external as-of 2024 witness remain absent.
- Local GitHub runner timestamps are not an independent time-stamping authority. Full venue funding/mark, account fee-tier, liquidity, fill and tiered liquidation are NOT established by Klines.
- Any genuine Brooks V5 decision evaluation is a **decision trace only**, not a filled position, historical PnL, profitable edge or pristine prospective OOS. Subsequent Stage19 research must preserve the same limitations.
- Deployment, trade, Telegram send, paper-mode activation and production mutation remain **unauthorized**.
- Public dataset redistribution rights and applicable Binance public data terms require separate review before republication.

## CI policy

CodeQL from the repository **GitHub Advanced Security Default Setup** and the intact Publication Safety companion check both reported SUCCESS on the previously verified Stage17 head `c54ab9854cc42890e94bb8497e752bc42c69548a`. A conflicting custom advanced CodeQL workflow was removed after the scanner rejected it because Default Setup was already enabled; no security gate was weakened or skipped. Validate all checks again on the final PR HEAD before merging. This PR remains Draft and does not modify main.

**Status: REAL_2024_MONTH_DATA_ACQUIRED_AND_STAGE16_STAGE12_VALIDATED; ECONOMICS/OOS/PRODUCTION_GATES_STILL_CLOSED.**
