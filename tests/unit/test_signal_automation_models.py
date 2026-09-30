from app.db.base import Base
from app.modules.signal_automation.models import SignalAutomationMetadata, SignalRuleEvidence
from app.modules.signals.models import Signal, SignalPublicationScope


def test_models_match_applied_0012_tables() -> None:
    assert Signal.__table__.c.publication_scope.name == "publication_scope"
    assert SignalAutomationMetadata.__tablename__ == "signal_automation_metadata"
    assert SignalRuleEvidence.__tablename__ == "signal_rule_evidence"
    assert SignalPublicationScope.PRIVATE_TEST.value == "PRIVATE_TEST"


def test_automation_models_are_registered_in_metadata() -> None:
    assert "signal_automation_metadata" in Base.metadata.tables
    assert "signal_rule_evidence" in Base.metadata.tables
