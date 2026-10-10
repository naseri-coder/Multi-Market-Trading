# Nonproduction Kraken Futures BTC/USD → genuine Brooks V5 → PAPER

**Stage result is conditional on actual GitHub Actions E2E, not a mocked PASS.**
No dedicated VPS is required for these **one-off** GitHub-hosted Ubuntu jobs.
No production bot, Postgres, Telegram channel, broker, exchange key, private
NYFR core or 24/7 service is involved.

## Independent source, never a silent exchange fallback

The existing Binance USD-M `fapi.binance.com` adapter remains intact and
reports HTTP 451 from a GitHub-hosted US runner (separate draft PR #160).
This Kraken integration uses Kraken's **TRADE** OHLCV candles for the **linear
`PF_XBTUSD` perpetual, quoted in USD**, not `BTCUSDT`/USDT. Do not pool its
signals, calibration or instrument identity with Binance USD-M, spot or the
private owner-custom engine.

Documented public Kraken API:
`https://futures.kraken.com/api/charts/v1/trade/PF_XBTUSD/15m?count=73`.
The separate provider reachability probe also checks inverse
`PI_XBTUSD` and Binance Spot market-data-only, but neither is automatically
used to analyze with the Kraken linear contract; a spot probe cannot be
reported as a successful futures test.

The feed uses a fixed HTTPS host (no proxy and no redirect), TLS validation,
size/timeout limits and a strict contract/timeframe allowlist. It drops the
last forming bar, requires 60–256 fully closed consecutive OHLCV bars in UTC,
rejects stale/future data and impossible price geometry, and preserves
`provider=kraken_futures_trade_public`, `exchange=kraken_futures`,
`market_type=futures`, `symbol=PF_XBTUSD`, `quote_currency=USD` in the
canonical data passed to Brooks. Market data is public and not
cryptographically exchange-signed.

### Authoritative futures price tick metadata

The frozen Brooks V5 policy intentionally has a *Binance-symbol* price-tick
allowlist. Applying that original policy directly to `PF_XBTUSD` fails
closed, rather than safely producing a Kraken signal. The public adapter
therefore separately GETs the official **Kraken Futures instrument listing**
(`https://futures.kraken.com/derivatives/api/v3/instruments`), requires
exactly one tradeable `PF_XBTUSD` futures instrument, and checks its positive,
bounded `tickSize`. Missing, stale, malformed, unavailable, duplicate or
nontradeable instrument metadata stops PAPER without a signal.

The isolated `brooks_replay` worker uses this *explicit instrument metadata*
only to extend its local `BrooksFullCorePolicy.context.futures_tick_sizes`
tuple for the real Kraken symbol. It cannot alter any existing Binance tick,
threshold or historical source byte; it cannot be used for another symbol,
provider or market. The engine version and provenance remain V5; the
context configuration version records the added tick mapping. **This is
exchange execution metadata, not a trading threshold optimization.**

## Full-core PAPER safety

The **actual pinned BrooksTrilogyFullCoreEngine V5** runs in a separate child
interpreter using the existing `replay_once` worker, not a replacement
simulator or a newly invented strategy. Only the new data adapter and
strict safety tests are added; historical `production_source` and
`SHA256SUMS` remain unchanged.

Only when a development operator **explicitly** enables
`brooks_price_action` and sets it to `PAPER` plus `crypto`/`all`
does `naseri-brooks-kraken-paper` fetch public market data. It refuses when
OFF before network, and revalidates CAS state after the network read and
again during journal commit. Each closed-candle snapshot is idempotent.
An admin request to enable channel publication does **not** enable
publication: effective publication is still false; routes remain DISABLED;
no Telegram API is called.

## Local command — NONPRODUCTION ONLY

Run from a verified checkout **outside all existing production deployments**,
with the public wheel installed, its already-frozen historical source present
separately and PAPER settings applied only to a development state DB:

```bash
naseri-brooks-kraken-paper --once \
  --state-dir /absolute/disposable-dev-state \
  --legacy-source /absolute/checkout/production_source \
  --symbol PF_XBTUSD --bars 72 --ack-nonproduction-paper
```

A bounded 2-cycle option exists: `--cycles 2 --poll-seconds 30`. There is
**no continuous background loop**, service or schedule in this stage. The
`/engines` private development admin menu owns requested engine/PAPER
permissions, but does **not** autonomously launch a process or send channels.

## Real HTTP end-to-end acceptance

`.github/workflows/brooks-kraken-paper-e2e.yml` runs a temporary GitHub
runner with 30-second-separated real HTTPS calls, isolated ephemeral SQLite,
full genuine V5 evaluation, re-fetch/dedup verification, pre-network OFF
denial and revocation-after-disable test. The runner deletes its temporary
DB at exit. All unit safety tests, source pin verification, wheel/NYFR
exclusion, lint and repository-wide CI checks must also pass.

Success verdict: `PASS_REAL_KRAKEN_FUTURES_BROOKS_PAPER`.

A network restriction, insufficient data, unexpectedly changed schema or
engine failure is a failure, NEVER transformed into mock data or a PASS.
No actual trade profit or Telegram delivery is inferred from a healthy
market-data-to-PAPER integration.

For an always-on market ingestion worker or opt-in channel publishing,
use a future explicit deployment/security approval. Do not confuse
GitHub-hosted one-off smoke tests with a persistent runtime.
