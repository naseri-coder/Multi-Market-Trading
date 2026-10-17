# CERT-A19-R22 — Byte-Identical Wolfi ELF Loader and apko v1.4.11 Filesystem Collision Contract

**Research verdict:** \`CERT_A19_R22_SIGNED_BASE_VS_PACKAGE_ELF_LOADER_SHA256_PARITY_PASS__TWO_ROOTFS_COMPOSITION_CONFLICTS_UNRESOLVED__A6_DENY_199_OPEN\`

**Scope:** evidence-only investigation. **No apk/apko installation, no filesystem mutation, no build, no Worker/target ELF/guest execution, no deployment, no PR merge, no changed A6, no CVE waivers.**

## 1. Hosted proof and pinned trust anchors

- [Dedicated, non-PR R22 Actions run #38649169689](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38649169689): **SUCCESS**, one limited CI job on \`cert-a19-byte-audit-run\`. No broad PR tests. This is a successful **audit workflow**, not a passed runtime-composition qualification.
- Exact signed public Wolfi OCI base: \`cgr.dev/chainguard/wolfi-base@sha256:256c88bb066424045021090932d50be93c8e3f2ce3586707702a401b146f3e43\`. \`cosign verify\` enforced \`https://github.com/chainguard-images/images/.github/workflows/release.yaml@refs/heads/main\` issuer \`https://token.actions.githubusercontent.com\`. It was \`docker create\` + \`docker export\` only; the container was **NEVER STARTED**.
- R18 verified 36-APK closure, original result JSON SHA-256 \`78356a69bf4c7aa50856450b1b4f55f9aaaf4909072891909a9fe73697fd139b\`; R21 proof JSON SHA-256 \`8ccc6f9a02a373d2262dad6e9ebd9d3bf07b523fa850bbb82e83e2d1591847e8\`. Both were restored from **their exact historical GitHub Actions artifacts** and rehashed before research.
- Original independently accepted Wolfi signed \`APKINDEX.tar.gz\` bytes SHA-256 \`8011fbdaf70278ae83e3729dc2c44a8148a91cf03ea0ef7a3d049e30a65e36a5\`. **No live mutable index substituted**.
- All 4 needed Wolfi archives \`ld-linux-2.44\`, \`ncurses\`, \`libffi\`, and \`wolfi-baselayout\` were downloaded with their exact R18 observed whole \`.apk\` SHA-256 and checked against compressed control/data byte hashes and \`.PKGINFO\` identities. None was installed or executed.
- **R22 artifact:** \`cert-a19-r22-loader-byte-parity-and-collision-review\`, GitHub artifact ID **11933641716**, two-day retention. Exact \`r22-loader-and-conflicts.json\` payload **6,588 bytes**, SHA-256 **\`41cefc3fc5e72ca023b3f915b5605b9dd950f24860d313c37de56309d67efec7\`**. Only JSON evidence was uploaded (no archived loader binary, OCI export, source executable, package or image).
- R18 \`apko 1.4.11\` release had separately passed authenticated release SHA/signature and \`GitCommit 5b3c3182430465dd2212a656411267f150034255\`. R22 downloaded **only** source text from the pinned exact commit and verified Git blob SHA-1 via \`git hash-object\` before inspecting installation rules; no apko executable was run in R22.

## 2. Previously unproven question: are base and pinned APK ELF loaders identical?

**YES — full SHA-256 parity on each exact 272,272-byte ELF, not just file length.**

| Independently authenticated source | File | Bytes | Full ELF SHA-256 |
|---|---|---:|---|
| Sigstore-signed, stopped Wolfi base export | \`usr/lib/ld-linux-x86-64.so.2\` | 272,272 | \`2b1529d949956d0913dce1809976adf339adc0d992de5ae6eba21dad0fa9fb09\` |
| R18-pinned \`ld-linux-2.44=2.44-r8\` APK | \`usr/lib/ld-linux-x86-64.so.2\` | 272,272 | \`2b1529d949956d0913dce1809976adf339adc0d992de5ae6eba21dad0fa9fb09\` |

Both sources have ELF magic. Both source files are independently observed behind the \`/lib64 -> usr/lib\` link proven in R21. **This closes only the file-content parity question.** It does not prove that the final rootfs's symlink and loader files survive package composition; no program/dynamic loader was executed, no ABI symbols relocated, and no final image created.

## 3. Version-verified apko v1.4.11 source collision handling

The exact \`apko\` v1.4.11 release Go source was frozen by immutable commit and Git blob custody:

- [\`pkg/apk/apk/install.go\`](https://github.com/chainguard-dev/apko/blob/5b3c3182430465dd2212a656411267f150034255/pkg/apk/apk/install.go), Git blob SHA-1 \`627e6aae37100935e7b298874e224e26d3311a1f\`, source SHA-256 \`550a214c235aba83f0d089b0439d7d4024645e6cd57f4da0af3dd59ebc65d344\`.
- [\`pkg/apk/apk/implementation.go\`](https://github.com/chainguard-dev/apko/blob/5b3c3182430465dd2212a656411267f150034255/pkg/apk/apk/implementation.go), Git blob SHA-1 \`588398c9bf71aae2c43bfb167500d5746b87ea64\`, source SHA-256 \`dac79dbe25afa0daa6e727453b62ffb9b6c7254c360538def0e6ff66bcb215c2\`.

Static source inspection of this exact version (NOT a successful actual install) found:
- \`installRegularFile\` compares existing content checksum. Overwrite of a different file depends on **matching package origin or an explicit \`replaces\` relationship**; there are additional checks on registered file ownership and the existing installed-state database. A broad \`cp\` or TAR overlay does not replicate that policy.
- An existing symlink to a directory can be accepted for a directory TAR header **only when filesystem checks confirm the link target is a directory**.
- An already-existing symlink with an identical target can be left alone; otherwise symlink creation invokes the filesystem's \`Symlink\` operation, whose result depends on state and order.
- \`wolfi-baselayout\` provides \`merged-lib\`; the source has explicit handling for the usr-merged base layout. These are generic mechanisms, **not evidence they succeed for this exact 36-package + base composition**.
- \`FixateWorld\` checks resolver conflicts and can refuse package installation. R18's solver package list succeeded, but R22 did NOT run \`FixateWorld\` or install anything.

R22 validated the seven expected source guard patterns against the real SHA-pinned Go source files. There was no dynamic package manager execution, file install or final rootfs creation.

## 4. Actual package metadata and conflict provenance

### Collision A — \`usr/bin/clear\`

| Observed source | Type/target | Integrity |
|---|---|---|
| Signed stopped Wolfi base | Symlink \`/bin/busybox\` | Source is the signed image |
| R18-pinned \`ncurses=6.6.20261010-r0\` | Regular ELF **17,208 bytes** | Full file SHA-256 \`98011ef86e4d2985ccc4d4a4e529c7790d1cc2e2f94ffa3296d4dc17f51377ed\` |

The \`ncurses\` package metadata gives \`origin=ncurses\`, **no \`replaces\` value**. It cannot be assumed that overwriting the signed base's BusyBox symlink is automatically authorized; exact base-package ownership, overwrite policy, install state and package sequencing would be needed for proof. R22 performs **no substitution** and reports a continuing composition decision gate.

### Collision B — \`usr/lib64\`

| Observed source | Type/target | Integrity |
|---|---|---|
| Signed stopped Wolfi base | Symlink \`lib\` | Sigstore-verified base export |
| R18-pinned \`libffi=3.8.0-r2\` | Directory | \`origin=libffi\`, no \`replaces\` |
| R18-pinned \`wolfi-baselayout=20230201-r30\` | Symlink \`lib\` | \`origin=wolfi-baselayout\`, no \`replaces\`, advertises \`merged-lib\` |

The pinned apko source **conditionally** accepts a directory header when the existing symlink resolves to a directory, and conditionally accepts an existing symlink with the exact same target. These observations suggest a plausible non-conflicting installation path **if install order, actual filesystem semantics and symlink resolution are as expected**. They **do not prove** that this exact package set and base compose successfully. No winner or changed link is invented.

### Collision and trust disposition

- **PASS:** exact base/APK loader ELF full SHA-256 parity, legacy index-linked package-byte custody, and official v1.4.11 apko source-rule provenance.
- **OPEN:** final installed file at \`usr/bin/clear\`, package-installed \`usr/lib64\` semantics, install order, original base package ownership, final \`/lib64/ld-linux-x86-64.so.2\` after composition, dynamic-loader behavior and actual four-language ABI.
- No claim that either collision is a vulnerability, impossible combination, or resolved simply by observing source code.
- The previously reported legacy signed APKINDEX \`C:Q1\` SHA-1 collision-resistance caveat remains, as do publisher-attestation limitations for npm TypeScript / PyPI Wasmtime.

## 5. Final R22 restrictions and next safe gate

**DO NOT:** merge PR #275, modify \`main\`, touch A11 372-item Debian lock or A2/A15/A18 existing worker sources/images, create/ship a Worker, deploy/restart production systems, execute user code, bypass A6, or close/suppress CVEs. The original **18 Critical + 181 High = 199** findings remain review-open, **0 CVEs certified fixed**. RUNTIME-A6 retains \`A6_INDEPENDENT_HOST_CERTIFICATION_REQUIRED\` hard DENY.

**Next R23 recommendation:** a **separate scoped nonproduction, no-guest-code filesystem-composition qualification** using verified \`apko v1.4.11\`, exact frozen R18 index and archive SHA pins, with proper package manager install rules, deterministic file-state and ownership records for \`usr/bin/clear\` and \`usr/lib64\`, and final ELF loader path+full-file SHA checks. Only if its package manager can safely compose an inert rootfs should a later, separately reviewed benign-fixture-only runtime test be considered. Never infer secure sandboxing from a successful installer test.

**R22 verdict:** \`CERT_A19_R22_LOADER_SHA256_BASE_PACKAGE_IDENTICAL__SOURCE_PINNED_APKO_COLLISIONS_STILL_OPEN__A6_DENY_199_OPEN\`.
