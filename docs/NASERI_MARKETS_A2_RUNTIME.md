# NASERI MARKETS — A2: Engine Runtime and Multi-Market Quote Contract

**Implementation status: development-only, no broker/Telegram/production integration.**

A2 extends A1 with an executable, explicitly activated, in-process multi-engine runner.
The legacy \`production_source\` v0.3.2 application and SHA256 release manifest remain frozen.

## Modules

- \`quotes.py\`: canonical timestamped provider/instrument-aware Bid/Ask ticks;
  quote provenance (live, replay, synthetic); independent quote-watermark
  tracking and conservative quarantine on stale, future, spread or out-of-order.
- \`adapters.py\`: pure parsing of Binance USD-M bookTicker (\`E,s,b,a\`) and
  MT5 tick mappings (\`time_msc,symbol,bid,ask\`), never synthetically inventing timestamps.
  MT5 instrument is namespaced with \`provider='mt5:<account-or-feed>'\`.
- \`sessions.py\`: explicit verified provider session windows, closure overrides,
  and IANA time-zone conversion; DST is automatic for NY calendar zones.
  Unverified/missing calendar means no processing.
- \`runtime.py\`: explicit engine binding, allowed instruments, opt-in activation,
  bounded per-engine invocation, output validation and fault isolation.
  Zero import-time registration or automatic startup.

## Security and quality boundaries

- Never trust \`origin=LIVE\` alone: the caller must supply a separately verified feed.
- No trading, Telegram, network calls or private NYFR rules are present.
- A symbol is not a unique identity; provider, market and symbol must match.
- Replay or synthetic quotes cannot be represented as forward observations.
- All signals are intents, NOT filled trades or verified financial performance.
- Data quality quarantine requires an explicit post-resynchronization reset.
- In-process duplicate suppression is volatile and **not** production idempotency.
- Only explicit, verified market-session calendars permit dispatch. Broker
  holidays/early closes/rollovers remain a required external calendar integration.
- FX/index/metal symbols cannot share crypto risk/position-size assumptions.
  Contract specification and quote-currency conversion remain separate A3 work.

## Validation and readiness

Run \`python -m pytest -q tests/unit/test_naseri_markets_a2.py
tests/unit/test_naseri_markets_foundation.py\` from the repository root.

A2 is ready for code review only. It does NOT establish a live Binance client,
authenticated MT5 data, verified broker holiday calendar, resilient queue,
persisted duplicate prevention, private channel routing integration, or any
proof of strategy profitability.
