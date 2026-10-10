# Brooks V5 — actual Binance public HTTPS E2E (no dedicated server)

This stage **does not require an owned VPS**: run a two-cycle, one-off,
nonproduction smoke on a temporary GitHub-hosted Ubuntu runner. Its disposable
SQLite working directory is created using tempfile and deleted after the job;
no Docker, Compose, production database, background service, Telegram bot
token, channel message or broker order is used.

**Separate concepts**
- The production legacy Telegram bot remains untouched and NOT connected
  to this new feed.
- The new development-only `naseri-brooks-market` poller already exists,
  but nothing automatically launches it.
- This stage validates the **actual public Binance USD-M HTTPS API**, rather
  than previous mocked Binance JSON. Real data is never equivalent to
  proven trade profitability.
- The real frozen historical `BrooksTrilogyFullCoreEngine` is called via
  `replay_once`; source bytes and manifest may never be changed.
- Telegram channel forwarding remains DISABLED even if an ephemeral admin
  explicitly saves `requested_publication=true`.

## Acceptance plan

The opt-in script `scripts/brooks_real_http_smoke.py` runs:

1. SHA-frozen source verification; reject disarmed poll BEFORE transport.
2. Create isolated `TemporaryDirectory` and enable exactly Brooks +
   PAPER using production-equivalent CAS settings APIs, without starting a
   Telegram Application; also request publication to prove requested
   preference is **not** effective send permission.
3. Request live `BTCUSDT` USD-M `15m` public OHLCV over ordinary verified
   HTTPS; validate closed-bar data, source, continuity, freshness and
   geometry, then evaluate V5 and commit NO_SIGNAL or PAPER outcome.
4. Repeat once after **30 seconds**. Confirm unique scan keys, actual
   two-cycle outcome, no Telegram and no broker; no signal is invented when
   V5 finds no setup.
5. Disable Brooks using revision CAS and prove no further transport call or
   new journal write can occur. Check publication remains false and route is
   still `DISABLED`. Destroy local ephemeral state on completion/failure.

## Reproducible job

`/.github/workflows/brooks-real-http-smoke.yml` contains the test. It
requires explicit `--ack-public-http-paper` from the operator-controlled
CI invocation, with no secrets. Its result is a line starting
`BROOKS_HTTP_E2E=`, with structured verdict.

- `PASS_ACTUAL_PUBLIC_HTTPS_BROOKS_PAPER`: two genuine HTTP cycles completed
  with a real engine and all safety invariants.
- `BLOCKED_EXTERNAL_MARKET_FEED`: Binance inaccessible or data
  rejected from this runner. **Not a pass**; do not substitute fixtures
  and do not claim actual live validation. HTTP 451/geographical restrictions,
  429/rate limits and network timeouts may vary by GitHub runner location.
- `BLOCKED_BROOKS_VALIDATION`: historical engine/source or analysis
  integration is not proven; a defect must be investigated.
- Any unhandled error or failed assertion is also **not a pass**.

This workflow is intentionally **one-off** on an ephemeral runner, not a
periodic signal bot. For a continuously running service, one still needs a
separately authorized always-on runtime and an operational deployment review.
Neither the temporary runner nor the public repository is a persistent
low-latency production data ingestion service.

Do not create a permanent GitHub Actions cron that masquerades as the
running production bot. Do not publish signals, merge private strategies
or activate a broker as part of this phase.
