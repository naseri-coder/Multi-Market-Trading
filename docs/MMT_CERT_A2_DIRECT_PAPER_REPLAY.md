# CERT-A2 — direct pinned DATA-A1 and Pine evidence replay

**NONPRODUCTION DIRECT-CALCULATION REVIEW ONLY. NO EXECUTION AUTHORITY.**

CERT-A1 PR #256 and PR #257 already track 15 artifact extensions,
but PAPER inputs and Pine trace proof could be simple caller-created
dataclasses. CERT-A2 replays original bytes using the existing validators
instead of trusting submitted Stage report claims.

The cert_a2_direct_paper_replay module does the following:
- Requires MMT_NONPRODUCTION=1 and explicit acknowledgement, rejects
  MMT_PRODUCTION=1.
- Takes a SHA256-pinned local CSV/Parquet HistoricalFileSpec with at most
  10000 rows and a separately supplied absolute file path.
- Re-runs the A13 source audit for three permanent A6 launch-denial
  invariants and the actual DATA-A1 Stage-5 causal CoreInput data intake.
- If a previous DATA-A1 review is supplied, compares its entire dataclass
  to the regenerated report. Missing or forged fields cause refusal.
- Optionally accepts all four Pine proof components at once: strict Pine
  source bytes, source SHA256, complete oracle CSV and oracle SHA256.
  It parses only the approved six-statement closed-bar SMA crossover
  subset, reruns the full trace against the SAME history file and
  denies any mismatched signal, bar count, symbol or digest.
- If a previous Pine review is supplied, compares every field with the
  newly regenerated trace, including claimed provenance/authority.
- Returns a source-free fingerprint and row/trace counts. It never
  returns source content, executes a strategy or places PAPER orders.

These checks are independent CALCULATIONS in one local trust domain,
NOT independently authenticated exchange data, source publisher,
TradingView oracle, genuine Point-in-Time data or physical custody.
Even an exact match can be forged when an attacker supplies both data
and hash/expected trace. The maximum 10000-row cap prevents unbounded
Pine oracle retention. CSV/Parquet parsing remains in original DATA-A1.

The other thirteen current format extensions are still covered by
CERT-A1's static inventory; this narrower stage does not pretend that
arbitrary Python, JavaScript, TypeScript, WASM, MetaTrader, DLL/SO/EXE
or SDK programs can be safely executed as PAPER strategies.

The test workflow creates real CSV and PyArrow Parquet row groups,
checks full typed input reproduction, complete Pine SMA bar-by-bar
trace with positive and mismatched reference fixtures, modified file
hashes, forged previous dataclass claims, missing proof elements,
production/operator denials, subprocess/network interdiction and
unchanged A6 Worker launch denial. No real exchange dataset or
independently verified TradingView export was provided.

**STATUS: CERT_A2_DIRECT_REPLAY_REPRODUCED_ONLY_ALL_EXECUTION_DENIED.**
