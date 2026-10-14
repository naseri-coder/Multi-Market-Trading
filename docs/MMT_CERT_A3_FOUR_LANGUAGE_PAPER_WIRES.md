# CERT-A3 — four-language direct PAPER wire reproduction

**VERDICT: NONPRODUCTION CANONICAL WIRE PREPARATION ONLY, NO EXECUTION.**

CERT-A1 inventoried all 15 file types but could accept fabricated,
unattested stage-review dataclasses. CERT-A2 directly replayed CSV/Parquet
and a restricted Pine indicator subset. CERT-A3 closes the remaining
replay-calculation gap for Python, JavaScript, TypeScript and WASM by
reconstructing canonical RUNTIME-A1 request frames directly from the
same SHA-pinned DATA-A1 file and source byte submissions.

The purpose is to prove that the local software can reproduce the SAME
causal data scope and frame counts across four formats — never that the
different strategies are semantically equivalent, safe or executable.

## Exact contract

Call reproduce_four_runtime_wires with:
- An absolute offline local CSV/Parquet path, matching HistoricalFileSpec
  (at most 2048 rows), typed CoreManifest and CoreBinding.
- Exactly four RuntimeSourceSubmission values, one per RuntimeKind:
  Python (.py), JavaScript (.js), TypeScript (.ts), WASM (.wasm). All must
  have filename, nonempty bounded exact bytes and SHA256 digest.
- Optional previously obtained DATA-A1 intake report and wire review claims.
- MMT_NONPRODUCTION=1, absence of MMT_PRODUCTION=1, and operator_ack=True.

CERT-A3 calls CERT-A2 to reverify actual dataset bytes, then calls the
existing DATA→RUNTIME wire-building function once for each language.
Recomputes all four frame traces and verifies they agree on data hash,
feed source reference, instrument, timeframe, core/binding identity,
total bars, warmup bars, prepared-frame count and ready timestamps.

A matching previous review must be byte-for-byte identical as a typed
report. Forged booleans or counters fail. Differing source formats
naturally have DIFFERENT request-transcript hashes; comparing those
SHA256 values for equality would be an incorrect semantic equivalence
claim. Each trace is instead committed separately into the final digest.

## No authority is created

The four source files are inspected as untrusted DATA, not imported or
evaluated. No Python exec, JavaScript runtime, TS transpilation, WASM
engine, Docker process, market transaction, order, broker, Telegram,
live account or database write is invoked.

A valid four-language PAPER wire means an inert CoreInput/request packet
was built. It does NOT mean the strategy ran, generated any valid
CoreResult, traded, matched another language's strategy logic, or
passed a real gVisor/native host confinement assessment.

Publisher hashes, broker market data, independent custody, latest
checkpoint, signing identity, Point-in-Time provenance, terminal
behavior and hardware sandbox are NOT authenticated here. All source,
host, execution, order, Telegram, broker, quarantine-release and
production release approval booleans remain FALSE. RUNTIME-A6
unconditionally denies Worker launch.

## Validation

The dedicated GitHub Actions workflow uses synthetic local CSV and
actual PyArrow Parquet with multiple row groups, four inert source-byte
fixtures, real canonical frame serialization, and existing DATA-A1 /
CERT-A2 / DATA→RUNTIME / A6 test suites.

Negative cases cover missing/duplicate source language, wrong file
extension, wrong SHA256, oversized bytes, altered historical source,
conflicting manifest or binding, forged stage receipts, production
environment, absent acknowledgement, subprocess/network attempts and
the mandatory A6 Worker hard stop. No native code is executed and
no TradingView, MetaTrader or live trading service is contacted.

**STATUS: CERT_A3_FOUR_LANGUAGE_PAPER_WIRES_REPRODUCED_EXECUTION_DENIED.**
