# Stage 18 — USD-M Futures Economics Evidence Reconciliation (Research Only)

**Implementation state:** NONPRODUCTION CODE + SYNTHETIC RESEARCH TESTS. NO REAL-FUNDING/MARK/ORDER-BOOK DATA CLAIMS.

**Dependency:** Stage17 draft PR #300 / branch `feature/stage17-authentic-monthly-market-data-custody-v1`, exact starting HEAD `7042ea365f7ada922fbce49b4880994096d17299`. Stage17 REAL-DATA custody is unresolved; do not merge this stage into main until Stage17's data gate and independent code review have passed.

## What Stage18 adds and what it reuses

The existing Stage16 module `futures_economic_scenario_stage16_v1.py` already computes explicit USDT-linear long/short cashflow from Decimal price, size, model taker fee/slippage, and an operator-supplied list of signed funding rate/mark events. It is not an exchange-certified fee engine. Stage18 **does not duplicate or rewrite that accounting model**; it wraps it in a stricter evidence/coverage and robustness gate.

New module `futures_economics_evidence_stage18_v1.py`:

1. Requires a complete `Stage17Capture` plus the JSON quality report produced by Stage17's file-backed, Stage12-verified archive acquisition; exact ZIP/CHECKSUM/canonical CSV/receipt SHA lineage is checked, and **the Stage16 raw ZIP parser is rerun**.
2. Requires SHA256-pinned operator-supplied *claimed* USD-M instrument/fee/margin metadata in the existing Stage16 exact schema. Metadata is not independently authenticated.
3. Requires two separately SHA256-pinned **normalized** CSV inputs. A prior declared funding-schedule inventory (`funding_time_utc`) must exactly match the full funding and mark rows (`funding_time_utc,funding_rate,mark_price`) in strictly increasing UTC chronology, with positive marks and bounded signed rates. Missing event, duplicate time, extra row or checksum drift refuses instead of silently inserting zero funding.
4. Accepts 1–16 ordered, nonoverlapping, entirely hypothetical scenario trades bounded to the actual historical candle-month window. Entries and exits must use UTC 15m boundaries; cost and contract constraints remain enforced by the **original Stage16 model**. These prices are NOT historical order fills and are not derived from Brooks signal execution.
5. Explicitly requires claimed isolated collateral to exceed modeled initial-margin plus a conservative maintenance reserve proxy, with max research leverage 20x. This is a **sanity refusal only**, not a real exchange tiered maintenance margin, mark liquidation or insurance model.
6. Runs exactly four predetermined cashflow cases per scenario: baseline, doubled taker-fee, doubled adverse slippage, and both doubled. Enforces stress net return cannot improve relative to the baseline. Reports signed funding, two taker fees, adverse slippage, net USDT and model evidence fingerprints. **No parameter tuning to fit profit**.
7. Always returns false for independent provider authentication, independent funding schedule completeness, historical mark authenticity, effective account fee tier, order book/impact verification, actual liquidation model, genuine Brooks trade attribution, tested profitability and production authorization.

## Required normalized evidence schemas

Funding schedule input: ASCII CSV with exactly one header column and strictly increasing event times:

```csv
funding_time_utc
2024-01-01T08:00:00Z
2024-01-01T16:00:00Z
```

Funding/Mark input: ASCII CSV with **exactly** the same event times in the same order:

```csv
funding_time_utc,funding_rate,mark_price
2024-01-01T08:00:00Z,0.0001,100
2024-01-01T16:00:00Z,-0.0002,101
```

These rows are illustrative **synthetic examples**. They are NOT a complete month, authentic Binance funding, or indicative actual BTCUSDT rates. A real importer must independently establish historical funding schedule and observed mark prices from legitimate primary sources, freeze the expected schedule before modeling, and preserve source revision, raw responses, SHA256 and a trusted acquisition clock. Merely matching two user-provided CSVs does **not** establish independent completeness.

## Acceptance and refusal criteria

- **Code / offline structure:** Stage17 full-month synthetic transport, existing Stage12 verification, real Stage16 cashflow library, Stage18 funding matching and static frozen stress scenarios; negative tests for malformed inputs, time-order, missing events, hash mismatch, stale Stage17 receipt, nonproduction fences, overlapping trades, bad leverage and inadequate reserve.
- **Actual source acceptance:** BLOCKED until genuine complete closed-month ZIP + CHECKSUM and independently tracked download/provenance are obtained and Stage17 receipt passes.
- **Futures evidence acceptance:** BLOCKED until historical source metadata, schedule, actual signed funding/mark, effective fee tier, liquidity/market depth and maintenance margin tiers are supported by original timestamped evidence and provenance review.
- **Trade-attributed economic backtest:** NOT RUN. Stage19 cannot label one of these user-created scenarios as a Brooks strategy fill.
- **OOS edge / paper / LIVE:** NOT AUTHORIZED.
- Production source/manifests, live account, Telegram, order router, database, private NYFR, original Brooks thresholds and release configuration remain unchanged.

## Test execution

All files are under the non-production `naseri_markets/`, `tests/unit/`, `docs/` paths. The existing public unit corpus workflow includes `tests/unit`; existing protected CI checks must pass on the exact HEAD. The tests stub Stage17 HTTPS acquisition and generate synthetic monthly ZIPs only; **their success does not count as empirical trading evidence**. Do not create additional network-reliant CI jobs, consume trade credentials, or fetch market data during CI.
