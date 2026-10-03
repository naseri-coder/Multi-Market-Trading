#!/usr/bin/env python3
"""Fail-closed stdlib preflight for a fresh isolated install. Never echo values."""

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
for raw in path.read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#"):
        continue
    if "=" not in raw:
        fail("invalid line")
    key, value = raw.split("=", 1)
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key) or key in env:
        fail("invalid/duplicate key")
    env[key] = value

settings_keys = {
    "APP_NAME", "APP_ENV", "LOG_LEVEL", "LOG_FORMAT",
    "TELEGRAM_RUNTIME_ENABLED", "TELEGRAM_BOT_TOKEN", "TELEGRAM_POLL_TIMEOUT",
    "TELEGRAM_DROP_PENDING_UPDATES", "ADMIN_IDS", "REPORT_TIMEZONE",
    "BROADCAST_RATE_PER_SECOND", "BROADCAST_BATCH_SIZE", "BROADCAST_MAX_RETRIES",
    "BROADCAST_RETRY_AFTER_CAP_SECONDS", "DATABASE_URL", "DB_ECHO",
    "DB_POOL_SIZE", "DB_MAX_OVERFLOW", "DB_POOL_TIMEOUT_SECONDS",
    "DB_CONNECT_TIMEOUT_SECONDS", "PAPER_RUNTIME_ENABLED",
    "PAPER_PRIVATE_TEST_CHANNEL_ID", "PAPER_DEFAULT_LEVERAGE",
    "PAPER_POLL_INTERVAL_SECONDS", "PERFORMANCE_INTELLIGENCE_SHADOW_MODE",
    "PERFORMANCE_REPORTS_ENABLED", "PERFORMANCE_REPORT_CHANNEL_ID",
    "PERFORMANCE_REPORT_PARSE_MODE", "PERFORMANCE_REPORT_TIMEZONE",
    "PERFORMANCE_REPORT_MAX_RETRY", "PERFORMANCE_REPORT_INTERVAL",
    "BROOKS_RUNTIME_ENABLED", "BROOKS_RUNTIME_MODE", "BROOKS_EXCHANGE",
    "BROOKS_MARKET_TYPE", "BROOKS_SYMBOLS", "BROOKS_TIMEFRAMES",
    "BROOKS_SNAPSHOT_LIMIT", "BROOKS_POLL_INTERVAL_SECONDS",
    "BROOKS_LIVE_LEVERAGE", "BROOKS_VIP_CHANNEL_ID", "BROOKS_LIVE_CUTOVER_AT",
    "BROOKS_HISTORICAL_PROBABILITY_DOMAIN", "BROOKS_SCALE_IN_MODE",
    "BROOKS_OPERATIONS_ENABLED", "BROOKS_OPS_CUTOVER_AT",
    "SIGNAL_LIFECYCLE_POLL_INTERVAL_SECONDS", "SIGNAL_LIFECYCLE_CANDLE_LIMIT",
    "PAYMENT_SETTLEMENT_POLL_INTERVAL_SECONDS",
    "VIP_ENTITLEMENT_POLL_INTERVAL_SECONDS", "VIP_INVITE_TTL_HOURS",
}
compose_keys = {"POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"}
if set(env) - settings_keys - compose_keys:
    fail("unsupported environment variable")

required = {
    "APP_ENV", "ADMIN_IDS", "TELEGRAM_RUNTIME_ENABLED", "TELEGRAM_BOT_TOKEN",
    "BROOKS_RUNTIME_ENABLED", "BROOKS_OPERATIONS_ENABLED", "PAPER_RUNTIME_ENABLED",
    "PERFORMANCE_REPORTS_ENABLED", "DB_ECHO", "POSTGRES_USER",
    "POSTGRES_PASSWORD", "POSTGRES_DB", "DATABASE_URL",
}
if required - set(env):
    fail("missing required environment variable")
if any("REPLACE_" in value for value in env.values()):
    fail("unresolved placeholder")
if env["TELEGRAM_BOT_TOKEN"] != "":
    fail("TELEGRAM_BOT_TOKEN must be empty")


def must(name: str) -> str:
    value = env.get(name, "")
    if not value:
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

for key in (
    "TELEGRAM_RUNTIME_ENABLED",
    "BROOKS_RUNTIME_ENABLED",
    "BROOKS_OPERATIONS_ENABLED",
    "PAPER_RUNTIME_ENABLED",
    "PERFORMANCE_REPORTS_ENABLED",
    "DB_ECHO",
):
    if env.get(key, "").lower() != "false":
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
