# Multi Market Trading — Stage 4: Secure Plugin Runtime V1

**Status:** Non-production source candidate. No deployment, no public plugin marketplace, no validated hostile-code containment, no real orders, no Telegram publication.

**Scope:** an *additive* `naseri_markets/secure_plugin_runtime_v1.py` implementation. Stage 3's `core_api_v1.py`, old `trusted_custom.py`, legacy v0.3.2 process, PostgreSQL, Telegram, brokers and private NYFR source remain unchanged.

## 1. Fundamental boundary

Third-party core source is **never** imported into the parent trading-bot Python process. The host owns the market binding, source verification, serialized market data, result schema and authorization decision. The untrusted worker may only calculate an *inert* `CoreResult` describing one or more setups, entry intent, optional management or exit intents. No output can authorize a broker order, Telegram publication, account login, resource allocation or portfolio-risk bypass.

The Stage 4 host accepts only **synthetic or replay inputs** supported by Stage 3, not a live market feed. Plugin source must be an approved, SHA256-pinned UTF-8 Python single-file script with the Python 3.12 standard library. SHA256 protects byte identity, **not publisher identity, code safety or profitability**. Registration, reviewer attestation and publisher signatures remain separate future contracts.

## 2. Conservative execution gate

`SecurePluginPolicy(enabled=False)` is the default. Activation is refused unless:

- the invoking process is **non-root**;
- the image uses an exact `image@sha256:<64 hex>` reference, is already loaded, and Docker runs with `--pull=never` (the image must be independently reviewed and verified);
- Docker endpoint is the **calling user's own rootless Unix socket** at `unix:///run/user/<uid>/docker.sock`, with matching socket owner; `/var/run/docker.sock`, remote Docker endpoints and symlink sockets are prohibited;
- Docker daemon reports `name=rootless` in its `SecurityOptions`;
- an operator has independently installed and verified **gVisor `runsc`** on that rootless daemon. The host explicitly requests `--runtime=runsc`, with **no fallback** if absent;
- the approved plugin digest matches exact input bytes and input data satisfy Core API v1.

These conditions narrow the attack surface; **they are not proof of complete isolation**. The runtime itself, Linux kernel, daemon, image and host must still be patched and validated on a disposable machine without valuable files or credentials. A compromised Docker client or gVisor/kernel vulnerability can still affect the host.

## 3. Mandatory container containment switches

`--network=none`, `--ipc=none`, `--read-only`, `--cap-drop=ALL`, `--security-opt=no-new-privileges`, `--user=65534:65534`, `--pids-limit=32`, `--memory=128m`, `--memory-swap=128m`, `--cpus=0.5`, `--ulimit=nofile=64:64`, `--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=8m,mode=1777`, `--pull=never`, `--runtime=runsc`.

No host bind mount, Docker socket inside the container, host network, privileged mode, inherited environment, credentials, account IDs or secret-bearing files are handed to the worker. `python -I -S` executes a static bootstrap, receiving the code and single market-event request **over standard input**. Neither script bytes nor trading data are present in CLI arguments. Standard error is discarded by default; plugin stdout is bounded to 16 KiB. Parent requests are capped at 192 KiB; source at 64 KiB, and wall-clock timeout at 0.5–10 seconds. Detached daemon-side containers are *best-effort* force-removed by unique random name on exit/error; failure to prove cleanup requires manual isolated-host inspection.

## 4. Data and API contract

Host sends one framed payload:

`4-byte unsigned big-endian source length | exact source bytes | UTF-8 JSON request`

JSON request keys: `abi_major`, `abi_minor`, `manifest_digest`, `input_digest`, `event`. The event is the immutable, host-selected Stage-3 `CoreInput`; it includes only binding identity, provider-normalized prices and necessary prior-candle/position geometry. Account balances, API tokens, leverage, per-position capital, private routes and broker credentials are **absent**.

Worker must emit exactly one JSON object with keys:

`abi_major`, `abi_minor`, `core_id`, `core_version`, `instance_id`, `binding_id`, `observed_at`, `input_digest`, `decisions`.

Each decision has required `decision_id` and `kind`, with optional Stage-3 `CoreDecision` fields. Prices are **decimal strings**, timestamps timezone-aware ISO 8601, and decisions pass Stage-3 `validate_core_result()`. Duplicate fields, extra schema fields, nonfinite values, stale identity/digest/revision, incorrect setup, bad entry/stop/target geometry or unauthorized trailing all fail closed. A failed invocation quarantines that binding **in memory** until an explicitly managed later recovery. There is no persistent quarantine, external audit ledger or journal in Stage 4.

Minimal illustrative single-file *no-setup* worker (not a profitable strategy):

```python
import json
import sys

request = json.load(sys.stdin)
event = request["event"]
print(json.dumps({
    "abi_major": 1, "abi_minor": 0,
    "core_id": event["core_id"],
    "core_version": event["core_version"],
    "instance_id": event["binding"]["instance_id"],
    "binding_id": event["binding"]["binding_id"],
    "observed_at": event["observed_at"],
    "input_digest": request["input_digest"],
    "decisions": [{"decision_id": "illustrative_1", "kind": "no_setup"}],
}))
```

This example emits a structurally valid *no-setup* response when the provided manifest and Core API v1 market event are compatible. It does not evaluate a trading strategy, publish a signal or provide any execution permission. A future developer SDK should include a complete multi-setup sample and conformance pack without copying trusted host modules into the untrusted container.

## 5. Validation evidence and limitations

The Stage-4 unit tests exercise fail-closed default, privileged-user/socket and unpinned-image denial, exact OCI containment switches, bounded parser, duplicate-key/extra-key and float rejection, replay binding and digest match, forged stop/target and unauthorized action denial, approved source SHA, mocked request framing, quarantine and missing daemon. Stage-3 contract tests are rerun without modifying Stage-3 modules.

**Local tests use mocks for the Docker/gVisor launcher.** They validate arguments and security *policy*, **not real kernel/runtime isolation**. The following are still required on a disposable authorized rootless+gVisor machine before a claim that arbitrary third-party code can run safely:

1. Independently verify rootless Docker/gVisor installation, pinned Python 3.12 OCI image provenance and daemon policy; confirm `runsc` is actually used rather than silently falling back.
2. Observe a harmless synthetic Core API v1 worker round-trip, deterministic output, timeout/oversize and forced cleanup.
3. Run safe negative tests proving blocked DNS/TCP, blocked host filesystem and credential reads, socket absence, memory/CPU/PID limits, and lack of privileges; observe from both host and inside isolated worker.
4. Test host restart, daemon crash, container orphan detection, concurrent invocations, per-user quotas and persistent quarantine/audit before enabling a public plugin service.
5. Obtain a security review and patch/vulnerability response plan. Keep the host separate from real trading/account servers.

**Current verdict:** `STAGE4_POLICY_AND_OFFLINE_PARSER_IMPLEMENTED__HOST_ISOLATION_NOT_VERIFIED`.

The legacy `trusted_custom.py` remains explicitly trusted-local only and **must never be presented as safe untrusted-code execution**. Do not wire Stage-4 to its arbitrary-Python executor as a fallback. No publication/real-money authorization follows from this stage. No public/private NYFR copying.

## 6. Next-stage integration requirements

Stage 5 should integrate provider-neutral market events only *after* isolated-host acceptance, carry instance/binding IDs throughout orchestration, add durable dedup/quarantine/evidence, and retain separate permissions for Telegram and orders. Correct behavior remains deny-by-default for unavailable/unauthorized exchanges/brokers. Production rollout remains a separate explicit authorization.
