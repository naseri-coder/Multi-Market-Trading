# Stage 37 — Independent offline firewall and gVisor control-template review

**Authorization: GITHUB / NONPRODUCTION ONLY.** This stage does not connect to, configure, certify, or test a real server. A disposable security-test host has still not been explicitly designated. The API accepts **untrusted offline snapshots**, not automatically authenticated host observations.

## What Stage37 actually adds

Stage36 already verifies cryptographic custody across the signed Stage32/33/35 statements and the Stage34 sanitized self-observation, with an externally supplied latest digest+sequence checkpoint. Stage37 invokes that complete verifier, then applies **independent policy validation** to two additional bounded artifacts rather than merely checking their signatures:

* **nftables JSON static configuration:** Accepts only an `inet` table explicitly named `mmt_disposable`, exactly three filter base chains `input`, `output`, and `forward`, each with **default DROP** at priority zero, and exactly two interface-limited ACCEPT rules for `iifname == lo` on input and `oifname == lo` on output. Unknown tables/families, NAT features, rules enabling nonloopback traffic, wildcard permits, extra chains, unusual expressions, duplicates, malformed entries, or missing default-deny policy fail closed. This is a deliberately tiny template; **a passing parse does NOT attest to the actual machine's complete nftables ruleset, active network namespace, non-nft firewall layers, UDP listeners, network egress, or external reachability**.
* **gVisor/runsc normalized configuration:** Validates an exact operator-normalized policy using runtime `runsc`, no network, read-only root filesystem, UID/GID 65534, no added capabilities, drop ALL, no bind mounts/devices/ports, no-new-privileges, private IPC/cgroup namespace, no host PID namespace, bounded PIDs, memory, CPU, and a *fixed, harmless test canary, not user code*. A passing normalized JSON snapshot is **NOT a Docker inspect receipt**, proof the runtime actually used gVisor, proof of kernel enforcement or a hostile-code containment test. An operator can invent these JSON fields unless separately collected and independently corroborated.

The two exact SHA256 snapshot hashes plus the Stage36 **externally pinned Stage35 binding SHA** are signed by a **third** Ed25519 review key, distinct from both prior signing identities. The reviewer key SHA and a 128-bit fresh challenge must be known via independent operator custody, not learned from the review envelope. The Stage37 signed claim has a short validity window (at most 300 seconds), binds host alias and all three hashes and must explicitly disavow real-host attestation, public deployment, plugin execution, Telegram sends and broker orders. Parsing uses bounded JSON with duplicate-key and NaN rejection. The module never generates, writes, imports or executes unknown plugin source.

### API

`review_nftables_static_snapshot(raw: bytes) -> int` and `review_gvisor_static_snapshot(raw: bytes) -> str` validate the narrow templates without assuming they are genuine host output.

`verify_offline_host_controls(bundle, stage36_verification=..., firewall_snapshot=..., runtime_snapshot=..., signed_review=..., reviewer_public_key=..., reviewer_public_key_sha256=..., expected_host_alias=..., expected_challenge=..., now=..., operator_ack=True)` verifies **Stage36 first** and then checks both policy snapshots and the third reviewer signature. All Stage36 trust arguments (independent reviewer/auditor keys and digests, pinned Stage35 digest+sequence, host/nodename/time) must come from the trusted operator, never from the snapshots. The separately pinned Stage37 challenge and reviewer public-key digest are similarly required.

There is no persistent Stage37 challenge-replay database. The independent operator must manage nonce uniqueness and freshness, including across machines, otherwise a correctly signed review can be replayed within its short validity window. This contract therefore does NOT implement a global transparency log, deployment gate or live-source attestation.

### Result and limitations

A successful evaluation returns `STATIC_CONTROL_TEMPLATES_REVIEWED_NOT_HOST_ACCEPTED` with hashes of the two policy documents, the exact Stage35 checkpoint, three approved DROP chain definitions, and **all** independent host attestation, live endpoint TLS, real firewall enforcement, real gVisor operation, hostile-code certification, public developer API deployment, third-party core execution, Telegram sends and broker order authorizations set to **false**.

An attacker can fabricate internally consistent nftables/runsc snapshots, and even a signature by a legitimate reviewer can certify only that these bytes were reviewed, not that they reflect a live host. Host custody, actual TLS, firewall and runtime enforcement must each be validated **separately on an explicitly designated credential-free disposable machine**. In particular, the gVisor policy parser does not enable public execution of unknown code and makes no claim about the results of containment tests.

## GitHub acceptance

A dedicated Python 3.12 GitHub Actions job runs real (ephemeral **test-only**) Ed25519 cryptography and adversarial policy tests. Negative cases include default ACCEPT, NAT tables, wildcard/forward rules, leaked mounts/devices, root identity, elevated capabilities, wrong OCI runtime, network escape, oversized resource limits, forged and privilege-escalated reviews, altered Stage36 checkpoints, replaced hash inputs, and unsafe production flags. The CI suite also exercises Stage22–36 regressions and a separate installed-wheel test environment, alongside the standard full project PostgreSQL and publication safety workflows.

**Stage37 readiness: `OFFLINE_STATIC_CONFIG_VALIDATOR_READY / REAL_HOST_NOT_DESIGNATED / LIVE_FIREWALL_AND_GVISOR_NOT_VERIFIED / PUBLIC_DEPLOYMENT_BLOCKED`.** No production bot/server, PostgreSQL state, broker credentials, Telegram signal, private NY First-Reversal code or installed runtime is touched.
