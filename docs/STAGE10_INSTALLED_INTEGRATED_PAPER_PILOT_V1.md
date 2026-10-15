# Stage 10 — Clean Installed Integrated PAPER Pilot V1

**STATUS: NONPRODUCTION · ISOLATED INSTALLED WHEEL · SYNTHETIC TWO-BINDING PAPER ONLY · NOT A PUBLIC/LIVE RELEASE**

## The gap actually closed

The project already contains a **real Stage-20 integration** of the Stage-12 operator settings, Stage-16 bounded replay, Stage-17 scheduled jobs, Stage-19 effect intents/receipts, Stage-8/9 modeled PAPER position lifecycle, Stage-10 no-send signal state and Stage-13/19/9 reconciliation. It uses two public demonstration bindings on **synthetic OHLC bars**, never real broker orders.

The Stage-20 module was runnable using a Python module invocation but did not expose a dedicated **installed** command with a separate-process, **strictly read-only reopen** of its five persistent databases. Stage-10 adds that missing narrow entry point without creating a new engine, worker, ledger, migration or execution adapter. The old installed toy **naseri-paper-demo** remains unchanged.

### Product and package isolation

- Authoritative preview distribution: `multi-market-trading==0.4.0rc1` from `platform_release/pyproject.toml`.
- New console script: `naseri-paper-pilot` calling `naseri_markets.installed_paper_pilot_stage10_v1:main`.
- Original root `crypto-price-action==0.3.2` package, PostgreSQL volume, Docker service, private NY First-Reversal and live server remain untouched.
- Installation never launches a process, modifies state, attaches provider APIs or sends notifications.

## Clean nonproduction installation

Use Python 3.12 on a **disposable machine**; do not use the production bot host or production keys. The existing `scripts/a6_prepare_package.py` creates a standalone reviewed source tree and refuses a destination inside the checkout. Example:

```bash
python3.12 -m venv /tmp/naseri-stage10-venv
/tmp/naseri-stage10-venv/bin/python scripts/a6_prepare_package.py \
    --destination /tmp/naseri-stage10-build
/tmp/naseri-stage10-venv/bin/python -m pip wheel --no-deps \
    --wheel-dir /tmp/naseri-stage10-wheels /tmp/naseri-stage10-build
/tmp/naseri-stage10-venv/bin/python -m pip install --no-deps \
    /tmp/naseri-stage10-wheels/multi_market_trading-0.4.0rc1-*.whl
```

An isolated runner must keep repository imports absent; the wheel is installed and invoked from outside the checkout.

### First process: two-binding PAPER demonstration

Set `MMT_NONPRODUCTION=1`, ensure `MMT_PRODUCTION` is unset, and choose an **absolute, previously nonexistent** directory under a private owner-controlled location. The Stage-20 runner creates the directory with `0700` and refuses to overwrite existing runs.

```bash
export MMT_NONPRODUCTION=1
TOOL=/tmp/naseri-stage10-venv/bin/naseri-paper-pilot
$TOOL --run --state-dir /tmp/naseri-stage10-first \
  --first-symbol BTCUSD --second-symbol ETHUSD \
  --first-timeframe 5m --second-timeframe 1h \
  --ack-synthetic-offline
```

Expected output is the Stage-20 synthetic report showing exactly two completed jobs, two closed PAPER trades, six exact **initial** effects (2 × reserve/plan/dry-signal), Stage-13 cross-ledger integrity PASS, no-send signal records and no LIVE/feed/profitability/release grant.

To intentionally omit no-send signal journaling, add `--no-dry-run-signals` to **both** invocations; this must produce four instead of six initial effects. It **never** means signals will be transmitted.

### Second, entirely separate process: inspect existing evidence

First stop every potential writer and independently confirm that the five stores form a coordinated frozen snapshot (including SQLite WAL data, where needed). **This is an explicit operator assertion, not cryptographic custody proof**. Then:

```bash
$TOOL --inspect --state-dir /tmp/naseri-stage10-first \
  --ack-synthetic-offline --ack-writers-stopped
```

This verifies private ownership, directory mode `0700`, regular non-symlink SQLite role files with no group/other permissions, duplicate file roles, no missing data and bounded file size. It opens only existing files read-only; no initialization, schema migration, dispatcher or attempt to resume incomplete work is allowed.

It reuses:

- **Stage-13** integrity and binding/plan/exits/signal evidence checks.
- **Stage-19** exact-ID, hashed audit chain and target/receipt checks.
- **Stage-9** recovery decision table with predeclared Stage-20 kind sets for every one of the two jobs; the job IDs are read from the existing Stage-17 registry but **the expected kinds are fixed by this pilot contract**, not inferred from successful receipts.
- Strict two-binding, two-DONE-job, two-PAPER-order, two-plan and signal-mode counts.

If either a job is not DONE or an effect is missing/conflicting/ambiguous, the inspection **refuses**, not repairs. A success includes deterministic evidence digests and never means global exactly-once or actual market profitability. **Re-running --run on the same state directory always refuses rather than overwriting or replaying.**

## Hard boundaries and acceptance

**No data replay on inspect, no crash retry, no completion of quarantined jobs, no automatic PAPER restore, no broker/Telegram access, no strategy fitting or real feeds.** All exposed flags `public_release_authorized`, `automatic_recovery_authorized`, `broker_order_sent`, `telegram_sent`, `live_trading_enabled` and `exactly_once_guaranteed` remain false.

CI tests:

1. Unit tests use the actual Stage-20 two-binding synthetic engine and a **separate read-only inspector**, test byte-for-byte preservation of the five closed SQLite files and repeatable digests, validate optional no-signal mode.
2. Refuse stale/unknown installed package versions, missing opt-in, missing explicit operator stop acknowledgment, symlinks, overly broad permissions, missing SQLite role, crash-quarantined runtime jobs, incomplete effect receipt and reusing an already-existing directory.
3. **Clean-wheel GitHub Actions** builds an isolated preview wheel, installs into a fresh Python 3.12 virtual environment, runs `naseri-paper-pilot --run` in one subprocess and `--inspect` in another subprocess from a clean work directory with empty Python import path. The original five database file hashes remain the same between these processes. Duplicate run and missing acknowledgment are rejected.
4. Full protected repo workflows, Stage-19 effect audit and Stage-20 installed acceptance must continue to pass.

The synthetic data source and trusted demonstration core have **no evidentiary value for real trading profitability**. A clean-wheel success proves only this installed, bounded PAPER product journey; it does not prove a verified Brooks adapter, provider provenance/eligibility, deployment, third-party plugin sandbox or multi-ledger atomicity.

**Change boundary:** 1 new public module, 1 dedicated test module, 1 isolated GitHub workflow, this document, and one entrypoint in `platform_release/pyproject.toml`. No modification to Stage-20 core execution, default CLI, Stage-9 reconciler, database schema, migrations, production code or package root.

**Stop after Stage 10.** Do not start Stage 11 or release/activate the actual public trading bot automatically.
