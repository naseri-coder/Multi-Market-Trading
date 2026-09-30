"""Database infrastructure exceptions."""

from app.core.errors import ApplicationError


class DatabaseUnavailableError(ApplicationError):
    """Raised when PostgreSQL cannot complete a health check."""

    code = "database_unavailable"
