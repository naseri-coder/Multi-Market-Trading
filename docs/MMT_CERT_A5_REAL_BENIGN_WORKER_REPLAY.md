# CERT-A5 — genuine four-language harmless fixture replay

**Status: GitHub nonproduction implementation candidate.**

**Do not interpret this as host isolation certification, strategy certification,
an ability to execute user uploads, or trading authority.**

## Why CERT-A5 exists

CERT-A4 compared four caller-created synthetic CoreResult streams with
DATA-A1-derived CoreInput and verified causal identity, hash and shape.
It did not actually run Python, JavaScript, TypeScript or WASM.

RUNTIME-A2 already contains real four-language worker interpreters, exercised
with fixed harmless fixtures. CERT-A5 adds the missing integration test:
the same SHA-checked real CSV and real Parquet historical inputs are decoded
through the existing OfflineMarketDataEngine, converted to causal canonical
RUNTIME-A1 frames, and sent to the standalone existing A2 fixture worker.

## Exact bounded tests

- Both actual CSV and PyArrow Parquet sources, three historical bars each;
  minimum lookback two; exactly two ready CoreInput events per format.
- Each ready event reaches a fixed literal, reviewed test fixture in each
  of the four language engines (Python, Node JavaScript, transpiled TypeScript,
  and fuel-limited Wasmtime). Exactly 16 genuine Worker roundtrips in the two
  positive test cases.
- Each fixture computes an inert NO_SETUP result with a decision identifier
  derived from the event's closed candle count. The WASM fixture distinguishes
  the two pinned event lengths via its fixed memory-only ABI; it is not a
  general-purpose trading strategy.
- The original trusted parse_core_result rechecks each real response against
  its actual event and CoreManifest: digests, observed time, bindings and
  decision structure. Cross-language fixture decision identifiers must match.
- Separate negative tests reject a modified framed source digest and a forged
  response binding identity.
- The same dedicated test job reruns RUNTIME-A6's unconditional denial tests
  and treats every skipped test as a failure.

## Nonproduction execution limitations

- **Only literal fixtures committed with the tests may execute.** Never
  replace them with uploaded, arbitrarily modified or unreviewed strategies.
- The tests run on a GitHub-hosted CI runner using A2's fixed child
  interpreters. Python -I/-S, Node vm and Wasmtime execution do not certify
  the entire host as isolated from hostile code.
- CI runner execution is not independent rootless Docker + gVisor
  attestation. The A2 OCI candidate still has mutable/unattested dependencies
  requiring separately reproducible pinned images and external provenance.
- The local files contain synthetic historical prices. A genuine CSV/Parquet
  decoder result does not authenticate market origin, Point-in-Time vendor
  history or broker execution.
- The fixture exercises event-dependent shape, not actual trading strategy
  semantics. It does not prove PnL parity, profitability or independent
  source custody.
- The tests do not modify installed strategies, the public engine registry,
  the Runtime-A1 dispatch path, A6, quarantine, production settings, database,
  Telegram, broker, account funds, or deployment.
- A passing test neither calls nor disables the A6 launch fence. The A2
  standalone fixture harness remains separate from the A1/A3 launch path.

## Required acceptance

1. Dedicated CERT-A5 GitHub job must pass with no skipped tests.
2. A6 denial regression must pass.
3. Diff must contain test, documentation and workflow only.
4. All real user-uploaded execution and trading/publication permissions remain
   DENIED until a separately designated disposable host is independently
   certified and a new explicit authorization is supplied.

## Verdict vocabulary

- Before CI is confirmed: CERT_A5_IMPLEMENTED_CI_NOT_YET_VERIFIED.
- After the dedicated CI passes: CERT_A5_BENIGN_WORKER_REPLAY_PASS_A6_DENY.
- Never claim: INDEPENDENT_HOST_ISOLATION_CERTIFIED,
  ARBITRARY_USER_CODE_EXECUTION_APPROVED, TRADING_READY.

**Next external dependency:** a dedicated expendable host with verified
rootless Docker + gVisor, immutable toolchain/image hashes, trustworthy
supply-chain custody, and real negative containment exercises. Do not use
TELMIVO, license-authority or trading production servers for that purpose.
