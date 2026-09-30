"""Expected referral failures safe for adapter-level handling."""


class ReferralError(Exception):
    """Base exception for expected referral failures."""


class InvalidReferralError(ReferralError):
    """Raised when a referral code or identifier is invalid."""


class ReferralUserNotFoundError(ReferralError):
    """Raised when a user required by a referral operation is missing."""


class ReferralCodeNotFoundError(ReferralError):
    """Raised when a submitted referral code does not exist."""


class SelfReferralError(ReferralError):
    """Raised when a user attempts to refer themselves."""


class ReferralCodeGenerationError(ReferralError):
    """Raised after bounded referral-code collision retries are exhausted."""


class ReferralRepositoryError(ReferralError):
    """Raised when referral persistence cannot complete safely."""
