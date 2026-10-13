# MMT-RUNTIME-A2 — actual fixed-fixture language workers

**Mode:** GitHub-only nonproduction preparation. This is an implementation
of the A1 framed protocol with interpreter dispatch. It is **not** an
independent security certificate for arbitrary uploaded strategies.

## Actual interpreter routes

The standalone `scripts/runtime_a2_worker.py` accepts exactly the A1 frame:
4-byte artifact length, exact artifact, strict JSON request including canonical
`event`, **canonical `manifest`** and digests. It validates SHA-256 of source,
event, manifest and the expected ABI, kind, synthetic/replay origin and identity
**before** invoking a language interpreter. There is no direct model/strategy
import into the trading bot's process. All four routes return JSON
**decisions only**. The trusted host supplies identity, wraps CoreResult and
reruns the existing strict `parse_core_result` check.

1. Python 3.12: source defines `evaluate(event)`, returns list of decisions.
   Fixed child launcher uses `python -I -S`; never shell.
2. JavaScript: source defines `function evaluate(event)` returning decisions.
   Node runs it in its `vm` engine; **Node vm is NOT a security boundary**.
3. TypeScript: source defines `function evaluate(event: unknown)` returning
   decisions. Pinned TypeScript transpilation via `transpileModule`; same Node
   VM and runtime risk. No on-demand network package installation.
4. WASM: guest exports memory and `evaluate(ptr:i32,len:i32)->i64`.
   Input JSON bytes at linear offset 0. Return is high 32 bits pointer, low 32
   bits byte count, referring to UTF-8 JSON array of CoreDecision records.
   The host rejects imports, out-of-range memory and oversized results; Wasmtime
   fuel and memory limits apply. No WASI imports, network or filesystem.

## What is actually tested

`tests/unit/test_runtime_a2_worker.py` executes four **fixed harmless**
source/WASM fixtures through real Python, Node, TypeScript and Wasmtime
binaries on an ephemeral GitHub-hosted CI job. It verifies structured Core API
v1 identity, digest, type checks, corrupted file/manifest/event, unsupported
kind, oversized frames, WASM imports, and default-deny registration. The
test checks must not skip the WASM scenarios.

A candidate Dockerfile exists at `deploy/runtime_a2/Dockerfile`. A
separate CI job **builds the nonproduction image and runs four committed,
harmless fixtures with no network, a read-only root, nonroot uid and
resource restrictions**. GitHub-hosted Docker is not rootless+gVisor for
this job. These positive smoke tests do not simulate hostile code.
The recipe is **not** an authorized, signed or pinned final image; its
base tag and apt-installed Node remain to be locked to independently
verified exact package/image digests. Running the candidate on a
non-rootless host is NOT proof that arbitrary uploads are contained.

## Non-negotiable security gate before untrusted execution

- Operator-approved final OCI image digests **separately** for Python, Node,
  TypeScript and Wasmtime, including reproducible dependency attestations.
- A separately authorized disposable **rootless Docker + gVisor runsc** host,
  not the trading production host; verify seccomp/no-network/no-bind-mount,
  resource limits, filesystem/credential refusal, nonroot uid and runtime
  provenance from inside/outside guest. The A1 host remains disabled by default.
- Real OCI end-to-end positive and adversarial negative roundtrips, cleanup
  proof, daemon failure, orphan response, persistent quarantine, host restart,
  quotas and log redaction.
- The Python and Node children are **not sandboxes** by themselves. Do not run
  any uploaded/unreviewed scripts on the GitHub runner, in ChatGPT container,
  or on TELMIVO/trading servers. CI only executes source fixtures committed
  with the tests.
- No forwarding of broker orders, Telegram messages, API secrets, accounts
  or production data. There are no real strategy adapters or deployments.

## Verdict taxonomy
- `A2_WORKER_FIXED_FIXTURE_PASS`: all four real interpreter test roundtrips
  passed; code and ABI ready for independent OCI security audit.
- `A2_ISOLATION_CERTIFIED`: **NOT GRANTED** by this phase; a completed host
  security audit with genuinely verified rootless/gVisor is required.

No existing Al Brooks, NYFR R0, First Follow-up or Public Custom Engine
source was changed. The Core API validation contract is unchanged.
