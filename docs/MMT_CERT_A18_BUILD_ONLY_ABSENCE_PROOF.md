# CERT-A18-R1 — fixed Debian-owned code path absence proof

**Nonproduction, research-only, NO security fix acceptance.**
This stage does not install patches or change any existing A2/A15 Worker
source, A11 package hashes, A12 signed Debian snapshot or A6 launch denial.

## Candidate scope

A separate fixed A18 Dockerfile consumes the previously built local A15
image. Its guard checks that five Debian Node build-tool import roots are
missing (handlebars, flatted, brace-expansion, ip, postcss). The final A18
image has the **same executable payload as A15**, with metadata-only
differences; it cannot be described as a newly patched or safer version.

GitHub-hosted ephemeral CI also obtains the original installed dpkg
package-owned file lists from the stopped pinned A2 container (no guest
process started), lists original and A18 filesystem tar entries from
stopped containers, and matches exact original-owned JS/JSON paths.
It requires at least one actual code file per package originally present,
checks every listed code path is absent from A18, verifies the original
Debian package versions against the unchanged 372-archive A11 SHA lock,
and requires the essential Node/undici/TypeScript/Worker files to remain.

## Findings still open

- All **18 Critical and 181 High** A14 findings remain review-open.
- A dropped path is **not** proof every copy of vulnerable code was removed
  from the final image. Renamed, vendored, bundled or embedded copies may
  still exist; independent source-code and full-content provenance is needed.
- The externalized Debian `undici` code, the base glibc, SQLite, Node ELF
  libraries and original Critical advisories remain unpatched by A18.
- Syft or Grype may fail to detect vulnerabilities if dpkg identity has
  been stripped by the A15 image. Numeric findings are observations only.
- The source A2 code paths are tied to locally observed Debian dpkg data
  and the pinned A11 package lock, **not** independently witnessed
  upstream source-signing/key custody or proof of no other code copies.

## Concrete gates for this PR

- Build actual A18 candidate from locally built A15; no pull, no network,
  no registry push, no TELMIVO or production mutation.
- Run the existing harmless fixed four-language Worker roundtrips in A18.
- Require target modules absent, and Node/undici/TypeScript present.
- Prove the A2 baseline dpkg-owned code paths with stopped-container
  filesystem exports, reject any mismatch, missing manifest or changed
  package hash lock; never execute the stopped containers.
- Compare A15 and A18 actual CycloneDX/Grype scans under the same
  advisory DB build timestamp. Findings must not be suppressed.
- Keep CI artifacts for three days and preserve A6 unconditional DENY.

Expected review status:
`CERT_A18_R1_OWNED_BUILD_ONLY_PATHS_ABSENT__199_FINDINGS_OPEN__RELEASE_DENIED`.

**Do not promote the A18 image or infer a CVE was fixed.** A subsequent
stage requires independent upstream patches with full signed supply-chain
and compatibility evidence for glibc, SQLite, undici and remaining P0s.
