# RUNTIME-A4 — Offline security-evidence admission contract

**Status:** GitHub-only, nonproduction, **evidence-review preparation**.
No containers, brokers, servers, Telegram bots, production data, or actual
trading algorithms are changed or launched in this stage.

## What changes

`naseri_markets/runtime_a4_security_evidence.py` validates a strictly
bounded JSON envelope (`payload`, `mac_sha256`) authenticated by
HMAC-SHA256 with an **out-of-band** operator trust key. The receipt is
bound to an exact reviewed runtime kind, pinned OCI image digest, complete
Stage-4 runtime policy, named host, expected one-time challenge nonce, trusted
issuer name, exact worker digest and a maximum 15-minute UTC window.

Every mandatory probe **claim** must be present and exactly true:
rootless Docker, actual runsc runtime, network rejection, read-only root,
no mounts, no privileges, nonroot uid, CPU/RAM/PID limits, no worker
credentials, OCI cleanup, and successful fixed-fixture Core API ABI tests.

Unknown/duplicate fields, wrong pins, incorrect runtime language,
wrong operator issuer/host, missing/expired/future challenge, unexpected
float/NaN, invalid MAC, extra checks and absent security claims fail closed.
Maximum receipt size is 16 KiB.

## Critical meaning of verification

A valid HMAC demonstrates **that someone possessing the review key signed
the supplied claims**, not that the probes were conducted, that the
container actually ran under gVisor, or that the host is secure. The
verifier and issuer share the same secret: **this is not independent,
asymmetric third-party attestation**, and the secret must never be committed
to GitHub or supplied to a worker. The key used in CI is explicitly fake.

The return value `EvidenceReview` therefore always says:
- `SIGNED_CLAIMS_MATCH_REVIEW_ONLY`;
- `host_isolation_certified=False`;
- `untrusted_code_execution_permitted=False`;
- `worker_installed=False`;
- `live_enabled=broker_enabled=telegram_enabled=False`.

This module does not enable/modify a runtime profile, start Docker, grant
PAPER permission, clear A3 quarantine or issue any authorization token.
The existing A1 host can still be called directly by development code;
A4 is **not yet a system-wide enforced runtime gate**. Production execution
remains out of scope. A nonce is supplied by the caller but replay-resistant
nonce custody and cross-process nonce consumption are not implemented here.

## Remaining work before allowing untrusted programs

1. Build and lock reproducible worker images and interpreter packages to
   verified immutable SHA-256 digests. Sign artifacts with a separately
   controlled issuer key. A2's tagged candidate is not such a release.
2. On a **separately authorized, disposable** rootless Docker+gVisor host,
   collect genuinely independent probe evidence: runsc runtime status,
   restricted filesystem/network/resource/secret tests, orphan/cleanup and
   adversarial static fixtures, with external trusted audit receipts.
3. Secure anti-replay challenge custody (durable nonce ledger), independently
   pinned signer trust, consistent host provenance and approval expiration.
4. Integrate a certified admission guard **mandatorily** into A1/A3 dispatch,
   without allowing a code path that bypasses it. Run cross-process and
   crash/restart conformance before granting even PAPER execution.
5. Keep Al Brooks and NYFR separately reviewed, unmodified; their adapters,
   runtime privileges, live data, broker orders and Telegram publication are
   independent later authorization stages.

## CI (no external binaries or uploaded code)

`python -m pytest -q tests/unit/test_runtime_a4_security_evidence.py`

Tests verify four language scopes, fabricated valid receipts, forged MAC,
false/missing probe claims, wrong image/policy/host/nonce/issuer, malformed
JSON and timestamps, nonproduction fence, and no Docker/process execution.
A test-valid receipt is **not** evidence of a real secure host.

**Stage verdict:** `RUNTIME_A4_EVIDENCE_CONTRACT_PREPARED`.
`A4_ISOLATION_CERTIFIED` and `A4_EXECUTION_AUTHORIZED` are **NOT granted**.
