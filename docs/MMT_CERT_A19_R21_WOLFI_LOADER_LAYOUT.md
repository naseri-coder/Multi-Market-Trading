# CERT-A19-R21 — Signed Wolfi Base + Full 36-APK Static Loader Path Resolution

**Research status:** \`CERT_A19_R21_STATIC_INTERPRETER_FOUND_IN_SIGNED_BASE_AND_FROZEN_APK_SET__COMPOSITION_COLLISIONS_AND_RUNTIME_BLOCKED\`
**Date:** 2026-10-14/15 UTC hosted Actions.
**Production:** DENIED — NO MERGE, NO WORKER/IMAGE BUILD, NO RUNTIME UNLOCK.
**Original main:** \`dccfe791f465040cc87d210c0ca33fad44f654ae\`, unchanged.

## 1. Real R21 experiments

1. [Run #38648065313](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38648065313) **FAILED** at the first static Docker-export TAR inventory because the initial parser intentionally rejected special entries (e.g. device/FIFO metadata). This is a parser strictness issue, **not** failed signature verification or missing ELF loader. The verified signed OCI source was obtained but no archive/path verdict produced.
2. [Run #38648206711](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38648206711) **SUCCESS** after narrowly accepting special TAR entries as **metadata only**, without creating, installing, mounting device nodes or executing container code. Original loader-path tests and all provenance/ABI stop-gates were retained.
3. Exact GitHub Actions artifact: \`cert-a19-r21-signed-rootfs-loader-path-static\`, ID **11932744568**, 2-day retention, \`r21-static-rootfs-path.json\`. Independently unpacked JSON SHA-256: **\`8ccc6f9a02a373d2262dad6e9ebd9d3bf07b523fa850bbb82e83e2d1591847e8\`** (5,370 bytes). The artifact contains provenance and symlink information only, not a rootfs, image, APK files or executables.
4. Original immutable evidence was restored and compared **before** any network access: R18 full 36-package proof SHA-256 \`78356a69bf4c7aa50856450b1b4f55f9aaaf4909072891909a9fe73697fd139b\`; R20 150-ELF static report SHA-256 \`72cd119a29ad364cb5cce4eb5e7536783582ccc4a7f4ecf98905f61972fc542b\`; historic R17 native-accepted signed \`APKINDEX.tar.gz\` SHA-256 \`8011fbdaf70278ae83e3729dc2c44a8148a91cf03ea0ef7a3d049e30a65e36a5\`.
5. Reverified exact immutable Wolfi-base Sigstore publisher identity via \`cosign verify\`: \`cgr.dev/chainguard/wolfi-base@sha256:256c88bb066424045021090932d50be93c8e3f2ce3586707702a401b146f3e43\` with \`https://github.com/chainguard-images/images/.github/workflows/release.yaml@refs/heads/main\` and \`https://token.actions.githubusercontent.com\`. A container was **created but NEVER started**, and \`docker export\` of this public base was used solely to read static file/link metadata. Export TAR: **18,548,224 bytes**, **421 inventory entries**, including 4 special device/FIFO entries observed as metadata only. No \`docker run\` or \`docker start\`.
6. All **36** pinned R18 \`.apk\` archive files were re-downloaded (**73,750,485 original bytes**) and checked against their exact historical whole-file SHA-256 plus compressed \`.PKGINFO datahash\`. The resulting package-only graph contained **2,224 entries**. A synthetic **static union inventory** with the signed base contained **2,495 entries**. This was a Python dictionary of metadata, **NOT a built, installed, verified or executable OCI rootfs**.

## 2. Concrete loader path — R20's apparent missing path explained

R20 had flagged a missing exact literal file path \`/lib64/ld-linux-x86-64.so.2\`, requested by **17 ELF files** including Node.js 24 and Python 3.12. R21 followed the actual symlinks through both proven historical sources rather than doing a literal pathname lookup:

| Source | \`/lib64\` entry | Resolved path | Terminal file |
|---|---|---|---|
| Signed, stopped Wolfi base | Symlink with raw value **\`usr/lib\`** | \`/usr/lib/ld-linux-x86-64.so.2\` | Present, **272,272 bytes** in signed base |
| Frozen \`wolfi-baselayout=20230201-r30\` APK | Symlink with raw value **\`usr/lib\`** | \`/usr/lib/ld-linux-x86-64.so.2\` | Present, **272,272 bytes**, supplied by pinned \`ld-linux-2.44=2.44-r8\` APK |
| Naive combined static metadata inventory | Symlink \`/lib64 -> /usr/lib\` | \`/usr/lib/ld-linux-x86-64.so.2\` | Present, but metadata union retained the existing base file, not proof of final installation order |

**Proof:** the **missing-path diagnosis in R20 is resolved at the level of static source files and link targets**. Both authenticated sources independently contain a valid chain to an ELF-loader *file*. The ELF interpreter was not invoked, its machine code was not executed, and file-content parity of the two 272,272-byte loaders was **not established** merely by equal size. **Do not claim the final runtime loader/ABI is certified.**

## 3. Two concrete rootfs composition conflicts requiring review

1. **Signed-base versus package collision:** \`usr/bin/clear\`. The signed base contains a symlink to **\`/bin/busybox\`**, while pinned \`ncurses=6.6.20261010-r0\` contains a **regular file of 17,208 bytes** at the same location. Replacing a BusyBox utility with a full version may be normal, but static TAR dictionary union does **not** prove the actual package installation's overwrite policies, relative symlink resolution or final resulting bytes. This must be explicitly resolved in a controlled package-composition plan.
2. **Conflicting metadata inside the set of selected APKs:** \`usr/lib64\` is recorded as a **directory** from \`libffi=3.8.0-r2\` and a **symlink** with target **\`lib\`** from \`wolfi-baselayout=20230201-r30\`. This can be sensitive to extraction/installation order and layout semantics. It must be adjudicated with a verified package manager / apko filesystem-composition procedure. Never simply replace a symlink with a directory or guess the winner.

The first is exactly **1 base-vs-package file-type collision**; the second is exactly **1 package-to-package file-type collision**. Neither observation alone proves malware or runtime incompatibility. The archive-to-base static union is deliberately *not* accepted as an actual final rootfs, and the report's conservative \`LOADER_PATH_STILL_BLOCKED_OR_UNION_COLLISION\` reflects the unresolved composition even though the **interpreter path itself is proven in both source graphs**.

**Additional restrictions:** R20 recorded 27 multi-candidate DT_NEEDED names (many are symlink aliases to versioned objects), but R21 did **not** certify dynamic loader search order, symbol relocation or resolve every pair against a materialized final rootfs; no false “27 library conflicts” claim is made. The Wolfi base's already present loader file cannot automatically be treated as byte-identical to the pinned \`ld-linux-2.44\` package; this byte comparison is an open future proof obligation.

## 4. Safe fixed four-language test plan remains gated

The R20 contract for fixed, developer-authored benign Python, JavaScript, TypeScript, and WebAssembly fixtures still stands only as a **SPEC**. No canonical Wasm module bytes or digest have been fabricated. No TypeScript code compiled, Wasmtime module executed, Python/Node runtime imported or target binary executed in R21. No guest strategy was processed.

Even a successful future benign fixture experiment on an independently controlled disposable runner **does not authorize** unknown-user code execution absent independent rootless/gVisor confinement certification. The A6 denial must be preserved until independently approved.

## 5. Closure and proposed R22

**R21 narrowly demonstrated:** a concrete, byte-sourced reason the original literal R20 loader path appeared missing. Both signed base and frozen package-root metadata have \`/lib64 -> usr/lib\` resolving to \`usr/lib/ld-linux-x86-64.so.2\`, a present file. **The repository remains blocked for final runtime build/certification because actual package composition has not been proven**.

**Recommended R22:** independently compare raw SHA-256 of the base and pinned loader binaries, check exact symlink/file overwrite policies in the immutable apko 1.4.11 provenance already authenticated, and produce a **nonproduction rootfs-composition collision decision** for \`usr/bin/clear\` and \`usr/lib64\` — without assembling an executable Worker, changing A11/A2/A15/A18 locks or violating RUNTIME-A6. Any future fixed-harmless-fixture execution requires separate reviewed sandbox/host authorization.

**No changes** to main, production, broker, Telegram, TELMIVO, trading algorithms, image hashes, old Debian A11 372-item pin, RUNTIME-A6 hard DENY, or original **199 REVIEW-OPEN** Critical/High security findings; **0 CVEs** closed/suppressed; PR #275 stays **DRAFT / DO NOT MERGE**.

**R21 evidence-based verdict:** \`CERT_A19_R21_STATIC_LOADER_LINK_PROVEN_IN_BASE_AND_36_APKS__TWO_ROOTFS_COMPOSITION_COLLISIONS_OPEN__NO_RUNTIME_A6_DENY_199_OPEN\`.
