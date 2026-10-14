# CERT-A4 — Synthetic four-language CoreResult contract replay (NO Worker execution)

**Verdict: CERT_A4_SYNTHETIC_RESULT_CONTRACT_REPLAY_ONLY_ALL_EXECUTION_DENIED**

Baseline: CERT-A3 at main SHA cf49f0ad24cdef746a583da0b0d1a388809c759b.
A3 confirmed that four canonical Core API request wire traces can be
reconstructed from a pinned dataset. It did **not** execute four strategy
implementations or produce genuine CoreResult messages. A4 does not
change that security boundary.

## What this stage actually tests

New library: naseri_markets/cert_a4_synthetic_result_contract.py

1. Requires explicit MMT_NONPRODUCTION=1 and operator_ack=True. Denies
   MMT_PRODUCTION=1. Uses a fixed, local SHA256-pinned DATA-A1 CSV/Parquet
   historical dataset (maximum 512 rows) and existing CoreManifest and
   CoreBinding. All files are read-only.
2. Recreates the full **A3 four-language wire fingerprint** from the
   submitted Python, JavaScript, TypeScript and WASM *source bytes*.
   It can compare an optional older A3 report, rejecting forged fields.
3. Accepts exactly four corresponding **synthetic** CoreResult streams,
   one per language, of exactly the expected number of ready frame events.
   The caller must explicitly mark the origin SYNTHETIC_TEST_FIXTURE_NOT_WORKER_OUTPUT.
4. Re-reads the same DATA-A1 dataset, produces actual typed closed-bar
   CoreInputs through the existing offline market-data engine and rejects
   future, mismatched, stale or misplaced identities, source references,
   input digests, timestamps, setups, duplicated decision IDs, unsupported
   decision batches, and entry stop/target geometry.
5. Recreates each CoreDecision and CoreResult dataclass before validation.
   Frozen Python dataclasses can otherwise be mutated via object.__setattr__
   after construction; checking only the outer CoreResult would be weak.
6. For each bar, requires all FOUR operator-supplied decision traces to
   match exactly, reporting a domain-separated trace hash and separate
   full report fingerprint. A synthetic ENTRY_INTENT is treated as data
   shape validation **only**: there is no translation into SignalIntent,
   PAPER simulator, order routing or trading bot.
7. Any inconsistent or forged synthetic claims fail closed. Returns
   only aggregate counts and identities, not strategy code, market candles,
   broker credentials or individual orders.

The positive CI fixtures contain two ready closed bars (and one warmup
bar), with one manufactured NO_SETUP result and one manufactured valid
ENTRY_INTENT per language. They are NOT outputs of executed Python,
JavaScript, TypeScript or WASM strategies. Even exact agreement of all
four fixtures **does not demonstrate strategy semantic equivalence**.

## Explicit remaining certification blockers

- Independently obtained and authenticated real market data, Point-in-Time
  history, time/session/contract semantics and controlled quality evidence.
- Real four-language **execution** inside an independently certified
  disposable no-secrets/no-network runtime, including timeout, isolation,
  crash, revocation and restart validation.
- Independent origin and custody of real CoreResult traces; arbitrary
  caller-provided dataclasses, even matching perfectly, can be forged.
- Actual strategy-level equivalence and PnL parity after realistic market
  costs, which cannot be deduced from two synthetic signals.
- Independent signer and checkpoint custody, trusted monotonic versions.
- Explicit later approval is needed to reconsider any A6 launch gate.

Every authority field (actual_worker_results, source provenance, PAPER
strategy execution, PAPER orders, broker orders, Telegram, quarantine
release and production release) remains FALSE. The original A6 launcher
is not modified. No MetaTrader, TradingView, native binary, Docker Worker,
production server or real trading service is invoked.

## CI

.github/workflows/cert-a4-synthetic-core-results.yml uses pinned Python,
Ruff, pytest and PyArrow. It verifies true CSV/Parquet decoding, accurate
CoreInput digests, correct synthetic decision reconstruction, valid
ENTRY_INTENT geometry without execution, corrupted/stale/changed binding
and hash refusals, four-language disagreement, output count mismatch,
forged dataclass mutation, production-mode rejection, prevented process
and network use, and A6 unconditional launch denial.

**PAPER contract shape may be checked; actual strategy is still not run.**
