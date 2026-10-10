# Multi Market Trading — A17 Continuous Fixture Watchdog & Resource Ceilings

**Non-production fixture-only release; production approval: DENIED.**

This stage extends the existing signed A12 offline owner grant, A13 local
provisioning, A14 immutable synthetic data ZIP, A15 signed release witness
and A16 static subprocess supervisor. No real private engine is downloaded,
imported, executed, deployed or connected.

## Architecture

- `ContinuousFixtureWatchdog` is the sole operator of an A16 static,
  non-executing mock worker. The independently supplied `session_factory`
  is invoked **inside the watchdog-owned thread**, and opens **all**
  PluginManager/TrustStore/OfflineProvisioner/SignedReleaseAuthority
  SQLite connections in that same thread. Main-thread callers send
  commands via a bounded, synchronous queue; no cross-thread SQLite
  connections, private engine entry points or dynamic code imports.
- An exclusive Linux `flock` under a 0700 temporary directory prevents
  a second active A17 owner using the same watchdog root. This is
  cooperative file locking, not a security boundary against hostile root.
- A16 has optional `FixtureProcessLimits` requiring Linux child-side
  `RLIMIT_AS` (256 MiB default), `RLIMIT_CPU` (5 seconds),
  `RLIMIT_NOFILE` (48 handles) and disabled core dumps. The resource
  prelude executes **inside the child before the fixed worker code**,
  avoiding Python `preexec_fn` in a threaded application. Invalid
  parameters fail closed, and A17 rejects A16 sessions that omit limits.
  These are per-process resource ceilings, **NOT namespaces, seccomp,
  rootless containers or security sandboxing**.
- Every **0.05–30 seconds** (0.15 default; operator must select), the
  watchdog invokes A16 `health()`. Each probe checks the full current
  A12/A13 admission, A14 bytes, A15 Ed25519 publisher release with
  high-water sequence and expiration, and the real owned child's
  PING/PONG response. This is background in-process periodic monitoring,
  not a continuously active remote service.
- On a failed health probe, A16 shuts down **its own** fixture child and
  records `QUARANTINED`. If a clock or unexpected monitor exception
  occurs, an explicit owned-only quarantine hook closes that child.
  The monitor stops polling; it never auto-restarts a crashed child.
- A17 `start()`, `stop()`, `reconcile()`, `status()` and
  negative-test `crash_fixture_for_test()` are queued to the
  owner thread. The initial `start()` requires one completed signed
  health probe, not merely a spawned PID. Manual `reconcile()` is
  required after quarantine; a fresh `start()` rechecks all cryptographic
  and revocation gates. STOP remains available even after revocation.
- `WatchdogSnapshot.last_probe_admitted` is **last-observed status**,
  not a continuous authorization proof. Revocation is acted upon on
  the next scheduled probe, not instantaneously. Delay may exceed the
  nominal interval if the thread is blocked or OS scheduling stalls.
  `monitoring` means the local thread continues checking, not
  production runtime health.

## Fail-closed rehearsal

`tests/unit/test_a17_watchdog.py` tests real Linux child RLIMIT values
using `resource.prlimit`, multiple background health ticks, revoked
A13 licenses, revoked A15 publisher, expired signed envelope, unexpected
clock exceptions, manual crash and recovery with **no auto-restart**,
tampered ZIP, single-owner lock, invalid resource limits, and independent
thread-owned SQLite sessions. Full A12 signed grant and A15 publisher
signature integration is exercised with real, ephemeral public/private
key pairs; no issuer private key is stored in platform source.

`.github/workflows/a17-continuous-watchdog.yml` runs those and the
A12–A16 regressions on an ephemeral Ubuntu 24.04 GitHub runner, checks
frozen historical source and public-only package contents, and statically
fences package imports against private engines and network code.
Existing full platform CI remains a mandatory independent merge gate.

## Still NOT suitable for production

This is **NOT** a private code deployment/execution manager. It lacks
OS identity isolation, network-deny firewall, seccomp, namespaces,
cgroups, durable off-host monotonic counter and independent 24/7
supervisor. A15 anti-rollback witness is still local SQLite; a
host-wide rollback can bypass it. The startup and health proof share
in-process trust and do not provide independent witness attestation.
The worker is a fixed Python fixture only.

A17's long-running watchdog is an **in-process daemon thread**; it
ends on parent death, so this implementation does not guarantee
operation through a manager crash. Parent stdin EOF causes the A16
child to exit, but any abnormal parent termination that prevents clean
pipe close or OS kill timing is not a production cleanup guarantee.
External `systemd`, cgroups, rootless sandbox/least-privilege
credentials, hardened signed private binary provenance, OS watchdog,
off-host backup trust, and production operator approval remain future
separately authorized work.

No production servers, historical trading bot, PostgreSQL deployment,
Docker Compose settings, live Telegram, private strategy or broker
integration was touched.

**Verdict: A17_NONPRODUCTION_FIXTURE_VERIFIED only after CI success.**
