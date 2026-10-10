# Multi Market Trading — A13 Offline Private Engine Provisioning

**Status:** implementable, testable **GitHub-only NON-PRODUCTION** preparation.
There is **NO VPS**, actual private NYFR connection, Docker installation,
remote service provisioning, key generation/custody, Telegram delivery, live
data acquisition or order execution in this stage.

## Real A13 workflow

A13 introduces a metadata-only private-engine provisioning lifecycle in
`naseri_markets/a13_provisioning.py`, separate from the public plugin
manager and separate from the trust store.

```text
Public Multi Market Trading
  A8 PluginManager: registered PRIVATE/external_contract, disabled
    + A12 TrustStore: independently pinned ACTIVE trust generation
    + A13 exact plan: pinned digest, owner fixture DNS, manifest,
      issuer policy generation, CA and leaf fingerprint
       |
       v
    PREPARED (persisted, metadata-only)
       |
    A12 verified Ed25519 signed PAPER grant and pinned certificate identity
       |
       v
    OFFLINE_VERIFIED (metadata; no service installed/connected)
       |
    Recheck fresh evidence and trust policy on each health query
       |
    SUSPENDED -> staged new plan (monotonic CAS) or RETIRED
```

### Operator protocol

1. Review the private owner and license issuer **out of band**. Verify an
   independent SHA-256 of the exact plan; hashing a self-supplied plan
   does **NOT** authenticate its publisher.
2. Register the approved private descriptor and active A12 trusted policy
   with the existing managers. The plugin MUST remain **disabled** to
   prepare it. A13 never toggles the engine.
3. Call `OfflineProvisioner.prepare(raw, approved_sha256=...)` with the
   strict schema v1 `offline_paper_only` plan. The plan cannot contain
   URLs, executable paths, passwords, commands, code or hidden fields.
4. To verify readiness, supply **fresh** A12 `OfflineAdmission` evidence
   with a valid signed grant, exact engine identity/version/manifest,
   matched installation and policy generation, trusted certificate bytes,
   clock and local revocation state. `verify(...)` creates
   `OFFLINE_VERIFIED` and increments the revision atomically.
5. After process restart, the status remains stored but is
   **RECHECK_REQUIRED** until new trusted evidence is presented.
   `health(..., admission=..., now=...)` refuses revoked, expired,
   disabled/removed/reinstalled or rotated engines. The health card
   ALWAYS reports `external_engine_connected=false` and
   `live_trading_permitted=false`.
6. `suspend(engine_id, expected_revision)` blocks further affirmative
   readiness, and only SUSPENDED metadata may be re-prepared with
   a fresh pinned plan and monotonically nondecreasing policy generation.
   `retire(...)` is terminal. All transitions have a durable metadata
   audit and expected-revision compare-and-swap fences.

### Meaning of provisioning

A13 `PREPARED` means a PLAN was evaluated, NOT a package installed.
A13 `OFFLINE_VERIFIED` means the offline metadata and signed grant
were checked at that specific time; it is **NOT** proof the owner
service is running or authenticated remotely. Physical provisioning,
real process supervision and release rollback are NOT available here.

The file `a13_provisioning.py` deliberately imports **no** `requests`,
`socket`, remote GitHub, `subprocess`, dynamic plugin importer or
private NYFR source. Its lifecycle SQLite is isolated from PostgreSQL,
the A3 Telegram outbox and private trade/market data. No live
trading or publication can be enabled by any A13 transition.

### Security limits / next production gates

The A12 trust state is a **local SQLite file**, not independent
monotonic counter custody. Restoring a stale snapshot of all
installation state is not prevented by A13. For actual deployment,
separately build secure owner-controlled package/service acquisition,
trusted provenance/entitlement verification, mTLS remote identity and
certificate issuance/rotation, externally pinned rollback floors,
revocation propagation, secure key storage and operator-reviewed
run/stop/deploy/rollback runbooks.

These are **NOT completed** by A13. The historical v0.3.2
`crypto-price-action` package, its frozen manifest, Dockerfile and
Compose/PG volume, and the independent `multi-market-trading==0.4.0rc1`
distribution/version remain unchanged.

Tests are in `tests/unit/test_a13_provisioning.py` and
`.github/workflows/a13-offline-provisioning.yml`. The latter requires
the A12 cryptography test dependency on a disposable runner, performs
fail-closed negative test cases, verifies frozen source safety,
and builds the public-only independent wheel to confirm no private
strategy or issuer signing key is included.
