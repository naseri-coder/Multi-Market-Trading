# CERT-A15 — Lean Worker experiment, NOT a release or CVE fix

**Nonproduction only. Current A2 and A6 stay byte-for-byte unchanged.**
No production host, TELMIVO, gVisor host, broker, Telegram, signing or user code.

## Frozen experiment design

Use the existing GitHub-hosted `RUNTIME-A2` candidate image already built
from the immutable CERT-A10/11/12 snapshot, hashes and signed indexes.
Do **not** mutate that image, historic 372-.deb lock, Worker source or A6.

Build one *additional* local ephemeral image with the same immutable
`python:3.12-slim-bookworm` digest but no apt-get/npm/pip operation
in its final stage. A fixed no-network export step copies only:
- the existing A2 Worker, with its previously verified source hash;
- pinned Node.js 18.20.4 executable and its `ldd`-resolved ELF closure;
- TypeScript 5.9.3 library for `require("typescript")`; NOT npm or tsc;
- pinned Debian Node externalized bootstrap modules: cjs-module-lexer,
  undici, acorn and acorn-walk. These remain runtime code with **unresolved original
  Debian advisories**, not independently verified upgrades or fixes;
- Wasmtime 49.0.0 Python package and its exact installed wheel metadata.

The multi-stage build reads **only the local preexisting A2 tag** and uses a
separate Dockerfile and exact one-file build context allowlist. It does not
deploy, push, install or replace any original Docker image. Its final
image runs as uid/gid 65534, with the same Worker entrypoint.

## Required real checks

The same existing A2 CI job must demonstrate:
1. Original candidate built and unchanged after lean build; candidate
   constructed with `--pull=false --network=none`.
2. Identical four fixed harmless Python / JavaScript / TypeScript / Wasmtime
   fixture responses under read-only no-network Docker; no user code.
3. Pinned Node, TypeScript, Wasmtime installed and importable; `npm` and
   `tsc` absent from lean final image.
4. Docker inspect actual uncompressed image sizes for both images, using
   the same runner and source baseline; report size delta even if negative.
5. Syft CycloneDX and Grype against **both** actual images, under the
   **same** Grype advisory DB built timestamp. Record observed Critical,
   High, Medium, Low, Negligible, Unknown counts, match totals and SBOM
   component counts, with original image IDs and report SHA-256.
6. Upload comparison + lean SBOM + lean scan with 3-day retention; no
   registry promotion. All CI suites and Publication safety must be green.

## Security interpretation / blind spots

Copying ELF binaries, shared libraries and Debian Node's externalized
JavaScript bootstraps out of installed packages removes or obscures original
package identity. In particular, **the original node-undici CVEs remain
OPEN** even if raw scanner match counts decrease.

Copying ELF binaries and shared libraries out of an installed Debian
package removes or obscures the original dpkg metadata. Grype or Syft
may therefore *stop recognizing vulnerabilities in code that remains
present in the lean image*. A lower count cannot by itself prove that a
CVE was fixed, removed, mitigated, unreachable or irrelevant.

The copied shared-object files also have no independently verified Debian
package-to-file provenance in the lean OCI image. No independent OCI
publisher signature, SBOM completeness attestation, reproducibility,
scanner coverage, container breakout resistance or rootless+gVisor host
certification exists.

Do not infer security acceptance, claim "all CVEs resolved", hide
CVE matches or relax RUNTIME-A6. The **original CERT-A14 199 Critical/High
findings remain OPEN** until independently adjudicated or demonstrated
absent with file-level mapping and reachability evidence.

**Possible verdicts**:
- Passing functional/scan comparison:
  `CERT_A15_BENIGN_FIXTURES_AND_INVENTORY_COMPARED_RELEASE_DENIED`.
- Any failed test/build/missing artifact:
  `CERT_A15_EXPERIMENT_UNVERIFIED_BLOCKED`.

The next independent step should establish exact ELF-to-Debian package
provenance and attest runtime equivalence across more environments before
even considering replacement of the baseline candidate.
