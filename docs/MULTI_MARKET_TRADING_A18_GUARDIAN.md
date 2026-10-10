# Multi Market Trading — A18 Independent Linux Fixture Guardian & Sandbox Rehearsal

**VERDICT SCOPE: NON-PRODUCTION / SYNTHETIC FIXTURE ONLY.**

A18 extends A12 signed owner PAPER grants, A13 offline provisioning,
A14 inert synthetic data packages, A15 pinned Ed25519 publisher releases,
A16 process control and A17 periodic thread supervision. Unlike A17, the A18
guardian is a **separate Linux process and OS session**. It can continue
enforcing the monotonic short-term fixture lease after its launching manager
is killed with `SIGKILL`. It is not a production private-engine loader.

## Files

- `naseri_markets/a18_guardian.py` — fully standalone and stdlib-only
  immutable fixture supervisor, loaded by explicit absolute path with
  `python -I -S`, never from a ZIP entry point. It owns and reaps its
  fixed subprocess, Unix-domain control socket and 0600 atomic state.
- `naseri_markets/a18_controller.py` — exact A12/A13/A14/A15 gate before
  launching and before each **explicit** lease renewal; it passes a
  throwaway 256-bit authorization token via inherited pipe, not argv,
  and starts the guardian in a new OS session. Stops on failed gate.
- `tests/unit/test_a18_guardian.py` — real Ubuntu/Linux system calls,
  actual signed publisher/grant E2E, manager SIGKILL, lease expiry,
  independent guardian, kernel safety and manual recovery tests.

## Linux child confinement (rehearsal, not a sandbox for hostile code)

Inside the *static inert child only*, **before** READY, A18 applies:

- `PR_SET_NO_NEW_PRIVS=1` and verifies `/proc/self/status`.
- Loaded Linux seccomp BPF filter via `libseccomp.so.2`, explicitly
  denying networking syscalls (`socket`, `connect`, `bind`, etc.),
  `execve/execveat`, `ptrace`, mount, bpf, keyctl and subprocess
  creation calls with EPERM. Startup refuses if the filter cannot be
  loaded. The fixed fixture **actually calls socket()** and requires
  EPERM before reporting `NET_DENIED`.
- `RLIMIT_AS=256 MiB`, `RLIMIT_CPU=5 sec`, `RLIMIT_NOFILE=48`,
  `RLIMIT_CORE=0`, minimal environment, no inherited FDs, isolated
  Python `-I -S`, temporary private cwd and no package-provided code.
  CI independently examines `/proc/<pid>/status` and `prlimit`.

**Important:** the filter defaults to allow and adds selected deny
rules. This is **not default-deny seccomp**, a security boundary against
malicious same-user host processes, or a container. There is NO separate
Linux uid/gid, mount namespace, cgroup or SELinux/AppArmor policy here.
Do not run private or otherwise untrusted executable code in this
rehearsal. The guardian itself may use a local AF_UNIX socket; it has
not been syscall-sandboxed like the child.

## Independent guardian and fail-closed expiry

1. Controller requires fresh, authorized A12/A13 grant and matches exact
   signed A15 current release (including publisher key, signature,
   revocation, current high-water sequence and package byte digest).
   The A14 mock worker must be STOPPED.
2. Guardian acquires a nonblocking exclusive lock and starts the
   fixed, inert worker, only after the authenticated `START` control
   message. Worker must prove `NNP1|SECCOMP2|NET_DENIED` and answer
   a bounded PING to become RUNNING.
3. Guardian checks worker PING/PONG on its own monotonic timer and
   stops/quarantines if the child dies or fails heartbeat. It
   additionally owns a short monotonic lease of **0.35 to 5.0 seconds**.
   Every `RENEW` is issued only after the controller freshly verifies
   A12–A15. A failed check immediately asks the guardian to STOP.
4. If the controller **is killed or disappears**, no RENEW occurs.
   The guardian, as a separate session, expires the lease and stops
   its own child. It eventually closes its control socket and releases
   the guardian lock after a bounded grace period. **No automatic
   restart, adoption of historical PIDs or silent rollback**.
5. A replacement controller can only **manually reconcile** after the
   guardian's exclusive lock is free, a terminal state was durably
   written and a *fresh* signed admission is valid. The operator may
   explicitly launch a new bounded fixture after reconciliation.
   Persisted PIDs are observational only, never authority to signal.

IPC uses a 0700 temporary directory, 0600 AF_UNIX socket, Linux
`SO_PEERCRED` same-uid check, ephemeral secret transferred via private
FD, bounded JSON frames, bounded response sizes and fixed command
allowlist. These are cooperative local controls; a compromised
same-user environment can tamper with files and is outside proof scope.

## Scope and security limitations

- A18 guardian does **not** hold or validate A12 issuer keys or A15
  publisher keys. Validation occurs in its controller **on start and
  explicit renewal**; guardian independently enforces short monotonic
  leases if the controller dies. A controller that fails to renew
  is intentionally treated as authorization loss.
- A18 does not currently include an automatic signed-renewal thread
  or fully independent trust-database admission evaluator. Operators
  must explicitly renew within the lease. It must not be described
  as a 24/7 autonomous licensed service.
- Local A15 SQLite witness still cannot defend against a whole-host
  filesystem rollback. A process with same-user access or privileged
  host compromise is not contained by this local demonstration.
- Abnormal guardian termination can leave a worker until its pipe is
  closed by the kernel; the fixed worker consumes stdin and exits on
  EOF. This is not an audited production process tree/cgroup guarantee.
- `SIGKILL` manager recovery is tested on the dedicated fixture
  only; no real license server, service, plugin, external network,
  cryptocurrency exchange, broker, Telegram or trading code is used.
- `libseccomp.so.2` and Linux `/proc` are hard dependencies for
  verified start. Unsupported hosts must fail closed.
- Production needs dedicated least-privilege user, **default-deny**
  seccomp, rootless container/namespaces, cgroups, service manager,
  independently pinned off-host trust counter, externally audited
  binary provenance, independent revocation watch and explicit
  rollback/reconciliation policies. None is approved or deployed.

The historical v0.3.2 `production_source/`, live bots, DBs,
Compose/environment secrets and all real private engines are unchanged.

**A18_NONPRODUCTION_FIXTURE_ONLY.**
