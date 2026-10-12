# Stage 25 — Cross-ledger third-party Core preinstall evidence gate

**Nonproduction only: operator-initiated, no source execution and no public installation.**

Stage25 is an explicit **read-only cross-check** of the otherwise independent Stage22 (tenant-restricted offline Core admission), Stage23 (dual-signed generic public-source candidate), and Stage24 (reviewer-signed observation of a manual Stage23 gVisor canary). The checks identify mismatched, revoked, stale or previously enabled metadata without authorizing installation. It does not run or connect the plugin.

## Current admission contract

`naseri_markets.preinstall_evidence_stage25_v1.review_preinstall_evidence` accepts *already-open, explicitly operator-authorized* Stage22, Stage23 and Stage24 owner-private witnesses. It requires exact tenant, publisher, publisher-key identifier, CoreManifest, selected CoreBinding, source bytes, image SHA256, host alias and bounded source evidence. The independent trusted host must authenticate identities **before** passing them to this API. Merely calling a function with a tenant name is not authentication.

The reviewer validates:

1. Stage23's current, non-revoked, non-expired Ed25519 publisher **and** operator candidate with immutable source, manifest, binding and pinned image;
2. Stage24's current, non-revoked, non-expired Ed25519 reviewer statement, exact Stage23 fixed-canary receipt digest, pinned image and expected host alias; this proves signed *claims*, **not** remote attestation;
3. Stage22's stored tenant/core/version/instance/manifest/binding/source identities, its exact Stage4 isolated image, required **DISABLED** state and **zero** earlier execution attempts (even a prior failed attempt blocks);
4. nonproduction opt-in fences, a no-source-import boundary, no database mutations, no Telegram calls, no provider or broker connections.

If an input, signature, operator identity, expiry, locked revision or runtime pin is inconsistent, the review refuses with an anonymized error. If all local evidence matches, the result is **only** `LOCAL_CROSS_STAGE_EVIDENCE_MATCHED_NOT_AUTHORIZED`. It always sets `installation_authorized=false`, `activation_authorized=false`, `runtime_wiring_authorized=false`, `telegram_signal_authorized=false`, `broker_order_authorized=false`, `live_trading_authorized=false`, `host_isolation_independently_verified=false`.

Stage25 intentionally exposes no public authorizing endpoint or enable toggle. It does **not** hook Stage22's existing nonproduction enable/evaluate API; therefore it is **not yet a universal enforcement mechanism** for callers that bypass Stage25. Such integration must be a later explicit audited change with atomic revocation checks. A Stage22 state previously enabled is a hard review refusal. This API is an inspection tool, not a substitute for authenticated tenant isolation, real hostile-code sandbox audits or a secure public marketplace.

## Why real-host approval remains BLOCKED

Stage23's Docker/gVisor fixed smoke test has never been run by this project's GitHub-only implementation on an **explicitly designated disposable host**. Even if it is run, a signed Stage24 statement about the output does not independently prove the claimed process isolation or resistance to malicious code. Docker documentation also notes that in rootless mode cgroup resource controls may be ignored without cgroup v2 + systemd: [Docker rootless resource limitations](https://docs.docker.com/engine/security/rootless/tips/), [gVisor rootless constraints](https://gvisor.dev/docs/user_guide/rootless/). Such runtime claims need host-side checks and independent assessment, not an inferred PASS from unit tests.

Before any future public plugin installation, separate authorization must establish actual sandbox host custody, resource quotas in that specific environment, signed publisher onboarding and key revocation, atomic enforcement of the trusted admission path, provenance of container image and actual isolation test evidence with adversarial cases. No true source execution is authorized by Stage25.

## Acceptance scope

New offline fixture-only GitHub workflow checks real ephemeral Ed25519 signature verification, revoked publisher/reviewer, mismatched tenant/host/image/source, expiry, previously enabled or attempted Stage22 workloads, read-only result, missing ack and production fences. It runs Stage22–24 regression plus Python3.12 isolated installed wheel and existing all-repo publication/DB controls. No gVisor image provision, production database write, Telegram message, real market request, NY First-Reversal implementation or broker order.

**Status after successful CI remains: `CROSS_STAGE_EVIDENCE_ONLY / PRODUCT_NOT_READY_FOR_PUBLIC_UNTRUSTED_PLUGIN_INSTALL`.**
