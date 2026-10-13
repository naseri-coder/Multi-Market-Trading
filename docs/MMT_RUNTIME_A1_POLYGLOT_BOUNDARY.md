# MMT-RUNTIME-A1 — Polyglot CoreResult execution boundary

**Scope:** GitHub-only, nonproduction source candidate. Does **not** install or
certify runtime images or modify any trading strategy. No adapter has been
created for the real Al Brooks or either private NYFR strategy.

## Four language routes
- Python: `.py` inspected by existing SDK AST lint; the prior Stage-4 Python
  OCI worker is retained unchanged. This new entrypoint is a proposed common
  framed protocol, NOT an installed replacement for the reviewed Python worker.
- JavaScript: `.js`, UTF-8 intake, requires a separately built, audited
  pinned Node OCI worker.
- TypeScript: `.ts`, UTF-8 intake, requires a separately built, audited,
  pinned compiler/transpiler + interpreter OCI worker; no compiler is
  supplied or invoked by the control-plane.
- WebAssembly: `.wasm`, header check only, requires an audited pinned
  WASI/Wasmtime OCI worker with fuel/memory/clock and filesystem policies.

**This commit adds the host boundary, not functioning interpreter images.**
Untrusted JS/TS/WASM is never executed in the ChatGPT session, on any server,
or in the parent bot. The unit tests only mock worker responses. There are
no real multi-language execution/sandbox certification results at this stage.

## Wire protocol (runtime-a1-framed-v1)
Input standard input:
1. Four-byte unsigned big endian artifact length.
2. Exact SHA256-pinned source or WASM bytes.
3. Canonical JSON containing `abi_major`, `abi_minor`,
   `protocol=RUNTIME_A1_FRAMED_V1`, `runtime_kind`,
   `artifact_sha256`, `manifest_digest`, `input_digest`, `event`.
The worker (NOT in this stage) must recompute each digest, parse exact
schemas, refuse trailing data, enforce limits and output **one** canonical
Core API v1 JSON result without printing logs to stdout.

Output is restricted by the already-existing
`secure_plugin_runtime_v1.parse_core_result`:
`abi_major`, `abi_minor`, `core_id`, `core_version`, `instance_id`,
`binding_id`, `observed_at`, `input_digest`, `decisions`.
Host checks exact identity, provenance, no-lookahead, setup catalog,
decimal price geometry and position management against the same original
`CoreManifest` and `CoreInput` contracts.

## Security and availability
- Default registry **all languages = WORKER_NOT_INSTALLED**, regardless of
  an uploaded file or enabled panel toggle.
- Explicit operator-created `RuntimeProfile` requires a pre-reviewed
  image with exactly matching `@sha256` digest and an enabled Stage-4
  `SecurePluginPolicy`. The image digest is identity NOT an independently
  verified publisher signature; operator review flag is not cryptographic
  proof of safe code.
- `build_polyglot_command` reuses Stage-4 rootless + gVisor OCI flags:
  no network, no IPC, read-only, cap-drop ALL, no new privileges, no
  bind-mount, nonroot UID, CPU/RAM/PID limits, no external credentials.
  All source bytes go to child **stdin**, never argv or Docker environment.
- Only `SYNTHETIC` or `REPLAY` data admitted; `FORWARD` refused.
  Output remains an inert CoreResult without trade, broker or Telegram
  permission.
- Bounded input 192 KiB, source still bounded by current Intake stage,
  worker output 16 KiB, deadline from Stage-4 policy (0.5–10s).
  Failure or forged result quarantines the binding in memory.
- Actual host rootless Docker/gVisor probe and adversarial hostile-code
  containment remain outstanding. On failure to prove container cleanup
  the host fails closed, but independent orphan detection is required.
- In-memory quarantine is **not persistent**; restarting the program
  does not constitute an approved recovery mechanism. Before real usage
  add a durable audit log, instance lifecycle and explicit recovery fence.

## Next phase prerequisites
1. Build exact, independently reproducible pinned worker OCI images for all
   four languages, with no package/network fallback and separately reviewed
   compiler/WASM engines.
2. Run real harmless worker roundtrips on disposable authorized rootless
   Docker/gVisor host and negative tests for network, filesystem, timeouts,
   process crash, CPU/RAM, PID and credential isolation.
3. Add signed worker-profile admission, durable quarantine, cancellation
   recovery, per-binding quotas and crash-safe outbox/integration.
4. Only after independent approval, connect inert CoreResult to the existing
   Stage-16 PAPER coordinator through a separately authorized adapter.
5. Real strategy adapters, host deployment, Telegram and broker remain
   explicitly out of scope.

**Verdict:** RUNTIME_A1_HOST_POLICY_AND_WIRE_PREPARED;
POLYGLOT_EXECUTION_AND_HOST_ISOLATION_NOT_YET_CERTIFIED.
