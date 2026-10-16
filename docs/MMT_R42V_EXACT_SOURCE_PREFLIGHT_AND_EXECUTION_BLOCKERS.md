# R42-V — canonical R42 exact-source preflight, runtime acceptance BLOCKED

**Date:** 2026-10-16  
**Scope:** independent source/read-only assessment of the exact R42-C PR #337 head; no operational host, GitHub Actions, production, broker, connected PAPER or Telegram.  
**Upstream chain:** R41 Draft #334 → R42 canonical candidate Draft #336 → R42-C Draft #337 → this R42-V evidence-only Draft.  
**Pin:** R42-C reviewed head `3624bce93a20dd9dfe7b22928055c718d6a8f85e`. Do not substitute moving branch names for this evidence.

## Exact GitHub file identities

| Path | Git blob SHA-1 at the reviewed R42-C head |
| --- | --- |
| `scripts/mmt_r42_offline_market_account_evidence_v1.py` | `1bf038ae05616b3871df575bf5516b798a6bcde3` |
| `tests/unit/test_mmt_r42_offline_market_account_evidence_v1.py` | `81626378e4ecf11ac479584e248640c6263da495` |

The above GitHub source files were fetched and inspected directly at the **commit SHA**, not reconstructed from prior conversation or a floating branch. Diff/commit ancestry was examined separately in the preceding R42-C review.

## Static preflight actually inspected

- Deny gate `source["observed_at"] != baseline["observed_at"]` leads to `R42_ACCOUNT_LEDGER_TIMESTAMP_DRIFT` before the value comparison.
- Both parameterized new mismatch scenarios and the new CLI-refusal scenario are present in the **committed** test source.
- The module retains explicit `MMT_NONPRODUCTION=1` and `MMT_PRODUCTION`-absent guards.
- Successful synthetic results explicitly mark real provider authentication, account ownership, remote account reconciliation and LIVE authorization **false**.
- No direct known exchange/HTTP/Telegram imports or overt filesystem mutation calls were found in the inspected R42 module. These are **limited static observations, not a sandbox certification**.
- The committed test module contains 39 `def test_...` functions, including parameterized cases, but **no test-run PASS claim** is made from function count.
- Source/token review was bounded to R42 canonical two files; no whole-stack Python import, wheel execution or dependency lint was run.

## Execution environment and hard blocker

An independent assistant sandbox was inspected on 2026-10-16: Python **3.13.5** and pytest are available; Python **3.12** and Ruff are **not installed**. Git/network fetch from that sandbox was unavailable. The GitHub connector was able to read and update the code but does **not** execute Python. Connected Desktop Commander devices show only **operational Telmivo** online; this server was **NOT USED**. The old price-action and Telmivo-license-authority devices were offline.

**No actual Python3.12 test execution, Ruff execution, installed wheel/venv test, or full-repository regression was possible or performed in this independent approved environment.** Nor was a substitute 3.13-only run of the exact committed source/test performed. Do not count authored tests as passed, and do not substitute previous reported synthetic results.

## Explicit acceptance table

| Gate | Observed verdict |
| --- | --- |
| Pinned GitHub source/test identity | STATIC INSPECTION PASS |
| R42-C timestamp refusal exists | STATIC INSPECTION PASS |
| Three new test scenarios exist | STATIC INSPECTION PASS; EXECUTION PENDING |
| Existing R42 test corpus | EXECUTION PENDING |
| Python 3.12 isolated clean-room pytest | BLOCKED — no independent Python3.12 host |
| Targeted/full Ruff and project regression | BLOCKED — Ruff/whole repo unavailable |
| Verified nonroot installed wheel end-to-end | PENDING |
| R41 independent rootless gVisor hostile test | PENDING |
| Real signed venue provenance / remote reconciliation | NOT ESTABLISHED |
| Stage15 nine P0 + one P1 blockers | UNCHANGED |
| Real market orders / LIVE / public signals / production | HARD DENY |
| Status | `R42V_STATIC_REVIEW_COMPLETE_RUNTIME_ACCEPTANCE_BLOCKED` |

## Exact reproducible next acceptance (on separately approved disposable nonproduction Linux host)

Use a clean pinned checkout at R42-C commit `3624bce93a20dd9dfe7b22928055c718d6a8f85e`, Python **3.12.x**, and a dependency environment created from separately reviewed project constraints. Reject any source/blob mismatch. Verify the exact two blob IDs above before executing. Run the committed `tests/unit/test_mmt_r42_offline_market_account_evidence_v1.py` via `python3.12 -m pytest -q`, then targeted Ruff against script and test, followed by relevant Stage3/5/15 regressions and nonroot wheel acceptance. Record actual Python/pytest/Ruff versions, command exit codes, SHA-pinned inputs, test count, failures and environment identity. Test on synthetic data only. Do not invoke GitHub Actions by default.

Fail closed and record `PENDING` rather than adapting requirements to make a green report. R42-V can only be considered **fully accepted** after genuine executable evidence and independent release review. This PR is **evidence-only**, not a release switch.
