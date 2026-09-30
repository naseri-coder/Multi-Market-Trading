from pathlib import Path

text = Path(
    "migrations/versions/20260902_0013_create_signal_delivery_tracking.py"
).read_text(encoding="utf-8")

assert 'revision: str = "20260902_0013"' in text
assert 'down_revision: str | None = "20260902_0012"' in text
assert '"signal_deliveries"' in text
assert "uq_signal_deliveries_signal_destination" in text
assert "'AMBIGUOUS'" in text
assert 'ondelete="CASCADE"' in text
