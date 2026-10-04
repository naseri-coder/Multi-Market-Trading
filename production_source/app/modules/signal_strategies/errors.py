"""Signal-strategy configuration errors."""


class SignalStrategyError(Exception):
    """Base error for strategy configuration."""


class SignalStrategyNotFoundError(SignalStrategyError):
    """Requested strategy is not registered."""


class SignalStrategyChannelRequiredError(SignalStrategyError):
    """Strategy cannot be enabled before a delivery channel is configured."""


class SignalStrategyEngineNotReadyError(SignalStrategyError):
    """Strategy core is not connected yet."""


class InvalidSignalStrategyError(SignalStrategyError):
    """Strategy configuration input is invalid."""
