# CERT-A19-R23 — Actual Signed apko Package-Only Minirootfs Composition, With Base Overlay Still BLOCKED

**Final limited verdict:** \`CERT_A19_R23_36_APK_PACKAGE_ONLY_MINIROOTFS_COMPOSED_LOADER_AND_LIB64_PASS__SIGNED_BASE_OVERLAY_CLEAR_COLLISION_UNVERIFIED__A6_DENY_199_OPEN\`
**Scope:** disposable nonproduction file-system composition, not a Worker image, not a production runtime, not independent sandbox certification.
**Baseline:** unchanged \`main\` \`dccfe791f465040cc87d210c0ca33fad44f654ae\`; Draft PR #275 unmerged.

## 1. Valid completed hosted experiment

- [GitHub Actions run **38650418247**](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38650418247), on isolated \`cert-a19-byte-audit-run\` branch at commit \`d5c00d9697d10422f3bb159e57c7c00a14d92fa7\`: **SUCCESS**, one job. Workflow \`.github/workflows/cert-a19-r23-minirootfs.yml\` and research script \`scripts/ci_cert_a19_r23_package_composition.py\`.
- Exact R18 original signed APKINDEX compressed bytes SHA-256 \`8011fbdaf70278ae83e3729dc2c44a8148a91cf03ea0ef7a3d049e30a65e36a5\`, full 36-package evidence JSON \`78356a69bf4c7aa50856450b1b4f55f9aaaf4909072891909a9fe73697fd139b\`, and R22 loader/collision report \`41cefc3fc5e72ca023b3f915b5605b9dd950f24860d313c37de56309d67efec7\` were restored from immutable GitHub artifacts and SHA checked before use.
- Signed immutable Wolfi base image was only verified for publisher identity and used to copy public package-signing keys without starting it. **The Wolfi base root filesystem was NOT included in the mini-rootfs build.**
- Verified official apko **v1.4.11** Linux/amd64 release tarball whole SHA-256 \`5445ea2467a4ab0db3e31d9f795133128d0564c7afdaa46fcdaa1ee3cf92c757\` AND exact Sigstore release signer identity/issuer before executing the apko builder. The package manager ran in a constrained container with \`--network=none\`, read-only root, dropped capabilities, no-new-privileges and unprivileged user; only a writable scratch mount.
- **36/36** exact R18 package archive bytes, **73,750,485 total input bytes**, re-downloaded and checked against full-file SHA-256, archived authenticated package index, package control and data digests. A local repository with **only** these frozen artifacts was passed to apko.
- The verified apko **build-minirootfs** operation performed actual package-manager installation into a **disposable package-only tar filesystem**, with no installed Worker, TypeScript/Wasm payloads, production deployment, unknown user strategy, code evaluation or published OCI image. The runner then inspected the output **as data only**. The generated rootfs tar was not attached as evidence and an explicit cleanup step completed successfully.

### Measured package-only output

| Measure | Real observed value |
|---|---|
| Exact packages in installed DB | **36/36 PASS** |
| Mini-rootfs artifact bytes | **195,088,384** |
| Mini-rootfs SHA-256 | \`57a8db08358aadfd98877806bdea97f9d6d70ab31eb7d856126d4d20c3df2b63\` |
| Mini-rootfs tar entries | **2,257** |
| ELF loader request \`/lib64/ld-linux-x86-64.so.2\` | link \`lib64 -> usr/lib\` resolves to real file \`usr/lib/ld-linux-x86-64.so.2\` |
| Resolved loader file size | **272,272 bytes** |
| Loader whole SHA-256 | **\`2b1529d949956d0913dce1809976adf339adc0d992de5ae6eba21dad0fa9fb09\`** — matches R22 base and pinned package |
| \`/usr/lib64\` | link \`usr/lib64 -> lib\`; resolves to \`usr/lib\`, a directory |
| \`/usr/bin/clear\` | final regular ELF from \`ncurses\`, 17,208 bytes, SHA-256 \`98011ef86e4d2985ccc4d4a4e529c7790d1cc2e2f94ffa3296d4dc17f51377ed\` |

**Interpreting the two former collisions correctly:**
- The **package-to-package** \`libffi\` directory vs \`wolfi-baselayout\` symlink difference was compatible with the actual package-manager-created *package-only* filesystem: the final \`usr/lib64\` is a symlink that resolves to an actual directory, with no inventing of a file type or a manual override.
- The \`usr/bin/clear\` observed file proves that the package-only rootfs contains the pinned \`ncurses\` binary. It does **NOT** exercise replacement of the **signed base image's existing BusyBox \`clear\` symlink**; that conflict remains OPEN in a base-image overlay build.
- A valid no-execution installation of 36 packages establishes file-system composition only; it does **NOT** establish that Python, Node, TypeScript or Wasmtime execute, that dynamic linker relocations succeed, or that untrusted guest code is safe.

## 2. Original evidence preserved and independently examined

- GitHub Actions artifact **11934846299**, name \`cert-a19-r23-signed-apko-package-only-composition\`, retention 2 days. The artifact was downloaded and extracted for this report and contains:
  - \`prepared.json\` SHA-256 **\`c2d793238ecd84ef5760ae96086e3a20c5b88f02d698c6f8a18de8bec10e3f00\`**, containing all 36 actual whole-archive hashes and source metadata;
  - \`r23-package-only-rootfs.json\` SHA-256 **\`1e649d3c64bcf70769b32885dcb192b2a3789a49852f1358460284692e814435\`**, contains exact installed DB, loader, lib64, clear, and unresolved signed-base-overlay statuses;
  - \`apko-build-stderr.log\` SHA-256 **\`7bffac282c64ad25bd752148832df237ff7c83b9b9680151f629506b34e6fee7\`** for nonproduction diagnostic.
- The JSON was written during inspection, *before* the later successful workflow cleanup. Its field \`post_build_output_rootfs_deleted_in_runner=false\` is a pre-cleanup status, **not** evidence that cleanup failed; the log has a separately successful \`Delete disposable rootfs tar and package input files\` step. Nothing executable was uploaded.

### Separate, redundant follow-up diagnostic — failed without invalidating the completed run

- A later trial [run **38650936146**](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38650936146), introduced as a secondary non-PR R23 script/workflow on \`cert-a19-byte-audit-run\`, **FAILED** after it had revalidated all 36 frozen APKs. The build attempted to create an apko package cache at \`/.cache/dev.chainguard.go-apk\` inside a deliberately **read-only** container root filesystem.
- This failure is attributable to the trial's unconfigured cache location (\`mkdir /.cache: read-only file system\`); it is **not evidence of a package dependency, OCI signer or package collision failure**. The earlier independently completed package-only run remains the sole PASS basis. No additional CI reruns or broad suites are needed for R23. The secondary trial's unverified build output is NOT a certification input.
- This stage does not claim to have cancelled the second job; it completed and failed. In either case there were no changes to production or \`main\`.

## 3. Stronger base-image composition is still an explicit separate authorization gate

The authenticated source of apko v1.4.11 shows \`build-minirootfs\` builds package-only layers: it does not overlay the previously verified *existing* signed Wolfi base. The \`apko build\` path can use an experimental \`contents.baseimage\`, but its code requires a **specific OCI layout, base installed-package metadata and a consistent lockfile**. These must be independently derived and signed-source checked before any experiment could claim final base-overlay semantics. A naive tar union is NOT equivalent.

Unpassed:
1. Package-manager composition onto the exact signed base image, including known original base installed DB / file ownership, and the \`usr/bin/clear\` BusyBox link replacement decision.
2. Final base-overlay rootfs ELF loader alias and byte/hash after package manager operations, not just package-only rootfs.
3. Final runtime Python 3.12, JS Node 24, TS 5.9.3 and Wasmtime 49 ABI/execution/parity on benign fixed fixtures.
4. Independent rootless OCI+gVisor security certification, including no claims that Node \`vm\` is a security boundary.
5. Legacy SHA-1 signed APK index threat model and independent npm/PyPI publisher attestation; original **199 Critical/High issues review-open, zero CVE closures**.

**No production Worker image or strategy code executed, no registry publication, no build on production, no \`main\` edits, no A11/A2/A15/A18 rewrite, no Telegram/TELMIVO/broker/trade operations, no PR merge.** \`A6_INDEPENDENT_HOST_CERTIFICATION_REQUIRED\` remains hard DENY.

**Next R24 recommendation:** independently derive frozen base-image OCI layout plus exact base installed-package DB from the signed image, source-pin apko's experimental baseimage and lockfile paths, then make a separate disposable, no-network base-overlay composition attempt with strict digest/ownership/file-path assertions. If the original BusyBox \`clear\` symlink cannot be resolved through the package manager's documented ownership/replaces rules, fail-closed. No four-language or guest execution at that stage.

**R23 release verdict:** \`CERT_A19_R23_SIGNED_APKO_36_PACKAGES_INSTALLED_IN_EPHEMERAL_PACKAGE_ONLY_MINIROOTFS__BASE_OVERLAY_AND_RUNTIME_CERTIFICATION_DENIED__A6_DENY_199_OPEN\`.
