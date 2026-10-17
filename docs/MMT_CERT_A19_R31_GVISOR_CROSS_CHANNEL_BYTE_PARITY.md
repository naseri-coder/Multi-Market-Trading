# CERT-A19-R31 — gVisor GitHub Release vs Signed-Vendor-APT Native Binary SHA-256 Parity

**Stage:** CERT-A19-R31
**Date:** 2026-10-15 UTC
**Verdict:** \`CERT_A19_R31_ALL_SEVEN_GVISOR_GITHUB_AND_VENDOR_APT_EXECUTABLE_BYTES_IDENTICAL__PUBLISHER_FINGERPRINT_INDEPENDENTLY_UNAPPROVED_HOST_DENY_A6_DENY_199_OPEN\`
**Scope:** targeted nonproduction research on the existing scratch branch; downloaded bytes were treated as inert data, never installed or executed. No Worker/host launch, no production, no PR merge.

## 1. Authoritative hosted run and evidence

- Targeted [GitHub Actions SUCCESS #38710006962](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38710006962), exact isolated branch \`cert-a19-byte-audit-run\`. Workflow \`.github/workflows/cert-a19-r31-gvisor-cross-channel.yml\` at scratch commit \`127321a81be52f7eeb1376a1f2ec9d3b365ae956\`; source parser \`scripts/ci_cert_a19_r31_cross_channel_binary_parity.py\` (pre-trigger source commit \`852bb8d5792c24c42e8d041156d56a430b1ce19a\`).
- Both historical **R29** evidence JSON (SHA-256 \`16400ae6890cbc5aae0a26df3179ab91db049b2d8fbce60c8e45646af2b0b160\`) and **R30** signed-APT JSON (SHA-256 \`baefb28f1ee94932362078246cf6e6c8b4845b0c920938764d8e7926adc764da\`) were rehydrated from their exact GitHub Actions artifacts and checked byte-for-byte before this investigation.
- The official **GitHub release \`google/gvisor\` / tag \`release-20261005.0\`** \`gvisor-x86_64.tar.zstd\` compressed archive was fetched in the disposable GitHub runner. The original \`SHA256SUMS\` text SHA-256 \`dc3ea2d7486b9c07d9ad0ae3880b69a1a020708b83c4a8fe3bb781a871ef2308\` and exact tarball SHA-256 \`0a8a9058b9f11791a2097f03190c2ddc5b963c3dbee5bb9fd8497f4801c42f92\` both PASSED against the frozen R29 values. No \`latest\` alias was trusted.
- Stream-decompressed **as data only** with the GitHub-hosted Ubuntu runner's trusted \`zstd\` and Python tar reader. No software files were extracted to any executable path. The TAR contained **seven regular members** and one directory metadata entry; 328,097,690 uncompressed file bytes were examined.
- **Original R31 proof artifact:** \`cert-a19-r31-gvisor-release-vs-signed-apt-binary-parity\`, GitHub artifact **11959678573**, two-day retention; \`r31-two-channel-byte-parity.json\`, independently downloaded/extracted and SHA-256 **\`fd2171354fa3ac56eb899fb18a5fd28ae01b3116a01ce705ee37a5663ab3101d\`**, 4,367 bytes. No executable, GPG key or tarball was uploaded. Workflow cleanup deleted the downloaded software bytes.

## 2. Direct comparison with R30 signed-vendor-APT seven-file custody

The signed APT R30 run [#38703730127](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38703730127) already verified the vendor GPG signature on its APT \`InRelease\` and recorded the whole-package and all seven executable file hashes. R31 independently read all seven paths from the fixed *official GitHub tarball*, computed each file's full SHA-256 and size, and compared with the frozen **R30 APT measurements**.

| Relative filename after removing APT's usr/bin prefix | Bytes in each publication | SHA-256 (same in both channels) | Match |
|---|---:|---|---|
| \`runsc\` | 109,966,750 | \`210b437a9cfae51e8f8c9074ed19b8b5e59477178e2e391a18117d8d6b924f7a\` | PASS |
| \`containerd-shim-runsc-v1\` | 43,626,680 | \`2bff94d15386d36e62e2f105ba835f650e55327cb731d96820cbbfe5592c2a6b\` | PASS |
| \`gvisor-bin/checkpointgofer\` | 69,128,994 | \`c454d0b5fab4627d8915194f901a70c66bb4792f680e3f75d2a47516382b449a\` | PASS |
| \`gvisor-bin/gvisor-sentry-prewarmer\` | 1,416 | \`3315d7ad7c2d3751d349e4976fa02da1da6fd7e41746c35622304e5fabe4fce0\` | PASS |
| \`gvisor-bin/gvisor_sentry\` | 52,149,808 | \`0050e7c6063e17de1729500cd73b18322d85c758eb0ffcab18e539df7110bd12\` | PASS |
| \`gvisor-bin/runsc-fd-parking\` | 1,320 | \`03af90d07ea466c10ecc3e3ba839b2a59540959dd3286aea3886917cba850c11\` | PASS |
| \`gvisor-bin/runsc-metric-server\` | 53,222,722 | \`7bcbe5846a0f6d34c7d2bd312033bb92ab6305b9ac93e09b753b3474f91f27b2\` | PASS |

**Result: full SHA-256 and byte-size equality 7/7.** This directly closes the particular R30 cross-channel byte-identity uncertainty. Notably, the R30 sample reports all 7 with ELF headers, even when a few are short: R31 checked the same files' magic byte directly; R31's report records each flag explicitly. Do not infer that any of the seven were started/executed.

## 3. Security classification and nonupgraded trust

**Two publisher-controlled publication channels matching does not constitute two independently authenticated publishers.** GitHub release checksum text was distributed on Google's own release page and GitHub's tag was reported unsigned by R29. Vendor APT's signing GPG key was previously retrieved from \`https://gvisor.dev/archive.key\` over vendor HTTPS. Its R30 observed fingerprint is \`6F1DF85E3A71C24918E727D56FC6D554E32BD943\`; R31 preserves it as **OBSERVED, NOT independently reviewed or authorized**. It was not silently converted into an independent user-trust pin by being hardcoded into a test script. There was no audited out-of-band fingerprint approval, no signed provenance attestation reviewed from a distinct trust root, no key-rotation policy approved.

- Exact 7-file byte identity and consistent vendor release membership: **PASS, R31 limited research**.
- Independent GPG publisher fingerprint, host accreditation, secure rootless daemon, registered \`runsc\`, kernel confinement, independent negative/escape audit: **NOT CERTIFIED**.
- TypeScript/Wasmtime runtime installation, four-language harmless fixed fixture equivalence, Node 18→24 semantics, final usable untrusted Worker sandbox: **NOT TESTED**.
- Original **199 Critical/High security scanner findings stay REVIEW-OPEN**; **zero CVEs certified fixed/waived**.
- RUNTIME-A6 still throws \`A6_INDEPENDENT_HOST_CERTIFICATION_REQUIRED\` hard DENY; no \`main\`, A11, A2/A15/A18, broker/trading, TELMIVO, Telegram, production, Worker/image/registry or PR merge mutation.

gVisor official guidance describes APT and Cloud Storage as its canonical channels and GitHub release as a mirror; sharing the same official publisher is precisely why their identical files are strong *publication-consistency* evidence, not independent signing approval: https://gvisor.dev/release/ .

## 4. Sensible next R32 gate

- Conduct **independent key fingerprint approval** out of band, with reviewer identity, key lifetime/rotation and revocation policy, and recheck the signed APT metadata against the explicitly approved fingerprint. Merely downloading the same key again from another mirror is not independent approval.
- If no independent key-identity anchor or authorized host exists, create a fail-closed, local/offline approval contract and document \`INDEPENDENT_KEY_APPROVAL_REQUIRED\`; do not trigger a guest or host install. Do NOT manufacture approval metadata.
- A real separately approved disposable nonproduction rootless/gVisor host must satisfy R29/R28 host-control requirements before benign fixtures can be considered; fixture success will not automatically authorize arbitrary untrusted execution or remove A6.

**Formal R31 disposition:** \`CERT_A19_R31_SEVEN_GVISOR_EXECUTABLES_BYTE_IDENTICAL_IN_GITHUB_AND_VENDOR_APT__INDEPENDENT_SIGNATURE_TRUST_AND_HOST_DENY_A6_DENY_199_OPEN\`.
