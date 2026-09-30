"""Administrator ORM model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, UniqueConstraint, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import BigIntIdentityMixin, TimestampMixin

if TYPE_CHECKING:
    from app.modules.settings.models import BotSetting
    from app.modules.users.models import User


class Admin(BigIntIdentityMixin, TimestampMixin, Base):
    """Persistent administrator assignment for a registered user."""

    __tablename__ = "admins"
    __table_args__ = (UniqueConstraint("user_id", name="uq_admins_user_id"),)

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        server_default=true(),
    )

    user: Mapped[User] = relationship(back_populates="admin")
    updated_settings: Mapped[list[BotSetting]] = relationship(back_populates="updated_by")
