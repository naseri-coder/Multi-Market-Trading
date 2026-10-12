# Stage 26 — Permanent database-level lock for PUBLIC untrusted Core candidates

**Nonproduction/GitHub-only. No installation, runtime execution, Telegram sends, broker orders or host deployment.** Stage25 cross-stage evidence review is not an execution grant, and Stage23/24 signed local claims are not gVisor attestation. Stage26 explicitly keeps this trust limitation rather than turning an apparently green signed statement into a public executable.

## Implemented enforcement

The existing Stage22 owner-private SQLite database now contains `secure26_public_fence` (once created it has **no API to unset it**) and persistent SQLite triggers. A trusted operator may call `seal_public_candidate(...)` only after a precise Stage25 verification of the exact Stage22 tenant/Core binding/manifest/source pin, current non-revoked dual signed Stage23 candidate and Stage24 reviewed host observation. The preflight requires a **DISABLED** Stage22 binding with **no previous execution attempts**, no output/send/live authorization and a separate explicit nonproduction acknowledgment.

The seal itself runs inside Stage22 `BEGIN IMMEDIATE`, rechecks the binding's exact revision, immutable source/manifest/binding hashes, state and zero attempt rows, re-reads the Stage23/24 signatures and commits a **single new permanent fence row**. A process crash before COMMIT leaves no fence, and the binding cannot pass a later promotion if it was previously run. A completed seal survives reopening/restart.

All Stage22 access paths now consult this table: its old `set_enabled(... enabled=True)` refuses sealed public candidates, as does `evaluate(...)` before the isolated host call. Crucially, **database triggers** also block raw SQL changing the sealed binding's state to `ENABLED` or `EVALUATING`, or adding a new execution attempt. Update/delete of the Stage26 fence is blocked. This is stronger than a front-end-only check: another application using the same unmodified Stage22 API cannot accidentally enable the marked binding.

The returned `SEALED_PUBLIC_UNTRUSTED_CANDIDATE_NO_EXECUTION` receipt includes public candidate/observation hashes, exact revision and immutable **false** install/evaluate/live flags. `inspect_public_candidate_lock(...)` returns safe owner-specific status without private source or signing keys. No CLI, API server, Telegram toggle, public package downloader, or automatic Stage22 evaluation was added.

## Important scope boundaries

- The **legacy Stage22 isolated nonproduction RESEARCH** `register/set_enabled/evaluate` API remains available for **unclassified** trusted local testing, to preserve existing Stage22/25 regression contracts. This is *not* an authenticated public plugin admission route. Marking a binding as a public third-party candidate must be done by a trusted application operator using Stage26. **Stage26 does not globally prevent a malicious or incorrectly wired privileged host from deliberately misclassifying a third-party core as research.** Full mandatory provenance enforcement across every integration entry point still requires a new separately reviewed, authenticated public installer and a host policy that refuses unclassified public inputs.
- SQLite triggers protect operations by cooperating applications using this managed database; an actor with database-owner privileges can drop triggers/change data and is *outside* this enforcement boundary. The owner's directory/file permissions and signer custody remain independent operational requirements.
- Stage26's Stage22 write+trigger update is atomic **inside one SQLite database only**. Stage23 and Stage24 are separate databases and cannot be assumed atomically locked with the Stage22 transaction. New revocations after sealing are safe for Stage26 because a sealed candidate can *never* execute; a future grant system must design its own same-transaction ongoing revocation and signed-claim validation before any execution.
- No actual Docker/gVisor host has been provided or tested. A signed Stage24 observation does not attest to real kernel isolation. Rootless Docker, gVisor, cgroup limits, hostile source confinement and orphan process cleanup require independent authorized, disposable-host assessment.
- All publication and trading outcomes remain `BLOCKED_PENDING_REAL_HOST_AND_AUTHENTICATED_INSTALLER_REVIEW`. No production server, running Telegram bot, broker account, database migration in production, legacy v0.3.2 code, or owner-private NY First-Reversal changes.

## Testing

Dedicated Python3.12 GitHub Actions covers Stage26 fixed source and clean installed-wheel security acceptance, plus Stage22/23/24/25 regressions. Negative tests exercise revoked/expired/wrong signer, bad binding or code, prior execution, concurrent revision change, direct SQL state and attempt bypass, fence deletion/update, persistence across multiple SQLite connections and production refusal. Standard publication, separate package and PostgreSQL checks must all pass before merge.

**Next architectural requirement:** a single authenticated public registration pathway that *forces* Stage26's public class rather than allowing the legacy research API to be invoked for public plugin code, followed by independently verified disposable-host runtime isolation. A separate grant authorization would need new evidence and must never be inferred from Stage26's permanent denial receipt.
