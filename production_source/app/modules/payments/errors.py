"""Expected payment domain and persistence failures."""


class PaymentError(Exception):
    """Base class for expected payment failures."""


class InvalidPaymentError(PaymentError):
    """Raised when payment input violates a business rule."""


class PaymentNotFoundError(PaymentError):
    """Raised when a payment does not exist."""


class PaymentUserNotFoundError(PaymentError):
    """Raised when a payment user does not exist."""


class PaymentPlanNotFoundError(PaymentError):
    """Raised when a payment plan does not exist."""


class PaymentStateError(PaymentError):
    """Raised when an invalid payment-state transition is requested."""


class DuplicatePaymentReferenceError(PaymentError):
    """Raised when an internal or provider reference is already used."""


class PaymentRepositoryError(PaymentError):
    """Raised when payment persistence fails unexpectedly."""
