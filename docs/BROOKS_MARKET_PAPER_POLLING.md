# Brooks V5 — Opt-in Binance USD-M CLOSED OHLCV → PAPER periodic analysis

**Scope**: public Multi Market Trading platform, development/operator-invoked only.
This stage does NOT deploy, restart or alter any production bot, Postgres
database, broker, chat, publisher, historical Brooks engine or private NYFR.
No signals are sent to Telegram channels. A public HTTPS market-data source is
not a private authenticated trading execution feed; its OHLCV is verified for
shape, continuity, UTC timing, completeness, freshness and plausible prices,
not independently exchange-signed.

## Data path

1. An explicit operator uses the existing **private development admin panel**
   `/engines` to request enablement of the **public**
   `brooks_price_action` built-in, set its timeframe to one of
   `1m,5m,15m,1h,4h,1d`, scope `crypto` or `all`, and environment
   `PAPER`. Initial state is DISABLED/OFF. This is independent of channel
   publication; requesting publication is NOT enough to authorize sending.
2. The separate, manually started `naseri-brooks-market` CLI polls the
   fixed read-only Binance USD-M public endpoint
   `https://fapi.binance.com/fapi/v1/klines` with a strict USDT-symbol
   allowlist. It requires no exchange key or Telegram token. It uses TLS,
   bounded response/timeouts, denies redirects/proxies and rejects malformed
   responses. Network errors stop the poller closed, not fabricate prices.
3. The adapter discards the unclosed current candle (Binance's inclusive
   close timestamp is converted to the Brooks exclusive candle end),
   requires **60–256** finalized, ordered, contiguous, bounded OHLCV bars,
   verifies decimal geometry, and refuses stale/future timestamps. Uses the
   existing `parse_candle_replay` strict validator. Source and timeframe
   identity are explicit; no time travel or partial-bar repainting.
4. The already-verified `replay_once` runs the **actual SHA-frozen public
   BrooksTrilogyFullCoreEngine V5** in an isolated child interpreter, with
   configuration revision fences before/after evaluation and transactional
   final permission revalidation. Results are real `NO_SIGNAL` or a PAPER
   SignalIntent. The same `brooks_replay_scans` + A7 PAPER intent ledger
   enforces idempotency on a repeated closed window.
5. CLI JSON output identifies the actual data path as
   `AUTOMATIC_MARKET_CLOSED_CANDLE_PAPER`, rather than claiming the source
   was a historic offline file. The internal validated input still uses
   `origin=replay` because it is the existing V5 worker's *input schema*.
6. An explicitly invoked `--loop` repeats at 30–3600-second bounded
   cadence and supports a finite `--max-cycles`. It stops on first
   transport, quality, configuration or engine failure. It is not launched
   by installing the wheel, importing the module or opening the bot.
   Repeating an unchanged closed candle creates no duplicate scan/signal.

**Important:** The development admin panel saves engine enablement, PAPER,
market and timeframe preferences. It does not start/stop OS-level processes:
an operator starts and stops the separate poller; disabling Brooks in the
panel prevents further analysis/persistence. The admin panel reports the
genuine scan/PAPER history already stored in the development SQLite ledger.

## Local operator commands (never on a production host)

From a trusted development checkout with project dependencies installed,
an explicit separate private `dev-state` directory and a SHA-frozen
`production_source` tree:

```bash
# Configure Brooks ON + PAPER + crypto/all + selected timeframe in the
# development /engines Telegram admin chat, not the production bot.

# One verified closed-candle evaluation (read-only public market HTTPS):
naseri-brooks-market --once \
  --state-dir /absolute/dev-state \
  --legacy-source /absolute/checkout/production_source \
  --symbol BTCUSDT --bars 128 --ack-nonproduction-paper

# Optional operator-started periodic poller, stops after three cycles:
naseri-brooks-market --loop --poll-seconds 60 --max-cycles 3 \
  --state-dir /absolute/dev-state \
  --legacy-source /absolute/checkout/production_source \
  --symbol BTCUSDT --bars 128 --ack-nonproduction-paper
```

`--loop --max-cycles 0` runs until operator interruption or failure.
It creates no daemon/service, container, Cron job, exchange order or
Telegram publisher. Limit to one operator-controlled poller per
symbol/timeframe/state directory; the underlying journal is idempotent,
but independent processes can waste API quota. Feed access is subject
to Binance regional availability, rate limiting and service terms.

## Safety and acceptance

- No modifications to `production_source/`, frozen SHA256SUMS, pricing
  policy, signal thresholds or legacy bot startup.
- No NY First-Reversal private source/assets in public code, package or CI.
- No forward publisher; `requested_publication` is *not* a send permission;
  `effective_publication=false`, `delivery_mode=DISABLED`.
- Network blocked, stale candle, unclosed candle, candle gap, unsafe decimal,
  wrong market/scope/timeframe, disabled PAPER or mid-fetch configuration
  change = refuse without a committed new signal.
- `tests/unit/test_brooks_market_feed.py` uses deterministic **mocked HTTP
  transport** and one real frozen V5 worker with fixtures, not live exchange
  downloads or evidence of profitability.
- New CI workflow verifies the new unit tests, existing offline replay,
  release preflight, pinned manifest, built wheel command and publication
  safety. No CI step sends a Telegram message or contacts Binance.

This is a **nonproduction integration candidate**, not an assertion that
the operational bot has an active live feed or that live signal publication
is authorized.
