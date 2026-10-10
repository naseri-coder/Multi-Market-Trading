# Multi Market Trading — A12 Trust, Certificates & Private Engine Grants

**Status:** GitHub-only, non-production. Official project name is **Multi Market
Trading**. All A12 operations and new cryptographic grants are strictly for
**offline/synthetic PAPER analysis**. No remote endpoint, Telegram send,
order execution, NYFR source or production server is involved.

## Split trust architecture

The public repository stores **only** operator-approved metadata and issuer
PUBLIC key material. Private signing keys and private strategy source must
remain separately controlled by the issuer/owner.

1. **Owner trust policy** (strict schema v1) binds engine ID and version,
   SHA-256 of the previously approved plugin descriptor, expected TLS owner
   DNS, exact owner certificate DER SHA-256, exact CA PEM SHA-256,
   issuer Ed25519 public key, issuer ID, and monotonically increasing
   policy generation. An operator must independently approve its SHA-256;
   hashing untrusted bytes received from the same network is NOT trust.
2. **Staging and promotion**: a new generation can be staged without changing
   current admission. A compare-and-swap promotion retires the old generation.
   New CA/certificate/publisher key is never accepted automatically. An
   explicitly revoked generation cannot be reused. An older signed grant
   cannot authorize the new generation. TrustStore persists these states
   and serial/key revocations in a separate local SQLite database.
3. **Ed25519 PAPER grant**: a separate issuer signs a domain-separated,
   canonical version-1 grant for one installation, engine, version,
   descriptor digest, issuer ID, owner DNS, exact trust-policy generation,
   issued time, expiration (maximum 24h), serial and **paper_analysis only**.
   The public side verifies it using a trusted public key. No symmetric
   issuer secret is needed on the public bot. Expired, forged, stale,
   cross-installation or revoked grants are rejected.
4. **TLS identity pinning**: A11 mTLS already verifies CA chain, hostname and
   certificate expiration in the real TLS handshake. A12 adds optional
   exact owner leaf fingerprint pinning **before sending any request**
   in `LoopbackMtlsExchange`. The independent A12 admission gate checks
   the approved CA and leaf hashes. Production MUST wire the same verified
   policy into both TLS handshake pinning and grant admission.
5. **Request lifecycle fence**: A10 PrivatePaperConnector optionally
   accepts an `OfflineAdmission` gate. It checks the signed grant, pins,
   policy generation and registered descriptor BEFORE requesting the
   synthetic owner. It validates grant/revocations and pin state AGAIN
   after the owner's response and before returning the PAPER envelope.
   Revocation/rotation/expiration during an async exchange fails closed.

## Cryptographic dependency

The existing `multi-market-trading==0.4.0rc1` wheel still has **zero required
third-party dependencies**. Ed25519 grant verification requires the audited
`cryptography` package, installed explicitly ONLY in disposable A12 test
environments. If it is not installed, the grant verifier refuses the request;
there is NO unsigned or HMAC license fallback. A separate future release
must declare and lock the security dependency before actual deployment.

## Operational limitations

- SHA-256 policy approval alone is not a PKI or publisher signature.
- A12 does not contain a licensing authority, issuer signer service,
  certificate issuing service, commercial billing, key vault, hardware
  security module, OCSP/CRL handling, or auto-refresh.
- Local SQLite generation fences are NOT resistant to restoring the entire
  trust DB to a stale snapshot. Production requires an **independent trusted
  monotonic floor** and external revocation evidence.
- TLS is still **loopback-only** and permits fixture DNS ending in
  `.fixture`. No real private NYFR connection or production installation
  is attempted.
- The test fixture signer creates a new Ed25519 secret in-memory and never
  stores it in GitHub source, artifacts or build metadata.
- Public `naseri_markets` identifiers, the legacy 0.3.2 distribution,
  Docker/Compose/data volumes, source integrity manifest and the
  0.4.0rc1 package version are preserved. No actual release tag is issued.

## Test and release gates

The A12 GitHub workflow tests valid issuance, invalid Ed25519 signatures,
cross-installation grant substitution, wrong engine/version/digest, stolen or
rotated cert pins, false admin authority, expiry, key/serial revocation,
staged vs active CA rotation, rollback prevention, restart persistence
and revocation during in-flight PAPER analysis. All existing A5–A11,
PostgreSQL, Docker, CodeQL and Publication Safety workflows remain mandatory.

**A12 is an offline trust/entitlement prototype, not a production license
authority or deployed private engine.** Real provider-independent signer
custody, external monotonic rollback fencing, trust-store distribution,
revocation propagation and remote mTLS require further authorization.
