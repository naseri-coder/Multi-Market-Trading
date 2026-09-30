"""Expected support ticket domain and persistence failures."""


class SupportError(Exception):
    """Base class for expected support failures."""


class InvalidSupportMessageError(SupportError):
    """Raised when message text or identifiers are invalid."""


class SupportTicketNotFoundError(SupportError):
    """Raised when a ticket is missing or not owned by the requester."""


class SupportTicketStateError(SupportError):
    """Raised when a ticket state disallows the requested operation."""


class SupportRepositoryError(SupportError):
    """Raised when support persistence cannot complete safely."""
