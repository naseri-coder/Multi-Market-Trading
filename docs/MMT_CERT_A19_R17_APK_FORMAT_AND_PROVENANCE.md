# CERT-A19-R17 — Independent Wolfi APK v2 Signed-Index-to-Archive Control/Data Integrity Audit

**Date:** 2026-10-14 (GitHub UTC runner execution)
**Verdict:** \`R17_SIGNED_INDEX_Q1_SHA1_CONTROL_PLUS_CONTROL_PKGINFO_SHA256_DATA_PARITY_PASS_FOR_FOUR_DIRECT_APKS__NO_STANDALONE_RSA_SIGNATURES__FULL_SOLVER_AND_HOST_CERTIFICATION_OPEN\`
**Authority:** Nonproduction research only, main and A6 DENY preserved, PR #275 **DRAFT / DO NOT MERGE**.

## 1. Why R16 reported UNTRUSTED

R16 ran \`apk verify\` against four direct Wolfi APK files with an offline registry and recorded \`0 - UNTRUSTED\` for each. That observation was correct **for the requested native standalone signature verification** and must not be relabeled as an RSA signature success or proof of malicious content. R17 inspected actual APK v2 bytes and discovered that the packages have **two concatenated gzip members**: first the control stream containing \`.PKGINFO\`, then the data stream. None of these four direct APKs has a separate \`.SIGN.RSA\` or \`.SIGN.RSA256\` gzip stream. Thus a native check requiring an independently embedded archive signature cannot succeed for them.

The relevant, separately verifiable supply-chain linkage for this specific packaging variant is:
1. Sigstore-verified immutable Chainguard Wolfi *base image identity*, supplying the trusted Wolfi/Chainguard APK index keyring.
2. Native \`apk search -x busybox\` signature acceptance of the **exact downloaded APKINDEX.tar.gz bytes** from the repository encoded in that base, without disabling signature verification.
3. For the exact package-name/version/size entry in this **signed index**, compare index \`C:Q1<base64 SHA1>\` with the SHA-1 digest of the **raw, compressed APK v2 control member** (first gzip stream in these unsigned APKs).
4. In the validated control's \`.PKGINFO\`, compare \`pkgname\`, \`pkgver\` and the contained \`datahash\` SHA-256 to the **raw, compressed second gzip data stream**. A data mutation independently changes the SHA-256; a control mutation changes the signed-index Q1 digest.
5. Record full-archive SHA-256 independently; **never** conflate it with the index \`C:Q1\` checksum.

**Security limitations:** the signed-index \`Q1\` digest uses legacy **SHA-1**. A matching SHA-1 is subject to the known weakness of collision resistance and does not equal a contemporary SHA-256 publisher signature over the entire APK. The \`.PKGINFO datahash\` is SHA-256 on the data segment but its trust comes through the SHA-1-bound control. The base image's public signing keys were verified as content of its Sigstore-signed image, not independently custody-attested. No per-APK standalone RSA signatures were present. All of these limitations remain visible in the decision.

Specification: https://wiki.alpinelinux.org/wiki/Apk_spec (work-in-progress, v2 wire format and \`C:Q1\` field), https://pkg.go.dev/chainguard.dev/apko/pkg/lock (explicit range/checksum structure).

## 2. Actual three narrow GitHub-hosted runs

| GitHub run | Outcome | What it established |
|---|---|---|
| [38637178390](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38637178390) | FAIL-CLOSED | Verified publisher identity/index, downloaded 4 APKs, but first verifier rejected a conservative too-small gzip inflate bound. Also revealed Wolfi's installed \`apk-tools 2.14.10\` does not support \`apk query --recursive\` (that command is in *newer* apk documentation). Saved negative evidence for native solver compatibility. |
| [38637520735](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38637520735) | FAIL-CLOSED | Verified same custody inputs and four APK bytes; inspected glibc's real gzip members: first 17,174 compressed / 105,472 inflated bytes, second 3,146,046 compressed / 6,586,368 inflated bytes. Revealed **two-member** unsigned/control+data APK layout, not a three-member separately RSA-signed layout. |
| [38637717187](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38637717187) | **SUCCESS** | Independently extracted and checked each of four v2 control and data compressed members against **the same locally retained, native-signature-accepted APKINDEX snapshot**. Positive Q1 and datahash matches **4/4**; negative one-byte control and data tamper tests rejected **4/4** each; recorded exact byte SHA-256 for each archive and each compressed member. **0/4 standalone RSA signatures present**. No package installation or Worker execution. |

Successful run output artifact ID **11928024023**, name \`cert-a19-r17-apkv2-control-signature-integrity\`, **2-day GitHub retention**. Archive includes \`APKINDEX.tar.gz\` bytes, \`r17-result.json\`, and the actual native tool version record. The raw \`.apk\` archives themselves were **not** uploaded; a new independent package-byte recheck must fetch by exact full-APK SHA-256 and use the retained index bytes.

### New signed-index snapshot identity

- Repository: \`https://apk.cgr.dev/chainguard\` (read from pinned, signed Wolfi base)
- Source image: \`cgr.dev/chainguard/wolfi-base@sha256:256c88bb066424045021090932d50be93c8e3f2ce3586707702a401b146f3e43\`
- R17 exact compressed signed index SHA-256: **\`8011fbdaf70278ae83e3729dc2c44a8148a91cf03ea0ef7a3d049e30a65e36a5\`**
- The R17 signed index differs from archived R16's exact SHA \`6c61d61969ccb760a72e3cd5aad769102c0146cf0a7a9962ab6491a28e849496\`; R17 independently verified its own snapshot **in the same hosted run**. No stale index accepted.

## 3. Four proven direct-APK byte/member relationships

| Direct package | Observed **whole .apk SHA-256** | Signed-index \`C:Q1\` equals raw control SHA-1? | Signed control's \`datahash\` equals compressed data SHA-256? | Embedded standalone RSA signature? |
|---|---|---|---|---|
| \`glibc-2.44 2.44-r8\` | \`e38603061dbeea4a647b2d46d454c954e8af89a495f9b2c07b51b590995a7da0\` | **PASS** | **PASS** | **ABSENT** |
| \`python-3.12 3.12.15-r3\` | \`8086d4e00e7c479957b6b863a31958f9de8e54e2890ca8624dd5dab37f047293\` | **PASS** | **PASS** | **ABSENT** |
| \`python-3.12-base 3.12.15-r3\` | \`ca4ac0aef2c9dea512ce43510b247a8b082593a8af3e50842b06fadc3935db0a\` | **PASS** | **PASS** | **ABSENT** |
| \`nodejs-24 24.22.0-r0\` | \`8c007c9f6027020d5cc580613d59ade62205b0875d93d6be8c2042ce8b130bcf\` | **PASS** | **PASS** | **ABSENT** |

All four signed-index \`C:Q1\` checks and all four \`datahash\` checks passed; all eight one-byte mutation controls rejected mismatch. Full stream SHA-256 and signer-presence flags, true \`apk-tools 2.14.10\` version and original index SHA are recorded individually in the attached GitHub JSON. **Do not call this “4/4 RSA signatures PASS”; RSA signature count is 0.** This proves the narrow, legacy index-to-control-to-data correspondence only.

## 4. Package-solver/rootless host and other residual hard gates

1. **Native tool mismatch is real:** \`apk-tools 2.14.10\` in the exact signed base does not implement \`apk query --recursive\` from the newer documented \`apk-tools\` master. R17 does not claim solver PASS or full dependency closure. Earlier \`apk fetch --recursive --simulate --url\` also failed. The proper next step must use a version-specific supported solver or an independently signed, version-frozen **apko** release with demonstrable checksum enforcement and an offline index/archive snapshot.
2. **Additional apko caveat:** CVE-2026-42575 / GHSA-hcwr-pq9g-rq3m identifies an apko build path in versions before **1.2.7** that did not compare downloaded APK against signed-index checksum. Only a current, verified release with exact source/attestation and a tested index-to-archive comparison may be considered; **do not propose an old apko binary**. Sources: https://github.com/chainguard-dev/apko/security/advisories/GHSA-hcwr-pq9g-rq3m and https://advisories.gitlab.com/golang/chainguard.dev/apko/CVE-2026-42575/ . This is a tool-selection advisory, not a new assertion that the Multi-Market-Trading Worker directly depends on vulnerable apko.
3. 4 verified **direct** packages do not provide all ELF glibc, Python, Node/ICU/OpenSSL/native SONAME, Wasmtime and TypeScript dependencies, and are not sufficient to build a four-language Worker image.
4. No four-language runtime parity, no Python/Node ABI execution, no independent strong rootless OCI+gVisor host, no native Node VM guest escape certification. Original A6 denial remains binding.
5. The original **199** Critical/High findings are still REVIEW-OPEN, with **0** CVEs certified closed, waived or classified false positive. Historical A11 372-lock, A2/A15/A18, \`main\` and production systems are immutable.

**R17 narrow result: signed-index-to-archive member authenticity linkage demonstrated for exactly four root packages, with explicit SHA-1 and unsigned-per-APK limitations. Full runtime supply chain and launch suitability: DENY.**

**Recommended CERT-A19-R18:** derive a deterministic, solver-accepted *full transitive* package closure from the **archived exact R17 signed index bytes**, using a source-verified compatible resolver (apko >= 1.2.7 or audited supported native apk 2.14 command), and individually check Q1/control/datahash/whole SHA-256 for **every** selected archive before any candidate build. Scope control and CI quota budget require one carefully planned isolated run. Do not build, merge, deploy or remove A6 before independent host certification.
