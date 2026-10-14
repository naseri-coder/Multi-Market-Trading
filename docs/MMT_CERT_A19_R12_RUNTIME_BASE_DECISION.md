# CERT-A19-R12 — Debian-Neutral Worker Runtime Architecture Decision
**Status:** RESEARCH-SPEC-FROZEN / IMPLEMENTATION-NOT-AUTHORIZED
**Date:** 2026-10-14
**Repository:** naseri-coder/Multi-Market-Trading
**Authoritative baseline:** main at dccfe791f465040cc87d210c0ca33fad44f654ae
**Scope:** Nonproduction design evaluation only. No runtime source, Dockerfile, A11/A12 locks, registry, production server, worker deployment, broker, Telegram, TELMIVO, or License Authority mutation.

## 1. Problem statement and correction

Debian is not a product/platform requirement. It entered the runtime supply chain because the experimental Worker OCI image was based on an immutable python:3.12-slim-bookworm digest, used pinned Debian APT packages for Node.js and its dependency tree, and later copied runtime files to the A15/A18 candidate. This is an **implementation coupling**, not a requirement for customers to install Debian.

Smaller filesystem / fewer reported scanner packages do **not** mean independently verified security. Merely changing Linux distributions does not fix the runtime isolation gap, Node's VM limits, or any of the 199 historical security findings. A18 is currently an **unreleased research candidate**, not a certifiable production image.

**Important newly verified concern:** Node.js **v18.20.4** is frozen in A15's exporter, whereas the Node.js 18 line reached official EOL on 2025-03-27. A future security-eligible candidate needs an independently verified, maintained Node line (prefer Node 24 LTS as a **research target**, not a silent upgrade), and all application/ABI behavior must be requalified. See https://nodejs.org/en/about/previous-releases and https://nodejs.org/en/about/eol .

## 2. Evidence-backed current runtime contract (not a hypothetical stack)

Verified in current main:
- Base: deploy/runtime_a2/Dockerfile -> python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258.
- Dockerfile A11/A12: exactly 372 fixed Debian packages, signed snapshot and hash checks. Never mutate historical proofs; replacement candidate must be independently versioned and carry separate locks.
- A15: Dockerfile.a15-lean copies Python/Node/Wasmtime runtime closure from the original image into the **same Python Debian base**; a smaller scanner inventory does not prove remediation.
- A18: Dockerfile.a18-absence recreates the A15 payload with extra guard/metadata. No library or engine security patch.
- Python is 3.12. Node exporter enforces precisely v18.20.4. TypeScript compiler version is 5.9.3 from pinned npm archive. The wasmtime Python wheel is 49.0.0 with SHA-256 94f0288f9e1c33924995a72bb769f4c4e2885002391589dd6992cdaa35d1990a for historical manylinux x86-64.
- scripts/runtime_a2_worker.py implements a framed ABI 1.0 protocol, four runtime kinds {python,javascript,typescript,wasm}, capped artifact/frame/output sizes, timeouts, event/manifest digests, and output schema. Python uses a Python child process; JavaScript uses Node's vm with an injected event; TypeScript uses the TypeScript compiler and the same Node VM; WASM uses the Python wasmtime binding.
- For JavaScript the Worker uses node:vm's runInNewContext. The **official Node documentation explicitly states that node:vm is not a security mechanism and must not be used alone to run untrusted code**: https://nodejs.org/api/vm.html .
- Runtime-A6 must remain denied: A6_INDEPENDENT_HOST_CERTIFICATION_REQUIRED. No distribution switch can supersede independent rootless OCI + gVisor/stronger isolation certification.
- The Debian tree includes node-undici from its packaging. A newer Node line may contain internally bundled Undici even if no external node-undici package is present; absence of the Debian package is **not** proof that all Undici-related attack paths vanished.

## 3. Candidate options (no fabricated size, CVE count or compatibility outcome)

| Candidate | Debian dependency | Benefits to test | Material unresolved costs | Decision |
|---|---|---|---|---|
| A. Continue pinned Python slim Bookworm | Yes | Existing reproducible research evidence / minimum migration work | Node 18 EOL, Debian vulnerabilities and unchanged A6 host gate | Historical reference only, not security-complete |
| B. Google Distroless Debian 13 with combined Node/Python runtime | **Yes** | Removes shell and package manager; has signed images; reduces final runtime utilities | Still Debian; currently documented python3-debian13 is Python 3.13 vs our Python 3.12, Node binary/ABI layering and external type module need proof | Comparison control, NOT a Debian-free solution |
| C. Wolfi/glibc (Chainguard-style minimal custom OCI) | **No Debian APT** | glibc familiarity for Python/Node native ABI; minimal final packages; signed SBOM/provenance support | Availability of exact Python/Node versions, composition of both, image signature/identity and key custody, trust in new packaging, cost/availability, TLS/CA/NSS/ELF closure must be verified | **Primary research candidate**; NOT approved for deployment |
| D. Alpine/musl minimal custom OCI | **No Debian APT** | Small runtime; musl ecosystem; Wasmtime 49 *does* publish musllinux 1.2 x86_64/aarch64 wheels | Existing manylinux wheel cannot be reused byte-for-byte; Node supported musl build/source signing, Python native extension/ABI, dynamic loader and four-language parity need proof | Secondary research candidate, NOT rejected on Wasmtime alone |
| E. scratch / fully static single image | None if truly static | Small possible executable closure | Combined CPython + Node + Wasmtime, glibc/loader/CA/NSS requirements and licensing/provenance make claimed static portability unsupported | DEFER; no source verified |
| F. Separate isolated per-language Workers | Choice depends on each image | Can reduce per-image code and package surface; Python+WASM and Node+TS might separate naturally | Changes process topology, framed ABI, external host policies, latency, memory, routing, isolation, and testing; cannot assume no regressions | Architecture alternative for later, NOT part of R12 |

Vendor references:
- Chainguard minimal images/Wolfi supply chain: https://github.com/chainguard-images ; source/SBOM workflow: https://support.chainguard.dev/hc/en-us/articles/56768221947675-Download-the-source-code-for-packages-in-a-Chainguard-image
- Distroless Debian 13 / image signing: https://github.com/GoogleContainerTools/distroless/blob/main/README.md ; Python3 runtime compatibility: https://github.com/GoogleContainerTools/distroless/blob/main/python3/README.md .
- musllinux vs manylinux ABI: https://peps.python.org/pep-0656/ ; official Wasmtime 49.0.0 wheels include both glibc and musl Linux variants: https://pypi.org/project/wasmtime/49.0.0/ .
- Node release lifecycle: https://nodejs.org/en/about/previous-releases .

**Not asserted:** Chainguard offers a single public image already containing exactly Python 3.12 + Node 24 + TypeScript 5.9.3 + Wasmtime 49.0.0; whether Node 24 is compatible with current Worker without edits; actual Wolfi/Alpine SBOM/CVE count or image size.

## 4. Decision and migration shape

**R12 ARCHITECTURAL DECISION:** decouple *Worker public ABI* from *Linux-distribution implementation*. Treat the current Debian-based A18 runtime as a **frozen reference** for nonproduction equivalence only. Investigate a **Wolfi/glibc-based Debian-neutral minimal runtime with Node 24 LTS** as the first candidate and Alpine/musl as the independent fallback. Do not decide production suitability by distro name, Docker image size or scanner counts.

Proposed strictly isolated implementation path for future **explicitly authorized** R13:
1. Freeze a candidate-independent Worker compatibility contract from main (frames, digests, return codes, runtime kind, four fixed benign fixtures, error determinism), without modifying the Worker.
2. Gather authentic image-publisher signatures, immutable OCI per-architecture digests, per-file SBOM and source attestations, Python and Node binaries and exact version/ABI support **before** any candidate build.
3. Prepare a separate, versioned, nonproduction build recipe and dependencies manifest outside existing historical A2/A15/A18 files and A11 lock; no changes to main.
4. Do not install package managers, developer toolchains, npm CLI or downloaded archives in the final Worker image. Build-stage tooling is permitted only with explicit provenance and bounded, pinned dependency inputs.
5. Validate Python 3.12 requirement first; if a new Python version is proposed, classify it as an **additional ABI migration** and gate separately. For Node target 24, separately assess V8/VM behavior, JS/TS compatibility, built-in Undici and security lifecycle.
6. Confirm ELF loader, OpenSSL, CA cert bundle, resolver/NSS, timezone, stdlib, Wasmtime native library and TypeScript imports exist without undocumented copied libraries.
7. Run side-by-side **fixed harmless** four-language regression fixtures, serialization and error-path cases in disposable, suitably fenced environments; prove output equivalence for every accepted fixture. Never use real users' strategies.
8. Independent secure-host preflight/rootless runtime/gVisor confinement, filesystem read-only, immutable identity, disabled ambient network, Linux capabilities dropped, seccomp/kernel restrictions, timeouts and memory limits before allowing any nonfixture code.
9. Generate SBOM plus comparable fixed-advisory-DB scan for old and new candidates; inspect **actual source bytes and surviving equivalents**. Carry all 199 original A17 findings as review-open until per-finding independent disposition.
10. Fail closed and prefer no candidate rather than relax A6, edit current locks, move thresholds, deploy or merge.

## 5. Binary go/no-go acceptance gates for a future candidate

Every gate must be **PASS with traceable hashes and artifact IDs**, otherwise release status is DENY:

| Gate | Required evidence | R12 present state |
|---|---|---|
| G01 Provenance | Verified, frozen base OCI digest, authenticated signature identity and software SBOM | NOT_RUN |
| G02 ABI | Exact Python 3.12 or separately authorized Python migration; maintained Node branch, Wasmtime/TS native ABI manifests | NOT_RUN |
| G03 Surface | Actual final image inventory contains no package manager/shell/npm/compiler unless justified; no added networking capability | NOT_RUN |
| G04 Semantics | Same four-language framed payload, timing/error/path behavior on fixed fixtures | NOT_RUN |
| G05 Security | Independent host rootless OCI + gVisor or reviewed equivalent, including malicious guest isolation; node:vm alone denied | NOT_RUN |
| G06 Native libraries | ELF/interpreter/CA/TLS/NSS and glibc or musl wheel compatibility verified | NOT_RUN |
| G07 CVE evidence | Same-DB SBOM and file-byte analysis; no invented CVE closures or risk waiver | NOT_RUN |
| G08 Custody | Immutable per-architecture artifact and reproducible evidence, no file outside review scope | NOT_RUN |
| G09 Authorizations | RUNTIME-A6 stays hard DENY unless separately certified by independent authority; no production | DENY |
| G10 Preservation | No changes to original A11 372 lock, A2/A15/A18 files, GitHub main, TELMIVO or other production services | PASS (document-only R12) |

**Production/candidate promotion decision: DENY.** This document is a design gate, not a passing runtime, CVE patch, deployment request, registry publication or removal of the Debian historic branch. Existing R7–R11 results remain valid research evidence and must not be interpreted as an authorization to suppress their 199 original findings.

## 6. R12 outcome

- Accepted for **nonproduction research priority only:** Wolfi/glibc minimal combined runtime, maintained Node 24 + verified Python / Wasmtime / TypeScript compatibility.
- Keep Alpine/musl as a separately measured option. Never infer musl impossible: Wasmtime 49.0.0 publishes specific musllinux wheels, but the A10 pinned manylinux binary is NOT that wheel.
- Rejected for the goal "remove Debian": a Debian 13 distroless image is still based on Debian, though it may be an excellent minimal-image *comparison*.
- No R13 implementation, OCI build, Docker run, CI, CVE close, external communication, production deployment, PR merge or permission changes executed.
- `CERT_A19_R12_ARCHITECTURE_RESEARCH_PASS_SECURITY_CANDIDATE_NOT_BUILT_A6_DENIED_199_OPEN`
