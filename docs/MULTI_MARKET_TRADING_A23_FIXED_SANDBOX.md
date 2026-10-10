# Multi Market Trading — A23 Fixed Custom Sandbox & Lifecycle Rehearsal

**Scope: NON-PRODUCTION. Public `generic_custom` PAPER bytes only.**

## A21 owner and commercial boundary

**NY First-Reversal is owner-only and NEVER installable for the public** —
not as plaintext code, binary, ZIP, licensed plugin, encrypted bundle, or
obfuscated software. A23 does not even accept an A21 `owner_only` or
`commercial_candidate` descriptor and never imports any strategy code.
Future private commercialization requires independent explicit authorization
and separate distribution/ownership design, outside this public installer.

## A23 isolated generic Custom PAPER data path

- `FixedCustomSandbox` accepts ONLY an independently pinned and registered
  A21 `public_custom`, `generic_custom` descriptor. Catalog registration
  remains metadata-only, not publisher authentication or a software license.
- A23 launches a *fixed public Python relay* via
  `sudo -n systemd-run --scope` under a randomly identified, ephemeral
  A20-compatible Linux cgroup. This is **only enabled** when a nonroot,
  disposable GitHub Actions Linux runner provides `sudo`, systemd and
  cgroup-v2. There is **no fallback** to the old same-UID subprocess.
- The child runs as pre-existing low-privilege `nobody` with Python
  `-I -S -u`, RLIMIT memory/CPU/file descriptors/core and kernel
  `NoNewPrivs: 1`. It installs a strict **default-EPERM seccomp** filter
  (small allowlist) and proves live socket, file open and fork calls fail.
  The parent independently checks the observed PID, UID difference,
  `/proc` seccomp state and A20's genuine `memory.max=256MiB`,
  `memory.high=192MiB`, `cpu.max=50%`, `pids.max=16` kernel values.
- The relay has ONE fixed byte protocol: bounded `ECHO` for
  **already-computed** A7 PAPER envelopes; `PING`, `STOP` and
  `CRASH_TEST` for test-only lifecycle. Its only behavioral transformation
  is returning *exactly* the submitted bytes plus a random per-exchange nonce.
  There is **no uploaded executable, dynamic import, plugin script,
  callbacks, broker, Telegram, network server or strategy generation**.
  The controller validates A7 paper signal identity, market, quote
  timestamp and risk geometry BEFORE and AFTER relay. This protects the
  data-boundary contract, not a hostile custom-code runtime.
- A23 `dispatch()` integrates **A22 CustomPaperRuntimeBridge** by checking
  operator-enabled state, descriptor digest, CAS revision and platform
  PAPER mode before relaying. It checks permissions again after the
  async relay before delegating to A22's existing post-await CAS validation
  and atomic A7 paper journal. Disable/revoke during relay prevents
  persistence of stale outputs.

## Owned lifecycle, no implicit upgrades

- One owner per 0700 temporary root, exclusive Linux `flock`, 0600 atomic
  JSON checkpoint, no PID adoption after owner loss.
- Startup is explicit with the same independently approved A21 digest.
  `NEW → RUNNING → STOPPED` or `QUARANTINED`. The child expires by its
  own **3-second monotonic lease** if no heartbeat/data traffic occurs;
  controller pipes also close on owner death. No restart is automatic.
- Explicit `reconcile()` is available only when the owned subprocess is
  already fully stopped or quarantined, with renewed operator-pinned
  metadata. Invalid pin, active worker or stale persisted state fail closed.
  An abandoned root with previous metadata is **blocked**, not silently
  reclaimed. Production-grade stale-owner recovery requires additional
  evidence and separate authorization.
- `stop()` always closes the owned worker, even if its paper runtime has
  been disabled; it never executes package-derived paths or shell snippets.

## Verification and operational limitations

Dedicated ephemeral CI tests run real systemd cgroup policy, separate
low-privilege UID, default-deny seccomp, actual EPERM proofs, relay and A22
paper journal, malformed/cross-engine/live feed rejection, owner/commercial
and NYFR exclusion, disable-in-flight race, crash, lease expiry, exclusive
lock, no auto-restart and explicit controlled recovery. They include
A7–A22 regressions. The full PR also gates immutable legacy
`production_source`, disposable PostgreSQL, publication safety and
public-only packaged artifacts.

**Scope warning:** This is not a safe runner for **arbitrary third-party
code**. The strict kernel policy is specialized for a **fixed fixture
whose only task is forwarding validated data**. Neither the A21 descriptor
hash nor the local CAS state authenticates the engine publisher, tenant
identity, authority-issued license or trusted code execution. Public
generic source/binary plugin hosting and durable systemd Production
deployment require separately designed permission and supply-chain
controls, not a toggle of A23.

**Expected CI verdict:** A23_FIXED_SANDBOX_PAPER_RELAY_VERIFIED_NONPRODUCTION.
