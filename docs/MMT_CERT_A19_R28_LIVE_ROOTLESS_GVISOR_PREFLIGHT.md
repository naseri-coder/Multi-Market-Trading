# CERT-A19-R28 — Actual Temporary GitHub Runner Rootless/gVisor Host Preflight

**Final verdict:** \`CERT_A19_R28_ACTUAL_GITHUB_RUNNER_DAEMON_READONLY_AUDIT_COMPLETE__ROOTLESS_AND_RUNSC_NOT_PRESENT__INDEPENDENT_HOST_CERTIFICATION_BLOCKED__A6_DENY_199_OPEN\`

**Date:** 2026-10-15 UTC.
**Authority:** Nonproduction host capability inspection ONLY; not independent security certification, not an actual future deployed host.
**Original main:** \`dccfe791f465040cc87d210c0ca33fad44f654ae\`, unchanged. Unmerged research Draft PR #275.

## 1. Actual hosted run and immutable input/output evidence

- [One isolated GitHub Actions run #38698762835](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38698762835): **SUCCESS** for running the *read-only audit*, **NOT** a security HOST_PASS verdict. Repo \`naseri-coder/Multi-Market-Trading\`, scratch branch \`cert-a19-byte-audit-run\` only. The workflow did not trigger broad PR CI or production operations.
- Exact preceding R27 immutable evidence was restored from real artifact #11954717453, rather than copying human-reported statuses. \`r27-report.json\` SHA-256 **\`818e8b3165c53404d1e33ac7bfb04d51886288b5c40b37155681f756485dcf5b\`** and \`r27-vectors.json\` SHA-256 **\`6f9c7847c5029d29f0f29fe5beae94c318bfc9a8c4f7f4a6512052e667812f1d\`**, canonical JSON SHA-256 **\`0c1836b766d9cd93399ae86d2f093be2d7de85593077489d66ced0b46fb48fe0\`**. The audit refused previous claims implying executed guest code or relaxed A6.
- New artifact **11955436679**, name \`cert-a19-r28-live-rootless-runsc-preflight\`, retention **2 days**, downloaded and inspected. Exact output files:
  - \`r28-host-live-preflight.json\`, 1,634 bytes, SHA-256 **\`94ad37614eb28a995d447148b9a90673831240735d399b5ae1d5a53e366a97b6\`**;
  - \`r28-fixture-host-contract.json\`, 1,155 bytes, SHA-256 **\`384fa24c19fcac781a1d5587dddf15f46d0644576b2682b92251e9fac73f24b7\`**.
- No downloaded application code was executed; the only probes were trusted host Python standard library, \`docker version --format\`, \`docker info --format\` against the current Docker CLI daemon, checking whether \`runsc\` or \`rootlesskit\` are available in \`PATH\`, checking a per-user Docker socket's presence, and local namespace/cgroup filesystem interfaces. No socket/host address, env secrets, usernames, process arguments, daemon labels, system hostname or network data was stored.
- No \`docker run\` / \`docker start\`, no installation of gVisor, rootless Docker, OS/OCI packages, no Worker or guest code, no network scan or container start. The user did **not** authorize a live independent host or production change.

## 2. Actual observed GitHub-hosted temporary runner — not a security certification

| Predicate or property | Measured outcome |
|---|---|
| Can query current Docker daemon with read-only \`docker info/version\` | **YES** |
| Docker server version reported | \`28.0.4\` |
| \`name=rootless\` in current daemon's reported security options | **NO** |
| Registered OCI runtime named \`runsc\` in current daemon | **NO** |
| \`runsc\` executable present in runner PATH | **NO** |
| \`rootlesskit\` executable present in runner PATH | **NO** |
| Current UID's per-user Docker socket present | **NO** |
| Script's own host process runs as root | **NO** |
| Namespace paths observed (\`/proc/self/ns/user\`, \`/proc/self/ns/mnt\`) | **YES** |
| cgroups v2 controllers interface observed | **YES** |
| Independently owned/reviewed rootless+gVisor machine attested | **NO** |
| Container or guest executed | **NO** |
| Approved four-language fixture execution | **NO** |
| Production/A6 unlock | **NO** |

**Interpretation:** The tested GitHub Actions runner's **current Docker daemon** does not advertise Rootless and does not register \`runsc\`; the runner's PATH also lacks \`runsc\`. That is a concrete reason not to run the next sensitive execution phase on this particular runner. This does NOT mean no other host anywhere could be configured for Rootless/gVisor, and checking a self-selected ephemeral runner is NOT independent kernel/host security review. The audit therefore **fails closed** regardless of the results of individual probes.

Presence of kernel namespaces, cgroups v2, and source-level flags \`--runtime=runsc\`, \`--network=none\`, \`--ipc=none\`, \`--read-only\`, \`--cap-drop=ALL\`, \`--security-opt=no-new-privileges\`, \`--pids-limit=32\`, \`--user=65534:65534\`, and \`--pull=never\` proves only **potential prerequisites or static intent**; it does **NOT** establish that a real rootless daemon and safely configured gVisor exist, nor that CPU/memory/seccomp constraints are certified.

## 3. R28 reviewed, **NOT EXECUTED**, fixture-host contract

An additional canonical JSON \`r28-fixture-host-contract.json\` was saved under the same artifact. The proposal prohibits unknown strategies, proprietary guest code, credentials, broker sockets, production mounts, privileged host access or network access. Any later separately authorized, independent benign fixture host must meet all of the following as hard preconditions:

1. **Independent authorization and custody:** a user-approved disposable nonproduction host, identified only to the auditor; independently attest the host's rootless daemon, signed and pinned gVisor \`runsc\`, secure daemon socket, kernel/security patch level, exact OCI binary digest and filesystem ownership. Do not treat a shared production TELMIVO machine or generic GitHub runner as automatically permitted.
2. **Fixed reviewed fixtures only:** exact immutable R27 7 accepted and 4 rejected numeric-offset inputs, reviewed developer-authored Python/JavaScript/TypeScript/WASM fixture source/bytes and hash. Four-language binaries in the R25 candidate OCI were **not** co-installed and no module was compiled or executed in this stage.
3. **Enforcement:** no network, no IPC, read-only root, no capabilities, no new privileges, nonroot guest UID/GID, immutable/pinned OCI with no implicit pull, reviewed seccomp and gVisor syscalls, bounded pids+RAM+CPU, strictly bounded stdout/stderr/artifacts, no secrets, broker mounts, Docker daemon socket, or user data.
4. **Negative controls and cleanup:** bounded timeout, explicit inspectable kernel resource-limit enforcement and container/image deletion evidence after every attempt. Neither cleanup nor tested confinement may be claimed until witnessed.
5. **Independent product gate:** preserve original \`require_worker_launch\` hard refusal \`A6_INDEPENDENT_HOST_CERTIFICATION_REQUIRED\` regardless of a successful harmless developer fixture on an isolated host. Such a fixture could support runtime parity, **not** production certification for unknown users.

R28's static plan records these requirements but does not certify or satisfy them.

## 4. Security disposition and R29 recommendation

**PASS:** Narrow live read-only host capability inventory; frozen R27 hash checks; denial of guest execution; no host/tool mutation; collection of two byte-bound evidence JSON files.

**BLOCKED:** Any actual rootless+gVisor security certification, independently attested host or runsc, actual sandboxed fixture execution, Node18→24 behavioral parity, 4-language runtime parity, TLS/CA runtime or named-zone support, arbitrary user strategies or production release. The current Actions runner **lacks observed Rootless+runsc prerequisites**.

**Recommended R29 without a designated isolated host:** construct a verifiable **host-accreditation runbook and attestable preflight contract**, with a separate offline signed-binary custody path for gVisor, exact rootless daemon/socket ownership and negative cases; research and freeze documentation in GitHub, no provisioning or installation on production. Request independent nonproduction host authorization only when ready to run the physical host-accreditation test. Do not repurpose production TELMIVO or license authority hosts without separate explicit and risk-reviewed permission.

**Preserved:** historical original **199 Critical/High findings REVIEW-OPEN, 0 CVEs** closed; no modifications to \`main\`, A11 372-package Debian lock, A2/A15/A18 contracts, original Worker, broker, trading algorithms, production, TELMIVO, Telegram, or PR merge. PR #275 stays **DRAFT / DO NOT MERGE**. \`RUNTIME-A6\` remains **hard DENY**.

**R28 final label:** \`CERT_A19_R28_LIVE_GITHUB_HOST_INSPECTED__ROOTLESS_RUNSC_NOT_AVAILABLE__INDEPENDENT_HOST_UNVERIFIED__A6_DENY_199_OPEN\`.
