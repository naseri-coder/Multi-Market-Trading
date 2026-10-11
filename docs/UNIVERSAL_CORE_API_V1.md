# Multi Market Trading — Universal Core API v1

**Stage:** 3 / `MMT-S3-CORE-ABI-V1`  
**Contract:** `abi_major=1`, `abi_minor=0`  
**Execution:** trusted, explicit, in-process **OFFLINE fixture/PAPER contract only**  
**Production:** **NOT AUTHORIZED**. No live market listener, account, order sender, Telegram publisher, or untrusted-code sandbox.

## Intent and the key separation

This additive API introduces `naseri_markets/core_api_v1.py` without modifying
`contracts.py`, `runtime.py`, `external_abi.py`, `trusted_custom.py`, legacy
`production_source/`, source manifests, SQLite schema, or PostgreSQL.

A developer supplies a strategy **without broker, exchange, pair, account,
leverage, risk allocation, or messaging implementation**. One strategy can
recognize many setups. The host/Telegram manager (in a later integration stage)
selects *multiple* independent `CoreBinding`s for that core: a market,
provider, provider-native symbol and timeframe. A binding is passed *to* the
core as read-only market identity; it is never programmed into the core.

The host also owns credentials, trading mode, account mapping, risk settings,
and independent `signal_enabled` / `auto_trade_enabled` switches. **These are
not present in `CoreInput`** and are not decided by this API. Core output is
only an intent, never approval to send a message or order.

## Interfaces

| Object | Contract |
| --- | --- |
| `CoreManifest` | Stable core ID/version, exact ABI, supported market classes, allowed events, setup catalog and minimum closed-candle lookback |
| `SetupSpec` | Stable `setup_id`, plain description, `may_manage_stop` permission; no trading accounts |
| `CoreBinding` | Host-selected instance/binding IDs, `Instrument` (market, provider, native symbol, quote currency, timezone), timeframe |
| `CoreInput` | Offline evidence origin, bounded closed candles or bounded tick data, optional readonly position snapshot and source reference |
| `CoreDecision` | `NO_SETUP`, `SETUP_CANDIDATE`, `ENTRY_INTENT`, `MANAGEMENT_INTENT`, `EXIT_INTENT` with shape validation |
| `CoreResult` | Exact core/instance/binding/event identity, observed timestamp and input SHA-256 digest; bounded decision batch |
| `OfflineCoreHarness` | **Trusted code only**; off by default; calls `evaluate` and validates the result; quarantines a misbehaving binding |
| `to_legacy_paper_intent` | **Data-only** one-way translation of validated `ENTRY_INTENT` into existing `SignalIntent` with `EvidenceMode.PAPER` |

An explicit `NO_SETUP` is exclusive and cannot create a trade. `SETUP_CANDIDATE`
provides diagnostic evidence but cannot create an order. A valid `ENTRY_INTENT`
requires side, entry, protective stop, 1–5 targets and optional future expiry.
An open position can request a tighter stop only if its setup declares
`may_manage_stop=True`. A position can also request exit or an existing pending
entry can request cancellation; the host must independently validate ownership,
revision, risk and broker permissions before taking **any** action.

**No generic trailing rule is invented:** if a setup does not declare stop
management, a move-stop intent is refused. For a declared setup, a move-stop
intent must be tied to a known matching position ID/revision and must tighten
its existing stop. The model never calls an exchange to change the stop.

## Example core: two setups, different operator bindings

`example_dual_setup_core_v1.py` is a deterministic **illustrative fixture**, not
a validated profitable strategy. It declares:

- `close_above_previous_high` (long, optional stop-to-entry after modeled 1R)
- `close_below_previous_low` (short, no stop-management capability)

The same core object receives host-supplied bindings such as `crypto_a/ABCUSD`
and `fx_broker_b/EURUSD`. Those names appear **only in tests/host bindings**, not
in the strategy. The sample uses *closed* consecutive timestamped bars, not
future data or authenticated provider candles. It supplies only an intent; it
never opens a position, trades or sends a signal.

```python
from naseri_markets.core_api_v1 import OfflineCoreHarness
from naseri_markets.example_dual_setup_core_v1 import DualSetupExampleCore

core = DualSetupExampleCore()
host = OfflineCoreHarness(core, enabled=True)  # explicit trusted OFFLINE opt-in
result = host.evaluate(operator_supplied_core_input)  # CoreInput; no side effects
```

## Safety invariants and contract boundaries

1. Major/minor ABI is currently **exactly 1.0**; unknown/newer versions are
   rejected, not silently interpreted as old A7 envelopes.
2. Input history consists of closed, timezone-aware bars (1–512) or a single
   timestamped Bid/Ask tick. Future, overlapping and malformed bars are refused.
   Market-hour session gaps are intentionally **not** auto-filled or declared
   invalid in this Stage 3 contract; data-quality/session validation is a
   separate host responsibility in Stage 5.
3. `DataOrigin` permits `SYNTHETIC` and `REPLAY` only. It cannot represent an
   authenticated live provider or a broker execution receipt.
4. Identity/digest, known setup IDs, decision uniqueness, expiration, geometry,
   expected position revision, and trailing declaration are checked by
   `validate_core_result`. SHA-256 is an **integrity fingerprint**, not
   independent market provenance or signed code trust.
5. A bad core response quarantines that binding in the **in-memory fixture
   harness**. Quarantine, restart/deduplication, admission and state persistence
   for real execution require the later independent host implementation.
6. The harness calls trusted Python **in the same process**. This is **NOT**
   an adversarial sandbox and is unsuitable for unreviewed third-party code.
   No claim of process isolation, resource enforcement, safe arbitrary imports
   or secret protection may be made for a malicious plugin.
7. The adapter only creates an existing `SignalIntent` (PAPER). **It does not
   attach the legacy production runtime**, publish to Telegram or authorize a
   portfolio risk reservation, order, fill or realized PnL.
8. Existing Iran futures venue eligibility and all LIVE/publication fences
   are unchanged. No public/private NY First-Reversal code is included.

## Scope and acceptance

Run in a disposable Python environment with the same project source tree:

```bash
python -m pytest -q tests/unit/test_core_api_v1.py
```

The Stage-3 acceptance tests cover: ABI negotiation, independent multi-setup
outcomes, one immutable sample core across distinct host-selected bindings,
NO_SETUP, identity and digest, malformed/future OHLC, bad entry geometry,
missing expirations, optional trailing and stale revision, entry/exit/cancel
shapes, legacy PAPER translation and quarantine.

**Deferred intentionally:** Telegram/admin UI binding persistence and callback
RBAC, a versioned host registry, untrusted-plugin sandbox, real cryptographic
release admission, external feed adapters, broker order execution, canonical
transactional DB, actual crash/dedup recovery, PAPER position fill simulation
and full installed-wheel integration. Those belong to subsequent roadmap
stages and **must not** be inferred from the Stage-3 passing fixture tests.

**Rollback:** remove only the additive `core_api_v1.py`,
`example_dual_setup_core_v1.py`, corresponding unit tests and this document.
No data migration, legacy code/manifest change or runtime configuration
rollback is necessary.
