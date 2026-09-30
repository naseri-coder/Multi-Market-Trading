"""Application-level exception hierarchy."""

from __future__ import annotations


class ApplicationError(Exception):
    """Base class for expected application failures."""

    code = "application_error"


class ConfigurationError(ApplicationError):
    """Raised when environment configuration cannot be validated safely."""

    code = "configuration_error"

    def __init__(self, message: str, *, details: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.details = details


class StartupError(ApplicationError):
    """Raised when external runtime startup fails."""

    code = "startup_error"
