"""Conversation-local state for user and administrator support replies."""

from telegram.ext import ContextTypes

SUPPORT_USER_ACTION_KEY = "phase10_support_user_action"
SUPPORT_USER_LIST_PAGE_KEY = "phase10_support_user_list_page"


def clear_support_user_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(SUPPORT_USER_ACTION_KEY, None)
