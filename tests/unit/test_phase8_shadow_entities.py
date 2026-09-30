from datetime import UTC, datetime
from decimal import Decimal

from app.modules.brooks_core.engine_contract import BrooksEngineResult
from app.modules.shadow_replay.entities import (
    ShadowObservation,
    ShadowReplayMetrics,
    classify_engine_result,
)
from app.modules.signal_automation.entities import BrooksRuleEvidence


def result(*, setup_type=None, reasoning=(), evidence=()):
    return BrooksEngineResult(
        decision="NO_SIGNAL",
        entry_price=None,
        stop_loss=None,
        targets=(),
        setup_type=setup_type,
        reasoning=reasoning,
        rule_ids=(),
        failed_rules=(),
        rule_evidence=evidence,
        engine_version="e",
        rule_set_version="r",
        configuration_version="c",
    )


def test_classification_prefers_source_setup_detection():
    assert classify_engine_result(result(setup_type="H2_CONFIRMED")) == "H2"
    assert classify_engine_result(result(setup_type="L2_CONFIRMED")) == "L2"


def test_classification_uses_structured_ambiguity_then_fail_closed_blocker():
    ambiguous = BrooksRuleEvidence(
        rule_id="BR-031",
        status="AMBIGUOUS",
        source_pages=(127,),
    )
    assert classify_engine_result(result(evidence=(ambiguous,))) == "AMBIGUOUS"
    assert classify_engine_result(
        result(reasoning=("Second-entry assessment: EH-006 unresolved edge case; fail-closed",))
    ) == "BLOCKED"
    assert classify_engine_result(result(reasoning=("nothing",))) == "NO_SIGNAL"


def test_metrics_are_derived_without_performance_persistence():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    classes = ("H2", "L2", "AMBIGUOUS", "BLOCKED", "NO_SIGNAL")
    observations = tuple(
        ShadowObservation(
            sequence=i + 1,
            snapshot_id=f"id-{i}",
            snapshot_hash=f"hash-{i}",
            captured_at=now,
            window_first_open=now,
            window_last_close=now,
            classification=value,
            decision="NO_SIGNAL",
            setup_type=None,
            reasoning=(),
            rule_ids=(),
            failed_rules=(),
            engine_version="e",
            rule_set_version="r",
            configuration_version="c",
        )
        for i, value in enumerate(classes)
    )
    metrics = ShadowReplayMetrics.from_observations(observations)
    assert metrics.evaluated_snapshots == 5
    assert metrics.h2_count == 1
    assert metrics.l2_count == 1
    assert metrics.ambiguous_count == 1
    assert metrics.blocked_count == 1
    assert metrics.no_signal_count == 1
    assert metrics.detections_per_1000_snapshots == 400.0
