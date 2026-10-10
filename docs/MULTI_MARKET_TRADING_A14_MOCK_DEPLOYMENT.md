# Multi Market Trading — A14 Private Engine Package & Mock Service Deployment

**Scope:** isolated non-production Linux/CI rehearsal, building on A8–A13.
**No production host, no actual private strategy, no private source disclosure,
no Docker/systemd installation, no Telegram, no network, no trading.**

## What is implemented

`naseri_markets/a14_packages.py` provides `MockPackageDeploymentManager`
and strict `inspect_bundle`. A14 ONLY accepts synthetic, data-only ZIP files
containing exactly `manifest.json` and `payload.bin`. There is no dynamic
plugin loading, payload execution, networking, private NYFR import or owner
service deployment. The public repository holds ONLY the generic manager,
tests and fixture bytes.

A14 can be used only inside the OS temporary directory, with a 0700 instance
directory, SHA-256 content-addressed releases, a durable JSON active-pointer,
fsync/rename atomic writes, Linux advisory locks and expected-revision CAS.

The mock worker is a hardcoded, isolated Python process waiting for a one-byte
stdin shutdown signal. It does not read or execute `payload.bin` and is
not an actual external engine or service monitor. The manager never touches
arbitrary PIDs.

## Exact synthetic package contract (schema v1)

```json
{
  "schema_version": 1,
  "kind": "synthetic_private_data",
  "engine_id": "private_example",
  "engine_version": "1.0.0",
  "installation_id": "a13_fixture_install",
  "manifest_sha256": "<64 lowercase hex chars: A8 descriptor digest>",
  "trust_generation": 1,
  "release": "1.0.0",
  "mode": "offline_paper_only",
  "payload_sha256": "<64 lowercase hex chars: SHA256(payload.bin)>",
  "mock_behavior": "healthy"
}
```

The package archive SHA-256 must be independently pinned and passed as
`approved_sha256`; its value must not merely be copied from the same
untrusted supplier. This proves bytes equal the operator-approved value,
**not** publisher authorship or a production distribution signature.
`mock_behavior` may be `healthy` or `fail_start` to trigger deterministic
automatic mock rollback on a failed start.

ZIP bounds: <= 96 KiB archive, exactly two regular members, neither encrypted
nor directories/symlinks, <= 64 KiB per entry, <= 4 KiB manifest, <= 32 KiB
opaque synthetic payload. Unknown fields, duplicate JSON fields, NaN/Infinity,
path traversal entries, mismatched payload hashes, foreign installation/grant,
changed A8 descriptor, disabled A12 trust and expired/revoked grants fail closed.

## Operator lifecycle — non-production only

Prerequisite: use the real A8 private/disabled descriptor, A12 independently
pinned ACTIVE owner policy and valid Ed25519 offline grant, then complete A13
`prepare(...)` → `verify(...)`. A14 calls A13's *fresh* `health(...)`
before every installation, mock start or rollback; A13 binds the exact
installation, trust store, key, grant, revocations and disabled plugin.

```python
# Illustrative API only; not a production configuration.
mgr = MockPackageDeploymentManager(
    temp_root, provisioner=verified_a13,
    engine_id="private_example", installation_id="a13_fixture_install")
state = mgr.install(synthetic_zip_bytes,
    approved_sha256=independently_approved_package_hash,
    expected_revision=0, admission=fresh_a12_grant, now=checked_epoch)
state = mgr.start(expected_revision=state.revision,
                  admission=fresh_a12_grant, now=checked_epoch)
state = mgr.stop(expected_revision=state.revision)
# After staging a newer fixture release while STOPPED:
state = mgr.rollback(expected_revision=state.revision,
                     admission=fresh_a12_grant, now=checked_epoch)
mgr.close()
```

Transitions are `STOPPED → MOCK_RUNNING → STOPPED`. Only STOPPED permits
install/rollback. On successful activation the previously active archive is
retained as the rollback target, and the active pointer changes with an atomic
durable replace. If a newer fixture release has `fail_start`, A14 restores
the previous *verified* archive pointer and remains STOPPED, never secretly
enabling a live engine.

`stop` remains available after grant revocation for safety.
`reconcile_interrupted(expected_revision=...)` is necessary when persisted
state says running but the managing process restarted. It requires an
exclusive worker lock; an unrelated manager cannot adopt or kill a running
fixture process. This is NOT general-purpose daemon supervision.

## Validation

`tests/unit/test_a14_packages.py` tests installation, controlled start/stop,
upgrade/rollback, forced failed start recovery, byte tampering, archive
traversal, cross-installation substitution, stale revisions, symlink
rejection, worker locks, interruption reconciliation and real A12/A13
grant/revocation integration. A dedicated GitHub Actions workflow
runs these tests and Linux safety checks on disposable runners.

## Explicitly outstanding before any production deployment

- Trusted owner-controlled package publisher and independently verifiable
  signed release provenance (SHA pin alone does not authenticate a publisher).
- Strong supply-chain artifact signature/certificate enforcement, entitlement
  checks, secure package fetching, sandboxed private execution, real service
  supervisor and OS isolation.
- Persistent monotonic anti-rollback custody outside the host, transaction
  journal/crash recovery and full durable audit trail; A14 cannot defend
  against an attacker with local write access to **all** state files.
- Correct live revocation propagation and mid-run shutdown, mTLS owner
  network service, separate private-only distribution, container limits,
  backups and disaster recovery testing.
- Production-approved operator runbook, negative security review, strict
  service monitoring and explicit separate deployment authorization.

The source/version/manifest in `production_source/`, legacy v0.3.2 manager,
PostgreSQL and public signal routing remain untouched. **This A14 result
must not be described as production-ready private-engine deployment.**
