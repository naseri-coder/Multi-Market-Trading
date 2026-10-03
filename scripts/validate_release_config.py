#!/usr/bin/env python3
"""Validate v0.3.0 release configuration without exposing secret values."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_KEYS = {"POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"}
PLACEHOLDERS = {
    "REPLACE_WITH_NUMERIC_ADMIN_ID",
    "REPLACE_WITH_NEW_RANDOM_URLSAFE_PASSWORD",
}


def fail(message: str) -> None:
    raise SystemExit("RELEASE_CONFIG_FAIL: " + message + " (values suppressed)")


def parse_env(path: Path, *, allow_placeholders: bool = False) -> dict[str, str]:
    if not path.is_file() or path.is_symlink():
        fail("environment file missing/invalid")
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in raw:
            fail("invalid environment line")
        key, value = raw.split("=", 1)
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key) or key in values:
            fail("invalid/duplicate environment key")
        if not allow_placeholders and any(token in value for token in PLACEHOLDERS):
            fail("unresolved placeholder")
        values[key] = value
    return values


def validate_template(path: Path) -> None:
    values = parse_env(path, allow_placeholders=True)
    if values.get("ADMIN_IDS") != "REPLACE_WITH_NUMERIC_ADMIN_ID":
        fail("ADMIN_IDS template placeholder missing")
    if values.get("POSTGRES_PASSWORD") != "REPLACE_WITH_NEW_RANDOM_URLSAFE_PASSWORD":
        fail("POSTGRES_PASSWORD template placeholder missing")
    if values.get("DATABASE_URL", "").count("REPLACE_WITH_NEW_RANDOM_URLSAFE_PASSWORD") != 1:
        fail("DATABASE_URL password placeholder missing")
    if values.get("APP_ENV") != "production":
        fail("template APP_ENV must be production")
    for key in (
        "TELEGRAM_RUNTIME_ENABLED",
        "BROOKS_RUNTIME_ENABLED",
        "BROOKS_OPERATIONS_ENABLED",
        "PAPER_RUNTIME_ENABLED",
        "PERFORMANCE_REPORTS_ENABLED",
        "DB_ECHO",
    ):
        if values.get(key, "").lower() != "false":
            fail(f"template safe default required for {key}")
    print("RELEASE_CONFIG_TEMPLATE_PASS")


def settings_class():
    for source in (ROOT / "production_source", ROOT):
        if (source / "app").is_dir():
            sys.path.insert(0, str(source))
            break
    try:
        from app.core.config import Settings
    except Exception as exc:
        fail(f"application Settings unavailable: {type(exc).__name__}")
    return Settings


def collect_environment() -> dict[str, str]:
    Settings = settings_class()
    known = {name.upper() for name in Settings.model_fields} | COMPOSE_KEYS
    return {key: value for key, value in os.environ.items() if key in known}


def validate_env(values: dict[str, str], *, mode: str):
    Settings = settings_class()
    known = {name.upper() for name in Settings.model_fields} | COMPOSE_KEYS
    unknown = set(values) - known
    if unknown:
        fail("unsupported environment variable: " + ",".join(sorted(unknown)))
    missing_compose = COMPOSE_KEYS - set(values)
    if missing_compose:
        fail("missing Compose database variable")
    settings_values = {
        key.lower(): value
        for key, value in values.items()
        if key not in COMPOSE_KEYS
    }
    try:
        settings = Settings.model_validate(settings_values)
    except Exception as exc:
        errors = getattr(exc, "errors", None)
        if callable(errors):
            details = []
            for item in errors(include_input=False, include_url=False):
                loc = ".".join(str(part) for part in item.get("loc", ()))
                details.append(f"{loc}: {item.get('msg', 'invalid')}")
            fail("; ".join(details) if details else type(exc).__name__)
        fail(type(exc).__name__)

    parsed = urlsplit(settings.database_url.get_secret_value())
    password = values["POSTGRES_PASSWORD"]
    if not (
        parsed.scheme == "postgresql+asyncpg"
        and parsed.hostname == "postgres"
        and parsed.port == 5432
        and parsed.username == values["POSTGRES_USER"]
        and parsed.password == password
        and parsed.path == "/" + values["POSTGRES_DB"]
        and not parsed.query
        and not parsed.fragment
    ):
        fail("DATABASE_URL must match the Compose PostgreSQL service")

    if mode == "safe-install":
        if settings.telegram_runtime_enabled or settings.telegram_bot_token is not None:
            fail("safe-install requires Telegram disabled and token empty")
        if (
            settings.brooks_runtime_enabled
            or settings.brooks_operations_enabled
            or settings.paper_runtime_enabled
            or settings.performance_reports_enabled
            or settings.brooks_scale_in_mode != "disabled"
        ):
            fail("safe-install requires all effectful runtime modes disabled")
    elif mode == "paper":
        if not (
            settings.telegram_runtime_enabled
            and settings.brooks_runtime_enabled
            and settings.brooks_runtime_mode == "paper"
            and settings.paper_runtime_enabled
            and not settings.brooks_operations_enabled
        ):
            fail("paper mode contract is incomplete")
    elif mode == "live":
        if not (
            settings.telegram_runtime_enabled
            and settings.brooks_runtime_enabled
            and settings.brooks_runtime_mode == "live"
            and not settings.paper_runtime_enabled
            and settings.brooks_vip_channel_id
            and settings.brooks_live_cutover_at is not None
        ):
            fail("live signal mode contract is incomplete")
    else:
        fail("unsupported validation mode")

    if settings.brooks_runtime_enabled and (
        settings.brooks_exchange != "binance"
        or settings.brooks_market_type != "futures"
    ):
        fail("enabled Brooks runtime requires Binance USD-M Futures")
    return settings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--from-environment", action="store_true")
    parser.add_argument(
        "--mode",
        choices=("template", "safe-install", "paper", "live"),
        required=True,
    )
    args = parser.parse_args()

    if args.mode == "template":
        if args.from_environment or args.env_file is None:
            fail("template mode requires --env-file only")
        validate_template(args.env_file)
        return

    if args.from_environment == (args.env_file is not None):
        fail("choose exactly one of --env-file or --from-environment")
    values = collect_environment() if args.from_environment else parse_env(args.env_file)
    validate_env(values, mode=args.mode)
    print(f"RELEASE_CONFIG_PASS mode={args.mode}; values suppressed")


if __name__ == "__main__":
    main()
