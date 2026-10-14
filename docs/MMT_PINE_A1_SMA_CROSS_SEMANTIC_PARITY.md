# PINE-A1 — bounded Pine-to-rule semantic port and offline trace parity

**Status: NONPRODUCTION research only. NOT general Pine Script conversion, NOT an interpreter and NOT TradingView-certified equivalence.**

The universal artifact intake already recognized the .pine suffix as an
untrusted artifact, but had no approved interpreter, Pine-to-Core
semantic rules or external TradingView oracle validation.

## Exact supported source (version 5 or 6)

~~~pine
//@version=5
indicator("SMA Cross", overlay=true)
fast = ta.sma(close, 2)
slow = ta.sma(close, 3)
longSignal = barstate.isconfirmed and ta.crossover(fast, slow)
shortSignal = barstate.isconfirmed and ta.crossunder(fast, slow)
~~~

Only the title and two integer lengths may vary: 2 <= fast < slow <= 200.
UTF-8 source must be <=16KiB and pinned with independent lowercase SHA-256.
The parser rejects EVERY other statement instead of silently converting
or approximating it. These rules are not a general Pine converter.
No strategy(), request.security(), alert, plotshape, custom expressions,
MTF, input.int, EMA, unconfirmed bars, arrays or repainting shortcuts.

The parser returns a frozen, NONEXECUTABLE PineSmaCrossRule IR, rather
than translated executable Python or compiled strategy. A source name
or same-host SHA256 never proves authorship or semantic safety.

## Deterministic closed-bar semantics

The reviewer reads only already-validated, hash-pinned DATA-A1 CSV/
Parquet REPLAY CLOSED_CANDLE packets. It uses Decimal closes and
cross-multiplied integer SMA window sizes to avoid rounding:
- Cross up when FAST > SLOW at current close AND FAST <= SLOW at previous.
- Cross down when FAST < SLOW at current close AND FAST >= SLOW at previous.
- First SLOW bars output NONE (previous slow average unavailable).
- Signals are observations, NOT orders or a PAPER trading strategy.

Both source and oracle must contain all contiguous candle timestamps,
never merely cherry-picked positive examples. Exactly one oracle row
is required per market bar, including all warmup and NONE rows.
Only strictly increasing timestamps with explicit UTC offsets qualify.

## Operator-provided full-bar oracle

The operator provides a bounded, SHA256-pinned UTF-8 CSV of exactly
two ordered columns:

~~~csv
close_at,signal
2026-10-13T10:15:00Z,NONE
2026-10-13T10:30:00Z,NONE
~~~

Allowed signal values: NONE, LONG, SHORT. Max 10000 bars and 1MiB
reference file. The report includes source, history and oracle SHA256,
matching/mismatching bar totals, count of LONG/SHORT marks, timestamp
of first mismatch, and domain-separated SHA256 trace digest.

**A local trace match does NOT prove genuine TradingView equivalence.**
The oracle may have been handwritten or forged. Actual TradingView
source, chart state, market bar feed, lookahead/repaint behavior,
closed-bar calc timing, time zone, session calendars, exchange instrument
adjustments, and output export must be authenticated independently.

Pine strategy backtesting includes process_orders_on_close, fills,
pyramiding, slippage, costs and broker emulation. None of those are
implemented here. Thus neither Pine strategy PnL nor entry-order
equivalence is claimed by this simple indicator rule.

## Safety and acceptance

- Explicit MMT_NONPRODUCTION=1 and operator_ack=True required.
- MMT_PRODUCTION=1 is denied.
- No TradingView login/browser access, Pine interpreter, generated
  runnable code, subprocess, broker API, worker/container, database,
  Telegram or execution authorization.
- No raw source or market bytes included in the report.
- Every source-authentication, TradingView equivalence, PAPER strategy
  execution, order, telegram, Worker or quarantine-release field FALSE.
- RUNTIME-A6 unconditional launch fence unchanged.

The new CI checks actual synthetic CSV and real multi-group Parquet
data against a **separately hand-authored reference trace**, and tests
bad syntax, forged oracle SHA, altered market data, timestamp drift,
mismatched trace, missing rows, malformed CSV, production mode and
no-subprocess/no-network behavior. Green tests validate this restricted
subset only, not actual TradingView-generated evidence.

**Verdict: PINE_A1_NARROW_SMA_CROSS_RULE_AND_OFFLINE_TRACE_REVIEW_ONLY.**
