# Stage 29 — Authenticated developer session and mandatory offline quarantine intake

**Scope: GitHub-only, explicit nonproduction operation.** This is a *real Ed25519 proof-of-key-possession authentication contract* for already operator-onboarded Stage28 publisher identities, plus a single authenticated package-submission API. It is **not** a deployed website, public HTTP API, identity/KYC service, server deployment, gVisor security certification or permission to run code. No source module is executed.

## Login and trust boundaries

The existing Stage28 registry holds a reviewed publisher key and records key rotation/revocation. The new `AuthenticatedDeveloperIntake` adds a domain-separated, **120-second, randomly generated single-use challenge**. A developer proves possession of the currently ACTIVE Ed25519 key by signing exactly:

`MMT-STAGE29-DEVELOPER-LOGIN-V1\0 + canonical(challenge)`

The challenge is bound to the trusted host's tenant ID, publisher ID, key ID, current publisher revision, scope `QUARANTINE_SUBMIT_ONCE`, nonce, issued timestamp and expiry. The trusted host checks signature, key state, revision and the previously issued challenge in a single SQLite `BEGIN IMMEDIATE` transaction, consumes the challenge, and creates a **300-second, one-use** opaque 256-bit bearer token. Only its SHA256 is stored; the raw token is returned once and must be protected by the caller. Challenge replay, forged claims, stale signatures, cross-tenant claims and login after key rotation/revocation all fail closed. Pending challenge and active-session limits are four per publisher; history is bounded.

**Authentication is cryptographically real only within the operator-trusted registry**. The Stage28 publisher identity was operator-assigned, not independently matched to a person's government identity. This library does not transport a credential safely over a network by itself. A future HTTPS/TLS service with CSRF protections, secure cookies or equivalent bearer-secret handling, host-side client/rate controls and independent publisher onboarding remains a separate approval.

## Single authorized submission entry point

`AuthenticatedDeveloperIntake.submit_package(token=..., ...)` derives the tenant, publisher and active signing key **from its authenticated server-side session row**, never from user-supplied query parameters. It passes the exact Stage23 reviewed claim and Stage28 ZIP to the existing quarantiner.

When Stage29 is initialized for a Stage22 database, the **persistent `secure29_policy` table enables mandatory authentication** for *all Stage28 `submit()` calls sharing that database*, including the legacy operator-only call: one must supply the internal, 64-character SHA256 session digest, which is revalidated under the same Stage22 SQLite `BEGIN IMMEDIATE` used by Stage28 to insert Stage27's permanent public/non-executable classification, Stage28's immutable submission record and the audit entry. A successful commit simultaneously consumes the token. Reuse is forbidden. A failed transaction rolls back token consumption as well as database registration; an inert owner-only ZIP staging orphan can remain if the disk write finished first.

The already signed Stage23 publisher/operator candidate is rechecked against the Stage28 ACTIVE key *inside the same transaction*. Rotating or revoking the publisher key changes the Stage28 revision or status, invalidating previously issued sessions immediately. Stored sessions can also be explicitly revoked using the bearer token.

Stage27's permanent SQL/API denial still guarantees **no `ENABLED`, `EVALUATING`, broker order, Telegram signal or public plugin install** for a submitted public source. The Stage4 sandbox is not invoked.

## Explicit limitations

- This stage creates **no internet listener, login page, OAuth account, API secret, public uploader, new BotFather command or production service**.
- The caller must supply verified, operator-assigned publisher identity to initiate challenge creation. The trusted time is taken from an internal server clock, not from a client timestamp. Unit tests inject a fixed clock; production has not been exercised.
- Persistent local SQLite security is bounded to the trusted host. A database owner can tamper with tables and remove policy/triggers; cryptographic key ownership is not independent human identity vetting. The Stage22 research registry and Stage27 direct operator research APIs remain for compatibility. They are *not* public intake paths; Stage29 does **not** claim every possible privileged Python code path is universally forced through authenticated intake.
- The `_auth_session_sha256` argument on Stage28 is an **internal trusted-call convention** and not a safe external API. Never permit client-supplied digests or untrusted Python access to the owner-owned registry. Stage29 is the only intended user-facing logical submission method.
- No upload is automatically trusted as code or installed: archive content remains inert, fixed-size, locally hashed ZIP in private quarantine. No gVisor host isolation was actually proven, no malware scanning is claimed, and source or trading strategy profitability has not been assessed.

## Test and acceptance

GitHub Python3.12 CI uses **real ephemeral Ed25519 private/public keys only inside disposable tests**, official Stage22–28 fixture contracts, and no network/real plugin execution. Positive cases cover challenge issuance and signed login; adversarial cases cover invalid key signatures, cross-tenant claims, extra challenge fields, expiry, 1-use replay, session logout, publisher key rotation/revocation, rate limiting, direct Stage28 bypass refusal, Stage27 permanent non-executable intake, and rollback of both session consumption and database submission on a simulated second-insert failure. The new installed wheel is tested from outside the repository directory. All existing project-wide PostgreSQL and publication gates must pass before merge.

**Delivery verdict: `AUTHENTICATED_OFFLINE_QUARANTINE_ONLY / PUBLIC_RUNTIME_AND_TRADING_BLOCKED`.** No live bot, production database, production server, trading account, GitHub secret, Telegram channel, or owner-only NY First-Reversal is changed.
