# CERT-A17 — Frozen security-remediation research (NO MUTATION)

**As of 2026-10-14.** This stage documents official advisories, candidate directions
and fail-closed checks only. No Dockerfile, runtime, 372-deb lock, A12 signed
snapshot, TELMIVO server, trade, publication or RUNTIME-A6 mutation is authorized.

## Baseline evidence

- A16 merged commit: 5567e106f4dc81d441ee8aff1db100df244134d6.
- A16 evidence fingerprint: fe25ab67ef9252f2b4694f4f0ddd12d305958878e9fb42cfa98a0ee5d3198d30.
- 199 Critical/High observations (18 Critical, 181 High), **ALL OPEN**.
- 70 still scanner-matched; 14 disappeared but sampled file bytes retained;
  115 disappeared with actual payload removal NOT PROVEN.
- Exactly 18 original Critical matches are frozen in
  deploy/runtime_a2/a17_remediation_review.json, including all duplicate
  package instances; NO High match has been individually resolved.
- A11 archive closure: 47bd698232b4f624d1aab35c6453e1f01641b1b6ebdd8d4d7dc38a4dd19ae872.
- A12 snapshot: 20261014T000000Z.
- Important: libc6, libc-bin and libsqlite3-0 are NOT among the 372 newly
  downloaded pinned .deb archives. Their runtime contents are linked to
  the pinned base image and A16 sampled bytes. Their exact source archive
  custody/backport mapping still needs independent research.

## Official Debian Bookworm advisory research

| CVE | Pinned installed version | Debian tracker Bookworm | Required route |
| --- | --- | --- | --- |
| CVE-2026-5450 glibc | 2.36-9+deb12u14 | vulnerable | Debian source patch or entire independently pinned base migration and ABI review |
| CVE-2025-7458 sqlite3 | 3.40.1-2+deb12u2 | vulnerable | Verified SQLite security patch plus Python/Wasmtime compatibility |
| CVE-2026-33937 node-handlebars | 3:4.7.7+~4.1.0-1 | vulnerable | Prove build-only removal or verified Debian patch |
| CVE-2026-33228 node-flatted | 3.2.7~ds-1+deb12u1 | vulnerable | Prove runtime absence or verified Debian patch |
| CVE-2026-25547 node-brace-expansion | 2.0.1-2 | vulnerable | Reconcile Debian fork, vulnerable code and backport |
| CVE-2026-13697 node-undici | 5.15.0+dfsg1+~cs20.10.9.3-1+deb12u4 | tracker lists vulnerable | **Resolve upstream 7/8 vs Debian 5.15 applicability conflict** |
| CVE-2026-84961 node-undici | 5.15.0+dfsg1+~cs20.10.9.3-1+deb12u4 | tracker lists vulnerable | **Resolve upstream 7/8 vs Debian 5.15 applicability conflict** |

Primary official sources (not independently signed witness custody):
- https://security-tracker.debian.org/tracker/CVE-2026-5450
- https://security-tracker.debian.org/tracker/CVE-2025-7458
- https://security-tracker.debian.org/tracker/CVE-2026-33937
- https://security-tracker.debian.org/tracker/CVE-2026-33228
- https://security-tracker.debian.org/tracker/CVE-2026-25547
- https://security-tracker.debian.org/tracker/CVE-2026-13697
- https://security-tracker.debian.org/tracker/CVE-2026-84961

**Important nuance:** source trackers reporting undici 5.15 vulnerable
while some upstream advisory descriptions refer only to 7.x/8.x does NOT
prove it safe, and does NOT prove exploit reachability. Reconcile exact
Debian source code, downstream patch series, version ancestry and the
relevant runtime call path before considering any disposition.

Other A14 Critical rows, including GHSA npm/Babel/tar/webpack and Debian
node-ip/node-postcss, remain OPEN and precisely listed in the 18-row
registry. The six Grype proposed npm versions are NOT independently
verified safe or compatible Debian replacement packages.

## Three possible future remediation tracks — NOT EXECUTED

**R1 (build-only removal):** Prove which handlebars, flatted, brace-expansion,
PostCSS, IP, Babel, tar or webpack paths are build-only using actual file
ownership and SHA-256, not dpkg metadata disappearance. Prove absence of
risky code and preserve four-language benign Worker functionality.
Externalized undici remains runtime code in A15; it cannot be silently
counted as removed.

**R2 (base modernization):** Evaluate a separately signed/digest-pinned
Debian base and complete dependency closure. Never mix Debian suites or
replace glibc/SQLite ad hoc. Compare ABI compatibility, Python/Node/
TypeScript/Wasmtime, benign fixture outputs, full file ownership and
same-database vulnerability inventory, including newly introduced CVEs.

**R3 (upstream patch):** Before changing undici or npm modules, authenticate
upstream advisories and exact patch commit, reconcile Bookworm source
branches, dependencies and exports, then review software licenses and
construct a *separately authorized* nonproduction candidate.

## Mandatory acceptance evidence before any later candidate/release

1. Exact installed Debian-source-to-file ownership and SHA-256.
2. Official advisory applicability, version range and backport diff.
3. Verified vulnerability reachability or independently proven code absence.
4. Candidate pinned content digests, software origin and license review.
5. Original four-language harmless equivalence and honest SBOM coverage.
6. Independent rootless Docker+gVisor isolation and publisher custody,
   plus explicit human approval before executing unknown code.

None of these gates is waived by fewer Grype matches. No production
service, signing keys, broker or Telegram actions, no user strategies.

## Verdict

CERT_A17_REMEDIATION_RESEARCH_FROZEN_18_CRITICAL_AND_181_HIGH_OPEN_NO_MUTATION

All 199 findings remain review-open. RUNTIME-A6 denial remains mandatory.
