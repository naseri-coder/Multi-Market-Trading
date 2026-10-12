# Stage 27 — Signed public-developer intake, atomic non-execution classification

**Nonproduction, GitHub-only. No third-party source execution, installation, account access, publishing or trading.** This stage closes the registration-to-lock gap for the **new trusted PUBLIC intake path**. It does not confer remote host attestation, user-session authentication, or global code-provenance enforcement outside this path.

## Why Stage27 is needed

Stage26 can permanently seal an already registered PUBLIC-untrusted candidate after Stage25 cross-evidence review. Before Stage27, existing Stage22 `register()` committed the binding in `DISABLED` state without permanently classifying it as public: an authorized trusted-local caller could call `set_enabled()` before Stage26 seal. Stage27 introduces a new **signed public intake pathway** that commits the identity and its permanent execution prohibition in **the same Stage22 BEGIN IMMEDIATE transaction**. There is no new public execution grant.

## Source and publisher authentication

`register_signed_public_candidate(...)` requires an **already admitted, current Stage23 dual-Ed25519-signed executable candidate** (independently pinned publisher public key plus separately pinned operator approval public key), the exact CoreManifest, CoreBinding, source SHA256 and pinned OCI `image@sha256`. The stage23 witness verifies the signed tenant ID, publisher, publisher key ID, source, manifest, symbol/provider/timeframe binding, validity window, locked signing keys and absence of revocation.

**Authentication boundary:** Stage23 authenticates the signing keys attached to the reviewed claim; a trusted caller must still authenticate the actual tenant/operator session and establish that the publisher key truly belongs to the purported developer via an external onboarding process. Passing an arbitrary `tenant_id` to a Python function is not web/API authentication. This version has **no public upload endpoint**, account login or publisher enrollment service, and does not auto-register an unsafe unsigned plug-in.

Registration shares the exact same Stage22 global and per-tenant quotas using a common internal helper, then atomically inserts `secure27_public_intake` with immutable fields: tenant, publisher, reviewed candidate SHA, exact source/manifest/binding SHA, pinned image digest, initial revision and **PUBLIC_UNTRUSTED_PENDING_INDEPENDENT_HOST**. If the second insertion or transaction fails, registration rolls back entirely. Only after both rows have committed does any result return.

## Permanent execution prohibition

- Stage22's old `set_enabled(enabled=True)` and `evaluate()` refuse every Stage27 public-classified binding **before launching the isolated worker**. Future Stage26 sealing cannot reclassify it as executable.
- Database triggers block direct SQL transitions to `ENABLED` or `EVALUATING`, direct new execution attempts, deletes or updates of the public classification. A restart or second SQLite connection does not remove these checks.
- Stage26's later signing/evidence seal validates the initial Stage27 source/candidate/manifest/image pins rather than treating any unrelated signed proof as applicable to this binding. It adds a **second** permanent denial fence after Stage25's preinstall review.
- Read-only `inspect_public_intake` presents tenant-fenced safe status. No exposed code, private developer signing keys, privileged host IDs or broker/Telegram capabilities.

## Scope and limitations

The preexisting Stage22 `register / set_enabled / evaluate` remains available for separate trusted **LOCAL_RESEARCH** fixtures and previous Stage22–26 regression compatibility. It **must not** be used as a public third-party onboarding path. Stage27 prevents bypass **within a binding already admitted to this signed-public path**, not all hypothetical integrations or arbitrary privileged code that bypasses registration by knowingly misclassifying third-party input. SQLite triggers themselves do not protect against a database owner intentionally dropping the triggers; signature storage and server custody require external controls. A hypothetical future public installer must be a single authenticated endpoint *wired exclusively* to Stage27 and enforce classification at every source intake; no such endpoint is exposed by this stage.

Stage27 never runs a real Docker/gVisor canary. Stage23/24 signed **statements** about a test are not independent runtime attestation. Before any unknown code is executed there must be a separately authorized disposable-host adversarial isolation review, publisher identity onboarding, key recovery/revocation policy, end-to-end installer admission tests and an audited execution-time license/trust recheck. Positive CI does not certify strategy profitability or real exchange trading.

## CI acceptance

Dedicated Stage27 Python3.12 CI runs real ephemeral dual Ed25519 signatures, wrong tenant/publisher/key/image/source/revision/expiry, revoked candidate, cross-transaction rollback fault, direct SQL trigger bypass, Stage26 transition, prior Stage22 research compatibility and isolated installed-wheel tests. All standard repository GitHub Actions gates must pass on the PR head before merge.

**Release verdict is always `PUBLIC_UNTRUSTED_INTAKE_BLOCKED`; public install, live orders and Telegram signal toggles remain off.** Owner-only NY First-Reversal and the production running bot are untouched.
