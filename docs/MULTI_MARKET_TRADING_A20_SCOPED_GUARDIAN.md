# Multi Market Trading — A20 Hardened Guardian Non-Production Integration

**Scope: GitHub-hosted disposable Ubuntu runner ONLY. Production admission DENIED.**

A20 connects previous A19 kernel controls **to the actual A18 signed Guardian
fixture** rather than a separate demonstration-only process. It does NOT
execute private plugin code, provision production, change a server, exchange,
Telegram, operator user list, permanent service or host database.

## Executed controls

- A18 `SignedGuardianController` accepts an explicitly opt-in
  `a20_ci_scoped=True` only for a *non-root GitHub Actions runner*.
  Existing A18 behavior and public API default are unchanged.
- Before Guardian START/RENEW the unchanged A12/A13/A14/A15 contract
  requires live signed offline-owner admission, pinned Ed25519 publisher,
  exact immutable archive hash, revision and rollback witness. On failed
  renewal, Controller issues immediate STOP; if Controller disappears,
  the independent Guardian's monotonic short lease expires and stops worker.
- A20 uses a **transient systemd `--scope`** with genuine Linux cgroup-v2
  `memory.max=268435456`, `memory.high=201326592`,
  `cpu.max` = 50% and `pids.max=16`. The *same* Guardian and its
  worker are in the scope. No permanent service/unit is installed.
- Guardian runs under the CI operator account inside the scope;
  the *fixed inert worker* is launched via CI-authorized `sudo -n -u
  nobody`. No new user/group is created. Controller sends its 256-bit
  authenticated Guardian capability once via stdin (not argv).
- A20 worker sets `PR_SET_NO_NEW_PRIVS=1` and a **default-deny**
  libseccomp filter allowing a small explicit syscall set. It verifies
  actual EPERM on `socket()`, `open('/etc/passwd')` and `fork()`.
  Worker identity, actual PID, kernel no-new-privileges and seccomp,
  cgroup paths and quotas are verified before Guardian reports RUNNING.
  Per-process RLIMIT_AS/CPU/NOFILE/CORE remain bounded.
- Cgroup observation reads exact kernel controller files for the running
  Guardian/worker. Missing permissions, unsupported platform, changed
  cgroup path, different quota, missing guard attestation or failed
  signature cause a **fail-closed** refusal, not a silent fallback to
  the weaker A18 process profile.

## Tests

`tests/unit/test_a20_integration.py` provides real disposable systemd
scope/worker testing: A12-A15 signed launch, Linux cgroup quotas, strict
kernel response, distinct worker UID, renewal, A13 admission revocation,
A15 publisher revocation, archive tampering, absence of secret-laundering,
bounded lease expiry, manager SIGKILL, no auto-restart, manual locked
reconciliation and explicit reauthorization. Existing A12-A19 tests
run unchanged in the same CI workflow.

`.github/workflows/a20-cgroup-scope-probe.yml` independently confirms
temporary scope capability. Main A20 workflow additionally runs the full
repository regressions and public-only distribution checks. No permanent
unit, cgroup mutation outside systemd's ephemeral scope, live license
authority or private strategy code.

## Important limitations

A20 remains an *inert, synthetic* local service exercise. The default-deny
filter is specialized for the fixed deterministic Python heartbeat
fixture and is NOT a safe drop-in policy for private engine binaries,
which must not be passed as code, command, scripts or imports.
An ephemeral systemd scope is not a durable `systemd` service manager
after reboot, and no independent A12/A15 verifier exists inside the
Guardian: each renewal is verified by the A18 Controller, while the
Guardian enforces short expiry if Controller is lost.

The Guardian/Controller privilege boundary is NOT hardened against an
adversary with administrative permissions over the disposable runner,
or against a same-user adversary able to mutate fixture state. The
locally pinned SQLite rollback counter is not an off-host independent
witness. Exposing this profile on a non-GitHub host is prohibited until
a separately authorized production architecture review.

**Verification verdict:** A20_NONPRODUCTION_SCOPED_FIXTURE_ONLY on CI PASS.
