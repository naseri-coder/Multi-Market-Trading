"""Typed environment configuration."""

from __future__ import annotations

import re
from datetime import datetime
from functools import lru_cache
from typing import Annotated, Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.core.errors import ConfigurationError

Environment = Literal["development", "test", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
LogFormat = Literal["json", "console"]
AdminIds = Annotated[frozenset[int], NoDecode]
BrooksSymbols = Annotated[tuple[str, ...], NoDecode]
BrooksTimeframes = Annotated[tuple[str, ...], NoDecode]
BrooksHistoricalProbabilityDomain = Literal["LEGACY_MIXED", "FUTURES_ONLY"]
BrooksScaleInMode = Literal["disabled", "shadow", "live"]

_TELEGRAM_TOKEN_PATTERN = re.compile(r"^\d{6,12}:[A-Za-z0-9_-]{30,}$")


class Settings(BaseSettings):
    """Application settings loaded from environment variables or ``.env``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        validate_default=True,
    )

    app_name: str = Field(default="crypto-signal-telegram-bot", min_length=1, max_length=100)
    app_env: Environment = "development"
    log_level: LogLevel = "INFO"
    log_format: LogFormat = "json"

    telegram_runtime_enabled: bool = True
    telegram_bot_token: SecretStr | None = None
    telegram_poll_timeout: int = Field(default=10, ge=1, le=60)
    telegram_drop_pending_updates: bool = False
    admin_ids: AdminIds = Field(default_factory=frozenset)
    report_timezone: str = "Asia/Tehran"
    broadcast_rate_per_second: float = Field(default=20.0, ge=1.0, le=30.0)
    broadcast_batch_size: int = Field(default=250, ge=1, le=1000)
    broadcast_max_retries: int = Field(default=2, ge=0, le=5)
    broadcast_retry_after_cap_seconds: int = Field(default=60, ge=1, le=300)

    database_url: SecretStr
    db_echo: bool = False
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_max_overflow: int = Field(default=10, ge=0, le=100)
    db_pool_timeout_seconds: int = Field(default=30, ge=1, le=120)
    db_connect_timeout_seconds: int = Field(default=10, ge=1, le=60)

    # PAPER runtime is fail-closed and disabled by default.
    paper_runtime_enabled: bool = False
    paper_private_test_channel_id: int | None = None
    paper_default_leverage: float = Field(default=1.0, gt=0, le=125)
    paper_poll_interval_seconds: int = Field(default=60, ge=15, le=3600)

    # Brooks Full Core v3 runtime. PAPER and LIVE VIP are mutually exclusive.
    # Performance Intelligence shadow analytics. Read-only, disabled by default.
    performance_intelligence_shadow_mode: bool = False
    # Performance Intelligence Telegram reporting. Reporting is fail-closed by default.
    performance_reports_enabled: bool = False
    performance_report_channel_id: int | None = None
    performance_report_parse_mode: Literal["HTML"] = "HTML"
    performance_report_timezone: str = "UTC"
    performance_report_max_retry: int = Field(default=3, ge=0, le=5)
    performance_report_interval: int = Field(default=3600, ge=60)

    brooks_runtime_enabled: bool = False
    brooks_runtime_mode: Literal["paper", "live"] = "paper"
    brooks_exchange: Literal["binance", "bybit"] = "binance"
    brooks_market_type: Literal["spot", "futures", "linear", "inverse"] = "futures"
    brooks_symbols: BrooksSymbols = Field(
        default_factory=lambda: ("BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "SOLUSDT")
    )
    brooks_timeframes: BrooksTimeframes = Field(default_factory=tuple)
    brooks_snapshot_limit: int = Field(default=120, ge=40, le=999)
    brooks_poll_interval_seconds: int = Field(default=60, ge=15, le=3600)
    brooks_live_leverage: float = Field(default=1.0, gt=0, le=125)
    brooks_vip_channel_id: int | None = None
    brooks_live_cutover_at: datetime | None = None
    brooks_historical_probability_domain: BrooksHistoricalProbabilityDomain = "LEGACY_MIXED"
    # Multi-lot Scale-In architecture is fail-closed. LIVE remains unavailable until
    # an authenticated exchange execution/reconciliation connector exists.
    brooks_scale_in_mode: BrooksScaleInMode = "disabled"

    # Production operations: lifecycle, payment settlement, VIP entitlements, health.
    brooks_operations_enabled: bool = False
    brooks_ops_cutover_at: datetime | None = None
    signal_lifecycle_poll_interval_seconds: int = Field(default=30, ge=15, le=3600)
    signal_lifecycle_candle_limit: int = Field(default=240, ge=30, le=999)
    payment_settlement_poll_interval_seconds: int = Field(default=60, ge=15, le=3600)
    vip_entitlement_poll_interval_seconds: int = Field(default=300, ge=30, le=3600)
    vip_invite_ttl_hours: int = Field(default=24, ge=1, le=168)

    @field_validator("app_name", mode="before")
    @classmethod
    def normalize_app_name(cls, value: object) -> object:
        """Trim textual application names before constraints are evaluated."""
        return value.strip() if isinstance(value, str) else value

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: object) -> object:
        """Allow conventional lowercase log levels in environment files."""
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("performance_report_parse_mode", mode="before")
    @classmethod
    def normalize_performance_report_parse_mode(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("brooks_historical_probability_domain", mode="before")
    @classmethod
    def normalize_brooks_historical_probability_domain(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("performance_report_channel_id", mode="before")
    @classmethod
    def parse_optional_performance_report_channel_id(cls, value: object) -> object:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return value

    @field_validator(
        "log_format",
        "app_env",
        "brooks_exchange",
        "brooks_market_type",
        "brooks_runtime_mode",
        "brooks_scale_in_mode",
        mode="before",
    )
    @classmethod
    def normalize_lowercase_values(cls, value: object) -> object:
        """Normalize case-insensitive enum-like settings."""
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("telegram_bot_token", mode="before")
    @classmethod
    def validate_telegram_bot_token(cls, value: object) -> SecretStr | None:
        """Validate a provided Telegram token; offline mode may omit it."""
        raw_token = value.get_secret_value() if isinstance(value, SecretStr) else value
        token = raw_token.strip() if isinstance(raw_token, str) else ""

        if not token:
            return None
        if not _TELEGRAM_TOKEN_PATTERN.fullmatch(token):
            raise ValueError("must match the Telegram bot token format")

        return SecretStr(token)

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, value: object) -> frozenset[int]:
        """Parse a comma-separated allowlist of positive Telegram user ids."""
        if value is None or value == "":
            return frozenset()

        raw_values: object
        if isinstance(value, str):
            parts = [part.strip() for part in value.split(",")]
            if any(not part for part in parts):
                raise ValueError("must be a comma-separated list without empty entries")
            raw_values = parts
        else:
            raw_values = value

        if not isinstance(raw_values, (list, tuple, set, frozenset)):
            raise ValueError("must be a comma-separated list of Telegram user ids")

        admin_ids: set[int] = set()
        for raw_admin_id in raw_values:
            if isinstance(raw_admin_id, bool):
                raise ValueError("must contain only positive integer Telegram user ids")
            try:
                admin_id = int(raw_admin_id)
            except (TypeError, ValueError) as exc:
                raise ValueError("must contain only positive integer Telegram user ids") from exc
            if admin_id <= 0 or admin_id > 2**63 - 1:
                raise ValueError("must contain valid positive bigint Telegram user ids")
            admin_ids.add(admin_id)

        return frozenset(admin_ids)

    @field_validator("brooks_symbols", mode="before")
    @classmethod
    def parse_brooks_symbols(cls, value: object) -> tuple[str, ...]:
        """Parse comma-separated uppercase market symbols without guessing a universe."""
        if value is None or value == "":
            return ()
        if isinstance(value, str):
            parts = tuple(part.strip().upper() for part in value.split(",") if part.strip())
        elif isinstance(value, (list, tuple, set, frozenset)):
            parts = tuple(str(part).strip().upper() for part in value if str(part).strip())
        else:
            raise ValueError("must be a comma-separated list of symbols")
        if not parts:
            return ()
        if len(parts) != len(set(parts)):
            raise ValueError("must not contain duplicate symbols")
        if any(not re.fullmatch(r"[A-Z0-9]{4,30}", part) for part in parts):
            raise ValueError("contains an invalid market symbol")
        return parts

    @field_validator("brooks_timeframes", mode="before")
    @classmethod
    def parse_brooks_timeframes(cls, value: object) -> tuple[str, ...]:
        """Parse comma-separated canonical timeframes supported by market_data."""
        if value is None or value == "":
            return ()
        if isinstance(value, str):
            parts = tuple(part.strip().lower() for part in value.split(",") if part.strip())
        elif isinstance(value, (list, tuple, set, frozenset)):
            parts = tuple(str(part).strip().lower() for part in value if str(part).strip())
        else:
            raise ValueError("must be a comma-separated list of timeframes")
        allowed = {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w"}
        if not parts:
            return ()
        if len(parts) != len(set(parts)):
            raise ValueError("must not contain duplicate timeframes")
        if any(part not in allowed for part in parts):
            raise ValueError("contains an unsupported canonical timeframe")
        return parts

    @field_validator("report_timezone", "performance_report_timezone", mode="before")
    @classmethod
    def validate_report_timezone(cls, value: object) -> str:
        """Require an available IANA timezone for calendar-based reports."""
        timezone_name = value.strip() if isinstance(value, str) else ""
        if not timezone_name:
            raise ValueError("must be a non-empty IANA timezone name")
        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("must be a valid IANA timezone name") from exc
        return timezone_name

    @field_validator("database_url", mode="before")
    @classmethod
    def validate_database_url(cls, value: object) -> SecretStr:
        """Require an asyncpg PostgreSQL URL without exposing its credentials."""
        raw_url = value.get_secret_value() if isinstance(value, SecretStr) else value
        database_url = raw_url.strip() if isinstance(raw_url, str) else ""
        parsed = urlsplit(database_url)

        if parsed.scheme != "postgresql+asyncpg":
            raise ValueError("must use the postgresql+asyncpg scheme")
        if not parsed.username or not parsed.hostname or parsed.path in {"", "/"}:
            raise ValueError("must include username, hostname, and database name")

        return SecretStr(database_url)

    @model_validator(mode="after")
    def prevent_sql_echo_in_production(self) -> Settings:
        """Enforce security-critical production configuration."""
        if self.telegram_runtime_enabled and self.telegram_bot_token is None:
            raise ValueError(
                "TELEGRAM_BOT_TOKEN is required when TELEGRAM_RUNTIME_ENABLED=true"
            )
        if not self.telegram_runtime_enabled:
            incompatible: list[str] = []
            if self.performance_reports_enabled:
                incompatible.append("PERFORMANCE_REPORTS_ENABLED")
            if self.brooks_runtime_enabled:
                incompatible.append("BROOKS_RUNTIME_ENABLED")
            if self.brooks_operations_enabled:
                incompatible.append("BROOKS_OPERATIONS_ENABLED")
            if incompatible:
                raise ValueError(
                    "TELEGRAM_RUNTIME_ENABLED=false is incompatible with: "
                    + ", ".join(incompatible)
                )
        if self.app_env == "production" and self.db_echo:
            raise ValueError("DB_ECHO must be disabled in production")
        if self.app_env == "production" and not self.admin_ids:
            raise ValueError("ADMIN_IDS must contain at least one administrator in production")
        if self.paper_runtime_enabled:
            if self.paper_private_test_channel_id is None:
                raise ValueError(
                    "PAPER_PRIVATE_TEST_CHANNEL_ID is required when PAPER_RUNTIME_ENABLED=true"
                )
            if self.paper_private_test_channel_id == 0:
                raise ValueError("PAPER_PRIVATE_TEST_CHANNEL_ID must be non-zero")
        if self.brooks_runtime_enabled:
            if not self.brooks_symbols:
                raise ValueError(
                    "BROOKS_SYMBOLS is required when BROOKS_RUNTIME_ENABLED=true"
                )
            if not self.brooks_timeframes:
                raise ValueError(
                    "BROOKS_TIMEFRAMES is required when BROOKS_RUNTIME_ENABLED=true"
                )
            if self.brooks_exchange != "binance" or self.brooks_market_type != "futures":
                raise ValueError(
                    "Enabled Brooks runtime requires BROOKS_EXCHANGE=binance "
                    "and BROOKS_MARKET_TYPE=futures"
                )

            if self.brooks_runtime_mode == "paper":
                if not self.paper_runtime_enabled:
                    raise ValueError(
                        "Brooks PAPER mode requires PAPER_RUNTIME_ENABLED=true"
                    )
            else:
                if self.paper_runtime_enabled:
                    raise ValueError(
                        "Brooks LIVE mode requires PAPER_RUNTIME_ENABLED=false"
                    )
                if self.brooks_vip_channel_id is None or self.brooks_vip_channel_id == 0:
                    raise ValueError(
                        "BROOKS_VIP_CHANNEL_ID is required in Brooks LIVE mode"
                    )
                if self.brooks_live_cutover_at is None:
                    raise ValueError(
                        "BROOKS_LIVE_CUTOVER_AT is required in Brooks LIVE mode"
                    )
                if self.brooks_live_cutover_at.tzinfo is None:
                    raise ValueError(
                        "BROOKS_LIVE_CUTOVER_AT must include timezone information"
                    )
        if self.brooks_scale_in_mode == "live":
            raise ValueError(
                "BROOKS_SCALE_IN_MODE=live is unavailable: no exchange "
                "execution/reconciliation connector is installed"
            )
        if self.brooks_scale_in_mode == "shadow" and not self.brooks_runtime_enabled:
            raise ValueError("BROOKS_SCALE_IN_MODE=shadow requires BROOKS_RUNTIME_ENABLED=true")
        if self.brooks_operations_enabled:
            if not self.brooks_runtime_enabled or self.brooks_runtime_mode != "live":
                raise ValueError(
                    "BROOKS_OPERATIONS_ENABLED=true requires Brooks LIVE runtime"
                )
            if self.paper_runtime_enabled:
                raise ValueError(
                    "BROOKS_OPERATIONS_ENABLED=true requires PAPER_RUNTIME_ENABLED=false"
                )
            if self.brooks_vip_channel_id is None or self.brooks_vip_channel_id == 0:
                raise ValueError(
                    "BROOKS_VIP_CHANNEL_ID is required for production operations"
                )
            if self.brooks_ops_cutover_at is None:
                raise ValueError(
                    "BROOKS_OPS_CUTOVER_AT is required when production operations are enabled"
                )
            if self.brooks_ops_cutover_at.tzinfo is None:
                raise ValueError(
                    "BROOKS_OPS_CUTOVER_AT must include timezone information"
                )
        return self


def _safe_validation_details(exc: ValidationError) -> tuple[str, ...]:
    """Return useful validation messages without including secret input values."""
    details: list[str] = []
    for error in exc.errors(include_input=False, include_url=False):
        location = ".".join(str(part) for part in error["loc"])
        details.append(f"{location}: {error['msg']}")
    return tuple(details)


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    """Load and cache validated settings for the process lifetime."""
    try:
        return Settings()
    except ValidationError as exc:
        raise ConfigurationError(
            "Invalid application configuration",
            details=_safe_validation_details(exc),
        ) from exc


def clear_settings_cache() -> None:
    """Clear cached settings for tests and controlled reloads."""
    load_settings.cache_clear()
