# Stage 22 — Durable tenant-fenced public third-party core admission (offline)

**Status: source candidate, nonproduction only.** This stage closes a *control-plane* gap in the existing Stage-4 `SecureOfflineCoreHost` rootless Docker + gVisor design. It does **not** implement or claim a public marketplace, universal hostile-code isolation, a production-installed host, cryptographically signed publisher identity, live strategy loading, authorized broker orders, Telegram signal publication or private NY First-Reversal execution.

## What is new

`naseri_markets.durable_isolated_core_gate_stage22_v1.DurableIsolatedCoreGate` wraps the **exact existing** `SecureOfflineCoreHost` type. It refuses the disabled policy or any in-process alternative and never falls back to the old trusted-local `python -I -S` child, which does *not* sandbox arbitrary hostile source. Unlike the old in-memory Stage4 quarantine, Stage22 persists **explicit owner authorization** and crash-safe deny state in one owner-private SQLite file.

- **Private installation + tenant partitioning**: 0700 caller-owned directory and exact 0600 regular SQLite file, no symlink, owner mismatch or public permissions. The caller supplies a validated tenant identifier from a **trusted host authentication layer**; merely supplying an ID is *not* authentication. One global binding ID cannot be claimed by a different tenant. Max 8 binding identities per tenant and 64 per instance; registrations are disabled by default.
- **External review pins**: `register(tenant_id, manifest, binding, approved_manifest_digest, approved_source_sha256, operator_ack=True)` stores only manifest, binding and source SHA256 pins, not source code, API keys, account identities or other plugins' state. A SHA256 pin verifies bytes, **not** publisher safety, signed release, licensing or profitability. A new version/source needs a **fresh binding identity** and separate review.
- **Explicit CAS enable/disable**: `set_enabled(..., enabled=True, expected_revision=..., operator_ack=True)`. Only a DISABLED binding can be enabled. Every state change increments a durable revision. QUARANTINED and REVOKED identities cannot be silently reset, reused or reenabled. No legacy database or BotFather handlers are changed.
- **One-shot event admission**: `evaluate(..., source=..., operator_ack=True)` refuses absent permissions, mismatched tenant/source/manifest/binding digest, an event from `LIVE`, incompatible market or duplicate input digest. At most two externally executing analyses per tenant. It reserves a persisted `EVALUATING` lease and unique input digest **before** requesting the Stage4 sandbox. No matching host authorization → no launch.
- **Crashes and disable-during-evaluate**: a process loss preserves the EVALUATING lease in SQLite and on restart it **blocks**, never automatically retries. Revocation while evaluation runs increments the revision, causes any late result to be **discarded**, and permanently REVOKEs the old incarnation. A malformed or failed isolated evaluation causes a persisted **QUARANTINE**, also across restarts.
- **Strict inert result**: the trusted host Stage4 parser plus explicit Core API contract validation must accept every output. Only an inert `CoreResult` can return to the trusted caller. No signal-send, risk cap bypass, position allocation, order placement, broker/Telegram access or automatic stage19 side effects are provided. The local evidence ledger only reports `VERIFIED`, `FAILED`, `DISCARDED` or `IN_FLIGHT` with no private source/payload storage.

## Example trusted application-side use

This API is deliberately not wired to the Telegram admin panel until authenticated tenant identity, a signed publisher supply chain, independently approved sandbox host and an operator integration decision exist. In trusted application code, use a previously reviewed **real** Stage4 OCI host policy, in a disposable nonproduction machine with Docker rootless+gVisor independently audited:

```python
from pathlib import Path
from naseri_markets.durable_isolated_core_gate_stage22_v1 import DurableIsolatedCoreGate

# host is an independently reviewed SecureOfflineCoreHost with enabled,
# pinned OCI image and genuine rootless+runsc enforcement on a sacrificial host.
with DurableIsolatedCoreGate(Path("/private/owner/state/core-22.sqlite"), host=host) as gate:
    gate.register(
        authenticated_tenant_id, approved_core_manifest, host_binding,
        approved_manifest_digest=independent_manifest_sha,
        approved_source_sha256=independent_code_sha,
        operator_ack=True)
    # Separately CAS-enable this exact binding then evaluate only
    # synthetic/replay market events. There is no live trading API.
```

This is a conceptual *host integration snippet*, not a runnable installation without the caller-owned reviewed objects and policy.

## Isolation and deployment security disclaimer

Rootless Docker reduces daemon privileges but cannot itself guarantee immunity to malicious code. gVisor must actually run via `--runtime=runsc`, with no network, read-only filesystem, dropped capabilities, no new privileges, no host mounts and explicit resource limits. The existing Stage4 contract documents these restrictions. See [Docker rootless security](https://docs.docker.com/engine/security/rootless/) and [gVisor rootless runtime](https://gvisor.dev/docs/user_guide/rootless/).

**Stage22 CI uses mocked host evaluations** and tests only the control plane. It does **not** start Docker/gVisor, run actual hostile code, prove seccomp escape prevention, verify orphan-container cleanup, or establish cryptographic publisher authority. Existing Stage4 daemon container force-removal remains **best effort**; an isolated host with uncertain cleanup must be manually inspected before reuse. A compromised host, operator, SQLite owner, OS runtime or signing authority can still circumvent controls.

**No automatic marketplace activation.** All third-party upload, source execution, licensing, public publication, real LIVE feed, brokerage and production readiness remain `BLOCKED_PENDING_INDEPENDENT_ISOLATION_AND_SUPPLY_CHAIN_REVIEW`.

## Acceptance

New CI tests check tenant spoofing, global binding collisions, immutable pins, no unauthorized invokes, disabled-by-default, off-production fences, unique input replay across restart, failure quarantine surviving restart, crash-induced persistent lease, late-result discard after CAS disable, per-tenant quota, invalid/forged outputs and harmless Stage4 source fixtures. Runs previous Stage4, Stage7 and Stage19–21F regression suites and installs the 0.4.0rc1 wheel from outside the repo. All legacy production and private assets remain untouched.

**Explicitly prohibited in this stage:** server provision/restart/deploy, new Github Actions secrets, privileged Linux commands, real source execution with Docker, public strategy publication, database migration on production, real Telegram messages, auto broker orders, strategy profitability claims, or copying owner-only NY First-Reversal.
