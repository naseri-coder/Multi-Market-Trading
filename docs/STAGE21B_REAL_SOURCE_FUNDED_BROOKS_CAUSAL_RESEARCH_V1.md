# Stage21B — Source-joined Brooks V5 and Funding Research

**Status: RESEARCH ONLY. No connected PAPER, no broker orders, no verified performance or genuine prospective OOS.**

## Source custody and branch consolidation

This PR is stacked on Stage21A Draft PR #305, itself dependent on Draft #303, #302, #301 and #300. The Stage18 primary-source parser and its unchanged unit tests were carried across from separate Draft PR #304 because that branch is not an ancestor. Review and consolidate overlapping additions before any merge; never merge blindly.

Inputs to the new Stage21B adapter are an exact Stage17Capture with Stage12 quality report, the full January-2024 BTCUSDT original official trade-price archive, the actual original 8-hour funding ZIP + .CHECKSUM, actual original 15m Mark Price ZIP + .CHECKSUM, and a separately SHA-256-pinned operator-supplied USD-M economic assumption document. No file is silently fetched by the adapter.

## Strict time boundaries

Run genuine SHA-frozen V5 with only 60–224 historical CLOSED candles. Its output is verified through the unchanged Stage15 original geometry and source integrity checks. Only afterward is a distinct chronological window of 1–32 subsequent closed bars used by a hypothetical execution model. Stage16 validates full-month Kline chronology and original ZIP/CHECKSUM. Funding and mark are normalized by the exact Stage18 source parser; all 93 provider funding records (15 recorded offsets of +1..+3 milliseconds) and 2976 Mark OHLC bars are accounted for, except the Jan 1 midnight event intentionally excluded from modeled settlement because the preceding December mark candle is unavailable.

The bridge requires every expected 8-hour funding record in the WHOLE future horizon. An observed funding event after a modeled early stop/TP is checked for source completeness but NOT charged to an already closed hypothetical position. If an expected record is outside source coverage (including February 1 midnight), the evaluation refuses rather than creating a zero-funding assumption.

## Trade model, NOT trading performance

A genuine V5 LONG/SHORT is turned into a fixed hypothetical MARKET next-open assumption, requiring the subsequent opening price to be within 2% of the true original V5 entry anchor and respecting the original V5 stop and TP1. Same-bar stop/target collision uses STOP first (adverse), an opening gap through stop uses worse observed open, a gap through target never gets more than TP1, and a 32-bar horizon closes the model at the final observed close if neither exit occurs. Cashflow uses the existing Stage16 cost calculator with operator-defined lot, tick, taker fee and adverse slippage plus real provider historical funding rates and **prior-15-minute Mark candle close as a settlement-price proxy**. It does NOT reconstruct actual fills, queue, margin liquidation, volatility-dependent slippage or exact settlement mark.

Real ZIP SHA256 (transport byte custody only, not issuer signatures):
- Price: 76953983fcd4cc35ac181c4a1c69d28cbb4ef8b983021aac84a111ea4e82ef69
- Funding: 3e0d30870672aa8f0f937881056e3cfd55913ae5c780cd50b33f2763aa0ba58e
- Mark: aa64b8b765a37c28f11235f2f2ff59f8558b9ff62251315de8b789a22698c926

The data are RETROSPECTIVE and were obtained in October 2026. There is no independently timestamped January 2024 publication version or independent precommitted OOS holdout; an observed hypothetical result is not proof of edge.

## Operational fences

No network in the Python adapter; no order router, Telegram sender, registered PAPER bot, Production source/manifest/risk-threshold changes, server restart, database writes or main merge. A PASS in CI permits only the use of this research module. Fee tier, real execution, futures liquidation, prospective OOS and full security Publication Safety/CodeQL must be independently signed off before a separate operational PAPER launch.

**Verdict target:** STAGE21B_REAL_SOURCE_FUNDING_JOIN_RESEARCH_ONLY.
