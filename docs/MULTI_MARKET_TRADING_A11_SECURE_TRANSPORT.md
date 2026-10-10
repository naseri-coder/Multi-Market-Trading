# Multi Market Trading — A11 Real Two-Process mTLS Rehearsal

**Status:** GitHub-only, non-production implementation. Product name is
**Multi Market Trading**; the canonical public GitHub slug is
`naseri-coder/Multi-Market-Trading`. Existing legacy `naseri_markets`
module paths, package versions, database/Compose IDs, past documents and
SHA-256 manifests are retained as compatibility identifiers. The project is
NOT called NASERI MARKETS as a product.

## What is real in A11

GitHub Actions runs two genuinely independent Python OS processes on
one disposable Ubuntu runner:

1. The public-side test harness uses A9 `PluginManager`,
   A10 `PrivatePaperConnector`, and A11 `LoopbackMtlsExchange`.
2. The owner-side **fixture process**, stored only under
   `tests/fixtures/a11_owner_process.py`, uses Python's TLS server
   implementation and A10 HMAC validation to construct a synthetic
   PAPER-only reply. No actual private strategy code is present.
3. Ephemeral OpenSSL CA, server and client certificates (with distinct
   SAN identities and serverAuth/clientAuth key uses), plus two
   independent random HMAC direction keys, are generated in runner
   temporary storage and never committed or published as artifacts.
4. Both sides require a verified certificate chain; client checks
   expected owner DNS identity, server requires a client certificate
   whose SAN is `public-bot.fixture`.
5. The server binds ONLY `127.0.0.1` on a random port. The client
   is physically hard-coded to the same loopback address; arbitrary
   domains, external IPs and insecure SSL contexts cannot be used.
6. A10's timestamp/HMAC/request-nonce response binding plus persistent
   replay/revocation checks remain in place and the final signal is
   validated as A7 PAPER before recording in the local A8 journal.

## Resilience

The A11 transport has independently bounded connect/write/read time,
a strict 20,000-byte length-delimited message cap, serialized requests,
**no automatic retries**, and a fail-closed circuit breaker with
operator-configurable attempt limit/cooldown. Service loss, no client
certificate, wrong signed client identity, untrusted CA, wrong server
hostname, repeated signed request and revoked key must fail closed.
This is not a high-availability service manager, and resetting the
breaker does not reconcile an unknown previous request outcome.

## Still intentionally NOT delivered

- No external/non-loopback network connector, DNS discovery or hosted
  endpoint; no deployment files, port exposure or key distribution.
- No TLS root of trust enrolled from an independent license authority,
  PKI rotation/recovery, hardware-backed custody, revocation of
  certificates, entitlement verification or true publisher attestation.
- No real NYFR strategy or private GitHub repository changes.
- No live source attestation, real market data, Telegram publish, trading
  permissions, broker orders or Production service startup.
- No upgrade of the existing `crypto-price-action==0.3.2` distribution,
  Docker volume, PostgreSQL migration, or `multi-market-trading==0.4.0rc1`
  package version. The new public TLS module is packaged by the existing
  isolated wheel procedure without bumping or releasing a new artifact.

A11 completes the **separate-process, verified-transport rehearsal** only.
Production requires a separately approved architecture and real
owner-operated service with proper CA/trust-store, mTLS endpoint,
key custody, rate limits, licensing and operational recovery procedures.

Evidence: `.github/workflows/a11-loopback-mtls.yml`, real negative
handshake tests in `tests/unit/test_a11_mtls.py`, and the unchanged
existing A5–A10/full PostgreSQL/CodeQL/publication safety workflows.
