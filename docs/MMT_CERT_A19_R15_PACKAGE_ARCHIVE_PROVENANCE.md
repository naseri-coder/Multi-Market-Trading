# CERT-A19-R15 — Wolfi APK direct-archive byte measurement (BLOCKED — NOT a resolved closure)

**Date:** 2026-10-14
**Status:** PARTIAL_EVIDENCE / FAIL_CLOSED / DO_NOT_MERGE
**Repository:** naseri-coder/Multi-Market-Trading
**Source baseline:** main \`dccfe791f465040cc87d210c0ca33fad44f654ae\` (unchanged)
**Prohibition:** No production, registry push, Worker build/execution, package install, trading/broker/Telegram/TELMIVO actions, A11/12/15/18 rewrites, A6 unlock, CVE suppressions, or merging PR #275.

## 1. Exact source of trust — unchanged R14 signed snapshot

- Signed Chainguard base: \`cgr.dev/chainguard/wolfi-base@sha256:256c88bb066424045021090932d50be93c8e3f2ce3586707702a401b146f3e43\`. Cosign verified its pinned publisher certificate and issuer again within R15's scoped CI runs.
- Repository observed in the signed base: \`https://apk.cgr.dev/chainguard\`. Its Wolfi native \`apk\` CLI and base keyring accepted the locally supplied x86_64 repository index, *without* disabling signature checks. Only the trusted manager's bounded search was executed; no unknown guest/Worker code was run.
- Exact R14 compressed APKINDEX SHA-256: \`15f8b555714bfe44b0f4de0ee24910e0533f7b4fbb4a650cf533115c6a4f281a\`. The first four R15 job attempts through run #38633084874 passed this exact index pin and signature/identity acceptance. Later run #38633234712 **stopped** because the live repository index did **not** match that SHA-256 anymore. Old snapshot bytes were NOT preserved by R14 in a durable artifact, so the exact original snapshot cannot safely be assumed to be retrievable from a mutable live URL.

## 2. Four direct package archives downloaded and SHA-256 observed — **NOT signature-verified**

An isolated, non-PR, nonproduction GitHub Actions run **#38633084874** downloaded the following four exact, R14-signed-index-named \`.apk\` archives using HTTPS; their final distribution host was recorded as \`9236a389bd48b984df91adc1bc924620.r2.cloudflarestorage.com\`. The payload bytes below are **observed SHA-256 measurements**, **NOT signed-package authentication** or proof of a complete dependency closure:

| Package | Version | Downloaded bytes | Measured full APK SHA-256 | Cryptographic archive signature |
|---|---|---:|---|---|
| \`glibc-2.44\` | \`2.44-r8\` | 3,163,220 | \`e38603061dbeea4a647b2d46d454c954e8af89a495f9b2c07b51b590995a7da0\` | **NOT VERIFIED** |
| \`python-3.12\` | \`3.12.15-r3\` | 14,737 | \`8086d4e00e7c479957b6b863a31958f9de8e54e2890ca8624dd5dab37f047293\` | **NOT VERIFIED** |
| \`python-3.12-base\` | \`3.12.15-r3\` | 12,397,267 | \`ca4ac0aef2c9dea512ce43510b247a8b082593a8af3e50842b06fadc3935db0a\` | **NOT VERIFIED** |
| \`nodejs-24\` | \`24.22.0-r0\` | 29,784,925 | \`8c007c9f6027020d5cc580613d59ade62205b0875d93d6be8c2042ce8b130bcf\` | **NOT VERIFIED** |

Source: https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38633084874 ; GitHub artifact ID **11926503082** \`cert-a19-r15-wolfi-four-root-apk-custody\`, containing \`selection.json\` with the four observed hashes, \`phase=FOUR_DIRECT_ARCHIVES_FETCHED_PENDING_NATIVE_SIGNATURE_VERIFICATION\`, and \`apk_archives_verified=0\`. Retention is 2 days. These files were **not installed**, executed, copied into an image, nor published as a release. Raw \`.apk\` archives were not retained in the evidence artifact.

The native \`apk verify\` step in that run **failed**, so none of the four archives has been cryptographically authenticated. The temporary archive directory initially used restrictive \`0700\` permissions, preventing an unprivileged verifier from reading the mounted files; corrected to \`0755\` **on the ephemeral experimental branch only**, but the next run hit signed-index drift *before reaching* verification. The permission explanation is supported by code review, **not** a proven causal diagnosis of the original verifier failure because that run did not persist \`verify.log\`. Do not state that signatures passed.

## 3. Transitive dependency resolution is not completed

- Two earlier native \`apk fetch --recursive --url\` attempts against a separate temporary package root failed. One failed due to the unsupported \`--initdb\` option (recorded in stderr), another returned nonzero without a useful stderr diagnostic. The native APK solver did **not** provide an independently verified deterministic closure of \`glibc-2.44\`, \`python-3.12\`, \`nodejs-24\`, and all dependencies.
- **Do not** conflate the four exact direct root packages with the full dependency graph. The index contains virtual SONAME dependencies, version alternatives, \`!musl\`, native OpenSSL/ICU and loader constraints; manual selection is insufficient.
- The R14 index \`C:\` control checksums are **not** full \`.apk\` SHA-256 values. Recording observed file SHA-256 is necessary but not sufficient for vendor authenticity.
- No Python 3.12 + Node 24 + Wasmtime 49 + TypeScript 5.9.3 combination was built, installed, executed, ABI-checked, or four-language parity-tested.
- No rootless-gVisor independent runtime host certification exists. \`node:vm\` is not a security boundary, and RUNTIME-A6 remains \`A6_INDEPENDENT_HOST_CERTIFICATION_REQUIRED\` hard DENY.

## 4. Exact R15 hosted history (bounded, honest)

| Run ID | Outcome | Earliest blocking gate |
|---|---|---|
| [38632106217](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38632106217) | FAILURE | Native APK recursive solver failed; stderr evidence was not yet retained |
| [38632316315](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38632316315) | FAILURE | Native solver \`--initdb\` unsupported; [artifact 11927395149](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38632316315) preserved stderr |
| [38632521795](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38632521795) | FAILURE | Isolated-root native solver exited nonzero; no successful solved package list |
| [38632874232](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38632874232) | FAILURE | Exact signed-index direct-root resolution passed; HTTPS CDN redirect policy denied expected distribution redirect |
| [38633084874](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38633084874) | FAILURE | All **four archive downloads succeeded**; unprivileged signature verification failed; artifact contains full measured hashes, **zero verified signatures** |
| [38633234712](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38633234712) | FAILURE | The live compressed APKINDEX digest no longer equals frozen R14 digest; **stopped before archive verification** |

Only narrow experimental R15 workflow was triggered by changes on \`cert-a19-byte-audit-run\`; there were no broad PR CI jobs, production host access, Worker builds, deployment or server restarts. **DO NOT claim R15 PASS.**

## 5. Freeze the blockers and a safer next gate

**Decision:** \`CERT_A19_R15_BLOCKED_SIGNED_INDEX_SNAPSHOT_DRIFT__FOUR_APK_SHA256_OBSERVED_BUT_NATIVE_SIGNATURE_UNVERIFIED__TRANSITIVE_CLOSURE_UNRESOLVED__A6_DENY_199_OPEN\`.

The appropriate **R16** nonproduction authorization gate is an *atomic same-run source snapshot and provenance lock*, not further blind reruns of R15:

1. Verify exactly one immutable Chainguard OCI publisher identity and Linux/amd64 child digest, its APK repository and embedded keys, and the current \`APKINDEX.tar.gz\` signature. Publish the **compressed APKINDEX bytes themselves** as an expiring evidence artifact with exact size/SHA-256, not merely a digest. Do not mislabel an arbitrary new live index as the old R14 snapshot.
2. Independently inspect local native \`apk\` version/CLI semantics and solver diagnostics; perform a simulation in an empty temporary root with **no package installation or untrusted Worker process**; preserve full bounded stdout/stderr.
3. Preserve chosen package versions, index membership/constraints, package manager's solver result and all transitive SONAME providers. On ambiguous or unsatisfiable dependency closure stop and report root cause; never invent a set.
4. Only then retrieve bounded archives; verify \`apk verify\` of **each** with an immutable independently captured signer keyring in a readable, read-only mounted archive directory, and record complete per-archive SHA-256, identity, size and exact source repository.
5. Keep offline authenticated artifacts to survive future mutable index updates, preserve strict no-execution/no-prod gates, and do not certify final runtime until actual native ABI + four-language fixed benign fixture parity, separate independent rootless/gVisor host test and security review pass.
6. Remain within the established GitHub Actions quota, prefer a single planned run, no CI bursts.

**Project disposition:** R12 architecture comparison and R13 signed Wolfi base proof stand; R14 signed-index snapshot proof stands **for its original bytes**. R15 remains **BLOCKED** pending the new atomic snapshot/solver/archive authentication path. All **18 Critical + 181 High = 199** original findings remain review-open, **0** CVEs closed or suppressed. **NO PR MERGE / NO RUNTIME-A6 CHANGE / NO PRODUCTION DEPLOY.**
