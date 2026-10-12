# Stage 21E — Public Funding settlements, current Mark and PAPER liquidation-risk scenarios

**Status: opt-in, nonproduction, read-only public research with an offline analytical annex.** This does not enable real orders, Telegram messages, broker accounts or a background feed. No actual public HTTPS GET is made by CI; injected mock transports are always distinguished from operator-authorized public retrieval.

## Official input contracts

- [KuCoin current Mark price](https://www.kucoin.com/docs-new/rest/futures-trading/market-data/get-mark-price): fixed public `GET /api/v1/mark-price/{symbol}/current`, contains `timePoint`, `value`, and `indexPrice`. It is **a current snapshot**, *not* historical bars or a mark series corresponding to Stage21C historical Klines.
- [KuCoin public Funding history](https://www.kucoin.com/docs-new/rest/futures-trading/funding-fees/get-public-funding-history): fixed public `GET /api/v1/contract/funding-rates?symbol=...&from=...&to=...`, with `timepoint` and `fundingRate`. May be empty or incomplete; the code never infers that missing events mean zero funding or that all settlements are provided.
- [KuCoin liquidation mechanism](https://www.kucoin.com/support/26694703491737): liquidation varies with isolated/cross margin, account equity, maintenance margin tiers, liquidation fee, Mark price and other venue state. We **do not** know these exchange/account variables and do not compute an official liquidation price.

Public fixed URLs only; no private funding, position, leverage, margin, order or trading route. Four explicit GETs for two symbols and no polling, pagination or retry. Time bounds, JSON duplicate keys, native symbols, nonfinite values, 30-second current Mark freshness, funding event duplicates/range, bytes and response semantics are fail-closed.

## Operator workflow (two independent invocations)

First produce a **valid, already sealed** Stage21C forward-capture bundle by the previous documented ARM→SEAL steps. The bundle must be in an owner-private directory and its original captured response digests intact.

Capture the supplemental **current** Mark and historical settled Funding responses (four calls total) from the official fixed host:

```sh
MMT_NONPRODUCTION=1 python -m naseri_markets.public_funding_mark_cli_stage21e_v1 capture \
  --bundle-dir "$HOME/mmt-research/bundle-001" \
  --ack-public-readonly-get
```

Run separate local analysis with **no network I/O**:

```sh
MMT_NONPRODUCTION=1 python -m naseri_markets.public_funding_mark_cli_stage21e_v1 analyze \
  --bundle-dir "$HOME/mmt-research/bundle-001" \
  --ack-offline-research
```

Optionally pass `--paper-db "$HOME/mmt-research/paper-001/paper.sqlite"` to perform a read-only retrospective **entry-notional funding sensitivity** on the same immutable Stage21D ledger. The ledger is checked using the existing Stage21D audited contract risk/exit statements. If there are partial or nonterminal positions, the funding estimate is `UNKNOWN_OPEN_OR_PARTIAL_POSITION`; no invented zero fees or imaginary closure. The calculated funding proxy assumes notional at trade entry rather than mark at settlement and **never changes** the Stage3/9 actual modeled stored PnL.

Optional stress controls are **explicit assumptions**: `--mark-basis-limit 0.02`, `--assumed-leverage 5`, `--assumed-maintenance-rate 0.01`. Output includes the Mark/Index dislocation fraction and one hypothetical isolated 1-lot margin buffer per instrument. These values are sensitivity illustrations only; the report **always** sets `liquidation_price=null`, `historical_margin_backtest_credible=false`, `funding_history_complete=false`, and `live_trading_authorized=false`. It never represents a current-Mark observation as a historical one.

## Strict evidence boundary

`stage21e.json` is written only after four strictly validated public-format responses; it binds the prior Stage21C sealed manifest, source digests, observation time, exact symbol identity and public/injected source mode. Only new 0600 regular files are created with O_EXCL and O_NOFOLLOW; on partial write failure the annex is not reusable, requiring manual reconciliation. Existing Stage21D PAPER SQL databases remain untouched.

Local SHA256 proves **local content identity**, not a signed KuCoin statement or an independently attested UTC source timestamp. No websocket, exchange order book, real historical Mark series, settlement-time Mark, verified Funding history completeness, account maintenance tiers, cross-margin positions, liquidation waterfall or actual broker fills are available here. The analytical report should **never** be used to certify strategy edge or approve LIVE.

## CI and release fences

Dedicated GitHub Actions runs negative and positive offline fixtures: public data schema, source provenance, stale/future Mark, missing/duplicated Funding, tampering, one-shot capture, two-symbol Stage21C→21D PAPER→21E read-only scenario, and installed wheel. Stage19/20/21B/21C/21D regression and legacy publication safety must also pass. No real network calls in tests.

**No production host, server, exchange credentials, Telegram, NY First-Reversal, or v0.3.2 runtime change.** Release remains `PRODUCT_NOT_READY_FOR_PUBLIC_OR_LIVE_RELEASE`.

### Remaining next-gate work

To make liquidation and funding economically attestable rather than advisory: independently verify KuCoin market-data access under provider terms, obtain bounded historical settlement-time Mark evidence, verify funding-pagination completeness, model actual per-symbol margin tiers and cross-margin position exposure, and validate against real provider account statements using a separately authorized nonproduction test identity. Do not infer a verified liquidation price from a simple leverage/MMR assumption.
