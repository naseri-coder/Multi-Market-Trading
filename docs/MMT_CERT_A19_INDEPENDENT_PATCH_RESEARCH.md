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

## CERT-A19-R10 — signed Debian source static CVE mechanism / Worker call-edge audit (2026-10-14)

**Hosted proof:** https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38624129354 — SUCCESS; run commit `866bc4e79a8b7fa38a0f58d9719b4e4988f9a016` on dedicated non-PR branch `cert-a19-byte-audit-run` only. Its isolated R10 audit script and workflow are intentionally **not** introduced into main or this PR. Output artifact `cert-a19-r10-signed-source-static-applicability`, ID `11924170548`, two-day retention. Only the R10 dedicated workflow was triggered by this push; no Docker build or Worker / untrusted code execution.

The R10 runner first revalidated the R8 Debian developer-signed `.dsc`, all seven source components and pinned patched-source `lib/balanced-pool.js` SHA-256 `06e20567449a6131d5ae6f049b5d85f17c3139f2fed6a2783f656429180ff865`. Then the static verifier inspected **that exact Debian-patched source** plus committed fixed Worker wrapper and A6 source; all assertions PASSED.

### CVE-specific entrypoint and mechanism results

| CVE | Official upstream affected ranges (NPM advisory) | Required mechanism / precondition | Exact Debian Bookworm 5.15 static evidence | Worker fixed-path evidence | Decision |
|---|---|---|---|---|---|
| CVE-2026-84961 (GHSA-w293-vg96-wgc3) | 7.24.1–before 7.29.1; 8.0.0–before 8.10.2 | `BalancedPool` plus function-valued custom `connect`/`tls` callback; JSON serialize/reparse drops callback | `index.js` **does export** BalancedPool (a possible library API route), but actual `lib/balanced-pool.js` dispatches via `Object.assign({}, this[kOptions])`; specified `JSON.parse(JSON.stringify(...))` mechanism ABSENT in pinned Debian file | Fixed JS Child has no explicit `require('undici')`, `BalancedPool` construction or TLS callback route | `MECHANISM_NOT_PRESENT_IN_INSPECTED_DEBIAN_5X_SOURCE__DEBIAN_TRACKER_OPEN` |
| CVE-2026-13697 (GHSA-4cwx-7wf7-3272) | 7.0.0–before 7.29.0; 8.0.0–before 8.9.0 | `interceptors.cache()` in shared mode; vulnerable `lib/util/cache.js` qualified private parser, malformed Cache-Control header / cross-request cache match or mixed-private parse error | **Both** `lib/util/cache.js` (the advisory's exact patched file) and `lib/interceptor/cache.js` ABSENT from patched 5.x tree. No `interceptors.cache()` export in inspected `index.js`; no cache-named files in inspected `lib/` path inventory. This is stronger than the R3 check of only one path. | Fixed JS Child has no explicit shared-cache interceptor import or activation | `NAMED_CACHE_INTERCEPTOR_PATHS_ABSENT_IN_INSPECTED_DEBIAN_5X__DEBIAN_TRACKER_OPEN` |

Authoritative advisories: https://github.com/nodejs/undici/security/advisories/GHSA-w293-vg96-wgc3 and https://github.com/nodejs/undici/security/advisories/GHSA-4cwx-7wf7-3272 .
**Do not conflate upstream NPM version applicability with the Debian vulnerability database.** The Debian Security Tracker (checked 2026-10-14) continues to mark Bookworm `node-undici 5.15.0+dfsg1+~cs20.10.9.3-1+deb12u4` **vulnerable/postponed** for both:
https://security-tracker.debian.org/tracker/CVE-2026-84961 and https://security-tracker.debian.org/tracker/CVE-2026-13697 .

### Critical limits of a static reachability finding

- The committed `scripts/runtime_a2_worker.py` trusted JS wrapper sets a fresh `Object.create(null)` VM sandbox and explicitly injects `event` only; it imports `node:fs`, `node:vm` and `typescript` as a trusted outer wrapper. There is no **explicit** Undici/Cache/BalancedPool import or execution path in that inspected entrypoint.
- **No Node VM escape, sandbox security, hidden Node runtime import, alternative equivalent library implementation or arbitrary untrusted guest behavior has been comprehensively ruled out**. Treat this as named-path static evidence only, never as independent sandbox assurance. RUNTIME-A6 remains `A6_INDEPENDENT_HOST_CERTIFICATION_REQUIRED` hard DENY.
- R7/R8/R9 established source binary and **rebuilt** stopped-image file parity, but historical original A18 image ID differs; its direct `balanced-pool.js` byte equality is **not proven**.
- No active CVE remediation, false-positive reclassification, version upgrade, Debian tracker override or release verdict. The original **18 Critical + 181 High = 199** findings remain review-open, 0 certified fixed. No glibc or SQLite changes, no Production/TELMIVO/trading/broker/Telegram change.

**R10 verdict:** `CERT_A19_R10_SIGNED_DEBIAN_5X_SPECIFIC_MECHANISMS_NEGATIVE_FIXED_WORKER_NO_EXPLICIT_CALL_EDGE__DEBIAN_TRACKER_VULNERABLE__ZERO_CVE_CLOSURES`.

**Next gate:** independent vendor/Debian applicability review of upstream 7.x/8.x advisory versus Debian 5.x, plus authoritative assessment of Node bootstrap/VM escape and stopped historical image provenance, before considering any scanner triage disposition. Retain PR #275 DRAFT / DO NOT MERGE.

## CERT-A19-R11 — independent Debian / upstream applicability disposition dossier (2026-10-14)

**Mode:** read-only official-source adjudication and decision documentation, no APT/npm, no test re-run, no Docker/Worker execution, no production or release, no patch. This section is **not** an authoritative Debian security-team verdict.

### A. Frozen evidence and scope

- Exact Debian Bookworm **source/binary**: `node-undici 5.15.0+dfsg1+~cs20.10.9.3-1+deb12u4`, fixed historical 372-.deb A11 manifest with `.deb` SHA-256 `78ec8918d63e365bbdec6edd35bebec9e20cc931f084f24e8673badf191d100c`.
- GitHub-hosted signed source / APT byte evidence (R7: https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38617730406 ; R8: https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38619436727) cryptographically checked .dsc signer using ephemeral Ubuntu-packaged Debian keyring, seven source components, and exact patched `lib/balanced-pool.js` SHA-256 `06e20567449a6131d5ae6f049b5d85f17c3139f2fed6a2783f656429180ff865` in both source and binary.
- The reconstructed stopped A2/A15/A18 package-file SHA matched the above in R9: https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38620656384 . Historic original A18 image digest was different and **historical byte-identical-image parity was NOT established**.
- Narrow signed-source / fixed-wrapper static advisory-path assertions passed R10: https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38624129354 . Static checks do not certify absence of alternate code or VM escape.
- The source-signer keyring was obtained from the GitHub-hosted Ubuntu package manager; independent offline keyring custody and reproducible rebuilding of the complete package/image were **not** attested.
- **Official security status checked 2026-10-14:** Debian Tracker currently lists both CVEs for Bookworm 5.15 as `vulnerable` with `[bookworm] <postponed> (Minor issue)` notes. `postponed` does not mean fixed or not affected.

### B. Authority disagreement — two distinct findings

| CVE | Upstream GitHub Security Advisory exact NPM range / precondition | Independent checks against signed Debian 5.15 source and reviewed wrapper | Debian authority and bugs | R11 recommendation |
|---|---|---|---|---|
| `CVE-2026-84961` / `GHSA-w293-vg96-wgc3` | `>=7.24.1,<7.29.1` and `>=8.0.0,<8.10.2`. TLS callback loss occurs through `BalancedPool` **JSON stringify/parse** of function-valued `connect`/`tls` options. | Public `BalancedPool` API exists in 5.15 (so mere absence of imports is not enough); exact Debian `lib/balanced-pool.js` instead uses `Object.assign({}, this[kOptions])`, with no claimed JSON deep-clone mechanism. Fixed Worker wrapper has no explicit `undici` / `BalancedPool` call edge. Alternative paths / VM escape unproven. | Debian [tracker](https://security-tracker.debian.org/tracker/CVE-2026-84961) says 5.15 bookworm vulnerable/postponed. [Bug #1146745](https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=1146745) is **closed for newer unstable 8.10.2**, not proof of any Bookworm fix; that bug says found in 8.9.0. Even Debian trixie 7.3 currently reads vulnerable despite advisory lower bound 7.24.1, further showing version-mapping review needed. | `POSSIBLE_VERSION_RANGE_TRACKER_DISCREPANCY__MAINTAINER_ADJUDICATION_REQUIRED`; **REVIEW_OPEN**, no scanner suppression. |
| `CVE-2026-13697` / `GHSA-4cwx-7wf7-3272` | `>=7.0.0,<7.29.0` and `>=8.0.0,<8.9.0`. Requires enabling `interceptors.cache()` with relevant malformed qualified `Cache-Control: private`; leak in shared cache or parser error. | In exact signed Debian 5.15, `lib/util/cache.js` (**actual advisory patched path**) and `lib/interceptor/cache.js` absent; `interceptors.cache()` not exposed in inspected `index.js`; fixed Worker wrapper doesn't explicitly enable the interceptor. Alternative implementation and hidden import possibility not globally excluded. | Debian [tracker](https://security-tracker.debian.org/tracker/CVE-2026-13697) says 5.15 bookworm vulnerable/postponed. [Bug #1143070](https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=1143070) is **closed for newer unstable 8.9.0**, not proof of any Bookworm fix; found in 8.5.0. | `POSSIBLE_MISSING_FEATURE_TRACKER_DISCREPANCY__MAINTAINER_ADJUDICATION_REQUIRED`; **REVIEW_OPEN**, no scanner suppression. |

Primary upstream sources:
- https://github.com/nodejs/undici/security/advisories/GHSA-w293-vg96-wgc3
- https://github.com/nodejs/undici/security/advisories/GHSA-4cwx-7wf7-3272
Debian source tracking: https://security-tracker.debian.org/tracker/source-package/node-undici .

### C. No false equivalence between contradictory scopes

1. The **upstream advisory** pertains to specifically described implementation/version ranges and conditions; verified absence of its mechanism in one exact Debian 5.15 file is strong scoped counterevidence.
2. The **Debian Security Tracker** is the authoritative published Debian triage state and marks this release vulnerable. Do not override it in the project's scanner or claim a CVE officially fixed or `not-affected`.
3. Debian BTS bugs #1146745 and #1143070 were closed after newer **unstable** packages; they do **not** close the **Bookworm** tracking entries, which explicitly remain vulnerable/postponed.
4. This version-mapping conflict does **not** imply a blind backport of a 7.x/8.x fix into 5.15 would work, nor does it justify replacing A11 frozen dependencies without new source/reproducibility reviews.
5. Do not generalize results for these **two exact CVEs** to the other original 197 findings; all 18 Critical + 181 High findings remain review-open. A18 historic exact-image proof / rootless gVisor host are missing and A6 remains hard DENY.

### D. Decision record, independent reviewer sign-off required

| Gate | 84961 | 13697 |
|---|---|---|
| Published upstream range includes Debian 5.15 | **NO** | **NO** |
| Described affected mechanism found in signed Debian 5.15 inspected paths | **NO** | **NO** |
| Fixed Worker explicit call to that mechanism | **NO OBSERVED**, not absence proof for guest processes | **NO OBSERVED**, not absence proof for guest processes |
| Debian Bookworm published triage | **VULNERABLE / POSTPONED** | **VULNERABLE / POSTPONED** |
| Maintainer/security team says Bookworm `not-affected` | **NOT OBTAINED** | **NOT OBTAINED** |
| Historic A18 original image byte reproducibility / external host certification | **NOT PROVEN** | **NOT PROVEN** |
| Authorized CVE closure or patch candidate | **NO** | **NO** |
| Project disposition | **REVIEW_OPEN / ESCALATE EVIDENCE** | **REVIEW_OPEN / ESCALATE EVIDENCE** |

**Next decisive evidence:** ask the Debian Security Tracker team to clarify whether the 5.15 Bookworm rows were inherited from source-package version threshold or from separately confirmed 5.x-affected code, and request the exact applicable file/patch/entrypoint if the latter. An independent reviewer must evaluate the answer against signed 5.15 Debian bytes and historic image provenance before suggesting any scanner classification changes.

### E. Prepared maintainer inquiry — draft only, **NOT SENT**

Debian's own Security Tracker contributor guidance (https://security-team.debian.org/security_tracker.html) requests evidence-based triage and accepts a security-tracker mailing-list patch or a Salsa merge request. The archived BTS bugs are **not** proof of a change to Bookworm status. This is a draft to be reviewed before initiating any external communication:

> Subject: Review request: Debian bookworm node-undici 5.15 applicability for CVE-2026-84961 and CVE-2026-13697
>
> Hello Debian Security Tracker maintainers,
>
> We inspected the Debian Bookworm source package node-undici 5.15.0+dfsg1+~cs20.10.9.3-1+deb12u4. We verified the Debian developer-signed .dsc and all seven source archives, applied the packaged patches, and compared the resulting balanced-pool.js SHA-256 with the Debian binary file. We observed `Object.assign({}, this[kOptions])`, not the JSON function-dropping clone described by CVE-2026-84961. We also found neither `lib/util/cache.js` nor `lib/interceptor/cache.js` nor an `interceptors.cache()` export described by CVE-2026-13697. The upstream advisories identify 7.x/8.x vulnerable ranges, while the Debian tracker lists Bookworm 5.15 as vulnerable/postponed.
>
> Could you clarify whether the Bookworm entries represent confirmed 5.x-specific vulnerable code/backports, or whether version applicability warrants review? If Bookworm is affected, please identify the code path or patch proving it. We are **not** requesting an automatic downgrade; we have kept both entries open pending maintainer adjudication.
>
> Technical evidence: CERT-A19 R7–R10 hosted runs and signed source-file hashes linked in https://github.com/naseri-coder/Multi-Market-Trading/pull/275 . Related Debian bugs: #1146745, #1143070 (newer unstable fixes).
>
> Thank you.

**R11 verdict:** `CERT_A19_R11_OFFICIAL_DEBIAN_UPSTREAM_VERSION_MISMATCH_DOCUMENTED_MAINTAINER_REVIEW_REQUIRED_199_REVIEW_OPEN_NO_SECURITY_PATCH`.

**No change in authorization:** main/A11/A18/RUNTIME-A6 unchanged, no new Worker image, no CI quota spent, no Production, TELMIVO, broker, Telegram or unknown code; PR #275 remains DRAFT and must NOT merge.

## CERT-A19-R12 — Worker base-image architecture decision, Debian-neutral research only

**Decision artifact:** [CERT-A19-R12 Debian-neutral runtime architecture and exact acceptance gates](MMT_CERT_A19_R12_RUNTIME_BASE_DECISION.md). This is an **architecture freeze**, not a replacement Worker candidate, Debian vendor resolution, CVE repair or permission to deploy/merge.

Review of frozen main found: Python 3.12 slim Bookworm base, A11 fixed 372 Debian archives, Node v18.20.4 with upstream EOL since 2025-03-27, TypeScript 5.9.3, wasmtime 49.0.0 manylinux x86-64, and framed Python/JavaScript/TypeScript/WASM Worker with `node:vm` (officially not an isolation/security mechanism). A15 retains glibc runtime imports; A18 is metadata-only.

**Research shortlist:** first investigate **signed, minimal, Debian-neutral Wolfi/glibc** combined Python + maintained Node (Node 24 LTS as provisional target) + TypeScript + Wasmtime; separately investigate Alpine/musl as alternative (Wasmtime 49 has musllinux wheels but the pinned manylinux A10 wheel cannot be copied as-is). Google Distroless Debian 13 is a useful minimal-image comparison but **still Debian**, and documented Python3 Debian13 carries Python 3.13, an additional migration relative to pinned 3.12.

**Mandatory independent gates:** provenance and per-arch signed digest, native Python/Node ABI, required ELF/TLS/CA/NSS closure, Node bundled Undici analysis, strict Python/JS/TS/WASM fixed harmless fixture equivalence, independent rootless/gVisor host security, actual comparable scanner/file-byte findings, and preserved original A6 DENY. Historical **199** findings stay open, 0 CVEs closed; no new candidate, Docker build, CI or production changes. Keep PR #275 DRAFT / DO NOT MERGE.

Disposition: `CERT_A19_R12_ARCHITECTURE_RESEARCH_PASS_SECURITY_CANDIDATE_NOT_BUILT_A6_DENIED_199_OPEN`.

## CERT-A19-R13 — independently signed Wolfi OCI base custody, no Worker built

**Full documentary evidence:** [MMT_CERT_A19_R13_WOLFI_BASE_CUSTODY.md](MMT_CERT_A19_R13_WOLFI_BASE_CUSTODY.md).

- First isolated base-provenance run https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38628208782 completed **FAIL** at a too-strong initial assumption that `wolfi-base` already includes a glibc package. Actual checked minimal rootfs **does not** list `glibc` as installed. Upstream image signature and stopped-filesystem acquisition steps had succeeded; the failure was correctly not treated as worker compatibility.
- Corrected single-purpose hosted run https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38628389282 completed **SUCCESS** with separated gates. The exact Cosign/Sigstore public Chainguard certificate identity was checked for immutable **index digest** `sha256:256c88bb066424045021090932d50be93c8e3f2ce3586707702a401b146f3e43`; selected linux/amd64 manifest `sha256:030e45cb37187dff322bbefe9658bcaec31b824a5d523380771a64864c9f45d4`. The stopped container reports `ID=wolfi` with 19 installed APK-db entries, **no observed glibc package**. No container/Worker code was started. CI evidence artifact ID `11926010501` (2 days).
- This **authenticates only the signed Wolfi base**. Python 3.12, Node 24, TypeScript 5.9.3, Wasmtime 49.0.0, glibc, native libraries and four-language Worker semantics **have not been installed or tested in a custom image**; source/package signatures and immutable Apk closure unverified. No security certification, production or permission.
- R14 gate: independently source and pin exact Wolfi glibc / Python 3.12 / Node 24 packages and native ABI first, then isolated, nonproduction 4-language parity after required host-security scope is independently reviewed.
- No production, main, A11/A12, A2/A15/A18, TELMIVO/Telegram/broker, original 199 findings or A6 hard DENY changes; PR #275 stays DRAFT / DO NOT MERGE.

**Verdict:** `CERT_A19_R13_SIGNED_WOLFI_BASE_DIGEST_AND_STOPPED_ROOTFS_PASS_GLIBC_NOT_INSTALLED_COMPONENTS_AND_ABI_NOT_RUN_199_OPEN`.

## CERT-A19-R14 — Wolfi signed-index package candidate snapshot, **NOT** an APK closure lock

[Independent detailed report and source/version checks](MMT_CERT_A19_R14_SIGNED_APK_INDEX.md).

- After four narrow fail-closed iterations, **single-purpose** [GitHub Actions run #38630624422](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38630624422) completed SUCCESS. The exact `cgr.dev/chainguard/wolfi-base` base's Cosign publisher identity/digest was rechecked. Its repository `https://apk.cgr.dev/chainguard` and APK trusted-key files were extracted by `docker create`/`docker cp` from a stopped container.
- The *same signed-base native APK utility* was run in a tightly limited, network-disabled, read-only nonproduction CI container to inspect the local x86_64 `APKINDEX.tar.gz` with verified-base trusted keys; **NO Worker, no user source, no APK package installation, no new Docker Worker image**. SHA-256 of accepted index: `15f8b555714bfe44b0f4de0ee24910e0533f7b4fbb4a650cf533115c6a4f281a`; 8,083,283 bytes; 122,471 package-version records.
- Version candidates *observed but **NOT APK-solver selected / NOT archive-SHA-pinned***: `glibc-2.44=2.44-r8`, `python-3.12=3.12.15-r3`, `python-3.12-base=3.12.15-r3`, `nodejs-24=24.22.0-r0`. Version duplicates are preserved as available alternatives. Indexed `C:` checksums are NOT exact full `.apk` archive SHA-256.
- Evidence artifact `cert-a19-r14-signed-wolfi-index-candidate-versions`, ID `11926177576`, two-day retention. **Known report boolean correction:** hosted report's `worker_or_any_container_code_executed=false` is too broad: trusted `apk` signature/search code **WAS executed**, but no Worker or guest code was. This is documented and corrected in experimental code without rerunning costly CI; do not suppress that distinction.
- Original A11/A12, A2/A15/A18, RUNTIME-A6 DENY, main, 199 open findings and 0 CVE closures remain unchanged. PR #275 remains DRAFT / NOT MERGED.
- Next proof gate: independently verify immutable package archives, resolve full consistent transitive dependencies and ELF/ABI, **then** consider fixed four-language nonproduction qualification. No production approval.

Verdict: `CERT_A19_R14_SIGNED_WOLFI_APK_INDEX_AND_CANDIDATE_VERSION_SNAPSHOT_PASS__FULL_ARCHIVE_SHA_AND_CLOSURE_NOT_PROVEN__A6_DENY_199_OPEN`.

## CERT-A19-R15 — partial four-.apk SHA observations, **BLOCKED** signed-index drift and unresolved solver

**Authoritative fail-closed record:** [R15 package archive provenance and open gates](MMT_CERT_A19_R15_PACKAGE_ARCHIVE_PROVENANCE.md).

R15 narrow experiments confirmed exact R14 Chainguard Sigstore-signed base identity and native keyring acceptance of the **original R14 x86_64 signed APKINDEX digest** `15f8b555714bfe44b0f4de0ee24910e0533f7b4fbb4a650cf533115c6a4f281a` before further checks.

A hosted nonproduction run [#38633084874](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38633084874) **downloaded and measured** the four exact R14 direct-root `.apk` files (glibc-2.44 2.44-r8, python-3.12 3.12.15-r3, python-3.12-base 3.12.15-r3, nodejs-24 24.22.0-r0). Artifact `cert-a19-r15-wolfi-four-root-apk-custody` ID `11926503082` contains only `selection.json` with exact measured full APK SHA-256 and bytes, but has `apk_archives_verified=0` because **native `apk verify` FAILED**. Do NOT treat these observed hashes as cryptographically publisher-authenticated.

Earlier `apk fetch --recursive` attempts did **not** resolve a full transitive closure. On subsequent [run #38633234712](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38633234712), the **live** index bytes had changed versus the frozen R14 index SHA and preflight refused to continue; R14 had not retained raw immutable index bytes. No new index was silently substituted, no signatures or CVEs reclassified, and no full Wolfi combined Worker candidate was constructed.

**R15 verdict:** `CERT_A19_R15_BLOCKED_SIGNED_INDEX_SNAPSHOT_DRIFT__FOUR_APK_SHA256_OBSERVED_BUT_NATIVE_SIGNATURE_UNVERIFIED__TRANSITIVE_CLOSURE_UNRESOLVED__A6_DENY_199_OPEN`.

Future R16 should atomically archive the signed index **bytes** and validate genuine native dependency solver semantics before downloading and signing every archive, without changing old A11/A2/A15/A18, main, A6 or production. PR #275 remains DRAFT and unmerged; original **199** findings remain review-open; 0 CVEs closed.

## CERT-A19-R16 — exact signed Wolfi APKINDEX bytes preserved, archive authenticity / solver remain BLOCKED

[Full R16 evidence and fail-closed disposition](MMT_CERT_A19_R16_ATOMIC_APK_SNAPSHOT.md).

Two independent isolated non-PR, nonproduction GitHub-hosted runs [#38634725817](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38634725817) and [#38634958383](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38634958383) each **accepted one locally held signed APKINDEX** using the verified Chainguard/Wolfi base native keyring and stored the **actual compressed APKINDEX.tar.gz bytes** in GitHub artifacts **11926324789** and **11926664490**, 2-day retention. Both snapshots are byte-identical: SHA-256 `6c61d61969ccb760a72e3cd5aad769102c0146cf0a7a9962ab6491a28e849496`, size 8,083,699, 122,474 package-version records / 15,770 unique names. This new signed snapshot was not misrepresented as the earlier R14 version.

Four direct `.apk` archives were downloaded and their full SHA-256 checked twice; however native `apk verify` returned **`0 - UNTRUSTED` for all four**, both before and after mounting the same locally held index and disabling container network access. Therefore **zero archive signatures certified**. The actual official legacy APKINDEX `C:Q1` checksum binds the **compressed control stream with SHA-1**, not full-package SHA-256; no independent raw archive control-member correspondence or final data-stream authenticity has yet been proven (https://wiki.alpinelinux.org/wiki/Apk_spec).

Native `apk fetch --recursive --simulate --url` returned unable-to-select-package diagnostics for all pinned roots. Offline inventory of the identical signed index exposed **39 unique direct dependency expressions** and **5 multiply-provided dependency names**; this does NOT replace an accepted recursive solver. No full dependency closure, Python/Node native ABI or 4-language Worker execution. No original scanner CVE closure and **199 remain OPEN**.

**VERDICT:** `CERT_A19_R16_SIGNED_INDEX_SNAPSHOT_BYTES_RETAINED__FOUR_APK_ARCHIVE_SIGNATURES_UNTRUSTED__NATIVE_SOLVER_UNRESOLVED__A6_DENY_199_OPEN`.

R17 gate: investigate and verify native APK v2 archive signature/control structure, independently check signed-index Q1 control checksums against actual compressed APK data, preserve tampered-file negative controls and obtain genuine native transitive resolver evidence before any image build. Preserve historical A11 and A2/A15/A18; `main` unmodified, A6 hard DENY, PR Draft and no merge.

## CERT-A19-R17 — four real signed-index Q1→control SHA1→data SHA256 chains PASS, no standalone APK RSA

[Detailed R17 analysis, archive hashes, signer limitations and logs](MMT_CERT_A19_R17_APK_FORMAT_AND_PROVENANCE.md).

A dedicated non-PR, nonproduction [GitHub Actions run #38637717187](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38637717187) **SUCCEEDED** after two fail-closed layout diagnostic runs (#38637178390 too-restrictive gzip limit; #38637520735 incorrectly required three gzip streams). It independently reverified immutable Chainguard base signer, received and natively accepted the current exact Wolfi x86_64 signed APKINDEX, then directly parsed four actual `.apk` v2 archives without installing or executing their contents.

**Critical corrected authenticity semantics:** all four archives contain **two** gzip members (compressed control + compressed data), with **NO individual `.SIGN.RSA[256].*.rsa.pub` stream**. The native `apk verify` result `UNTRUSTED` in R16 therefore must **not** be rewritten as a per-file RSA signature pass. Instead, each exact APK's full SHA-256 and size matched its pinned observed values and signed-index size; index `C:Q1` matched the **SHA-1 of the raw compressed control member**; `.PKGINFO` package identity matched and its signed-control-bound `datahash` matched the **SHA-256 of the raw compressed data member**. **Four out of four control and data chains passed.** Four independently mutated-control and four independently mutated-data negative checks were rejected. **0/4 independent RSA signatures present.**

Verified R17 compressed signed APKINDEX snapshot SHA-256 `8011fbdaf70278ae83e3729dc2c44a8148a91cf03ea0ef7a3d049e30a65e36a5`, preserved as **full index bytes** in hosted artifact `cert-a19-r17-apkv2-control-signature-integrity` ID **11928024023**, 2-day retention, with full `r17-result.json` and native apk version provenance. R17 used `apk-tools 2.14.10`; this version does **not** implement `apk query --recursive` (newer docs), so the **full transitive package dependency closure remains UNVERIFIED**.

**SHA-1 Q1 caveat:** matching the legacy signed-index-to-control hash is not equivalent to collision-resistant, signed SHA-256 over the entire APK. Any future apko resolver candidate must be independently signed, versions >=1.2.7 (older apko subject to CVE-2026-42575 incomplete index-to-payload binding), and prove all transitive archive checks. No native Worker ABI/four-language tests, rootless/gVisor host certification or production capability established.

**R17 verdict:** `CERT_A19_R17_FOUR_APK_V2_SIGNED_INDEX_Q1_AND_DATAHASH_PASS__ZERO_STANDALONE_RSA__FULL_CLOSURE_AND_HOST_UNVERIFIED__A6_DENY_199_OPEN`.

No source/Dockerfiles/Workflows in main changed; A11/A2/A15/A18, original 199 review-open findings and RUNTIME-A6 `A6_INDEPENDENT_HOST_CERTIFICATION_REQUIRED` hard DENY remain unchanged. PR #275 is **DRAFT / DO NOT MERGE**.

## CERT-A19-R18 — signed source verified apko resolves and authenticates **36** transitive Wolfi archives (legacy signed-index chain)

**Full signed-index index-to-file research custody:** [MMT_CERT_A19_R18_APKO_SIGNED_CLOSURE.md](MMT_CERT_A19_R18_APKO_SIGNED_CLOSURE.md). Its table permanently preserves all 36 whole-file SHA-256 values.

A single isolated non-PR hosted [GitHub Actions run #38642890495](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38642890495) completed **SUCCESS**. The v1.4.11 apko Linux/amd64 release's exact GitHub asset SHA-256 `5445ea2467a4ab0db3e31d9f795133128d0564c7afdaa46fcdaa1ee3cf92c757` and Sigstore GitHub Actions signer identity were verified **before** executing the tool. The resolver's local repository contained **only** the archived, independently accepted exact R17 signed index bytes SHA-256 `8011fbdaf70278ae83e3729dc2c44a8148a91cf03ea0ef7a3d049e30a65e36a5`, no mutable live index substitution.

From exact `glibc-2.44=2.44-r8`, `python-3.12=3.12.15-r3`, `python-3.12-base=3.12.15-r3` and `nodejs-24=24.22.0-r0` roots, the genuine `apko show-packages` solver selected **36 unique x86_64 package/version records** in the authenticated index. Independent raw archive byte verification covered **36/36** index `Q1` compressed control matches, **36/36** signed-control `.PKGINFO` compressed-data SHA-256 matches, and **72/72** hash mutation negative controls; **73,750,485 bytes** inspected, with each archive's full SHA-256 recorded.

Evidence artifact: `cert-a19-r18-apko-signed-offline-closure-audit`, GitHub Actions ID **11931730171**, 2-day retention; `r18-result.json` SHA-256 `78356a69bf4c7aa50856450b1b4f55f9aaaf4909072891909a9fe73697fd139b`. Archived local copy and permanent SHA table exist. **This is exact legacy signed-index-linked archive integrity**, NOT 36 independent standalone RSA signatures and NOT remediation for SHA-1 Q1 collision-resistance limitations.

**Hard stops remain:** The package closure does NOT cover TypeScript/Wasmtime or final Worker. No native Python/Node ABI/four-language fixture equivalence, no independent rootless gVisor host security, no production, **199 original findings REVIEW-OPEN, 0 CVE closures**. RUNTIME-A6 hard DENY. No A11/A2/A15/A18/main/TELMIVO/trading edits; PR #275 remains DRAFT / DO NOT MERGE.

Verdict: `CERT_A19_R18_36_PACKAGE_APKO_SOLVER_AND_LEGACY_SIGNED_INDEX_BYTES_PASS__ABI_TS_WASMTIME_AND_HOST_UNVERIFIED__A6_DENY_199_OPEN`.

## CERT-A19-R19 — TypeScript 5.9.3, Wasmtime 49.0.0 package integrity and 19 static Wolfi ELF checks (NO runtime)

[Full R19 technical evidence and explicit gates](MMT_CERT_A19_R19_NATIVE_ABI_AND_COMPONENT_CUSTODY.md).

The single-purpose non-PR [GitHub-hosted R19 run #38645056701](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38645056701) **SUCCEEDED**. It rehydrated and SHA-256 checked exact R18 36-package evidence and the historical R17 signed APKINDEX bytes; no mutable package index was trusted in place of prior evidence.

- npm **TypeScript 5.9.3** official tarball `dist.integrity` SHA-512 **matched actual bytes**; full SHA-256 `10e108c9cf7d5f2879053dff18515fb405abf2ccef63eaaf017d9c571687a1d3`. Internal package identity/compiler file names verified. Registry integrity is not an independently verified publisher signature.
- PyPI **Wasmtime 49.0.0** Linux x86-64 manylinux1 Python wheel SHA-256 `94f0288f9e1c33924995a72bb769f4c4e2885002391589dd6992cdaa35d1990a` matched official metadata and download; embedded `_libwasmtime.so` SHA-256 `9594714d3c73c3087ab3d42d9614cf72973b25c181b8625ffcc46a8a75972d7e`. No independently authenticated wheel publisher attestation established.
- 6 exact R18 native APK archives rechecked against full R18 whole-file SHA-256, with **19 static ELF64 x86-64 objects** inspected via trusted host `readelf`. Maximum observed glibc symbol needed: **Node 24: GLIBC_2.44**, **Wasmtime: GLIBC_2.28**, Python executable GLIBC_2.34, libpython GLIBC_2.38, libcrypto/libssl GLIBC_2.38. No *inspected* ELF needs later than glibc 2.44.
- **NOT VERIFIED:** static all-36-packages ELF link closure, actual loader/linker execution or CA/TLS/NSS functionality, TS compilation / Wasmtime WASM behavior / four-language Worker parity, independent rootless+gVisor host security, production readiness. No Worker image built, no target runtime code executed, no updated historical artifacts.

Evidence GitHub artifact ID **11931782690** (`cert-a19-r19-ts-wasmtime-elf-static-evidence`, two-day retention), actual `r19-report.json` SHA-256 `aeacd3dee432ebbebd2bf3b94f41b13aff5c94bd7eb34dcd16814ad4c6166d55`. RUNTIME-A6 remains DENY, original 199 Critical/High findings review-open and zero CVEs certified closed. Draft PR #275 remains unmerged.

**Verdict:** `CERT_A19_R19_STATIC_ELF_19_OF_SELECTED_COMPONENTS_AND_TS_WASMTIME_HASHES_PASS__NO_WORKER_BUILD_ABI_RUNTIME_OR_SECURITY_CERTIFICATION__A6_DENY_199_OPEN`.

## CERT-A19-R20 — all 36 historical pinned Wolfi APKs and 150 ELF files scanned, loader alias not proven (NO Worker)

[Full R20 signed-byte ELF and fixed-benign-fixture acceptance report](MMT_CERT_A19_R20_FULL_ELF_AND_FIXTURE_SPEC.md).

Single non-PR [GitHub Actions run #38646520589](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38646520589) **SUCCEEDED**. It restored exact authenticated R18 36-package and R19 component evidence, verified frozen original R17 signed-index bytes, re-downloaded **all 36 exact whole-APK SHA256** packages totaling **73,750,485 bytes**, checked each compressed data `.PKGINFO datahash` and inventoried **1,934 files**, **75 symlinks**, **0 hardlinks**. Every discovered ELF64 x86-64 file (**150/150**) was inspected by host `readelf`, **without ever executing target ELF, Worker or user code**.

**Observed static details:** no inspected ELF declared a GLIBC requirement above **2.44**, no `DT_NEEDED` *name* lacked a filename/SONAME candidate, but **27 DT_NEEDED names had multiple filename candidates** (typically a symlink alias plus its versioned target; not a proof of 27 conflicts). **1 literal interpreter path**, `/lib64/ld-linux-x86-64.so.2`, was absent from the combined archive pathname graph while **17 ELF files request it**, including Node and Python. The final root filesystem /usr-merge alias was **not** assembled or proved; this is a **loader-path gate BLOCKED**, not a verified runtime incompatibility. R19 Wasmtime wheel's NEEDED names were compared only against package file-name candidates; the wheel itself was not installed.

Evidence artifact `cert-a19-r20-36-apk-all-elf-static-audit` ID **11932642207**, retention two days. Full actual `r20-static-all-elf.json` SHA-256 `72cd119a29ad364cb5cce4eb5e7536783582ccc4a7f4ecf98905f61972fc542b`. The report also freezes benign-only Python/JS/TS/WASM fixture and negative-control contract **as a SPEC, not a test result**. The Wasmtime compiled module is not invented or run.

**Verdict:** `CERT_A19_R20_36_APKS_150_ELFS_STATIC_PASS__LOADER_LIB64_PATH_NOT_PROVEN__NO_RUNTIME_A6_DENY_199_OPEN`. No new Worker/image, TypeScript/WASM execution, per-APK modern signing assertion, dynamic loader test, independently certified rootless/gVisor, production, CVE changes, old A11/A2/A15/A18/main changes or PR merge. A6 stays hard DENY and all 199 findings remain review-open. Suggested R21: source-prove loader symlink/rootfs semantics then separately approve safe fixture-only runtime.

## CERT-A19-R21 — Signed Wolfi base and 36 frozen APKs prove `/lib64` loader symlink, but rootfs composition still blocked

[Complete R21 signed-base/packaged-loader-path dossier](MMT_CERT_A19_R21_WOLFI_LOADER_LAYOUT.md).

- First isolated [run #38648065313](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38648065313) failed at a strict Docker-export special TAR-entry parser, not at provenance/loader. The corrected single-purpose [run #38648206711](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38648206711) **SUCCEEDED**: immutable Sigstore-verified Wolfi-base `sha256:256c88bb066424045021090932d50be93c8e3f2ce3586707702a401b146f3e43` was `docker create` + `docker export` **without any `docker start/run`**. R18 36 exact APK SHA-256 and `.PKGINFO datahash` were rechecked against frozen signed-index evidence. 18,548,224-byte public base rootfs export; 73,750,485 total APK bytes scanned.
- Previously missing literal ELF interpreter `/lib64/ld-linux-x86-64.so.2` is **statically reachable** in both independently observed source graphs: signed base `/lib64 -> usr/lib` and packaged `wolfi-baselayout` `/lib64 -> usr/lib`; in both graphs it resolves to an **existing** `/usr/lib/ld-linux-x86-64.so.2`, 272,272 bytes. The package-only loader comes from pinned `ld-linux-2.44=2.44-r8`. **No assertion of byte-for-byte base-vs-package loader parity or actual dynamic-link execution.**
- A strict static union is **not a verified installed image**. Exactly **1 base/package file-type collision**: `usr/bin/clear` (BusyBox symlink vs ncurses binary). Exactly **1 package/package file-type collision**: `usr/lib64` (libffi directory vs wolfi-baselayout symlink). Both require controlled package-manager ordering and final rootfs semantics; no manual filesystem mutation or runtime execution performed. **R20's missing literal pathname is explained; future image composition is still BLOCKED.**
- Artifact `cert-a19-r21-signed-rootfs-loader-path-static`, ID **11932744568** (two-day retention). `r21-static-rootfs-path.json` SHA-256 `8ccc6f9a02a373d2262dad6e9ebd9d3bf07b523fa850bbb82e83e2d1591847e8`.
- **Still DENIED:** runtime loader/ABI/Node/Python/TypeScript/Wasmtime fixture parity, independently approved rootless+gVisor host, Worker release, original 199 critical/high finding closure. RUNTIME-A6 stays hard DENY. Main, A11/A2/A15/A18, Telegram/TELMIVO/trading/production and PR merge unchanged.

**Verdict:** `CERT_A19_R21_STATIC_LOADER_LINK_PROVEN_IN_BASE_AND_36_APKS__TWO_ROOTFS_COMPOSITION_COLLISIONS_OPEN__NO_RUNTIME_A6_DENY_199_OPEN`. Suggested R22: confirm loader's exact file-content parity and adjudicate `usr/bin/clear`/`usr/lib64` with verified package-composition semantics before any image or fixture execution.

## CERT-A19-R22 — base-vs-package ELF loader full SHA-256 parity PASS; apko 1.4.11 collision rules provenance PASS, final image OPEN

[Full R22 signed-loader byte and source-pinned filesystem composition decision](MMT_CERT_A19_R22_LOADER_BYTE_PARITY_AND_COMPOSITION.md).

An isolated non-PR [GitHub Actions run #38649169689](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38649169689) **SUCCEEDED** for read-only source validation. Restored exact frozen R18 36-APK and R21 symlink evidence; reauthenticated `cgr.dev/chainguard/wolfi-base@sha256:256c88bb066424045021090932d50be93c8e3f2ce3586707702a401b146f3e43` using `cosign verify`, exported **created, never-started** image filesystem as TAR. Four fixed R18 signed-index-bound APK files (`ld-linux-2.44`, `ncurses`, `libffi`, `wolfi-baselayout`) were downloaded and checked by exact prior whole-archive SHA-256, package control and compressed datahash.

**Closed R21 file-content doubt:** signed base and R18-pinned `ld-linux-2.44=2.44-r8` deliver **exactly equal 272,272-byte ELF files** at `usr/lib/ld-linux-x86-64.so.2`; independently measured whole-loader SHA-256 **`2b1529d949956d0913dce1809976adf339adc0d992de5ae6eba21dad0fa9fb09`** in both. Combined with R21 `/lib64 -> usr/lib` path, this establishes the loader's static source-byte parity, **NOT final rootfs composition or dynamic loading PASS**.

Two immutable Go source files from apko v1.4.11 exact release Git commit `5b3c3182430465dd2212a656411267f150034255` passed expected Git blob SHA checks: `pkg/apk/apk/install.go` **`627e6aae37100935e7b298874e224e26d3311a1f`** and `implementation.go` **`588398c9bf71aae2c43bfb167500d5746b87ea64`**. Source rules conditionally require matching file origin/`replaces` for overwrites; allow existing symlink-to-directory under checked conditions; and identify usr-merge via `merged-lib`. These generic rules **do not prove** actual ordering/ownership of the selected packages.

Actual remaining composition decisions (no silent overrides): `usr/bin/clear` base BusyBox symlink vs `ncurses` regular ELF (17,208 bytes, SHA `98011ef86e4d2985ccc4d4a4e529c7790d1cc2e2f94ffa3296d4dc17f51377ed`); `usr/lib64` base/wolfi-baselayout symlink `lib` vs `libffi` directory. Actual `.PKGINFO` of `ncurses`, `libffi`, `wolfi-baselayout` has **no explicit `replaces`**; final installer decisions, file collision order and composed symlink graph remain unproven.

Evidence GitHub artifact `cert-a19-r22-loader-byte-parity-and-collision-review`, ID **11933641716**, 2-day retention; original JSON SHA-256 `41cefc3fc5e72ca023b3f915b5605b9dd950f24860d313c37de56309d67efec7` (6,588 bytes). No package, tool, ELF, Worker, image or target code installed/executed. **All 199 original findings review-open, 0 CVE closures, A6 hard DENY**, no main/A11/A2/A15/A18/production/Telegram/TELMIVO/broker/trading mutation, PR #275 DRAFT / DO NOT MERGE.

**Verdict:** `CERT_A19_R22_LOADER_SHA256_BASE_PACKAGE_IDENTICAL__SOURCE_PINNED_APKO_COLLISIONS_STILL_OPEN__A6_DENY_199_OPEN`. Safe R23 is a separate isolated package-manager rootfs *composition* qualification and exact final file/symlink check, without any guest/Worker execution.

## CERT-A19-R23 — verified apko installs frozen 36 packages into package-only mini-rootfs; base-overlay collision remains OPEN

[Full R23 completed-hosted-run evidence, exact final path hashes, and conservative base-overlay hold](MMT_CERT_A19_R23_PACKAGE_ONLY_MINIROOTFS.md).

An isolated non-PR [GitHub Actions run #38650418247](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38650418247) completed **SUCCESS**, using exactly pinned Sigstore-authenticated `apko v1.4.11`, the archived signed R17 index, R18 36-package list, and all **36/36** previously authenticated APK full SHA-256+compressed control/data bytes (**73,750,485** source archive bytes). `apko build-minirootfs` **actually installed the 36 packages in a disposable package-only filesystem** with no network or unknown Worker code execution. Real installed database contains exactly **36** packages; generated tar **195,088,384** bytes, SHA-256 `57a8db08358aadfd98877806bdea97f9d6d70ab31eb7d856126d4d20c3df2b63`, static inventory **2,257** entries. It was not uploaded as executable binary or image.

Final observed **package-only** filesystem: `/lib64 -> usr/lib`, loader `usr/lib/ld-linux-x86-64.so.2` SHA-256 **`2b1529d949956d0913dce1809976adf339adc0d992de5ae6eba21dad0fa9fb09`** (272,272 bytes), exact same as signed base and R18 package; `usr/lib64 -> lib` resolves to real `usr/lib` directory despite `libffi` directory vs `wolfi-baselayout` symlink TAR headers; final `usr/bin/clear` is 17,208-byte `ncurses` regular ELF SHA-256 `98011ef86e4d2985ccc4d4a4e529c7790d1cc2e2f94ffa3296d4dc17f51377ed`.

**Major limitation:** `build-minirootfs` did **NOT** overlay the *existing signed Wolfi base image*. Therefore **the original signed-base BusyBox `clear` symlink vs `ncurses` file collision has NOT been tested**, nor actual base-installed-package ownership, rootfs final overlay, dynamic loader, four-language execution or rootless/gVisor certification. No production image/Worker was created.

Complete evidence artifact `cert-a19-r23-signed-apko-package-only-composition` ID **11934846299** (2-day retention); `r23-package-only-rootfs.json` SHA-256 **`1e649d3c64bcf70769b32885dcb192b2a3789a49852f1358460284692e814435`**. A separate redundant [trial #38650936146](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38650936146) **failed** solely because apko attempted to create its cache under `/.cache` on a read-only container root; no installer collision verdict is inferred from that trial and no further R23 runs are justified.

**R23 verdict:** `CERT_A19_R23_SIGNED_APKO_36_PACKAGES_INSTALLED_IN_EPHEMERAL_PACKAGE_ONLY_MINIROOTFS__BASE_OVERLAY_AND_RUNTIME_CERTIFICATION_DENIED__A6_DENY_199_OPEN`. Original 199 findings review-open, 0 CVEs closed, A6 DENY, original A11/A2/A15/A18/main and production unaffected; PR #275 remains **DRAFT / DO NOT MERGE**. Recommended next R24: immutable base-OCI-layout+installed-DB lock and **separate** safe base-overlay composition qualification only; no guest code or Worker execution.

## CERT-A19-R24 — actual signed Wolfi baseimage + frozen 36-APK apko OCI overlay PASS, 40 installed packages; no runtime certification

[Complete R24 successful base-overlay proof, byte hashes, failure explanations and remaining OS gates](MMT_CERT_A19_R24_WOLFI_BASE_OVERLAY.md).

A scoped non-PR, nonproduction [GitHub Actions R24 #38685577527](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38685577527) **SUCCEEDED**. Two earlier fail-closed diagnostics [#38685356127](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38685356127) (strict Docker-save config filename parser) and [#38685447839](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38685447839) (host UID could not stat/clean disposable OCI blobs even though package-manager build succeeded) were resolved only by accepting valid Docker OCI blob config paths and using runner-matched **nonroot** container UID. The latter retry preserved `--network=none`, readonly container root, `--cap-drop=ALL`, no-new-privileges and no target execution.

Unlike R23 package-only minirootfs, R24 took the **exact Sigstore-verified immutable signed Wolfi base**, `docker create`+ `docker cp` (never start), preserved image config/layer bytes from `docker save` in a temporary OCI layout, recovered **19 actual preinstalled package records**, and passed those as `contents.baseimage.apkindex` into source-authenticated **apko v1.4.11**, with exact historical R17 signed APKINDEX and all **36** full-APK SHA-256 pins rechecked. `apko lock` selected **21 new package records**, `apko build --lockfile` produced **12 OCI layers** (original **11** signed-base layer digests preserved as an identical prefix plus exactly one new layer), and the merged OCI layer inventory held **40 installed packages**. All disposable OCI/APK inputs were removed in successful cleanup; no registry push or Worker created.

**Final overlay collision and loader observations:**
- `usr/bin/clear` originally a base BusyBox symlink became **pinned ncurses 17,208-byte regular ELF** in new layer 11, SHA-256 `98011ef86e4d2985ccc4d4a4e529c7790d1cc2e2f94ffa3296d4dc17f51377ed` — **PASS static overlay**.
- `usr/lib64` became an actual **directory** in new layer 11 — **PASS final static type**, different from R23's package-only symlink, with no uncontrolled override.
- `/lib64 -> usr/lib` still resolved to the 272,272-byte exact loader, SHA-256 `2b1529d949956d0913dce1809976adf339adc0d992de5ae6eba21dad0fa9fb09` — **PASS exact final static path/file hash**.
- Final installed `usr/lib/apk/db/installed` has **40 unique packages**, SHA-256 `a1431328059280c1b6f99c4547f7b84f63d66bdb8ed16b81b024c33ed13fcea5`.
- **Explicit remaining OS warning:** apko emitted `/etc/passwd`, `/etc/group`, `/etc/os-release` missing in its build context; final namespace semantics **NOT independently verified**. No runtime relocation, NSS/TLS, Node/Python/TS/WASM fixture, independent gVisor/host certification or source attestation upgrade.

Original source proof artifact `cert-a19-r24-frozen-base-overlay-package-manager-evidence` ID **11950280583**, two-day retention, final actual `r24-result.json` SHA-256 **`284ccd9f9549fbcd6572c442cc5f9ebf5759d4cdf5ccb419f2235bff8a3e2f61`**. This is a nonproduction, unsigned rebuilt OCI research image, **NOT an authorized production artifact**.

**Verdict:** `CERT_A19_R24_SIGNED_WOLFI_BASE_APKO_LOCKED_OCI_OVERLAY_40_PACKAGES_3_PATHS_PASS__RUNTIME_HOST_NOT_CERTIFIED_A6_DENY_199_OPEN`. Keep **199** initial findings review-open, **0 CVEs** certified fixed, RUNTIME-A6 hard DENY, old A11/A2/A15/A18, `main`, production and PR #275 **DRAFT / DO NOT MERGE** unchanged. Suggested R25: final OS account/trust-path preflight and then separately gated developer-only fixed benign four-language fixture checks.
