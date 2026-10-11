# Stage 4 — no-VPS product acceptance (2026-10-11)

**Purpose:** verify the independently installed Multi Market Trading
0.4.0rc1 development product as a coherent user-operable PAPER preview,
using a GitHub-hosted disposable CI runner rather than a purchased or
existing server. This is not a production deployment.

## Acceptance gates (all required)

| Acceptance gate | How it is exercised | Condition for PASS |
| --- | --- | --- |
| Frozen legacy preservation | SHA256 source manifest and A6 release preflight | Historical app, private NYFR, Docker/Compose unaffected |
| Clean product installation | Official isolated `scripts/install_platform_dev.sh` on Ubuntu runner | New, non-root venv/wheel/Telegram extra; fresh 0700 state and working CLI |
| No implicit execution | Fresh `mmt-dev status` and worker-state inspection | Worker `NOT_INSTALLED`, no Telegram polling |
| Real mounted admin UI | Installed wheel's actual `build_admin_application` and `IntegratedEnginePanel`; **no Telegram network** | `/engines` and `/custom` registered |
| User access controls | Admin-only callback attempt with unauthorized user | Rejected, no data leakage or setting change |
| Persistent options | Authorized Telegram inline `5m` selection; close/reopen SQLite | Updated timeframe and CAS revision persisted |
| Replay resistance | Repeat old callback, forge `ex:set` and `ep:set` | No stored exchange/symbol changes or extra revisions |
| Iran-approved venues | Real live product eligibility predicate and UI | No prohibited/unverified venues shown or writable |
| Metadata is not permission | Fixed offline KuCoin-format contract API fixture | Native `XBTUSDTM`, and all trading/PAPER grants remain false |
| PAPER worker by default | SHA-pinned Brooks source and real service object, fail-closed policy | `IDLE`, no HTTP fetch, no recorded scans |
| Direct feed by default | Direct Kraken poll with no-network transport | Refused **before** metadata/market HTTP |
| Requested channel publication | Admin expresses requested publication | `effective_publication=false`, route `DISABLED` |
| Simulated internet outage | Local injected reader raises `KRAKEN_FEED_HTTP_503` | Worker `DEGRADED`, bounded retry and no duplicate immediate call |
| Simulated restoration | Same local reader succeeds after the retry window | `WAITING`, counters report 1 refused and 1 completed |
| Restart / state durability | Stop worker and construct a fresh genuine worker against same SQLite | New lease, prior selected timeframe, actual residency restriction intact |
| Final state | Open SQLite and query `mmt-dev status` | Worker `STOPPED`, no actual market scans, no Telegram delivery and no live orders |
| Evidence | JSON report created by installed-wheel acceptance harness | Machine-checked verdict, list of passed gates, no secrets |

**Important:** Since the approved Iranian-resident futures exchange list
remains **empty**, the correct result for exchange/pair *switching* is a
**blocked selection**, not successful live trading. Testing a successful
non-restricted venue switch would require operator authorization and
officially verified Iranian-resident futures support. Fake venue eligibility
is used **only inside one in-memory test scope**, to exercise the retry
state machine. The mock is removed before restart and never persists.

Similarly, the simulated HTTP 503 and subsequent restoration do **not**
constitute an outage of a real exchange; no network was used by the
acceptance harness. No real Telegram bot was connected and no real
Telegram delivery is claimed. Neither positive PnL nor real broker
account authorization is tested here.

## CI execution, reproducibility and artifact

GitHub Actions:
[`product-stage4-acceptance.yml`](../.github/workflows/product-stage4-acceptance.yml)

Run on every PR that modifies the Stage 4 contract and, when explicitly
requested, by workflow_dispatch. It creates a *fresh* Linux runner,
installs the real new-product wheel using the existing non-root
installer, invokes the **installed-wheel** acceptance program using
`python -I`, and checks the output using a separate Python verifier.
No VPS, host firewall, actual bot token, market API key, production
PostgreSQL or custom NYFR source is used.

GitHub Actions artifact (30-day retention):
`product-stage4-offline-acceptance`, containing:

- `product-stage4-acceptance.json`: machine-readable named acceptance gates
- `product-stage4-status.json`: final separate CLI status
- `product-stage4-run.log`: acceptance summary

The tests do not write to the repository or overwrite an existing
evidence file. No source, runtime settings, Telegram chat IDs or tokens
are included in the evidence JSON.

## Explicitly outside Stage 4 without a service environment

- Telegram Bot API round-trip, receiving real updates and posting
  signals to a real channel
- Production server install, systemd supervision, external secrets,
  database backup/restore in a running deployment
- Actual provider disconnect/reconnect or 24/7 uptime
- A new approved Iran-resident derivatives exchange and eligible
  provider-specific real-time feed
- Profitability, signal frequency, strategy calibration or trading orders

**Verdict semantics:** `PASS_NONPRODUCTION_OFFLINE_STAGE4_ACCEPTANCE`
indicates **offline acceptance passed** only. It must never be
rendered as `PRODUCTION_READY`, `REAL_TELEGRAM_DELIVERY_READY`,
or `IRAN_FUTURES_EXCHANGE_AVAILABLE`.

## Repeating locally without a new server

On a disposable Ubuntu/Linux development computer with a fresh
checkout, Python 3.12, Git, network access only for installing Python
dependencies and the explicit Stage 1 development opt-in:

```bash
export MMT_NONPRODUCTION=1
bash scripts/install_platform_dev.sh \
  --destination "$HOME/mmt-stage4-test" \
  --ack-isolated-dev-install

"$HOME/mmt-stage4-test/venv/bin/python" -I \
  scripts/product_stage4_acceptance.py \
  --state-dir "$HOME/mmt-stage4-test/state" \
  --legacy-source "$PWD/production_source" \
  --report "$HOME/mmt-stage4-report.json"
```

Use a **new** installation path and new report path each time. No bot
token is required; the test constructs an offline Telegram Application
with a clearly fake token.
