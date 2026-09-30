from app.modules.brooks_core.phase7_blockers import BLOCKERS

def test_all_known_engineering_hypotheses_are_explicitly_blocked() -> None:
    ids = {item.hypothesis_id for item in BLOCKERS}
    assert ids == {"EH-001", "EH-002", "EH-003", "EH-004", "EH-005", "EH-006", "EH-007"}
