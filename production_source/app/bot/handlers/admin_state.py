"""Conversation-local state keys shared by administrator input workflows."""

from telegram.ext import ContextTypes

CHANNEL_ACTION_KEY = "phase7_channel_admin_action"
BROADCAST_ACTION_KEY = "phase8_broadcast_admin_action"
FORWARD_BROADCAST_ACTION_KEY = "phase9_forward_broadcast_admin_action"
SUPPORT_ADMIN_ACTION_KEY = "phase10_support_admin_action"
SUPPORT_ADMIN_LIST_KEY = "phase10_support_admin_list"
SUBSCRIPTION_ADMIN_ACTION_KEY = "phase17_subscription_admin_action"
SIGNAL_ADMIN_ACTION_KEY = "phase20_signal_admin_action"
SIGNAL_ADMIN_LIST_KEY = "phase20_signal_admin_list"


def clear_admin_input_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cancel any pending free-form administrator input operation."""
    context.user_data.pop(CHANNEL_ACTION_KEY, None)
    context.user_data.pop(BROADCAST_ACTION_KEY, None)
    context.user_data.pop(FORWARD_BROADCAST_ACTION_KEY, None)
    context.user_data.pop(SUPPORT_ADMIN_ACTION_KEY, None)
    context.user_data.pop(SUBSCRIPTION_ADMIN_ACTION_KEY, None)
    context.user_data.pop(SIGNAL_ADMIN_ACTION_KEY, None)
