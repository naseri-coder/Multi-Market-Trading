# CERT-A19-R30 — gVisor Signed APT Repository and Seven Native Executable Artifact Digest Custody

**Date:** 2026-10-15 UTC
**Final bounded verdict:** \`CERT_A19_R30_VENDOR_GPGV_APT_INRELEASE_TO_RUNSC_20261005_PACKAGE_AND_7_NATIVE_FILE_HASHES_PASS__SIGNING_KEY_INDEPENDENT_TRUST_AND_ROOTLESS_HOST_UNVERIFIED__A6_DENY_199_OPEN\`
**Mode:** isolated nonproduction GitHub-hosted supply-chain research only. No installation, target binary execution, new or modified Worker, production deploy, registry push or PR merge.

## 1. Verified run and evidence source

- **Final narrowly scoped Actions success:** [#38703730127](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38703730127), scratch branch \`cert-a19-byte-audit-run\`, final workflow trigger commit \`10e9d201caf384d75acaf3a5debeffe45affcafd\`, not the Draft PR source branch.
- Prior fail-closed attempts: [#38703461838](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38703461838) due to wrong formatting assumption for trusted \`dpkg-deb -f\` field output and [#38703616029](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38703616029) due to mixing Python string/byte literals in a **synthetic negative case**. Their signer/index/package checks had not produced a successful report; both fail statuses are preserved. Corrected parser and negative-case construction, then successful single bounded verification. Neither failure is evidence of upstream signature compromise or an incompatible release.
- Verified earlier original R29 JSON from artifact 11955487600 with exact SHA-256 \`16400ae6890cbc5aae0a26df3179ab91db049b2d8fbce60c8e45646af2b0b160\`, prior to any trust upgrade.
- Final artifact \`cert-a19-r30-gvisor-signed-apt-native-custody\`, GitHub Actions ID **11956908134**, 2-day retention; it contains ONLY \`r30-apt-custody.json\`, 3,491 bytes, independently downloaded and calculated SHA-256 **\`baefb28f1ee94932362078246cf6e6c8b4845b0c920938764d8e7926adc764da\`**. No apt GPG key, executable, .deb, container, credentials, host files, or secrets were uploaded. Disposable runner files were removed in the successful cleanup step.
- Script: \`scripts/ci_cert_a19_r30_gvisor_signed_apt.py\`; narrowly guarded workflow: \`.github/workflows/cert-a19-r30-signed-apt.yml\` on scratch branch only. Neither is merged into \`main\` or Draft PR.

## 2. Independently checkable vendor publication chain actually tested

Official publisher install guide: https://gvisor.dev/docs/user_guide/install/

**Observed publication trust path:**

\`\`\`
HTTPS official gvisor.dev/archive.key [vendor distributed, not independently fingerprint-anchored]
    ↓
GPGV VALID SIGNATURE on official storage.googleapis.com/gvisor/releases/dists/release/InRelease
    ↓
signed InRelease SHA256 table binds main/binary-amd64/Packages.gz (exact length+hash)
    ↓
verified Packages stanza: Package=runsc; Architecture=amd64; Version=20261005.0
    ↓
signed metadata SHA256 and size bind pool/20261005.0/binary-amd64/runsc.deb
    ↓
dpkg-deb trusted host parser: package/version/architecture match signed stanza
    ↓
seven ELF-header native artifact files, full-byte hashes calculated
\`\`\`

| Evidence | SHA-256 / identity |
|---|---|
| Downloaded vendor APT signing public key bytes | \`757d2ebdf00cdc5661f88443e2bea848d3e2ded0780cbcd2d811be05e0c1d5dd\` |
| Observed GPG public-key fingerprint | \`6F1DF85E3A71C24918E727D56FC6D554E32BD943\` |
| Signature validation | **GPGV PASS**, \`InRelease\`; no unsigned APT index accepted |
| Official \`InRelease\` exact bytes | \`39aaac6a68db1f817ae75bcfab0d58bc05954442da7caddce5a51fd38f677fd7\` |
| Signed \`main/binary-amd64/Packages.gz\` bytes | \`2634c547fee00870d9301eb9b2d44561ef618d64d89d8936f060f09beff86adf\` |
| Selected \`runsc\` Debian package | \`20261005.0\`, \`amd64\`, path \`pool/20261005.0/binary-amd64/runsc.deb\` |
| Full Debian package bytes | **171,393,970**, SHA-256 \`2e7193c95424de28ac1a936fd5f0ec615dd288b74517bba697aa87c06df4a7c4\` |
| Separately inventoried ELF-header executables | **7**, all downloaded as inert data; neither launched nor installed |

**Actual seven executable-artifact identities from the hash-verified Debian package:**

| Archive-relative filename | Bytes | Observed SHA-256 |
|---|---:|---|
| \`usr/bin/runsc\` | 109,966,750 | \`210b437a9cfae51e8f8c9074ed19b8b5e59477178e2e391a18117d8d6b924f7a\` |
| \`usr/bin/containerd-shim-runsc-v1\` | 43,626,680 | \`2bff94d15386d36e62e2f105ba835f650e55327cb731d96820cbbfe5592c2a6b\` |
| \`usr/bin/gvisor-bin/checkpointgofer\` | 69,128,994 | \`c454d0b5fab4627d8915194f901a70c66bb4792f680e3f75d2a47516382b449a\` |
| \`usr/bin/gvisor-bin/gvisor-sentry-prewarmer\` | 1,416 | \`3315d7ad7c2d3751d349e4976fa02da1da6fd7e41746c35622304e5fabe4fce0\` |
| \`usr/bin/gvisor-bin/gvisor_sentry\` | 52,149,808 | \`0050e7c6063e17de1729500cd73b18322d85c758eb0ffcab18e539df7110bd12\` |
| \`usr/bin/gvisor-bin/runsc-fd-parking\` | 1,320 | \`03af90d07ea466c10ecc3e3ba839b2a59540959dd3286aea3886917cba850c11\` |
| \`usr/bin/gvisor-bin/runsc-metric-server\` | 53,222,722 | \`7bcbe5846a0f6d34c7d2bd312033bb92ab6305b9ac93e09b753b3474f91f27b2\` |

All seven files had ELF magic and were statically hashed after decoding the authenticated Debian package with the trusted runner \`dpkg-deb --fsys-tarfile\` parser. No byte was loaded, imported, executed or installed; no \`runsc install\`, \`docker run --runtime=runsc\`, rootless service change, host probing or image launch.

Eight input rejection/negative tests were checked (hash mismatch condition, unsafe filename/path, wrong download host/scheme, duplicate signed-index entry, missing package SHA-256, malicious APT package path). These are **unit negative controls** over Python input validation, not kernel escape security tests.

## 3. Critical trust limitations — no upward release promotion

**APT signature is real, key's independent identity is not.** The GPG key was fetched from the **official vendor HTTPS site**, then used to verify the official vendor-hosted APT \`InRelease\`. Thus the test demonstrates an internally consistent cryptographic chain anchored in a vendor-origin HTTPS public key. There was **no separately approved pre-pinned key fingerprint, independent auditor confirmation of this fingerprint, cross-signed external certificate or SLSA provenance claim**. Do not promote this from \`VENDOR_APT_GPGV_PASS\` into \`INDEPENDENT_PUBLISHER_ATTESTATION_PASS\`. An attacker who subverted the same distribution channels could still matter. Before host qualification, independently endorse/freeze the key fingerprint via a separate trust process, account for key rotation/expiry, and revalidate the exact package and binaries under that policy.

**Different distribution channel vs R29 checksum tarball:** APT package version \`20261005.0\` corresponds numerically to prior GitHub \`release-20261005.0\` tag, but **this audit did not compare the APT executables byte-for-byte to the R29 GitHub release tarball** SHA-256 \`0a8a9058b9f11791a2097f03190c2ddc5b963c3dbee5bb9fd8497f4801c42f92\`. Identical version strings are NOT byte equivalence or independent provenance. No GitHub binary tarball was downloaded.

**Physical rootless/gVisor host remains absent:** R28's live GitHub ephemeral runner lacked proven rootless daemon/runsc; no separately approved nonproduction host has been provided or independently security-accredited. Pinning authenticated \`runsc\` bytes does not prove kernel confinement, registration, seccomp policy, isolation, socket ownership, escape resistance, test cleanup or safe execution of user code. No gVisor-verified host test, no four-language fixture execution or Node 18→24 behavioral parity. Wolfi R24/R25 composed OCI remains an *unexecuted nonproduction* candidate and never got the Wasmtime/TypeScript runtime artifacts installed.

**Historical product blockers:** RUNTIME-A6 \`A6_INDEPENDENT_HOST_CERTIFICATION_REQUIRED\` remains hard DENY. All original **199 Critical/High security findings REVIEW-OPEN**, **0 CVEs certified closed**; no modification to \`main\`, A11 Debian 372 locks, A2/A15/A18, production, TELMIVO, Telegram, trading, broker, or PR #275 merge. The research PR is still **DRAFT / DO NOT MERGE**.

## 4. Suggested R31, not authorized by R30

- Obtain **independent official-source verification of the vendor APT key fingerprint** and a frozen policy for rotation/revocation. If possible, independently cross-compare the exact R29 GitHub release tarball and apt \`runsc\`/sidecar content for the same version; **do not assume byte equality in two different packaging formats**.
- Preserve the identity-bound seven-binary manifest above, signed apt Release SHA, and other package manifest hashes beyond the 2-day ephemeral artifacts. Add fail-closed negative cases for key substitution and \`Release\` tampering using a *pre-pinned and independently reviewed* key. Reusable script must refuse any key drift rather than silently accepting a newly fetched key.
- Only after separate user authorization for a nonproduction host and independent host security review, attempt actual rootless OCI+gVisor host accreditation. A fixed benign fixture could help runtime equivalence but **cannot** unlock A6 for untrusted guest execution on its own.

**Formal verdict:** \`CERT_A19_R30_GVISOR_VENDOR_SIGNED_APT_AND_SEVEN_BINARY_HASHES_PASS__INDEPENDENT_FINGERPRINT_ROOTLESS_HOST_AND_FOURLANG_EXECUTION_BLOCKED__A6_DENY_199_OPEN\`.
