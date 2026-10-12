# Stage 40 — Evidence-aware security readiness matrix, default DENY

**Nonproduction, offline library only.** No live host was designated, tested, configured or deployed. Stage40 makes the security release decision more transparent without granting permissions: twelve separately named **independent real-host acceptance blockers** remain open even when every historical signature, synthetic policy and self-reported receipt is internally consistent.

## Problem addressed

Stages32–39 created several independent signed security statements: Stage32 local TEST certificate preparation, Stage33 reviewer declarations with a twelve-category checklist, Stage34 sanitized loopback TLS / TCP self-observation, Stage35 binding and SQLite custody, Stage36 independently pinned portable signature verification, Stage37 declared restrictive nftables/runsc templates and Stage38 self-process kernel observations, linked with another auditor signature in Stage39.

A green Stage39 result is **not** proof of actual host identity, live firewall, real HTTPS infrastructure or gVisor's containment of an untrusted extension. A software operator needs a consistent, machine-readable view of exactly which checks were stated, which static or self-reported artifacts exist and what **still requires independent real-host testing**.

## Implemented contract

`assess_offline_host_readiness(bundle, stage39_options=..., operator_ack=True)` **re-runs** the complete Stage39 verification before producing any status, which in turn re-runs the independent Stage37 + Stage36 signing chain. It does not trust a caller-supplied `"success"` flag. The Stage39 options must be independently operator supplied and include all original source bytes, independently pinned Ed25519 public key hashes, the externally pinned Stage35 SHA256 and sequence, bounded challenge, trusted timestamp and exact host/nodename.

After that full check, Stage40 reads the already authenticated Stage33 twelve-check status fields from the embedded Stage36 archive. It reports for every required area:

* `NOT_RUN` → `NOT_RUN_NO_INDEPENDENT_MEASUREMENT`.
* `DECLARED_PASS` → `SIGNED_REVIEWER_CLAIM_ONLY` (**not a measurement**).
* `DECLARED_FAIL` → `SIGNED_REVIEWER_REPORTED_FAILURE_ONLY` (**not independently reproduced**).

For a subset of areas it additionally names the limited earlier supporting material: Stage32 test certificate and Stage34 self-reported loopback TLS, Stage37 declared nftables/runsc configuration or Stage38 self-process kernel hashes. These are labeled as **static template or self report**; none is converted to independent verification.

The result `OfflineHostReadiness` is an immutable, safe-to-display diagnostic with host alias, nodename, Stage35/39 SHA256 references, sorted per-check blocker IDs, signed declaration counts, exact independently required future tests and canonical JSON + SHA256 serialization. No private keys, raw certs, sensitive kernel data, application credentials, arbitrary source or signed raw packets are returned.

## Hard release fence

The number of missing **independent host controls stays 12** for this Stage40 API. Every check has `independently_verified=false`, `release_gate_satisfied=false` regardless of signed declarations and static evidence. The aggregate always reports `FULL_OFFLINE_CRYPTO_CHAIN_VALIDATED_HOST_NOT_ATTESTED` with actual host testing, real firewall, hostile-code containment, public API, public plugin install, untrusted-core execution, Telegram signals and broker orders **all false**.

This is a deliberately narrower guarantee than a security certification. It is not possible to bypass the gate by setting a JSON `passed` value, re-signing a fake Stage33 pass or substituting a stale Stage35 checkpoint. New live-host evidence validation and separate release authorization would require **a different contract and explicit new user approval**.

## Tests and outstanding work

Dedicated GitHub Python3.12 acceptance tests use real ephemeral Ed25519 signatures over fully synthetic cross-stage evidence, check all twelve blockers, exact reason strings, sanitized deterministic JSON, static-vs-real differentiation, wrong signer/challenge/host/pinned checkpoint, forged Stage33 pass and nonproduction fencing. They also execute all Stage22–39 regression tests in both checkout and independently installed wheel, and preserve all existing full-corpus PostgreSQL and publication-safety CI checks.

**Stage40 readiness:** `DIAGNOSTICS_COMPLETE / LIVE_HOST_NOT_SELECTED / REAL_HOST_TEST_NOT_RUN / PUBLIC_DEPLOYMENT_AND_TRADING_BLOCKED`.

A genuine path beyond Stage40 requires separately designating an isolated credential-free disposable machine and explicitly authorizing a read-only inspection of the exact host identity, actual TLS peer/network/firewall state and actual runsc/namespace/cgroup negative tests. This step does not buy or provision servers, run external commands, inspect live servers or touch the Telegram production bot or private NY First-Reversal.
