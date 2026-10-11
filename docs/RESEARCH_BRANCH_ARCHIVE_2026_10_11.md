# Closed / unapproved MARC & FM research archive — 2026-10-11

**Purpose:** preserve audit decisions for obsolete research branches while clearing GitHub's active branch/PR queues. **No research code is merged into `main`.** This document is a result and SHA pointer index, not approval to trade or to reuse an already-observed holdout.

**Independent baseline:** public `main` at `0ac9e05b5d049f4fe42a40735dae178c68a25082`. The 15 branches below were previously unmerged; all are historical research only, not valid current production strategies. This cleanup must not change active source, strategy settings, migrations, secrets, production servers, bot deployment or the existing PAPER/MT5 CI.

## Research branches retired (15)

| Branch at audit | Exact HEAD SHA (Git object provenance) | Associated PR | Closure decision |
| --- | --- | --- | --- |
| `feature/marc-ma-regime-core-v0.1` | `7e583b56dffb06b16a005340d89e77dda1d63531` | #113 | Base MA7/25/99 MARC prototype never approved for runtime |
| `feature/marc-oos-backtest-v0.1` | `fee34cf08775797af9f8e2edaecae579e62f85f7` | #114 | R1 OOS after-cost expectancy **−0.247236R**, 0/10 profitable streams |
| `feature/marc-r2-diagnostic-v0.1` | `9db1d429ea8651b168bd736e620c8cc4d78bb2ac` | #115 | Noncausal post-entry diagnostics only; no validated edge |
| `feature/marc-r2-causal-search-v0.1` | `5a9ef5d5380dca841d6673988104c65e120fba8f` | #116 | No pre-registered development variant passed |
| `feature/marc-r2-exit-repair-v0.1` | `9c9e8fde49e3dfa37f0ae7881ca7a7c91e9d9143` | #117 | Exit/cost adjustments failed development gate |
| `feature/marc-r2-pure-reversal-v0.1` | `6c525bebae16d7a7c3f66d83a5d0f70bfaec8978` | #118 | FRT v0.1 slight pooled base edge, failed stress robustness |
| `feature/marc-r2-frt-cost-clean-v0.2` | `38e76c146d4fa7810c9c9b4c22d0a22153157bf8` | #119 | FRT v0.2 positive only 2/5 development symbols, failed |
| `feature/marc-r2-frt-execution-v0.2` | `6f3513b065d6208d78ccd021bd05eae9c6aef7ea` | #120 | Execution budget: 2/5 positive streams, failed |
| `feature/marc-r2-lead-reversal-v0.3` | `7c738e844a604fdcbcb48bf091f633539b3331bf` | #121 | Branch-specific lead reversal research; no standalone acceptance |
| `feature/marc-r2-frt-lead-reversal-v0.3` | `f4682b72082e1ab65d15bf3c43a0ac145303e940` | #122 | Development PASS; untouched cross-sectional holdout **−0.12306R base**, FAIL |
| `feature/marc-r2-short-reversal-v0.3` | `38e76c146d4fa7810c9c9b4c22d0a22153157bf8` | none | Duplicate exact HEAD of FRT cost-clean; no separate accepted research |
| `feature/marc-r3-regime-instrument-qualification-v0.1` | `c056ff61a71f596591697d24f6e99cd99690aa75` | #123 | Walk-forward base **−0.04250R**, 1/4 positive folds; FAIL |
| `feature/marc-r4-morphology-directional-qualification-v0.1` | `41a9b84ea10b7aa1bb9d2a7536710ea4168d5b7d` | #124 | Walk-forward base **−0.16539R**, 0/4 positive folds; FAIL |
| `research/fm-one-year-top10-scan-v0.1` | `a9713cf775240aeb6a260e1638a0a7ea8cbc7a46` | #125 | One-year FM confirmed-limit base **−0.31608R**, STOP **−0.44879R**; FAIL |
| `research/fm-top10-1y-15m-30m-v0.1` | `6d0213b89135479b4906c66cb1774062a1b75c15` | none | Preliminary deterministic FM protocol only; later #125 research failed |

In all these cases, `runtime_approval=DENIED_RESEARCH_ONLY` or equivalent non-authorization remains effective. Some branches contain earlier research that was profitable on development samples, but that is **not** an acceptance of a tradable edge. The R2 cross-sectional holdout (ADA/DOGE/LINK/LTC/BCH) has been observed and **must not be described as untouched in any subsequent research**. R3/R4's next holdout (AVAX/DOT/TRX/ATOM/NEAR) was not opened after development failed, as documented in the PRs.

## Historical report links retained

- [MARC baseline and OOS results — PR #114](https://github.com/naseri-coder/Multi-Market-Trading/pull/114)
- [MARC causal search and no holdout — PR #116](https://github.com/naseri-coder/Multi-Market-Trading/pull/116)
- [MARC cost-clean FRT — PR #119](https://github.com/naseri-coder/Multi-Market-Trading/pull/119)
- [MARC FRT lead / cross-sectional holdout failure — PR #122](https://github.com/naseri-coder/Multi-Market-Trading/pull/122)
- [MARC R3 walk-forward — PR #123](https://github.com/naseri-coder/Multi-Market-Trading/pull/123)
- [MARC R4 morphology — PR #124](https://github.com/naseri-coder/Multi-Market-Trading/pull/124)
- [FM one-year research — PR #125](https://github.com/naseri-coder/Multi-Market-Trading/pull/125)

## Preserved, NOT part of destructive cleanup

- `main`: **PROTECTED / never delete or rewrite**. Validated current product and PAPER/MT5 development.
- `develop/v0.3.0`: **PROTECTED / never delete in this cleanup**. Historical release-development reference; 50 commits ahead and 68 behind `main` as at audit. Not safe to merge wholesale.
- `feature/brooks-real-http-nonprod-e2e` / [PR #160](https://github.com/naseri-coder/Multi-Market-Trading/pull/160): blocked by actual HTTPS **HTTP 451**; preserved as explicitly unfinished, nonproduction provider diagnostics. Do not claim real API compatibility and never bypass georestrictions.

## Cleanup safety contract

Only the 15 *exactly* enumerated research branch names and their audited HEAD SHAs may be deleted. Their PRs #113–#125 must be closed **without merge** and with final explanation. A changed SHA, protected ref, missing documentation or any unexpected branch identity must fail closed and be left for manual review. Historical PR comments, associated workflow evidence, archive document and `main` source must remain. Do not amend/delete tags or unrelated branches.

**No successful automated cleanup claims until GitHub has independently verified each ref is gone.**
