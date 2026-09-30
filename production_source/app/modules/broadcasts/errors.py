"""Expected broadcast domain, persistence, and Telegram delivery failures."""


class BroadcastError(Exception):
    """Base class for expected broadcast failures."""


class InvalidBroadcastError(BroadcastError):
    """Raised when broadcast content violates Phase 8 rules."""


class BroadcastNotFoundError(BroadcastError):
    """Raised when a requested broadcast does not exist."""


class BroadcastStateError(BroadcastError):
    """Raised when a broadcast transition is no longer permitted."""


class BroadcastRepositoryError(BroadcastError):
    """Raised when broadcast persistence cannot complete safely."""


class BroadcastDeliveryError(BroadcastError):
    """Expected non-retryable Telegram delivery failure."""

    def __init__(self, error_code: str = "TELEGRAM_ERROR") -> None:
        super().__init__(error_code)
        self.error_code = error_code


class BroadcastBlockedError(BroadcastDeliveryError):
    """Recipient blocked the bot or otherwise permanently forbids delivery."""

    def __init__(self) -> None:
        super().__init__("BOT_BLOCKED")


class BroadcastRetryAfterError(BroadcastDeliveryError):
    """Telegram requested a bounded retry delay."""

    def __init__(self, retry_after_seconds: float) -> None:
        super().__init__("RATE_LIMITED")
        self.retry_after_seconds = retry_after_seconds
