# Real Brooks Full-Core V5 — OFFLINE REPLAY → PAPER → Telegram Admin Preview

**Scope:** new public Multi Market Trading product, locally triggered, strictly
nonproduction. This stage calls the **actual preserved Brooks engine** in
`production_source/app/modules/brooks_core/books_full_engine.py`.
It does **not** replace Brooks with a toy setup, simplified indicator,
LLM signal, test fixture, or new strategy.

**No production deployment; no live market feed; no broker orders; no
automatic Telegram channel publishing.** Owner-only NY First-Reversal
code remains OUTSIDE this public repository and the isolated release.

## Execution architecture

1. In the integrated Telegram admin panel (`/engines`), select
   `brooks_price_action` (public built-in), request enablement of
   analysis, select `PAPER`, choose timeframe and `crypto` or `all`
   market scope. These are per-engine persisted operator settings.
2. Independently supply an **offline** replay JSON file with a single
   historical window of **60–256 contiguous, finalized OHLCV bars**.
3. Explicitly run `naseri-brooks-replay` from a trusted local checkout,
   passing the NEW platform's private state directory and the untouched
   `production_source` directory.
4. The runner verifies the independently pinned SHA-256 of the **362-entry
   frozen manifest** and each listed source file. Three previously existing
   public unmanifested cold-start modules are separately SHA256-pinned;
   unknown or modified Python files and source symlink traversal are denied.
   It then launches an isolated Python child
   interpreter and runs `BrooksTrilogyFullCoreEngine.evaluate` with the
   native `BrooksFullCorePolicy(enable_trade_decisions=True)`. That engine
   flag computes a geometry *decision*; it does NOT place orders.
5. A real `NO_SIGNAL` becomes a recorded no-signal scan. A real
   `LONG`/`SHORT` with valid price, stop and structural targets becomes
   a `SignalIntent(EvidenceMode.PAPER)` in the existing isolated
   `custom_paper.db.a7_paper_intents` table.
6. The database verifies engine enablement, selected timeframe, selected
   market, PAPER environment and exact settings revisions **again under the
   SQLite write transaction**. A disable or changed configuration during
   evaluation prevents persistence. Repeated replay is idempotent.
7. The existing Telegram admin panel **shows genuine Brooks PAPER results**
   and the counts of replay scans and no-signal outcomes. It may preview
   PAPER intents **only in the authorized private administrator chat**.
   This stage NEVER sends a signal to an assigned channel.

The worker is a separate process to isolate the old `app` import namespace
from the new `naseri_markets` package; it is **NOT an OS sandbox** and the
operator must only point it at the trusted public repository checkout.
The publicly packaged v0.4 wheel intentionally **does not include** the
legacy historical tree. Operators must supply that separately.

## Local, nonproduction operator example

In a developer checkout with project dependencies already installed and
the explicit private state directory accessible to the same OS user:

```bash
naseri-engine-admin --state-dir /absolute/private/dev-state \
  --admin-ids 123456789 --owner-ids 123456789 --check

# Enable Brooks requested analysis and PAPER in the DEVELOPMENT Telegram
# /engines panel; then execute an already prepared OFFLINE replay file:
naseri-brooks-replay \
  --state-dir /absolute/private/dev-state \
  --legacy-source /absolute/trusted/checkout/production_source \
  --replay /absolute/offline/BTCUSDT-15m.json
```

**Do not use your production server, production database, production bot
token or production chat in this test.** No background polling is initiated
by `naseri-brooks-replay`.

Input file schema (bar array must have 60–256 consecutive complete bars;
the **illustration below contains one bar only**, so it is intentionally
NOT directly executable):

```json
{
  "schema_version": 1,
  "origin": "replay",
  "market": "crypto",
  "provider": "binance_replay",
  "symbol": "BTCUSDT",
  "timezone": "UTC",
  "quote_currency": "USDT",
  "exchange": "binance",
  "market_type": "futures",
  "timeframe": "15m",
  "candles": [
    {
      "open_time": "2026-01-01T00:00:00+00:00",
      "close_time": "2026-01-01T00:15:00+00:00",
      "open": "100",
      "high": "101",
      "low": "99",
      "close": "100",
      "volume": "10"
    }
  ]
}
```

Candle prices are **decimal strings**, time is timezone-aware and mapped
to UTC, bars must be contiguous and have the exact selected interval.
Only `origin="replay"` and `market="crypto"` are accepted; no live,
unclosed, bid/ask-tick, forex, index or metal data can enter this adapter.
Replay evaluates the **last bar of the supplied window**, not a full
multi-window backtest and not a continuously running bot engine. A
`NO_SIGNAL` outcome is correct if the real Brooks detector finds no
eligible setup. The integration never invents a setup or relaxes rules
to improve PnL.

### Separation of enablement and publication

`requested_enabled=true` plus `signal_environment=PAPER` authorizes
the **manual offline replay** only. `requested_publication` from PR #157
is merely a saved future preference and is **not consulted** to post PAPER
results: PAPER never goes to the channel.

`effective_publication=false`, channel `delivery_mode=DISABLED` and
`telegram_sent=false` stay fixed in this stage. Automatic publication
needs a separate authenticated FORWARD provider, delivery idempotency,
re-verification of channel permissions and explicit later deployment.

## Validation

`tests/unit/test_brooks_real_offline_replay.py` invokes the **genuine**
frozen full-core engine end-to-end (not mocked) with closed-candle
fixtures, then checks persistence, repeatability, privacy and safety.
Separate explicitly labeled **mock transport-contract tests** exercise
the storage path when a compatible LONG decision exists; those are
NOT historical evidence of trading profitability or a claim that the
synthetic fixture naturally produced a profitable strategy signal.
GitHub CI also validates the pinned frozen manifest, isolated package
build, legacy regressions, complete test corpus and publication safety.

**Nonproduction verdict target:**
`PUBLIC_BROOKS_REAL_REPLAY_PAPER_INTEGRATED`,
not `BROOKS_LIVE_SIGNAL_PUBLICATION_ENABLED`.
