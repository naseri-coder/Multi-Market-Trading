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

## 2026-10-16 additional source review: POSIX child lifecycle + Git environment

Two independent, disposable local demonstrations were **actually executed** outside the project checkout:

1. A test parent spawned a sleeping subprocess, then itself exited with return code 0. Checking its private POSIX process group correctly found the surviving child and a SIGKILL signal was issued to that group. This validates the operating-system behavior used by the new R34 group-lifecycle guard, **not** a passed R34 repository unit test.
2. A temporary local `git init` checkout behaved normally with Git's environment cleared; a deliberately injected `GIT_DIR` / `GIT_WORK_TREE` caused the Git check to fail, while a minimally-whitelisted environment and disabled Git hooks/fsmonitor restored the expected normal checkout result. This demonstrates that ambient Git variables can affect acceptance checks.

The R34 source was amended accordingly:
- after the direct test-runner process finishes, probe the original isolated process group; if any process remains, issue group termination and record `ORPHANED_CHILD_GROUP` rather than `PASS`, regardless of its exit code;
- pass only whitelisted environment variables to Git, force noninteractive/optional-lock-free read-only operations, and disable `core.fsmonitor`, hooks and submodule recursion to prevent dangerous ambient or repo-local Git behavior;
- add deterministic negative unit tests for both cases. These tests are **authored but not yet executed against the complete project checkout**.

**Limitations:** These protections cannot detect descendants that call `setsid`, avoid PID/process-group reuse races, or constitute OS sandboxing and independent signed evidence. Never run untrusted tests on an operational server. No Merge, LIVE, real account or production environment was used.


## Android-only execution route: Ubuntu 24.04 in Termux (manual, unexecuted here)

A workable **version-specific** path is Termux \`proot-distro\` with \`ubuntu:24.04\` on Android, instead of changing a trading/Telegram production host or trying to force Python 3.13 into a Python 3.12-only project. Official \`termux/proot-distro\` README documents \`pkg install proot-distro\`, \`proot-distro install ubuntu:24.04\`, \`--name\`, and \`proot-distro login\`; it does **NOT** claim Docker-grade kernel/network isolation. This guide requires internet, sufficient spare storage and manual approval; no command has been run on the operator's phone.

**In Termux (outside any production folder):**

    pkg update
    pkg install proot-distro git
    proot-distro install ubuntu:24.04 --name mmt-r34-lab
    proot-distro login mmt-r34-lab

**Inside the fresh Ubuntu 24.04 instance (NOT inside an existing bot installation):**

    apt-get update
    apt-get install -y ca-certificates git python3.12 python3.12-venv
    python3.12 --version
    mkdir -p /root/mmt-r34-lab
    cd /root/mmt-r34-lab
    git clone --single-branch \
      --branch feature/mmt-r34-offline-stack-acceptance-evidence-v1 \
      https://github.com/naseri-coder/Multi-Market-Trading.git src
    cd src
    git status --porcelain=v1 --untracked-files=all
    git rev-parse HEAD

**CRITICAL:** Independently compare printed HEAD to the GitHub PR #327 head displayed at execution time. Do **not** run any tests if different, dirty, or untrusted. Put that independently reviewed exact 40-hex SHA in the final command in place of \`REPLACE_WITH_VERIFIED_PR327_HEAD\`. Use the full exact hash, never a branch name as an authority token.

Create a venv OUTSIDE the audited Git checkout and install exactly the versions from the committed \`pyproject.toml\` (this step can take time on an Android ARM device and can fail if wheels are unavailable):

    python3.12 -m venv /root/mmt-r34-venv
    . /root/mmt-r34-venv/bin/activate
    python -m pip install --upgrade pip
    python -m pip install \
      'pytest==9.1.1' 'pytest-asyncio==1.4.0' 'ruff==0.16.9' \
      'alembic==1.20.0' 'asyncpg==0.31.0' 'httpx==0.28.1' \
      'matplotlib==3.11.2' 'numpy==2.5.3' \
      'pydantic-settings==2.15.0' 'python-telegram-bot==22.8' \
      'SQLAlchemy[asyncio]==2.0.54' 'tzdata==2026.4' \
      'build==1.6.1' 'pyproject-hooks==1.3.3'
    python --version
    python -m pytest --version
    python -m ruff --version
    git status --porcelain=v1 --untracked-files=all

If package installation fails, **stop and report the exact dependency/version failure**; do not substitute newer versions or falsely mark acceptance PASS. A reproducible requirements lock with hashes will be a separate supply-chain review, not presumed satisfied by pip version pins alone. Do not install the project itself in editable mode into the pinned Git checkout; this can dirty the source inventory.

Run the intentionally **deny-only** R34 script from this reviewed disposable checkout, without any real broker credentials or Telegram bot token:

    export MMT_NONPRODUCTION=1
    unset MMT_PRODUCTION
    mkdir -m 700 -p /root/mmt-r34-audit
    python -m scripts.mmt_r34_manual_stack_acceptance_v1 \
      --source-root "$PWD" \
      --expected-head REPLACE_WITH_VERIFIED_PR327_HEAD \
      --run-stage-tests --run-ruff \
      --output-private-json /root/mmt-r34-audit/local-acceptance.json \
      --ack-execute-local-repository-tests

The test runner returns exit code **1 even on locally all-green tests** because independent release authorization is intentionally denied; 2 means refusal/preflight failure. Once the first run is reviewed, \`--run-full-unit-suite\` may be added for a **separate manually authorized local rerun**, using a **new** report filename. Never reuse an existing report path, because the script refuses overwrite. Do not use \`sudo\` or native broker APIs, operational SQLite databases, token files, Docker sockets, production services, server access, GitHub Actions, or external Telegram sending.

**Limitations:** PRoot is not a security sandbox against deliberately malicious local processes; review the exact Git checkout before enabling test execution. Termux background lifecycle, network restrictions, RAM/storage, ARM binary wheels and Python package availability may prevent completion. This route is **prepared but unverified on the operator's Android device**, not a record of passing pytest/Ruff.

## 2026-10-16: first genuine Termux R34 pytest results and follow-up

The operator verified the exact GitHub PR #327 head `48920b1d27e141ee95cfacd398c3e6ce47f2c651` on a separately installed Ubuntu 24.04 PRoot environment, with Python 3.12.3, pytest 9.1.1, pytest-asyncio 1.4.0 and Ruff 0.16.9; `git status --short` was clean. The operator **actually ran Ruff on the three R34 files and obtained `All checks passed!`** after a three-issue I001/SIM105 correction.

The operator then ran isolated R34 pytest with `--noconftest` and reported exactly **30 passed / 2 failed** (3.02 s). Both failures occurred in `_private_new_report` before file creation. Confirmed root cause on POSIX Python: the strict `type(path) is not Path` check rejects the `PosixPath` object returned by `Path(...)`. A separate unverified portability risk existed in `Path.resolve(strict=True) != path.parent`, so the fix removes this textual canonicalization dependency as well. The first expected a private report creation; the second expected a `PRIVATE_0700` error for a public `0755` directory but instead encountered premature `PRIVATE_NEW_REPORT_PATH_REQUIRED`.

The fix deliberately **does not remove private-directory or symlink protection**. It opens the immediate parent with `O_DIRECTORY | O_NOFOLLOW`, verifies owner, `0700` confidentiality and directory type via `fstat(dir_fd)`, and creates the new file relative to the verified directory file descriptor using `dir_fd=...`, `O_CREAT | O_EXCL | O_NOFOLLOW`, mode `0600`. It verifies new file mode/owner/type/link-count before writing and always closes the directory descriptor. This avoids reliance on pathname text equality that can differ under PRoot while eliminating the directory-swap race between check and write. New regression tests simulate an attacker replacing the directory's pathname with a link after it has been opened, and check that pre-existing symlink targets remain untouched.

**Acceptance is still pending.** The newly amended tests must be rerun on the operator's actual PRoot host; the old result `30 passed / 2 failed` does not count as PASS. Ruff and clean Git status must also be rechecked at the exact new PR head. No LIVE, network broker, GitHub Actions, server deployment or main merge is authorized.

### Correction to the observed test failure root cause

The immediate problem was **strict Python class identity**, not a proven PRoot canonical-path mismatch. On POSIX, `Path(...)` constructs a `PosixPath`, so `type(path) is not Path` is True and rejects valid inputs. Both the receipt routine and `_head` worktree validation now use `isinstance(value, Path)`. The worktree check also uses an opened `O_DIRECTORY | O_NOFOLLOW` directory descriptor and `os.path.samefile` for path-identity verification, without trusting `Path.resolve()` string equality. This changes neither the pinned Git SHA requirement nor dirty checkout refusal. A new test creates a **real local, disposable Git repository**, checks SHA and dirty-tree refusal, and rejects a symlinked checkout.

The prior reported result remains **30 passed, 2 failed** at commit `48920b1...`. The current PR now includes **three new negative tests** in addition to the original 32; running the new 35-test suite on the operator's Ubuntu 24.04 PRoot is necessary for acceptance. None of the new tests has been claimed as executed yet.

## R30 downstream offline acceptance: reproducible rejection-code mismatch

The operator ran **six** infrastructure test files (R28–R33, excluding the
previously reported frozen Brooks R27 worker failure) against PR #327 under
Python 3.12.3 in disposable Termux/Ubuntu and reported **40 passed, 1 failed**
with `--maxfail=1`. The first failing parameter case was R30
`test_r30_any_unsettled_runtime_effects_block[CLAIMED]`: an assertion expected
`R30_PENDING_DONE_OR_UNKNOWN_RUNTIME_EFFECTS` but code returned
`R30_UNVERIFIED_RUNTIME_OR_SIDE_EFFECTS`.

The safety outcome was **already fail-closed**: R30 first rejects
`manual_reconciliation_required=True` before inspecting nonzero runtime job
counts. The real runtime supervisor correctly sets this flag for CLAIMED or
QUARANTINED jobs. In R30's test fixture, these jobs also set the flag, so
the *outer* fence's rejection code is correct and the test expectation was
incorrect. Correcting the test does not relax or reorder either guard:
- CLAIMED / QUARANTINED with reconciliation flag set must reject under
  `UNVERIFIED_RUNTIME_OR_SIDE_EFFECTS`;
- the same nonzero counts with that flag (incorrectly) false must independently
  reject under `PENDING_DONE_OR_UNKNOWN_RUNTIME_EFFECTS`;
- manual reconciliation True with all counters zero still rejects;
- PENDING / DONE continue to reject due to nonzero counts.

Only the R30 **test** in this stacked R34 branch has changed; no R30 risk
logic or live trading code has been changed. This causes PR #327 to contain
one additional downstream test file; the earlier four-file R34-only count
is no longer true. The underlying R30 Draft PR #323 still requires explicit
forward/backport reconciliation before any stacked merge plan.

**Status:** new test cases are authored but **not yet executed** on the
operator's Ubuntu device. The first failing R30 assertion is diagnosed, not
claimed fixed by execution. Genuine Brooks R27 worker remains deferred and
not accepted, not deleted/waived.

## R32 offline kit PosixPath regression from real 2026-10-16 acceptance run

In a disposable Ubuntu 24.04 / Python 3.12.3 Termux test execution of six
selected R28–R33 infrastructure test modules (with `--noconftest`), the
operator reported **66 passed / 1 failed** and `--maxfail=1` stopped at
`test_r32_pinned_checkout_private_review_kit_roundtrip`:
`R32_ABSOLUTE_ROOT_AND_PIN_REQUIRED`. This is a real result, not a synthetic
claim. The cause is three erroneous strict type-identity checks of the form
`type(value) is not Path` in the R32 review kit. On POSIX Python,
`Path(...)` produces a concrete `PosixPath` and so legitimate arguments
were mistakenly rejected before validation.

The source correction is **only** to replace those three guards (for Git
checkout, existing private parent, and new destination) with
`not isinstance(value, Path)`. It retains checks of absolute paths, SHA-pinned
clean checkout, exact source blobs, symlink and output confinement, directory
ownership and mode `0700`, and exclusive `0600` report files. It does not
change Brooks, risk/order policy or LIVE boundaries. An additional negative
test ensures plain strings and symlinked private parents remain rejected,
while a real `PosixPath` is admitted.

**Acceptance status:** The new R32 source and negative test have been
committed to the stacked **Draft PR #327**. The operator must pull the new
PR head and re-run the R32 unit file, followed by all six R28–R33 files.
The earlier `66 passed / 1 failed` result does not become a PASS
until an actual subsequent run succeeds.
