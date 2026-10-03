"""Historical reference only; not current release proof or runtime source.
Original source: integration_phase1/tests/test_migration_static.py
Original SHA256: 6bfb9275dd5f121fbd0241e20dac4fd02fcdfcbd39c38236c7129d8a1276e40b
"""
from pathlib import Path
p=Path("migrations/versions/20260902_0012_create_brooks_signal_metadata.py")
text=p.read_text(encoding="utf-8")

assert 'down_revision: str | None = "20260902_0011"' in text
assert '"signal_automation_metadata"' in text
assert '"signal_rule_evidence"' in text
assert '"publication_scope"' in text
assert '"idempotency_key"' in text
assert '"market_snapshot_id"' in text
assert '"market_snapshot_hash"' in text
assert '"configuration_version"' in text
assert '"counts_toward_performance"' in text
assert "uq_signal_automation_metadata_producer_idempotency" in text
assert "ondelete=\"CASCADE\"" in text
print("MIGRATION_CHAIN_HEAD=PASS")
print("AUTOMATION_METADATA_SCHEMA=PASS")
print("RULE_EVIDENCE_SCHEMA=PASS")
print("IDEMPOTENCY_UNIQUE_CONSTRAINT=PASS")
print("CASCADE_LIFECYCLE=PASS")
