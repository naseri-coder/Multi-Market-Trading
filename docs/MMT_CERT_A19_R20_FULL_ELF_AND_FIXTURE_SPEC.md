# CERT-A19-R20 — Full 36-Package Wolfi ELF Static Inventory and Loader-Path Decision

**Status:** \`CERT_A19_R20_36_APK_150_ELF_STATIC_INVENTORY_PASS__DYNAMIC_LOADER_PATH_UNPROVEN__A6_DENY_199_OPEN\`
**Type:** Nonproduction, read-only custody + analysis. **Not a fully functional Worker or approved deployment.**
**Date:** 2026-10-14/15 UTC.
**Original baseline:** main \`dccfe791f465040cc87d210c0ca33fad44f654ae\` unchanged.
**Draft audit-only PR:** #275. Keep DRAFT and unmerged.

## 1. Actual hosted run and complete evidence

- Dedicated isolated non-PR, nonproduction **SUCCESS**: https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38646520589, job 116134606059. The workflow runs only on a guarded path on \`cert-a19-byte-audit-run\`, not broad PR CI, not production.
- Artifact: \`cert-a19-r20-36-apk-all-elf-static-audit\`, ID **11932642207** (2-day retention), contains ONLY \`r20-static-all-elf.json\`, no downloadable executable archives.
- Actual JSON SHA-256, independently recalculated from downloaded artifact: **\`72cd119a29ad364cb5cce4eb5e7536783582ccc4a7f4ecf98905f61972fc542b\`**, original 87,927 bytes.
- The run restored exact historic R18 36-package report SHA-256 \`78356a69bf4c7aa50856450b1b4f55f9aaaf4909072891909a9fe73697fd139b\`, R19 report SHA-256 \`aeacd3dee432ebbebd2bf3b94f41b13aff5c94bd7eb34dcd16814ad4c6166d55\`, and original R17 signed Wolfi repository APKINDEX SHA-256 \`8011fbdaf70278ae83e3729dc2c44a8148a91cf03ea0ef7a3d049e30a65e36a5\`; all matched exact frozen bytes **before** any package fetch.
- Downloaded all **36 exact apko solver-selected APK files**, in a bounded x86-64-only disposable GitHub-hosted job. **36/36 full APK SHA-256** matched the R18 research manifest; **36/36 compressed payload \`.PKGINFO datahash\` SHA-256** matched, without installing or executing target packages. Total archive bytes **73,750,485**. Full provenance from R18 remains legacy signed-index Q1 SHA-1 and signed-control-bound SHA-256 data; no separate modern per-APK signature is claimed.
- Parsed the compressed tar payloads *as data only*, including all regular files, symlinks and hardlink metadata. For every ELF magic-header regular file, executed only host-trusted \`readelf --wide -h/-d/-V/-l\` (not target runtimes, not the ELF interpreter). Current readelf semantics: https://sourceware.org/binutils/docs/binutils/readelf.html .

## 2. Grounded inventory and observations

| Evidence measure | Observed |
|---|---:|
| Exact R18 APK closures re-downloaded and pinned | **36 / 36** |
| Regular archive files enumerated | **1,934** |
| Symbolic-link entries inventoried | **75** |
| Hard-link entries inventoried | **0** |
| All discovered ELF64 x86-64 files statically inspected | **150** |
| Observed requirements newer than GLIBC_2.44 | **0** |
| Max ELF requirement seen | **GLIBC_2.44** |
| DT_NEEDED library names with **no filename/SONAME candidate at all** | **0** |
| DT_NEEDED names with multiple filename candidates (often an alias plus a versioned shared object) | **27** |
| Missing literal ELF interpreter path | **1 distinct path**, referenced by **17 ELF files** |
| External R19 Wasmtime wheel ELF's NEEDED names lacking a candidate in the 36-APK filename inventory | **0** |

**Important qualifier on 27 multiple matches:** the name-based static check intentionally records both a symlink such as \`libfoo.so.1\` and its versioned target \`libfoo.so.1.x\` where applicable. Those are NOT 27 independently proven conflicting libraries or attacks; they are **27 names where a simple basename/SONAME inventory cannot uniquely establish final loader resolution**. Further symlink-target and soname mapping is required, without inferring a dynamic link PASS.

**Actual hard remaining blocker:**
- Exactly **\`/lib64/ld-linux-x86-64.so.2\`** was **not present at that literal path in the extracted 36-package combined static file inventory**, while **17 ELF entries request that interpreter**, including \`usr/bin/node\`, \`usr/bin/python3.12\` and other packaged executables.
- The requisite loader is linked to the pinned \`ld-linux-2.44\` component through the distribution's standard library layout; **but the final rootfs layout or an independently proved \`/lib64\` alias is not present in this static archive graph**. The issue is therefore an **image-composition / loader-path certification gap**, NOT proof that glibc or Node binaries are intrinsically incompatible. Do not repair by silently changing the historical A2/A15/A18 Dockerfiles.
- Static scan does not simulate the Linux loader's exact search order or resolve all local symlink chains, versioned symbols, relocations, \`RPATH/RUNPATH\`, \`dlopen\` behavior or ABI execution.
- The supplementary Wasmtime \`_libwasmtime.so\` evidence from R19 was compared by NEEDED **name only**, **not actually inserted as a file in the frozen 36-APK filesystem**. Wasmtime Python wheel and TypeScript tarball are separately bounded research artifacts and are **NOT** installed here.

### Distribution of ELF files by selected APK (nonzero values)

| APK | ELF count |
|---|---:|
| \`python-3.12-base\` | 75 |
| \`glibc-2.44\` | 18 |
| \`ncurses\` | 17 |
| \`gdbm\` | 5 |
| \`xz\` | 5 |
| \`libicu78\` | 4 |
| \`openssl-provider-legacy-allowed\` | 3 |
| \`mpdecimal\` | 2 |
| \`readline\` | 2 |
| Each of the other nonzero ELF packages | 1 |

Counts above summarize examples and package families only; the complete per-package counts for all **36** and per-file \`DT_NEEDED\`, \`DT_SONAME\`, interpreter, \`RPATH/RUNPATH\`, highest required glibc and SHA-256 are in the **immutable R20 JSON**. No executable payload was run, imported or published as an OCI image.

## 3. Four-language fixed-harmless-fixture acceptance contract (SPEC ONLY, NOT EXECUTED)

Authoritative Worker source: \`scripts/runtime_a2_worker.py\` at main, SHA blob \`0c21b87b77604c4025b8ea44ba35a24664c1537b\`. It accepts framed ABI 1.0 requests, with exactly nine keys \`{abi_major,abi_minor,protocol,runtime_kind,artifact_sha256,manifest_digest,manifest,input_digest,event}\`, \`protocol=RUNTIME_A1_FRAMED_V1\`; inputs must have verified digests and synthetic/replay origin, and return a nonempty list of up to twelve decisions. Actual Worker retains a hard precondition for independent rootless/gVisor host confinement.

**Future fixed developer-only harmless vectors (not executing here):**
1. Python: fixed audited function \`evaluate(event)\` returns \`[{"fixture_only":true}]\` independent of input, without imports, side effects, network or filesystem operations.
2. JavaScript: fixed audited \`evaluate(event)\` function returns the same single inert decision object. Node18→Node24 difference and VM semantics are an independent comparison gate.
3. TypeScript: same fixed function with a static \`event\` type annotation, transpilation under TypeScript 5.9.3 and exact output equivalence. No async imports, \`require\`, network, package fetches or dynamic code.
4. WASM: reviewed and hash-pinned tiny deterministic compiled module with **no imports**; exports \`memory\` and \`evaluate(ptr,len)\` in the exact ABI expected by the current Worker, returning the one inert decision JSON payload at a bounded memory offset. **No canonical byte sequence/hash is invented here; block this fixture until independent source-to-bytes review and pinned hash are produced.**
5. Negative controls: wrong artifact/event/manifest digest, duplicate JSON field, unrecognized kind, UTF-8 invalid artifact, rejected float, 65,537-byte artifact, output decision not a list, outputs beyond 12 decisions, bad WASM ABI. The current code's actual size/frame rules must determine exact expected rejection codes; no source changes authorized for R20.
6. Match the original A2 contract's result envelope and deterministic identity fields, compare canonical bytes for accepted fixtures and exact refusal categories for negative cases. Never compare live market PnL or "optimize" fixtures to pass.
7. Execute any future fixtures only in separately approved disposable host confinement with **network disabled, read-only filesystem, Linux capabilities dropped, tight CPU/RAM/PID limits, and independent rootless+gVisor review**; running fixed benign fixtures does NOT unlock A6 for unknown user input.

These vectors are a **reviewed plan**, not a validated four-language test report. Do not call any language PASS in R20.

## 4. Fail-closed release barriers / exact next step

| Gate | Result |
|---|---|
| Exact historical 36-apk bytes/metadata preserved and reverified | **PASS** |
| **All** ELF present in the 36-package archive closure inventoried and statically inspected | **PASS** |
| No missing DT_NEEDED basename candidate | **PASS in filename/SONAME scope only** |
| Actual resolved interpreter /lib64/ld-linux-x86-64.so.2 in final filesystem | **NOT PROVEN: 17 ELF requests** |
| Unique loader search and all symlink target resolution | **NOT PROVEN** |
| Correct final Python/Node/TypeScript/Wasmtime ABI and behavior | **NOT RUN** |
| Independent rootless/gVisor host and untrusted guest isolation | **NOT CERTIFIED** |
| Modern per-archive cryptographic origin and SHA-1 threat review | **NOT COMPLETE** |
| 199 original Critical+High scanner findings | **REVIEW-OPEN**; 0 closed |
| Production / merging Draft PR | **DENIED** |

**R20 verdict:** \`CERT_A19_R20_36_APKS_150_ELFS_STATIC_PASS__LOADER_LIB64_PATH_NOT_PROVEN__NO_RUNTIME_A6_DENY_199_OPEN\`.

**Recommended R21:** map exact Wolfi \`ld-linux-2.44\` and \`wolfi-baselayout\` symlink semantics, possible \`/lib64\`/usr-merge path and all SONAME aliases from the **frozen archives**, build a **nonproduction static rootfs plan** with provenance and fail-closed loader-path assertions. Then separately gate a fixture-only, independently sandboxed compatibility execution authorization. No production, source mutation, Worker activation, CVE suppression or PR merge before the stronger host and original A6 certification.
