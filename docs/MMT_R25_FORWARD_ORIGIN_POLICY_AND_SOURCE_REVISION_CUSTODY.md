# MMT-R25 — Provenance Policy, Immutable Source Revision Journal and 14-Day Forward Operations

**NONPRODUCTION source research only. No trading, connected PAPER, scheduled collection, main merge or deployment.**

## Binding signed source, versus unsigned market evidence

- Genuine externally signed FreeTSA Brooks V5 PLAN SHA256: c557e8792ff7f097ee483903e2e6702c622a20f3975af898ee9aca7e257ad94d.
- Original external RFC3161 response SHA256: 2e36862213d0f32cffadf161b3edae2610b03eef32f49e3b368253b49f83cf75.
- Signer timestamp: 2026-10-16 01:36:00 UTC.
- Signed prospective study: BTCUSDT Binance USD-M, 15m, Oct20 00:00 to Nov3 00:00 UTC.
- External public original artifacts fetched and verified in R23. R25 re-runs R23's real OpenSSL crypto and R24's complete prior source replay, not just an existing PASS flag.
- No alternative or second-signed plan, Brooks strategy/source change, retuning or forged prior observations are permitted.

Four different provenance claims must NOT be conflated:

| Subject | Evidence now available | Honest interpretation |
| --- | --- | --- |
| Pre-study PLAN existed at a signed UTC time | Original RFC3161 signed plan under pinned public certificates | Plan was cryptographically timestamped, NOT actual market data |
| Data was received through a client-observed secure transport | CA-checked HTTPS, certificate hash, HTTP Date, retained raw body and local SHA | Original local transport claim; not independent venue-signed data provenance |
| Data was received at a particular UTC time | Phone/runner clock and unsigned HTTP Date | UNATTESTED independent reception time |
| Dataset has no historical corrections, is suitable for OOS | Original local custody hash chain, later candidate comparisons | Not independently established; provider revisions, source gaps, real fill/fee evidence remain pending |

There is no operator flag permitting elevation of those source trust statements. A real independent attestation would need verified identities, trusted external key governance, independently witnessed UTC content-receipt time, source-body digest, contemporaneous chain of evidence and separate methodology approval. A TLS padlock or SHA256 alone does not prove dataset authorship.

## Proposed 14-session forward data operations (not automated)

The immutable signed window is exactly 14 days = 1,344 consecutive 15-minute bars. The recommended manually initiated collection plan uses exactly 14 × 96-bar batches; it is calculated ONLY from the original signed plan and **is NOT an amendment of that plan or an unattended collector**.

- First batch: Oct20 00:00 through Oct21 00:00 UTC, earliest permissible manual request Oct21 00:00:05 UTC, complete response must arrive by Oct21 01:00:00 UTC.
- Next 12 daily batches: same five-seconds-after-midnight-to-one-hour window for Oct22 through Nov2 inclusive.
- Final 14th batch: through Nov3 00:00 UTC; manual request window Nov3 00:00:05–01:00:00 UTC.
- Each actual GET requires a separately acknowledged explicit manual operator command using existing R23 first-batch capture and R24 next-batch capture, not this R25 module. R25 has NO HTTP client and NEVER starts a job or connector.
- If the operator already captured only the FIRST one-bar batch, do not attempt to re-label it as a 96-bar first batch. Use R24-contiguous alternative window bookkeeping and independent review.
- A missed source window or client outage does NOT certify exchange outage; R24 writes gap/failure receipts and refuses replacement or retrospective backfill masquerading as prospective evidence.
- R24 maximum 128 prior batches permits 14 daily windows but cannot handle 1,344 separately captured one-bar windows without protocol review.

Because these operating and admission decisions post-date the external plan timestamp, **independent research-methodology review** is needed before reporting any confirmatory OOS. The 14-session schedule is a practical suggestion, not proof of valid future observations.

## Implementation and outputs

Module: naseri_markets/brooks_forward_source_governance_mmt_r25_v1.py
CLI: scripts/mmt_r25_offline_forward_provenance_review_v1.py

1. r25_fixed_manual_96bar_schedule re-verifies the original RFC3161 evidence, checks the exact signed plan, and renders 14 manual first-open/end/earliest/latest windows. An eligible window is not authorization to connect.
2. r25_offline_chain_governance re-verifies the signed PLAN and EVERY previous original R24 source folder before reporting an offline chain-readiness summary. It explicitly distinguishes signed-plan-with-no-source from revalidated local source. It cannot infer a Binance outage from a local missing interval.
3. r25_record_untrusted_revision_observation reads a separately operator-supplied, bounded original JSON file, replays the complete prior chain from the genuine signed plan, validates the candidate against the same BTCUSDT window and 12-column Kline schema, and writes an exclusive, append-only observation folder containing the candidate original bytes and a review receipt. **No accepted historical source folder is modified**.

The later candidate is UNTRUSTED even when it appears to come from Binance. Four possible comparison statuses:

| Status | Meaning | Action |
| --- | --- | --- |
| EXACT_RAW_BYTES_UNCHANGED | Locally submitted bytes are identical | No source trust upgrade |
| ORIGINAL_BYTES_CHANGED_CANONICAL_CANDLES_UNCHANGED | Raw bytes differ, canonical OHLCV CSV unchanged | Require human methods review; preserve both |
| CANONICAL_SOURCE_CANDLES_CHANGED_REVIEW_REQUIRED | Prices/volume or other canonical fields differ | Require human review; NEVER overwrite original |
| UNREADABLE_OR_WRONG_WINDOW_NOT_A_VALID_SOURCE_REVISION | Malformed JSON/price/time grid | Preserve invalid candidate as evidence; DO NOT accept |

All review reports explicitly set source issuer attribution, provider corrections, external receive time, independent OOS, PAPER and LIVE to **false/unverified**. A second source observation is neither a Binance signature nor a valid correction proclamation.

## Termux operator commands — offline only

Before genuine future data collection, use the original R23 verified witness in private Termux HOME.

Schedule, without a network request:

    cd "$HOME/mmt-r25-source"
    MMT_NONPRODUCTION=1 MMT_PRODUCTION=0 \
      python scripts/mmt_r25_offline_forward_provenance_review_v1.py \
      --ack-research-only \
      --witness-dir "$HOME/mmt-r23-research/original-witness" schedule

Policy audit after a REAL accepted first data batch (add every subsequent directory oldest-first):

    MMT_NONPRODUCTION=1 MMT_PRODUCTION=0 \
      python scripts/mmt_r25_offline_forward_provenance_review_v1.py \
      --ack-research-only \
      --witness-dir "$HOME/mmt-r23-research/original-witness" \
      audit --prior-batch-dir "$HOME/mmt-r23-research/first-real-capture-20261021"

Later independent operator-supplied raw bytes, journal WITHOUT modifying original:

    MMT_NONPRODUCTION=1 MMT_PRODUCTION=0 \
      python scripts/mmt_r25_offline_forward_provenance_review_v1.py \
      --ack-research-only \
      --witness-dir "$HOME/mmt-r23-research/original-witness" \
      compare --prior-batch-dir "$HOME/mmt-r23-research/first-real-capture-20261021" \
      --target-batch-index 0 \
      --later-original-response "$HOME/mmt-r23-research/later-untrusted-source.json" \
      --output-dir "$HOME/mmt-r23-research/review-later-source-one"

These commands never fetch market data. Actual one-shot market retrieval requires separately approved R23 or R24 commands. Termux Android device clock remains an untrusted source-time claim. No exchange API secrets or account credentials are needed.

## Hard acceptance blockers

| Gate | Status |
| --- | --- |
| Exact original signed study/recommended manual window verification | CODE/TST pending full CI |
| Complete local source chain replay, immutable revision journal | CODE/TST pending full CI |
| Genuine CodeQL and unmodified Publication Safety on final SHA | PENDING |
| Actual Oct20-Nov3 future market observations | NOT YET COLLECTED |
| Independent signed venue source/receive-clock attestation | NOT VERIFIED |
| Complete source revision and outage history | NOT VERIFIED |
| Historical futures economic fee, funding, fill parity | NOT VERIFIED |
| True prospective OOS edge / connected PAPER / LIVE | NOT VALIDATED OR AUTHORIZED |
| Server, main or production changes | NONE |

R25 is stacked on Draft R24 PR #316; all prior staged research PRs remain Draft. Read-only security-audit PR #309 is strictly **DO NOT MERGE**.

**Target outcome: MMT_R25_OFFLINE_POLICY_AND_SOURCE_REVISION_JOURNAL_CODE_PASS — REAL_PROSPECTIVE_SOURCE_AND_INDEPENDENT_ATTESTATION_PENDING.**
