"""Telegram adapter dependency accessors."""

from __future__ import annotations

from telegram.ext import ContextTypes

from app.db.session import DatabaseManager


def get_database_manager(context: ContextTypes.DEFAULT_TYPE) -> DatabaseManager:
    """Return the initialized database manager or fail closed."""
    database = context.application.bot_data.get("database")
    if not isinstance(database, DatabaseManager):
        raise RuntimeError("DatabaseManager is not initialized")
    return database


def get_admin_ids(context: ContextTypes.DEFAULT_TYPE) -> frozenset[int]:
    """Return the validated immutable administrator allowlist."""
    admin_ids = context.application.bot_data.get("admin_ids")
    if not isinstance(admin_ids, frozenset) or not all(
        isinstance(admin_id, int) and not isinstance(admin_id, bool) for admin_id in admin_ids
    ):
        raise RuntimeError("Administrator allowlist is not initialized")
    return admin_ids


def get_report_timezone(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Return the validated timezone used for calendar-based reports."""
    timezone_name = context.application.bot_data.get("report_timezone")
    if not isinstance(timezone_name, str) or not timezone_name:
        raise RuntimeError("Report timezone is not initialized")
    return timezone_name
