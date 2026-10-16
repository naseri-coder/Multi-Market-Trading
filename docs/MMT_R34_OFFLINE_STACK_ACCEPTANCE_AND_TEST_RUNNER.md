# MMT R34 — Independent Test-Coverage Preparation and Offline Acceptance Evidence

**Status:** development Draft stacked on R33 PR #326, not main, no actual LIVE, connected PAPER, broker/MT5/Telegram sender, server deployment or GitHub Actions run.

## Why R34 comes next

R27 (PR #320) through R33 (PR #326) are still **OPEN DRAFT UNMERGED** as observed on October 16, 2026. Repeated additions of new feature phases without running real tests leave accumulated acceptance debt. R34 addresses this with a deterministic test runner and deny-only acceptance matrix rather than another trading subsystem. It neither merges existing PRs nor claims that they pass. The original R29 prospective Brooks study is Oct 20–Nov 3 UTC, still in the future on this date.

### New modules

- `naseri_markets/mmt_r34_offline_stack_acceptance_v1.py`: immutable, exact-order eight-stage test evidence contract R27–R34, Ruff, full unit suite, AST static syntax. Values PASS, FAIL, TIMEOUT, UNAVAILABLE and NOT_RUN are explicit. PASS requires process exit 0 **and a SHA256 of test output**. It checks pinned/observed Git HEAD equality, checkout cleanliness, whether tests really ran, and six distinct independent upstream/OOS/account/recovery gates. Every result, including all PASS with every claimed external proof flag TRUE, ends `REVIEW_ONLY_RELEASE_BLOCKED` and grants zero order/Telegram/LIVE/deploy actions. Test-output digest is a local accountability primitive, not external attestation.
- `scripts/mmt_r34_manual_stack_acceptance_v1.py`: operator-run stdlib CLI. Requires `MMT_NONPRODUCTION=1`, explicit human consent, a SHA-pinned clean, absolute non-symlink checkout; static Python AST parsing of all sixteen changed R27–R34 source modules and all eight stage unit test files. Separately opt in to eight stage tests, Ruff, and/or entire `tests/unit` suite. Never starts GitHub Actions or runs an install/deployment command.
- `tests/unit/test_mmt_r34_offline_stack_acceptance_v1.py`: checks malformed/faked evidence, ordered stage inventory, even all-green hard refusal, no accidental test subprocess invocation without opt-in, tightly scoped commands, redaction of ambient credential environment, output directory privacy and exclusive non-overwriting report creation.

## Security boundary and limitations

This runner executes *repository Python test code* when you explicitly select `--run-stage-tests` or `--run-full-unit-suite`; running tests can trigger arbitrary actions if the repository is malicious. Environment sanitization, disabled plugin auto-loading, dummy network proxies and no automatic API credentials are **not a network sandbox**. Thus **only use a disposable NONPRODUCTION Termux environment or equivalently isolated test system**, after reviewing the exact repo content. Do not run on the production Telmivo server, another operational trading server, a host with live broker credentials, or a persistent production DB. Do not claim the runner provides independent provenance or fully hermetic test execution.

It uses fixed `sys.executable -m pytest` arguments with no shell and `-p pytest_asyncio.plugin` explicitly, because `pyproject.toml` requires pytest-asyncio; `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` prevents uncontrolled plugin discovery. `-p no:cacheprovider` and `PYTHONDONTWRITEBYTECODE=1` reduce local writes. Ruff invokes `python -m ruff check`. Each stage is given 240 seconds; full unit suite has an explicit 900-second timeout. Review later whether more time is warranted on an Android device. `PIP_NO_INDEX=1` prevents pip repository access from this helper but does not block arbitrary network calls by third-party test code. No log stdout/stderr is printed; only exit outcome and hashed output are exported. No test command is automatically retried.

## Python compatibility and source checkout limitations

The **repository's actual `pyproject.toml`** declares `requires-python >=3.12,<3.13` and development pins `pytest==9.1.1`, `pytest-asyncio==1.4.0` and `ruff==0.16.9`. The R34 runner now **refuses executing pytest with any Python other than 3.12** rather than recording misleading success/failure. Check `python --version` and ensure dependencies are installed independently in a throwaway NONPRODUCTION environment before requesting stage/full pytest. Ruff and read-only AST review alone do not establish executable acceptance.

**2026-10-16 session limitation:** an accessible isolated sandbox provided Python 3.13.5, pytest 9.0.2 and pytest-asyncio 1.3.0 (Ruff absent), with no complete Git checkout and no direct github.com name resolution. Therefore there is **no valid real R27–R34 full-suite PASS in this session**. GitHub source-file existence and ancestry checks are not the same as executing the repository tests. Do not start operational or LIVE services to work around these limitations.

The runner explicitly discards inherited `PYTHONPATH`, `PYTHONHOME`, `PYTEST_ADDOPTS`, `PYTEST_PLUGINS`, Python startup hooks and user-site package paths; for a **separate disposable test checkout**, it reconstructs `PYTHONPATH` exclusively from the chosen checkout's `production_source` and repository root, because the shared `tests/conftest.py` imports the historical `app.core.config`. It remains **not an OS sandbox** and must never run on a production server.

## Manual exact-commit Termux validation

First inspect the PR, commit and source in GitHub. Work on a **new disposable checkout**; never touch an operational directory. Check the branch commit immediately before running:

    cd "$HOME/Multi-Market-Trading-R34-TEST"
    git status --short
    git rev-parse HEAD

Copy the exact **current R34 PR head SHA** after independently comparing it with the GitHub PR. For example:

    export MMT_NONPRODUCTION=1
    unset MMT_PRODUCTION
    mkdir -m 700 -p "$HOME/mmt-r34-audit"
    python -m scripts.mmt_r34_manual_stack_acceptance_v1 \
      --source-root "$PWD" \
      --expected-head REPLACE_WITH_EXACT_R34_COMMIT_SHA \
      --run-stage-tests \
      --run-ruff \
      --output-private-json "$HOME/mmt-r34-audit/stage-tests.json" \
      --ack-execute-local-repository-tests

A separate, more intensive (not run by default) option is `--run-full-unit-suite`. On any missing tests, invalid pinned HEAD, not-clean source, timeout, import failure, Ruff issue, or missing dependency, the evidence report describes the failure rather than guessing a PASS. The command intentionally exits with status **1 even if all local tests passed** because release remains blocked; exit 2 means preflight/refusal.

The JSON report must be kept in a previously created private `0700` owner directory **outside** the checkout, written as a new `0600` file using exclusive creation. Any attempt to overwrite a previous report or write inside the checkout is refused.

## Gate acceptance checklist for actual human review

1. Execute the six R28–R33 unit test files plus R27, Ruff and full unit suite on exact final R34 SHA; retain original logs privately with independent custody. The runner only stores their SHA256 for comparison and *does not itself retain raw logs*.
2. Reconcile and correct any failing test/fixture/code finding in its owning PR. **Do not infer a pass from tests existing in GitHub.**
3. Independently run CodeQL/Publication Safety, dependency and supply-chain inspection, and R32 review-kit+disposable cold restore. GitHub Actions quota is known to be constrained; manual local execution is permissible, but independently attested verification is still necessary.
4. Review stacked PR ancestry and branch protection from oldest first. R27 and earlier ancestors may still be Draft; do not merge R34 independently onto an unapproved main. Do not merge any PR automatically.
5. R29 original forward closed-candle data and independent performance/risk witness are not available until after the Oct20–Nov3 study; keep PAPER/LIVE claims separate from synthetic fixture results.
6. Verify exchange-specific jurisdiction/API permission, trusted live account snapshot, liquidation/fee/funding semantics, crash/UNKNOWN handling and independently monitored one-way kill switch before even considering a further separate LIVE-specific approval.

**As of creation of this PR:** GitHub tool verification of changed files and PR lineage is available. **Full repo pytest, Ruff, CodeQL, actual future market research, cold restore and signed deployment have NOT been executed here.**

**Disposition:** `MMT_R34_OFFLINE_TEST_EVIDENCE_PREPARED_NOT_ACCEPTED` — no release, no merge, no orders.

## 2026-10-16 continuation: performed Python file inventory check (limited PASS)

A real GitHub connector comparison enumerated the changed filenames for PRs #320 through #327 (R27–R34). It computed their distinct changed Python source/test paths, and compared the result against this PR's static sources, per-stage unit tests and R34 self-test.

| Audit item | Observed |
|---|---|
| PRs reviewed by filename | 8 (#320–#327) |
| Distinct changed Python files | 24 |
| Python source and CLI files in static audit | 16 |
| Python test files in static audit | 8 |
| Changed Python files missing from source/test inventory | **0** |
| Unexpected Python files in declared inventory | **0** |
| Result of filename-coverage comparison | **PASS** |

This is ONLY a filename/coverage comparison. It does **not** mean AST passed, Ruff passed, pytest passed, CodeQL passed, security or provenance independently verified, or LIVE approved.

The coverage gap was corrected: R27 source, R28 supervisor modification, R29 CLI modules, R32 review CLIs and R33 CLI are now included. The test runner was also amended to launch explicitly approved tests in a separate POSIX session and kill the process group on deadline, instead of potentially leaving subprocess children. Synthetic negative regressions were authored but **not executed**. The test runner now refuses Python versions other than 3.12 for pytest and checks local source bytes against pinned Git blobs before/after each selected session.

**Remaining execution blocker:** the local sandbox cannot download the full GitHub checkout; available Python is 3.13.5 rather than project-required 3.12. Consequently the actual R27–R34 pytest, full unit suite, Ruff and CodeQL remain **NOT_RUN**, not PASS. No GitHub Actions, server or production service was used.

## 2026-10-16 additional acceptance hardening

The available **isolated local sandbox was inspected directly** (not guessed):

| Actual installed tool | Actual version | Required version | Result |
|---|---:|---:|---|
| Python | 3.13.5 | 3.12.x | INCOMPATIBLE |
| pytest | 9.0.2 | 9.1.1 | INCOMPATIBLE |
| pytest-asyncio | 1.3.0 | 1.4.0 | INCOMPATIBLE |
| Ruff | missing | 0.16.9 | NOT INSTALLED |
| Full repository checkout | unavailable | exact pinned Git HEAD | UNAVAILABLE |

**Real integration test disposition: BLOCKED_BEFORE_EXECUTION.** Do not label unit, integration, Ruff, security or performance tests PASS. Only separately enumerated GitHub content/PR-change coverage checks were performed.

R34 now checks all of these pinned Python and test toolchain versions before launching pytest/Ruff. Child output to its temporary spool has a **4 MiB ceiling** (bounded inspection every ~200ms), and process groups are terminated on timeout/output overflow. Such a limit does not guarantee no single instantaneous output burst or all possible process escape; do not run untrusted code on a host with operational data. Source-code only regressions were added for these defenses but they have NOT been executed in a Python 3.12 checkout.

This PR remains Draft with no LIVE, no merge, no server access and no GitHub Actions.

## R34 stage completeness and bounded-output follow-up

The stage-by-stage test flag now explicitly includes **R34's own unit tests**
in addition to R27–R33. All eight stage outcomes are required and ordered in
the acceptance report; full unit suite remains an additional independent
selection. The Ruff and source-byte/AST inventories include all 24 Python
files changed in the PR #320–#327 lineage **exactly once**.

A locally running test process can produce excessive stdout/stderr and fill a
disposable device's disk. The subprocess capture is now limited to 4 MiB per
command, polled at bounded intervals; `OUTPUT_LIMIT` is an explicit failed
terminal state, never PASS. Timeout/output overflow kills the separately
created POSIX process group. Although this bounds routine output under normal
scheduling, it is not a hard OS resource quota or a sandbox against hostile
forked/detached processes. Run only reviewed code in an isolated test host.

The runner now checks exact installed development versions *without importing
pytest plugins*: pytest 9.1.1, pytest-asyncio 1.4.0 and Ruff 0.16.9. Python
3.12 remains mandatory for pytest. No real R27–R34 test pass has been claimed
in this PR without a proper, exact-commit disposable checkout.
