"""Reusable Telegram authorization guards."""

from app.bot.middlewares.admin import admin_required

__all__ = ["admin_required"]
