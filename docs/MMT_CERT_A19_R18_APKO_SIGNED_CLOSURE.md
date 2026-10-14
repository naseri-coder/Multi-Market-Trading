# CERT-A19-R18 — Authenticated apko Resolver and Complete 36-APK Research Closure

**Status:** R18 VERIFICATION SUCCESS for the declared four Wolfi direct roots and all apko-selected transitive dependencies. **NOT a Worker build, runtime security certification, production readiness, or CVE closure.**
**Evidence date:** 2026-10-14 UTC.
**Actual hosted run:** https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38642890495 — SUCCESS, one targeted non-PR workflow and no general suite.
**Artifact:** `cert-a19-r18-apko-signed-offline-closure-audit`, ID **11931730171**, 2-day retention. Includes original compressed signed R17 APKINDEX bytes, resolver output and JSON with all component control/data hashes.
**Result JSON SHA-256:** `78356a69bf4c7aa50856450b1b4f55f9aaaf4909072891909a9fe73697fd139b`, independently calculated on the downloaded report.

## Verified trust and solver mechanism

1. Fixed authenticated Wolfi base: `cgr.dev/chainguard/wolfi-base@sha256:256c88bb066424045021090932d50be93c8e3f2ce3586707702a401b146f3e43`, Sigstore signer identity `https://github.com/chainguard-images/images/.github/workflows/release.yaml@refs/heads/main`. Keys and repository location extracted from a **created and never started** stopped container.
2. Restored the exact original R17 `APKINDEX.tar.gz` bytes from artifact 11928024023, pinned SHA-256 `8011fbdaf70278ae83e3729dc2c44a8148a91cf03ea0ef7a3d049e30a65e36a5`; verified that image's native `apk` accepted the local signed index without disabling signature checks. **No current live index was substituted.**
3. Used official **apko v1.4.11**, source/release https://github.com/chainguard-dev/apko/releases/tag/v1.4.11, published 2026-10-12. Release tarball SHA-256 `5445ea2467a4ab0db3e31d9f795133128d0564c7afdaa46fcdaa1ee3cf92c757` was checked AND `cosign verify-blob` verified its exact GitHub Actions release-signing identity and OIDC issuer BEFORE execution. Actual binary reported `GitVersion v1.4.11`, `GitCommit 5b3c3182430465dd2212a656411267f150034255` on linux/amd64. This release is newer than the security fix in apko v1.2.7 for CVE-2026-42575, but that is not a declaration that every possible apko issue was audited.
4. `apko show-packages` ran against a **local absolute-path repository** containing only the pinned R17 index, with exact glibc-2.44 2.44-r8, python-3.12 3.12.15-r3, python-3.12-base 3.12.15-r3, and nodejs-24 24.22.0-r0 root requirements, x86_64 only. It selected **36 unique package/version entries**; the independent verifier enforced exact signed-index membership, root identities and bounded package count/bytes.
5. All **36** archive files were downloaded from indexed package URLs (bounded trusted HTTPS distribution hosts). For each: selected index name/version/size matched; raw legacy v2 compressed control `Q1` SHA-1 matched the **signed index**, control `.PKGINFO` name/version and `datahash` matched SHA-256 of the raw compressed data stream, and whole APK SHA-256 was recorded. **36/36 control and data chains PASS; 72/72 negative hash mutation controls rejected**, **73,750,485 total original archive bytes**. No APK files executed or installed; no new OCI image produced.

**Crucial limitation:** All sampled packages have two gzip members and **no independent embedded RSA signature**. The **Q1 SHA-1 control hash** and the **SHA-256 datahash inside that control** derive trust from the authenticated APKINDEX, not from modern standalone archive signatures; legacy SHA-1 collision concerns remain. No independently escrowed Wolfi keyring or final signed package SHA-256 manifest exists yet. This is research provenance under explicit constraints, not a complete independent supply-chain security attestation.

## Complete 36-package immutable whole-archive SHA-256 research manifest

The following exact values were taken from the successful R18 report. They are preserved here because Actions artifact retention is short. Every future download MUST match these hashes; they are not permission to install or ship the packages.

| Package | Version | Observed full archive SHA-256 |
|---|---|---|
| c-ares | 1.34.8-r4 | `a94a6e11ad55758377b17daed08911a96dda3283719732ee1c5cfdb9ef575e51` |
| ca-certificates-bundle | 20260909-r2 | `aa18190f42bd94e0a1cf4a4c44aa464ee95229a340fc5e851956e8ac0f906d77` |
| gdbm | 1.26-r7 | `b353e1fb3f7702fe2faba2fd6800bbfd3db63a726e17d294a626aacbf239629b` |
| glibc-2.44 | 2.44-r8 | `e38603061dbeea4a647b2d46d454c954e8af89a495f9b2c07b51b590995a7da0` |
| glibc-2.44-locale-posix | 2.44-r8 | `fb171f1e6f2ab314b5964e5b1ba5dbabf42ace912744e02c206f7d4bff32b284` |
| icu78-data-full | 78.3-r4 | `05864995b3445b6eed42f3a3cfa3d158710fcf2da133d452c24e9b91b67dbf37` |
| ld-linux-2.44 | 2.44-r8 | `e0c7e3b457c86a7d672a339a166ee13959356ac8a5b19ab4af5a771fee6c699f` |
| libbrotlicommon1 | 1.2.0-r6 | `583c35b3ad7127def10d535cb7cadc636b64cdc289a49cf24f6d960e8bfcfaa0` |
| libbrotlidec1 | 1.2.0-r6 | `d7d68feac257eaedce2e30289e19fc592b77eb9a78e1c2d6031e58a5b082c50b` |
| libbrotlienc1 | 1.2.0-r6 | `8a48aa008d75e7b0b201318b7fb129c4a6c44da2e2abf29b133af44d1567789c` |
| libbz2-1 | 1.0.8-r25 | `52d98e5a8b0ea3e1f301d565bf8c8fed6b106f881d9d120dbde0d38fbd4f9fb8` |
| libcrypt1-2.44 | 2.44-r8 | `553ebdf51c301926dcb62e43396a550a5bfa8f7f5ce0544d59efc91356149695` |
| libexpat1 | 2.9.0-r0 | `49291dad97f2292a5796c2cdb766f6476b274332ae2bbd3c35447d7f305f81a8` |
| libffi | 3.8.0-r2 | `93fe2f937802653775e8537c7a2840c6de8a1d83c396559be200c0d5d86375f6` |
| libgcc | 16.2.0-r1 | `6c41a73a5e07bfa17ff3fa6c64d0a898905168c780a04f2092eacb53545106db` |
| libicu78 | 78.3-r4 | `a77f0ed940ecebf98b81a949850ef9d1014005b36775a54d2f73ab4fb392260d` |
| libnghttp2-14 | 1.70.0-r5 | `120404110bee390a2cfdea037e0f9714aeed9664505b4a9983c4bfd9c1d4b61b` |
| libstdc++ | 16.2.0-r1 | `fc233c091aa551d6ba6da3e444d99a94e9947d53814d20183a0a7ded9a668f80` |
| libuuid | 2.42.4-r0 | `e1f5d85296afc0074e4d69fb3bdf7cb12b82233768ea5ad38330d53c76724785` |
| libuv | 1.53.0-r0 | `9432226dda75384b6b75271e67da552ca31d3f8731e9312caaf18743e9127624` |
| libxcrypt | 4.5.2-r6 | `fab127bcb2474adc952b6c34a6e3f5c633672b47429a24fcc6fd719425aafb93` |
| mpdecimal | 4.0.1-r4 | `823156afdf095874d8e386ab453e69bf5677ab76dd249da7f6451929e6f9ccd4` |
| ncurses | 6.6.20261010-r0 | `475d8c2ec463637844149030a9cc3fc607782cfe681e3c16f80d2a6bc940bb63` |
| ncurses-terminfo-base | 6.6.20261010-r0 | `fac2c47f1e85175a8cb6842c374b5462aa8a10d548b5d602d28ee7829b00a751` |
| nodejs-24 | 24.22.0-r0 | `8c007c9f6027020d5cc580613d59ade62205b0875d93d6be8c2042ce8b130bcf` |
| openssl-4.0-libcrypto | 4.0.3-r6 | `902627db5c736916f3ba34ca2ae95a034e877cd06b0636f4d01d1ceec81d331e` |
| openssl-4.0-libssl | 4.0.3-r6 | `65e30d6a2cc79e9bf5f744b013451cd7267470ee61743f4d84418b51cf56ab73` |
| openssl-provider-legacy-allowed | 4.0.3-r1 | `5617a56d9eeede758f0448e75e8459d518e6230a41626bc48f8fc00288790990` |
| py3-pip-wheel | 26.2.1-r4 | `9e7ff37eeaa621df6d066b9904a91555848c5c13db95dab7efd2ad67c11fae7a` |
| python-3.12 | 3.12.15-r3 | `8086d4e00e7c479957b6b863a31958f9de8e54e2890ca8624dd5dab37f047293` |
| python-3.12-base | 3.12.15-r3 | `ca4ac0aef2c9dea512ce43510b247a8b082593a8af3e50842b06fadc3935db0a` |
| readline | 8.3-r3 | `bc694bcbfcf3d3d48c890b2701714269c9c0851a85c44bb5bf38347e4999f80b` |
| sqlite-libs | 3.54.0-r0 | `3dbad4bc5618d05eb8efc2c2111575396db90591a96e716b82c152528e1c4ff4` |
| wolfi-baselayout | 20230201-r30 | `0544802d073dac63485309a64a1f533735580bbbaa18b83a59058676c040c2fb` |
| xz | 5.8.4-r0 | `d015b40af8b300a0a33e710573e1e7d6cdc31ae5124bcac2fd299bea90a8506a` |
| zlib | 1.3.2.1_rc20260921-r0 | `f84ebe39e0e002274e8d75955c4aaf5eb9854f2e5f6e1f84df01ef26df7a8153` |

## Explicit unpassed gates

- This package closure covers only glibc/Python/Node roots and their solver-selected transitive closure. **It does NOT include TypeScript 5.9.3 and Wasmtime 49.0.0** or their source/wheel/native dependencies; no four-language Worker image or baseline equivalence exists.
- Native ELF loader, library ABI, OpenSSL/TLS, resolver/NSS, timezone, CPython imports, Node runtime behavior, Wasmtime binding and TS compilation have **not** been run or certified.
- No arbitrary code sandbox or VM escape resistance proven; Node `vm` is not a security boundary. Independent rootless OCI+gVisor host certification is still absent. A6 remains `A6_INDEPENDENT_HOST_CERTIFICATION_REQUIRED` DENY.
- Historical A11 372-archive lock, all A2/A15/A18 recipes, main, and original 199 open Critical/High vulnerabilities remain unchanged. **0 CVEs closed or suppressed.** No production deployment, registry push, user strategy execution or PR merge.

**R18 verdict:** `CERT_A19_R18_36_PACKAGE_APKO_SOLVER_AND_LEGACY_SIGNED_INDEX_BYTES_PASS__ABI_TS_WASMTIME_AND_HOST_UNVERIFIED__A6_DENY_199_OPEN`.

**Next R19:** Source-authenticate and pin TypeScript 5.9.3 and Wasmtime 49.0.0 against compatible Wolfi/Python 3.12 ABI, inspect frozen 36-package ELF/loader/TLS closure and prepare fixed harmless fixture equivalence checks. Do not run unknown user strategies, relax A6 or claim production approval.
