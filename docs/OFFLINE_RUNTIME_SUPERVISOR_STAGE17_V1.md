# Multi Market Trading — Stage 17 Offline Runtime Supervisor V1

**Status: nonproduction operator-driven queue, not a live daemon or public release.**

Stage 17 adds a durable work queue around existing Stage 12 control-plane settings and Stage 16 offline replay integration. It **does not** create a competing strategy/risk engine, install unknown strategies, connect to real market data, authorize real trades, or send Telegram messages. Stage 16 remains the only handoff implementation for this research path.

## Boundary and user journey

`operator-reviewed CoreManifest + Stage 6 research catalog → Stage 12 private panel config (actor/instance/binding/revision) → enqueue supplied immutable synthetic closed candles with due time → bounded operator-invoked run_due → Stage 16's existing Stage 5/7 evaluation + optional already-approved Stage 8/9 PAPER and Stage 10 NO-SEND signal journal → durable result hash → read-only health`. The queue is a *separate, non-atomic* SQLite file.

In particular, Stage 17 is **not a self-starting background poller**. The host must supply closed candles (REPLAY or SYNTHETIC domain only) from an explicitly authorized offline source and invoke `run_due` in a trusted process. It does not make a Binance, Kraken, MetaTrader, Telegram, HTTP, market provider or broker request. Nothing starts automatically at installation, import, bot `/engines` click, or restart.

## Operational invariants

- Enabled only with `MMT_NONPRODUCTION=1` and explicit `enabled=True`. The state directory must already exist, be owned by the caller and private (`0700`); the dedicated Stage 17 database must be non-symlink, single-link, and private (`0600`). Unknown existing databases are refused, not migrated.
- A work unit includes the host-selected instance/binding, immutable panel revision, canonical closed candles, source reference and `due_at` in UTC. Work identity is content-addressed SHA-256; enqueueing the same content again cannot create another row or reschedule a completed entry.
- At enqueue and *again before and after execution*, the supervisor checks authorized actor/instance, fresh Stage 6 provider metadata, selected binding, requested modes, and panel revision. Changes fail closed; **no toggle grants a broker, actual Telegram or LIVE permission**.
- SQLite `BEGIN IMMEDIATE` atomically claims one due `PENDING` work unit and assigns a random claim token. Another local worker cannot claim the same unit. At most 25 tasks can run in one explicit bounded invocation.
- A `CLAIMED` work unit blocks scheduling later work from being executed on that same binding until the operator has stopped the other worker and resolved the ambiguity; other independent bindings can continue.
- `DONE` requires an inert Stage 16 result with `telegram_sent=false`, `broker_order_sent=false`, `live_trading_enabled=false`. A result digest is stored, not secrets. No broker order or actual channel message is accepted as a valid completion.
- A callback error, stale panel version, bad result or tampered queued payload is `QUARANTINED`. No automatic retry follows, because Stage 8/9 and Stage 10 are separate ledgers; a failure might already have caused a committed PAPER reservation or signal.
- A process crash/kill can leave `CLAIMED`; restarts never auto-steal or retry it. `quarantine_inflight(operator_ack=True, all_workers_stopped=True)` can change that to `QUARANTINED` **only** after all other workers are positively stopped. Inspect the offline Stage 13 ledger gate and independent journal evidence before deciding a new, different work event is safe. This API is *not* an automatic ledger reconciliation algorithm or proof that a claimed worker has stopped.
- Actor authentication is inherited from the trusted panel boundary; **numeric actor ID supplied in Python is not remote identity verification**. Host-level runtime isolation and distributed multi-host leader election are not provided.

## Developer API (trusted operator code only)

```python
from naseri_markets.offline_runtime_supervisor_v1 import (
    OfflineRuntimeSupervisor, Stage16ReplayExecutor,
)

# On an isolated, authorized development machine, with existing private
# state dir, trusted panel and manifest, canonical offline candle tuples:
with OfflineRuntimeSupervisor(runtime_path, panel=panel,
       actor_id=approved_admin_id, enabled=True) as supervisor:
    job_id = supervisor.schedule(
        instance_id, binding_id,
        expected_panel_revision=current_panel_revision,
        candles=closed_candles, source_ref="approved_synthetic_replay",
        due_at=closed_candles[-1].close_at, operator_ack=True)
    # `integration` is the existing reviewed Stage-16 host.
    # If PAPER is requested, explicit Stage-8/9 authorization, risk/account
    # setup, and matching budget must already have happened independently.
    outputs = supervisor.run_due(
        Stage16ReplayExecutor(integration, paper=preconfigured_paper,
                              signals=local_no_send_signal_ledger,
                              quantity=paper_quantity,
                              dry_run_channel_id=local_research_route),
        now=closed_candles[-1].close_at, limit=1, operator_ack=True)
    print(supervisor.health())
```

The Stage-16 adapter is never implicitly authorized by the queue and never calls `authorize_paper` or changes an account policy. `signals` can remain absent when the panel did not request dry-run signals; `paper` can remain absent when PAPER was not requested.

## Clean-install synthetic proof

Use an isolated Python 3.12 environment containing the independently installed `multi-market-trading==0.4.0rc1` wheel and a fresh private destination. Then run:

```bash
MMT_NONPRODUCTION=1 python -m naseri_markets.supervisor_synthetic_smoke_v1 \
  --state-dir /safe/private/parent/stage17-demo \
  --ack-synthetic-offline

MMT_NONPRODUCTION=1 python -m naseri_markets.runtime_supervisor_health_v1 \
  --runtime-db /safe/private/parent/stage17-demo/supervisor.sqlite \
  --ack-nonproduction-readonly
```

The smoke invokes the **real Stage-16 public demonstration core** and Stage-10 NO-SEND journal, closes/reopens Stage-17 and verifies zero duplicate work. It does **not** run the real Stage-8/9 PAPER order path; that path is exercised in a separate affected-module test on the complete repository and is not claimed as part of the wheel smoke. No synthetic profit result is evidence of real-market edge.

## Test/release expectations

1. New tests include deterministic scheduling, due-time ordering, concurrent two-handle claim exclusion, restarts, crash-with-inflight, tampered payload, unsafe executor result, stale panel revision, private file permissions, owner/admin ACL, and **real Stage-16 offline signal**.
2. In the complete repository, the focused cross-ledger test adds an independent Stage 12 → 16 → 8/9 PAPER → 10 signal → Stage 13 read-only integrity check, with no real broker/Telegram call. The reduced local fixture skips that portion when historic Stage-3 dependencies are absent.
3. `.github/workflows/stage17-offline-supervisor-acceptance.yml` independently tests a clean installed Python 3.12 wheel and recovery; the existing full corpus, publication safety and native PostgreSQL workflows retain their own independent CI evidence.
4. If any CI workflow fails, **do not merge**.

## Remaining gaps (publication BLOCKED)

- No continuously running independently authenticated operator service, production scheduling, real provider callback or consumer, multi-process crash fencing outside this SQLite file, or host daemon/soak tests.
- No automatic *atomic commit* across Stage-12, Stage-8/9 and Stage-10 SQLite ledgers. A crash after external ledger mutation cannot be fixed by content hashes alone; requires operator-run reconciler and recovery policy.
- Stage-4 untrusted Python runtime has no adversarial host validation. External plugins are not approved for a generic public marketplace.
- No verified Telegram `sendMessage`/`editMessage` acknowledgements or real order state matching; no live market account, feed authenticity, futures legal eligibility or business readiness.
- The Stage-11 research lab has not proven genuine historical edge/profitability.
- The private NY First-Reversal core is excluded; no private source or metadata is placed in this public stage.

**Release gate:** `STAGE17_OFFLINE_RUNTIME_SUPERVISOR_IMPLEMENTED` is not `PRODUCT_READY_FOR_LIVE` and does not authorize deploy, installation on production, Telegram publishing or live trading.
