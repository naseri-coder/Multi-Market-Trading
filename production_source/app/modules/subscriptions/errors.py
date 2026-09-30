"""Domain and persistence errors for subscriptions."""


class SubscriptionError(Exception):
    """Base class for expected subscription failures."""


class InvalidSubscriptionError(SubscriptionError):
    """Raised when subscription input violates a business rule."""


class SubscriptionPlanNotFoundError(SubscriptionError):
    """Raised when a plan does not exist."""


class DuplicateSubscriptionPlanError(SubscriptionError):
    """Raised when a plan name is already used."""


class SubscriptionPlanInUseError(SubscriptionError):
    """Raised when historical subscriptions prevent plan deletion."""


class SubscriptionUserNotFoundError(SubscriptionError):
    """Raised when the target user does not exist."""


class ActiveSubscriptionExistsError(SubscriptionError):
    """Raised when a user already has a non-expired active subscription."""


class ActiveSubscriptionNotFoundError(SubscriptionError):
    """Raised when a user has no active subscription to expire."""


class SubscriptionRepositoryError(SubscriptionError):
    """Raised when subscription persistence fails unexpectedly."""
