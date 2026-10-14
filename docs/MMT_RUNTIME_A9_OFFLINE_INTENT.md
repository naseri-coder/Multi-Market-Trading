# RUNTIME-A9 — short-lived, one-time, revocable INERT review tickets

**Status: nonproduction, simulation-only. No execution grants.**

A9 builds a persistent, strictly scoped demonstration of ticket lifecycle
rather than turning a signed claim into an actual Worker launch permission.
The A6 hard stop remains unchanged, and A9 is not wired into A1/A3 launch.

## Contract

- Exactly one Python, JavaScript, TypeScript or WASM reviewed A1 profile.
- Complete A4 policy SHA-256 (which binds the OCI image and its declared policy),
  plus operator-supplied Worker SHA-256, source SHA-256 and request SHA-256.
- A5 ConsumedReview receipt SHA-256, host and issuer IDs.
- New 192-bit random nonce, canonical JSON, HMAC-SHA256 with domain separator.
  Operator supplies an out-of-band test signing key (minimum 32 bytes).
- Valid for 1 through 300 seconds, based on exact caller-supplied UTC seconds.
- Explicit nonproduction environment, authorized operator and acknowledgement
  required for issuance, spending and revocation.
- Owner-only local SQLite file, FULL synchronous commit, BEGIN IMMEDIATE
  transitions: ISSUED -> SPENT or ISSUED -> REVOKED. At most one reviewer
  can spend a ticket; restart and second-connection replay are denied.
- Ledger stores the ticket SHA-256, scope and state, not plaintext token or
  operator HMAC key. Result objects explicitly mark ALL broker, Telegram,
  launch and quarantine release permissions false.

## What has NOT been proven

A Python ConsumedReview instance does not by itself prove A5's database
issued it. A5 currently does not return the reviewed Worker digest as part
of the consumed object; the binding supplied to A9 is a caller assertion,
not independent measured provenance. A8's local SHA-256 matching also does
not prove publisher authenticity. The HMAC authenticates only shared-key
possession, not an independent reviewer.

The SQLite state is not anchored off-host. A privileged attacker may roll
back or rewrite the file; caller-supplied time is not a trusted clock.
This is NOT a safe distributed authorization system, and no sandbox/runtime
execution or untrusted code admission is permissible on its basis.

There is NO Docker execution, no direct Worker integration, no A6 bypass,
no trading/Telegram/API/database/production changes. These tickets must not
be described as executable capabilities even when signature and replay
checks pass.

## Review tests

Run the workflow runtime-a9-intent-review.yml. The tests cover four
languages, forged HMAC, revoked/spent and expired tickets, A5 flag forgery,
host/issuer/request/worker/source changes, duplicate fields, corrupted
SQLite, nonproduction and operator fencing, cross-connection atomic spend,
and unchanged A6 hard stop. CI uses a fixed fake signing key and fixtures
only. It cannot certify an actual disposable host.

**Verdict: RUNTIME_A9_INERT_ONCE_INTENT_PREPARED_NO_RUNTIME_RELEASE.**
