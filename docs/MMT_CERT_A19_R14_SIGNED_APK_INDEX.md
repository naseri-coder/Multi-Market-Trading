# CERT-A19-R14 — Verified Wolfi APKINDEX and explicit version-candidate custody

**Date:** 2026-10-14
**Verdict:** \`SIGNED_REPOSITORY_INDEX_VERIFIED / VERSION_CANDIDATES_OBSERVED / PACKAGE_ARCHIVE_AND_TRANSITIVE_CLOSURE_NOT_LOCKED\`
**Scope:** Authenticated index read, offline signature-backed native APK search on a fixed Chainguard/Wolfi OCI base; **NO** Worker build, NO APK package install, no server deployment and no A6 unlock.

## 1. Purpose and trust chain

R13 authenticated the public Chainguard Wolfi base image:
\`cgr.dev/chainguard/wolfi-base@sha256:256c88bb066424045021090932d50be93c8e3f2ce3586707702a401b146f3e43\`.

R14 reverified the same immutable image via \`cosign verify\` with exact signing identity
\`https://github.com/chainguard-images/images/.github/workflows/release.yaml@refs/heads/main\`
and issuer \`https://token.actions.githubusercontent.com\`. It then used **only** \`docker create\` + \`docker cp\` on the stopped root filesystem to copy the image's exact \`/etc/apk/repositories\` and \`/etc/apk/keys\`. The signed image's package repository was \`https://apk.cgr.dev/chainguard\` (not automatically \`packages.wolfi.dev/os\`).

The exact \`https://apk.cgr.dev/chainguard/x86_64/APKINDEX.tar.gz\` was downloaded and bounded. The native \`apk\` utility from the SAME verified, digest-pinned Wolfi image was executed with a strictly bounded **search-only** operation against that exact **locally mounted** index, \`--network=none\`, \`--read-only\`, \`--cap-drop=ALL\`, \`--security-opt=no-new-privileges\`, \`--user=65534:65534\`, read-only mounts, and no package installation. This is a trusted tool invocation inside an ephemeral CI container, **not** execution of the Worker or untrusted guest code; it does **not** certify an independent gVisor / rootless host.

The native \`apk\` accepted the index under the signed base's default trusted keyring and returned available \`busybox\` package records without untrusted-signature errors or signature bypass flags. This is **signature-backed native acceptance**, not independently witnessed/escrowed signing key custody or a proved complete final Worker supply chain. A malicious-key negative-control test was **not** run and must not be claimed.

### Immutable observed identity
- GitHub Actions **SUCCESS**: https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38630624422
- Workflow head: \`db4da20e0c2a3fc016b48c2ce6513e39151767b6\`; isolated non-PR branch \`cert-a19-byte-audit-run\`; no broad PR CI.
- Evidence Artifact: \`cert-a19-r14-signed-wolfi-index-candidate-versions\` GitHub ID \`11926177576\`; retention 2 days; included \`cert-a19-r14-index-custody.json\`.
- Verified repository index snapshot SHA-256: \`15f8b555714bfe44b0f4de0ee24910e0533f7b4fbb4a650cf533115c6a4f281a\`.
- Exact compressed index size: **8,083,283 bytes**; **122,471** signed index package records, including historical versions. **Multiple versions per package name are normal and were preserved rather than arbitrarily selected.**
- Key filenames/key-material hashes from verified base documented in the JSON artifact (three Chainguard-key files and \`wolfi-signing.rsa.pub\`). This does NOT constitute separate signer custody.
- \`APKINDEX\` \`C:\` control checksums are **NOT the full file SHA-256 of individual \`.apk\` archives**; no archive SHA-256 pin was asserted.

## 2. Real signed-index package candidates for linux/amd64

These entries are the **highest versions observed in the exact signed snapshot by numeric version/epoch sorting**. They are **not yet package-resolution results**, a full dependency lock, recommendations to choose one combination or proof that the \`.apk\` file bytes were downloaded. Multiple older versions remain in the immutable snapshot.

| Package name | Highest observed version | Signed-index control checksum (NOT package SHA-256) | Index runtime dependency highlights | Candidate status |
|---|---|---|---|---|
| \`glibc-2.44\` | \`2.44-r8\` | \`Q1QD7MR3LUBjYC3CjWPYwBPlWUIF8=\` | \`!musl\`; \`glibc-2.44-locale-posix\`, \`ld-linux-2.44=2.44-r8\`, \`libgcc\`, base directories and ELF loader | Available in signed index; ABI **NOT RUN** |
| \`python-3.12\` | \`3.12.15-r3\` | \`Q1H+t9zNl2TKOgcTqykl4LKp0Eie8=\` | Exact \`python-3.12-base=3.12.15-r3\` | Available in signed index; ABI **NOT RUN** |
| \`python-3.12-base\` | \`3.12.15-r3\` | \`Q1aZYUW2hxzkJ80Xq65mS7AJnAe1o=\` | TLS/OpenSSL \`so:libcrypto.so.4\`, \`so:libssl.so.4\`, libc/ELF, sqlite3, readline, native modules | Available; native/ABI closure **NOT LOCKED** |
| \`nodejs-24\` | \`24.22.0-r0\` | \`Q1RLBV7bA+XfIYy0NEnUH0aAJ17Ag=\` | \`so:libcrypto.so.4\`, \`so:libssl.so.4\`, ICU, libuv, libc/ELF | Available; Node/TS/JS behavior **NOT RUN** |

The package index separately lists \`glibc\` and \`glibc-2.43\` families, and \`glibc-2.44\` variants. The R13 observation that an exact-name \`glibc\` package was not preinstalled in the minimal base does **not** establish that Wolfi lacks a compatible glibc build. It merely showed this base does not contain the required runtime libraries as installed packages.

**Important:** The signed index has 27 \`glibc\`, 5 \`glibc-2.43\`, 9 \`glibc-2.44\`, 30 \`python-3.12\`, 30 \`python-3.12-base\`, and 29 \`nodejs-24\` **version records**. An APK dependency solver, version constraints, variant conflicts, \`provides\`, and shared-library dependencies must select a consistent set. Sorting by latest version is not a dependency solver.

## 3. Honest audit history and correction

R14 used the **same single-purpose workflow** with scoped corrections, none on PR #275 / main:
1. \`38629991897\`: FAILED because Ubuntu 24.04 hosted apt repositories did not offer \`apk-tools\`; avoided adding an unauthenticated package source.
2. \`38630202312\`: FAILED because a read-only nonroot container cannot acquire a writable APK database lock for \`apk update\`.
3. \`38630295008\`: FAILED due to missing temporary APK DB directory. This did **not** imply a signature failure.
4. \`38630474843\`: native APK **accepted** the downloaded index in read-only \`apk search\`, then the script stopped at \`DUPLICATE_TARGET_PACKAGE_NAME\`; the actual signed index naturally contains version variants.
5. \`38630624422\`: **SUCCESS** after preserving all published version variants, completing bounded JSON evidence. **No Worker build, installed APK packages or broad CI suites.**

**Correction to one generated evidence boolean:** The successful hosted JSON artifact contains the inaccurate field \`worker_or_any_container_code_executed=false\`. That wording is **overbroad**: the verified native Wolfi \`apk\` executable **WAS executed** in a nonproduction, read-only, network-disabled container solely to inspect the index; **no Worker or unknown guest payload was executed**. Corrected code on temporary branch in commit \`23d9d48293f6433a44490da46ea0a60f631e6122\` intentionally used \`[skip ci]\` to save CI quota and did not rewrite the immutable hosted artifact. The corrected, explicit claim above supersedes that one boolean. The rest of the archived evidence still records the package names, digest, versions and source URL.

## 4. Non-claims and decision

**PASS / verified:** publisher identity and immutable Wolfi base digest; exact source repository read from trusted image rootfs; native keyring acceptance of bounded, SHA-pinned x86_64 APKINDEX; evidence of package names, available version variants and declared direct dependencies.

**NOT VERIFIED:** independently escrowed Wolfi key identity, independent malicious-key negative-control, all \`.apk\` archive binary SHA-256, per-package individual signature provenance, transitive solver-accepted closure, pairwise Python/Node/Wasmtime/TypeScript compatibility, ELF/CA/NSS native integration, four-language framed ABI parity, Node \`vm\` untrusted escape isolation and any independent rootless + gVisor host certification.

**No production-ready runtime candidate exists.** Historical A11 372-item lock, A2/A15/A18 source/Dockerfiles, main, Telegram, TELMIVO, broker, production and all CVE dispositions remain unchanged. Original **18 Critical + 181 High = 199** review-open findings; **0** fixed/false-positive certified. \`A6_INDEPENDENT_HOST_CERTIFICATION_REQUIRED\` remains hard DENY. PR #275 **DRAFT / DO NOT MERGE**.

**R14 verdict:** \`CERT_A19_R14_SIGNED_WOLFI_APK_INDEX_AND_CANDIDATE_VERSION_SNAPSHOT_PASS__FULL_ARCHIVE_SHA_AND_CLOSURE_NOT_PROVEN__A6_DENY_199_OPEN\`.

**Next distinct gate, R15:** Use the exact R14 index SHA-256 to obtain a native APK solver-accepted deterministic package selection and transitive closure; fetch bounded archive bytes with matching index \`C:\` identity; independently record immutable full archive SHA-256 and source provenance; fail closed on any mismatch. Only after that consider isolated fixed four-language execution under separately reviewed strong host controls. Do not construct or publish the final Worker in R14.
