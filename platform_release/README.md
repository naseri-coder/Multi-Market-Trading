# NASERI MARKETS 0.4.0rc1 — isolated public platform preview

This distribution packages the public `naseri_markets` source only.
It exposes typed market contracts, quote-quality gates, explicit in-process
engine registry/runner, paper/forward-observation stores, and optional generic
Telegram transport library code; nothing runs automatically.

The CLI is **offline-only**: `naseri-markets --check` or
`naseri-markets --engine-plan example.json`. It has no activation,
server, channel token, DB migration, order execution or private strategy
download capability.

The historical v0.3.2 `crypto-price-action` release has a distinct
Python package, Dockerfile, Compose project and PostgreSQL volume.
No migration between the two is performed by this candidate.


## Actual public Custom PAPER workflow (operator-trusted code only)

The optional installed `naseri-custom` CLI now supports **explicitly
operator-approved locally stored standalone Python Custom scripts** and
PAPER-only replay with a durable SQLite journal. Source hash pinning and
`--trust-local-code` are mandatory. It is NOT an untrusted-code sandbox,
public automatic installer, signed A24/A25 publisher entitlement, live feed,
Telegram bot, or broker/trading integration. See
[trusted local Custom PAPER MVP](../docs/TRUSTED_LOCAL_CUSTOM_PAPER_MVP.md)
for commands, the ABI and the private NY First-Reversal exclusion.


### Optional Telegram administration controls

Install the optional `[telegram-admin]` extra and mount
`CustomAdminPanel(...).register(application)` into the **same** approved
python-telegram-bot application. Provides private admin-only per-engine
PAPER enable/disable, verified private channel destination configuration
(**delivery remains disabled**), PAPER signal previews and audit history.
This is **not** integrated into the old frozen production bot or deployed.
See [Custom admin panel guide](../docs/CUSTOM_TELEGRAM_ADMIN_PANEL.md).


## New product Telegram engine manager (nonproduction)

The installed `naseri-engine-admin` command can perform a local offline
`--check` and only under explicit development flags mount a single Telegram
Application with `/engines` and `/custom`. It lists Al Brooks as a built-in
reference, with separately requested analysis/publication. The new explicit
`naseri-brooks-replay` command runs the genuine frozen Brooks full-core V5
against validated offline candle windows and stores PAPER results for the
admin panel; the continuously running bot engine remains **not mounted**. NY First-Reversal is a protected, owner-only
Custom **metadata reference** (opt-in `--owner-reference`); no private code
is installed or exposed. Per-engine OFF/PAPER, market, timeframe preferences,
private channel settings and admin audit are available. No auto channel
sending or live trading. See [integrated engine management](../docs/INTEGRATED_ENGINE_MANAGEMENT.md).


## Genuine Brooks full-core replay (public, offline PAPER only)

The `naseri-brooks-replay` command requires explicit local paths to a
SHA-verified historical `production_source` directory and an offline
closed-candle replay file. It calls the **actual** existing Al Brooks V5
analyzer in a separate trusted local worker and records only eligible
PAPER intents or no-signal scan evidence in the unified private SQLite
journal. Settings are checked before execution and under the final journal
writer lock. Brooks PAPER outcomes are visible to the private admin through
`/engines`. No live data, automatic channel posting, broker orders or
private NYFR loading. Full usage and boundaries:
[Real Brooks offline PAPER replay](../docs/BROOKS_REAL_OFFLINE_PAPER_REPLAY.md).
