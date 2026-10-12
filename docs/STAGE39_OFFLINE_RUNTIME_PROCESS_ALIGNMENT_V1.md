# Stage 39 — Signed, offline comparison of declared runsc policy and process self-observation

**Nonproduction, GitHub-only. No disposable Linux host has been designated. Nothing in this stage opens a socket, reads live procfs, runs Docker/gVisor, executes untrusted code, sends Telegram messages, places broker orders or provisions infrastructure.**

## Purpose and new safety boundary

Stage37 independently validates a **declared** restrictive nftables/runsc configuration, anchored to Stage36’s verified Stage32–35 evidence chain and a separately pinned third Ed25519 review key. Stage38 adds a manual, passive **self-process** kernel posture sampler, which reports UID/GID, zero capabilities, seccomp, no-new-privileges, read-only root and loopback-only routes, but cannot prove that it was inside the claimed gVisor sandbox.

Stage39 performs a **strict offline reconciliation** between these previously unconnected artifacts. This catches internal inconsistency such as a declared gVisor configuration with UID/GID 65534 but an observed process running as root or a different user. It does not prove the signed sample genuinely came from the designated machine.

## Verification contract

`verify_offline_runtime_alignment(bundle, stage37_options=..., stage38_self_report=..., signed_alignment=..., witness_public_key=..., witness_public_key_sha256=..., expected_host_alias=..., expected_nodename=..., expected_challenge=..., now=..., operator_ack=True)`:

1. Re-evaluates the **entire Stage36 portable Ed25519 chain** including externally pinned Stage35 SHA and monotonically increasing sequence, then revalidates Stage37’s independently signed nftables and gVisor static policies. The prior reviews cannot be replaced by an unchecked caller-provided success boolean or pasted hashes.
2. Demands the **exact canonical, bounded Stage38 receipt schema**: correct host and nodename, timestamps within 300 seconds, all four SHA256 snapshot fields, bounded loopback-route count and `local_process_restrictive_snapshot=true`. Every statement claiming actual host/gVisor, real firewall or external egress certification, public deployment, plugin execution, Telegram publishing or broker trading must be the literal boolean **false**.
3. Checks that Stage38’s **reported** process UID/GID exactly match the restrictive Stage37 runsc user `65534:65534`, and that its observation followed the Stage34 report within 300 seconds. It also checks a fourth reviewer’s signature was issued after the Stage37 report and the Stage38 observation, with expiry at most five minutes later.
4. The fourth Ed25519 review public key, its SHA256 pin, and a 128-bit nonce are obtained **out of band**, and the key must differ from the Stage32 reviewer, Stage33/35 auditor and Stage37 reviewer. The domain-separated signed claim binds the exact Stage35 checkpoint, Stage37 signed review SHA, Stage38 original canonical receipt SHA, host alias, nodename, observation timestamp, nonce and time window.
5. On any missing or noncanonical field, source mismatch, root or privileged process claim, different UID/GID, forged key, stale observation, old checkpoint, wrong host or even a **valid signature that claims execution permission**, verification fails closed. The routine has **no stateful nonce replay store**; the trusted operator must track nonce uniqueness outside this untrusted packet.

The successful verdict is **`SIGNED_OFFLINE_POLICY_ALIGNMENT_NOT_HOST_ATTESTED`**. A receipt includes exact SHA256 references and explicitly false flags for actual gVisor containment, host identity authentication, firewall enforcement, blocked egress, public developer API, plugin execution, Telegram and broker operations.

## What a success does *not* demonstrate

Stage38's self-reported kernel hashes are **not raw authenticated kernel measurements**. A malicious actor can compose a plausible Stage38 canonical JSON matching the declared Stage37 profile and persuade an authorized reviewer to sign it. Stage39 proves only that reviewed bytes and declared attributes are mutually consistent, with traceable signature custody; neither it nor the earlier Stage36/37 proofs establish that a real host exists or that runsc applied the restrictions to the correct process.

Actual acceptance requires **explicit authorization of a named isolated, credential-free disposable host**, reading genuine namespace and kernel configuration in the proper context, runtime provenance validation, and independent observation of firewall, TLS and gVisor adversarial canary results. A real host review still would not automatically grant live broker, public installer or Telegram permissions. No such host is named for this stage.

## CI gate

Dedicated Python 3.12 source and installed-wheel test suites verify legitimate synthetic cross-stage consistency and reject root/wrong UID, inconsistent timestamps/hostnames, weak process claims, fourth-key impersonation, mismatched Stage37 and Stage38 SHA, privilege escalation signed by a real key, noncanonical JSON and stale Stage35 checkpoint. CI runs all prior Stage22–38 regressions and standard repository PostgreSQL/publication safety workflows. The tests must not invoke Stage38’s genuine Linux sampler on GitHub runners.

**Readiness: `OFFLINE_DECLARED_RUNTIME_AND_SELF_REPORT_CONSISTENCY_READY / REAL_HOST_UNDESIGNATED / GVISOR_CONTAINMENT_UNVERIFIED / PUBLIC_INSTALL_AND_TRADING_BLOCKED`.**
