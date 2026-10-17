# MMT-R23 — Termux portable Brooks forward evidence preparation

**Research only; no connected PAPER, orders, production writes, periodic tasks or trading account.** This solves the practical Draft-branch GitHub workflow_dispatch limitation without merging to main or provisioning a server.

## Exact existing immutable evidence

- Actual FreeTSA-signed plan SHA256: c557e8792ff7f097ee483903e2e6702c622a20f3975af898ee9aca7e257ad94d
- Genuine external RFC3161 timestamp response SHA256: 2e36862213d0f32cffadf161b3edae2610b03eef32f49e3b368253b49f83cf75
- Entire original GitHub artifact ZIP SHA256: 7e05a160c1f4dc0740ca18604456924df81e8254a3455dab76643f9106809868
- Original GitHub Actions run 38835965013, original artifact ID 12019181218, 30-day retention. User-downloaded filename: STAGE21E_REAL_EXTERNAL_BROOKS_RFC3161_PRECOMMIT.zip
- Cryptographically signed Oct 16 2026 at 01:36:00 UTC. Research timeframe BTCUSDT USD-M 15m, from Oct 20 2026 00:00 to Nov 3 2026 00:00 UTC. **The other, accidentally generated timestamp is not canonical.**

MMT R23 checks the **entire original ZIP SHA**, all eight original member names and byte SHA digests, rejects path traversal, symlinks, duplicate/unexpected files and oversized objects, and verifies the original timestamp **with real OpenSSL RFC3161 signature, imprint, signer EKU and chain checks**. It does not create any new timestamp or change the original economic or Brooks strategy configuration.

## Android / Termux manual preparation

Download the actual original public FreeTSA artifact ZIP to Android Downloads (no private signing keys or API secrets included). On Android's Termux:

~~~bash
pkg update
pkg install -y python openssl git
termux-setup-storage
git clone --depth 1 --single-branch \
  --branch feature/mmt-r23-termux-original-witness-forward-first-capture-v1 \
  https://github.com/naseri-coder/Multi-Market-Trading.git \
  "$HOME/mmt-r23-source"
mkdir -p "$HOME/mmt-r23-research"
cd "$HOME/mmt-r23-source"
MMT_NONPRODUCTION=1 MMT_PRODUCTION=0 \
python scripts/mmt_r23_termux_brooks_manual_forward_v1.py \
  --ack-research-only prepare \
  --original-zip "$HOME/storage/downloads/STAGE21E_REAL_EXTERNAL_BROOKS_RFC3161_PRECOMMIT.zip" \
  --evidence-dir "$HOME/mmt-r23-research/original-witness"
~~~

The ZIP can be accessed using the **actual** Android Downloads filename. Its bytes must match the pinned SHA; never re-zip or replace the reference. The prepared witness and all future capture files are written under Termux private HOME, **not Android public shared storage**. No account data or exchange credentials are requested. Preparation is fully offline.

Check the certified original plan without contacting Binance:

~~~bash
cd "$HOME/mmt-r23-source"
MMT_NONPRODUCTION=1 MMT_PRODUCTION=0 \
python scripts/mmt_r23_termux_brooks_manual_forward_v1.py \
  --ack-research-only status \
  --evidence-dir "$HOME/mmt-r23-research/original-witness"
~~~

Before Oct 20, expected state is AWAITING_FIRST_CLOSED_CANDLE. The phone's clock is **NOT independently attested** by this command even if network time sync is enabled.

### First manually authorized real data-capture opportunity

Only from **2026-10-20 00:15:05Z to 2026-10-20 01:15:00Z**, operator may explicitly choose a **single read-only public HTTPS GET**, with a complete original first closed 15m bar. Run Termux in foreground at the chosen time; no background timer exists.

~~~bash
cd "$HOME/mmt-r23-source"
MMT_NONPRODUCTION=1 MMT_PRODUCTION=0 \
python scripts/mmt_r23_termux_brooks_manual_forward_v1.py \
  --ack-research-only capture \
  --evidence-dir "$HOME/mmt-r23-research/original-witness" \
  --output-dir "$HOME/mmt-r23-research/first-real-capture-20261020" \
  --bars 1 \
  --confirm-one-readonly-public-get I_APPROVE_ONE_READONLY_PUBLIC_BINANCE_GET
~~~

The one-hour deadline applies to the **complete received HTTP response**. The R23 entrypoint does not override the stricter Stage21G start/end/window checks. It must refuse an early or missed study window; there is no force flag, clock backdating, historical backfill disguised as forward, repeated network request or silent source substitution. Additional first-batch choices 4/16/32/96 bars have different authorized completion times and are still optional single operator invocations. There is no multi-day continuous collector.

## What is preserved and what is NOT proven

On success the existing Stage21G first-window collector exclusively writes attempt.json, original-venue-response.json (original bytes), canonical-reviewed-closed-candles.csv, stage21f-quarantine-receipt.json and source-tls-http-observation.json in a fresh destination; each file refuses overwrite. On a started attempt that fails, a sanitized failure-ledger.json is retained. Never blindly retry or discard a failed attempt, and never infer an exchange outage from a local connection problem.

Observed HTTPS TLS certificate, hostname validation, original HTTP Date, source status and body hash are client transport evidence only. Binance did NOT digitally sign the original Kline observations for this research; mobile device clock is not externally attested, market-history corrections remain unproven, funding/mark/fill/account-specific fees remain unresolved. No live trading, connected PAPER, strategy decisions, real net PnL or prospectively verified OOS edge is claimed.

Binance service may refuse public API access by venue/provider policy or jurisdiction. No bypass, mirror, proxy or unaudited replacement endpoint is used.

## GitHub execution and quality gates

This new source branch is stacked on Draft R22 PR #314 and all earlier research branches. It does not merge to main. GitHub's Stage21G manual workflow definition remains on a feature branch and generally requires default-branch installation before Actions UI dispatch. The local Termux CLI is the chosen **non-default-branch, non-server lane**. This has not been executed on a user's Android device.

An R23 **offline-only** GitHub CI job downloads exactly the existing original FreeTSA evidence files from run 38835965013, re-verifies their exact pins and genuine signed cryptographic receipt with OS OpenSSL, and asserts zero market candles/active trading. It does **not** request Binance data. Source ZIP negative unit tests use synthetic fixtures and do not fake actual signature trust. The original real ZIP was separately verified in a local independent OpenSSL environment.

Full Public Test Corpus, Ruff and genuine CodeQL/Publication Safety must pass on the final commit. GitHub security audit PR #309 remains **NEVER MERGE**. R23 readiness is not authorization to deploy, trade, use Telegram, or produce an OOS profit claim.

**Target state: MMT_R23_PORTABLE_ORIGINAL_WITNESS_READY — FIRST_REAL_MANUAL_CAPTURE_PENDING.**
