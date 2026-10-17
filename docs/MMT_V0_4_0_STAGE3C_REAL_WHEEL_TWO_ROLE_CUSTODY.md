# MMT v0.4.0 — Stage 3C real-source dual-signature cross-custody

**Status:** real GitHub-source wheel + two ephemeral synthetic keys; **NOT publisher identity or official release approval**.

## Confirmed starting point

The exact code SHA `8323c350ac0cdd388099da8227589243f3f771d2` reached **79/79 successful pull-request CI workflows** (2026-10-17). The 15 Stage3B tests exercised `verify_operator_review` but did **not** exercise the full publisher + operator + source-to-wheel integration against a wheel built from all 226 real Git source modules.

## Stage 3C coverage

- `scripts/ci_stage2z_publisher_custody.py` now reuses its existing clean-Git provenance, independent twin stable-overlay wheel builds and independently verified source-to-wheel manifest/RECORD checks.
- In the *same disposable CI workspace*, generate **two different in-memory Ed25519 private keys**, one for the publisher manifest and the other for an operator-review receipt. Neither is saved, trusted as a production authority, or uploaded.
- Sign a canonical time-limited operator receipt that cryptographically binds the exact commit, public source tree/snapshot, stable overlay hash, wheel SHA256, publisher manifest digest, signer fingerprint and publisher trust-policy SHA256.
- Execute **`verify_full_custody` against that actual Wheel and Git checkout** (not a mocked audit and not synthetic Python module bodies). Require 226 modules and an explicit release-denied verdict.
- Negative end-to-end cases: forged operator detached signature, legitimately signed operator receipt with `source_date_epoch` inconsistent with the publisher's signed manifest, and publisher/operator key-role collision. All must fail closed.
- `scripts/mmt_v040_operator_two_role_admission_v1.py` now compares operator-signed source epoch with the independently verified publisher manifest epoch; re-reads/re-pins the manifest following the Git-to-Wheel custody audit. A reviewer cannot approve a different source time even if other hashes match.
- `tests/unit/test_mmt_v040_operator_two_role_admission_v1.py` adds coverage for the authenticated reviewer epoch; Stage3B remains an independent isolated test workflow.

## CI and acceptance markers

The existing Stage2Z GitHub Actions workflow re-tests the entire real-source dual-build chain on every PR head. It must emit:

- `STAGE3C_REAL_SOURCE_TWO_INDEPENDENT_TEST_SIGNERS_PASS_RELEASE_BLOCKED`
- `STAGE3C_FORGERY_EPOCH_SPLIT_AND_ROLE_COLLISION_REFUSED_PASS`
- Existing Stage2Z source/Wheel and forged/revoked publisher signature checks
- `independent_approved_publisher_verified=false` and `publication_authorized=false` (non-negotiable)

Stage3B and the full corpus must also be green on the same immutable SHA. A prior 79/79 result does not automatically transfer to a later commit.

## Remaining real-world admission — unchanged

Neither a passing stage3C test nor any self-signed CI keys prove the ownership or approval of real signing identities. Require independently authenticated **distinct real** publisher/operator public key fingerprints, their separately reviewed revocation policies, an actual offline-signed stable manifest and operator receipt, the exact final Git-to-Wheel custody proof, explicit decision on the two intentionally skipped public-data HTTPS smokes, and authorized human review of protected `main`.

**No private key in chat, GitHub Actions, PR comments or release artifacts. No `main` merge, no stable `v0.4.0` tag, no Prod/Telmivo, Telegram or LIVE.** Keep PR #352 Draft and issue #354 open.
