# R41 — Rootless Docker + gVisor independent-host security gate

**2026-10-16: read-only source-contract review candidate, NOT an isolated
host acceptance or public/LIVE security certification.**

## Actual scope and change

R41 introduces the standalone standard-library audit
scripts/mmt_r41_readonly_oci_contract_audit_v1.py and negative unit
tests/tests/unit/test_mmt_r41_readonly_oci_contract_audit_v1.py.

This is intentionally **read-only**: it does not invoke Docker, runsc,
plugins, Python subprocess execution, brokerage, Telegram or any
market-data API. It **does not** run any hostile source. The user can
continue GitHub development without having to install Docker inside
Android Termux or touch the operational Telmivo host.

The auditor accepts an **independently reviewed exact SHA256** of the
existing Stage4 source file
naseri_markets/secure_plugin_runtime_v1.py. It never extracts an
expected hash from the file it is verifying. It requires
MMT_NONPRODUCTION=1, *absence* of MMT_PRODUCTION (any value),
and explicit acknowledgement.

After bounding and reading the exact regular file without following a
symlink, it parses the source with the Python standard-library AST.
It checks that the reviewed Stage4 container command includes its
strict rootless/gVisor switches: runsc, network=none, ipc=none,
read-only filesystem, cap-drop=ALL, no-new-privileges, non-root
UID 65534, resource/pid limits, no pulled images, ephemeral tmpfs,
Python isolated flags, and expected rootless socket routing.
It refuses privileged, host-network, host PID/IPC, mount, host-device
or extra published-port switches. It also requires recognized
SecureOfflineCoreHost.evaluate calls to
_assert_rootless_socket, _ensure_rootless_daemon and _invoke, plus
a strictly bounded non-dynamic f-string container name.

This is a **static source + command-template control**, not a Docker
daemon, Linux kernel, gVisor, seccomp, cgroup or container cleanup
attestation. The external SHA256 must be authenticated by a separate
reviewer and independently compared against the intended GitHub SHA.
A merely recomputed local digest or self-authored PR report is not
a publisher signature.

Success-shaped audit output is explicitly
R41_STATIC_OCI_CONTRACT_PASS_HOST_TRIAL_PENDING, with:

- independent_rootless_host_tested=false
- gvisor_runtime_verified=false
- hostile_core_containment_proven=false
- cleanup_under_crash_proven=false
- broker_order_authorized=false
- telegram_authorized=false
- public_release_authorized=false
- live_authorized=false

An invalid/missing source pin, missing flag, dynamic Docker command
expression, bypassed rootless probe, symlink or malformed source is
fail-closed without writing anything.

## Required external independent hostile-host acceptance (PENDING)

This work cannot be accepted solely from static inspections.
The operator/security reviewer must provision an *unrelated*
disposable Linux host with confirmed rootless Docker and
actual --runtime=runsc. The host must have zero production credentials,
real broker access, Telegram token, or connected service sessions.

Only on that dedicated authorized environment, independently observe,
record and validate:

1. Actual rootless daemon and real runsc/gVisor runtime identity;
   prohibit fallbacks to runc/host Python.
2. No network connectivity, no mounted host secrets, no accessible
   production file system, no host PID/IPC and no capabilities.
3. CPU, memory, process count, file descriptors, temporary storage
   and wall-time enforcement, including runaway/fork/large-output
   test cases with inert synthetic inputs.
4. Wrong SHA/publisher/binding, cross-tenant read, forged Core API
   result and unauthorized LIVE/Telegram flags all denied before
   dispatch; input identity remains fenced to one tenant.
5. Forced timeout, early tool termination, unknown child state
   and container-side orphan cleanup; independently inspect and
   reconcile all orphaned containers before host reuse.
6. Operator revocation and quarantine persistence across process
   restarts; no blind retry, no host-wide silent reset.
7. Host OS kernel/gVisor vulnerability posture, patching, image
   digest authenticity, rootless socket ownership and log/attestation
   provenance from an independent review channel.

Every test needs a recorded environment fingerprint, independent
observer, date, source SHA, image digest, unambiguous pass/fail,
host artifact hashes and a cleanup declaration. Failed/unknown
conditions must block admission; one current or forged runsc banner
is not enough to prove hostile-Python containment. Never execute
hostile fixtures on the operational Telmivo server.

## Local unit test and execution status

R41 tests inspect a copy of the **real Stage4 source** and do not
start Docker. The authored suite includes positive source contract
checking, repeatability/no writes, wrong pin, absent runsc/network
flag, injected privilege, missing rootless function or skipped
rootless check, malicious dynamic Docker name, replaced host class,
symlink/hardlink and incorrect module name, explicit
nonproduction acknowledgement, four production variable values,
and CLI refusal/success. The suite is **authored but not yet marked
executed/pass** in an exact clean GitHub branch Python 3.12.3 run.

The assistant's ephemeral local Linux environment has Python 3.13,
pytest, but **no Docker/runsc installed** and cannot access the
connected user's Termux or an independently qualified gVisor host.
Therefore no kernel-isolation/adversarial evidence is claimed.

Stage15's P0_EXTERNAL_CORE_CONTAINMENT stays OPEN. All nine P0 and
one P1 release blockers remain unresolved, including the frozen
R27 Brooks worker (DEFERRED). R37/R38/39/40 Draft/acceptance gaps
are not closed by a static R41 check. Do not Merge or grant any
public distribution, production, connected PAPER or LIVE access.
