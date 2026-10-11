# Multi Market Trading — Stage 7: Universal Strategy Orchestrator V1

**Baseline:** `main@dad1a5613080110048a378c6e10a7b9fd86d7b03` (Stage 6)  
**Status:** additive, OFFLINE/NONPRODUCTION; no bot integration, no live feed, no broker orders, no Telegram sends.

## 1. What this stage actually adds

`naseri_markets/strategy_orchestrator_v1.py` links the *existing* Stage-5 `OfflineMarketDataEngine` to the Stage-3 `CoreManifest` / `CoreBinding` / `CoreResult` data contract, via one of two explicitly defined evaluator adapters:

- `TrustedCoreEvaluator(OfflineCoreHarness(..., enabled=True), manifest)` — **reviewed, trusted, in-process** Python used only for operator-approved offline development, not user-supplied arbitrary code.
- `IsolatedCoreEvaluator(SecureOfflineCoreHost(...), manifest, source, sha256)` — Stage-4 **rootless Docker + gVisor** proposal for externally supplied plugin source, disabled until explicit isolated-host setup and attestation. It has no fallback to regular Python execution. The Stage-4 runtime remains **not independently adversarially verified**.

Both return inert, independently validated `CoreResult` decisions, not orders or channel publications. No strategy imports, provider APIs, installation, market scraping or account operations are added to the orchestrator. The developer's core does **not** choose provider, broker, symbol, timeframe, capital, leverage, account or publication destination: each `CoreBinding` is administered by the host.

## 2. Architecture and process boundaries

```
Operator/test-only OFFLINE MarketPacket
       |
       v
Stage 5 OfflineMarketDataEngine -- isolated feed lane, causal validation, dedup
       |
       +--- binding A (crypto, BTC..., 15m) ---> Reviewed Core A
       +--- binding B (crypto, ETH..., 5m) ----> Reviewed Core A
       +--- binding C (forex, EURUSD, 1h) -----> Reviewed Core B
       +--- binding D (same feed as A) --------> Stage-4 sandboxed Core C
                                                [only after separate host verification]
       |
       v
Core API v1 validation + binding-level quarantine + bounded in-memory dedup
       |
       v
OrchestratorReceipt (INERT): CoreResult, input digest, price/volume basis,
analysis state, errors, no execution or publication permission
```

Stage 6 research metadata can inform an operator's selection, but its `trading_authorized=False` is never promoted or overridden. The currently empty Iran-resident futures eligibility allowlist remains unchanged. Futures contract listing data does not authorize an account, a strategy publication, PAPER market polling or live order execution.

## 3. Controls and contractual guarantees

1. `OfflineStrategyOrchestrator(enabled=False)` refuses packets by default; each registered binding is also disabled by default. An enabled Stage-5 data engine does not implicitly activate a core.
2. The operator must supply `operator_ack=True`, the **current revision**, and the exact binding ID to enable/disable offline evaluation. **This boolean is not an authentication system** and must never be exposed as a public end-user authorization route.
3. Core manifest, supported market/event and exact instrument/timeframe are checked by Stage 5 at subscription time; evaluator manifests must match. Binding IDs are unique in this orchestrator instance.
4. One normalized, validated feed is shared between all subscribed binding IDs. Each receives a distinct CoreInput and digest, even if the same strategy source is evaluated for several accounts, symbols or timeframes.
5. Exact repeated market packet is dropped by Stage 5. Identical CoreInput following an explicit feed reset is suppressed at the binding layer. Returning an already-seen actionable decision ID (entry, management or exit) quarantines the affected binding.
6. Evaluation errors, malformed results, cross-binding spoofing and stale/cross-position decisions fail closed and quarantine **only the offending binding**. They do not quarantine the shared healthy feed or unrelated engine instances. The operator cannot re-enable a quarantined binding using the toggle.
7. Invalid market samples and feed sequencing errors quarantine **only the affected feed** in Stage 5. Recovery is a separate operator-assisted resynchronization, never an automatic backfill or unknown-data acceptance.
8. Status reports completed/refused event counts, revision, last observed time and stable error code **without including strategy exceptions, credentials or raw source**.
9. Both `BindingStatus.telegram_enabled`, `BindingStatus.broker_orders_enabled` and the equivalent two fields of `OrchestratorReceipt` are always False. **No published messages, broker fills, realized returns, signal delivery guarantees or LIVE authorization.**
10. This candidate evaluates one packet synchronously under a local lock. A blocking **trusted** in-process callback may block other subscriptions; hostile code must go through a separately verified bounded Stage-4 worker. Concurrency, persistence, scheduler and capacity validation are separate future stages.

### Retention / idempotency scope

- Maximum registered bindings: 128 by default (configurable 1–1024).
- Maximum remembered actionable IDs **per binding**: 2048; earlier IDs eventually expire. This is **not** permanent deduplication.
- The Stage-5 feed state, binding revision/activation, decision ID memory, quarantine state and receipts are **in-memory only**. A process restart loses them. Do not attach this to a live channel or account before a durable journal, revision fencing and startup reconciliation are built and audited.
- Shared feed fan-out is sequential, not a performance claim. No process isolation is promised for the trusted in-process test path.

## 4. Minimal illustration (synthetic / replay only)

```python
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from naseri_markets.contracts import Instrument, Market
from naseri_markets.core_api_v1 import ClosedCandle, CoreBinding, CoreEventType, DataOrigin, OfflineCoreHarness
from naseri_markets.example_dual_setup_core_v1 import DualSetupExampleCore
from naseri_markets.market_data_engine_v1 import (
    FeedDefinition, MarketPacket, OfflineMarketDataEngine, PriceBasis, VolumeSemantics)
from naseri_markets.strategy_orchestrator_v1 import (
    OfflineStrategyOrchestrator, TrustedCoreEvaluator)

core = DualSetupExampleCore()  # illustrative, NOT a proven profitable strategy
instrument = Instrument(Market.CRYPTO, "offline_example_venue", "ABCUSD", "UTC", "USD")
feed = FeedDefinition("feed_crypto", instrument, "15m", CoreEventType.CLOSED_CANDLE,
                      DataOrigin.SYNTHETIC, "offline_fixture", PriceBasis.TRADE,
                      VolumeSemantics.TRADED)
market = OfflineMarketDataEngine(enabled=True)
market.register_feed(feed)
manager = OfflineStrategyOrchestrator(market, enabled=True)
manager.attach(feed.feed_id, core.manifest,
               CoreBinding("instance_alpha", "binding_alpha", instrument, "15m"),
               TrustedCoreEvaluator(OfflineCoreHarness(core, enabled=True), core.manifest))
manager.set_enabled("binding_alpha", enabled=True, expected_revision=1, operator_ack=True)
start = datetime(2026, 10, 11, 10, 0, tzinfo=UTC)
for i in range(2):
    t = start + timedelta(minutes=15 * i)
    candle = ClosedCandle(t, t + timedelta(minutes=15), D("100"),
                          D("108") if i else D("102"), D("99") if i else D("98"),
                          D("106") if i else D("100"), D("10"))
    receipt = manager.ingest(MarketPacket(feed.feed_id, i+1,
                             candle.close_at + timedelta(seconds=1),
                             feed.source_ref, candle=candle))
    # 'receipt.outcomes' contains inert validated CoreResults, NOT orders.
    assert receipt.telegram_sent is False and receipt.broker_order_sent is False
```

## 5. Acceptance / reproducibility

- New tests: `tests/unit/test_strategy_orchestrator_v1.py` (offline unit/integration cases, including parameterized cases).
- Regression: Stage 3 contract, Stage 4 sandbox guard mock tests, Stage 5 data fan-out and Stage 6 research adapter tests.
- Validate the **full existing GitHub public/unit suite and publication safety checks** before merging. Stage 7 adds no GitHub Actions workflow and does not rerun expensive unrelated CI without need.
- Tests are all offline; they intentionally create no network session, Telegram bot, database, positions, futures account or real server service.

## 6. Explicitly not done

- Broker or exchange live market feed, exchange eligibility approval, MT5 REAL access, broker execution, Telegram publication or signal PnL.
- Operator/Telegram authentication, user profiles, public plugin installation, dynamic selection UI or per-account risk.
- Transactional persistence, multi-worker concurrency, cross-restart replay protection, durable decision-to-signal/order handoff, watchdog/restart, validated hostile-code containment.
- Private NY First-Reversal source or metadata publication.

**Expected verdict once merged + tests verified:** `STAGE7_STRATEGY_ORCHESTRATOR_NONPRODUCTION_PASS`. A local merge or tests are not a production qualification.
