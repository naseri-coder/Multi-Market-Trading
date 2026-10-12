# Stage 35 — Immutable Stage32 → Stage33 → Stage34 self-observation evidence binding

**Status: Nonproduction, GitHub-only.** This stage binds *bytes and signed assertions*, not real-world security outcomes. It does not probe any physical host, create a network listener, run a container, turn on a marketplace, sign or publish Telegram signals or place broker orders. No real disposable host has been designated.

## Objective and evidence roles

Three prior artifacts had separate security meanings:

1. **Stage32**: a signed, owner-private review of a *local TEST certificate/key pair* and a proposed network posture. This is not a host measurement.
2. **Stage33**: independently pinned auditor-signed claims and a twelve-category checklist (NOT_RUN / DECLARED_PASS / DECLARED_FAIL). Hash pointers are *declarations*, not evidence of their source or execution.
3. **Stage34**: a canonical, sanitized *local self-observation* receipt the operator may generate only on an explicitly approved disposable Linux host. It records the hashed TCP listener snapshot and actual local loopback TLS handshake result, but it has **no signature of its own** and makes no independent host attestation.

**Stage35** implements a new signed chain-of-custody edge between those artifacts. The Stage33 auditor (not the host) signs a *second, domain-separated Stage35 binding claim* containing the exact SHA256 of the canonical Stage34 receipt, Stage33 assessment SHA256, Stage32 preparation SHA256, host alias, pinned nodename, reading timestamp, fresh window and monotonic sequence. The operator supplies all exact original bytes separately to the Stage35 verifier, rather than accepting a self-asserted hash as proof. No private signing key is produced or stored by Stage35.

## Admission requirements and failure conditions

`SelfObservationEvidenceChain(stage33, operator_ack=True).record(stage34_probe=..., signed_binding=..., expected_nodename=..., now=..., operator_ack=True)`:

- Requires `MMT_NONPRODUCTION=1` and no `MMT_PRODUCTION=1`; exact local Stage33 ledger and explicit operator acknowledgment.
- Strictly parses the Stage34 JSON: exact dataclass schema, canonical ASCII, no duplicate/unknown fields, bounded to 4 KiB. All security and trading authorizations **must be the literal JSON boolean false**, local loopback handshake flag the literal true. Current reading age is at most 600 seconds; hostname, nodename, TLS cipher, independent certificate SHA and listener count are bounded and type checked.
- Verifies an exact canonical Stage35 Ed25519 envelope signed by the already pinned Stage33 auditor public key with a new Stage35 domain string. Claim expires within 600 seconds and must not grant public deployment, plugin install, Telegram send, broker orders or independent host verification. The signer must bind the actual original Stage34 receipt hash and timestamp.
- Rechecks the **actual stored Stage33 signed assessment bytes**, auditor Ed25519 signature, source SHA, schema and valid review window. Rejects a superseded earlier assessment and requires the reading to precede the signed reviewer assessment. Verifies the signed Stage32 preparation bytes again under the original Stage32 reviewer key, checks all identity and reference hashes, and refuses a probe's TLS certificate SHA that differs from the Stage32 locally reviewed TEST certificate.
- Commits an immutable Stage35 SQLite linkage and the exact canonical self-observation bytes in the same owner-private Stage32/33 database with per-host monotonically increasing sequence and UNIQUE linkage to Stage33 and Stage34 SHA256. SQL triggers forbid edits/deletes; duplicate, stale, gapped or cross-host submissions fail. A privileged DB/filesystem owner still can remove these triggers or replace the entire store; the chain is not an HSM or externally anchored audit log.
- Emits `STAGE34_SELF_OBSERVATION_CHAINED_NOT_HOST_ATTESTED`, with independent host verification, real external TLS, firewall enforcement, gVisor certification and public deployment/trading toggles **always false**. Even a valid signature cannot convert an invented self-observation into proof of a physical host.

## Threat boundaries and prerequisites

**Do not mistake signatures for observations:** An auditor can sign an entirely synthetic Stage34 JSON and Stage35 will validate its *signature and internal consistency* while still reporting independent host verification **false**. Stage35 neither establishes that a named host exists nor authenticates the origin of a claimed `/proc` snapshot. The complete chain is therefore a useful basis for accountability, tamper detection, sequence-control and offline review, **not production readiness**.

A future real-host security gate still needs an explicitly designated, credential-free disposable machine, separately approved manual Stage34 read-only execution, genuine TLS identity and firewall verification, rootless gVisor adversarial checks, a trusted evidence-collection channel and independent reviewer custody. In particular, Stage34's local TCP-listener inspection is not a firewall policy test or outbound-denial proof; none of those checks run in Stage35. There is no production host change, no protected NY First-Reversal source exposure, no public API/HTTPS listener and no order/Telegram execution.

## CI acceptance

Python 3.12 dedicated GitHub Actions runs 1) strict source lint and publication safety; 2) Stage35 adversarial receipt, crypto signature, timeline, Stage32/33 provenance, tampering, anti-replay/SQL immutability and production-denial tests alongside Stage22–34 regressions; 3) an independently built/installed wheel outside the source tree. All repository full-corpus PostgreSQL and publication checks must pass before merging. All Stage34 readings used by Stage35 CI are synthetic; the prior Stage34 socketpair handshake suite also runs but *does not constitute a real designated-host test*.

**Release status: `OFFLINE_SELF_OBSERVATION_CUSTODY_READY / NO_REAL_HOST_ATTESTATION / NO_GVISOR_AUDIT / NO_PUBLIC_INSTALL_OR_TRADING`.**
