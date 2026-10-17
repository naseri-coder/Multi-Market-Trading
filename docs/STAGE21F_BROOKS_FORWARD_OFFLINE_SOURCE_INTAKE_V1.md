# Stage21F — Offline Binance USD-M Future-Candle Admission (Brooks)

**MODE: NONPRODUCTION VALIDATION PREPARATION ONLY. No network fetch, subscription, scheduler, exchange order, broker connection, background PAPER service, production change or future-data performance claim.**

## Canonical frozen campaign

This stage is strictly bound to the **first** externally stamped prospective Brooks plan from Stage21E; it cannot silently register a new version or substitute the accidental second notarized study plan.

| Immutable basis | Value |
| --- | --- |
| Original plan SHA-256 | `c557e8792ff7f097ee483903e2e6702c622a20f3975af898ee9aca7e257ad94d` |
| Original RFC3161 response DER SHA-256 | `2e36862213d0f32cffadf161b3edae2610b03eef32f49e3b368253b49f83cf75` |
| FreeTSA root PEM SHA-256 | `2151b61137ffa86bf664691ba67e7da0b19f98c758e3d228d5d8ebf27e044438` |
| FreeTSA signer PEM SHA-256 | `8bfb0305bb64e2571ca507552ef3245cb1c2fee8728e0ff8689225081ea13467` |
| Issued signed timestamp | `2026-10-16T01:36:00Z` |
| Future study start / end (UTC) | `2026-10-20T00:00:00Z` to `2026-11-03T00:00:00Z` |
| Market | Binance USD-M futures BTCUSDT, 15-minute closed Klines |

The original 709-byte plan is held in `docs/evidence/STAGE21E_BROOKS_ORIGINAL_EXTERNALLY_TIMESTAMPED_PLAN_20261016.json`. The **original binary timestamp token and both public certificates** were saved as GitHub Actions artifact `12019181218` (30-day retention) and in the Stage21E user-delivered ZIP. For real input, those exact original bytes must be supplied; substitutes do not pass the pins. Local tests **mock Stage21E's already-tested cryptographic primitive** when testing synthetic market payloads; they do not claim possession of a venue-signed future candle.

## New pure, network-free Stage21F adapter

`naseri_markets/brooks_forward_http_intake_stage21f_v1.py` accepts the complete signed Stage21E witness evidence, operator-supplied original Binance USD-M `fapi/v1/klines` JSON response bytes, declared request URL/HTTP status/content type/Date header, an operator-supplied aware UTC observation time, and optionally the previous genuine Stage21C locally hashed receipt. It:

1. Requires `MMT_NONPRODUCTION=1`, Production not equal to 1 and explicit operator acknowledgement **before all work**. Validates the exact original campaign SHA pins and actually calls `verify_brooks_rfc3161_precommitment` with the raw original signed token and certificates, then insists on the **first** 2026-10-16 01:36 UTC stamp.
2. Accepts only `200` JSON response claims for the **single exact canonical read-only request** `https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=15m&startTime=<first_open_ms>&limit=<record_count>`. A claimed URL/Date/HTTP 200 **does not itself prove origin**. No API keys, account routes, headers carrying secrets, parameter alternatives, redirects or live market calls are used.
3. Requires **raw original byte SHA-256** and 1–96 exact 12-field REST Klines. Refuses partial/empty malformed JSON, invalid types/floats/prices/volumes/OHLC, unaligned/open or closeTime-mismatched 15m grid, missing/duplicate/reordered bars, unexpected reserved field, surplus bars and unsupported payload sizes. Converts Binance's inclusive `closeTime` in milliseconds to the original Stage21C's exclusive UTC `close_at` representation.
4. Requires the operator-claimed observation be 5 seconds to 10 minutes after the **last** closed bar, and a parseable claimed HTTP Date no more than 5 minutes behind that local timestamp. These are reasonable screening gates; the raw HTTP Date and local clock are **NOT cryptographically authenticated** and could be backdated.
5. Feeds the complete resulting source-pinned canonical CSV to the original Stage21C `review_brooks_forward_candle_receipt`, enforcing exact alignment with the notarized study's first bar and each previous recorded receipt. Returns the full SHA-256-linked Stage21C receipt, canonical CSV bytes, and new Stage21F provenance report, without writing to a database or dispatching trades.

The caller must save and protect original raw HTTP response bytes, the submitted captured response metadata, resulting normalized CSV, both receipts and any previous chain. The new adapter does not itself provide durable external storage or append-only evidence notarization. A malicious collector may still forge locally asserted HTTP headers, bytes and observation times and recompute ordinary hashes: the signed precommitment covers the **study plan**, not newly acquired market data.

## Mandatory labels — NEVER upgrade without independent evidence

The admission report always declares `actual_issuer_signed_price_message_verified=false`, `https_tls_session_evidence_verified=false`, `independent_capture_clock_verified=false`, `future_market_data_prospectively_verified=false`, `actual_forward_brooks_engine_evaluated=false`, `verified_out_of_sample_profitability=false`, `connected_paper_authorized=false` and `live_trading_authorized=false`. It is not an automated feed or a broker-order execution journal.

Tests use **synthetic future October 2026 candles**, a mocked pre-existing signed-plan cryptographic entrypoint (the Stage21D tests separately exercise actual OpenSSL cryptography), time and sequence tampering, and explicit absence-of-network checks. They are *not* evidence of genuine October 20 market observations.

## Pending before genuine OOS or active PAPER

A separately approved network collector with immutable **provider-origin custody**, external receipt timestamp witnessing, outage/revision monitoring, independently reviewed TSA legal trust policy and real Futures fee/position/fill/mark evidence is required. The first true prospective bar cannot exist until **2026-10-20T00:15:00Z** has actually elapsed. No capture, trade, validated OOS or profitability result is claimed here. Native protected GitHub Advanced Security CodeQL and Publication Safety are required on the exact final commit; do not disable, imitate or bypass either. All PR dependencies are Draft/unmerged.

**Target acceptance:** `STAGE21F_OFFLINE_FUTURE_INPUT_ADMISSION_CODE_PASS_REAL_FEED_AND_EXTERNAL_RECEIPTS_PENDING`.
