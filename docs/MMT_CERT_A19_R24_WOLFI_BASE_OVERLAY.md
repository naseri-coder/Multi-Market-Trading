# CERT-A19-R24 — Signed Wolfi Base OCI Overlay with Frozen apko v1.4.11 Lock

**Date:** 2026-10-15 UTC
**Verdict:** \`CERT_A19_R24_REAL_BASE_OVERLAY_OCI_FILE_COMPOSITION_PASS__FOUR_LANGUAGE_EXECUTION_AND_INDEPENDENT_HOST_SECURITY_NOT_CERTIFIED\`
**Scope:** disposable nonproduction file-system composition, not production Worker certification.
**Original main:** \`dccfe791f465040cc87d210c0ca33fad44f654ae\`, **unchanged**; PR #275 **DRAFT / NOT MERGED**.

## 1. Source custody and exact hosted evidence

The independently verified public base image was \`cgr.dev/chainguard/wolfi-base@sha256:256c88bb066424045021090932d50be93c8e3f2ce3586707702a401b146f3e43\`. The published Chainguard Sigstore GitHub Actions signer identity and OIDC issuer were verified via pinned \`cosign\`. The image was \`docker pull\`, \`docker create\` (**NEVER STARTED**), \`docker cp\` for genuine preinstalled package database and public keys, and \`docker save\`. The OCI base layout created locally retained the exact source image's configuration blob SHA-256 (verified against Docker image ID) and all original unmodified base layer bytes, with a newly generated index/manifest. **Do not confuse the newly generated OCI manifest digest with the original vendor-signed index digest.**

The genuine installed-package database recovered from the never-started base contained **19** packages. The exact historical R17 native-accepted signed \`APKINDEX.tar.gz\` bytes SHA-256 \`8011fbdaf70278ae83e3729dc2c44a8148a91cf03ea0ef7a3d049e30a65e36a5\`, R18 36-package proof JSON SHA-256 \`78356a69bf4c7aa50856450b1b4f55f9aaaf4909072891909a9fe73697fd139b\`, and R23 successful package-only JSON SHA-256 \`1e649d3c64bcf70769b32885dcb192b2a3789a49852f1358460284692e814435\` were restored from their GitHub Actions artifacts and matched exact bytes before processing. All **36/36** previously frozen APK file SHA-256 and control/data stream hashes were checked again, total **73,750,485 bytes**.

The official \`apko v1.4.11\` Linux/amd64 distribution tar SHA-256 \`5445ea2467a4ab0db3e31d9f795133128d0564c7afdaa46fcdaa1ee3cf92c757\` and its exact Sigstore release signer/issuer were validated **before execution**. The cached index was natively accepted with signatures required. apko package resolution and construction were performed inside a disposable network-disabled, read-only-host, unprivileged-UID Docker sandbox, with caps dropped, no-new-privileges and bounded PID/memory. Only the ephemeral output directory was writable; no target Worker, guest Python/Node/TS/Wasmtime code was run, and no registry push occurred.

**Runs (do not conflate their verdicts):**
- [R24 run #38685356127](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38685356127) **FAIL-CLOSED**, at strict preparatory Docker save config path handling \`CERT_A19_R24_CONFIG_NAME_INVALID\`; no package manager lock/overlay result.
- [R24 run #38685447839](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38685447839) **PARTIAL**, successfully generated actual base-image lock and completed apko OCI base overlay, but independently auditing and cleanup of unprivileged OCI output files failed due to output-file ownership/permissions relative to the normal hosted-runner UID. No final success verdict from this run.
- [R24 run #38685577527](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38685577527) **SUCCESS**. The package manager ran as the host runner's same *unprivileged* UID (still with network disabled, read-only host root, dropped capabilities and no-new-privileges). All lock, OCI output and static file-path checks passed, and both the temporary OCI/package cleanup and single-purpose job succeeded. This is the authoritative R24 result.

Final job artifact \`cert-a19-r24-frozen-base-overlay-package-manager-evidence\`, ID **11950280583**, short two-day GitHub retention, was downloaded independently. The exact \`r24-result.json\` is **5,859 bytes**, SHA-256 **\`284ccd9f9549fbcd6572c442cc5f9ebf5759d4cdf5ccb419f2235bff8a3e2f61\`**. The artifact also contains bounded \`apko-lock.stderr\` and \`apko-build.stderr\`, but not the executable OCI image or APK bytes. Research code/CI run only on non-PR scratch branch \`cert-a19-byte-audit-run\`; this durable documentation belongs to unmerged Draft PR #275.

## 2. Actual apko base-image lock and final OCI composition

This test used **\`contents.baseimage.image\`** pointing to an OCI layout assembled exclusively from saved source-verified base config/layers, and **\`contents.baseimage.apkindex\`** pointing to the original package-install records extracted from that signed base. This is different from R23 \`build-minirootfs\`: R24 uses \`apko lock\`, then **\`apko build --lockfile\`** with exact local signed index and pinned APK files. The OCI build produced one new layer appended to the 11 original base layers; all base-layer digest entries were verified as the output's unchanged prefix. Actual output OCI was never started/executed and was removed in cleanup.

| Observed field | Value |
|---|---|
| Base installed database packages | **19** |
| Exact frozen APK source files verified | **36/36** |
| Actual apko overlay lockfile newly selected entries | **21** |
| Final combined installed package identities | **40** (19 base + 21 new) |
| Original base OCI layer count | **11** |
| Final output OCI layer count | **12** |
| Base layer original digests retained as identical prefix | **YES** |
| Final ephemeral OCI \`index.json\` SHA-256 | \`01e6cf8b16677f72b4ac75e4bb3fd21315aff46406f9f9b2c49e49da13e26b5c\` |
| Final installed DB path | \`usr/lib/apk/db/installed\` |
| Final installed DB size | **130,238 bytes** |
| Final installed DB SHA-256 | \`a1431328059280c1b6f99c4547f7b84f63d66bdb8ed16b81b024c33ed13fcea5\` |

The 21 new actual lockfile entries are \`c-ares\`, \`gdbm\`, \`icu78-data-full\`, \`libbz2-1\`, \`libexpat1\`, \`libffi\`, \`libstdc++\`, \`libicu78\`, \`libnghttp2-14\`, \`libuuid\`, \`libuv\`, \`mpdecimal\`, \`ncurses-terminfo-base\`, \`ncurses\`, \`nodejs-24\`, \`py3-pip-wheel\`, \`xz\`, \`readline\`, \`sqlite-libs\`, \`python-3.12-base\`, \`python-3.12\`. All were taken from the frozen R18 closure. The other 15 members of the requested 36 were already present among the signed base's 19 packages at the selected versions, not silently omitted.

### Exact final-layer collision and loader observations

| Source of old concern | Measured final OCI layer result | Verdict |
|---|---|---|
| \`usr/bin/clear\` signed-base BusyBox symlink vs pinned ncurses file | The **new layer 11** delivers a real **17,208-byte regular file** at \`usr/bin/clear\`; exact SHA-256 \`98011ef86e4d2985ccc4d4a4e529c7790d1cc2e2f94ffa3296d4dc17f51377ed\`, the expected ncurses binary | **PASS** as OCI layer filesystem resolution |
| \`usr/lib64\` signed base/baselayout symlink vs libffi directory | Final OCI layer 11 records \`usr/lib64\` as a **directory**, with no missing name/target | **PASS** static resulting type; this differs from the package-only R23 final symlink and shows why actual base-overlay tests matter |
| \`/lib64/ld-linux-x86-64.so.2\` | Signed base \`lib64 -> usr/lib\` is retained, linking to \`usr/lib/ld-linux-x86-64.so.2\` in **base layer 0**. Final loader file is **272,272 bytes**, SHA-256 \`2b1529d949956d0913dce1809976adf339adc0d992de5ae6eba21dad0fa9fb09\` | **PASS** static path and exact loader bytes |
| Actual installed DB | New layer 11 \`usr/lib/apk/db/installed\` contains **40 distinct package names** | **PASS** in recorded contents |

**Important nuance:** passing these observations means the OCI overlay's file and package metadata matched exact expected digests, **NOT** that runtime dynamic loader relocation, symlink order under a live kernel, CA/NSS/TLS resolution, or arbitrary code isolation was proven. The final ephemeral image was not imported into a container engine to run the target binaries, installed on a server or published to a registry.

## 3. Remaining warnings and independent security gates

During the successful build, apko emitted warnings that \`/etc/passwd\`, \`/etc/group\`, and \`/etc/os-release\` were unavailable **in its build-context view**. R24 did not establish whether these paths are readable in the final composed OCI namespace; this is a **separate explicit non-pass preflight**, not a basis for claiming full OS environment readiness.

No four-language fixture or ABI runtime test occurred. TypeScript 5.9.3 and Wasmtime 49.0.0 source artifacts from R19 were NOT installed as part of this R24 base/36-APK runtime foundation. No independent modern npm/PyPI publisher attestation was added. Original signed APKINDEX uses legacy SHA-1 Q1 compressed-control binding (with its documented collision-resistance caveat) even though all selected exact archive full SHA-256 values were rechecked.

**Hard DENY preserved:** \`A6_INDEPENDENT_HOST_CERTIFICATION_REQUIRED\` is still the runtime fence. Independent rootless OCI+gVisor security certification for unknown user code, full language fixture behavior/parity, OS environment, policy tests, whole-image SBOM/scanning and the original **199 Critical/High findings (18 Critical +181 High)** remain open. **0 CVEs** were certified closed/waived. No historical A11 372-lock changes, A2/A15/A18 package/source edits, \`main\` edits, production deploy, Telegram/TELMIVO/broker/trading actions, user code execution, or PR merge.

**Recommended CERT-A19-R25:** prove final OCI merged-path OS identity, user/group, NSS and trust bundle from the R24 source-frozen base+overlay at static inspect level, then prepare a separately authorized, safe developer-only benign four-language fixture equivalence run with strict host boundary and Node 18→24 comparison. The test image can be rederived from exact source pins if needed; never reuse short-lived GitHub artifact beyond retention or claim the experimental OCI is production signed. A6 remains DENY until independently certified host security.

**Final R24 verdict:** \`CERT_A19_R24_SIGNED_WOLFI_BASE_APKO_LOCKED_OCI_OVERLAY_40_PACKAGES_3_PATHS_PASS__RUNTIME_HOST_NOT_CERTIFIED_A6_DENY_199_OPEN\`.
