#!/usr/bin/env python3
"""Fail-closed checks for a fresh, isolated install. Never echo values."""

import re
import stat
import sys
from pathlib import Path
from urllib.parse import urlsplit

path = Path(sys.argv[1] if len(sys.argv) > 1 else ".env")


def fail(name: str) -> None:
    raise SystemExit("ENV_PREFLIGHT_FAIL: " + name + " (value suppressed)")


if not path.is_file() or path.is_symlink():
    fail("private .env missing/invalid")
if stat.S_IMODE(path.stat().st_mode) & 0o077:
    fail(".env must be chmod 600")

env: dict[str, str] = {}
for line in path.read_text().splitlines():
    if not line.strip() or line.lstrip().startswith("#"):
        continue
    if "=" not in line:
        fail("invalid line")
    key, value = line.split("=", 1)
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key) or key in env:
        fail("invalid/duplicate key")
    env[key] = value

required = {
    "APP_ENV",
    "LOG_LEVEL",
    "LOG_FORMAT",
    "ADMIN_IDS",
    "TELEGRAM_RUNTIME_ENABLED",
    "TELEGRAM_BOT_TOKEN",
    "BROOKS_RUNTIME_ENABLED",
    "BROOKS_OPERATIONS_ENABLED",
    "PAPER_RUNTIME_ENABLED",
    "PERFORMANCE_REPORTS_ENABLED",
    "DB_ECHO",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "DATABASE_URL",
}
optional = {"BROOKS_SCALE_IN_MODE"}

if set(env) - required - optional:
    fail("unsupported environment variable")
if required - set(env):
    fail("missing required environment variable")
if env["TELEGRAM_BOT_TOKEN"] != "":
    fail("TELEGRAM_BOT_TOKEN must be empty")


def must(name: str) -> str:
    value = env.get(name, "")
    if not value or "REPLACE_" in value:
        fail(name)
    return value


if must("APP_ENV") != "production":
    fail("APP_ENV")

admin = must("ADMIN_IDS")
if not all(
    re.fullmatch(r"[0-9]{1,19}", item) and 0 < int(item) <= 2**63 - 1
    for item in admin.split(",")
):
    fail("ADMIN_IDS")

if must("TELEGRAM_RUNTIME_ENABLED").lower() != "false":
    fail("TELEGRAM_RUNTIME_ENABLED: staging defaults must remain off")

for key in (
    "BROOKS_RUNTIME_ENABLED",
    "BROOKS_OPERATIONS_ENABLED",
    "PAPER_RUNTIME_ENABLED",
    "PERFORMANCE_REPORTS_ENABLED",
    "DB_ECHO",
):
    if env.get(key, "false").lower() != "false":
        fail(key)

if env.get("BROOKS_SCALE_IN_MODE", "disabled") != "disabled":
    fail("BROOKS_SCALE_IN_MODE")

user = must("POSTGRES_USER")
database = must("POSTGRES_DB")
password = must("POSTGRES_PASSWORD")

if not re.fullmatch(r"[a-z_][a-z0-9_]{0,30}", user):
    fail("POSTGRES_USER")
if not re.fullmatch(r"[a-z_][a-z0-9_]{0,30}", database):
    fail("POSTGRES_DB")
if not re.fullmatch(r"[A-Za-z0-9_-]{24,96}", password):
    fail("POSTGRES_PASSWORD")

try:
    parsed = urlsplit(must("DATABASE_URL"))
    valid = (
        parsed.scheme == "postgresql+asyncpg"
        and parsed.hostname == "postgres"
        and parsed.port == 5432
        and parsed.username == user
        and parsed.password == password
        and parsed.path == "/" + database
        and not parsed.query
        and not parsed.fragment
    )
except (TypeError, ValueError):
    valid = False

if not valid:
    fail("DATABASE_URL: must match disposable postgres service")

print("ENV_PREFLIGHT_PASS (values not displayed)")
