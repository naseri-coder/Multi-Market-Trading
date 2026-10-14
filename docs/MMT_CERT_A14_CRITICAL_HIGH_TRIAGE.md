# CERT-A14 — read-only Critical/High Worker vulnerability triage

**Status: DETECTED / OPEN_REVIEW_REQUIRED / RELEASE_DENIED.**
This is a reproducible analysis of the actual CERT-A13 Syft+Grype
GitHub-hosted, benign-fixture Worker image, NOT a package remediation,
security certification or authority to execute unknown code.

## Evidence provenance

- Source workflow: https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38583507207
- Actual SBOM + Grype + image ID artifact:
  https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38583507207/artifacts/11903538908
- Candidate image ID:
  sha256:fe5ed0ffe7b6ab44346512d3a215cbb2ce1e788f28f327f152948e4e0fb79c96
- Grype advisory DB built: 2026-10-14T06:30:34+00:00
- Actual Grype JSON SHA-256:
  378db212bc36876a6d8156ee7b91f45ba5b1c018d5dfa7a058ae26741c725392
- Actual Syft CycloneDX JSON SHA-256:
  4014ccbcc61bd93bff2c0426998f4188b4bd68b928c28b6656a4daa7270826fa
- Source report is time-limited (GitHub artifact retention: three days).
  Regenerate from the same controlled CI workflow for later re-evaluation.

## Evidence-derived counts (scanner matches, NOT unique exploit paths)

| Observation | Count |
| --- | ---: |
| All severities | 584 |
| Critical | 18 |
| High | 181 |
| Critical + High | 199 |
| Distinct Critical+High advisory IDs | 143 |
| Distinct Critical advisory IDs | 17 |
| Critical+High deb package matches | 144 |
| Critical+High npm package matches | 55 |
| Critical+High scan fix state: fixed | 52 |
| Critical+High scan fix state: wont-fix | 97 |
| Critical+High scan fix state: not-fixed | 50 |

The 29,155 SBOM components reported in CERT-A13 include 27,069 file
components. They must NOT be represented as 29,155 individually vulnerable
third-party packages. The 199 Critical/High observations cover 83 distinct
package names. Advisory IDs and package occurrences may repeat; e.g. glibc
CVE-2026-5450 appears separately for libc-bin and libc6.

**Every record remains OPEN_REVIEW_REQUIRED.** A Grype fix state of
wont-fix is NOT evidence that a CVE is false-positive, fixed, mitigated or
irrelevant to this Debian stable build. A semver npm fix version is NOT
automatically a valid Debian backport fix or a safely deployable replacement.
Reachability, exploitation prerequisites, and package runtime use have NOT
been independently verified.

## Critical list: all 18 observations

| Advisory | Package (ecosystem) | Installed version | Grype fix state / candidate |
| --- | --- | --- | --- |
| CVE-2026-106445 | handlebars (deb) | 3:4.7.7+~4.1.0-1 | not-fixed |
| CVE-2026-106446 | handlebars (deb) | 3:4.7.7+~4.1.0-1 | not-fixed |
| CVE-2026-33937 | handlebars (deb) | 3:4.7.7+~4.1.0-1 | wont-fix |
| CVE-2026-5450 | libc-bin (deb) | 2.36-9+deb12u14 | wont-fix |
| CVE-2026-5450 | libc6 (deb) | 2.36-9+deb12u14 | wont-fix |
| CVE-2025-7458 | libsqlite3-0 (deb) | 3.40.1-2+deb12u2 | wont-fix |
| CVE-2026-25547 | node-brace-expansion (deb) | 2.0.1-2 | wont-fix |
| CVE-2026-33228 | node-flatted (deb) | 3.2.7~ds-1+deb12u1 | wont-fix |
| CVE-2023-42282 | node-ip (deb) | 2.0.0+~1.1.0-1 | wont-fix |
| CVE-2026-45623 | node-postcss (deb) | 8.4.20+~cs8.0.23-1+deb12u1 | wont-fix |
| CVE-2026-13697 | node-undici (deb) | 5.15.0+dfsg1+~cs20.10.9.3-1+deb12u4 | wont-fix |
| CVE-2026-84961 | node-undici (deb) | 5.15.0+dfsg1+~cs20.10.9.3-1+deb12u4 | wont-fix |
| GHSA-67hx-6x53-jw92 | @babel/traverse (npm) | 7.20.13 | fixed: 7.23.2 |
| GHSA-2w6w-674q-4c4q | handlebars (npm) | 4.7.7 | fixed: 4.7.9 |
| GHSA-8r5x-fm3f-whwj | handlebars (npm) | 4.7.7 | fixed: 4.7.10 |
| GHSA-p8wg-vrv2-v86f | handlebars (npm) | 4.7.7 | fixed: 4.7.10 |
| GHSA-23hp-3jrh-7fpw | tar (npm) | 6.1.13 | fixed: 7.5.19 |
| GHSA-hc6q-2mpp-qw7j | webpack (npm) | 5.75.0 | fixed: 5.76.0 |

All 18 Critical matches and the other 181 High matches were extracted
individually with package, version, fix state, candidate fix versions,
PURL, advisory source and first observed image location, and are available
as a CSV/JSON triage bundle for operator review. No record is marked
false-positive, remediated, authorized, or excluded.

## Independent official Debian tracker spot checks (2026-10-14)

These spot checks are **not** a verification of all 199 findings.
They demonstrate why a Grype "wont-fix" label cannot be treated as
permission to discard a finding:

- CVE-2026-33937, Debian node-handlebars 3:4.7.7+~4.1.0-1:
  the Debian security tracker lists Bookworm as **vulnerable**.
  The described JavaScript injection requires untrusted, crafted
  Handlebars AST input to the compile path; Worker input reachability
  is NOT verified.
  https://security-tracker.debian.org/tracker/CVE-2026-33937
- CVE-2026-5450, Debian glibc 2.36-9+deb12u14:
  the tracker lists Bookworm as **vulnerable**. The described memory
  corruption requires the specific scanf %mc and width usage;
  runtime exploitability has NOT been demonstrated.
  https://security-tracker.debian.org/tracker/CVE-2026-5450
- CVE-2025-7458, Debian SQLite 3.40.1-2+deb12u2:
  the tracker lists Bookworm as **vulnerable**. The issue has a crafted
  SQL/expression precondition. Whether such input reaches SQLite in
  Worker is NOT established.
  https://security-tracker.debian.org/tracker/CVE-2025-7458

"no-dsa" / lower Debian maintenance urgency does not mean a CVE is
fixed, absent, or safe to expose in the candidate runtime image.
No upstream signature/key custody or production trust was claimed by
these source-based observations.

## P0 / P1 remediation research decision

**P0 — release remains blocked.** Preserve the unconditional
RUNTIME-A6_INDEPENDENT_HOST_CERTIFICATION_REQUIRED deny; do not execute
untrusted strategies or authorize broker/Telegram/production operations.

**P0 — Debian stable advisory review.** Investigate the exact pinned
Bookworm version and security-tracker state for libc6/libc-bin,
libsqlite3-0, handlebars, node-undici, node-ip, node-flatted,
node-postcss and node-brace-expansion. Check for backported patches,
affecting versions, fix/mitigation status, exploit prerequisites and
relevant execution paths. No offline scanner status substitutes for this.

**P0 — reduce unused runtime dependencies by design, not by CVE hiding.**
Critical npm and Debian Node packages occur in /usr/share/nodejs under
the installed Debian npm dependency closure. The candidate may be shipping
build-only npm tooling in the runtime image. Propose a separate, strictly
pinned multi-stage build experiment that assembles the TypeScript runtime
while excluding unneeded build-time tools; first prove actual ABI and
four-language fixture equivalence and enumerate every dependency removed.
This is NOT yet an authorized Dockerfile mutation.

**P1 — evaluate npm remediation targets.** Grype lists fixed upstream
npm versions for handlebars, webpack, tar, Babel traversal, and other
High findings. The installed npm package may be Debian packaged, so
do not blindly install upstream npm versions or modify the historical
372-deb / A12 InRelease locks. Any candidate must undergo a separately
authorized architecture, license and security review.

**P1 — exploitability and false-positive adjudication.** The presence
of /usr/share/nodejs/package.json or a Debian dpkg status file proves
inventory, not runtime code reachability. Each disposition requires dated
official Debian/GHSA evidence, exact package version and a causal input /
reachability argument. If evidence is insufficient, leave OPEN.

## Available non-mutating reproduction

scripts/ci_cert_a14_grype_triage.py reads the exact A13 raw Grype JSON
and A13 evidence summary, verifies the Grype SHA-256 and all severity
counts, rejects forged security grants or duplicate JSON keys, then
writes each Critical/High match as a review-only JSON record.
No network, Docker, scanner installation, package changes, privilege
elevation, database edits or sending of signals is performed.

A CERT-A14 mock-only CI regression validates the parser and retains
RUNTIME-A6 denial. It does NOT independently adjudicate Debian CVEs
or replace a live vulnerability scan.

## Blocked and excluded assertions

- Independent publisher/keyring custody: NOT VERIFIED
- Reproducible final OCI image and signature: NOT VERIFIED
- Rootless Docker + gVisor external-host certification: NOT VERIFIED
- Security disposition of any Critical/High match: OPEN
- Permission to execute unknown Worker input: DENIED
- Production / broker / Telegram execution: DENIED

**Verdict:** CERT_A14_199_CRITICAL_HIGH_MATCHES_TRIAGED_ALL_DISPOSITIONS_OPEN.
