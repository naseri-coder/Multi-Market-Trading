# CERT-A19-R29 — Offline gVisor Release Custody and Independent Rootless Host Accreditation Contract

**Date:** 2026-10-15 UTC.
**Verdict:** \`CERT_A19_R29_GVISOR_RELEASE_CHECKSUM_BYTES_PINNED__13_NEGATIVE_HOST_POLICY_TESTS_PASS__NO_PUBLISHER_SIGNATURE_OR_APPROVED_HOST__A6_DENY_199_OPEN\`
**Purpose:** establish verifiable prerequisites and a fail-closed host-accreditation policy for *future independently authorized* developer-only benign fixtures. This stage is **NOT** an operational host accreditation or a Worker runtime test.

## 1. Actual nonproduction proof and scope

- **Actual narrow hosted Actions run:** [#38700270209](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38700270209), **SUCCESS**, one independent research-branch workflow on \`cert-a19-byte-audit-run\` (no normal PR suites).
- Exact repository research source: \`scripts/ci_cert_a19_r29_host_policy.py\`, workflow \`.github/workflows/cert-a19-r29-host-accreditation.yml\`, scratch branch commit \`ae9ff01312e1a4ded62269e0aa178bc3988dbaf7\`.
- Original evidence artifact \`cert-a19-r29-offline-gvisor-host-policy\`, GitHub Actions artifact **11955487600**, 2-day retention. Downloaded actual JSON \`r29-policy-report.json\`, **4,451 bytes**, SHA-256 **\`16400ae6890cbc5aae0a26df3179ab91db049b2d8fbce60c8e45646af2b0b160\`**. Artifact has **no executable binary, host secrets, Docker socket, container or image**.
- The trusted GitHub-hosted Python standard library code tested an offline decision predicate and negative cases. **It did not contact, install or execute gVisor, runsc, rootlesskit, guest code or a Worker.** The release checksum listing was downloaded only as a small textual verification input; no gVisor tarballs were downloaded or extracted.
- The original R28 failed host qualification remains authoritative and was deliberately tested as a fail-closed **policy scenario**, not a newly certified host.

## 2. Exact source-fixed gVisor release identities

Official sources:
- https://github.com/google/gvisor/releases/tag/release-20261005.0
- https://gvisor.dev/docs/user_guide/install/
- https://gvisor.dev/docs/user_guide/rootless/
- https://docs.docker.com/engine/security/rootless/

| Source / artifact | Frozen observed identity |
|---|---|
| GitHub official gVisor release | \`release-20261005.0\` (published 2026-10-08) |
| Annotated Git tag object SHA | \`e1987e70c70be06e89be3bad7934f02ec715e333\` |
| Tag's target source commit | \`97e8e896904cb364319cd9758241d3f0bd27a6f4\` |
| Tag signature status exposed by GitHub | **\`verified=false; reason=unsigned\`** |
| Official release \`SHA256SUMS\` asset's SHA-256 | \`dc3ea2d7486b9c07d9ad0ae3880b69a1a020708b83c4a8fe3bb781a871ef2308\` |
| Release file \`gvisor-x86_64.tar.zstd\` published SHA-256 | \`0a8a9058b9f11791a2097f03190c2ddc5b963c3dbee5bb9fd8497f4801c42f92\` |

The hosted run downloaded the exact official checksum **text** for this release, enforced the immutable SHA-256 of that text, parsed and checked that the exact x86-64 tarball filename maps to the recorded full SHA-256, and rejected duplicate/invalid listing records. **It did not download or independently verify the 129 MB release binary**, did not inspect the extracted \`runsc\` executable, and did not obtain a separately verified publisher signature or signed SLSA attestation.

**Important cryptographic distinction:** a matching SHA-256 in a release's own asset metadata and checksum file provides reproducible **byte identity relative to GitHub's published listing**, not independent publisher-identity authentication. The GitHub annotated tag itself is unsigned. Do not label this a signed gVisor release certification or trust an unsigned tarball from a mirror. A later step must establish independently verifiable, trusted signing evidence (for example, verified upstream package repository signing chain or explicit signed build attestation) **and** the exact executable \`runsc\` SHA-256 from such an authenticated bundle before host accreditation can be granted.

The official gVisor release bundles \`runsc\`, the containerd shim and \`gvisor-bin/\` sidecar binaries. A future certified installation must preserve/examine these relative paths and exact contents, not pin only a tarball filename.

## 3. Pure accreditation decision contract — not a physical test

A future real candidate host must submit **externally verifiable evidence**, not merely JSON booleans or a claim in a log. The R29 policy records fail-closed checks requiring:

1. **Explicit scope and independent ownership:** a separately user-authorized disposable nonproduction host, independent auditor identity/approval, no shared use of production/TELMIVO/license authority/broker or access to user trading strategies.
2. **Actual rootless daemon provenance:** process/UID mapping proof showing *daemon and runtime* are truly unprivileged; rootful fallback disabled. Merely specifying a nonroot container user or joining the \`docker\` group is **not** rootless daemon evidence.
3. **Proven gVisor runtime:** real \`runsc\` binary and each sidecar identified by authenticated digest, correct release and registered runtime in the **rootless** daemon, plus verified launch path; not simply \`runsc\` present in PATH or a system daemon registering a name.
4. **Socket and kernel custody:** rootless daemon socket owner and ACL, denial of access to untrusted users, audited kernel patch/namespace/cgroup/syscall limits and resource controls. Treat cgroup filesystem presence alone as insufficient.
5. **Untrusted input confinement:** immutable OCI digest, no implicit pull, network and IPC restrictions, no host or Docker socket mounts, readonly guest root, no caps/new privileges, nonroot guest UID/GID, reviewed CPU/RAM/PID/timeouts and independent escape/negative tests. Evidence must be attributable to the specific host, runtime and test instance.
6. **Fixture/release gating:** exact source-reviewed benign Python/JS/TS/WASM bytes/digests, signed source custody, no secrets, no broker, no customer code, bounded output, verified cleanup. A fixture success would only establish a runtime compatibility property; it would **not** automatically certify arbitrary-user-code security.
7. **Product hard gate retained:** original \`A6_INDEPENDENT_HOST_CERTIFICATION_REQUIRED\` must remain DENY until a completely separate, authorized security release process; no blanket CVE waiver or PR merge.

The pure R29 policy self-test intentionally marks its data \`synthetic_test_data=true\`. It **never** uses that data to promote a real host to accredited status. The policy additionally blocks accreditation while no independent digest for extracted \`runsc\` and publisher attestation is available; no executable bytes were downloaded.

## 4. Measured negative cases

The script ran exactly **13** targeted changed-field negative checks, each rejected for the corresponding failure code:

| Scenario | Required denial |
|---|---|
| Missing explicit user approval | \`NO_EXPLICIT_HOST_AUTHORIZATION\` |
| Missing independent reviewer | \`INDEPENDENT_AUDIT_APPROVAL_MISSING\` |
| Production/shared host allowed | \`PRODUCTION_SEPARATION_UNPROVEN\` |
| Rootful Docker daemon | \`ROOTLESS_DAEMON_UNPROVEN\` |
| Rootful fallback enabled | \`ROOTFUL_FALLBACK_POSSIBLE\` |
| \`runsc\` not registered | \`RUNSC_RUNTIME_NOT_REGISTERED\` |
| Release archive digest tampered | \`RUNSC_RELEASE_ARCHIVE_DIGEST_DRIFT\` |
| Nonroot daemon socket ownership absent | \`ROOTLESS_SOCKET_CUSTODY_MISSING\` |
| Socket exposed to untrusted principals | \`UNTRUSTED_SOCKET_ACCESS_NOT_REJECTED\` |
| Guest network/host mount controls absent | \`NETWORK_OR_HOST_MOUNTS_NOT_DENIED\` |
| Independent escape tests absent | \`NEGATIVE_SECURITY_TESTS_NOT_PASSED\` |
| A6 hard denial removed | \`A6_DENY_NOT_PRESERVED\` |
| Guest execution performed in unauthorized scope | \`UNKNOWN_EXECUTION_STATUS\` |

All **13/13** tests passed *as negative control rejections*. A separate R28-matching synthetic record with \`daemon_is_rootless=false\`, \`runsc_registered_as_runtime=false\`, no independent authorized owner and no signing custody was likewise denied. There was **no real PASS-accredited host**, no positive physical execution, no attempt to install \`runsc\`.

### Interpretation of upstream requirements

gVisor's official Rootless guide explicitly distinguishes a truly rootless **entire process chain** from rootful Docker with merely nonroot guest UID. The gVisor architecture guide cautions that \`runsc --rootless ... do\` by default may expose the host filesystem for convenience and therefore is NOT by itself a security isolation acceptance test. Docker's rootless documentation demonstrates \`docker info\` rootless under a dedicated per-user daemon. All of these official warnings are reflected in R29's host contract. Avoid selecting \`runsc do\` as a shortcut test harness; prefer a separate independently accredited OCI confinement path.

## 5. Remaining hard gates and next step

**PASS (limited):** pinned gVisor official release/checksum listing byte verification; release tag signature-status observation (unsigned), source version chain recorded, fail-closed policy script 13/13 negative checks and R28 deny.

**BLOCKED:** authenticated runsc executable and sidecars, independent publisher-signed attestation, independently designated/reviewed nonproduction machine, actual rootless Docker and registered gVisor runtime, fixture execution/parity, TLS/NSS/tzdata runtime, 4-language runtime in a composited image, and verified host cleanup/isolation.

**No mutations:** \`main\`, old A11 372-file Debian pin, A2/A15/A18 runtime source/image, Broker/trading/TELMIVO/Telegram/prod remain untouched. Draft PR #275 **DO NOT MERGE**. The original **199 Critical/High security findings remain review-open** and **0 CVEs certified fixed**. RUNTIME-A6 hard DENY unchanged.

**Suggested CERT-A19-R30 (without new host):** research a true upstream publisher-authenticated gVisor distribution chain (signed apt repository metadata/release or signed attestations), freeze a reproducible identity-bound \`runsc\` + \`gvisor-bin\` digest inventory, and extend offline verifier negative controls to cover manifest/wheel/source signature substitution. If no independent proof exists, report unresolved. **Do not install, run, deploy or probe TELMIVO/production hosts without explicit separate authorization.**

**R29 label:** \`CERT_A19_R29_OFFLINE_GVISOR_CHECKSUM_IDENTITY_AND_13_FAIL_CLOSED_CONTROLS_PASS__ROOTLESS_RUNSC_PUBLISHER_PROVENANCE_AND_INDEPENDENT_HOST_BLOCKED__A6_DENY_199_OPEN\`.
