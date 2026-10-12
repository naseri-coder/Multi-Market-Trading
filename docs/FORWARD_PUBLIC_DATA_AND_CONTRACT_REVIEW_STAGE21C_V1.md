# Stage 21C — Forward-armed public Futures capture and contract geometry research

**Status:** opt-in nonproduction candidate. This is two-step public market-data acquisition plus a third, separate, offline PAPER action. No server provisioning, background polling, orders, Telegram messages, credentials or signed venue attestation.

## Why two capture steps?

A public contract list fetched *after* historical bars cannot prove historical contract multiplier, lot size, listing status or fee schedules. Stage 21B correctly requires Stage-6 metadata **observed before** the replay window. Stage 21C therefore **arms an owned capture folder with metadata first**, then requires a later operator invocation when two market-data intervals have fully closed. It refuses a backdated window, gaps, duplicated/overlapping Klines, stale metadata and tampering. No sleep/loop/task runs between the invocations.

Official public GET sources:

- Contract research: `https://api-futures.kucoin.com/api/v1/contracts/active` — [KuCoin Get All Symbols](https://www.kucoin.com/docs-new/rest/futures-trading/market-data/get-all-symbols)
- OHLC: `https://api-futures.kucoin.com/api/v1/kline/query` — [KuCoin Futures Get Klines](https://www.kucoin.com/docs-new/api-3470234)

**ARM** performs exactly one fixed-host public metadata GET after explicit `MMT_NONPRODUCTION=1` and consent. Reuses the Stage-6 strict contract parser, retains raw response bytes as `contracts.json` with SHA256, captures receipt time, and independently parses `tickSize`, `lotSize`, `multiplier`, `makerFeeRate`, `takerFeeRate`, `isInverse`, `isQuanto`, `settleCurrency`, `expireDate`, and listing status. It only accepts two distinct OPEN perpetual contracts quoted/settled in USDT with non-inverse type and positive sane contract parameters. Listing OPEN is **not** account eligibility.

**SEAL** later performs exactly two read-only public Kline GETs in the operator-specified order, enforces both series start at or after recorded metadata observation and finish no later than 24h later, requires at least four strictly consecutive fully closed candles per symbol, parses with Stage 21A constraints, stores immutable-by-convention 0600 `first.json` / `second.json` and a digest-linked `sealed.json`. On network, data, clock, or disk failure it refuses and never silently repairs, retries, or overwrites; uncertain partial files require manual forensic review.

**REPLAY** independently verifies *all stored hashes*, symbol/timeframes, timestamps, file permissions and format, reconstructs the genuine recorded Stage-6 metadata timestamp, then invokes the reviewed Stage-21B PAPER path with `DataOrigin.REPLAY`. This phase makes **zero network calls** and requires a fresh owner-private output directory plus explicit operator acknowledgment. Stage 19 exact intent reconciliation and Stage 13 risk cross-ledger audits are reused. Tests use injected transport only, never claim an actual public HTTPS request occurred on CI.

## Manual commands (separate operator invocations)

Use a Python 3.12 installed wheel in a trusted nonproduction computer. First create a **dedicated owner-private parent** (`0700`) and designate two real, checked KuCoin Futures contract symbols:

```sh
mkdir -p -m 700 "$HOME/mmt-research"
MMT_NONPRODUCTION=1 python -m naseri_markets.public_forward_capture_cli_stage21c_v1 arm \
  --bundle-dir "$HOME/mmt-research/bundle-001" \
  --first-symbol XBTUSDTM --second-symbol ETHUSDTM \
  --ack-public-readonly-get
```

**After** arming and after the chosen future windows are entirely closed, run **one** SEAL. These example timestamps are illustrative, not dates automatically suitable for your actual arming moment:

```sh
MMT_NONPRODUCTION=1 python -m naseri_markets.public_forward_capture_cli_stage21c_v1 seal \
  --bundle-dir "$HOME/mmt-research/bundle-001" \
  --first-symbol XBTUSDTM --first-timeframe 15m \
  --first-start 2026-10-13T10:00:00Z --first-end 2026-10-13T11:00:00Z \
  --second-symbol ETHUSDTM --second-timeframe 5m \
  --second-start 2026-10-13T10:00:00Z --second-end 2026-10-13T10:20:00Z \
  --ack-public-readonly-get
```

If and only if a valid sealed bundle exists, an explicit separate PAPER simulation can be run:

```sh
MMT_NONPRODUCTION=1 python -m naseri_markets.public_forward_capture_cli_stage21c_v1 replay \
  --bundle-dir "$HOME/mmt-research/bundle-001" \
  --state-dir "$HOME/mmt-research/paper-001" \
  --ack-offline-paper
```

`--dry-run-signals` enables local no-send journal entries; the default is **PAPER only**. Replay does not attempt a live market scan, publish a signal or communicate with a broker.

## Contract economics and data integrity LIMITS

**Stage 21D update:** The previously documented Stage-21C restriction on account-wide multiplier is resolved for the opt-in Stage21D PAPER replay: Stage3/8/9 now reserve risk and compute modeled PnL using immutable **per-instrument contract multiplier, lot-size, price-tick and fee** records, frozen per order. See [Stage21D detailed contract](CONTRACT_AWARE_PAPER_STAGE21D_V1.md). The Stage21C snapshot remains public and unsigned; economic output still does not attest real trading.

- `contract_economics_gate = MODELED_PER_INSTRUMENT_APPLIED_UNATTESTED`
- `real_exchange_contract_pnl_verified = false`
- `exchange_signature_verified = false`
- `profitability_proven = false`

The capture describes public HTTPS provenance as `PUBLIC_HTTPS_UNATTESTED`. SHA256 is only local content identity, **not a signed KuCoin observation or immutable external timestamp**. Operator-provided HTTP transport in tests is always separately labeled `INJECTED_TEST_TRANSPORT`. No proof of Internet availability, authentic historical contract eligibility, region-specific futures trading eligibility, full fill quality, true fees/slippage or future profitability exists.

## Acceptance and remaining release gates

CI uses fixed public-format fixtures and checks refusal on nonproduction/consent fences, invalid contract geometry, historic lookback, incomplete bars, tampering, no network on refusal, two-source forward capture, optional offline PAPER replay plus clean installed wheel. Retains Stage19/20/21A/B regression suites. Tests never connect to real KuCoin or any account.

For economically meaningful multi-symbol PAPER, **per-instrument contract units/multipliers/lotSize and per-symbol commissions must be represented in the durable risk/PnL ledger and reconciled with source metadata**. Provider licensing, country eligibility, real fetch success on an expressly approved research machine, feed provenance verification and real Al Brooks Core API adapter also remain open. Nothing in Stage 21C makes this project production-ready or authorizes LIVE trading.

**No** production bot, VPS, API credentials, legacy 0.3.2 runtime, NY First-Reversal private core or Telegram messages changed.
