# MMT-R32 — Offline Security Review Kit and Stopped-Ledger Recovery Gate

**Mode:** DRAFT ONLY, stacked on R31 PR #324. No main merge, no GitHub Actions, no remote server, no production database, no Docker, no external API, no broker order or Telegram signal publication.

## Why this is not a completed installer

Existing scripts/install.sh, scripts/a6_prepare_package.py, Stage18 recovery and Runtime-A8/A12/A13 security modules already exist. Replacing them risks duplicating authority and enabling the wrong release. **R32 adds a non-executable, locally reproducible source review kit and a read-only four-ledger recovery reviewer, NOT an installable or deployable product.** No older install script or SHA-frozen Brooks production source was modified.

### Four R32 files

- scripts/mmt_r32_offline_review_kit_v1.py — stdlib-only manual prepare/verify. Requires externally reviewed 40-hex Git HEAD, a clean checkout, exact Git blob matching for each file, a new private output directory (existing owner-only 0700 parent) and explicit nonproduction approval. Copies exactly fourteen allowlisted R28–R31 review files. No .env, secrets, databases, private NYFR engine or production_source included. Canonical SHA256 manifest and a denial notice are written into the partial review kit. The kit is NOT a functional runtime or installer.
- naseri_markets/mmt_r32_stopped_recovery_review_v1.py — calls existing Stage18 genuine evaluator on four distinct already preserved private offline snapshots. Returns a sanitized summary with ALL broker/Telegram/retry/restore permissions disabled.
- scripts/mmt_r32_stopped_recovery_cli_v1.py — one-shot explicit stopped-state review, never restoring data.
- tests/unit/test_mmt_r32_offline_review_kit_and_recovery_v1.py — synthetic local git and mocked Stage18 safety tests. No exchange, real production DB or host use.

## Android / Termux: offline source review

First compare the exact HEAD with the SHA from a separately trusted source. Do not infer publisher authenticity merely from the local git object or local SHA256.

Example commands (folder names are illustrative):

    cd "$HOME/Multi-Market-Trading"
    git status --short
    git rev-parse HEAD
    export MMT_NONPRODUCTION=1
    unset MMT_PRODUCTION
    mkdir -m 700 -p "$HOME/mmt-r32-review-output"
    python -m scripts.mmt_r32_offline_review_kit_v1 prepare \
      --source-root "$PWD" \
      --destination "$HOME/mmt-r32-review-output/kit-01" \
      --expected-head REPLACE_WITH_EXACT_REVIEWED_R32_HEAD_SHA \
      --ack-review-only

A mismatch, dirty checkout, assumed-unchanged blob drift, source symlink, unexpected output parent, existing destination or Production environment is refused. If interrupted after directory creation, remove the partial *new* directory manually; R32 never recursively deletes unknown paths.

Local verification, again NOT an independent signature:

    python -m scripts.mmt_r32_offline_review_kit_v1 verify \
      --directory "$HOME/mmt-r32-review-output/kit-01" \
      --ack-review-only

A hostile actor able to rewrite both payload and manifest can produce a matching local digest. Retain and compare the manifest hash through separately secured custody; the kit cannot prove independent publisher identity, absence of malware, or release fitness. No new release signing key is generated or imported.

## Offline recovery review — four separate databases

Stage18 uses the existing runtime/control/paper/signal ledger roles. These SQLite databases are not one atomic transaction. A Stage17 DONE callback hash does not prove order/outbox settlement. Claims, quarantines, UNKNOWN acknowledgements and partial effects **must not be retried automatically**.

1. Stop all relevant NONPRODUCTION writers independently. Only use disposable offline systems, never the live production host.
2. Retain four consistent, owner-only 0600 SQLite snapshots outside operational directories. For WAL mode, use a safe consistent SQLite backup/checkpoint process. Blindly copying a busy .db without WAL/shm consistency is not a certified snapshot.
3. Keep frozen copies separate, then run (example paths):

    export MMT_NONPRODUCTION=1
    unset MMT_PRODUCTION
    python -m scripts.mmt_r32_stopped_recovery_cli_v1 \
      --runtime "$HOME/mmt-review/runtime-copy.sqlite" \
      --control "$HOME/mmt-review/control-copy.sqlite" \
      --paper "$HOME/mmt-review/paper-copy.sqlite" \
      --signal "$HOME/mmt-review/signal-copy.sqlite" \
      --all-writers-stopped \
      --ack-nonproduction-review

No backup is created, no restore performed, and no token, account or signal is sent. Even a locally consistent audit cannot grant retry, live trading or order reservation. A real restore rehearsal on a disposable DB remains pending.

## Required independent checks before R32 can pass

On the full, SHA-pinned, disposable R32 checkout, without enabling GitHub Actions:

    export MMT_NONPRODUCTION=1
    unset MMT_PRODUCTION
    python -m pytest -q tests/unit/test_mmt_r32_offline_review_kit_and_recovery_v1.py
    python -m pytest -q tests/unit/test_mmt_r31_private_admin_console_v1.py
    python -m pytest -q tests/unit/test_mmt_r30_offline_risk_order_preflight_v1.py
    python -m pytest -q tests/unit
    ruff check scripts/mmt_r32_offline_review_kit_v1.py \
      scripts/mmt_r32_stopped_recovery_cli_v1.py \
      naseri_markets/mmt_r32_stopped_recovery_review_v1.py \
      tests/unit/test_mmt_r32_offline_review_kit_and_recovery_v1.py

Also independently review Runtime-A13 AST/security audit, A6 release preflight and install --check on an isolated host, full lockfile and supply-chain custody, real PostgreSQL/SQLite restore rehearsal, secret scanning, CodeQL, Publication Safety and exact crash/restart isolation. None has been run and accepted in this R32 GitHub session.

Upstream R28–R31 Draft PRs and R29 genuine 2026-10-20 through 2026-11-03 prospective market evidence remain unresolved. R33 controlled LIVE and installation into production were NOT started.

**Status:** MMT_R32_OFFLINE_REVIEW_AND_RECOVERY_CODE_PROPOSED_NOT_INSTALL_READY.
