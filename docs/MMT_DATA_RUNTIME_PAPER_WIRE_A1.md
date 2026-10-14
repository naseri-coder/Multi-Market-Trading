# DATA-RUNTIME-PAPER-A1 — inert offline bridge, not Worker authorization

Status: NONPRODUCTION SOURCE AND FIXTURE VALIDATION ONLY.

DATA-A1 already parses real local CSV/Parquet and validates all source rows.
RUNTIME-A1 already builds canonical framed requests for Python, JavaScript,
TypeScript and WASM. This phase connects the **two existing contracts**
while maintaining the unconditional RUNTIME-A6 launch-denial barrier.

## Implemented

Module: naseri_markets/data_runtime_paper_wire_a1.py

The host-supplied typed inputs are:
- Absolute on-disk CSV/Parquet path and exact HistoricalFileSpec SHA256,
  replay-only FeedDefinition and its claimed source reference.
- Explicit CoreManifest and CoreBinding with identical instrument, market,
  event and timeframe to the subscribed DATA-A1 feed.
- Explicit language, previously reviewed source bytes/filename/SHA256.
- MMT_NONPRODUCTION=1, MMT_PRODUCTION not equal 1, explicit operator ACK.
  Bounded maximum framed requests 1..2048.

The module fully validates the input file via DATA-A1 before delivering rows.
It then replays each packet into OfflineMarketDataEngine Stage 5, honors the
manifest warmup period, and checks causal CoreInput identities/timestamps.
Only for ready events does it call prepare_framed_request to validate and
construct the exact RUNTIME-A1 wire protocol. The resulting frame bytes are
immediately SHA256-hashed in a domain-separated ordered hash chain. Only
aggregated count, source/artifact digests, maximum frame size, first/last
ready observation time, identity and transcript digest are returned.
No raw frames, prices, source code or secrets are persisted or printed.

The module NEVER constructs or invokes MultiLanguageOfflineHost, _run_oci,
Docker, a Worker, strategy.evaluate, order routing, or Telegram. The
return value explicitly marks market provenance, point-in-time validation,
host attestation, strategy execution and all publication permissions FALSE.
A6 remains the unmodified unconditional Worker launch refusal.

### Limitations and release blockers

- A SHA256 pin and provider label prove equality to an operator-selected
  file, NOT authentic exchange provenance or historical availability.
- Replay availability_lag_seconds simulates causality, NOT historical
  provider feed/real session availability.
- Existing DATA-A1 file reading is not an atomic filesystem snapshot:
  privileged same-host concurrent rewrites could invalidate assumptions.
  Production-grade source custody requires immutable out-of-band evidence.
- Python/JS/TS/WASM framing tests use **static harmless source fixtures**
  and DO NOT execute those strategies. The actual isolated runsc/gVisor host,
  independently signed worker images and source/compiler chain-of-custody
  remain unresolved in A13. A1/A2 fixed fixture success is no host proof.
- max_frames=2048 bounds CPU and hashing per invocation. Any excess or
  incomplete/warm-only file fails closed without a success report.
- The output does not simulate a trade, perform a backtest or establish
  profitability. Real provider-certified historical market data remains
  unavailable until independently supplied.

### How to call (trusted operator-owned Python integration only)

Provide HistoricalFileSpec(feed, approved_sha256), CoreManifest and
CoreBinding; these must match by instrument and timeframe. Then call:

    review_file_to_runtime_wire(
        Path("/absolute/history.csv"), spec=spec,
        manifest=manifest, binding=binding, kind=RuntimeKind.PYTHON,
        artifact_name="reviewed.py", artifact=previously_reviewed_bytes,
        artifact_sha256=approved_artifact_sha, operator_ack=True,
    )

This is a library entrypoint, NOT an unauthenticated web upload endpoint,
and the operator must keep original files immutable during replay.

## Validation

Workflow: .github/workflows/data-runtime-paper-wire-a1.yml.
CI runs Ruff, original DATA-A1 tests, RUNTIME-A1 and A6 regressions plus
new CSV and **real PyArrow Parquet** multi-row-group fixtures.
Negative tests include wrong language/SHA/source, bad feed/binding,
warmup-only history, too many requests, tampered source, duplicate
market times, no operator/environment grant, no network and A6 hard stop.

VERDICT:
DATA_RUNTIME_A1_OFFLINE_WIRE_CONTRACT_PREPARED
REAL_MARKET_PROVENANCE_NOT_VERIFIED
WORKER_EXECUTION_STILL_DENIED_BY_A6.
