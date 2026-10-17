# MMT R31 — Private Admin, Runtime Health, Signal Ledger Preview (OFFLINE)

**Status:** Draft development artifact stacked on R30 PR #323. No main merge, market client, broker order, public channel publication, live trading or automatic poller. Older R28/R29/R30 Draft branches and code-acceptance gates remain unresolved.

## What was already implemented

- `trading_control_center_v1.py`: Stage12 admin role and per-owner instance ACL, revision/CAS and local audit; reviewed Core API parameter envelope, provider/symbol/timeframe bindings, request flags for analysis/signals/PAPER and capital limits. All *execution* permissions remain False. Built-in Brooks is a reference until separately mounted.
- `trading_control_telegram_v1.py`: private-chat, Telegram-framework Update-derived actor validation; opt-in Stage12 UI, settings and requested toggles. A raw numeric ID from a user message does **not** authenticate a remote identity.
- `integrated_engine_panel.py`, `engine_control_store.py`: existing nonproduction exchange discovery/venue eligibility, symbol/timeframe and engine configuration with owner-only private Custom reference. Venue discovery is not verified exchange permission.
- `offline_signal_lifecycle_v1.py`: Stage10 local signal+outbox lifecycle with no Telegram sender; `PENDING`, `CLAIMED`, `SIMULATED_ACK`, `UNKNOWN`. A simulated ACK is not an actual Telegram delivery confirmation. An `UNKNOWN` may represent a delivery of uncertain outcome and **MUST NOT** be blindly retried.
- `offline_runtime_supervisor_v1.py`: Stage17 single offline queue and read-only health (job counts); no background poller or broker.

## R31 additive implementation

`naseri_markets/mmt_r31_private_admin_console_v1.py` adds two *opt-in* classes:

1. `R31OfflineAdminConsole`: typed existing Stage12 + optionally Stage10 and Stage17 components; all operations require `MMT_NONPRODUCTION=1`, explicit operator approval, existing Stage12 admin/owner scope and matching Stage17 panel/actor. `overview(actor_id)` exposes only this administrator's instances and reviewed core references; `detail(actor_id, instance_id)` shows core, research provider/symbol/timeframe, parameter fingerprint, allocation, Stage12 audit count and Stage17 health. It DOES NOT identify a Stage6 research feed as legally eligible, actual orders, actual balance, real PnL or reliable source custody.
2. `disable_requests(... expected_revision ...)`: one Stage12 **BEGIN IMMEDIATE + CAS + hashed audit** mutation that atomically sets requested `analysis/signals/paper` to False. This is a **settings disable**, not actual broker cancel, position close, Stage3 kill-switch modification, external venue stop, or acknowledgment that an in-flight worker ceased. Existing unknown effects still require independent reconciliation.
3. `private_signal_preview(... signal_key ...)`: verified instance+core+binding owner scope before revealing local Stage10 signal state, counts of PENDING/CLAIMED/SIMULATED_ACK/UNKNOWN, and an explicit unresolved marker. Does **not** expose channel token/chat destination, claim an ACK or issue any outbox command. Per-signal recipient privacy/real Telegram route confirmation remains unavailable.
4. `R31PrivateTelegramAdminPanel`: optional handler registration on an already trusted, existing `python-telegram-bot` Application. Commands respond **only to the effective private actor chat**, using the pre-existing Stage12 `TelegramControlPreviewPanel._actor(Update)` guard. This relies on the trusted Telegram framework and host application; unit-created fake Update objects are for negative tests, **not remote authentication**. It never calls a channel publisher or `bot.send_message` to a signal target. Registering handlers does not start polling.

## Opt-in private admin commands

- `/mmt31`: this authorized administrator's research instances and menu.
- `/mmt31_view INSTANCE`: reviewed engine ID, research provider/symbol/timeframe, request toggles, queue health and explicit NOT VERIFIED trade report.
- `/mmt31_off INSTANCE REVISION`: atomically disables all three **requested** research modes using existing CAS; a stale or cross-owner command is rejected.
- `/mmt31_signal INSTANCE SIGNAL_KEY`: private local Stage10 outbox-status preview, **not publication**.

Existing Stage12 commands remain authoritative for binding and policy edits; R31 never creates a second source of settings. The new panel is **not** mounted into the production bot, app or service; a trusted operator must explicitly register it in an isolated nonproduction PTB application. If mounted/running, ordinary replies to the verified private administrator use Telegram; this does not imply delivering strategy signals into a private channel.

## Critical delivery semantics

Telegram Bot API sends are not one transaction with a local SQLite/PostgreSQL record. Exactly-once *real delivery* requires independent reconciliation of uncertain transport outcomes and cannot be claimed from the Stage10 `SIMULATED_ACK` state. R31 intentionally has **no channel send path**. It cannot prove actual delivery, prohibit all duplicate real sends elsewhere, or certify real RBAC beyond the host-attested private Update and Stage12 local ACL.

## Acceptance and release gates

- Proposed dedicated test `tests/unit/test_mmt_r31_private_admin_console_v1.py` exercises real Stage12/Stage10 *local* state: per-owner confidentiality, private/group/unauthorized command rejection, atomic disable+revision increment, stale CAS rejection, source binding coverage, simulated unknown outbox and no implicit publication methods.
- Recommended local checks after checking out **the exact R31 Draft SHA**, without invoking hosted GitHub Actions:

    export MMT_NONPRODUCTION=1
    unset MMT_PRODUCTION
    python -m pytest -q tests/unit/test_mmt_r31_private_admin_console_v1.py
    python -m pytest -q tests/unit/test_trading_control_center_v1.py tests/unit/test_offline_signal_lifecycle_v1.py
    python -m pytest -q tests/unit
    ruff check naseri_markets/mmt_r31_private_admin_console_v1.py tests/unit/test_mmt_r31_private_admin_console_v1.py

- Full real pytest, Ruff, independent CodeQL, Publication Safety, dangerous callback/failure-injection tests, complete future-source R29 study, independent actual authenticated private signal delivery and test deployment are **NOT RUN/NOT CERTIFIED** as of Oct 16.
- Do NOT merge, deploy, connect PAPER/LIVE or publish signals until corresponding permissions and external verification are independently established. R32 installer/release and R33 restricted LIVE remain blocked.

**Disposition:** `MMT_R31_PRIVATE_ADMIN_CODE_PREPARED_ACCEPTANCE_PENDING`.
