# RUNTIME-A6 — mandatory Worker launch hard stop

**State: nonproduction preparation; default DENY; no independent host certification.**

## Purpose and exact boundary

The A4 signed checks prove possession of a shared signing key, not genuine
gVisor/rootless isolation. The A5 SQLite challenge ledger consumes review
receipts once, but its output has `execution_authorized=False`. A5 is
review-only and is not a security capability.

A6 adds an unconditional launch fence at TWO choke points in the
`MultiLanguageOfflineHost` A1 call graph:

1. In `evaluate()`, **after safe source/event framing** and **before**
   rootless daemon probing or an injected/mocked OCI dispatcher.
2. In `_run_oci()`, **before Docker command construction**, process creation,
   environment handling or any child cleanup calls. Direct calls also deny.

A3's `DurableOfflineRuntime` reaches this same A1 `evaluate()` fence. A3
still records a failed/quarantined durable lease when it delegates and A6
denies; no release or reset is implemented. These are the A1/A3 polyglot
runtime dispatcher paths; the separate A2 benign fixture CLI remains a
standalone test harness, **not** a trusted sandbox/production executor.

## What is checked

The inert A6 review validates nonproduction-only environment, enabled
pinned/reviewed profile, bounded framed input and exact policy SHA-256.
Optional A5 `ConsumedReview` objects are accepted only as diagnostic
review-only records. A valid receipt, valid image SHA, positive-looking
fixture, or setting an environment variable cannot bypass the fence.

The `require_worker_launch` entry deliberately **has no allow path**:
it always raises `A6_INDEPENDENT_HOST_CERTIFICATION_REQUIRED` on a
well-formed request. Invalid profile, frame or environment fails earlier.
It cannot issue capabilities, execute a subprocess, enable broker/Telegram,
or release quarantine.

## Verification and limitations

Run `python -m pytest -q tests/unit/test_runtime_a6_dispatch_fence.py
tests/unit/test_multilang_runtime_a1.py tests/unit/test_durable_runtime_a3.py
tests/unit/test_runtime_a5_nonce_custody.py` in an isolated test environment.

Negative cases cover four languages, direct internal OCI calls, A1 and A3,
mocked/forged worker results, consumed A5 receipts, invalid environment,
malformed framed inputs and source-position check. No Docker host, trade
engine, Telegram, PostgreSQL, installed strategy or exchange is touched.

**Not a complete platform security proof:** Python modules can be replaced
by an adversary with code-execution privileges, and other independent
subsystems are outside A1/A3. A2's standalone benign-fixture script does not
constitute an A1 authorization route. Kernel isolation, independent probe
custody, receipt rollback resistance and per-launch short-lived grants
remain unresolved. Do not remove the hard stop until a later *separately
authorized* implementation and disposable-host acceptance has passed.

**Verdict:** `RUNTIME_A6_PRELAUNCH_FENCE_PREPARED_NO_EXECUTION`.
