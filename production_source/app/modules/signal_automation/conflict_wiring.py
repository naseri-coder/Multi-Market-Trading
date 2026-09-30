
from app.modules.signal_automation.conflict_guard import check_signal_conflict

def allow_new_signal(existing_direction: str | None, new_direction: str) -> bool:
    result = check_signal_conflict(existing_direction, new_direction)
    return result.allowed
