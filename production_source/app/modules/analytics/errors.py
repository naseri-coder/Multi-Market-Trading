"""Expected analytics failures safe for adapter-level handling."""


class AnalyticsError(Exception):
    """Base exception for expected analytics failures."""


class InvalidWinRatePeriodError(AnalyticsError):
    """Raised when a report period is not allow-listed."""


class WinRateRepositoryError(AnalyticsError):
    """Raised when outcome aggregation cannot be loaded safely."""
