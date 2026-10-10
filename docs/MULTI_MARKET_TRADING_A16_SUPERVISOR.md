# Multi Market Trading — A16 Offline Private Service Supervisor & Recovery

**Status target: GitHub-only non-production service supervision rehearsal.**
This stage extends **A12 signed installation grants**, **A13 offline
admission**, **A14 inert package staging** and **A15 signed release +
local rollback floor**. It does **not** install, execute, import or
connect to a real private trading engine.

## Separate process and exact trust chain

The `OfflineFixtureSupervisor` starts an independently running
`python -I -S -u -c <static fixture>` subprocess on an ephemeral
Linux test runner. The fixed worker uses only Python stdlib and
the parent-owned stdin/stdout pipes; it emits a bounded READY frame
and responds to bounded PING and STOP frames. Its only fault-injection
command, CRASH, exits with a fixed status. **No executable code is
read from any private package archive.**

One A16 start requires all gates, in order:

1. Existing A14 release directory and state are present, but A14's
   own worker is **STOPPED** (never two A14/A16 fixture workers).
2. A13 fresh verification of the **exact** A12 grant, trust-store
   instance, installation, private disabled A8 descriptor, signed
   issuer, revocation state and explicit evaluation clock.
3. A14 archive is still byte-identical to its SHA-256 digest and
   still bound to the A12/A13 manifest.
4. A15 independently pinned Ed25519 publisher signature and signed
   artifact receipt match the **current** locally witnessed high-water
   release sequence; revoked, rotated, expired or old artifact rejected.
5. Only the `healthy` synthetic mock behavior may start. A16
   acquires its own exclusive Linux worker lock, launches the **fixed
   inert worker**, performs an exact READY token/digest handshake
   and a PING response, then rechecks all release and admission gates
   before persisting RUNNING atomically with revision CAS.

The child never sees A12 grant, issuer secret, signing keys, owner
private code or network endpoint. A handshake correlation token and
digest are not claimed to be secure credentials or OS-level attestation.

## State machine and operational invariants

```text
UNINSTALLED (A15 has no signed active archive)
   └── A15 signed install [separate step; A16 cannot download]
STOPPED
   └── signed + fresh A12/A13 + fixed worker READY + PING
RUNNING (process owned by this A16 instance)
   ├── graceful STOP ─────────────────────> STOPPED
   ├── child crash / EOF / mismatch ──────> QUARANTINED
   ├── grant/signing/clock/release invalid > QUARANTINED
   └── parent disappears / new observer ─> RECOVERY_REQUIRED
QUARANTINED / RECOVERY_REQUIRED
   └── MANUAL reconcile + no living child + exclusive lock
                                         └── STOPPED
```

- Health is an **explicit single fresh probe**. It verifies current
  A12/A13 + A15 proof, A14 artifact and an on-pipe PING before returning
  an affirmative *fixture* status.
- If a running owned child fails this probe, the owner shuts down the
  specific tracked child (with graceful attempt, then bounded kill of
  **that same child only**) and atomically records QUARANTINED. The
  operator must explicitly reconcile before starting again.
- `status()` is purely observational: it does **not** imply a
  successful fresh admission; persisted RUNNING after owner loss is
  shown as RECOVERY_REQUIRED.
- The worker exits upon parent command-pipe EOF. A new supervisor
  cannot adopt or kill arbitrary PID values; while the real owner
  holds the exclusive worker lock, recovery is blocked.
- Every mutating API needs the exact monotonic A16 revision.
  No automatic restart, retry, downgrading publisher release sequence
  or restored old persisted RUNNING state is permitted.
- Controlled STOP remains available if A12 or A15 are revoked;
  shutdown is **not** hostage to a currently valid grant.
- Every transition stores a bounded ring of event labels in the
  same atomically fsynced 0600 JSON state snapshot.
- An unexpected direct A14/A15 release change while A16 is running
  is detected on the next explicit health probe and quarantines the
  worker. This is **not** an inter-manager OS-wide deployment lock.

## Scope and limits of testing

Dedicated tests in `tests/unit/test_a16_supervisor.py` use real,
disposable Linux subprocesses and actual ephemeral Ed25519 keys.
Negative cases cover startup timeout, crash, stale CAS, lost pipe,
worker-lock ownership, corrupted state, tampered package,
cross-installation rejection, explicit recovery, revoked publisher
and grant, expired signature, changed signed release mid-run, and a
full **real A12+A13+A15+A16 end-to-end** test.

`.github/workflows/a16-offline-supervisor.yml` runs the A16 tests
and the locked A12–A15 security regressions, historical manifest
safety, source lint, private-code import/static bans and public-only
isolated packaging. All work is on disposable GitHub runners.

## Explicit NON-PRODUCTION boundaries

**A16 is a development scaffold, not a deployable private service
manager.** The subprocess is inert and not a sandbox for untrusted
code. It has no OS namespace, seccomp, cgroup limits, systemd,
Docker, real private engine, external signing server, secure key
custody, mTLS network service, true code provenance attestation,
Market Data, Telegram, broker/exchange connectivity or trades.

The supervisor does **not** continuously monitor without being
called: health is a synchronous probe, not a recurring watchdog.
Revoked grants therefore cause shutdown at the next explicit probe
or explicit stop, **not immediately at remote revocation time**.

There is no hard anti-rollback guarantee against compromise or
restore of the independent local A15 SQLite witness. No seamless
cross-process recovery/adoption, cross-manager global lock or
distributed transactional release cutover is claimed. Production
deployment requires separately authorized hardening: off-host
monotonic counter custody, isolate real subprocess under restricted
OS identity and resource limits, real signed private code
distribution, continuous watchdog, end-to-end revocation push,
independent audited recovery and production-specific rollback plan.

No production server, historical `production_source/`, v0.3.2 bot,
Compose/PostgreSQL storage, licensed private strategy or operational
configuration is touched by this stage.

**Release verdict: NONPRODUCTION_FIXTURE_ONLY.**
