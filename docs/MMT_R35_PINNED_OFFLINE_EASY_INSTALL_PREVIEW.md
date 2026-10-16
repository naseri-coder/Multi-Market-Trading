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
