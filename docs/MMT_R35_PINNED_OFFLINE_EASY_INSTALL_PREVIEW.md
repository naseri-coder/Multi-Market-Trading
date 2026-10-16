# MMT R35 — Hash-Pinned Offline Easy Install Preview

Status: DRAFT; release, production, connected PAPER, Telegram and LIVE denied.

## Purpose

This stage introduces a separate local-only prebuilt Wheel installer for
public multi-market-trading 0.4.0rc1, distinct from the historical
crypto-price-action 0.3.2 launcher and Docker/DB namespace. It is not
an in-place upgrade, an operational trading deployment, nor a way to
install private NY First-Reversal code or run the frozen Brooks worker.

R34 operator evidence: 135 selected R28-R34 tests, 31 A6/Stage15/toy
tests, genuine isolated Wheel build, its independent SHA256 verification,
fresh offline isolated venv install, synthetic strategy smoke, persistent
toy PAPER idempotence, SQLite online backup/restore and post-restore
duplicate refusal all passed. These are bounded test claims, not release
authorization. The R27 frozen Brooks worker remains deferred.

## Entry points and security boundary

The new scripts/mmt_r35_offline_preview_install_v1.py has two modes.

--check-only is read-only. It requires Python 3.12, MMT_NONPRODUCTION=1,
and explicit absolute local Wheel, its full expected SHA256, and a
nonexistent absolute destination outside the checkout under a private
owned 0700 parent. It validates the Wheel ZIP, distribution metadata,
relevant public-only entrypoints and forbidden paths before returning
R35_OFFLINE_WHEEL_PREFLIGHT_PASS. It can run as root in the existing
disposable Termux PRoot lab because it makes no writes or subprocesses.

--install requires the same plus explicit
--ack-offline-preview-install, and MUST run as a non-root operator.
It creates a new private destination, an isolated venv using Python
ensurepip, and a private copy of the pinned Wheel. It then invokes
pip install --no-index --no-deps --no-cache-dir with a sanitized
environment, pip check and only the inert naseri-markets --check CLI.
Neither Telegram optional extra nor network dependency resolver is used.
It never executes PAPER replay or adds broker, signal, bot or service
processes. On failure it retains the new directory for manual review
rather than recursively removing or overwriting potentially modified
files. Successful completion is identified only by
R35_INSTALLED_OFFLINE_PREVIEW_PASS_RELEASE_DENIED plus a private JSON
report in the newly created directory.

SHA256 verifies *identical bytes* only, not publisher signature,
code audit or software trust. This is not an OS-level network
sandbox. Do not run the actual installer on a server or a root
PROot shell merely to bypass an intended non-root gate.

## Safe root Termux acceptance command (no installation)

Run from R35 checked-out branch with previously verified Wheel:

    cd /root/mmt-r34-lab/src
    unset MMT_PRODUCTION
    export MMT_NONPRODUCTION=1
    export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
    export PYTHONPATH="$PWD/production_source:$PWD"
    python -m scripts.mmt_r35_offline_preview_install_v1 \
      --check-only \
      --wheel /root/mmt-r34-wheel.7iTGsSLb/wheels/multi_market_trading-0.4.0rc1-py3-none-any.whl \
      --sha256 a99553947fba0e6a848e1c9b5cdb144408b70f380c8f713f43a14b393c15bc8f \
      --destination /root/mmt-r34-wheel.7iTGsSLb/r35-not-created

The destination must remain nonexistent. Run the separate R35 unit tests
with --noconftest and Ruff before considering an installation.
No R35 genuine Termux results have been received yet.

## Non-root deployment acceptance (future, NOT YET APPROVED)

A separately approved test must copy the pinned Wheel and installer to
a disposable non-root Linux account with a private owned target parent.
Only there, after explicit acknowledgment, may --install be invoked
using absolute paths. In the current user's root-only PRoot session
--install intentionally refuses.

The stacked Draft PR must not be merged or represented as product-ready.
Stage15's nine P0 and one P1 blockers remain unresolved.

## 2026-10-16 operator-proven Termux root check-only acceptance

The operator used their real disposable Ubuntu Python 3.12 Termux
environment and created a **detached worktree at
`eb8c6b62a4161f589abb5c8edcbf30bb0760cc60`**,
distinct from the original R34 tree. They executed the R35 test module
with `--noconftest` and disabled pytest plugin autoload, with explicit
`pytest_asyncio.plugin`; actual output: **`14 passed in 1.87s`**.

Their initial Ruff check reported **one style-only `SIM117` error**
(nested `with` statements in the symlink-archive negative fixture),
with no other errors reported. This specific test syntax has now been
rewritten as one parenthesized multi-context `with`, preserving the
test's original fixture/negative assertions; actual operator rerun
of Ruff and pytest on the amended head is **PENDING**.

The operator also ran genuine root-compatible **read-only
`--check-only`** against the previously hash-verified
`multi_market_trading-0.4.0rc1-py3-none-any.whl`. Actual stdout included
`verdict=R35_OFFLINE_WHEEL_PREFLIGHT_PASS`, `wheel_members=226`,
`wheel_bytes=787808`, SHA256
`a99553947fba0e6a848e1c9b5cdb144408b70f380c8f713f43a14b393c15bc8f`,
`writes_performed=false`, and all LIVE/broker/Telegram/production
permissions false. Their negative output confirmed
`NO_INSTALL_WRITES_CONFIRMED` and `git status --short` returned empty.

**Bounded decision:** `R35_CHECK_ONLY_OPERATOR_PASS`, but
`R35_INSTALLATION_NOT_YET_ACCEPTED` (the actual non-root path was
not run). Do not merge Draft PR, circumvent non-root checks, install
old v0.3.2 runtime or operate any connected/live services.

## 2026-10-16 operator rerun at corrected R35 HEAD — PASS

In the disposable Android/Termux PRoot Ubuntu Python 3.12 test checkout
`/root/mmt-r35-lab`, the operator fast-forwarded to exact Git commit
`1d0795126e226d72b276cda86e9dcf49c8198121`. The real command
`python -m ruff check --no-cache` for both the R35 installer and its
unit test returned **`All checks passed!`**, and isolated
`pytest -q -p no:cacheprovider -p pytest_asyncio.plugin --noconftest`
for the R35 unit module returned **`14 passed in 3.49s`**.
The operator's `git status --short` reported no local changes.

These results supersede the earlier pending style-retest note. The
previous operator `--check-only` against the exact SHA256-pinned local
Wheel had already returned `R35_OFFLINE_WHEEL_PREFLIGHT_PASS` and
`NO_INSTALL_WRITES_CONFIRMED` at the same application-code version;
the intervening change only reformatted one negative test and this
document. No actual R35 `--install` was performed.

**Verified status:** `R35_RUFF_AND_14_UNIT_PASS` +
`R35_CHECK_ONLY_PASS`. **Outstanding:**
`R35_REAL_NONROOT_INSTALL_AND_ISOLATED_RESULT_PENDING`. The current
PRoot root identity cannot establish a genuine independent kernel-level
non-root security boundary; an emulated UID in PRoot should never be
reported as an independent host-isolation acceptance. Before any
further state-changing test, inspect the available environment and
identify an explicitly disposable non-root test context. Keep this PR
Draft, preserve historical runtime and refuse real trading/Telegram.

## 2026-10-16 environment discovery: non-root installation not yet established

The operator reported real `id` output from the disposable PRoot Ubuntu:
`uid=0(root) gid=0(root)`, with Android supplementary AIDs.
`runuser`, `su`, `useradd`, `setpriv` and the Termux `proot`
executable are visible. `python3.12 --version` returns **3.12.3**.
An existing `nobody` entry is `uid=65534 gid=65534` with a
`/usr/sbin/nologin` shell. Root-only paths are reported as
`/root` = `0700` and the local verified Wheel laboratory
`/root/mmt-r34-wheel.7iTGsSLb` = `0700`; only
`/root/mmt-r35-lab` = `0755`, but its `/root` parent is private.
`git status --short` shows no modifications.

These facts mean **availability of UID-changing commands does not yet
prove a working non-root context**. Do not `chmod` the root directory
or the private Wheel laboratory; do not copy sensitive artifacts to a
public temporary directory. The next harmless diagnostics are
`runuser -u nobody -- /usr/bin/id` and
`setpriv --reuid=65534 --regid=65534 --clear-groups /usr/bin/id`,
capturing whether PRoot permits those calls. If either succeeds, it
must still be treated as a *PRoot functional test only*, not OS
host-isolation or production installation certification.
R35 real non-root installation remains **PENDING** and the draft is
unmerged.

## 2026-10-16 real UID feasibility check PASS in Android PRoot

The operator ran two actual identity checks inside their disposable
Ubuntu 24.04 PRoot environment (no files or users created):

- `runuser -u nobody -- /usr/bin/id` exited **0** and printed
  `uid=65534(nobody) gid=65534(nogroup)`.
- `setpriv --reuid=65534 --regid=65534 --clear-groups /usr/bin/id`
  exited **0** with the same UID/GID.
- Running `id` in the original shell still printed `uid=0(root)`.

The PRoot process retained Android supplementary groups; neither
result is independent OS host-isolation or a proof that filesystem
ownership, pip/venv creation, network containment or all Linux
privilege restrictions work as on a standard non-root host.

**Proposed next functional acceptance (not yet executed):**
have the `nobody` process create an unpredictable **0700** private
temporary directory in `/tmp` and verify its actual owner/mode; copy
**only** the already-hash-verified public 0.4.0rc1 Wheel and new R35
installer Python source into that sandbox without opening `/root`
permissions. Run the R35 opt-in `--install` using Python 3.12 as
`nobody` and a new destination inside that owned private sandbox;
assert SHA256, `pip --no-index --no-deps`, installed CLI deny flags,
and private install report. This would count as
`R35_PROOT_NONROOT_FUNCTIONAL_INSTALL`, never real independent host
security or production release. On any failure, stop without changing
the non-root refusal gate; do not delete incident artifacts silently.

## 2026-10-16 filesystem identity mismatch: PRoot non-root install HALTED

The operator first exited the PRoot container unintentionally during
a previous `set -e` command; the Android Termux shell did not have
`runuser` or `/tmp`. They then returned to the existing Ubuntu
container using `proot-distro login mmt-r34-lab`, confirming
`uid=0(root)`, Python **3.12.3** and `runuser`.

An actual probe of the proposed PRoot-nonroot installation destination
returned:

```text
CREATE_EXIT=0
PROBE_DIR=/tmp/mmt-r35-probe.MceoFspU
700 0:0 /tmp/mmt-r35-probe.MceoFspU
WRITE_EXIT=0
```

The new probe directory was created by
`runuser -u nobody -- mktemp -d /tmp/mmt-r35-probe.XXXXXXXX`,
yet `stat` in the parent shell reported the directory owner as
**UID 0 / GID 0** (not the apparent 65534 identity) with mode 0700.
`runuser -u nobody -- test -w "$AREA"` returned success, but
`test -w` is an access check and is **not proof of an actual write
operation**. Thus, the emulated-user identity, filesystem ownership
and effective permission behavior are inconsistent with assumptions
required for proving independent non-root confinement. The existing
R35 installer's `_new_destination` requires owner `st_uid` to match
`os.geteuid()` and a 0700 parent; do **not** weaken this check, chown
/chmod private root directories, or silently treat virtual PRoot IDs as
a kernel isolation boundary.

**Decision:** `R35_PROOT_FILESYSTEM_IDENTITY_INCONSISTENT`;
`R35_NONROOT_INSTALL_UNVERIFIED`; no successful R35 `--install`
output was observed. A focused, read-only Python UID/stat diagnostic
inside the emulated `nobody` context can clarify the precise mismatch.
A real non-root acceptance should occur only in an appropriately
isolated ordinary Linux account/environment with verified on-disk UID
and permissions, not by adjusting source guards or claiming permission
from PRoot ID translation. Keep this PR Draft and release denied.
