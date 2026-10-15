# Stage 11 — Reviewed Core Parameters in the Stage-12 PAPER Control Panel

**STATUS: NONPRODUCTION · CONTROL PLANE ONLY · NO STRATEGY EXECUTION / LIVE ACCESS · NO DEPLOYMENT**

## Why reuse, not rebuild

The existing `naseri_markets/core_parameter_guard_v1.py` (Stage 6) already strictly validates complete numerical, boolean and choice settings against an **externally host-pinned** JSON contract. The existing `naseri_markets/trading_control_center_v1.py` (Stage 12) provides private owner/admin scope, optimistic CAS revisions, one SQLite store and a hash-chained audit log. This stage joins those two **existing** components without introducing a separate settings authority, schema interpreter, new engine or broker runtime.

Only manifest-backed reviewed core listings may have parameter settings. The built-in Al Brooks public reference remains **REFERENCE_ONLY**; no genuine public Al Brooks Core API port is asserted. Owner-only custom core entries remain private/ACL-filtered. The private NY First-Reversal implementation, legacy 0.3.2 package, server and production SQLite/PostgreSQL volumes remain out of scope.

## Host-authoritative schema pins

The trusted application supplying `CoreListing` may optionally provide **both**:

- `parameter_schema_bytes` — exact reviewed Stage-6 JSON schema, max 48,000 bytes.
- `trusted_parameter_schema_sha256` — an independently approved 64-character lowercase SHA-256 pin retrieved from the trusted host inventory, **not supplied by the incoming Telegram command**.

A missing pair, hash mismatch, nonexistent CoreManifest or inconsistent manifest core ID/version refuses the listing. A source hash proves integrity against the pinned bytes, *not publisher signing, client authorization, strategy soundness or execution eligibility*. No schema is synthesized from user input. A schema can only be assigned to a reviewed `CoreManifest`. For Stage-6 grammar, exact decimal-string values, bounded grids and static cross-field relations, see `docs/CORE_PARAMETER_GUARD_STAGE6_V1.md`.

## Stage-12 single-store atomic contract

Exactly one additional table, `t12_parameter_settings`, is created in the existing **dedicated nonproduction Stage-12 SQLite file**. Its row is keyed by `instance_id` and records `core_id`, `core_version`, `schema_sha256`, `settings_sha256`, complete validated JSON bytes (as UTF-8 text) and `saved_revision`. This is an **additive local schema extension**, not an operational/production migration and not another SQLite ledger.

`set_core_parameters(actor_id, instance_id, settings_bytes, expected_revision)` runs through the **existing** Stage-12 `_mutate` transaction. It checks the operator ACL and instance owner, the expected revision, current reviewed CoreListing/Manifest identity and schema pin, and refuses edits while **any** analysis/PAPER/dry-signal requested flag is enabled. Only then does the Stage-6 guard validate the **entire** settings envelope (no defaults, missing entries, coercion or extra values). The same transaction writes the settings row, advances the instance CAS revision, and appends a Stage-12 audit-chain event containing only the digest, never raw parameter values.

On reopening `inspect_core_parameters` rechecks exact schema/version and stored content SHA256. Enabling any requested mode with a host-reviewed schema requires an already validated parameter row; `preview_bindings` also checks it. If the saved row exists but the host schema pin is absent or changed, access refuses rather than trusting historical values. The operator must turn requests OFF and supply an entirely new pinned settings set. Independent host trust/pin custody is required.

**Critical limit:** A saved Stage-11 parameter set **is not yet passed to the strategy evaluation API**. Existing Core API v1 and Stage-16 PAPER replay remain unchanged and do not automatically consume or apply these values. The new panel manages bounded, reviewed *research configuration data only*; claiming that changing `fast_period` changes Brooks execution or creates new live signals would be false. A separate, approved core-specific adapter and replay-equivalence tests are required before the settings affect strategy semantics. The existing Stage-13 reliability checker does not include the additional table in its aggregated data digest; integrity is checked by the Stage-12 on-read guard and Stage-12 audit event, not by independent external attestation.

## Private Telegram operator interface

The existing opt-in Stage-12 Telegram panel gets two commands in the **same** registered private-only development application (it never starts another poller):

- `/mmt12_params INSTANCE_ID` — read-only review of parameter field names/types and current schema/settings digests. Raw saved values are never echoed.
- `/mmt12_param_set INSTANCE_ID EXPECTED_REVISION FULL_JSON` — full Stage-6 versioned JSON settings envelope, bounded to a single private-chat message up to 4096 UTF-8 bytes, explicit expected revision and exact approved host schema. The command never tries an automatic retry. Refusals return only a generic warning without reflecting supplied settings.

Example schema-owned fixture values (not real strategy parameters):

```json
{
  "schema_version": 1,
  "core_id": "fixture.contract.check",
  "core_version": "1.0.0",
  "values": {
    "fast_period": 10,
    "slow_period": 26,
    "stop_buffer": "0.25",
    "confirmation": true,
    "average_type": "ema"
  }
}
```

Replace the identities/fields only with a genuinely **host-approved** schema for the specific manifest. Do not submit API credentials, personal data or proprietary source over Telegram. Telegram retains messages under its platform policies; this example is suitable only for non-sensitive, private development data. The system does **not** install an external authentication server or grant private channels, real-signal delivery, actual account eligibility or LIVE trading.

## Test and acceptance

The new `tests/unit/test_stage11_reviewed_core_parameters_v1.py` covers matching and forged/missing host pins, requested-mode preconditions, owner-only visibility, CAS stale updates, exact schema matching, missing and unsafe values, cross-field fast/slow constraints, restart integrity, tampering, missing pins, private-chat UI and absence of reflected sensitive input. Legacy Stage-12 tests must remain passing. No program logic calls the strategy engine with saved settings, sends signals, places broker orders or touches Production.

```bash
python -m pytest -q \
  tests/unit/test_stage11_reviewed_core_parameters_v1.py \
  tests/unit/test_core_parameter_guard_v1.py \
  tests/unit/test_trading_control_center_v1.py
```

Run all protected GitHub Actions on the **final head** before merging. Do not weaken protected source/package restrictions, introduce default-on semantics, modify main without green CI, migrate legacy runtime, or start Stage 12 of this roadmap under this authorization.

**Accepted status only:** `STAGE11_REVIEWED_PARAMETER_PANEL_NONPRODUCTION_PASS` if focused, legacy and protected checks succeed. **Release status remains `PRODUCT_NOT_READY_FOR_PUBLIC_OR_LIVE_RELEASE`.**
