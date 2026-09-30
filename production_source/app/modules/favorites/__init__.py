"""Public favorites module surface."""

from app.modules.favorites.entities import FavoriteMutation, FavoritePage
from app.modules.favorites.errors import (
    FavoriteError,
    FavoriteRepositoryError,
    FavoriteSignalNotFoundError,
    InvalidFavoriteError,
)
from app.modules.favorites.models import UserFavorite
from app.modules.favorites.repository import (
    FavoriteRepository,
    SQLAlchemyFavoriteRepository,
)
from app.modules.favorites.service import FavoriteService

__all__ = [
    "FavoriteError",
    "FavoriteMutation",
    "FavoritePage",
    "FavoriteRepository",
    "FavoriteRepositoryError",
    "FavoriteService",
    "FavoriteSignalNotFoundError",
    "InvalidFavoriteError",
    "SQLAlchemyFavoriteRepository",
    "UserFavorite",
]
