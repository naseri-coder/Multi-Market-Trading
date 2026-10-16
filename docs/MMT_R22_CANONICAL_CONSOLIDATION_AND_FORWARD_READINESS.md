# MMT-R22 — Canonical Consolidation & Forward Readiness

**Status: NONPRODUCTION CANDIDATE — NOT MERGE-APPROVED, NOT LIVE/PAPER.**

## Audited history and canonical decisions

The base for this phase is Stage21G Draft PR #313 at commit 5e95cc9703468edcd838a1f12a16fec9ff48b334. No GitHub main or legacy crypto-price-action v0.3.2 runtime files were modified.

| PR | R22 decision and effect |
| --- | --- |
| #300 Stage17 authentic BTCUSDT 2024-01 source | Restored three missing historical lineage artifacts: two exact-content evidence documents and the original archive-acquisition workflow, converted to explicit manual-only for bounded rerun |
| #301 futures economics | Existing ancestor, still assumed economics |
| #302 genuine Brooks V5 causal decisions | Existing ancestor, decision does not prove exchange execution or real PnL |
| #303 preliminary walk-forward | Existing ancestor, not statistically proved prospective OOS |
| #304 real historical funding and Mark archive | Parser and unit tests already present in #306/#313 as exact matching Git blobs. Restored original real-source evidence document and research workflow, made manual-only. DO NOT blindly merge duplicate copies |
| #305 Stage21A trade lifecycle | Existing ancestor; modeled next-open trades only |
| #306 Stage21B three-source Brooks | Existing ancestor; precommitted bridge code must remain hash-identical |
| #307 Stage21C receipt chain | Existing ancestor; local hashes do not independently authenticate receiver clocks |
| #308 Stage21D RFC3161 verifier | Existing ancestor; signatures valid under pinned roots, trust-policy accreditation separate |
| #309 main-target CodeQL security audit | NEVER MERGE; audit only |
| #310 Stage21E genuinely timestamped study | Existing ancestor; original first token only, no reissue |
| #311 alternative Stage21F importer | SUPERSEDED CANDIDATE, not imported. Useful strict original JSON/Kline checks transferred to canonical #312, avoid two implementations |
| #312 canonical Stage21F source intake | CHOSEN: the only code path invoked by #313 Stage21G. Strengthened to validate all 12 original Kline fields including quote/taker volumes, integer trade counts, reserved field and OHLC geometry |
| #313 manual-only Stage21G first source acquisition | Direct parent; code ready, real future source NOT captured, no automatic collector |

## Source preservation

Three restored documentation files are byte-for-byte equal to their reviewed #300/#304 original Git blobs. The Stage18 source parser and unit tests in the #304 branch and the Stage21G descendant have identical Git blob IDs: 320286e540db84b4197d1e16b308ec5567b01b6f and 7bcd0e7337cddd3ba0cfa9dd7cb63c61c9c792e7 respectively. There is no reason to merge two independent copies of these files.

The original Stage17 and Stage18 remote archive workflows were absent from Stage21G ancestry. R22 restored them while replacing only automatic pull_request triggers with workflow_dispatch plus explicit positive operator approval. Their scientific historical source parsing logic is retained. A new commit must not cause unattended external downloads, persistent CI quota use or issuance of a new signed study.

## Frozen experiment remains unchanged

Original signed Stage21E plan SHA256: c557e8792ff7f097ee483903e2e6702c622a20f3975af898ee9aca7e257ad94d. Original external TSR SHA256: 2e36862213d0f32cffadf161b3edae2610b03eef32f49e3b368253b49f83cf75. UTC study: 2026-10-20 00:00 through 2026-11-03 00:00. The original pinned Stage21B bridge source is not modified. The second accidental notarized plan MUST NOT be used.

The canonical Stage21F parser now rejects all malformed Binance 12-column Klines rather than normalizing unvalidated trailing source values. This is a fail-closed schema fix after notarization, not a strategy parameter change. An independent research-methodology reviewer must determine whether the precommitted study protocol permits such safety tightening; success of CI is not external methodology approval.

## Readiness gates, 2026-10-16

| Gate | State |
| --- | --- |
| Canonical code and source evidence branch | R22 CANDIDATE; Draft, unmerged |
| Genuine Jan 2024 trade-price / funding / mark archives | HISTORICAL RESEARCH PASS; no publisher revision witness dated 2024 |
| Genuine external RFC3161 original plan | CRYPTOGRAPHIC PASS; independent TSA policy/accreditation not certified |
| First-window forward candle collector | CODE READY ONLY, NO REAL DATA |
| GitHub manual workflow availability | BLOCKED unless workflow is independently authorized onto default branch; no merge to enable |
| First closed BTCUSDT 15m bar | Scheduled for Oct20 00:15 UTC; earliest capture 00:15:05 UTC and latest response 01:15 UTC |
| Later consecutive candles, outages and exchange corrections | NOT IMPLEMENTED as end-to-end continuous custody |
| Binance-authenticated signed data, independent UTC receive time | MISSING; ordinary TLS and HTTP Date are not independent signing |
| Real fees/contract tier/fills and strategy trade lifecycle parity | MISSING |
| Independent, representative prospective OOS and trading-edge evidence | MISSING |
| Running PAPER / actual exchange orders / Telegram signals | NOT AUTHORIZED |
| Installation product v0.4 preview vs old v0.3.2 | NOT IN R22; original release gate remains closed |

## R23 operational handoff

Before Oct20: review the duplicate branches and all dependent Draft PRs. DO NOT MERGE #309, DO NOT mix competing #311/#312 implementations. Select an explicitly authorized isolated research-only capture lane compatible with the actual GitHub default-branch workflow restrictions, or a verified local Termux execution with original TSA binary evidence. Verify the original timestamp artifact (source Actions run 38835965013, original artifact 12019181218) is still available and pinned. Verify venue and account policy permissions. Review a source-correction and outage ledger. Do not deploy a background poller or attempt a blind retry. If the first opening window is missed, record the missed window and separately notarize a future replacement study; do not backfill while claiming prospective source custody.

## Acceptance criteria

R22 adds negative regression tests asserting the original historical evidence Git blob IDs, signed plan and frozen bridge SHA, safe manual-only historical workflows and exactly one canonical Stage21F importer. The enhanced parser refuses malformed quote and taker volumes, trade-count booleans and reserved source columns before committing a canonical receipt.

Final public pytest, Ruff NEW FINDINGS and authentic GitHub Advanced Security CodeQL and Publication Safety must pass on the final exact SHA. No CI result authorizes merging these Draft branches or creating PAPER/live orders. A product is not validated by a successful source-research suite.

**Target verdict: MMT_R22_SOURCE_CONSOLIDATED_CODE_PASS — TRUE_FORWARD_EXECUTION_AND_PRODUCT_RELEASE_BLOCKED.**
