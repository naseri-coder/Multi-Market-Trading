# CERT-A19-R19 — TypeScript / Wasmtime Source Custody and Wolfi Native ELF Static Review

**Research verdict:** CERT_A19_R19_NPM_TYPESCRIPT_SHA512_PYPI_WASMTIME_SHA256_AND_19_STATIC_ELF_PASS__FULL_RUNTIME_ABI_GVISOR_AND_CVES_NOT_CERTIFIED
**Repository:** naseri-coder/Multi-Market-Trading
**Date:** 2026-10-14/15 UTC (hosted execution)
**Scope:** nonproduction research, no Worker build/deploy/execute or repository main changes.

## 1. Authoritative hosted validation

- Successful isolated GitHub-hosted job: https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38645056701
- Dedicated workflow ran from non-PR-only branch cert-a19-byte-audit-run and did **not** trigger all repository PR CI suites.
- GitHub artifact ID **11931782690**, name cert-a19-r19-ts-wasmtime-elf-static-evidence, 2-day retention. Carries r19-report.json, NOT binaries.
- Independently extracted exact JSON from the downloaded artifact and verified SHA-256:
  \`aeacd3dee432ebbebd2bf3b94f41b13aff5c94bd7eb34dcd16814ad4c6166d55\`.
- Exact R18 signed-index snapshot bytes were restored from source artifact and verified SHA-256 \`8011fbdaf70278ae83e3729dc2c44a8148a91cf03ea0ef7a3d049e30a65e36a5\`. The full 36-package R18 result JSON independently matched SHA-256 \`78356a69bf4c7aa50856450b1b4f55f9aaaf4909072891909a9fe73697fd139b\`, and verified the 6 selected native APK versions/hashes below against that 36-record manifest. This stage made NO new live APKINDEX request.

## 2. TypeScript 5.9.3 — exact official npm registry artifact custody

- Official \`https://registry.npmjs.org/typescript/5.9.3\` JSON metadata was requested and returned the exact \`name=typescript, version=5.9.3\`.
- Tarball URL: \`https://registry.npmjs.org/typescript/-/typescript-5.9.3.tgz\`.
- npm distribution \`dist.integrity\` matches the SHA-512 digest of downloaded tarball bytes, **PASS**:
  \`sha512-jl1vZzPDinLr9eUt3J/t7V6FgNEw9QjvBPdysz9KfQDD41fQrC2Y4vKQdiaUpFT4bXlb1RHhLpp8wtm6M5TgSw==\`.
- Full tarball SHA-256: \`10e108c9cf7d5f2879053dff18515fb405abf2ccef63eaaf017d9c571687a1d3\`.
- The package-internal JSON identity and compiler resources were checked. \`package/lib/tsc.js\` was 267 bytes, while \`package/lib/typescript.js\` was 9,112,572 bytes.
- No npm install, no TypeScript compilation, no downloaded npm code executed. **Important limit:** registry integrity matching is NOT proof of a separate verified npm publisher signature/attestation; this stage did not obtain one.

## 3. Wasmtime 49.0.0 — exact PyPI Linux/glibc Python wheel custody

- Official PyPI release JSON at \`https://pypi.org/pypi/wasmtime/49.0.0/json\` was checked for version 49.0.0 and exact wheel name.
- Selected wheel: \`wasmtime-49.0.0-py3-none-manylinux1_x86_64.whl\`. Python 3 generic package, Linux x86-64 glibc manylinux1 wheel tag; NOT the musllinux wheel.
- SHA-256 declared by PyPI AND independently computed from downloaded file:
  \`94f0288f9e1c33924995a72bb769f4c4e2885002391589dd6992cdaa35d1990a\` — **PASS**.
- Internal \`.dist-info/WHEEL\`, \`.dist-info/METADATA\` and \`.dist-info/RECORD\` and exact wheel tag/name/version checked. This is consistent with the historical A10 wheel artifact, but no production file was replaced.
- Extracted native library **for static inspection only**: \`wasmtime/linux-x86_64/_libwasmtime.so\` (31,590,960 bytes), SHA-256:
  \`9594714d3c73c3087ab3d42d9614cf72973b25c181b8625ffcc46a8a75972d7e\`.
- The wheel was published to PyPI without a Trusted Publishing attestation according to the public release metadata. No independent developer signature/attestation of this particular wheel was verified. **PyPI metadata + matching SHA-256 is a custody observation, not independent origin attestation.**
- No wheel installation, Python import, native load, WASM execution, or Worker action.

Official listing: https://pypi.org/project/wasmtime/49.0.0/.

## 4. Native ELF / glibc static ABI evidence (only a selected scope)

Actual APK files downloaded from the R18 pinned Wolfi archive URLs were full SHA-256 checked against the R18 manifest, with control/data checks on their APK v2 compressed streams. No packages installed. On those specific six package archives, Python extracted the ELF files as **data only**, using bounded tar/gzip extraction, and the host's trusted \`readelf\` inspected ELF dynamic sections, required glibc symbol versions, ELF interpreters and NEEDED sonames. No target runtime or target dynamic loader was invoked.

| R18-pinned native APK | Exact version | APK full SHA-256 | ELF subset inspected |
|---|---|---|---|
| glibc-2.44 | 2.44-r8 | \`e38603061dbeea4a647b2d46d454c954e8af89a495f9b2c07b51b590995a7da0\` | 7 |
| ld-linux-2.44 | 2.44-r8 | \`e0c7e3b457c86a7d672a339a166ee13959356ac8a5b19ab4af5a771fee6c699f\` | 1 |
| python-3.12-base | 3.12.15-r3 | \`ca4ac0aef2c9dea512ce43510b247a8b082593a8af3e50842b06fadc3935db0a\` | 7 |
| nodejs-24 | 24.22.0-r0 | \`8c007c9f6027020d5cc580613d59ade62205b0875d93d6be8c2042ce8b130bcf\` | 1 |
| openssl-4.0-libcrypto | 4.0.3-r6 | \`902627db5c736916f3ba34ca2ae95a034e877cd06b0636f4d01d1ceec81d331e\` | 1 |
| openssl-4.0-libssl | 4.0.3-r6 | \`65e30d6a2cc79e9bf5f744b013451cd7267470ee61743f4d84418b51cf56ab73\` | 1 |
| Wasmtime wheel native .so (not APK) | 49.0.0 | \`9594714d3c73c3087ab3d42d9614cf72973b25c181b8625ffcc46a8a75972d7e\` | 1 |

**19 ELF64 x86-64 files** statically inspected; no observed \`GLIBC_2.45\` or higher requirement. Representative maximum observed GLIBC symbol versions:

- \`usr/bin/node\` from Wolfi Node.js 24.22.0 — **GLIBC_2.44**.
- \`usr/bin/python3.12\` — **GLIBC_2.34**, while \`libpython3.12.so.1.0\` — **GLIBC_2.38**.
- \`libcrypto.so.4\` and \`libssl.so.4\` — **GLIBC_2.38**.
- \`wasmtime/linux-x86_64/_libwasmtime.so\` — **GLIBC_2.28**.
- \`libc.so.6\` — **GLIBC_2.44**.
- Node and Python ELF request interpreter \`/lib64/ld-linux-x86-64.so.2\`, but **a valid final image symlink/path and dynamic loading have not been tested**.

Across these 19 selected ELF files, 19 distinct \`DT_NEEDED\` library names were seen, including \`libcrypto.so.4\`, \`libssl.so.4\`, \`libpython3.12.so.1.0\`, \`libicui18n.so.78\`, \`libicuuc.so.78\`, \`libuv.so.1\`, \`libc.so.6\` and \`libstdc++.so.6\`. The actual file identities, required libraries and requested ELF interpreters are individually recorded in the attached JSON.

**THIS IS A STATIC, SAMPLED ELF REVIEW:** Not every ELF file in all 36 packages was inspected, no runtime linker/path resolution was executed, and no final combined OCI filesystem with NSS, CA/TLS or Python module import semantics was assembled. “All 4 languages compatible” is NOT proven.

## 5. Disposition and next gates

**Scope PASS:** TypeScript tarball registered-version SHA-512; Wasmtime wheel pinned PyPI SHA-256 and manylinux ELF; selected 6 R18-native APK full SHA-256 and 19 static ELF x86-64 dynamic/symbol inspection with glibc required-symbol upper bound **2.44**.

**NOT PASS / NOT RUN:** independently authenticated TypeScript/Wasmtime publisher attestations; all 36 native APK ELF/SONAME link closure; actual Python 3.12 + Node 24 + TypeScript 5.9.3 + Wasmtime 49 runtime integration; four fixed harmless-language fixture equivalence; malicious guest confinement; independently reviewed rootless OCI + gVisor host; A6 unlock; production.

**199 original Critical/High findings remain REVIEW-OPEN, 0 CVE closures.** No A11, A2/A15/A18 image/Dockerfile, runtime source, production, TELEGRAM/TELMIVO/broker, \`main\` or merge changed. PR #275 stays DRAFT / DO NOT MERGE; \`A6_INDEPENDENT_HOST_CERTIFICATION_REQUIRED\` remains hard DENY.

**Recommended CERT-A19-R20:** First complete static ELF path/SONAME closure on all 36 pinned APK bytes with explicit vendor source provenance and file hashes. Then prepare an independently controlled, benign-fixture-only runtime-equivalence harness with a separate host security gate, including explicit requalification of Node 18 → Node 24, before any new Worker image could be considered. Any package/publisher attestation gaps remain open; no silent security waivers.

**Final R19 label:** \`CERT_A19_R19_STATIC_ELF_19_OF_SELECTED_COMPONENTS_AND_TS_WASMTIME_HASHES_PASS__NO_WORKER_BUILD_ABI_RUNTIME_OR_SECURITY_CERTIFICATION__A6_DENY_199_OPEN\`.
