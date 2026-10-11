# Stage 6 — Read-Only Provider Adapters and Instrument Registry V1

**Scope: NONPRODUCTION.** Metadata observation only. No VPS, production database, Telegram bot, private NY First-Reversal core, API credentials, order placement or live feed activation.

## Architecture and invariants

1. The core/strategy (Universal Core API v1) must **not** choose exchange, broker, symbols, leverage, timeframe, account or capital. Bindings belong to the host/admin panel, under separately verified permissions.
2. The new `InstrumentMetadata` records a native provider symbol, market, timezone, quote currency, tick size, optional quantity step and contract multiplier. All values are typed and validated.
3. The in-memory `ResearchInstrumentCatalog` atomically replaces whole provider snapshots; duplicate symbols, mixed provenance, conflicting same-time snapshots, older snapshots, stale or future metadata fail closed. Other providers remain unaffected. No persistence or background work is performed.
4. Every record's `trading_authorized` and `paper_signal_authorized` flags are **false**. A public exchange `tradeable` flag means its instrument is exchange-listed, **never** that the operator has permission to trade. The existing Iran-residency futures eligibility fence is unchanged.
5. Stage 5's market-data engine still accepts only `REPLAY` or `SYNTHETIC`. Stage 6 metadata and DEMO quotes must not be passed off as authenticated LIVE observations or used to authorize signals.

## Provider integrations

| Provider | Already vetted source | Stage 6 output | Limit |
| --- | --- | --- | --- |
| Kraken Futures public contract research | `https://futures.kraken.com/derivatives/api/v3/instruments` via the existing `public_futures_contracts.py` | Native perpetual IDs, quote currency, price tick and exchange status | Does not imply residency eligibility, contract multiplier or lot step |
| KuCoin Futures public contract research | `https://api-futures.kucoin.com/api/v1/contracts/active` via the same existing parser | Native perpetual IDs such as `XBTUSDTM`, quote currency, tick and exchange status | No account/trading approval, real feed or margin assurance |
| Already connected MT5 DEMO terminal | Explicitly supplied, trusted MetaTrader5 SDK object | Read-only broker symbol specification (tick size, lot step, contract size) and fresh Bid/Ask | Requires SDK-reported DEMO + connected state; not broker or residency attestation |

No duplicate unauthenticated HTTP implementation is introduced. `futures_snapshot` transforms source bytes only. `discover_public_futures` is explicitly called by an operator and reuses the existing fixed-host, GET-only, no-proxy, no-redirect public-data downloader. Both `MMT_NONPRODUCTION=1` and `acknowledge_research=True` are required; `MMT_PRODUCTION=1` blocks it. A test transport can be injected to prevent real network requests.

The optional `mt5_demo_observation` function does **not** initialize a terminal or select symbols; it invokes only `account_info`, `terminal_info`, `symbol_info`, and `symbol_info_tick` on an already connected independently authorized SDK. It requires `operator_ack=True`, nonproduction mode, a DEMO account and connected terminal, fresh non-crossed prices, native broker symbol identity and plausible forex currency identity. It never accesses order APIs. MT5-reported values are untrusted until independently reconciled, and are not actual fills.

## Minimal example

```python
from datetime import datetime, timezone
from naseri_markets.instrument_registry_v1 import ResearchInstrumentCatalog
from naseri_markets.read_only_provider_adapters_v1 import futures_snapshot

# raw: previously obtained official-format JSON bytes, not a live attestation
observed = futures_snapshot("kucoin", raw, observed_at=datetime.now(timezone.utc))
registry = ResearchInstrumentCatalog(max_age_seconds=300)
registry.replace(observed)
records = registry.research_instruments("kucoin_futures", now=datetime.now(timezone.utc))
assert all(not entry.trading_authorized for entry in records)
```

## Tests and limitations

- Unit tests cover provider isolation, snapshot revisions, idempotency, stale/future data, duplicate symbols, invalid tick sizes, actual KuCoin parser schema, no-network defaults, opt-in read-only public API, MT5 DEMO-only account verification, stale/crossed quotes and absence of `order_send`.
- The source modules are additive. Existing Stage 3/4/5 modules, `trusted_custom.py`, frozen production manifests, Docker/Compose, Telegram and SQLite/PostgreSQL remain unchanged.
- **No real official HTTP call was made during development verification**; tests use fixed data. **No real MT5 account or authorized broker was accessed.** Provider terms, country-specific eligibility, account permissions, data licensing and feed provenance must be verified independently before a market can be enabled for users.
- Network/API test acceptance does not establish trading authorization or profitable strategy behavior. In particular, unavailable contract multiplier/size fields remain `None`, never guessed. FX Bid/Ask is not a simulated execution receipt.
- This is **not** a generalized multi-broker live feed, complete normalized instrument registry, or deployable public signal product.

**Next step (separate authorization):** Stage 7 Strategy Orchestrator — host-managed multi-symbol bindings and event dispatch, remaining default disabled and nonproduction. Live data, Telegram publication and real orders need separate acceptance and authorization.
