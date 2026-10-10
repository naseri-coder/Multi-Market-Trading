# Multi Market Trading — A19 Separate-UID Hardening & cgroup Policy

**Status: NON-PRODUCTION preparation and ephemeral kernel rehearsal.**
No host user, service, configuration, private plugin, licensed live engine,
PostgreSQL production database or exchange connection is changed.

A19 builds on A12–A18 but explicitly does **not** replace their admission
or Guardian contracts. It has two **separate** deliverables with distinctly
different assurance levels:

## 1. Executed kernel hardening — ephemeral GitHub runner only

`naseri_markets/a19_hardening.py` contains a fully static Python probe
run under the pre-existing Linux `nobody` account using
`sudo -n -u nobody -- /usr/bin/python3 -I -S -u -c ...`.
This is allowed **only when `GITHUB_ACTIONS=true` and `RUNNER_TEMP` is
available**. It never creates a user, writes a network policy, opens a
broker, imports private code or touches production.

The kernel proof requires:

- Effective UID is non-root and **distinct** from the invoking CI user
- `PR_SET_NO_NEW_PRIVS` is set before seccomp installation
- `libseccomp.so.2` installs a **default EPERM** BPF policy, with a small
  explicit syscall allowlist sufficient for a short deterministic fixture
- A real `socket(AF_INET)` call fails with `EPERM`
- A real filesystem `open('/etc/passwd')` fails with `EPERM`
- A real `fork()` attempt fails with `EPERM`
- `/proc/self/status` shows `NoNewPrivs: 1` and `Seccomp: 2`
- Hard Linux `RLIMIT_AS=256 MiB`, `RLIMIT_CPU=4 sec`,
  `RLIMIT_NOFILE=48`, `RLIMIT_CORE=0`

The fixed mock reports only six true booleans plus observed UID. All
claims are tested on a disposable Ubuntu GitHub Actions host. This
demonstration is not a generic Python/plugin runtime; its restrictive
syscall allowlist intentionally will not run real trading code.

There are **no secrets or package-supplied entrypoints** in the child.
The probe runs synchronously with a finite subprocess timeout and exits.
No privileged state persists.

## 2. Prepared, never-activated systemd/cgroup policy

`systemd_fixture_unit()` defines an **inert** offline-only service
preview with:

- `DynamicUser=yes`, fixed non-production service account name
- `NoNewPrivileges=yes`, empty capability sets
- PrivateNetwork, AF_UNIX-only address families, deny IPs
- RestrictNamespaces, ProtectSystem=strict, ProtectHome and
  kernel/filesystem/device/clock restrictions
- `MemoryMax=256M`, `MemoryHigh=192M`, `CPUQuota=50%`,
  `TasksMax=8`, limited open FDs, no core dumps
- `SystemCallFilter`, `RestrictSUIDSGID`, and other hardening fences
- `Restart=no`, `RefuseManualStart=yes`, intentionally absent activation
  condition `/run/mmt-a19-explicit-test-authorization-never-created`,
  **no WantedBy** and static `A19_INERT_FIXTURE_ONLY` command

Only 0600 files under a temporary directory may hold the exported
preview. The API verifies exact immutable expected contents and runs
`systemd-analyze verify` **without installing, enabling, starting
or calling any systemd service manager**.

`cgroup_readiness()` reads `/sys/fs/cgroup/cgroup.controllers`
without mutation; it reports whether `cpu`, `memory` and `pids`
controllers are visible. **`limits_enforced=False` always** because
A19 does NOT provision/activate cgroup limits on the host. It would be
incorrect to claim actual cgroup enforcement from a successful
`systemd-analyze verify` result.

## Trust and separation boundary

- A12–A15 offline signed grant and publisher release verification remain
  required in the A18 Controller.
- A18 Guardian still independently enforces a short monotonic worker
  lease after its Controller dies. A19 does not remove that lease.
- A19 seccomp/UID proof is a **separate throwaway fixed process**, not
  yet grafted onto A18's continuously licensed worker. This separation
  is deliberate: integration under DynamicUser/systemd and actual
  cgroup activation requires a new, separately authorized environment.
- A19's future systemd template is intentionally **nonfunctional as a
  production service** and provides no independent signed-grant
  evaluator or durable supervisor during machine reboots.

## Tests and limits

CI `.github/workflows/a19-offline-hardening.yml` runs:
historical immutable source-manifest preflight; strict ephemeral
non-root kernel denial tests, frozen systemd policy and real
`systemd-analyze verify`; A12–A18 signed offline regression; static
import and source boundary checks; public-only wheel preview.
Existing full PostgreSQL and publication workflows remain mandatory
merge gates.

**No production capability is claimed.** Separate-UID and default-deny
seccomp were exercised on the CI **probe**, while the systemd/cgroup
policy was **authored and statically verified, not activated**.
No private engine, key custody, off-host anti-rollback counter, manager
survival across reboot, true private network service or real trades.

**Verdict upon CI success: A19_NONPRODUCTION_HARDENING_PROBE_VERIFIED.**
