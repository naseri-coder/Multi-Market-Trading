# Step 1: Isolated new-product installer and development runtime

This is a **new-product development** path, not a v0.3.2 upgrade or an
authorized server deployment. No existing server, daemon, database, Docker
volume, Telegram bot token, or source manifest is modified. Target is
`multi-market-trading==0.4.0rc1` from a verified, separate Python wheel.
The original `bash markets.sh` remains the historic v0.3.2 manager.

## What is actually installed

- A new **non-root**, self-contained Python 3.12 virtual environment in
  the operator's explicitly requested **nonexistent, absolute** directory,
  always outside the source checkout.
- Only the public, A6 source-filtered new `naseri_markets/` wheel; a
  `[telegram-admin]` optional dependency install with `pip check`.
  No frozen `production_source/` or private NYFR code in the wheel.
- Dedicated 0700 `state/` with the A7-backed local SQLite control store;
  **no legacy PostgreSQL/volume access** or bot activation.
- A local `mmt-dev` command (within this installation only), which runs
  `naseri_markets.dev_operator` from the venv.
- The source remains *external*, read-only and SHA256-pinned by the existing
  `production_source/SHA256SUMS` verifier when a PAPER worker is started.

**Installer requirements:** Linux, Python 3.12, pip, `python3 -m venv`,
Git checkout with intact historical 362-entry source manifest,
`sha256sum`, internet access for Python package downloads, and an
unprivileged user. It refuses root, missing explicit dev opt-in, destinations
inside the repository, existing paths and symlink destinations. Does not
create a systemd service, network port, firewall rule or production cron.

On an **isolated and explicitly authorized development machine**, from the
cloned checkout:

```bash
export MMT_NONPRODUCTION=1
bash scripts/install_platform_dev.sh \
  --destination "$HOME/mmt-product-dev" \
  --ack-isolated-dev-install
```

The output includes a single locally installed command. After installation:

```bash
"$HOME/mmt-product-dev/mmt-dev" status
```

Example output fields: `worker_phase=NOT_INSTALLED`,
`iran_futures_eligibility_verified=false`,
`effective_channel_publication=false`, `real_orders_enabled=false`.
`status` is local only and does not connect to Telegram or a market.

## Start and stop the actual integrated development panel

Use a **different, test-only Telegram bot token**, never one from a live
installation. Enter it in the operator's environment without embedding it
in a command argument, source file or shell history. The token must be
available as `MMT_DEV_BOT_TOKEN`; set the allowed Telegram numeric admin ID:

```bash
"$HOME/mmt-product-dev/mmt-dev" run \
  --legacy-source "$PWD/production_source" \
  --admin-ids 123456789 \
  --owner-ids 123456789 \
  --ack-nonproduction-suite
```

Use the actual owner's ID instead of `123456789`, and set
`MMT_DEV_BOT_TOKEN` securely before running the above command.
`run` is an **explicit foreground supervisor**: it starts one
development Telegram `/engines` + `/custom` Application and one
independent Brooks PAPER worker, with the **same 0700 private state
directory**. No bot or worker starts on installation, on `status`, or
from a panel button.

Press **Ctrl+C** to stop both processes cleanly. If one child process
exits unexpectedly, the supervisor terminates and reaps the other.
It has no daemon mode or auto-restart. No host deployment, no supervisor
installation and no token writing is performed here.

For offline / CI checks or independent development processes:

```bash
"$HOME/mmt-product-dev/mmt-dev" worker \
  --legacy-source "$PWD/production_source" \
  --max-steps 1 --ack-nonproduction-worker
"$HOME/mmt-product-dev/mmt-dev" status
```

An isolated standalone panel is possible via `mmt-dev panel
--admin-ids ... --owner-ids ... --ack-nonproduction-panel`, but its
token and explicit development fences must be present. No polling test
runs in CI; CI verifies handlers via a fake token without any network
request.

## Important live-features distinction

The private Telegram menu supports Brooks desired state, saved selected
exchange/pair, 8 timeframes, PAPER/OFF, private destinations and health.
**The October 11 Iran-resident eligibility allowlist is EMPTY**. Therefore
the real worker is deliberately `IDLE` even if the operator sets
`Brooks ON` and `PAPER`, and it never makes Kraken/other exchange HTTP
requests or creates a new PAPER signal in that state. This is expected
safety behavior, **not** an installer malfunction. The existing genuine
Kraken public feed may be exercised only through separately authorized
public-data research/test mechanisms. Do not present prohibited exchanges
as Iran-eligible and do not bypass exchange terms/KYC.

This **Stage 1** verifies wheel installation, isolated process lifecycle,
panel mount, settings/heartbeats and shut down. It deliberately does
**not** authorize actual signal-channel publication, LIVE orders, a VPS
installation or an operator's real bot. Stages for end-to-end validated
provider onboarding and public Telegram delivery remain distinct.

## Verification and release gate

`.github/workflows/product-dev-integration.yml` requires:

1. Historical `production_source` SHA and A6 packaging policy pass.
2. Ruff and focused offline tests including permission and hidden-start denial.
3. Fresh isolated Python virtualenv install of the wheel **and PTB dependencies**,
   isolated `state` init/status, one genuine frozen-source **IDLE** worker
   iteration, stopped heartbeat, zero recorded signals, no Telegram send,
   and mounted `/engines` and `/custom` handlers without network.
4. No changes to legacy install/Compose, source manifest, private NYFR,
   current production servers or other repositories.

The wheel's existing A6 base `dependencies=[]` contract is retained.
The supported **Step 1 runtime path** explicitly installs the
`[telegram-admin]` extra; this is not an assertion that all other research
A-series utilities' dependencies are production-closed.
