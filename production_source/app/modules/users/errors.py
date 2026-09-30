"""User-domain and persistence errors."""


class UserError(Exception):
    """Base exception for expected user module failures."""


class InvalidUserIdentityError(UserError):
    """Raised when Telegram identity data violates domain limits."""


class UserRepositoryError(UserError):
    """Raised when user persistence cannot complete safely."""


class UserStatisticsRepositoryError(UserError):
    """Raised when user statistics cannot be loaded safely."""
