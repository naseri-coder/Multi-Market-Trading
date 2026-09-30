"""Expected channel-domain and integration errors."""


class ChannelError(Exception):
    """Base exception for expected channel failures."""


class InvalidChannelError(ChannelError):
    """Raised when channel metadata violates domain rules."""


class ChannelNotFoundError(ChannelError):
    """Raised when a requested channel does not exist."""


class DuplicateChannelError(ChannelError):
    """Raised when a Telegram channel is already configured."""


class ChannelRepositoryError(ChannelError):
    """Raised when channel persistence cannot complete safely."""


class TelegramChannelGatewayError(ChannelError):
    """Raised when Telegram cannot resolve or verify a channel."""


class ChannelMembershipCheckError(ChannelError):
    """Raised when membership cannot be verified for every active channel."""


class ChannelConfigurationError(ChannelError):
    """Raised when an active channel has no usable join URL."""
