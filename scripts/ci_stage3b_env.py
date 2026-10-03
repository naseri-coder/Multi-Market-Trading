#!/usr/bin/env python3
"""Runner-only synthetic config fixtures. Never display generated credentials."""

import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("RUNNER_ONLY: synthetic environment test")
if (ROOT / ".env").exists():
    raise SystemExit("REFUSED: unexpected pre-existing .env")
for key in (
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "DATABASE_URL",
    "TELEGRAM_BOT_TOKEN",
):
    if key in os.environ:
        raise SystemExit("REFUSED: inherited credential-related environment variable")

password = secrets.token_urlsafe(36)
template = (ROOT / ".env.example").read_text()
assert template.count("REPLACE_WITH_NEW_RANDOM_URLSAFE_PASSWORD") == 2
source = template.replace("REPLACE_WITH_NEW_RANDOM_URLSAFE_PASSWORD", password)
source = source.replace("REPLACE_WITH_NUMERIC_ADMIN_ID", "123456789")
source = source.replace("ADMIN_IDS=1", "ADMIN_IDS=123456789")
# The public example is intentionally development-safe; Stage3B validates the
# stricter fresh-host production contract using a runner-only synthetic file.
source = source.replace("APP_ENV=development", "APP_ENV=production")
source = source.replace("LOG_FORMAT=console", "LOG_FORMAT=json")
assert "REPLACE_" not in source


def write_private(path: Path, value: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as file:
        file.write(value)


def validate(path: Path) -> bool:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_env.py"), str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


write_private(ROOT / ".env", source)
assert validate(ROOT / ".env"), "Synthetic good config rejected"
bad_cases = [
    source.replace("ADMIN_IDS=123456789", "ADMIN_IDS=9223372036854775808"),
    source.replace("TELEGRAM_BOT_TOKEN=", "TELEGRAM_BOT_TOKEN=synthetic-not-real"),
    source.replace("BROOKS_RUNTIME_ENABLED=false", "BROOKS_RUNTIME_ENABLED=true"),
    source + "UNKNOWN_CONFIGURATION=synthetic\n",
    source.replace("@postgres:5432/", "@external.invalid:5432/"),
    source.replace("LOG_FORMAT=json\n", ""),
    source + "ADMIN_IDS=123456789\n",
]
with tempfile.TemporaryDirectory(prefix="stage3b-", dir=ROOT) as work:
    for idx, contents in enumerate(bad_cases):
        path = Path(work) / f"case-{idx}.env"
        write_private(path, contents)
        assert not validate(path), f"Unsafe synthetic case {idx} accepted"

print("SYNTHETIC_ENV_PASS: one accepted, seven rejected; secret values suppressed")
