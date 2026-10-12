# Stage 32 — Disposable-host preflight: private local TLS fixture, proposed policy, signed offline dossier

**Mode: GITHUB / NONPRODUCTION ONLY.** This stage does not deploy to any host or configure an operating-system firewall. It creates **a checkable preparation contract**, not a real-host certificate, remote attestation, full TLS audit, or public service authorization.

## Local test material assessment

The Stage32 `verify_local_test_certificate_pair` accepts two **already provisioned** owner-private local files, a separately expected SHA256 of a DER certificate, an exact disposable hostname ending in `.invalid` or `.test`, a trusted test timestamp and explicit operator acknowledgement. It rejects symlinks, non-regular/multiply-linked files, non-private parent directories, files not owned by the operator, weak file permissions (requires 0600), unexpectedly large files and insecure or out-of-bounds test material.

Using `cryptography.x509`, it checks the signed test certificate's SAN against the expected hostname, certificate validity, basic CA designation, RSA/EC public key size, digest algorithm and independent certificate fingerprint. Then an `ssl.SSLContext(PROTOCOL_TLS_SERVER)` loads the certificate and private key to check that they correspond, with TLS 1.3 min/max configured. **There is no socket, no HTTP/TLS listener, no TLS handshake in this stage, no real CA chain validation, and no scan of any actual VPS.** The Stage31 `MemoryBIO` test separately covers a real *laboratory* TLS1.3 handshake; it still is not a network-level host test.

No private key is created by the implementation, exposed in its result, uploaded, logged, exported or stored in its ledger. Tests generate disposable ephemeral certificate/key pairs in GitHub Actions scratch directories; private key files never enter git.

## Proposed host policy (not observed state)

`review_proposed_host_policy` validates an **exact** JSON-compatible dictionary of desired restrictions: a disposable nonproduction environment, operator-pinned authority name, `127.0.0.1:443` only, TLS 1.3 minimum, no public ingress, no external internet egress, no accepting client-supplied Forwarded headers, no broker credentials, no Docker socket, no untrusted code execution, and bounded API request size 132,000 bytes.

It emits a SHA256 of the canonical policy bytes, never a green firewall status. Passing a proposed policy **does not configure the firewall or prove actual Linux network state**. Real packet-filter/cgroup/container/runtime host validation remains a separate future authorized task.

## Independently pinned reviewer signature and append-only custody

The `HostPreparationDossier` accepts a reviewer-signed, canonical Ed25519 envelope. The reviewer public key and its independent SHA256 pin must be supplied out of band. The signed claim binds host alias, monotonically increasing sequence number, observation window of at most 3600 seconds, local fixture certificate SHA256 and exact proposed policy SHA256, and the **narrow review scope** `static_local_fixture_and_proposal`. Every affirmative statement about actual host verification, public deployment, public installer, Telegram publication, untrusted source execution or broker orders is *rejected*.

The owner-private SQLite dossier (0600, parent 0700) stores signed review bytes and hashes, has immutable record-row update/delete triggers, a sticky reviewer public key anchor, sequence continuity per host and a safe summary with all authorizations set false. This is **local custody**, not independent offsite anti-rollback: somebody who owns or replaces the entire SQLite file and its host filesystem is outside that guarantee. A forged statement signed by a compromised reviewer may still be accepted as a *statement* and cannot be converted into actual runtime attestation.

There is **no public review uploader, no signing private keys issued, no remote credential collection**, no BotFather/Telegram changes, no PostgreSQL production migration and no Docker/gVisor installation or provisioning. No private NY First-Reversal source or broker orders are touched.

## Acceptance

Python 3.12 GitHub CI tests the local disposable certificate/key pair against wrong SAN, certificate pin, private key mismatch, symlink and weak permissions; rejects broad ingress/egress policies; checks real Ed25519 review signatures, claims pretending a live host passed, wrong reviewers, tamper, expiry, repeated/gapped sequence IDs, persistent reviewer pin across reopening, immutable local custody, and production fences. Full Stage22–31 regression, isolated installed-wheel acceptance, PostgreSQL and publication safety checks are prerequisites to merge.

**Verdict after successful CI: `OFFLINE_DISPOSABLE_HOST_PREPARATION_COMPLETE / REAL_HOST_SECURITY_NOT_VERIFIED / PUBLIC_API_DEPLOYMENT_BLOCKED`.**

A future Stage33 **requires separate explicit designation of an isolated, credential-free disposable host** to inspect live services, port listeners, certificate issuance, firewall rules, actual TLS exchange to a real endpoint, logging/secrets, proxy provenance, and (separately) Docker/gVisor isolation. This Stage32 is not permission to purchase, create, modify, deploy or connect to that host.
