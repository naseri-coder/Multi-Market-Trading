
from dataclasses import dataclass

@dataclass
class LifecycleDecision:
    allowed: bool
    reason: str

def check_direction_conflict(existing_direction, incoming_direction):
    if not existing_direction:
        return LifecycleDecision(True, "NO_ACTIVE_SIGNAL")
    if existing_direction == incoming_direction:
        return LifecycleDecision(False, "DUPLICATE_ACTIVE_SIGNAL")
    return LifecycleDecision(False, "ACTIVE_OPPOSITE_SIGNAL_EXISTS")
