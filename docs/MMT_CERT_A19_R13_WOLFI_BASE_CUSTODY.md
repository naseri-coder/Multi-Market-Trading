# CERT-A19-R13 — Wolfi OCI base signature and stopped-rootfs custody

**Date:** 2026-10-14
**Status:** SIGNED_BASE_PINNED / FULL_WORKER_CANDIDATE_NOT_BUILT / A6_DENIED
**Scope:** One independently limited, temporary GitHub-hosted research workflow on \`cert-a19-byte-audit-run\`; no PR from that test branch, no production/TELMIVO/trading changes.
**Historic baseline:** \`main\` dccfe791f465040cc87d210c0ca33fad44f654ae; preserve all A11/A12/Dockerfile/A2/A15/A18 and no legacy dependency mutation.

## Objective
Before attempting any Debian-neutral Worker build, obtain a concrete immutable **multiarchitecture OCI manifest index digest** and a cryptographically checked Chainguard Sigstore signature identity for a **public Wolfi base**. Then inspect the linux/amd64 root filesystem without ever executing container code. Do not confuse signing of this base with the presence/compatibility of Python 3.12, maintained Node, TypeScript, Wasmtime, independently secure Worker confinement or an attested package closure.

## Actual hosted execution
- Run #38628208782: https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38628208782 — **FAIL** at final preflight because the *minimal* signed base had no installed \`glibc\` matching the initial requirement. Sigstore, OCI resolution, Docker pull, \`docker create\` and \`docker cp\` had completed successfully, but the final verifier stopped with \`CERT_A19_R13_BASE_GLIBC_NOT_IN_APK_DB\`. This is not a proof that glibc cannot be installed in a Wolfi *custom candidate*; it is proof that this signed base does **not already satisfy** the mandatory Worker glibc requirement.
- Narrow verifier correction split **verified base provenance** from **still-missing Worker glibc provisioning**. It did not silently certify ABI compatibility or change the base digest. A single isolated rerun was authorized on the same non-PR branch.
- Run #38628389282: https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38628389282 — **SUCCESS**. One dedicated job, no general PR CI. GitHub-hosted runner ubuntu-24.04; checkout SHA-pinned. \`sigstore/cosign-installer@6f9f17788090df1f26f669e9d70d6ae9567deba6\` (v4.1.2); \`cosign verify\` checked *exact digest* against the **fixed public Chainguard signing identity** and Sigstore OIDC issuer. Base image pulled by digest and inspected with \`docker create\`, \`docker cp\`, \`docker inspect\`, \`docker rm\`; **no \`docker run\`, \`docker start\`, Worker, trading fixture, or untrusted user code executed**.
- GitHub artifact ID **11926010501**, name \`cert-a19-r13-wolfi-signed-oci-provenance\`, two-day retention; JSON evidence: \`cert-a19-r13-provenance.json\`.

### Pinned identity, exact observation (NO claimed upgrade)
| Item | Observed verified value |
|---|---|
| Public publisher image | \`cgr.dev/chainguard/wolfi-base\` |
| Multi-arch index digest | \`sha256:256c88bb066424045021090932d50be93c8e3f2ce3586707702a401b146f3e43\` |
| Selected linux/amd64 manifest digest in index | \`sha256:030e45cb37187dff322bbefe9658bcaec31b824a5d523380771a64864c9f45d4\` |
| Manifest entries | 2 |
| Verified signatures matching the exact index digest | 1 |
| Sigstore OIDC issuer | \`https://token.actions.githubusercontent.com\` |
| Signer certificate identity | \`https://github.com/chainguard-images/images/.github/workflows/release.yaml@refs/heads/main\` |
| Signed base \`/etc/os-release\` | \`ID=wolfi\`, \`VERSION_ID=20230201\` |
| Rootfs package database entries | 19 (observed; **not** signed per-package closure) |
| \`glibc\` package already installed in base | **NO** — zero named \`glibc\` / \`glibc-locale-posix\` entries |
| Python 3.12 runtime installed + ABI verified | NO |
| Node.js 24 runtime installed + ABI verified | NO |
| TypeScript 5.9.3 installed + tested | NO |
| Wasmtime 49.0.0 installed + tested | NO |
| Four-language Worker fixture parity | NOT RUN |
| Independent OCI strong-isolation host / rootless gVisor | NOT CERTIFIED |
| CVEs fixed/false-positive certified | 0, all original 199 review-open |
| A6 / production | \`A6_INDEPENDENT_HOST_CERTIFICATION_REQUIRED\` hard DENY, no release |

### Supply-chain boundaries
A valid Sigstore signature with **specific publisher identity** plus immutable OCI index digest authenticates this observed public Wolfi **base** for that workflow. It does *not* cryptographically validate the future \`apk\` index, individual package identities, Python/Node download channels, historical Debian A18 bytes, the final derived Worker image, or the strong isolation of a host. The base is mutable by tag, thus **never use** \`:latest\` in a future candidate recipe; if this base is used, refer to the verified \`@sha256:256c88...\` index and record the exact amd64 manifest digest separately. Vendor reference: https://support.chainguard.dev/hc/en-us/articles/53833609818779-Verify-Chainguard-image-signatures-with-cosign .

### Evidence for future Wolfi package feasibility — not yet installed
- Wolfi's upstream recipe for \`python-3.12\` exists: https://github.com/wolfi-dev/os/blob/main/python-3.12.yaml . Its *current mutable upstream recipe* is not an authenticated, pinned APK archive closure or guaranteed compatible packaged Python for this base. In R13, no Python was installed, run or verified.
- Wolfi upstream has \`nodejs-24\` packages (an available package family, **not** a qualified Worker build): https://github.com/wolfi-dev/os/issues/78608 . Note independent reported ARMv8.0-A compatibility issues with some Wolfi \`nodejs-24\` aarch64 builds: https://github.com/wolfi-dev/os/issues/78694 ; the initial R13 target is **linux/amd64 only**, with no arm64 claims.
- Wasmtime 49.0.0 manylinux x86_64 wheel has historical pinned SHA-256 \`94f0288f9e1c33924995a72bb769f4c4e2885002391589dd6992cdaa35d1990a\`; this alone does not guarantee compatibility with the Wolfi Python shared library or loader: https://pypi.org/project/wasmtime/49.0.0/ .
- No npm/TypeScript toolchain installed, no network or stdlib compatibility tested.

## Decision and exact next gating

**R13 result:** \`CERT_A19_R13_SIGNED_WOLFI_BASE_DIGEST_AND_STOPPED_ROOTFS_PASS_GLIBC_NOT_INSTALLED_COMPONENTS_AND_ABI_NOT_RUN_199_OPEN\`.

Proceed **only after explicit separate authority** with an R14 *isolated package-custody plan*:
1. Select immutable, authenticated apk indexes and exact signed/hashed \`glibc\`, \`python-3.12\`, \`nodejs-24\` candidate packages with fixed per-arch versions; observe OpenSSL/CA/NSS and native ELF closure **without running code**.
2. Pin TypeScript 5.9.3 and Wasmtime 49 Python binding exactly; independently authenticate supply-chain sources, never silently reuse a Debian lock.
3. Prepare **new** nonproduction multi-stage Wolfi candidate recipe, never mutate A2/A15/A18 or A11 372 historical locks.
4. Only then run narrowly scoped fixed harmless **four-language parity** on a suitable independently guarded disposable runner; \`node:vm\` alone is not a secure sandbox.
5. Keep \`main\`, production/TELMIVO/trading servers, all 199 historical scanner findings, all A6 gate checks and Draft PR #275 untouched.

**Not authorized now:** release, Docker Worker build, kernel/security policy exceptions, production deploy, PR merge, removing Debian historical evidence or closing any CVE.
