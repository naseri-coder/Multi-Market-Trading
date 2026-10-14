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

## CERT-A19-R4 — Debian source provenance and explicit byte-custody blocker

Observed official Debian Bookworm source package metadata:
- https://packages.debian.org/bookworm/source/node-undici
- Exact Debian source version: `5.15.0+dfsg1+~cs20.10.9.3-1+deb12u4`.
- Debian source components listed: `.dsc`, `.orig.tar.xz`, five component `.orig-*.tar.xz` tarballs, and `.debian.tar.xz`. Package webpage lists **MD5**, which does NOT satisfy CERT-A19 SHA-256 artifact custody.
- Debian FTP Masters signed acceptance announcement exists: https://lists.debian.org/debian-changes/2024/06/msg00051.html . Message existence does not mean its signature was cryptographically verified in this execution.
- Debian exact source directory listing `lib/interceptor/` contains `redirectInterceptor.js` as its sole file: https://sources.debian.org/src/node-undici/5.15.0%2Bdfsg1%2B~cs20.10.9.3-1%2Bdeb12u4/lib/interceptor/
- Debian exact source index identifies `lib/balanced-pool.js` as 5,258 bytes: https://sources.debian.org/src/node-undici/5.15.0%2Bdfsg1%2B~cs20.10.9.3-1%2Bdeb12u4/lib/

### Evidence boundary (fail closed)
A direct source-file fetch of Debian `lib/balanced-pool.js` was not successful (web content-type rejection, container environment DNS unavailable). This execution therefore DID NOT obtain:
1. Independently cryptographically verified signed Debian `.dsc` and its SHA-256 hashes for all source components;
2. Debian-patched file bytes of `lib/balanced-pool.js`, its SHA-256 or quilt-applied patch equivalence;
3. Stopped A18 Worker runtime file bytes / SHA-256 from `/usr/share/nodejs/undici`;
4. Proven equality between Debian source file and actual A18 runtime payload.

For an authorized GitHub-hosted ephemeral, harmless **audit-only** successor, fetch the source components declared in the signed `.dsc`, verify Debian signature against a pinned trusted Debian key, SHA-256 check each component, apply Debian patches in clean directory, calculate SHA-256 for the two relevant files and inspect exact BalancedPool option-transfer call. Export stopped A18 image (never start unknown strategies), calculate SHA-256 of matching runtime JS files, and compare hashes. Explicitly reject absent file, mismatch, unknown package origin or missing trusted source signature. Include documented negative cases and protect CI quota with a single targeted run.

No CI triggered during R4; no source or image patch; no claim of new fixed CVEs. The original 199 Critical/High observations remain review-open, A6 DENY preserved, and CERT-A19 PR stays DRAFT.

Verdict: `CERT_A19_R4_OFFICIAL_SOURCE_PACKAGE_LOCATED_BYTE_CUSTODY_BLOCKED_NO_PATCH`.

## CERT-A19-R5 — Targeted GitHub-hosted Debian undici custody gate

New files: scripts/ci_cert_a19_undici_byte_custody.py; tests/unit/test_cert_a19_undici_byte_custody.py; .github/workflows/cert-a19-undici-byte-custody.yml.
Nine offline targeted tests PASSED locally (no Docker, Node or network execution). Hosted job result must be obtained independently before claiming hosted PASS.

Pinned A11 372-deb closure SHA256: 47bd698232b4f624d1aab35c6453e1f01641b1b6ebdd8d4d7dc38a4dd19ae872.
Exact Bookworm undici Debian .deb version 5.15.0+dfsg1+~cs20.10.9.3-1+deb12u4, architecture all, A11 archive SHA256: 78ec8918d63e365bbdec6edd35bebec9e20cc931f084f24e8673badf191d100c.
Official FTP Masters 2024-06-16 source acceptance https://lists.debian.org/debian-changes/2024/06/msg00051.html records .dsc SHA256: 6befcb981dea58f2fdb9bc0d78624d829090105ab955d48e617a02ead37fd44c.
Small targeted job downloads exactly the pinned .deb and .dsc from deb.debian.org, validates hashes and Debian metadata, extracts rather than installs the binary .deb, and computes exact BalancedPool file SHA with negative checks. It validates A11 closure and preserved A6 DENY.

IMPORTANT LIMIT: No A18 image is constructed or started in this job. The optional --a18-root requires independent stopped-image materialization; until provided, worker_byte_parity is UNVERIFIED_A18_STOPPED_IMAGE_NOT_PROVIDED. NO comparison of actual Worker bytes is asserted.
Likewise, the signed .dsc is SHA-anchored but its OpenPGP signature is NOT independently verified; full source component tarballs, Debian quilt patch series, and source-to-binary reproduction remain UNVERIFIED. This does NOT authorize a CVE false-positive or remediation claim.

The job is single-purpose, 8-minute timeout, no full A2/A18 build, no Syft/Grype rerun, no Node/Worker/user payload execution, no production/TELMIVO/orders/Telegram, read-only GitHub permissions, 2-day evidence retention. Critical/High review state: 199 OPEN.
Verdict: CERT_A19_R5_PINNED_DEBIAN_BYTE_AUDIT_PREPARED_A18_RUNTIME_PARITY_UNVERIFIED_NO_CVE_CLOSURE.

## CERT-A19-R8 — Verified developer-signed Debian source chain, no Worker-byte claim

**Source evidence run:** https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38619436727 ; completed SUCCESS 2026-10-14; fixed isolated, non-PR `cert-a19-byte-audit-run` branch; source verification code and workflow added **only on that disposable branch**, not in this PR.
**Expiring artifact:** `cert-a19-r8-debian-signed-source-sha-chain`, GitHub Actions artifact ID `11922005338`, retention 2 days. Download evidence before expiry.

- Exact Debian `.dsc` byte SHA-256 verified: `6befcb981dea58f2fdb9bc0d78624d829090105ab955d48e617a02ead37fd44c`.
- OpenPGP clear-signed `.dsc` verified with `gpgv` against Debian developer/maintainer keyring **installed from Ubuntu-signed APT on a fresh GitHub-hosted Ubuntu 24.04 runner**. Verified signer fingerprint: `03c4e7abb880f524306e48156611c05edd39f374`. This is stronger source-signature evidence, but the keyring's independent offline custody was **not** established.
- All **7 exact source components** enumerated in signed `Checksums-Sha256` were downloaded and each checked for exact signed size and SHA-256 (including 5 orig component tarballs + 1 orig main tarball + 1 Debian patch tarball). Source archive hash chain: PASS.
- `dpkg-source -x` applied Debian packaging patches without executing user/Node/Worker code. Patched `lib/balanced-pool.js` SHA-256 was `06e20567449a6131d5ae6f049b5d85f17c3139f2fed6a2783f656429180ff865`.
- This exact SHA-256 **equals** the independently inspected Bookworm Debian `.deb` `/usr/share/nodejs/undici/lib/balanced-pool.js` hash from hosted CERT-A19-R7, https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38617730406 (archived artifact ID `11919983437`).
- The inspected exact Bookworm source-file mechanism uses `Object.assign({}, this[kOptions])` and lacks the investigated JSON clone; `lib/interceptor/cache.js` is absent in the extracted, patched source tree. Mechanism-specific positive/negative observations, **NOT** a definitive CVE non-applicability judgment.

**NON-CLAIMS / hard gaps:** no stopped A18 `lib/balanced-pool.js` bytes have been exported or matched. An identical source-vs-.deb hash is NOT an actual Worker image byte match; source tree file equality is NOT full reproducible .deb build. External Debian signer key custody, all possible alternate issue paths, CVE scope against the actual Worker and host certification remain unresolved. Do not call 2026-84961 / 2026-13697 fixed or false-positive yet. No glibc/SQLite patch has been applied.

**Mutation discipline:** no main/Production/TELMIVO/license/broker/Telegram change, no Docker image built in R8, no unknown Worker execution, A6 remains hard DENY, original 199 (18 Critical +181 High) findings review-open, 0 CVE closures; keep PR #275 DRAFT and do not merge.

Stage verdict: `CERT_A19_R8_SOURCE_SIGNATURE_AND_SEVEN_COMPONENT_SHA_PASS_BINARY_SOURCE_FILE_MATCH_A18_RUNTIME_BYTES_UNVERIFIED`.

## CERT-A19-R9 — Stopped-container actual file SHA, reconstructed A2 → A15 → A18 (2026-10-14)

**Successful isolated GitHub Actions execution:** https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38620656384 ; SUCCESS; run commit `e2f5798e13631421218faa715bb67d4509b83091` on temporary **non-PR** `cert-a19-byte-audit-run` branch.
**Artifact:** `cert-a19-r9-stopped-a18-undeployed-byte-review`, GitHub artifact ID `11922201893`, two-day retention. The run triggered **only one** dedicated R9 workflow, no general PR CI suite.

### Actual read-only observed evidence
- Rebuilt the exact historical fixed A2 Dockerfile using the existing A11 372-package and A12 snapshot pins, then the same A15 exporter and A18 metadata-only Dockerfile, **only within the disposable nonproduction GitHub-hosted runner**. No registry push, release, production or server deployment.
- For each of the three reconstructed images, used `docker create --entrypoint=/bin/true` (never `docker start` / `docker run`) and `docker cp` to extract exactly `/usr/share/nodejs/undici/lib/balanced-pool.js` from a **created/stopped** container. Asserted container state `created` before and after; removed each container.
- Compared SHA-256 with the authenticated Debian source and binary file hash from R7/R8, `06e20567449a6131d5ae6f049b5d85f17c3139f2fed6a2783f656429180ff865`. ALL THREE actual extracted files matched:
  - A2 rebuilt image `sha256:22d04b9083d06f7ba881a7df82a64e5aa7cefd2254a1748220d3780b84c0e835`.
  - A15 rebuilt image `sha256:ff1d9c8e6b36eed23bdd94a0f8316735e4fda9483c364f6dd3d02b742613903b`.
  - A18 rebuilt image `sha256:ee50be233898473b358079e51351b99fcdcad664f858a195d28e7130eac5430e`.
- Validated A11 lock, exact A18 label, A15 `_UNDICI` whole-tree copy code, A6 original denial string, and local deterministic image ownership before reading files. No Worker/guest/trading executable was invoked; image BUILD commands performed only existing benign pinned package setup and fixed A15/A18 validation.

### Mandatory historical-image distinction
The successful earlier CERT-A18 run archived its original candidate **image ID** `sha256:dc8caca0022f73f0568a2962a1cf0da873566a15fd4a59fdc7e6724c9de82cef`. **This differs** from the newly reconstructed A18 image ID `sha256:ee50be233898473b358079e51351b99fcdcad664f858a195d28e7130eac5430e`. Therefore:
- **PASS:** exact byte parity with authenticated Debian for reconstructed A2, A15, A18 images.
- **NOT PROVEN:** direct equality of the archived 2026-10-14 earlier A18 image's `balanced-pool.js` bytes; the original ephemeral image is not preserved in downloaded artifacts. Never equate equal build *recipes* with an identical old image.
- **NOT PROVEN:** all vulnerable code paths/CVE false-positive status, full reproducible Docker image or independent rootless/gVisor host suitability.
- **OPEN:** original 18 Critical + 181 High findings; 0 certified fixed or false-positive. `A6_INDEPENDENT_HOST_CERTIFICATION_REQUIRED` DENY; no production, TELMIVO, broker, Telegram or licenses; PR #275 stays DRAFT and not merged.

Disposition: `CERT_A19_R9_RECONSTRUCTED_STOPPED_IMAGES_UNDICI_SHA_PASS_HISTORIC_A18_IMAGE_ID_DIFFERENT_199_OPEN`.
