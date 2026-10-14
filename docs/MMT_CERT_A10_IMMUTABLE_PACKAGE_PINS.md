# CERT-A10 — immutable base-image and dependency archive byte pins

**Scope:** nonproduction GitHub-hosted fixed four-language Worker fixtures ONLY.
No production/TELMIVO access, unknown uploaded code, broker/Telegram, deploy,
or RUNTIME-A6 dispatch change/authorization.

## Source of candidate hashes

Hashes were collected on 2026-10-14 by a disposable GitHub Actions PR
discovery workflow from public registry responses and downloaded artifact
bytes, and separately frozen into source review:

- Docker Hub python:3.12-slim-bookworm OCI index SHA-256:
  34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258
- npm TypeScript 5.9.3 tarball SHA-512:
  8e5d6f6733c38a72ebf5e52ddc9feded5e8580d130f508ef04f772b33f4a7d00c3e357d0ac2d98e2f290762694a454f86d795bd511e12e9a7cc2d9ba3394e04b
  (npm metadata also reported matching SRI SHA-512).
- PyPI Wasmtime 49.0.0 Linux x86_64 wheel SHA-256:
  94f0288f9e1c33924995a72bb769f4c4e2885002391589dd6992cdaa35d1990a

Lock: deploy/runtime_a2/a10_archive_pins.json. These are observed byte hashes,
NOT independently trusted publisher signatures or reproducibility proofs.

## Enforced nonproduction Dockerfile changes

1. Digest-addressed Python 3.12 slim Bookworm base; platform linux/amd64 only.
2. Download fixed TypeScript URL and check exact SHA-512 and 30 MB upper bound
   BEFORE offline, no-scripts npm installation. The check still runs when
   Python assertions are disabled.
3. Wasmtime installed from PyPI using --require-hashes and pinned wheel SHA256,
   --only-binary=:all:, --no-deps. No source distributions.
4. A8 source lock pins updated Dockerfile bytes; Worker and A1 source digests
   remain unchanged. A10 validates exact recipe and lock linkage.
   The dedicated deploy/runtime_a2/Dockerfile.dockerignore permits only
   the existing Worker script and new a10_wasmtime.lock in the Docker
   build context. A10 refuses any broader allowlist (including secrets).
5. Existing GitHub A2 candidate build, four-language fixed fixture, A8 Docker
   boundary smoke, A9 inside-image version/hash inventory, A6 mandatory denial,
   negative pin/forged-authorization tests are expected to remain green.

## Unresolved security blockers

- Debian APT repositories, exact Node.js/npm .deb archives and transitive
  dependencies remain mutable and not hashed to independently archived
  snapshots.
- Base image index digest locks fetched bytes only. Registry publisher identity,
  signature, build provenance, independent custody and reproducibility are
  still UNVERIFIED.
- Tarball/wheel hashes do not prove upstream publisher identity or absence
  of vulnerabilities.
- The final Worker OCI layers lack independently signed/reproducibly audited
  provenance and there is no independently approved rootless+gVisor host.
- All unknown-code execution, broker and Telegram permissions remain DENIED,
  and RUNTIME-A6 still unconditionally refuses Worker launches.

**Verdict after CI:** CERT_A10_BASE_NPM_WHEEL_HASH_ENFORCED_APT_AND_PROVENANCE_BLOCKED.

**Next:** Debian snapshot and .deb hash custody, publisher signatures,
independent reproducible evidence, dedicated disposable rootless+gVisor host.
