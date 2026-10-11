# Multi Market Trading — Stage 12 Trading Control Center V1

**Status: NONPRODUCTION CONTROL-PLANE CANDIDATE ONLY.** This is not a deployed bot, a venue-integrated control panel or real trading authorization.

## Baseline and scope

- Source baseline: `main@5a4d705f59cceb278f98bd1e706eb50f5b8559b3` (Stage 11).
- Additive modules: `trading_control_center_v1.py`, `trading_control_telegram_v1.py`, `trading_control_dev_mount_v1.py`, plus focused tests.
- Existing `bot_admin_app.py`, `integrated_engine_panel.py`, `engine_control_store.py`, Stage 3–11 contracts, old `production_source`, manifests, production database and services are **unchanged**.
- Mounting is explicit: call `build_stage12_dev_application` to register handlers on the **same** already existing development Telegram Application (no second poller). Caller must supply a **dedicated nonproduction token**, an existing dedicated state directory and a trusted user/owner ACL. The mount itself never connects or starts polling.

## 1. Core classification and privacy

- Built-in Al Brooks Price Action reference is visible in the public control-plane inventory as `brooks_price_action`, version `REFERENCE_ONLY`, *not* secretly claimed to implement Core API v1. Migrating the real Brooks engine to Core API is a separate future stage.
- A core becomes editable with market bindings only when the host supplies a reviewed, exact `CoreManifest` instance via `CoreListing`.
- Owner-only Custom entries are **not embedded** by ID, source, secrets or private repository paths in this public implementation. Operators may inject private metadata in isolated owner configuration; non-owner admins neither list, create nor view them.
- Each admin owns only their own instances, even when other admins can manage public cores. A trusted Telegram framework `effective_user.id` is required; bot messages and group/supergroup callbacks are denied. ACL booleans are **not** remote authentication on their own.

## 2. Per-instance, multi-market settings

```
Approved CoreManifest (host inventory, not imported strategy source)
  -> Instance (account_id + portfolio_id + actor owner)
     -> Many bindings (market/provider/symbol/timeframe)
     -> Independent research toggles (analysis / dry-run signals / PAPER orders)
     -> Budget preview (reserved risk / notional / per order / active count)
```

- Timeframes: `1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `12h`, `1d`.
- A binding needs an explicit Stage-6 `ResearchInstrumentCatalog` snapshot, a fresh exact provider + symbol match and a compatible Core Manifest. Unsupported, unknown, halted, time-skewed or reclassified metadata are rejected.
- Cryptocurrency public futures *contract discovery* and MT5 DEMO *read-only* metadata are **research inputs**, not evidence of Iran-resident eligibility, an authenticated LIVE feed, or permission to trade. The existing restrictive Iran-futures allowlist is **unchanged**.
- Same sample strategy can be previewed against independent crypto pairs and FX brokers *where operator has actual compatible research metadata*. No provider/pair/timeframe is embedded into the core formula.
- A selected instrument is tagged with Stage-6 metadata hash. Prior to creating a `CoreBinding` preview it is revalidated against the live-in-memory Stage-6 research snapshot. Changing metadata forces explicit review.
- Current view limit is 64 bindings per instance. No background scheduler, account selection web UI or live price subscriptions added.

## 3. Capital and independent modes

- Budget is a **requested configuration** per core instance, never money locked at a real broker. Funds are **not** reserved by this control plane.
- Account-level requested reserved-risk fractions cannot sum beyond 1 across instances in this dedicated database. Per-order budget cannot exceed per-instance budget. Stage-8 actual PAPER risk manager maintains the real offline account/portfolio/correlation/margin checks in a *different database*, and is not automatically activated here.
- Independent requested switches: `analysis`, `signals` (dry-run signal output only), and `paper` (PAPER intent only). Switching off one does not switch off the others.
- `telegram_publication_enabled`, `broker_orders_enabled`, and `live_trading_enabled` are **always False**, even if all three requested switches are True. The Stage-10 outbox remains DRY-RUN. Neither bot transport nor order sender is invoked from this module.
- Enabling a switch requires at least one binding and a reviewed manifest; the Brooks reference is shown but cannot be armed. No customer can authorize trade access through this panel.

## 4. Durable state, concurrency and recovery

- New dedicated SQLite file `stage12_control_preview.sqlite`, journal mode WAL, `synchronous=FULL`, `BEGIN IMMEDIATE`, foreign keys and numbered compare-and-swap revisions. **Refuses existing DB files containing unrelated tables.**
- Different admins are isolated by both owner ACL and SQLite row owner. Duplicate bindings or forged cross-instance binding IDs cannot be applied.
- Append-only administrative audit records include actor, action, instance revision, payload SHA256 and predecessor hash; this is locally tamper-evident *by convention*, not externally signed proof or append-only storage against privileged attackers.
- Stored panel preferences survive process restart; there is **no startup activation** of market feeds, paper engine, Telegram publishing or trade orders. Revalidated Stage-6 in-memory metadata must be reloaded explicitly before preview can be consumed.
- A callback carries bounded integer instance-row ID and expected revision; staleness is rejected. This is UI concurrency protection, **not cryptographic authorization**.

## 5. Available Telegram commands (private admin chat only)

- `/mmt12` — inventory and instances plus action buttons
- `/mmt12_new CORE_ID INSTANCE_ID ACCOUNT_ID PORTFOLIO_ID` — create a nonproduction configuration instance
- `/mmt12_add INSTANCE_ID PROVIDER SYMBOL TIMEFRAME` — add a symbol/timeframe from a fresh Stage-6 research snapshot
- `/mmt12_del INSTANCE_ID BINDING_ID` — remove one binding
- `/mmt12_risk INSTANCE_ID RESERVED_FRACTION NOTIONAL_FRACTION ORDER_FRACTION MAX_ORDERS` — revise modeled capital configuration

On the instance detail, inline buttons independently request analysis, dry-run signal handling, and PAPER handling. The bot displays a permanent no-LIVE/no-real-Telegram warning. All messages are plain text; no unescaped HTML/Markdown or arbitrary private strategy source is displayed.

### Opt-in development mount

```python
from pathlib import Path
from naseri_markets.trading_control_dev_mount_v1 import build_stage12_dev_application

handle = build_stage12_dev_application(
    token=dedicated_dev_token,             # supplied by trusted operator secret manager
    state_dir=Path("/separate/nonproduction/state"),
    admin_ids={verified_admin_id},
    owner_ids={verified_owner_id},
    listings=(reviewed_example_core_listing,),
    catalog=trusted_offline_stage6_snapshot_catalog,
    explicitly_enabled=True,
)
# The *same* existing development Application has old and Stage-12 handlers.
# No run_polling()/start() invoked here. Operator must authorize separately.
handle.close()   # only after the application has stopped
```

The existing launcher is deliberately **not** modified to auto-run Stage-12 handlers. The future production panel needs separate identity/auth, eligibility, secrets handling and activation fencing before being mounted in a production bot. In development, the new function returns an existing nonproduction application with both panels mounted.

## 6. Tests and acceptance

New `tests/unit/test_trading_control_center_v1.py` provides deterministic offline tests of:

- Public Brooks reference; owner-only Custom privacy; cross-admin isolation; private-chat-only Telegram callbacks.
- Independent toggles with no actual execution/publishing flags.
- Multiple crypto/forex instrument/timeframe bindings with host-selected CoreBinding identity.
- Fresh Stage-6 metadata, halted symbols, incompatible timeframes, duplicate rejection and metadata snapshot drift.
- Capital limits and account aggregate budget; transactional CAS and stale callback.
- SQLite restart persistence and audit chain; refusal to touch existing unrelated database.
- Single PTB Application registration with `explicitly_enabled=True` and no new polling.

Local test coverage cannot attest Telegram API permissions, genuine broker access, host security of an untrusted plugin, or a profitable strategy. Run the repository's public unit/full CI and publication-safety policy before merging.

## 7. Not included

No bot token in source/database, no exchanges or broker REST POSTs, no position modifications, no public channel publication, no GVisor proof, no real user credential auth, no trading eligibility approval, no production migrations, no real-market backtest, no LIVE or DEMO orders, no unknown plugin execution and no private NY First-Reversal source. Nothing here silently alters the prior integrated panel.

**Expected verdict after verified CI/merge:** `STAGE12_CONTROL_CENTER_NONPRODUCTION_MERGED_PASS`. This is not a statement of production readiness.
