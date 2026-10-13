# RUNTIME-A3 — Crash-persistent binding fence, no auto-retry

**Status:** Nonproduction GitHub source; no server changes, no installed plugin,
no real Al Brooks or NYFR adapters. No runtime authorization is granted.

## Protection gap closed

Prior A1 held `host.quarantined` only in Python process memory. After a
worker crash or restarted host, the set could disappear. A3 adds an explicitly
opt-in `DurableOfflineRuntime` wrapper and a separate local, private, SQLite
`DurableRuntimeLedger`.

For one binding identity (SHA256 of versioned `core_id`, `core_version`,
`instance_id`, `binding_id`), it writes a synchronous-FULL SQLite
`RUNNING` lease **before** invoking A1 host. This survives process exit.
A verified result commits `READY` **before** returning the inert CoreResult.
An exception commits `QUARANTINED`. A hard crash leaves `RUNNING`;
**both RUNNING and QUARANTINED permanently block retries** in this stage.
A second client/connection cannot claim the same RUNNING row.

Every mutation appends a SHA-256-chained transition record. The loader checks
SQLite integrity, each transition, contiguous event sequence and agreement
between final state and audited transitions. This detects many accidental
corruptions and uncomplicated tampering. However: **without an independently
stored signed known-good hash/pin, an attacker who controls the ledger files
can rewrite the database and hash chain**. Do not treat the chain as
tamperproof evidence or as a replacement for trusted external custody.

## Approval and recovery

`record_review` requires explicit operator authorisation, a pinned
evidence hash, a sanitized note and a claim that all workers are stopped.
This claim is not independently verified. The receipt stores only hashes,
not strategy code, tokens, prices or the note contents. Its verdict is
`REVIEW_RECORDED_NO_RELEASE`: it does not clear the A1 in-memory quarantine,
modify RUNNING/QUARANTINED state, reactivate a worker or publish Telegram.

**There is intentionally no reset/unquarantine API.** Reliable proof of host
cleanup, independent environment attestation, outbox reconciliation,
signed checkpoint and separately authorized new lease policy are prerequisites
to later recovery work.

## How it composes with prior stages

`DurableOfflineRuntime` wraps an **explicitly supplied**
`MultiLanguageOfflineHost`. Before creating a lease, it:
- enforces `MMT_NONPRODUCTION=1` and refuses `MMT_PRODUCTION=1`;
- requires operator acknowledgement and a previously reviewed runtime profile;
- revalidates artifact signature/hash, ABI, source quality and synthetic/replay
  event using the A1 framed request contract.

It never changes A1's default `WORKER_NOT_INSTALLED` registration and does
not start a worker on its own. Actual OCI permissions are still delegated to
A1 and remain blocked until the independent Rootless Docker + gVisor
certification. The audit DB is separate from the bot's operational database.

## Tests and limitations

`python -m pytest -q tests/unit/test_durable_runtime_a3.py`

Tests use **mocked A1 host only**. They verify full restart persistence,
crash-held RUNNING leases, failure quarantine, concurrent claim exclusion,
tampered SQLite/audit evidence, operator review without release, no profile,
no explicit operator approval, and basic file ownership/mode checks.

**Not provided:** live execution, signer trust, external attested audit pins,
automatic recovery, proof of no orphan container after process failure,
cross-host atomicity, database encryption, host-hardening certification,
multi-process active-lease shutdown coordination, a signed/verified operator
role source, broker orders or Telegram. No strategy engine is modified.

**Verdict:** `RUNTIME_A3_PERSISTENT_FENCE_PREPARED`, not
`ISOLATION_CERTIFIED` or `AUTORECOVERY_READY`.
