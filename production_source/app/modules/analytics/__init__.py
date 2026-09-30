"""Public analytics module surface."""

from app.modules.analytics.entities import (
    TradeExitReason,
    TradePerformanceRecord,
    WinRateOutcomeCounts,
    WinRatePeriod,
    WinRateReport,
)
from app.modules.analytics.errors import (
    AnalyticsError,
    InvalidWinRatePeriodError,
    WinRateRepositoryError,
)
from app.modules.analytics.repository import (
    SQLAlchemyWinRateRepository,
    WinRateRepository,
)
from app.modules.analytics.service import WinRateService

__all__ = [
    "AnalyticsError",
    "InvalidWinRatePeriodError",
    "SQLAlchemyWinRateRepository",
    "TradeExitReason",
    "TradePerformanceRecord",
    "WinRateOutcomeCounts",
    "WinRatePeriod",
    "WinRateReport",
    "WinRateRepository",
    "WinRateRepositoryError",
    "WinRateService",
]
