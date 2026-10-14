# RUNTIME-A10 — Offline evidence history and external-pin comparison

**Status: NONPRODUCTION PREPARATION — NO INDEPENDENT STORAGE OR HOST.**

The A5 nonce ledger and A9 inert ticket ledger use local SQLite. Both may
be rolled back by replacing the whole database file with an older, internally
valid copy. Database integrity and local event hashing alone do not protect
against that kind of full rollback.

## Scope implemented

A10 adds a separate, local, non-executable evidence index:
- Records only SHA-256 *claims* labeled A5_CONSUMED_REVIEW,
  A7_HOST_OBSERVATION, A8_SOURCE_LOCK or A9_SPENT_REVIEW.
  It stores no secrets, receipt bodies, tokens, or executable Worker files.
- SQLite application ID, private owner-only directory and file, FULL sync,
  atomic BEGIN IMMEDIATE appends, and contiguous predecessor-linked SHA-256.
- Rejects malformed records, gaps, tampered chain, unsupported event types,
  time regression, unsafe file permissions and unauthorized operators.
- Exports a canonical ledger identifier, sequence and head hash labeled
  LOCAL_EXPORT_NOT_INDEPENDENTLY_STORED.
- Requires a separate caller-supplied byte-exact pin for comparison. Checks
  its hash at its *sequence*, rejecting a locally restored shorter database,
  history divergence and an unrelated ledger identity.

## Critical limitation

A10 does NOT store the checkpoint outside the local host and cannot verify
that the supplied bytes came from genuine independent custody. A locally
generated or compromised pin is not a security guarantee. An old genuine
pin can attest only to the prefix up to its sequence, not later unpinned
records. An attacker controlling both ledger and supplied checkpoint can
forge two mutually consistent files.

SHA-256 supports comparison to a trusted independently held digest; it is
not signer identity, source provenance, trusted time, host sandbox proof or
distributed rollback resistance. Matching a checkpoint cannot authorize
execution, remove quarantine, enable broker operations or send Telegram.

## Future external custody gate (not accomplished here)

1. Designate an operator-owned, independently protected storage location
   outside any worker execution and production host. None has been designated.
2. Authentically seal ledger ID, head sequence and hash in tamper-evident,
   monotonic storage there. Preserve prior checkpoints and audit timestamps.
3. Retrieve the pin out-of-band; separately authenticate its source and
   freshness before providing it to A10's comparison method.
4. Red-team forged pins, stale pins, full restore/rollback, altered DB chain,
   stolen review keys, unauthorized operator and compromised host cases.
5. Only a separate authorized implementation may decide how a successful
   physical attestation becomes a narrow, revocable runtime capability.

No VPS, external account, network service, GitHub artifact custody, Worker,
Docker container, trading core, production PostgreSQL or Telegram service
was touched. The A6 mandatory Worker launch-denial barrier is unchanged.

## CI

The tests use ephemeral mock-only local SQLite databases. They deliberately
restore an old local copy and compare it against a newer pin kept in test
memory; this verifies the algorithm, NOT genuine independent storage.

The workflow also includes A9 and A6 regression tests and Ruff.

**Verdict: RUNTIME_A10_OFFLINE_PIN_COMPARISON_PREPARED_EXTERNAL_CUSTODY_REQUIRED.**
