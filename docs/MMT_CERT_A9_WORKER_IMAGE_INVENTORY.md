# CERT-A9 — CI-built Worker image contents and installed dependency inventory

**Verdict before CI: CERT_A9_SOURCE_PREPARED_CI_NOT_YET_VERIFIED.**

This stage closes a concrete blind spot left by RUNTIME-A8 source-only SHA locks
and CERT-A8 real Docker boundary smoke: the *actual installed container* was
not compared to the committed Worker source and expected Python/TS/Wasmtime
versions. The existing GitHub-hosted RUNTIME-A2 workflow already builds the
ephemeral candidate image. This stage reuses it and changes no Dockerfile.

## Measured contract

On the existing GitHub-hosted runner, AFTER the fixed four-language Docker
roundtrip and CERT-A8 harmless smoke:

1. Verify the existing committed RUNTIME-A8 source lock across all three
   fixed files; do not replace or regenerate the lock to obtain a pass.
2. Inspect the exact local image ID of the hard-coded candidate tag;
   require a SHA256-formatted ID. Do not pull, publish, tag or deploy.
3. Use a bounded, harmless, literal Python probe in that local image.
   It reads SHA256 of the installed /opt/mmt/bin/runtime-a1-worker file,
   the Python 3.12 patch version, Node.js, npm, tsc and the installed Python
   Wasmtime distribution metadata. It does NOT run any user code.
4. Compare the installed worker bytes to the previously verified source lock
   bytes. Fail if Python leaves the 3.12 line, TypeScript !=5.9.3,
   Wasmtime !=49.0.0, Node.js major <18, or any version is malformed.
   Node.js/npm precise versions are **observed, not pinned**.
5. Verify the same local image ID is present after the probe and bounded
   container cleanup. Fail closed on image replacement, absent container
   cleanup confirmation, malformed or forged stdout, timeout and other
   process errors.
6. Print a bounded result with actual installed versions, image ID, worker
   SHA, an evidence fingerprint, and explicit **false** supply-chain trust
   and trading permission fields.

The test job contains mocked negative scenarios for missing opt-in,
production/self-hosted/root invocation, file-version drift, tampered worker,
unexpected payload fields, changed image, orphaned container and failure.

## What is NOT proved

- The Dockerfile base image remains a mutable tag:
  python:3.12-slim-bookworm, not an externally authenticated immutable digest.
- APT-provided Node.js/npm packages are not locked by repository snapshot,
  .deb hashes or independent mirrors.
- TypeScript @5.9.3 only pins a package version, not the npm tarball integrity
  / upstream publisher identity. Wasmtime ==49.0.0 likewise has no pip
  --require-hashes wheel check and transitive provenance attestation.
- Local Docker image ID is a content identifier, **not** a registry OCI
  manifest digest, independently verified supplier signature or SBOM proof.
- A SHA lock checked out with its source from the same Git repository cannot
  independently authenticate that repository's supply chain.
- A GitHub-hosted *rootful* Docker runner does not attest rootless+gVisor
  host isolation or justify uploaded code execution.
- No exchange/broker, Telegram, trading strategy, account, TELMIVO,
  server, database, registry, network fetch inside guest, package install,
  production deployment, order, or RUNTIME-A6 unlock is involved.

**If all CI checks pass:** CERT_A9_INSTALLED_IMAGE_INVENTORY_PASS_EXTERNAL_PROVENANCE_BLOCKED.

**Remaining release blockers:** independently vetted immutable base image,
APT artifact snapshot, npm tarball integrity, Python wheel checksums,
signed/reproducible OCI build and independent custody, disposable
rootless+gVisor host containment, and explicit future approval.
