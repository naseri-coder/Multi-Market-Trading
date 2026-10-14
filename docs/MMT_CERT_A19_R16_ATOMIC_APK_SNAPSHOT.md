# CERT-A19-R16 — Wolfi atomic APKINDEX byte custody, independent archive authentication still BLOCKED

**Date:** 2026-10-14 (UTC GitHub Actions runs)
**Decision:** \`CERT_A19_R16_SIGNED_INDEX_SNAPSHOT_BYTES_RETAINED__FOUR_APK_ARCHIVE_SIGNATURES_UNTRUSTED__NATIVE_SOLVER_UNRESOLVED__A6_DENY_199_OPEN\`
**Authority:** Nonproduction security research, draft PR #275 only. **NOT A PATCH**. Never merge or deploy this state.

## 1. Why R16 was necessary

R15 recorded SHA-256 for four downloaded direct-root Wolfi APK files but did not authenticate their native package signatures or solve their transitive dependency graph. Its original R14 mutable live index URL later served different bytes. The specific R16 improvement is a **single-run signed-index snapshot**: retain exact compressed APKINDEX bytes in an evidence artifact and compute their hash, rather than assuming a previous remote URL will retain the same contents.

A successful signed index and real archive SHA-256 measurement **do not automatically prove** the archive is exactly the signed index's package payload. In legacy APK format, the signed index \`C:Q1...\` field is a base64-encoded **SHA-1 of the compressed package control member**, NOT the SHA-256 of the whole .apk. Do not equate signed-index \`C:\`, content identity, full archive SHA-256 or native \`apk verify\` signature result without explicit matching proof. Reference: https://wiki.alpinelinux.org/wiki/Apk_spec .

## 2. Concrete isolated CI runs and what truly passed

| Run | Event / outcome | Verified result | Failure / limit |
|---|---|---|---|
| [38634725817](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38634725817) | Dedicated R16 / **FAILURE** | Revalidated fixed Chainguard Cosign identity, copied repository/keys from *created but never started* digest-pinned Wolfi OCI image, downloaded **exact current APKINDEX bytes**, and native \`apk search -x busybox\` **accepted** that local signed index; four direct APK files downloaded | Native \`apk verify\` attempted a live repository access inside network-disabled sandbox: \`temporary error\`; returned \`0 - UNTRUSTED\` for each of four, so no signatures passed. The simulation solver returned \`unable to select package (or its dependencies)\` for every root. |
| [38634958383](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38634958383) | Narrow rerun after explicitly binding the same local, signed index into native archive verifier / **FAILURE** | All same checks and **exact same compressed APKINDEX SHA-256**; 4 downloads | Native \`apk verify\` still returned \`0 - UNTRUSTED\` on all four, even with the signed repository index explicitly mounted. Full solver still failed. **Do not claim a signer or solver pass.** |

Only the dedicated R16 workflow was triggered on \`cert-a19-byte-audit-run\` (without a PR). The experimental Python verifier and workflow are **not part of this Draft PR's code**. No Worker image built or published; no arbitrary Worker/guest code executed; the already authenticated native APK tool **was executed** inside an ephemeral constrained container, with no network, read-only root filesystem, dropped Linux capabilities, no-new-privileges and limited resources. This does **not** independently certify the host's gVisor isolation.

### Exact retained snapshot from both runs

- Authenticated base: \`cgr.dev/chainguard/wolfi-base@sha256:256c88bb066424045021090932d50be93c8e3f2ce3586707702a401b146f3e43\`; Cosign signing identity \`https://github.com/chainguard-images/images/.github/workflows/release.yaml@refs/heads/main\`, issuer \`https://token.actions.githubusercontent.com\`.
- Repository from the signed base: \`https://apk.cgr.dev/chainguard\`.
- Saved compressed \`APKINDEX.tar.gz\` **8,083,699 bytes**, SHA-256: \`6c61d61969ccb760a72e3cd5aad769102c0146cf0a7a9962ab6491a28e849496\`.
- **122,474** package-version records / **15,770** distinct package names. The two R16 artifact copies were independently unpacked and their exact index bytes SHA-256 recalculated as equal.
- This R16 index is **different** from the previously signed R14 snapshot SHA-256 \`15f8b555714bfe44b0f4de0ee24910e0533f7b4fbb4a650cf533115c6a4f281a\`. R16 does NOT reuse old signature metadata against new bytes: each R16 run independently passed native signed-index acceptance on its own downloaded local bytes.
- GitHub Actions archived the **original compressed index file itself**, \`r16-report.json\`, native solver stdout/stderr and archive-verifier stderr: artifact \`cert-a19-r16-atomic-index-four-root-review\` ID \`11926324789\` (run #38634725817) and ID \`11926664490\` (run #38634958383), **two-day retention**. No .apk payload bytes were uploaded; individual direct-archive hashes were recorded in JSON only. Long-term re-verification requires rehydrating the complete index bytes before these artifacts expire.

### Four measured direct roots — proof has a hard boundary

| Exact index-listed root | Version | Observed downloaded \`.apk\` SHA-256 (both R15 and R16 byte measurements) | Native \`apk verify\` |
|---|---|---|---|
| \`glibc-2.44\` | \`2.44-r8\` | \`e38603061dbeea4a647b2d46d454c954e8af89a495f9b2c07b51b590995a7da0\` | **UNTRUSTED** |
| \`python-3.12\` | \`3.12.15-r3\` | \`8086d4e00e7c479957b6b863a31958f9de8e54e2890ca8624dd5dab37f047293\` | **UNTRUSTED** |
| \`python-3.12-base\` | \`3.12.15-r3\` | \`ca4ac0aef2c9dea512ce43510b247a8b082593a8af3e50842b06fadc3935db0a\` | **UNTRUSTED** |
| \`nodejs-24\` | \`24.22.0-r0\` | \`8c007c9f6027020d5cc580613d59ade62205b0875d93d6be8c2042ce8b130bcf\` | **UNTRUSTED** |

"UNTRUSTED" is a recorded verifier result, **not proof these public packages are malicious**. The archive signature scheme / relevant package key model may differ from our assumptions, which require further investigation. Neither the index \`C:Q1...\` control member digest nor the package data stream has yet been independently matched to bytes inside each downloaded archive, and none of those archives is certified as publisher-authenticated.

## 3. Dependency landscape (OFFLINE index analysis, not solver decision)

The retained signed R16 APKINDEX was parsed offline from the exact artifact (no repository network access):

- Four selected direct root entries list **39 unique** dependency expressions; one is an explicit \`!musl\` conflict.
- **Five** of the 38 non-conflict direct dependency names admit **multiple distinct provider package names** in the signed index: \`py3-pip-wheel\` (2), \`so:ld-linux-x86-64.so.2\` (4), \`so:libc.so.6\` (3), \`so:libcrypt.so.1\` (4), \`so:libm.so.6\` (3).
- Every direct dependency expression had at least one matching *name* or advertised \`provides\`, but this does **not** prove a compatible version combination exists. Recursive indirect dependencies, APK version operators, conflicts, architecture and ELF compatibility remain unexamined by an accepted full solver.
- Both R16 native \`apk fetch --recursive --simulate --url\` diagnostic calls returned nonzero and printed \`unable to select package (or its dependencies)\` for all pinned roots. Thus **NO SOLVER-ACCEPTED CLOSURE** exists. A manual graph or simple "latest version" selection must not be substituted for that proof.

The local offline dependency inventory is retained as a standalone JSON companion for investigation but does not authorize a lock or image build.

## 4. Status, security guards and next evidence-based gate

| Gate | R16 disposition |
|---|---|
| Signed Wolfi base image digest and publisher identity | **PASS** for exactly pinned base |
| Same-run native APK acceptance of signed repository index | **PASS** |
| **Raw compressed index bytes archived and SHA-256 rechecked** | **PASS**, exactly two matching copies |
| Four direct archive download/size/full SHA-256 | **OBSERVED**, NOT authenticated |
| Four direct package native cryptographic signature verifications | **FAIL: UNTRUSTED** |
| Selected roots with independent \`C:\` control member checksum comparison | NOT RUN |
| Native solver accepted full transitive closure | **FAIL / UNRESOLVED** |
| Signed and SHA256-pinned transitive archive closure | NOT RUN |
| Python 3.12 / Node 24 / Wasmtime / TypeScript ABI/semantic parity | NOT RUN |
| Independent rootless Docker+gVisor host approval / strong guest isolation | NOT CERTIFIED |
| Production release | **DENIED** by untouched A6 |
| Original 18 Critical + 181 High = 199 findings | **199 REVIEW-OPEN; 0 FIXED** |

**R16 gate is BLOCKED, despite successful index byte custody.**

**Next narrowly scoped R17** should address the *package authenticity model*, not repeatedly run the same untrusted native verification: consult official APK v2 control/member specification and obtain a fixed audit of \`Q1\` control gzip stream SHA-1, inspect presence/absence of embedded \`.SIGN.RSA...\` members, and independently demonstrate tamper rejection with negative fixtures. Only if native signatures or authoritative signed index-to-archive correspondence is established should a new snapshot be declared an immutable package-binary lock. Resolve full dependency graph with a **supported** native query/solver mode, saving its exact command, stdout, stderr, and proven package versions before building any candidate. Note SHA-1 checksum/legacy signature-format caveats explicitly; no shortcut to an elevated security claim.

Original A11 372 Debian lock and A2/A15/A18 images are preserved. \`main\` unchanged. PR #275 remains **DRAFT / DO NOT MERGE**. No production server, Worker, TELMIVO, broker, trade or Telegram actions. A6 remains **\`A6_INDEPENDENT_HOST_CERTIFICATION_REQUIRED\` hard DENY**.
