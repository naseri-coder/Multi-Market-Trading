# R42-V — independently executed exact-committed R42-C synthetic test evidence

**Date:** 2026-10-16  
**Reviewed, immutable R42-C head:** `3624bce93a20dd9dfe7b22928055c718d6a8f85e` (PR #337).  
**Scope:** read-only / offline synthetic local evaluation; no GitHub Actions, Merge, production, Telmivo server, broker, connected PAPER, Telegram or network.  
**Acceptance classification:** `R42V_EXACT_COMMITTED_PY313_TESTS_PASS_PY312_HOST_ACCEPTANCE_PENDING`.

## Verified source/test identities

Using connected GitHub read-only file retrieval at the exact commit SHA, the two exact UTF-8 files were transferred into an **independent ephemeral assistant sandbox**, reconstructed locally and verified using Git's real SHA-1 blob identity algorithm (`SHA1("blob " + byte_length + NUL + raw_bytes)`) **before executing tests**.

| File | Bytes | Git blob SHA-1 | SHA-256 |
| --- | ---: | --- | --- |
| `scripts/mmt_r42_offline_market_account_evidence_v1.py` | 14627 | `1bf038ae05616b3871df575bf5516b798a6bcde3` | `91aa554fe0484b5327a9d64f7034686a1f02e4b83763035c342c6dd5759c9c67` |
| `tests/unit/test_mmt_r42_offline_market_account_evidence_v1.py` | 12805 | `81626378e4ecf11ac479584e248640c6263da495` | `b2a9d05f9e92656c3be51503cee6faface47c2c11ace2f3e889940dae47c76b1` |

No generated test substitutions or modified source were used in the two positive runs. The files are those directly committed to R42-C PR #337, not a paraphrased test harness.

## Concrete environment and results

- Linux ephemeral assistant sandbox, **nonroot UID=1000**, isolated from the user's operational hosts and accounts.
- CPython **3.13.5** (GCC 14.2.0), pytest **9.0.2**, coverage.py **7.13.3** (C extension).
- Nonproduction guard `MMT_NONPRODUCTION=1` set; `MMT_PRODUCTION` absent.
- Current working directory contained only the reconstructed `scripts/` and `tests/unit/` source paths.
- No real market/broker credentials or user account data; pytest temporary synthetic fixtures only.
- Python3.12 grammar syntax preflight via `ast.parse(..., feature_version=(3,12))` **passed** on both source and test files. This is a **grammar preflight, not Python3.12 runtime proof**.
- First direct run: `python -m pytest -q -c /dev/null -p no:cacheprovider --noconftest tests/unit/test_mmt_r42_offline_market_account_evidence_v1.py` → **48 PASSED in 0.13s**.
- Strict second run, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONHASHSEED=0 python -X dev -W error -m pytest -q -c /dev/null -p no:cacheprovider --noconftest ...` → **48 PASSED in 0.11s**.
- Third run, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONHASHSEED=33 python -m coverage run --branch --source=scripts.mmt_r42_offline_market_account_evidence_v1 -m pytest -q -c /dev/null -p no:cacheprovider --noconftest ...` → **48 PASSED in 0.16s**.
- `python -m coverage report -m` → 198 source statements, 20 missing, 92 branch sites, 14 partial branches, **88% measured total coverage** for the one R42 module. This is NOT whole-repository coverage.

The first attempt at strict warnings-as-errors without disabling third-party pytest plugin autoload stopped during pytest startup due to an **installed pytest-asyncio default-loop-scope deprecation warning**, before any R42 tests ran. Re-running with external plugin autoload explicitly disabled, without touching project code, passed 48/48. This configuration-specific harness warning should not be misreported as a product test failure or ignored in independent reproduction.

## Independent mutation-sensitivity test

On a **disposable local copy only**, remove these two original source lines:

```python
if source["observed_at"] != baseline["observed_at"]:
    raise R42Refused("R42_ACCOUNT_LEDGER_TIMESTAMP_DRIFT")
```

Run exactly the committed test file against the mutated copy with `pytest -k r42c --tb=line`. Actual observed result: **3 FAILED, 45 deselected, exit status 1**. Both parameterized direct-audit negative cases fail with `DID NOT RAISE`; the CLI regression fails `assert 0 == 2`. Thus all **three newly authored cases detect removal of the intended R42-C refusal gate**. The disposable mutated copy was discarded; original GitHub code was never changed by this test.

## What is now proven versus still blocked

| Gate | Observed result |
| --- | --- |
| Exact committed R42-C source/test bytes reverified | PASS |
| Actual pytest under nonroot Python3.13.5 | **48/48 PASS**, replicated under strict/dev and coverage configurations |
| Python 3.12 grammar-only parsing | PASS (does not substitute for Python3.12 runtime) |
| Mutation detection for R42-C timestamp regression | PASS: removal caused **3 intentional failures** |
| Targeted coverage (R42 module only) | 88% |
| **Actual Python 3.12 pytest** | **PENDING** — interpreter not available on approved independent host |
| Ruff binary / dedicated lint execution | **PENDING** — Ruff unavailable |
| Full-repository regressions, Wheel installation and nonroot full PAPER flow | **PENDING** — whole repository and install prerequisites unavailable |
| R41 actual hostile-plugin rootless/gVisor host evaluation | **PENDING** |
| Authenticated provider provenance or remote account reconciliation | **NOT ESTABLISHED** |
| Stage15 9 P0 + 1 P1 | **UNCHANGED** |
| LIVE / public signals / brokerage / production | **HARD DENY** |

**Interpretation:** The previously open "exact committed tests not executed" sub-gate is **now closed for Python 3.13.5 only**. The larger R42-V operational acceptance remains blocked on independent Python3.12, Ruff, complete installed test and external evidence. No server, broker, live permission, untrusted core or Telegram operation was used.
