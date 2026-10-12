# Stage 23 — Independently signed code candidate + real-host isolation canary

**Nonproduction security candidate. Not a public-plugin marketplace, not an execution grant, not a certified gVisor installation.**

The existing A24 and A25 signed release contracts intentionally approve **only inert DATA**, not Python sources. Stage 23 neither weakens nor reinterprets them. The separate Stage22 tenant-bound durable ledger and Stage4 rootless Docker/gVisor host remain disabled unless separately approved. Stage23 adds an *independent executable-code candidate review contract* and a *manual actual-isolation probe*, with two different evidence types and NO automatic connection between them.

## 1. Separate publisher/operator signatures for a reviewed source candidate

`signed_core_candidate_stage23_v1.py` accepts only a small, canonical, exact JSON envelope that binds an **independently operator-trusted** tenant, native binding ID, Core API manifest digest, binding digest, Python source digest, pinned OCI `image@sha256` identifier, expiry (max 24 hours), publisher ID, operator approval and monotonic candidate sequence.

Publisher and operator keys must be different independently known Ed25519 public keys, each verified against an out-of-band SHA256 pin and then locked into a 0600 locally durable SQLite witness. The two signatures use **new Stage23 domain separators**, not A24/A25's inert-data signing permissions. The operator signature covers the exact publisher-signed claim. Any extra field, version change, live-trading capability, signature mismatch, private-owner identifier, oversized source, revoked key floor, publisher/tenant mismatch, wrong image, wrong source bytes or old sequence is denied. A different executable source or image requires a **new binding identity and review**, even if signatures are valid. Local revision floors are not off-device anti-rollback protection.

Only a `SIGNED_EXECUTABLE_CANDIDATE_REVIEWED_NO_INSTALL` receipt is returned, explicitly declaring `executable_installed=false`, `executable_run_authorized=false`, `public_marketplace_authorized=false`, `trading_authorized=false`. The signed candidate never imports, extracts, downloads, registers or executes the provided source. **Neither this receipt nor an A24/A25 grant automatically enables Stage22.**

The Stage23 module does **not** create issuer private keys or expose a signing CLI. A future trusted owner-side signing service can emit the canonical domain-separated envelope only after a separate secure publisher-key onboarding and authorized signing workflow. The tests use ephemeral fake Ed25519 keys on disposable CI runners.

## 2. Real Docker rootless + gVisor probe, manually on a disposable host

`disposable_gvisor_canary_stage23_v1.py` provides a fixed, built-in harmless canary. It uses Stage4's unchanged `SecurePluginPolicy`, rootless-socket ownership, daemon rootless-mode verification and exact `--runtime=runsc`, `--network=none`, `--read-only`, `--cap-drop=ALL`, no privilege/new caps, no host bind mount and pinned OCI image flags. It does **not** execute any submitted developer code.

Inside the isolated container, a fixed local canary tests: UID 65534, empty effective capabilities, kernel NoNewPrivs flag, Docker socket absence, only-loopback network interfaces, rootfs write denial, a single outbound attempt to RFC5737 reserved documentation address `192.0.2.1` (success must be denied), root private-key path unreadability. The parent verifies an unpredictable nonce and exact bounded JSON boolean fields. After Stage4 attempts cleanup, the parent separately queries the rootless Docker daemon for an orphan container with that exact random name; uncertainty is a hard failure.

**This is an isolated-host smoke test, not hostile-code escape testing or a certificate of complete isolation**. The Docker daemon, gVisor version, kernel, /proc semantics, resource limits under sustained stress, side channels, orphan recovery across abrupt host failure, and external PKI still require independent authorized review. A successful probe does not sign a plugin or authorize a marketplace.

Manual execution is *not* part of GitHub CI. To run on an independently approved **credential-free, disposable nonproduction Linux host** that already has rootless Docker, gVisor `runsc`, verified pinned Python 3.12 image and operator-reviewed paths, use (substitute a real independently verified image pin):

```sh
MMT_NONPRODUCTION=1 MMT_DISPOSABLE_SANDBOX_HOST=1 \
python -m naseri_markets.disposable_gvisor_canary_cli_stage23_v1 \
  --image 'registry.example.invalid/verified-python@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' \
  --ack-disposable-host-canary
```

**The example image identifier is deliberately fake; it will not run.** Do not paste it into an actual environment or change the command to provision Docker automatically. No root/sudo execution or production/owner machine testing is authorized by this stage. The CLI fails closed without `MMT_NONPRODUCTION=1`, `MMT_DISPOSABLE_SANDBOX_HOST=1`, a non-root caller, explicit acknowledgment, exact pinned image and genuine existing rootless socket. The output identifies `OBSERVED_SINGLE_DISPOSABLE_HOST_CANARY_NOT_SECURITY_CERTIFIED`, and retains `actual_host_isolation_independently_audited=false`, `public_plugin_install_authorized=false`.

## 3. Acceptance evidence and hard blockers

Automated GitHub unit tests mock ONLY the host launch and cleanup actions; they must not claim actual Docker/gVisor deployment or isolation. They exercise Ed25519 signatures with real ephemeral test keys, revocation and anti-rollback, accidental source/image reuse, forged tenant/publisher, malformed claims, default-disabled sandbox, challenge response tampering, each failed containment check and nonproduction fences. Stage22 durable admission and Stage4 parser regressions continue to pass; separate clean-wheel Python 3.12 tests prove the two Stage23 modules can be imported and used independently of repository source paths.

**Still BLOCKED:** installation/execution of arbitrary third-party core by an unauthenticated tenant, publishing strategies to end-users, actual live exchange feeds, strategy profitability certification, Telegram publication, broker order authorization, margin/risk bypass, production release or host deployment. A standalone signed source candidate and a host canary are **separate evidence artifacts**, not an automatic signed-plugin deployment pipeline. Future production work must add authenticated publisher onboarding, key rotation/revocation, per-tenant operator scope, verified runtime/kernel/cgroup stress controls, real host forensic cleanup and integration with Stage22's same-transaction revocation checks. Never silently fall back to trusted-local `python -I -S` for untrusted code.

Owner-only NY First-Reversal and private source remain **outside** this repository. No production bot, PostgreSQL database, server, GitHub secret, broker credentials or Telegram state changed.
