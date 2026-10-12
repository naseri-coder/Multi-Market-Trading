# Stage 24 — Signed host observations and read-only Telegram readiness

**Nonproduction, GitHub-only preparation. Host security acceptance is NOT completed.** A disposable rootless Docker + gVisor host was **not supplied or remotely accessed** during Stage24. No real Stage23 canary has been run. This stage intentionally distinguishes recorded statements from verified isolation and retains fail-closed controls.

## 1. Durable custody of signed Stage23 observations

`host_observation_custody_stage24_v1.HostObservationLedger` admits an **externally generated and independently reviewer-signed statement** about a single Stage23 disposable-host canary receipt. It never runs Docker or the submitted core.

- A reviewer (not the strategy publisher or operator key implicitly reused) must have a separately registered Ed25519 public key pinned by its SHA256 **out of band**. Stage24 creates no signing keys and offers no signing command or remote input interface.
- The raw Stage23 CLI JSON receipt's SHA256 must be bound to the exact, canonical domain-separated reviewer-signed envelope. The claim includes an operator-specified host alias, fixed reviewed `image@sha256`, canary SHA256, exact nine true security observations, issued/expiry timestamps (max 24h), strict schema and monotonically increasing sequence.
- Receipt must explicitly say **not independently audited**, **no publisher trust**, **no untrusted user-source run**, **no public plugin install**, **no Telegram send**, **no broker order**, **no LIVE trading**. An unusually positive receipt is **rejected**, not converted to a grant.
- The ledger resides in an owner-private folder, stores only signed statements and hashes (not source or secrets), locks the reviewer key anchor at initial creation, enforces per-host monotonic sequence, immutable image and probe identity, and permanent explicit revocation. Local sequence floors cannot prevent rollback of an entire host disk; independent storage would be required for anti-rollback.
- The receipt proves only that a reviewer key signed a claim **about** supplied bytes. It cannot cryptographically prove the isolated code ran, that the reviewer observed a real host, or that the kernel enforced all advertised policies. A forged but validly signed statement is a supply-chain/reviewer custody risk, not a runtime-verified success.

Signed claim shape (operator-signed externally by a separate reviewed signing system; illustrative field structure only):

```json
{
  "claim": {
    "version": 1,
    "kind": "disposable_host_canary_observation",
    "host_id": "disposable_host_one",
    "image": "EXACT_PINNED_IMAGE@sha256:<64 hex>",
    "probe_sha256": "<64 hex>",
    "receipt_sha256": "<64 hex>",
    "sequence": 1,
    "observed_at": 1234567890,
    "expires_at": 1234568000,
    "review_scope": "manual_single_run_no_security_certification",
    "observation_checks": {
      "uid_unprivileged": true,
      "no_capabilities": true,
      "no_new_privileges": true,
      "docker_socket_absent": true,
      "docker_user_socket_absent": true,
      "only_loopback_interfaces": true,
      "rootfs_readonly": true,
      "external_network_denied": true,
      "root_secret_unreadable": true
    }
  },
  "reviewer_signature_b64": "EXACT_BASE64_ED25519_SIGNATURE"
}
```

The example is **not** a valid signed statement. No acceptance CLI or publisher signing keys are distributed.

## 2. Integration into the nonproduction Telegram management panel

The existing `IntegratedEnginePanel` adds private admin command `/coresecurity` to the **same existing nonproduction application**; it creates no new Telegram poller or BotFather registration and makes no remote API calls. It reads (via SQLite `mode=ro` and `PRAGMA query_only`) at most the count of nonrevoked local host statements in `state_dir/stage24_host_observation.sqlite`, if present.

The UI **never shows reviewer keys, hostname, developer source, private NY First-Reversal metadata, host aliases or raw signed blobs**. Even if evidence is present, it always states that independently verified gVisor security is **not yet achieved**, third-party public installation remains **BLOCKED**, and Telegram publications and broker orders remain **BLOCKED**. Unknown users and group chats cannot access the command. The UI does not enable Stage22 tenant leases or modify existing public/private core configuration, callback toggles or databases. A corrupted/unsafe status source fails closed with a refusal message.

## 3. Real-host work still required — not presumed successful

Independent, expressly authorized operations on an **empty, isolated, nonproduction** machine must verify the environment without sensitive accounts, install and independently pin rootless Docker/runsc images using separate approval, run the operator-gated Stage23 fixed canary, and capture provenance (system versions, verification commands, timestamps, fixed image SHA, cleaned orphan status). Current gVisor docs explicitly warn that even familiar runtime indicators such as dmesg can be imitated and should not be trusted for security attestation: [gVisor Docker quick start](https://gvisor.dev/docs/user_guide/quick_start/docker/). Rootless mode also has known limitations regarding host environment and resource enforcement: [Docker rootless docs](https://docs.docker.com/engine/security/rootless/).

A **single fixed canary** is not a hostile-code red team, nor a defense against kernel/gVisor vulnerabilities, confidential side-channels, all syscalls, cgroups exhaustion, side effects of a compromised operator, or adversarial supply-chain signing. Stage24 deliberately does not add a public uploader or invoke Stage4/22 at runtime.

## 4. Tests and release criteria

Dedicated Python3.12 GitHub checks use *synthetic signed statements and fake Stage23 receipts only* with ephemeral Ed25519 keys. They cover real signature math, key replacement after restart, source receipt tampering, invalid review scope, replay and immutable image pins, revocation, private filesystem permissions, symlink safety, no production mutation, no network, and admin-only read-only rendering. Stage23/22 and existing admin panel regressions are run with a clean installed-wheel acceptance and the repository's full standard required checks.

**Stage24 is complete as nonproduction code only after GitHub CI.** `HOST_RUNTIME_INDEPENDENTLY_UNVERIFIED`, `public_plugin_install_authorized=false`, `telegram_publication_authorized=false`, and `broker_order_authorized=false` are immutable until a *separate*, explicitly approved live host validation/integration stage. Public strategy installation and automatic orders remain prohibited.
