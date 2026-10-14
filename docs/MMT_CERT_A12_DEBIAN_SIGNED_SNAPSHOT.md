# CERT-A12 — signed Debian historical snapshot (nonproduction)

**Intent:** Close the mutable APT index part of CERT-A11 WITHOUT granting
new execution authority. Verified entirely on disposable GitHub-hosted
builds. No TELMIVO, License Authority, trading server, broker, Telegram,
user-uploaded code, database, production deployment or RUNTIME-A6 change.

## Observed data, not guessed

On 2026-10-14, a disposable pinned Python 3.12 Bookworm base successfully
fetched signed Debian Snapshot APT indexes at requested archival timestamp
20261014T000000Z, using the base image's Debian archive keyring. Then APT
downloaded and verified **all existing 372 CERT-A11 .deb archives** with
identical per-package names/versions/architectures/SHA-256 and closure digest:

47bd698232b4f624d1aab35c6453e1f01641b1b6ebdd8d4d7dc38a4dd19ae872

The exact signed InRelease file bytes were observed in the same successful
GitHub-hosted discovery run and frozen in a separate reviewable lock:

| Suite | InRelease SHA-256 |
| --- | --- |
| bookworm | 77737fa4b34f2693e982cc9ee35736816c35a7778fc2d326cc1bbf5b301fe1aa |
| bookworm-updates | cad962818b6fc8955fc243553c75f2bfff73909e3516099b2fcd3476925abeb3 |
| bookworm-security | 9e5050b09604010af7190f3e8391739d9fc7dc11616d1a25e90c7e25565e4f92 |

The archival timestamp identifies the latest snapshot at or before that
request, which can be earlier than the specified clock time; the exact
content is fixed by each observed InRelease digest. There are two archives:
`https://snapshot.debian.org/archive/debian/20261014T000000Z/`
(bookworm and bookworm-updates) and
`https://snapshot.debian.org/archive/debian-security/20261014T000000Z/`
(bookworm-security).

## Enforcement order in GitHub-built candidate

1. The base is pinned by the previously reviewed OCI index digest. The
   Docker context contains only the Worker script, Wasmtime lock, A11 helper
   and lock, and the three A12 helper/source/lock inputs. Never copy keys or
   unrelated repository files.
2. Remove any default APT source. Install the exact two HTTPS deb822 source
   stanzas. Each uses the base image's explicit Debian Signed-By keyring.
   Historical Valid-Until checking is disabled **for these three dated
   archival suites only**, as required for aged Debian snapshots; this
   DOES NOT disable cryptographic signature verification.
3. Reject any additional sources or unexpected source-file bytes BEFORE
   network access. `apt-get update` must verify signed Release metadata;
   A12 next SHA-checks all three exact InRelease files, verifies each with
   `gpgv` against the digest-pinned base's Debian keyring, and ensures files
   remain unchanged while checked.
4. Only after all three signatures and exact InRelease hashes validate,
   download the A11 372-entry Debian package closure, verify each .deb's
   SHA, install without downloading new bytes and confirm every installed
   version matches. Fail closed on any mismatch.
5. The old A10 TypeScript archive SHA-512 and Wasmtime wheel SHA-256 and
   the A9 installed Worker SHA/version inventory remain mandatory.
   Keep RUNTIME-A6's unconditional denial and run its regression tests.
6. The GitHub hosted rootful Docker build is ephemeral. Remove metadata
   helpers and apt source files after successful package installation,
   do not publish or deploy its candidate image.

## Explicit limitations

- The archival Valid-Until exception is scoped but allows using *old* signed
  metadata; this can include historical vulnerabilities. Frozen packages
  MUST NOT be assumed patched or secure merely because they are pinned.
- Debian's Signed-By public keyring is inherited from the *pinned base
  image*. Signature verification and release-content byte identity are
  meaningful but do NOT independently attest key custody or trust-anchor
  provenance; there is no independently witnessed Release timestamp.
- A same-repository lock plus matching SHA-256 cannot independently prove
  package publisher identity, provenance or reproducibility.
- Snapshot availability, archival CDN reliability, upstream publisher
  signature custody, final OCI image signature and independently reproducible
  build remain outside this stage.
- No rootless+gVisor standalone host has been certified. No unknown
  strategies, hostile code, broker orders or Telegram signal publication
  are permitted; Worker launch remains DENY.

## Verdict after all required CI checks pass

CERT_A12_SIGNED_ARCHIVAL_INRELEASE_AND_372_PACKAGE_BYTES_ENFORCED

Remaining: independently witnessed publisher/keyring custody, vulnerability
review of aged packages, reproducible OCI image and isolated gVisor host,
and separate future release approval. Do not overstate these checks as
production or hostile-code security certification.
