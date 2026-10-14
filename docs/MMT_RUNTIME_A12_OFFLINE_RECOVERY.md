# RUNTIME-A12 — Offline recovery and witness-key rotation rehearsal

**STATUS: NONPRODUCTION REVIEW ONLY — NO REAL MEDIA, TRUSTED FLOOR OR HOST.**

A11 accepts operator-retained witness receipts. A12 extends that review
contract with a dual-HMAC key handoff and new-witness genesis verification,
without connecting anything to a Worker dispatcher or enabling recovery.

## What was implemented

The isolated naseri_markets/runtime_a12_offline_recovery.py module:

- block_lost_media: reports BLOCKED irrespective of operator claims.
  No lost-media situation may automatically create a trusted new root.
- propose_key_rotation: accepts an exact latest witness receipt, its exact
  A10 anchor and a separately operator-supplied retained-floor copy. Requires
  the two copies to match byte-for-byte, validates A11 HMAC and A10 anchor
  association, then emits canonical, domain-separated, dual-key HMAC proposal
  referencing old/new witness IDs and old A10 head. Keys must be distinct.
- verify_key_rotation: checks both MACs, schema, audience and exact scope
  against caller-pinned new witness ID, key epoch, latest floor and anchor.
- verify_replacement_witness: checks a first receipt at sequence 1 under the
  new key, matching new witness identity and a strictly newer A10 anchor
  with the same A10 ledger ID. No Worker code is loaded or run.
- Proposals and reviews always report FALSE for execution, quarantine
  release, broker, Telegram, independent custody and activation.

A10, A11 and A6 source files remain unchanged. Keys are never stored
in the repository, a database or output objects. CI uses public fake keys.

## Operationally required, but NOT available

No independent witness computer, write-once or independently custodied media,
operator identity authority, trusted clock, vault or off-host monotonic
counter has been designated. No real key rotation or lost-media recovery
occurs in this stage.

**Key-loss rule:** if the old HMAC key, authentic latest old witness receipt,
its exact A10 anchor, or independently retained freshest floor is missing
or disputed, do not mint a new trusted root. Remain blocked.

**Freshness rule:** a compromised caller can submit an old valid receipt as
both the receipt AND supposed latest floor; equality does not authenticate
custody or freshness. Caller-provided key epochs can be stale. Two valid
proposals from the same old floor can fork without separately pinned
monotonic epoch evidence. This library cannot prevent that real-world attack.

HMAC is shared-secret message authentication, NOT an independent digital
signature. Old key compromise or forged transfer provenance defeats physical
identity claims. This component cannot erase old keys, revoke stolen keys
or provide trusted time.

## Mock-only validation

CI creates temporary A10/A11 SQLite with distinct fake keys. Tests exercise
inert dual-key handoff, replacement witness genesis, payload/HMAC forgery,
stale floors, lost old database or key, key reuse, wrong A10 ledger and
rollback, witness-sequence mismatch, operator/production denials, lost-media
always blocked and the mandatory A6 launch-denial regression.

No removable media, external account, VPS, Docker/Worker process, trading
core, broker, live database or Telegram bot is used.

**VERDICT: RUNTIME_A12_INERT_RECOVERY_REHEARSAL_PREPARED_EXTERNAL_CUSTODY_BLOCKED.**
