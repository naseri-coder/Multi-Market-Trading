# CERT-A19-R27 — Explicit-Offset Time Fixture Contract and Static Rootless/gVisor Launch Fence

**Formal R27 verdict:** \`BENIGN_EXPLICIT_OFFSET_VECTOR_CONTRACT_AND_STATIC_A6_HOST_PREFLIGHT_PASS__GUEST_EXECUTION_BLOCKED\`.
**Scope:** isolated read-only, benign host-only reference computation and source AST inspection. Not a cross-language runtime test, no Worker execution or permission to process user strategies. Do not merge PR #275.

## 1. Actual source custody and hosted execution

- Successful single-purpose non-PR [GitHub Actions run #38697550355](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38697550355); only the guarded path \`.github/workflows/cert-a19-r27-fixture-gate.yml\` triggered this test.
- Full evidence artifact \`cert-a19-r27-fixed-utc-and-host-gate-static\`, ID **11954717453**, short-lived 2-day retention. Artifact carries JSON only.
- Extracted exact proof \`r27-report.json\`, **1,314 bytes**, SHA-256 \`818e8b3165c53404d1e33ac7bfb04d51886288b5c40b37155681f756485dcf5b\`.
- Extracted exact fixture specification \`r27-vectors.json\`, **2,127 bytes**, whole-file SHA-256 \`6f9c7847c5029d29f0f29fe5beae94c318bfc9a8c4f7f4a6512052e667812f1d\`. Canonical sorted compact JSON fixture contract SHA-256 \`0c1836b766d9cd93399ae86d2f093be2d7de85593077489d66ced0b46fb48fe0\`.
- Rehydrated exact R25 source-only OCI report SHA-256 \`26bc9c72b4b49c396a973b783764875566f24b4b2568f9495032ad9dc51f9264\` and R26 UTC/guest-time review JSON SHA-256 \`2de79cd86da7ccc17ce15952455c8b7673cf4161d3f99a32955d668e7e9f1667\`. Original report fields for 40 installed Wolfi packages, 153 inspected static ELFs, signed pinned \`cgr.dev/chainguard/wolfi-base@sha256:256c88bb066424045021090932d50be93c8e3f2ce3586707702a401b146f3e43\` and hard A6 denial passed.
- Exactly **five untouched main source blobs** rechecked with Git blob SHA-1 and statically parsed with Python AST: \`scripts/runtime_a2_worker.py\` \`0c21b87b77604c4025b8ea44ba35a24664c1537b\`; \`naseri_markets/core_api_v1.py\` \`23c3c07a8c05f0e70d56c59bf431f858dbd7e267\`; \`naseri_markets/multilang_runtime_a1.py\` \`02478c2786488b1e28eaa2e113636dbf3c9b5a7e\`; \`naseri_markets/secure_plugin_runtime_v1.py\` \`8d8c4b98023ce77d0ade78e1b2fc45f316d0bc75\`; \`naseri_markets/runtime_a6_dispatch_fence.py\` \`2299dba87a0ba3cd7095d97bca9ed6409adcb0ec\`.
- No installed program from the Wolfi image was executed or loaded. Only the GitHub **trusted host Python standard library** calculated explicitly offset-aware dates.

## 2. Frozen, deterministic benign time vectors

**Spec-only application:** These are *candidate, reviewed fixed-fixture inputs*, not a new product-level policy rejecting named IANA zones or a modification to Worker semantics. A named zone remains **NOT CERTIFIED**, not silently unsupported by product.

All **7/7 accepted** vectors were independently computed by host Python \`datetime.fromisoformat(...).astimezone(datetime.timezone.utc)\`; all **4/4 rejected** vectors failed parsing or explicit-offset acceptance. This is *not* cross-runtime equivalence, Node 18/24 parity, or an independent test of named-zone DST rules.

| ID | Explicit-offset test instant | Expected UTC |
|---|---|---|
| UTC offset zero | \`2026-10-15T09:00:00+00:00\` | \`2026-10-15T09:00:00+00:00\` |
| Positive offset | \`2026-10-15T12:30:00+03:30\` | \`2026-10-15T09:00:00+00:00\` |
| Negative offset | \`2026-10-15T05:00:00-04:00\` | \`2026-10-15T09:00:00+00:00\` |
| Spring before (explicit +01:00) | \`2026-03-29T01:59:59+01:00\` | \`2026-03-29T00:59:59+00:00\` |
| Spring after (explicit +02:00) | \`2026-03-29T03:00:00+02:00\` | \`2026-03-29T01:00:00+00:00\` |
| Autumn first repeated local wall time (+02:00) | \`2026-10-25T02:30:00+02:00\` | \`2026-10-25T00:30:00+00:00\` |
| Autumn second repeated local wall time (+01:00) | \`2026-10-25T02:30:00+01:00\` | \`2026-10-25T01:30:00+00:00\` |

Four negative input cases: missing offset (naive), bare named-zone string, impossible hour, and impossible numeric UTC offset. **These cases do NOT establish that Europe/Berlin DST rule lookup works**, only that already-supplied numeric offsets map deterministically to UTC.

The suggested next developer-only fixed-fixture contract uses \`EXPLICIT_UTC_OR_FIXED_NUMERIC_OFFSET_FOR_AUDITED_FIXTURE_VECTORS_ONLY\`, never as an unapproved production capability change. The original R25 candidate OCI lacks \`usr/share/zoneinfo/UTC\`, and no \`tzdata\` was downloaded/installed, no global TZ env behavior was changed.

## 3. Independent host launch safety — what was verified and what was not

Static analysis of the real, unmodified main-source AST verified source-level presence of:

- \`_utc()\` rejects naive datetimes and normalizes offset-aware timestamps to UTC; the Worker \`observed_at\` value passes through the previously validated event without a new local-time conversion.
- \`_run_oci()\` in A1 reaches \`require_worker_launch(profile, payload)\` before the subprocess spawn and uses \`time.monotonic()\` for deadline accounting. Original Worker child env includes \`PATH\` and \`NODE_PATH\` but **does not explicitly supply \`TZ\`**.
- \`build_polyglot_command()\` reuses \`build_run_command()\`, whose checked command flags include \`--runtime=runsc\`, \`--network=none\`, \`--ipc=none\`, \`--read-only\`, \`--cap-drop=ALL\`, \`--security-opt=no-new-privileges\`, \`--pids-limit=32\`, \`--user=65534:65534\`, and \`--pull=never\`. These are **text/code-level preconditions**, not evidence that a compliant gVisor or rootless daemon is actually present.
- \`_ensure_rootless_daemon()\` has a source-level check for \`name=rootless\`; it was **not invoked** on any independent host or authenticated as a real audited running daemon.
- \`require_worker_launch()\` retains the unconditional hard refusal \`A6_INDEPENDENT_HOST_CERTIFICATION_REQUIRED\`.

**Not run/proven:** physical rootless+gVisor host, kernel/namespace boundaries, syscall and container escape resistance, actual Python/Node/TypeScript/Wasmtime benign-fixture execution, Node.js 18.20.4→24.22.0 parity, \`Intl\`/Python zoneinfo named-zone transitions, dynamic library linking and TLS/CA runtime behavior. Also note \`node:vm\` does not provide an isolation security boundary; four-language binaries and source are *not present together* in this 40-package candidate OCI.

## 4. Decision and next independent steps

**R27 PASS only for:** 7 host-Python explicit numeric offset reference calculations, 4 rejections, immutable review of 5 main-source blobs, and static presence of the A6/gVisor/rootless launch-fencing code.

**R27 NOT PASS:** cross-language parity, independent host confinement, code-execution safety, named IANA timezone support, package signing upgrades, production readiness.

**R28 candidate:** independently verify an actual disposable rootless OCI+gVisor host's security properties and audit the exact fixed benign fixture harness, including physical daemon/socket custody, no-network/read-only/capability/PID/RAM/CPU hard limits, no secrets/mounts/broker, and evidence of timely clean-up. **Do not execute guest/Worker code or relax A6 until that separate host authorization and confinement review succeeds.** If host approval cannot be obtained, continue source-level test design only. Never use untrusted arbitrary strategies as fixtures.

All historical **199 Critical/High findings stay REVIEW-OPEN; zero CVEs certified closed.** No \`main\`, old A11 372-archive Debian pin, A2/A15/A18 sources/images, live trading, Telegram, TELMIVO, broker, production, PR merge or runtime launch modification. PR #275 remains **DRAFT / DO NOT MERGE**.

**Final R27 status:** \`CERT_A19_R27_FIXED_EXPLICIT_OFFSET_HOST_REFERENCE_AND_A6_SOURCE_GATES_PASS__PHYSICAL_HOST_AND_FOURLANG_GUEST_EXECUTION_UNVERIFIED__A6_DENY_199_OPEN\`.
