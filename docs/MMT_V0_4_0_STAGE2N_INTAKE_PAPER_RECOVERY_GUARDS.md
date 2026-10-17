# MMT v0.4.0 — Stage 2N: intake, PAPER and stopped-recovery production guard hardening

**Date:** 2026-10-17  
**Scope:** `release/0.4.0-candidate`, Draft PR #352  
**Release verdict:** `EIGHT_REAL_RUNTIME_MODULES_HARDENED__NINE_GUARDS_CHANGED__REMAINING_GLOBAL_AST_GATE_BLOCKS_STABLE_RELEASE`

## 1. Reviewed real module changes

The following **eight actual GitHub source modules** had **nine** verified legacy conditions equivalent to `os.environ.get("MMT_PRODUCTION") == "1"`. These did not reject an explicitly defined `MMT_PRODUCTION=0`, `false`, or empty value even with `MMT_NONPRODUCTION=1`.

| Public Python module | Number of admission predicates corrected | Existing safety purpose |
| --- | ---: | --- |
| `naseri_markets/adapter_free_paper_runtime_v1.py` | 1 | Adapter-free PAPER runtime |
| `naseri_markets/binance_public_funding_mark_stage18_v1.py` | 1 | Funding/mark research data |
| `naseri_markets/binance_vision_archive_stage16_v1.py` | **2** | Monthly Binance Vision import and reviewed Brooks window |
| `naseri_markets/captured_paper_cli_stage21b_v1.py` | 1 | Explicit captured PAPER CLI |
| `naseri_markets/captured_paper_pilot_stage21b_v1.py` | 1 | Captured PAPER audit/pilot |
| `naseri_markets/data_a1_file_intake.py` | 1 | Historical A1 file intake |
| `naseri_markets/data_runtime_paper_wire_a1.py` | 1 | A1 intake → PAPER runtime wiring |
| `naseri_markets/mmt_r32_stopped_recovery_review_v1.py` | 1 | Writers-stopped recovery review |

Each old comparison was replaced by the strict presence test `"MMT_PRODUCTION" in os.environ`. **No execution strategy, trading algorithm, order placement, account settings, persistence, data transformation, CLI switches, exception class or exception code was altered.** No changes to internal subprocess environment constructors were necessary in this batch: the selected modules did not explicitly construct a child environment containing `MMT_PRODUCTION="0"`. The Stage2M historical Brooks parent/child fix remains intact.

Direct GitHub source inspection *after all eight updates* verified exactly **9 new presence checks and 0 old value-only checks in this scoped group**, while matching each file's new Git blob hash to the independently pinned snapshot. Existing repository tests were inspected for deliberate `MMT_PRODUCTION=0` fixtures in the affected surfaces; none were found. Prior tests generally asserted only `MMT_PRODUCTION=1` refusals.

## 2. Source-bound negative coverage and executed reduced-branch tests

New committed file: `tests/unit/test_mmt_v040_stage2n_entrypoint_guard_v1.py`.

This test is designed to run against the **real full repository checkout**: it parses each of the eight complete source files with `ast.parse`, identifies all nine exact `MMT_PRODUCTION in os.environ` admission branches, confirms every branch immediately raises its existing refusal, and executes **only the extracted original If branch** in a bounded test namespace. It never imports the trading modules, opens a database or file, sends Telegram, calls a broker or runs PAPER.

81 parametrized assertions:

- **54** cases: all nine admission branches reject six explicitly defined production values `""`, `"0"`, `"1"`, `"false"`, `"FALSE"`, `"no"`.
- **9** cases: with `MMT_NONPRODUCTION=1` and production *absent*, each entry predicate does not refuse (this only proves the initial gate, not full runtime success).
- **9** cases: missing nonproduction opt-in is refused.
- **8** cases: exact per-module admission branch inventory; no old comparison survives.
- **1** case: uniqueness and expected nine-branch scope.

**Actually executed in the assistant's isolated CPython 3.13.5 container: `81 passed in 0.18s`. Important qualification:** due to blocked direct GitHub checkout in that container, the local test used **reduced fixtures faithfully modeling the nine source admission branches**, NOT whole original source modules. The committed test will extract the real source AST when run in a full checkout, but **that complete-source run has not yet occurred**. Independently, connector-based source re-fetch *did* confirm the real eight files contain those exact nine presence checks and no legacy comparison. These two independent observations must not be conflated with a Python3.12 integration approval.

The committed test file Git blob SHA-1 was re-read as `82ed4c597603622a194628a19d7433c0b6822d03`; this exactly matches the tested local file bytes. Its SHA256 is `d53b078a8d194201d2b0d408c56b611cc881ce39ed0c75c368ff467944607bbe`.

## 3. Real 226-module Git source inventory rebaseline

The **only eight** changed public source modules collectively reduced the public source by **81 bytes**. The existing full source inventory was re-attested via a GitHub Git-tree read after the last commit: **226/226** public `naseri_markets/*.py` file paths, exact Git Blob SHA-1s and file sizes match the new lock, with no unexpected nested/symlink/non-Python package entries.

New exact external identifiers for this snapshot:

| Property | Current Stage2N value |
| --- | --- |
| Snapshot source Git commit | `fb7d5e0c9b4a856dc62bb8b446cba277cd7d32f0` |
| Public `naseri_markets` subtree Git SHA-1 | `85b561e65ac59eaeeda02560af3d671a71524e8d` |
| Current `docs/MMT_V0_4_0_PUBLIC_MODULE_SNAPSHOT.json` SHA256 | `515e3c7693064e2427f348d424097d019715ed760d2b844805d40900fe34ce4e` |
| Current JSON Git Blob SHA-1 | `beaf61740ccce7163584db9a4dfe1592c2ba5144` |
| Module count / source bytes | **226 / 2,501,292** |
| Changed sources | **8 modules / 9 guards** |
| Unchanged sources | **218 modules** |

The source inventory SHA256 was independently recomputed from the *actual* GitHub-returned UTF-8 snapshot contents, with an independently checked `abc` SHA256 known-answer vector. The old Stage2M snapshot SHA256 `9823877a252e330c125c6417a1d6f554f46efedc20d142354a27f8029f963534` is **historical and must not be reused** as the current source release pin.

## 4. Blockers, limitations and next safe phase

The whole-source AST release fence `scripts/mmt_v040_production_guard_ast_audit_v1.py`, added in Stage2L and enforced by the isolated stable staging utility, **remains mandatory**. A significant number of other actual package modules still use a value-only `MMT_PRODUCTION` check; no claim of fully fixing all 226 files is made. The eight scoped modules pass direct GitHub predicate inventory checks, but the **full source AST admission gate has NOT passed** and must continue to block release until those additional modules are reviewed.

Also **not executed** in this stage: actual full GitHub source installation on CPython3.12, Ruff, real full 226-module `0.4.0` Wheel dual builds, R35–R38/R42V installed test matrix, PostgreSQL and PAPER state recovery/rollback, signer approval or a public release. No GitHub Actions quota, user server/production environment, live broker or Telegram channel was used.

**Next:** Stage2O should continue module-specific remediation on offline trade/order/reconciliation and supervising workers while inspecting each child-environment and positive-test dependency. Rebaseline all exact Git-source pins after each reviewed batch. Run full nonroot CPython3.12, installed-wheel, PAPER and rollback tests once a complete approved checkout is available.

**Protected main / tag decision:** `NO_MERGE__NO_v0.4.0_TAG__DRAFT_PR_352`.
