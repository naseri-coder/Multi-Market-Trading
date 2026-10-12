# Stage 38 — Manual, passive Linux self-process kernel observation

**Mode: NONPRODUCTION SOFTWARE IMPLEMENTATION ONLY.** No real disposable Linux host has been explicitly designated, no production host will be accessed, and GitHub CI MUST NOT invoke this collector against its own runner. The operator-only CLI is NOT a deployment script and does not run Docker, nftables, `runsc`, shell, SSH, a reverse proxy, a broker or Telegram.

## Meaningful advance beyond Stage37's static config parser

Stage37 can reject permissive **declared** nftables and gVisor settings, but it has no way to establish those settings were applied anywhere. Stage38 implements a narrowly scoped **read-only Linux /proc observation** of the process currently invoking the tool. If a separately authorized, credential-free disposable host is designated later, a non-root operator can run the tool within the actual test process environment to obtain local kernel-state facts. No privileged commands, firewall changes, container starts, new TLS listeners, outbound probes or file writes take place.

`observe_authorized_process_kernel_posture(host_alias=..., expected_nodename=..., expected_gid=..., operator_ack=True)` requires exact `MMT_NONPRODUCTION=1`, `MMT_DISPOSABLE_SANDBOX_HOST=1`, production flag absent, non-root effective UID, operator approval, exact Linux nodename and separately expected non-root effective GID. These environment flags and the nodename are **not cryptographic authentication** of a physical host.

It opens **only four fixed kernel files** with bounded `O_NOFOLLOW` reads:

| Path | Restricted local observation |
|---|---|
| `/proc/self/status` | Real/effective/saved/fs UID/GID match expected non-root caller; no inheritable/permitted/effective/bounding/ambient capabilities; `NoNewPrivs=1`, `Seccomp=2` and a nonzero filter count when present |
| `/proc/self/mountinfo` | Exactly one root mount `/` and mount options containing `ro`, not `rw` |
| `/proc/self/net/route` | No IPv4 routes on a non-loopback network interface in the process namespace |
| `/proc/self/net/ipv6_route` | No IPv6 routes on non-loopback interfaces in the process namespace |

If any required file is absent, inaccessible, malformed, oversized, ambiguous or shows a disallowed state, the command fails without returning a green receipt. Its output is bounded canonical JSON with only process UID/GID, sanitized host alias/nodename, timestamp, SHA256 of each read kernel snapshot, loopback-route count and **permanently false** flags for independent host custody, actual firewall policy, independent egress denial, other-container gVisor operation, hostile-code containment, deployment, Telegram publication and broker orders. No raw `/proc` file, environment string, certificate, token or key is serialized.

### Critical trust boundaries

These are **kernel-reported facts for the CURRENT PROCESS AND NETWORK NAMESPACE**, not proof about some other sandbox or the entire OS. The gVisor `runsc` binary or host rootful Docker can be installed and used elsewhere independently of these observations; the tool does not inspect or attest them. Conversely, a passing snapshot cannot prove that the firewall blocks network access, as routing and packet filtering are different layers, routes could change after reading, other processes may have different namespaces, and a compromised kernel could fabricate `/proc`.

A passing snapshot therefore is **not** a signed origin, independent remote attestation, real host TLS test, nftables active-ruleset proof, gVisor kernel isolation validation or approval to execute third-party code. The prior Stage36/37 portable signing contracts remain independent and do not automatically accept a Stage38 receipt as sufficient proof.

### Manual invocation on a separately approved disposable host only

After a trusted operator independently designates a **credential-free** disposable Linux host and authorizes **passive self-process** inspection, ensure the tool is run inside the actual isolated test process/namespace, not on production or arbitrary GitHub CI hosts. A potential command (illustrative; do not run before explicit host designation):

```sh
MMT_NONPRODUCTION=1 MMT_DISPOSABLE_SANDBOX_HOST=1 \
python -m naseri_markets.passive_kernel_posture_cli_stage38_v1 \
  --host-alias approved_disposable_test \
  --expected-nodename exact_uname_nodename \
  --expected-gid 1001 \
  --ack-disposable-readonly-process-probe
```

A secure gVisor sandbox often applies the strict `CapBnd=0`, `Seccomp=2` and root-mount read-only conditions only **inside its payload**, not to the external host operator's login shell; the CLI will appropriately refuse unsuitable contexts. The tool does not launch the missing process sandbox or overcome this mismatch automatically. No live host has been probed by this development stage.

### CI and completion standard

Dedicated Python3.12 GitHub CI runs **only synthetic /proc fixtures**: strong restrictive cases, each privilege/capability regression, missing Seccomp, writable rootfs, external IPv4/IPv6 routes, malformed or excessive files, root UID, wrong nodename or GID, missing operator ack, production flag and CLI refusal without approval. Stage22–37 regressions, a clean installed wheel and all repository PostgreSQL/publication safety checks must also pass.

**Status: `MANUAL_PASSIVE_KERNEL_OBSERVER_IMPLEMENTED / LIVE_HOST_UNDESIGNATED / HOST_AND_GVISOR_UNVERIFIED / PUBLIC_EXECUTION_BLOCKED`.**
