# Multi Market Trading — A26 Atomic Permission Fencing & Revocation Consistency

**Non-Production only, public generic Custom synthetic PAPER signals.**

## Why A26 is different from A24/A25

A24 and A25 verified signed publisher/operator admission before and after
asynchronous sandbox activity. However A22 `PaperJournal.record_batch()`
began its own write transaction after the check. An installation or publisher
revocation could COMMIT between the last trust check and PAPER insertion.

A26 introduces an **opt-in transactional fence**:
- `CustomPaperRuntimeBridge(..., require_atomic_fence=True)` rejects all
  unfenced `dispatch()` calls with no fallback to the legacy A7 journal.
- `AtomicGuardedFixedSession` accepts the existing A25 double-signed inert
  bundle gate and A23 hardcoded, low-privilege fixture only. It checks trust,
  A22 enabled/revision, relays fixed **non-executable PAPER bytes**, checks
  again and calls A22 with an exactly typed bound A26 gate and explicit
  synthetic authorization clock.
- `AtomicPaperCommitFence` attaches **three distinct local SQLite files**
  to the existing A7 journal connection: A24 publisher + installation trust,
  A25 artifact floor, and A7 PAPER journal. It uses a single
  `BEGIN IMMEDIATE` transaction to take SQLite writer reservations over
  the attached databases BEFORE reading final revocation and sequence.
- Under those writer locks, it rechecks A24 and A25 revoked flags, current
  publisher public key and independent operator key, valid signatures
  from the pinned trust records, exact installation/engine/version and
  descriptor, active A22 PAPER permission, both exact signed admission and
  artifact SHA-256s, revision, sequence, expiry and timestamp. **No await
  or user-supplied callback runs between locked checks and SQL COMMIT.**
- The very same transaction writes the A7 PAPER-only intent rows. If any
  check or duplicate-identity conflict fails, `ROLLBACK` removes all
  pending inserts. Existing identical signal IDs remain idempotent.
  Any concurrent SQLite revoke/sequence advance must wait until the
  transaction releases its write lock. If revocation already committed,
  A26 rejects and writes nothing; if the PAPER transaction linearizes
  first, a later revoke cannot retroactively erase its prior authorized
  PAPER record.

## Tested races and scope

The isolated `tests/unit/test_a26_atomic_fence.py` creates actual
A24/A25 signatures and SQLite ledgers, the A23 low-privilege Linux
cgroup/seccomp relay, A22 PAPER bridge and journal. It tests forged or
stale admission, publisher/installation/bundle revocation, expiry,
release supersession, disabled A22 toggle, strict no-fallback gating,
zero-write denial, duplicate idempotency, partial batch rollback and
**two real concurrent writer threads** attempting to revoke A24 or
A25 from separate SQLite connections WHILE the A26 transaction holds
writer locks. Those threads must remain blocked until COMMIT and then
succeed. All tests run on disposable CI, no production database.

## Important precise guarantees and limits

**A26 provides a well-defined concurrency linearization point across
these locally attached SQLite databases**, not a fully independent
durability guarantee against sudden power failure: multiple ATTACHed
databases using WAL journaling do NOT have crash-atomic commits as a
group. All A24, A25 and A7 writes are still committed by their respective
SQLite writers, but an OS crash during a multi-database transaction
could result in inconsistent cross-file states. A future single-ledger
model or independently transactional service architecture is needed
for production-grade crash consistency.

Nor does A26 make the existing A22/A23/A24/A25 legacy development APIs
impossible to invoke: those are separate nonproduction fixtures. The
new explicitly fence-required A22 mode is the secured opt-in route,
not a global mandatory enforcement layer for all callers. The
`authorization_now` argument is a caller-provided TEST clock and is
not a tamperproof production time source. Locally stored SQLite
admission floors are not off-host tamperproof; a malicious host
administrator remains out of scope. Test injection hooks and direct
connection access are not production APIs.

The public product **still has NO real arbitrary third-party code
sandbox or executable plugin installer.** This stage passes only
precomputed data into a built-in fixed relay. No network, broker,
Telegram, live orders, private strategy code or production updates.

## Permanent owner boundary

NY First-Reversal is **OWNER_ONLY**, never publicly installable or
distributed, including compiled, obfuscated or encrypted artifacts.
An A26 fenced record cannot grant a commercial license or convert
any protected core into a public Custom plugin.

The A26 dedicated CI and full repository CI validate tests, Ruff,
immutable source history, public-only distribution and PostgreSQL
disposable resource cleanup prior to merge.

**Pass verdict: A26_SQLITE_CONCURRENT_REVOCATION_FENCED_NONPRODUCTION.**
