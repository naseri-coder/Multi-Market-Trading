"""Domain-safe signal failures exposed to future adapters."""


class SignalError(Exception):
    """Base exception for expected signal failures."""


class InvalidSignalError(SignalError):
    """Raised when signal input violates a business rule."""


class SignalNotFoundError(SignalError):
    """Raised when a requested signal does not exist."""


class SignalTargetNotFoundError(SignalError):
    """Raised when a requested target does not exist on a signal."""


class SignalStateError(SignalError):
    """Raised when an operation is invalid for the current lifecycle state."""


class SignalRepositoryError(SignalError):
    """Raised when persistence fails without exposing database details."""
