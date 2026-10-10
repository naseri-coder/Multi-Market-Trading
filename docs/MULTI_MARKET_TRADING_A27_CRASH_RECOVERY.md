# Multi Market Trading — A27 Crash-Consistent Authorization Ledger & Recovery Fencing

**Status: NON-PRODUCTION / disposable PAPER-only / no public private strategy.**

## Boundary and precise objective

A26 serialized revocations across three *attached SQLite WAL files*. A
group of WAL databases is **not** power-failure atomic. A27 introduces a
SEPARATE, explicitly opted-into **single-file ledger** for the authority
grant state, terminal revocations, generation fencing and PAPER intents.

- One SQLite **main** database. No `ATTACH`. `journal_mode=DELETE`,
  `synchronous=FULL`, integrity check on every open and a restrictive 0600
  file under a nonproduction temporary directory.
- At first creation the ledger imports an **already admitted** A24
  double-signed publisher/operator grant and an **already admitted**
  A25 double-signed inert Custom bundle through their existing
  verifiers. Stores their exact digests, monotonic sequence, version,
  A21 public generic descriptor and explicit issue/expiry window.
  Does NOT import executable artifacts or signing secrets.
- A new file initially contains a `SEALED` grant. On every PROCESS
  start/reopen, in-memory authorization is disarmed EVEN when the
  persisted record says `ACTIVE`. `recover()` requires an explicit
  descriptor pin, exact persisted generation (CAS), time-valid
  A24/A25 evidence, and advances the generation transactionally.
  There is no unconditional restart, stale process-PID adoption or
  automatic permission restore.
- `revoke()` is terminal in the A27 ledger: within one SQLite
  transaction it sets state `REVOKED` and increments the generation.
  `seal()` explicitly disarms and rotates the generation without
  granting further authority; a later manual reauthorization is
  required. Old captured generations and old startup states cannot
  authorize new commits.
- A27's PAPER `commit()` begins **one BEGIN IMMEDIATE transaction**,
  checks its own grant state, generation, A21 contract identity, A22
  paper-only enabled status, valid signed issue/expiry window, and
  inserts A7-shaped PAPER rows in **the same database and transaction**.
  All-or-nothing rollback on conflict; identical signals idempotent.
  Revocation and PAPER insert linearize on the same SQLite writer lock.
- A22 gains an opt-in fence-kind `"a27"` distinct from its existing
  `"a26"`. Exactly typed `UnifiedPaperCommitFence` is required;
  absent or mismatched gates are rejected. A26 remains the backward
  compatible default; no changes to old A7 journal schema.
- An optional `RecoveredFixedPaperSession` uses the **static A23
  low-privilege relay** to process already-computed A7 PAPER bytes.
  No arbitrary strategy code, dynamic imports, binaries, decrypted
  packages or execution from a user-supplied engine.

## Verification

CI uses disposable real SQLite and Linux A23 cgroup/seccomp, not a
simulation of authorization checks. Tests include:
- full fixed-relay → A22 runner → A27 single-database journal flow
- default SEALED state and absent-memory-authorization on restart
- signed pin + CAS recovery with generation rotation, no auto-adoption
- actual child `SIGKILL` in the middle of an open SQLite transaction
  after BOTH a grant update and PAPER insertion but BEFORE COMMIT,
  followed by fresh SQLite recovery proving both changes rolled back
- explicit seal, terminal revocation across restart, expiry and
  stale generation rejection
- concurrent independent SQLite writer attempting revoke while
  PAPER commit lock is held, and the opposite ordering
- PAP​ER partial-batch identity-conflict rollback, idempotent replay,
  and A22 no-fallback wrong-fence tests
- A7/A8/A12–A26 legacy regression, source digest freeze, safe public
  package preview, disposable PostgreSQL corpus and publication safety

## Honest limitations and deployment fence

**This is not an off-host or tamper-resistant License Authority.** Full
SQLite single-file rollback journal + FULL synchronous improves crash
atomicity in the tested local-filesystem environment, but hardware/
filesystem lying about fsync, host compromise, disk corruption or
copying back an entire OLD database file can break trust. An external,
cryptographically pinned high-water witness or authoritative remote
monotonic epoch is future work. Process SIGKILL tests are NOT a literal
physical power-cut certification.

**A27 is a separate cutover domain, not a transparent migration of the
legacy A24/A25 writers.** They verify imported signed evidence at initial
creation and each manual recovery. A24/A25 modifications made AFTER
A27's active cutover do not atomically update its grant; new A27
revocations MUST go through the single A27 ledger for this demo.
Do not run separate legacy writers concurrently with this A27 domain
or claim globally effective revocation. Production migration requires
an explicit single-authority cutover, fencing, recovery handover and
disabling old write endpoints.

A27's recovered bridge still operates only on static fixture-produced
PAPER bytes in a disposable CI runner. Real Custom executable hosting,
production, trading/broker access, commercial license issuance and
arbitrary third-party code isolation are **not** activated.

## Permanent private-owner policy

**NY First-Reversal remains OWNER_ONLY.** Source, compiled, encrypted,
obfuscated and otherwise repackaged proprietary core must NEVER become
publicly installable or distributed. A27 cannot be used as a backdoor
to execute it or to issue a public commercial entitlement.

**Target verdict:** `A27_SINGLE_FILE_CRASH_RECOVERY_VERIFIED_NONPRODUCTION`.
