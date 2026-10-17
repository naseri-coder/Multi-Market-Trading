"""Shared test configuration.

Two environment contracts are enforced here so that the public corpus is
reproducible on any Linux host and not only on an ephemeral GitHub runner:

* Every test runs with an explicit nonproduction acknowledgement
  (``MMT_NONPRODUCTION=1``), which is exactly what the operator-owned
  workflows export before invoking the same modules.  The production fences
  inside the product code are NOT touched: a module that requires the
  acknowledgement still refuses to run without it, and tests that assert that
  refusal keep deleting the variable locally.
* A test module declares the tests that genuinely need a disposable
  GitHub-hosted runner (``GITHUB_ACTIONS=true``, a non-root user with
  passwordless sudo and a systemd-managed host) with
  ``EPHEMERAL_RUNNER_REQUIRED = True`` for the whole module or
  ``EPHEMERAL_RUNNER_TESTS = frozenset({...})`` for individual tests.  Such
  tests are skipped with an explicit capability reason instead of failing on a
  normal workstation, and ``MMT_REQUIRE_EPHEMERAL_RUNNER=1`` turns the
  capability gap back into a hard failure so a capable host cannot hide a
  regression behind a skip.

The frozen release layout (``app/`` and ``migrations/``) is materialized here
exactly as the operator workflows do it, so the corpus also runs from a fresh
clone.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

# A fresh clone carries no materialized ``app/`` or ``migrations/`` copy at the
# repository root: CI runs ``cp -a production_source/app ./app`` before it
# imports the product package.  Importing the frozen ``production_source`` tree
# when that copy is absent keeps ``git clone && pytest`` working without
# touching the frozen bytes or the release-layout path contract tests.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FROZEN_SOURCE_ROOT = REPOSITORY_ROOT / "production_source"


def _materialize_frozen_layout() -> None:
    """Mirror the release-layout step the operator workflows run first.

    ``production_source/`` holds the frozen v0.3.2 bytes, while the product
    package is imported as ``app`` and several contract tests read literal
    ``app/...`` and ``migrations/...`` paths (and ``naseri_markets`` refuses a
    missing or symlinked frozen tree).  CI therefore runs
    ``cp -a production_source/app ./app`` before the corpus; doing the same here
    keeps ``git clone && pytest`` working, and never overwrites an existing
    directory.  Set ``MMT_SKIP_FROZEN_LAYOUT=1`` to opt out.
    """
    if os.environ.get("MMT_SKIP_FROZEN_LAYOUT") == "1":
        return
    import shutil
    for name in ("app", "migrations"):
        source, target = FROZEN_SOURCE_ROOT / name, REPOSITORY_ROOT / name
        if source.is_dir() and not target.exists():
            try:
                shutil.copytree(source, target, symlinks=True)
            except OSError:  # read-only clone: the import fallback below applies
                continue


_materialize_frozen_layout()

# A read-only clone cannot be materialized; importing the frozen tree still lets
# the corpus collect instead of failing during import.
if (not (REPOSITORY_ROOT / "app").is_dir()
        and (FROZEN_SOURCE_ROOT / "app").is_dir()):
    frozen_path = str(FROZEN_SOURCE_ROOT)
    if frozen_path not in sys.path:
        sys.path.insert(0, frozen_path)

from app.core.config import clear_settings_cache  # noqa: E402

ENVIRONMENT_KEYS = (
    "APP_NAME",
    "APP_ENV",
    "LOG_LEVEL",
    "LOG_FORMAT",
    "TELEGRAM_RUNTIME_ENABLED",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_POLL_TIMEOUT",
    "TELEGRAM_DROP_PENDING_UPDATES",
    "ADMIN_IDS",
    "REPORT_TIMEZONE",
    "BROADCAST_RATE_PER_SECOND",
    "BROADCAST_BATCH_SIZE",
    "BROADCAST_MAX_RETRIES",
    "BROADCAST_RETRY_AFTER_CAP_SECONDS",
    "DATABASE_URL",
    "DB_ECHO",
    "DB_POOL_SIZE",
    "DB_MAX_OVERFLOW",
    "DB_POOL_TIMEOUT_SECONDS",
    "DB_CONNECT_TIMEOUT_SECONDS",
    "ALL_PROXY",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "all_proxy",
    "http_proxy",
    "https_proxy",
    "no_proxy",
    "MMT_PRODUCTION",
)

# The public corpus is a nonproduction research run.  Each operator-owned
# workflow exports the acknowledgement explicitly; exporting it here as well
# keeps `MMT_NONPRODUCTION` deterministic for contributors without weakening
# any guard, because the production fences still read the variable at call time.
NONPRODUCTION_ENV_DEFAULTS = {"MMT_NONPRODUCTION": "1"}

EPHEMERAL_RUNNER_REQUIRED_ATTR = "EPHEMERAL_RUNNER_REQUIRED"
EPHEMERAL_RUNNER_TESTS_ATTR = "EPHEMERAL_RUNNER_TESTS"
EPHEMERAL_RUNNER_STRICT_ENV = "MMT_REQUIRE_EPHEMERAL_RUNNER"


def _configure_nonproduction_environment() -> None:
    for key, value in NONPRODUCTION_ENV_DEFAULTS.items():
        os.environ.setdefault(key, value)
    # A stale MMT_PRODUCTION=1 in a developer shell must never leak into the
    # corpus; individual tests that exercise the production fence set it
    # explicitly with monkeypatch.
    os.environ.pop("MMT_PRODUCTION", None)


_configure_nonproduction_environment()


def ephemeral_runner_gap() -> str | None:
    """Return the missing capability, or None when the host can run A23 tests.

    The checks mirror the preconditions that ``FixedCustomSandbox.launch``
    enforces before it will spawn a scoped worker, plus the systemd-managed host
    requirement of the ``systemd-run`` invocation itself.
    """
    if sys.platform != "linux":
        return "requires Linux"
    if os.geteuid() == 0:
        return "requires a non-root runner user"
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return "requires an ephemeral GitHub-hosted runner (GITHUB_ACTIONS=true)"
    if not os.environ.get("RUNNER_TEMP"):
        return "requires RUNNER_TEMP to be set by the runner"
    for binary in ("/usr/bin/sudo", "/usr/bin/systemd-run", "/usr/bin/python3"):
        if not Path(binary).is_file():
            return f"requires the runner image to provide {binary}"
    if not Path("/run/systemd/system").is_dir():
        return "requires a systemd-managed host (/run/systemd/system)"
    try:
        probe = subprocess.run(
            ["/usr/bin/sudo", "-n", "true"], stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "requires passwordless sudo for the runner user"
    if probe.returncode:
        return "requires passwordless sudo for the runner user"
    return None


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "requires_ephemeral_runner: disposable GitHub-hosted runner capability "
        "(systemd scope + passwordless sudo + non-root uid) is required",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item],
) -> None:
    del config
    gap = ephemeral_runner_gap()
    strict = os.environ.get(EPHEMERAL_RUNNER_STRICT_ENV) == "1"
    for item in items:
        module = getattr(item, "module", None)
        if module is None:
            continue
        whole_module = getattr(module, EPHEMERAL_RUNNER_REQUIRED_ATTR, False)
        declared = getattr(module, EPHEMERAL_RUNNER_TESTS_ATTR, None)
        if not whole_module and not declared:
            continue
        if not whole_module:
            function = getattr(item, "function", None)
            name = getattr(function, "__name__", item.name)
            if name not in declared:
                continue
        item.add_marker(pytest.mark.requires_ephemeral_runner)
        if gap is None or strict:
            continue
        item.add_marker(pytest.mark.skip(
            reason=f"ephemeral GitHub runner capability unavailable: {gap} "
                   f"(set {EPHEMERAL_RUNNER_STRICT_ENV}=1 to fail instead of skip)",
        ))


@pytest.fixture(autouse=True)
def isolate_settings(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Prevent developer environment and local dotenv files from affecting tests."""
    clear_settings_cache()
    monkeypatch.chdir(tmp_path)
    for key in ENVIRONMENT_KEYS:
        monkeypatch.delenv(key, raising=False)
    yield
    clear_settings_cache()


@pytest.fixture
def valid_token() -> str:
    """Return a syntactically valid, non-functional Telegram token."""
    return "123456789:" + "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"


@pytest.fixture
def valid_database_url() -> str:
    """Return a syntactically valid local PostgreSQL URL."""
    return "postgresql+asyncpg://crypto_bot:test_password@127.0.0.1:5432/crypto_bot_test"
