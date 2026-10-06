# MARC v0.1 Backtest and Out-of-Sample Protocol

This protocol validates the already-frozen MARC R1 signal rules. It is a
research stage only. It cannot enable MARC runtime, publish Telegram signals, or
authorize exchange execution.

## Frozen strategy under test

- `MARC_R1_MA99_REGIME_RECLAIM`
- engine `marc-core-v0.1.0`
- rules `marc-r1-v0.1`
- configuration `marc-baseline-v0.1`
- SMA 7 / 25 / 99 and Wilder ATR(14)
- 15m and 30m only

No strategy parameter is optimized by this protocol.

## Dataset

The automated research job reads public **Binance USD-M Futures** 15m klines
from official **Binance Data Vision monthly archives** for:

- BTCUSDT
- ETHUSDT
- SOLUSDT
- BNBUSDT
- XRPUSDT

The fixed research range is 2022-01-01 through 2026-09-30 UTC. Four days of
pre-window candles are downloaded only as indicator warm-up.

Every monthly ZIP is verified against Binance's companion `.CHECKSUM` file
before parsing. The report records the number of verified archives, a SHA256
digest of the archive manifest, and SHA256 hashes of every normalized series.

30m candles are reconstructed deterministically from two complete,
UTC-aligned 15m candles.

## Fixed split

- Validation: 2022-01-01 <= entry < 2025-01-01
- Out-of-sample: 2025-01-01 <= entry < 2026-10-01

The OOS window is not used to tune MARC parameters.

## Execution assumptions

- signal analysis uses closed candles only;
- entry is the next candle open;
- one active position is allowed per symbol/timeframe stream;
- TP1 closes 25% at 1R;
- TP2 closes 25% at 2R;
- the remaining 50% becomes the Chandelier runner after TP2;
- Chandelier uses length 22 and Wilder ATR(22), multiplier 3;
- a newly computed Chandelier level is effective only from the next candle;
- the trailing stop never loosens beyond the initial stop;
- if stop and target are both touched inside the same candle, **stop wins**;
- an adverse gap through a stop fills at the candle open;
- remaining exposure at the fixed window boundary is closed at the last close.

This is intentionally conservative where intrabar ordering is unknowable from
15m/30m OHLC data.

## Costs

Two explicit transaction-cost scenarios are reported:

- base: 6 basis points per side;
- stress: 10 basis points per side.

The cost is applied once to the full entry notional and pro-rata to every exit
fill. Funding payments are not modeled in v0.1 and are listed as a limitation.

## Metrics

Each symbol/timeframe is reported independently, plus a pooled trade
distribution. The pooled view is **not** a capital-weighted portfolio backtest.

Metrics include:

- trade count;
- long/short count;
- win rate and Wilson 95% interval;
- expectancy in R and bootstrap 95% interval;
- profit factor;
- per-trade Sharpe;
- cumulative R;
- maximum drawdown in R;
- TP1/TP2 rates;
- holding bars;
- terminal-exit distribution;
- base-cost and stress-cost results.

## Research classification

The report can classify evidence as insufficient, not established, uncertain,
cost-sensitive, or promising. Even the strongest classification remains
research-only.

Every report contains:

`runtime_approval = DENIED_BACKTEST_ONLY`

A positive backtest therefore cannot register the MARC runtime engine or enable
VIP publication. Runtime integration requires a separate authorized stage after
review of the OOS evidence and known limitations.
