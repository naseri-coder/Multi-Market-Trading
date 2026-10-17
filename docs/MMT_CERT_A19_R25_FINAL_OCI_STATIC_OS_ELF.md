# CERT-A19-R25 — Final Composed Wolfi OCI: All-ELF / OS Identity / NSS / CA Static Evidence

**Final research verdict:** `CERT_A19_R25_COMPOSED_40_PACKAGE_OCI_153_ELF_STATIC_AND_OS_PATHS_PASS__TLS_TZ_RUNTIME_AND_HOST_UNVERIFIED__A6_DENY_199_OPEN`

**Nonproduction only.** No Worker, unknown strategy, trading process, TypeScript compiler, Wasmtime module, Python/Node code or user-provided executable was run; no deployment, image push, CVE waiver, PR merge or original project logic change.

## Real hosted R25 verification and exact custody

- Independent single-purpose non-PR GitHub-hosted [Actions run #38687049515](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38687049515): **SUCCESS**; scripted static audit only after re-deriving source-pinned signed Wolfi base, 36 R18 APK byte-checked inputs and locked 40-package experimental overlay from R24.
- Frozen R24 SUCCESS proof source `r24-result.json` SHA-256 `284ccd9f9549fbcd6572c442cc5f9ebf5759d4cdf5ccb419f2235bff8a3e2f61` was rehydrated from its actual completed GitHub Actions artifact, independently checked and compared to the current run's R24 static outputs. The current experimental OCI layout index SHA-256 `01e6cf8b16677f72b4ac75e4bb3fd21315aff46406f9f9b2c49e49da13e26b5c` matched this source-fixed run.
- Base source: Sigstore-verified immutable Wolfi `cgr.dev/chainguard/wolfi-base@sha256:256c88bb066424045021090932d50be93c8e3f2ce3586707702a401b146f3e43`; previously verified full publisher OIDC signer. apko `v1.4.11` original GitHub release blob signature/full digest checked before builder execution, local signed historical index and exact archive hashes from R18, package base installed DB and R24 lockfile reused.
- Completed evidence artifact: `cert-a19-r25-final-oci-static-preflight`, ID **11950214136**, short-lived two-day retention. **Only JSON and non-executable diagnostic logs were uploaded.** Actual file `r25-static-final-oci.json`: **69,645 bytes**; independently calculated SHA-256 **`26bc9c72b4b49c396a973b783764875566f24b4b2568f9495032ad9dc51f9264`**. Downloaded artifact ZIP SHA-256 `6ff0caa1770b2d7f2db86b1c886f0678e44530e7d0534242ba3a91cb98ef1818`.
- All downloaded target ELF files were **read only as byte data**. Static inspector used runner-native `readelf -h/-d/-V/-l` on temporary files, deleted them after analysis, did not run loader/target binaries. Signed builder ran as unprivileged user in a scratch no-network read-only-root container; OCI files and package inputs were removed from the ephemeral runner at successful cleanup.

## Full composed filesystem results (not just R24's three selected paths)

| Research measurement | Actual |
|---|---:|
| Installed package DB count | **40** |
| Signed base layer prefix | **11 layers** |
| Final composed OCI layers | **12 layers** |
| Final distinct filesystem paths in static merged-layer inventory | **2,490** |
| TAR metadata entries traversed | **2,694** |
| File-kind overwrites across layers | **2** |
| OCI whiteouts / opaque directory markers observed | **0 / 0** |
| Special archive entries treated only as metadata | **10** |
| All final ELF64 x86-64 objects statically scanned with trusted readelf | **153** |
| Highest observed GLIBC required symbol version | **2.44** |
| DT_NEEDED names without *any basename or SONAME candidate* | **0** |
| DT_NEEDED names with multiple basename/SONAME candidates | **27** |

**Static ELF presence and file hashes:**

- `usr/bin/node` exists as real ELF, whole SHA-256 `4cd585ad40c3be56379742ada783e809277520645f624dfb9851b9516011741a` (83,928,832 bytes).
- `usr/bin/python3.12` exists as real ELF, whole SHA-256 `6b8a824670dbb27cc0265267df01434b5fbabbae54b8db790675fa28fd53b259` (15,792 bytes).
- `/lib64/ld-linux-x86-64.so.2` follows `lib64 -> usr/lib` and resolves to `usr/lib/ld-linux-x86-64.so.2`, whole ELF SHA-256 `2b1529d949956d0913dce1809976adf339adc0d992de5ae6eba21dad0fa9fb09` (272,272 bytes), matching R21–R24 and original verified base.
- `usr/bin/clear` is a real ELF, not BusyBox symlink, SHA-256 `98011ef86e4d2985ccc4d4a4e529c7790d1cc2e2f94ffa3296d4dc17f51377ed`, matches signed-index-linked ncurses archive.
- **Do not convert no missing `DT_NEEDED` *name* into actual linker path/ABI pass.** Multiple candidates include symlinks/versioned .so files, and dynamic loader order, relocations, dlopen, NSS, process execution and certificate TLS verification were **NOT** tested.

**Static OS identity, NSS, CA and timezone path evidence:**

| Checked final OCI path | Source-only observation |
|---|---|
| `etc/os-release` | File exists; `ID=wolfi`; SHA-256 `8209665b39efdb89514d7cadc50b7ffc3e64dff2cd05736cb04ea078a1a9a24a` |
| `etc/passwd` | File exists; root UID and an unprivileged user entry observed |
| `etc/group` | File exists; root group GID record observed |
| `etc/nsswitch.conf` | File exists; `passwd: compat`, `group: compat`, `hosts: files dns` entries observed |
| `etc/ssl/certs/ca-certificates.crt` | File exists; **121** PEM certificate markers, SHA-256 `028fca5150ee1915c4474489985d55c54fceaa680c754cc8d1301734f01b2232` |
| `etc/ssl/cert.pem` | Resolves to the same present CA bundle |
| `usr/share/zoneinfo/UTC` | **NOT FOUND** in composed source-only inventory |
| `usr/lib/os-release` and `usr/lib/ssl/cert.pem` | **NOT FOUND**; not necessarily required if applications use the verified canonical paths |

The missing zoneinfo path is a **documented timezone-data support gap**, not proof of broken UTC timekeeping or a reason to silently add packages. A later step must establish whether the original Worker needs IANA tzdata, or whether UTC-only operation is sufficient; do not assume.

## Security / provenance limitation and next gate

This is a **read-only static inspection of a disposable OCI filesystem**, not a four-language execution test and not an independently certified secure environment for unknown code. The image in R25 contains Wolfi/Python/Node foundation packages but **does not contain TypeScript 5.9.3 npm artifact or Wasmtime 49.0.0 Python binding**. Their R19 registry/wheel digests were inspected previously, but independent publisher attestations remain unverified. The historical Wolfi signed APKINDEX `Q1` SHA-1 collision-resistance caveat remains.

**Open before release:** full ELF loader functional tests, timezone expectations, NSS/CA/TLS runtime behavior, TypeScript/Wasmtime inclusion/provenance, four-language safe fixtures, Node 18→24 semantic comparison and independently approved rootless OCI+gVisor host execution boundary. Original **199 Critical/High findings** remain review-open, **0** CVEs closed, and A6 continues to raise `A6_INDEPENDENT_HOST_CERTIFICATION_REQUIRED` hard DENY.

**Recommended CERT-A19-R26:** prove whether timezone database is functionally required by the current Worker and audit original Python/Node/TS/Wasmtime runtime resource/config contracts **READ ONLY**; select signed Wolfi timezone data only if justified and source-pin it. Then plan separately authorized, controlled developer-only fixed benign fixtures under an independently reviewed host; never execute unknown strategies or claim security certification from simple container tests.

**R25 verdict:** `CERT_A19_R25_COMPOSED_40_PACKAGE_OCI_153_ELF_STATIC_AND_OS_PATHS_PASS__TLS_TZ_RUNTIME_AND_HOST_UNVERIFIED__A6_DENY_199_OPEN`.

**No changes** to `main`, original A11 historical Debian lock, A2/A15/A18 recipes, broker/trading logic, production, Telegram or TELMIVO. PR #275 remains **DRAFT / DO NOT MERGE**.
