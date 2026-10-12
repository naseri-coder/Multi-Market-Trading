# Stage 21F — Independent-code evidence gate, Funding reproduction and honest coverage

**Status: optional nonproduction research. All strategy profitability and LIVE/public-release verdicts remain BLOCKED.** This stage is intentionally an **independent read-only verifier**, not an independent signed market-data source. No server or account access, background polling, real orders, Telegram messages, funding DB edits or automatic capture.

## Official public source verification

- [KuCoin public Funding history](https://www.kucoin.com/docs-new/rest/futures-trading/funding-fees/get-public-funding-history) supplies settlement events in a requested window, not a guaranteed complete settlement schedule. No response field proves all expected settlements were present, including when an empty response was returned.
- [KuCoin current Mark price](https://www.kucoin.com/docs-new/rest/futures-trading/market-data/get-mark-price) supplies **current** price and index only. It cannot establish historical Mark prices within the Stage21C candle intervals or historical liquidation triggers.
- Provider terms, regional eligibility, account margin tiers, mark-price-at-settlement, fills and broker funding statement were NOT independently attested. Same-provider recapture is a cross-observation consistency test, not a different independent provider.

## Exactly two operator actions, separate times

Stage21F requires a valid, already-sealed Stage21C file bundle and Stage21E Mark/Funding annex. The original files and PAPER database are verified read-only using the existing Stage21C/D/E parsers and SHA256 evidence.

An optional operator explicitly authorizes **exactly TWO additional, bounded public Funding history GETs** for the same symbols and exact windows that were originally captured. It compares the *semantic settlement events* (symbol, timestamp and exact rate) after strict parsing. It rejects nonmatching, missing, conflicting and malformed responses rather than silently merging or filling gaps; re-fetching is never scheduled automatically. Exact matching outputs new immutable-by-convention 0600 `stage21f_funding_*.json` bytes and a digest-linked `stage21f_recheck.json`; any interrupted/partial commit is unusable until inspected manually.

```sh
MMT_NONPRODUCTION=1 python -m naseri_markets.market_evidence_gate_cli_stage21f_v1 corroborate \
  --bundle-dir "$HOME/mmt-research/bundle-001" \
  --ack-two-public-gets
```

To run the **zero-network** independent-code verifier on the bundle:

```sh
MMT_NONPRODUCTION=1 python -m naseri_markets.market_evidence_gate_cli_stage21f_v1 audit \
  --bundle-dir "$HOME/mmt-research/bundle-001" \
  --paper-db "$HOME/mmt-research/paper-001/paper.sqlite" \
  --ack-offline-readonly
```

`--paper-db` is optional and read-only. The audit checks local Stage21D per-contract reservation and PnL consistency and the Stage21E retrospective funding scenario, and never modifies those source journals. Without a second funding capture the auditor refuses by default; `--permit-no-recheck` permits an honest **NOT_TESTED** diagnostic report without a false comparison PASS.

## Three separate verdict dimensions

1. **Local data integrity:** verified format, exact symbol/timeframe identity, chronological ranges and SHA256 across Stage21C→21E→21F. May return `PASS_LOCAL_ONLY`, but a SHA256 checksum does not prove KuCoin signed the data or that all API results were returned.
2. **Funding reproducibility:** `MATCHED_SAME_PROVIDER_NOT_SOURCE_INDEPENDENT` only for an exact second observation. A completely matching, empty history still has `funding_event_completeness=UNKNOWN_NOT_ZERO`, because payment schedule and pagination completeness were not attested.
3. **Performance and liquidation eligibility:** always `BLOCKED_MISSING_MARK_FUNDING_EXECUTION_PROOF`; `historical_mark_coverage=ABSENT_CURRENT_MARK_ONLY`; `historical_liquidation_risk_verified=false`; `strategy_profitability_verified=false`; `publication_authorized=false`; `live_trading_authorized=false`. No sample count, positive PAPER return or green GitHub checks can override the missing venue evidence. Actual funding may be payable/receivable even where an API window appears empty.

The Stage21F verifier does not assert new, unverified claim that history source is immutable. Public response may evolve or differ; any conflict is an explicit RECHECK refusal requiring an operator-reviewed cause. No unseen candles, stop-loss outcomes or fee assumptions are filled in to make a strategy pass.

## Tests and remaining acceptance

Dedicated isolated-Python-3.12 CI uses only injected, official-format provider fixtures: two distinct symbols/times, exact second-fetch comparison, no-forward data, response corruption, conflicting funding rates, read-only Stage21D ledger audit, no-release verdict, missing acknowledgment, production refusal, legacy cross-stage tests and installed-wheel execution.

**For meaningful actual futures acceptance**, obtain permitted time-stamped historical Mark evidence, source-validated funding interval schedule and complete funding events, independently verified contract margin tier/liquidation handling, an approved nonproduction account's funding/fill records, and a statistically sufficient out-of-sample realized-performance record. Until these separate future approvals, do not enable any LIVE/DEMO broker operation, real Telegram publication, outside strategy core, production migration or public release.

**The owner-only NY First-Reversal and the running production bot remain untouched.**
