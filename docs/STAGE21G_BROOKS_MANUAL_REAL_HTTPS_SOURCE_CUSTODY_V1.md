# Stage21G — One-Shot Read-Only HTTPS Source Custody

**Research-only code preparation. No actual October 20+ market candles, no connected PAPER, no brokerage account and no live orders.**

## Frozen source and witness

- The canonical externally RFC3161-signed Brooks plan remains SHA256 c557e8792ff7f097ee483903e2e6702c622a20f3975af898ee9aca7e257ad94d, first signed 2026-10-16 01:36 UTC.
- Original FreeTSA response SHA256 2e36862213d0f32cffadf161b3edae2610b03eef32f49e3b368253b49f83cf75.
- Study BTCUSDT USD-M 15m: 2026-10-20 00:00 to 2026-11-03 00:00 UTC.
- The canonical original signed artifact is source GitHub Actions run **38835965013**, artifact ID **12019181218**, name stage21e-external-rfc3161-brooks-preregistration, retained for 30 days from original issue. No second or replacement timestamp is accepted. Original plan is also in docs/evidence/STAGE21E_BROOKS_ORIGINAL_EXTERNALLY_TIMESTAMPED_PLAN_20261016.json.

## Implemented capabilities

The offline research module naseri_markets/brooks_forward_source_custody_stage21g_v1.py and CLI scripts/stage21g_manual_initial_brooks_capture_v1.py are nonproduction only.

1. Require explicit operator acknowledgment, MMT_NONPRODUCTION=1, ST21G_EXPLICIT_MANUAL_CAPTURE=1, and a fresh absolute private destination. Refuse production.
2. Rehash every original approved RFC3161 plan/token/public CA/signer file; reject missing, altered, linked or oversized originals. Stage21F then performs genuine Stage21D cryptographic verification.
3. Only request the first 1, 4, 16, 32 or 96 fully closed candles, always starting from October 20 midnight UTC. Begin no earlier than 5 seconds after last close and receive the response no later than one hour after that close. Stale or early attempts fail; there is no hidden retrospective backfill.
4. Make exactly **one** direct standard-library Python HTTPS GET at fapi.binance.com /fapi/v1/klines, with verified CA/hostname TLS 1.2+, no proxy, redirect, API credentials or automatic retry. Capture original response bytes, observed leaf certificate SHA256, TLS version, HTTP Date, status/content headers, local request/receipt time and a bounded duration. Require 200/application-json/identity encoding and reject implausible server-Date drift.
5. Admit the original response through Stage21F fixed 12-column closed-bar validation and Stage21C chronological hash chain. Preserve original raw response, normalized seven-column CSV, admission and TLS/HTTP receipts exclusively without overwrite.
6. On failed capture, preserve a sanitized failure ledger **without asserting that a client-side failure proves a Binance outage** and without retry. A separately callable original-byte comparator flags changed market source snapshots but forbids silently overwriting earlier evidence.
7. Never claim a trusted independent HTTP Date or receiver clock, provider-signed price feed, absence of historical revisions, actual forward Brooks decisions/fills, profitability/OOS, or PAPER authorization.

## Explicit manual GitHub Actions workflow

The workflow .github/workflows/stage21g-manual-brooks-public-kline-capture.yml has only workflow_dispatch and an opt-in authorization control with exact value I_APPROVE_ONE_READONLY_PUBLIC_HTTPS_CAPTURE. It is NOT scheduled and NEVER triggered by a PR or new commit. It uses pinned actions/checkout, actions/download-artifact and actions/upload-artifact commits with only actions:read / contents:read, downloads **the exact original signed artifact from run 38835965013**, and runs the collector once. Results/failure receipts are retained as an immutable per-run 30-day artifact.

**Operational limitation:** GitHub generally requires a workflow_dispatch definition on the default branch. Since this PR is Draft and must NOT be merged merely to enable a workflow, the manual workflow might not be usable from the Actions interface yet. A separately authorized isolated Python/Termux environment could invoke the same CLI if the original public signed evidence ZIP is already available. Neither path is activated in this stage.

| Initial batch size | Earliest one-shot fetch (UTC) | Latest admissible complete response (UTC) |
|---|---|---|
| 1 bar | Oct 20 00:15:05 | Oct 20 01:15:00 |
| 4 bars | Oct 20 01:00:05 | Oct 20 02:00:00 |
| 16 bars | Oct 20 04:00:05 | Oct 20 05:00:00 |
| 32 bars | Oct 20 08:00:05 | Oct 20 09:00:00 |
| 96 bars | Oct 21 00:00:05 | Oct 21 01:00:00 |

These are choices for future authorized manual execution, **not** automations. This stage intentionally handles only the **first batch**. A second batch requires separate reviewed immutable prior-receipt ingestion, corrections and outage policy; neither a source-capture timestamp nor a data-origin witness is yet independently attested.

## Acceptance boundaries

Run complete public unit tests, Ruff and true GitHub Advanced Security CodeQL plus protected Publication Safety on the exact final SHA, optionally through the existing **read-only, never-merge** main-target audit PR #309. Stage21G is developed after the signed Stage21E plan, so ingestion methodology also needs independent review before an OOS study is eligible. A valid TLS connection is useful transport evidence, not exchange-signed market data. Historical fee/mark/liquidation/real fill parity and genuine forward/OOS are still separate blockers.

**Target status: STAGE21G_ONE_SHOT_HTTPS_COLLECTOR_CODE_READY — FIRST_REAL_PROSPECTIVE_SOURCE_PENDING.**
