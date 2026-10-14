# CERT-A19 — Independent security patch research (nonproduction; BLOCKED candidate)

Date: 2026-10-14. Starting main commit: `dccfe791f465040cc87d210c0ca33fad44f654ae`.
GitHub compare against main returned IDENTICAL (ahead 0 / behind 0). PR #274 merged as that commit.
This is a research record, **not a patch**, not a security certification and not authorization for unknown user code.

## Authoritative baseline
- A17 ledger: `deploy/runtime_a2/a17_remediation_review.json` (18 Critical observations, 181 High; 199 OPEN).
- A16: 70 original package/advisory/version matches still scanner detected, 14 no longer detected but sampled bytes retained, 115 removal unproven.
- A18: 109 exact original Debian build-only owned paths absent for five packages; same actual runtime payload as A15; NO new CVE fixes certified.
- A11 historical 372 .deb SHA lock, A12 snapshot and A2/A15/A18 remain IMMUTABLE.
- glibc and SQLite came from the base image, not from the 372 newly downloaded archives. Independent source-archive custody and ABI proof absent.

## Official source audit — version-specific observations
| Source/advisory | Observed installed | Debian bookworm tracker | Other Debian source version/status | A19 decision |
|---|---|---|---|---|
| node-undici / CVE-2026-13697 | 5.15.0+dfsg1+~cs20.10.9.3-1+deb12u4 | vulnerable, postponed | unstable fixed from 8.9.0+dfsg+~cs3.2.0-1 | UNVERIFIED source-code applicability; DO NOT upgrade across suites |
| node-undici / CVE-2026-84961 | same | vulnerable, postponed | unstable fixed from 8.10.2+dfsg+~cs3.2.2-1 | UNVERIFIED source-code applicability; DO NOT upgrade across suites |
| glibc / CVE-2026-5450 | 2.36-9+deb12u14 | vulnerable; no-dsa | trixie fixed at 2.41-12+deb13u4 | BLOCKED for patch candidate; no compatible pinned Bookworm patch custody |
| sqlite3 / CVE-2025-7458 | 3.40.1-2+deb12u2 | vulnerable; no-dsa | trixie fixed at 3.46.1-7+deb13u2 | BLOCKED for patch candidate; no compatible pinned Bookworm patch custody |

Official references:
- https://security-tracker.debian.org/tracker/CVE-2026-13697
- https://security-tracker.debian.org/tracker/CVE-2026-84961
- https://security-tracker.debian.org/tracker/CVE-2026-5450
- https://security-tracker.debian.org/tracker/CVE-2025-7458
- https://security-tracker.debian.org/tracker/source-package/node-undici
- https://security-tracker.debian.org/tracker/source-package/sqlite3

**Undici important conflict:** Advisory descriptions describe impacted upstream undici 7.x/8.x code paths, whereas Debian currently marks its packaged Bookworm 5.15.0 source as vulnerable. Neither the upstream interval nor Debian package-level classification independently establishes affected bytes or exploitability of the exact runtime 5.15 copy. Authenticate Bookworm 5.15 source tarball + Debian patch series; map exact changed functions, commits, preconditions, Node externalized bootstrap path and SHA-256 before any decision. No false-positive or fixed conclusion is permitted.

**glibc precondition:** CVE-2026-5450 involves a scanf-family %mc width >1024 heap overflow. An unaffected safe fixture does not prove absence of attacker-controlled triggering calls. The upstream change 839898777226a3ed88c0859f25ffe712519b4ead is a research lead, NOT an approved Bookworm backport.

**SQLite precondition:** CVE-2025-7458 requires ability to execute crafted SQL with large ORDER BY expression lists. Verify SQL boundaries and actual compiled feature/ABI before any independent patch.

## Frozen remediation evaluation specification (NOT implementation approval)
1. Obtain exact signed Debian Bookworm source archive, .dsc, patch series, build flags, SBOM ownership and file-level SHA; verify provenance and corresponding runtime sample bytes.
2. Reconcile exact advisory patch function against Bookworm's affected code, including backported patches and reachability. Require independent review and a precise pass/fail vulnerability claim.
3. For base libc6/libc-bin/libsqlite3-0 do NOT splice across Debian suites; any successor must be a separately pinned compatible whole-base experiment, with library closure, Python, Node, TypeScript and Wasmtime ABI checks.
4. Preserve same harmless four-language fixture outputs and negative tests; reject any missing checks, package drift, unknown digest or regression.
5. If authorized later: compare image SBOMs and scans with the SAME pinned Grype DB; report newly introduced advisories and missing classifications separately. Scanner deltas do not certify fixes.
6. Verify runtime_a6_dispatch_fence.py byte-identical, A6_INDEPENDENT_HOST_CERTIFICATION_REQUIRED still DENY; no TELMIVO, trading, Telegram, production, untrusted code or actual orders.
7. Keep this branch documentation-only until package fixes have authenticated SHA-256, license and compatibility evidence. No Docker build or CI quota consumption necessary for a docs-only research record.

## Explicit status
- Source/patch custody: INCOMPLETE
- Exact Debian undici 5.15 source-level patch applicability: UNVERIFIED
- Compatible hashed security remediation packages: NONE APPROVED
- Remediation candidate: BLOCKED — NOT CREATED
- Four-language test on changed image: NOT RUN — NO IMAGE CREATED
- SBOM / Grype on changed image: NOT RUN — NO IMAGE CREATED
- Original Critical/High findings certified fixed: 0
- Original 199 findings requiring review: 199
- Production authorization: DENIED
- Rootless + gVisor independent host certification: NOT PROVIDED
- Merge authorization: NOT MET; draft PR must stay open.

Verdict: `CERT_A19_RESEARCH_PARTIAL_PATCH_CANDIDATE_BLOCKED_NO_RUNTIME_MUTATION`
