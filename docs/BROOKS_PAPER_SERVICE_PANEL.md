# Brooks V5 — independent continuously running PAPER worker (development only)

## Architecture and authorization boundary

This stage adds a **separately operated** persistent *process model*, not a
production deployment. The public `Multi-Market-Trading` repository now has
the Python worker `naseri-brooks-paper-service`. It is not started when the
package is installed, when the development Telegram Application boots, or
when anyone taps an admin button. GitHub Actions runs **bounded tests only**.
An actual continuously running instance would need a deliberately installed
and authorized separate development host or supervisor. No VPS, service,
cron, broker or production bot has been provisioned or changed here.

The worker uses **only the independently identified Kraken Futures**
`PF_XBTUSD` (USD-quoted linear perpetual), **never** silently substitutes a
Binance Spot or Binance USD-M market, and calls the existing public
`naseri_markets.brooks_kraken_feed.poll_once` and the real pinned Brooks V5
child worker. The source manifest, historical `production_source`, its
SHA256SUMS, strategy thresholds, private NY First-Reversal, live execution and
Telegram publisher remain untouched.

## Real private panel control

The existing nonproduction Telegram `/engines` panel is the desired-state
controller. Only a configured private admin may press Brooks enable/disable,
choose a timeframe, market scope and `OFF` / `PAPER`, using existing CAS
revisions. The worker re-reads **the very same isolated SQLite state directory**
at least every five seconds and before every HTTPS request. Turning off
Brooks, switching to `OFF` or another market scope prevents new downloads
and analysis; the existing replay journal also checks CAS during persistence,
so settings changed while a request or worker is running cannot commit a new
PAPER signal. No process spawning is permitted from Telegram callbacks.

**Important distinction**: the Telegram action enables/disables *analysis
eligibility*, not the OS process. When the worker is not installed or its
heartbeat expires, the UI says `NOT_INSTALLED` / `STALE`; it never claims
that clicking ON started a service. A real alive worker reports `IDLE`,
`WAITING`, `ANALYZING`, or `DEGRADED`, plus last closed candle, count
of successful/failed cycles and a sanitized reason. A graceful shutdown
shows `STOPPED`. Idle/waiting heartbeats older than 30s are STALE; an in-progress ANALYZING\ncycle has a bounded 90s grace for Kraken metadata, OHLCV and the genuine V5\nchild process, then also becomes STALE. This remains
a development-local control channel; nothing connects to the existing
production bot.

## Reliability safeguards

- Manual, explicit standalone `--ack-nonproduction-standalone-paper` and
  `MMT_NONPRODUCTION=1`; `MMT_PRODUCTION=1` always blocks startup.
- Preflight SHA-pins the historical 362-entry source manifest and extra
  public modules. No unverified Brooks code can execute.
- Exclusive local advisory `flock` process lock; a second fresh worker
  lease is refused by SQLite too. Stale worker ownership cannot overwrite
  a new worker's heartbeat.
- No analysis while admin Brooks is disabled, market scope is noncrypto,
  or signal environment is OFF. No Telegram channel publication, even
  with `requested_publication=true` (effective publication always false).
- Timeframe-aware scan schedule follows finalized candle closure with a
  five-second finality buffer. The existing canonical snapshot/scan id
  deduplicates retry/restart and prevents duplicate PAPER signals.
- Fail-closed, **bounded** retry backoff (10–300 seconds) for inaccessible,
  malformed, stale data or failed engine evaluation; no fabricated bars,
  placeholder signal or automatic provider fallback. Errors are sanitized
  in heartbeat state. On the next allowed cycle, recovery happens without
  mutating trading thresholds or touching a production database.
- Graceful SIGTERM/SIGINT, finite-step CI tests and never a GitHub Actions
  infinite process. The external process supervisor is responsible for
  restart after host outage and for OS-level logs/resources.

## Reproducible, not-yet-deployed separate development runtime

The following is a **future development-host operator procedure**, NOT a
command to execute on any live bot host. The Telegram admin application and
worker need identical `/absolute/isolated-dev-state` and the preverified
checkout of historical sources:

```bash
export MMT_NONPRODUCTION=1
naseri-brooks-paper-service \
  --state-dir /absolute/isolated-dev-state \
  --legacy-source /absolute/checkout/production_source \
  --ack-nonproduction-standalone-paper
```

For a deterministic nonproduction smoke, use `--max-steps 3` (the worker
always exits after three state iterations). Configure desired Brooks ON,
`PAPER`, scope `crypto`/`all`, and supported Kraken timeframe via the
private development `/engines` panel. The worker initially remains idle;
only panel-authorized settings activate scans. Panel and worker must have
access to one shared, dedicated development SQLite folder. The separate
Telegram app must use a **development bot token**, never the legacy
production token.

An inert sample unit is retained at
`deploy/examples/brooks-paper-nonproduction.service.example`. On a
**separately authorized** development host, a dedicated unprivileged
`mmt-paper-dev` account and private writable `/var/lib/mmt-paper-dev`
state folder could be used with a process supervisor that restarts only on
real process failure. This file has not been installed, enabled or launched.
Do **not** copy the command or any token to the running price-action server,
enable any service, create a new VPS, open firewall ports or create a
deployment until an explicit, environment-specific deployment authorization
is given.

## Verification and limits

`.github/workflows/brooks-service-panel.yml` executes the frozen source
audit, package preflight, wheel install, panel and service tests, single
worker lease, desired-state enabling/disabling, stale heartbeat detection,
network failure/backoff safety, and unchanged channel publication. The
already-merged Kraken two-cycle real-HTTPS E2E is independent evidence for
the feed to pinned V5, **not** a claim of current 24/7 uptime.

This phase gives an **operator-ready, separately runnable development
service**, not running 24/7 yet. Per-symbol expansion and any Telegram
channel forwarding or actual trade execution require another separately
authorized stage. Signals and demonstrated positive expectancy are
different concepts: no profitability is asserted.
