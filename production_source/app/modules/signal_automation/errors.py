"""Expected failures for Brooks signal persistence integration."""


class SignalAutomationError(Exception):
    """Base automation integration error."""


class DuplicateAutomatedSignalError(SignalAutomationError):
    """Raised when the database uniqueness guard detects an idempotent duplicate."""


class SignalAutomationRepositoryError(SignalAutomationError):
    """Raised when automation persistence fails without exposing database details."""


class SignalAutomationConsistencyError(SignalAutomationError):
    """Raised when an idempotency conflict cannot be resolved to an existing signal."""
