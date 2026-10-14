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

## A19-R2 — Exact Bookworm source-tree and Debian patch-series investigation

Source tree confirmed for Debian node-undici `5.15.0+dfsg1+~cs20.10.9.3-1+deb12u4`:
https://sources.debian.org/src/node-undici/5.15.0%2Bdfsg1%2B~cs20.10.9.3-1%2Bdeb12u4/

Concrete paths from published Debian source inventory:
- `lib/balanced-pool.js` exists in Bookworm 5.15 (5,258 bytes per Debian source index).
- `lib/interceptor/` in that version indexes `redirectInterceptor.js` only; the newer upstream cache interceptor implicated by CVE-2026-13697 is not listed in that exact directory. This is DIRECTORY-LEVEL negative evidence ONLY: other paths, downstream integration or equivalent functionality not yet ruled out.
- `debian/patches/` lists named patches for CVE-2023-23936, CVE-2023-24807, CVE-2023-45143 plus build/distribution adjustments, but no patch named for CVE-2026-13697 or CVE-2026-84961. Patch *names* are insufficient to assert security applicability or nonapplicability; contents and downstream changes still require byte-level checking.

Reference directories:
- https://sources.debian.org/src/node-undici/5.15.0%2Bdfsg1%2B~cs20.10.9.3-1%2Bdeb12u4/lib/
- https://sources.debian.org/src/node-undici/5.15.0%2Bdfsg1%2B~cs20.10.9.3-1%2Bdeb12u4/lib/interceptor/
- https://sources.debian.org/src/node-undici/5.15.0%2Bdfsg1%2B~cs20.10.9.3-1%2Bdeb12u4/debian/patches/

Official tracker details:
- CVE-2026-13697 is a shared-cache private Cache-Control handling issue described for upstream 7.0.0–<7.29.0 and 8.0.0–<8.9.0; Debian Bookworm 5.15 is flagged vulnerable/postponed. Do not treat this contradiction as automatically resolved.
- CVE-2026-84961 is a BalancedPool JSON deep-clone dropping callback-valued TLS connector options, described for upstream 7.24.1–7.29.1 and 8.0.0–8.10.2; Debian Bookworm 5.15 is flagged vulnerable/postponed.
- The exact upstream function, imported call path and Debian 5.15 patched-source bytes have NOT yet been independently compared. No exploitability or false-positive verdict.

SQLite clarification: Debian tracker points to SQLite check-in `12ad822d9b827777`, but the visible upstream check-in describes SELECT DISTINCT / ORDER BY handling and is not by itself a demonstrated corrective patch for the `sqlite3KeyInfoFromExprList` integer overflow. Treat proposed patch identity as UNVERIFIED; do not backport blindly.
Official primary source: https://sqlite.org/src/info/12ad822d9b827777

### Mandatory rejection tests for later candidate
- Reject absent exact source archive hashes and unknown provenance.
- Reject different-suite `glibc` / `sqlite3` binary grafts.
- Reject declaring an A14/A16 finding fixed from Grype disappearance or missing dpkg metadata.
- Reject any change to `naseri_markets/runtime_a6_dispatch_fence.py` or RUNTIME-A6 DENY.
- Reject declaring undici 5.15 unaffected merely because an upstream advisory starts at 7.x without code-level comparison.
- Reject any production, unknown Worker code, broker/Telegram or TELMIVO action.

A19-R2 disposition: `SOURCE_DIRECTORY_EVIDENCE_COLLECTED__EXACT_CODE_AND_PATCH_SHA_UNVERIFIED__CANDIDATE_BLOCKED`.

## CERT-A19-R3 — upstream v5.15.0 source-level negative evidence (2026-10-14)

Authenticated via GitHub repository file fetch at the immutable upstream tag `nodejs/undici@v5.15.0`:
- `lib/balanced-pool.js` Git blob SHA-1 `10bc6a47bafd5cdc93c058e8d75e96e7d0fe1f07`.
- In that file the BalancedPool constructor sets `this[kOptions] = opts`; `addUpstream()` passes `Object.assign({}, this[kOptions])` to the Pool factory. **No** `JSON.parse(JSON.stringify(...))` clone exists in this fetched upstream file, so the upstream implementation inspected does not exhibit the *specified* function-dropping mechanism of GHSA-w293-vg96-wgc3. This is exact source-level negative evidence for upstream v5.15.0, not a Debian binary verdict.
- `lib/interceptor/cache.js` at `v5.15.0`: GitHub fetch returns 404 (absent at that exact path); `lib/interceptor/redirectInterceptor.js` exists with Git blob SHA-1 `7cc035e096c84ee97560f5c27c2a35a7714f8364`. Earlier published Debian 5.15 directory index likewise listed only redirectInterceptor.js. Thus the exact modern cache-interceptor path named by GHSA-4cwx-7wf7-3272 is not proven present in the legacy source. Missing path does **not** exclude alternate cache functionality or downstream patches.

GitHub canonical sources:
- https://github.com/nodejs/undici/blob/v5.15.0/lib/balanced-pool.js
- https://github.com/nodejs/undici/tree/v5.15.0/lib/interceptor
- https://github.com/nodejs/undici/security/advisories/GHSA-w293-vg96-wgc3
- https://github.com/nodejs/undici/security/advisories/GHSA-4cwx-7wf7-3272

Advisory-specific preliminary applicability:
| Advisory | Mechanism in official upstream advisory | Upstream v5.15.0 examined | Exact Debian Bookworm installed source/binary | Decision |
|---|---|---|---|---|
| CVE-2026-84961 | BalancedPool JSON clone discards function-valued TLS callbacks | Specific mechanism ABSENT in inspected v5.15.0 file | not byte-compared against actual Debian 5.15.0+deb12u4 patch set | UPSTREAM_MECHANISM_NOT_PRESENT; DEBIAN_UNVERIFIED |
| CVE-2026-13697 | new cache interceptor uses unsafe private Cache-Control parser | named modern cache.js path ABSENT in inspected v5.15.0 tag | not byte-compared or all alternate imports audited | PATH_ABSENCE_PROVEN_UPSTREAM; DEBIAN_UNVERIFIED |

The Debian Security Tracker still labels Bookworm vulnerable/postponed; do not override its status on this evidence alone. The file IDs above are Git *blob SHA-1*, NOT SHA-256. Do not misrepresent them as SHA-256 custody of Debian installed JS files.

**Next required verification:** fetch the exact Debian Bookworm patched source or source archive with signed .dsc + SHA-256; inspect exact `lib/balanced-pool.js`, `lib/interceptor/`, Debian quilt patch series, and Worker-resident `/usr/share/nodejs/undici` copied in A15/A18. Establish SHA-256 pairing before any Debian-specific NOT_AFFECTED or scanner false-positive certification.

Status: `CERT_A19_R3_UPSTREAM_MECHANISM_NEGATIVE_EVIDENCE_DEBIAN_BINARY_UNVERIFIED_NO_CANDIDATE`. Maintain 199/199 original findings review-open, RUNTIME-A6 DENY, no CI/image/production mutations.
