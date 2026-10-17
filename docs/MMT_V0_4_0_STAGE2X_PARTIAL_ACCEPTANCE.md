# MMT v0.4.0 — Stage 2X: read-only PostgreSQL admission and blocked-gate inventory

**Date:** 2026-10-17  
**Immutable tested code:** f8d3883c86b17b707d97fdd07253c645f4eb9886  
**PR:** #352 — Draft/open/unmerged  
**Verdict:** STAGE2X_PARTIAL_POSTGRES_CONNECTIVITY_PASS__MIGRATIONS_BLOCKED__RELEASE_DENIED

## 1. Genuine, isolated PostgreSQL connectivity

A temporary PostgreSQL 16.15 process ran as nonroot UID 70 in an internal-only Docker network with zero published host ports, tmpfs-only database storage and a read-only root filesystem. A separate nonroot Python 3.12 client verified the intended empty scratch database name, database role and internal server address.

The repository test tests/integration/test_database_connection.py ran against that real temporary server and returned **1 passed, 0 failed, 0 skipped (0.51s)**. The test exercised the application database health-check and SQL session. This is one of the **38** previously skipped PostgreSQL-gated cases; **37 other cases remain untested**.

**No Alembic schema migration was executed.** The proposed migration on the Telmivo-connected host was blocked by the environment's safety control. Do not attempt to bypass the block. No write-capable integration test, downgrade or production database migration was performed. The temporary PostgreSQL container and private Docker network were **both destroyed and their absence verified**. No production database, volume, broker, Telegram token or trading service was accessed.

**Independent-runner qualification:** An isolated Docker container still shares the underlying Telmivo-connected machine. It is **not** an independently attested disposable nonproduction host and does not meet that separate release condition.

## 2. Safe, read-only schema revision audit

All **23** Python migration revisions were statically parsed. Revision IDs and parent references were coherent, with a single root (20260901_0001) and a single head (20261013_0023). All migration files contained upgrade and downgrade entrypoints. Actual offline Alembic heads output confirmed 20261013_0023 (head).

This is a source graph check, **not** proof that actual PostgreSQL upgrade, downgrade or rollback succeeds.

## 3. Offline recovery and supply-chain tests

Under nonroot Python 3.12 with network disabled, the following existing test groups were re-executed:

- **42/42 passed:** A12 and PAPER08 offline recovery, R32 recovery review kit, and signal recovery policy.
- **135/135 passed:** simulated signed artifact preflight, custody, preview packaging, release provenance and supply-chain negative/admission tests.

These are **overlapping subsets** of the Stage2W complete suite (7,584 passed, 76 skipped); they are not 177 additional unique tests. Fixture signatures and test-only keys are **not** a trusted, independently signed public release artifact. The existing tested Wheel checksum is 33316353c0dcf0c5c3cd5b8926d87b70cfdd589e1ea3d5061f8ee90e127825fc and remains unsigned for publication.

## 4. Remaining acceptance matrix

| Outstanding coverage from the earlier 76 skips | Cases | Why still blocked |
| --- | ---: | --- |
| Real isolated PostgreSQL schema, migration and rollback | 37 | Migration execution blocked on Telmivo-associated host |
| Genuine ephemeral GitHub-hosted runner | 32 | No eligible attested runner and Actions quota constrained; never spoof GITHUB_ACTIONS |
| CERT-A5 committed benign fixtures | 4 | Explicit opt-in and test policy prohibit execution on a production machine |
| Public market-data smoke | 2 | Separate public-network opt-in required; no private credentials |
| **Total unexecuted** | **75** | One genuine PostgreSQL health test now passed |

Independent signer provenance, installed PAPER restart/rollback and release admission remain missing even if all 75 tests eventually pass.

## 5. Required next work before release

Continue **Stage 2X**, do not invent a full acceptance:

1. Obtain a genuinely independent ephemeral **nonproduction** environment. Provision dedicated scratch PostgreSQL with no production mounts, apply/verify Alembic migrations and downgrade/upgrade on that disposable database, then run the **37** remaining integration cases.
2. Execute the **32** runner tests only on an actual eligible ephemeral GitHub runner. Do not spoof its capability or claim the quota restriction is a pass.
3. Run the **4** CERT-A5 harmless-fixture cases only on a nonproduction machine with explicit opt-in. Consider the two public-data smoke tests separately and permit no real account keys.
4. Establish real installed-PAPER restart/recovery/rollback and a verified independent release-signing chain with an approved trusted public signer fingerprint. Keep private keys off shared test hosts.
5. Preserve PR #352 in Draft/open/unmerged status. **No main merge, official tag, Production mutation or LIVE trading.**

**Status: STAGE2X_PARTIAL_NOT_CLOSED__OFFICIAL_RELEASE_BLOCKED**.

Machine-readable evidence: docs/evidence/MMT_V0_4_0_STAGE2X_PARTIAL_ACCEPTANCE.json
