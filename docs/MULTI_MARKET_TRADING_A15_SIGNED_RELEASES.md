# Multi Market Trading — A15 Signed Private Release & Local Monotonic Floor

**Verdict target: NON-PRODUCTION simulated service release assurance only.**
Builds on the completed A8–A14 foundation. No production access, private
engine source, real publisher signer, network calls, trading or Telegram.

## Two independent cryptographic gates

1. **A12 / A13:** grants permit the *disabled* private plugin for one
   installation, generation, descriptor manifest and offline PAPER purpose.
   Expired/revoked A12 evidence fails at every A14 admission point.
2. **A15:** an independently operator-pinned Ed25519 **publisher public key**
   authenticates a separate release envelope. The signature covers the exact
   SHA-256 of one synthetic A14 ZIP, release sequence, installation/engine,
   A8 descriptor hash, A12 trust generation, mock release/version, signer
   identity/generation and validity window.

Publisher private keys **never** exist in the published platform runtime.
Tests generate throwaway keys at execution and discard them after use.
Signer authenticity rests on review of the initial public key fingerprint
out of band. **Copying a digest provided by an untrusted publisher does not
establish trust.**

### Signed envelope

The signed payload is canonical ASCII JSON (sorted keys, compact
separators, no NaN). The Ed25519 message is:

`b"MULTI-MARKET-TRADING-A15-RELEASE-ED25519-V1\\x00" + canonical(release)`

Each signed release has exact fields:

```json
{
  "schema_version": 1,
  "kind": "synthetic_private_data",
  "mode": "offline_paper_only",
  "engine_id": "private_example",
  "engine_version": "1.0.0",
  "installation_id": "a14_fixture_install",
  "manifest_sha256": "<A8 descriptor hash>",
  "trust_generation": 1,
  "release": "1.0.0",
  "release_sequence": 1,
  "artifact_sha256": "<exact signed A14 ZIP hash>",
  "publisher_key_id": "fixture_publisher_one",
  "publisher_generation": 1,
  "issued_at": 42,
  "expires_at": 300
}
```

The outer envelope has exactly `release` and `signature_b64`.
Values above are illustrative; timestamps are fixture values only.
Allowed signature validity is at most seven days.

## Independent locally persisted rollback floor

`SignedReleaseAuthority` uses a **separate SQLite file** from A14's
`state.json` / staged release directory. Every successful signed
release promotion stores the exact signed receipt and monotonically
advances `(release_sequence, artifact_sha256, signer_generation)` in
a synchronous SQLite transaction. Sequence comparisons are integers, not
semantic-version strings.

`SignedMockDeploymentManager.install()` checks:
- A14 STOPPED and exact revision CAS
- current signed A12/A13 offline admission and private disabled descriptor
- strict A14 package structure and content hash
- pinned A15 publisher Ed25519 signature and exact context binding
- separate local floor: strictly higher sequence, or identical sequence
  for the **same** previously witnessed artifact only

**Fail-closed commit order:** record the signed release and advance the
local floor **before** updating A14's atomic active pointer. A crash
between them can temporarily block starting an older package but cannot
silently authorize the earlier package through A15. A fresh retried
installation of the same signed artifact at the same sequence is allowed
to recover. A15 never deletes the retained A14 previous release.

`start()` checks the **current** signed receipt, publisher revocation
and rotation generation, signature time window, independent high-water
floor, A14 archive bytes and fresh A12/A13 admission *again*.
`stop()` is deliberately allowed after authorization revocation.

**Rollback policy change vs A14:** A14's pointer rollback remains a
fixture demonstration. Once A15's sequence floor has advanced, A15 blocks
starting a previous low-sequence package, including after A14's injected
failure auto-rolls its pointer back. Restoring old A14 metadata or
attempting direct A15 `rollback()` does not override the floor.
To redeploy an older software version intentionally, the trusted
publisher must issue a **new signed synthetic artifact with a higher
release_sequence**; no emergency operator force switch exists.

### Publisher key rotation and revocation

`rotate_publisher()` requires BOTH an independently approved new key
digest AND an Ed25519 handover signature from the current trusted key
over domain-separated, installation/engine-bound rotation fields.
Publisher generation must increment one step. Rotation keeps the
release high-water floor; old releases stop being admissible.

`revoke_publisher(expected_generation=...)` prevents future installs
and starts, but controlled stop of an already started mock process
remains available. No private signing keys are stored in the public
repository or runtime.

## Boundaries that A15 does NOT solve

- Separate local SQLite is **not** a genuine externally hosted,
  tamper-proof monotonic witness. Restoring all files together can roll
  back A15 itself; host-admin or file-write compromise is not resisted.
- Full crash consistency across the A14 JSON and A15 SQLite is not
  atomic. Fail-closed sequencing favors safety over availability;
  production would need durable transactional release intent and
  independent external counter pinning.
- A14 remains accessible as an **inert mock API**. It is not a secure
  production service manager. A15 requires use of its signed facade;
  no OS-enforced code-execution admission or hardened service sandbox
  has been delivered.
- The Ed25519 release signature proves possession of a particular
  operator-pinned publisher key, **not** business ownership, code quality,
  strategy secrecy, license validity outside A12, or a public PKI audit.
- No real private engines, external downloader, Linux systemd, Docker,
  MT5 execution, live-market data, Telegram, HSM/KMS or production VPS.
- No automated active-service kill on mid-run signer/grant revocation;
  future production orchestration must implement it and prove its timing.
- A15 keys are standalone publisher keys, intentionally distinct from
  A12 issuer-license keys. Neither substitutes for the other.

## Non-production tests and source custody

`tests/unit/test_a15_releases.py` exercises real ephemeral Ed25519 signatures,
artifacts, cross-installation scoping, tampering, expired/future envelopes,
sequence conflict, witness continuity across restarts, rollback rejection,
mock fail-start, authorized key rotation and revocation.

`.github/workflows/a15-signed-private-release.yml` runs A15+A14+A13
security suites on an ephemeral Linux runner, source baseline checks,
Ruff checks, private-import fence and a public-only wheel inspection.
The historical `production_source/` snapshot, legacy manager,
PostgreSQL, runtime settings and private strategy code remain unchanged.

**Production-readiness verdict: NOT APPROVED.**
