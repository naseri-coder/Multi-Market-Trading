# MMT v0.4.0 — Stage 2V: scoped release-script Ruff remediation

**Date:** 2026-10-17  
**GitHub PR:** #352, Draft, open, unmerged  
**Baseline:** `main` at `51e0e4de04e184fe28b59b9db4b6a70fbd67dfe0`  
**Code changes committed:** `7f5aad3d8bf540b45b825435591d7fe3287a2e36`  
**Verdict:** `NINE_SCRIPTS_LINT_CLEAN__1101_TESTS_PASS__38_NEW_RUFF_FINDINGS_REMAIN__RELEASE_DENIED`

## 1. Safe scope

Starting from an actual GitHub PR HEAD `7a45ab9953faf64088e834a9840bc21277ae0e9d`, corrected new Ruff findings in the following nine release/research audit scripts. Used bounded formatting and import changes, retaining admission gates and original refusal outcomes:

- `scripts/mmt_r29_manual_future_shadow.py`
- `scripts/mmt_r41_readonly_oci_contract_audit_v1.py`
- `scripts/mmt_r42_offline_market_account_evidence_v1.py`
- `scripts/mmt_v040_offline_stable_staging_v1.py`
- `scripts/mmt_v040_production_guard_ast_audit_v1.py`
- `scripts/mmt_v040_public_source_snapshot_audit_v1.py`
- `scripts/mmt_v040_rc_overlay_signed_custody_v1.py`
- `scripts/mmt_v040_signed_artifact_preflight_v1.py`
- `scripts/mmt_v040_source_wheel_custody_v1.py`

The signed/static production admission contract was not relaxed. In particular, the existing Stage 2L AST scanner retained `zip(..., strict=False)`, which is appropriate for adjacent operand pairs, and changed only formatting around that code.

Automatic Ruff changes to **16 public product modules were discarded** rather than committing changes before recalculating source custody and historical precommitment attestations. The official `naseri_markets` Git tree is still `3e13f90d5e2f7989b64cd91d15fce786be3c27ca`; the committed **226-source Git manifest is unchanged** and remains SHA-1/size-valid.

## 2. Tested real code in isolated Python 3.12

The connected test environment ran **CPython 3.12.15** inside a disposable Linux container under nonroot UID 1000 with network disabled, restricted resources, no production data mounts, no LIVE broker or Telegram network access.

- `ruff check` on **all nine** edited scripts: **PASS (0 Ruff findings)**.
- Source-bound tests `test_mmt_v040_* ` plus two R41/R42 audit test files: **1,101/1,101 PASS** on the original edited bytes before GitHub commit; re-run against the **freshly cloned exact GitHub code commit** `7f5aad3d8bf540b45b825435591d7fe3287a2e36`: **1,101/1,101 PASS in 21.30s**.
- `git diff --check` and Python AST parsing of all edited local scripts: **PASS**.
- GitHub readback: **9/9 exact source Git Blob SHA-1s** matched the locally tested files; PR remained Draft.
- Local readback of the exact GitHub code commit: `git status --porcelain` empty and unchanged source tree `3e13f90d5e2f7989b64cd91d15fce786be3c27ca`.

## 3. Ruff regression gate: measurable but NOT complete

Official `scripts/ci_ruff_no_new_debt.py` executed with `ruff 0.16.9` and external baseline commit `51e0e4de04e184fe28b59b9db4b6a70fbd67dfe0`:

| Metric | Before this stage | After exact GitHub code commit |
| --- | ---: | ---: |
| Historical baseline findings | 1,345 | 1,345 |
| Candidate Ruff findings in configured source scope | 1,412 | 1,383 |
| **New lint debt** | **67** | **38** |
| Edited release/audit scripts with remaining findings | N/A | **0 of 9** |
| New findings remaining in public product sources | N/A | **38 across 20 modules** |

The ratchet **still exits nonzero** because 38 new warnings remain. A global naive `ruff check .` includes older legacy/test lint debt and is not the project's accepted baseline-relative gate.

## 4. Outstanding release blocks

**Next Stage 2W: source-scoped Ruff and custody repair.** Resolve the 38 findings across 20 `naseri_markets` modules with minimal reviewed syntax-only changes. Reconstruct historical R22/Stage21 study original-source proofs, then regenerate the 226-module Git Blob and size manifest from the actual final source tree. Rerun original full 226-source AST gate and Stage2N–2V source-bound tests, **full Python3.12 project suite**, independent dual Wheel builds, RECORD/source custody and signature provenance on the **new immutable commit**. Do not merely repin a corrupted historic study or overwrite signed evidence to silence an assertion.

Further release gates remain unverified: **76 skipped tests** from a prior full Python3.12 run (including PostgreSQL/ephemeral-runner capability), isolated Postgres migrations, repeated PAPER restart/rollback/cold start, independent signer/host custody, final protected-main branch review, and official publication authorization. Historical **7,581 PASS / 76 SKIP** applies to an earlier candidate, not automatically this new code commit.

**No publication authority:** no merge into `main`, no `v0.4.0` or prerelease tag, no deployment, no LIVE trading, no Telmivo production mutation, no real keys or production database writes.
