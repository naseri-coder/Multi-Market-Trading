"""Expected favorites failures safe for adapter-level handling."""


class FavoriteError(Exception):
    """Base exception for expected favorites failures."""


class InvalidFavoriteError(FavoriteError):
    """Raised when favorite identifiers or pagination are invalid."""


class FavoriteSignalNotFoundError(FavoriteError):
    """Raised when a signal is missing or not publicly visible."""


class FavoriteRepositoryError(FavoriteError):
    """Raised when favorite persistence cannot complete safely."""
