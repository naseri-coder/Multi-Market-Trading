from __future__ import annotations

import asyncio
from dataclasses import replace
from decimal import Decimal
from hashlib import sha256
from types import SimpleNamespace

import pytest

from app.modules.signal_automation.entities import (
    BrooksSignalImport,
    FINAL_BROOKS_HP_SEMANTIC_COHORT_ID,
    HP_COLD_START_BOOTSTRAP_POLICY_ID,
    hp_cold_start_shadow_idempotency_key,
    hp_cold_start_shadow_source_signal_id,
)
from app.modules.signal_automation.models import SignalAutomationMetadata
from app.modules.signal_intelligence import probability as probability_module
from app.modules.signal_intelligence.probability import (
    HistoricalCase,
    HistoricalProbabilityEngine,
    _deduplicate_hp_economic_opportunities,
    _is_authorized_bootstrap_shadow,
    _stored_live_economic_opportunity_id,
)

FINAL = FINAL_BROOKS_HP_SEMANTIC_COHORT_ID
POLICY = HP_COLD_START_BOOTSTRAP_POLICY_ID


def _provenance(*, original: str, econ: str, source_id: str) -> dict[str, object]:
    return {
        "bootstrap": True,
        "policy_id": POLICY,
        "generation_mode": "SHADOW",
        "semantic_cohort_id": FINAL,
        "original_source_signal_id": original,
        "mode_scoped_source_signal_id": source_id,
        "economic_opportunity_id": econ,
        "state": "BOOTSTRAP_ENTRY_PENDING",
        "hp_eligible": False,
    }


def _shadow_command(
    *,
    econ: str = "opp-1",
    original: str = "core-1",
    snapshot_hash: str = "snap-hash-1",
    symbol: str = "BTCUSDT",
    timeframe: str = "15m",
    direction: str = "LONG",
) -> BrooksSignalImport:
    source_id = hp_cold_start_shadow_source_signal_id(
        original,
        FINAL,
        economic_opportunity_id=econ,
        symbol=symbol,
        timeframe=timeframe,
        direction=direction,
    )
    return BrooksSignalImport(
        source_signal_id=source_id,
        symbol=symbol,
        direction=direction,
        entry_price=Decimal("100"),
        stop_loss=Decimal("95") if direction == "LONG" else Decimal("105"),
        targets=(Decimal("110"),) if direction == "LONG" else (Decimal("90"),),
        leverage=Decimal("1"),
        exchange="binance",
        market_type="futures",
        timeframe=timeframe,
        setup_type="H2_CONFIRMED",
        market_snapshot_id=f"snapshot-{snapshot_hash}",
        market_snapshot_hash=snapshot_hash,
        engine_version="engine-final",
        rule_set_version="rules-final",
        configuration_version="cfg-final",
        reasoning=(),
        rule_ids=(),
        failed_rules=(),
        rule_evidence=(),
        generation_mode="SHADOW",
        publication_scope="INTERNAL",
        counts_toward_performance=False,
        semantic_cohort_id=FINAL,
        bootstrap_provenance=_provenance(
            original=original, econ=econ, source_id=source_id
        ),
    )


def _case(
    signal_id: int,
    *,
    econ: str | None,
    mode: str = "SHADOW",
    cohort: str | None = FINAL,
    policy: str | None = POLICY,
    outcome: int = 1,
    setup: str = "H2_CONFIRMED",
) -> HistoricalCase:
    return HistoricalCase(
        signal_id=signal_id,
        setup_type=setup,
        timeframe="15m",
        direction="LONG",
        structure_quality=80.0,
        context_quality=80.0,
        entry_quality=80.0,
        risk_feature=50.0,
        outcome=outcome,
        rule_ids=(),
        semantic_cohort_id=cohort,
        generation_mode=mode,
        bootstrap_policy_id=policy,
        economic_opportunity_id=econ,
    )


def _candidate() -> SimpleNamespace:
    return SimpleNamespace(
        setup_type="H2_CONFIRMED",
        timeframe="15m",
        direction="LONG",
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"),
        targets=(Decimal("110"),),
        rule_evidence=(),
        semantic_cohort_id=FINAL,
    )


def test_same_opportunity_is_stable_across_snapshot_and_original_source_churn() -> None:
    first = _shadow_command(econ="opp-stable", original="core-a", snapshot_hash="hash-a")
    second = _shadow_command(econ="opp-stable", original="core-b", snapshot_hash="hash-b")
    assert first.source_signal_id == second.source_signal_id
    assert first.idempotency_key == second.idempotency_key
    assert first.bootstrap_provenance["original_source_signal_id"] == "core-a"
    assert second.bootstrap_provenance["original_source_signal_id"] == "core-b"
    assert "hash-a" not in first.source_signal_id
    assert "core-a" not in first.source_signal_id


def test_distinct_economic_opportunity_is_not_suppressed() -> None:
    first = _shadow_command(econ="opp-a")
    second = _shadow_command(econ="opp-b")
    assert first.source_signal_id != second.source_signal_id
    assert first.idempotency_key != second.idempotency_key


def test_source_and_idempotency_use_same_namespace_but_independent_barriers() -> None:
    command = _shadow_command(econ="opp-namespace")
    expected_source = hp_cold_start_shadow_source_signal_id(
        "ignored-provenance",
        FINAL,
        economic_opportunity_id="opp-namespace",
        symbol="BTCUSDT",
        timeframe="15m",
        direction="LONG",
    )
    expected_idempotency = hp_cold_start_shadow_idempotency_key(
        semantic_cohort_id=FINAL,
        economic_opportunity_id="opp-namespace",
        symbol="BTCUSDT",
        timeframe="15m",
        direction="LONG",
    )
    assert command.source_signal_id == expected_source
    assert command.idempotency_key == expected_idempotency
    assert command.source_signal_id != command.idempotency_key


def test_live_idempotency_algorithm_is_unchanged() -> None:
    live = replace(
        _shadow_command(),
        source_signal_id="core-live",
        generation_mode="LIVE",
        publication_scope="VIP",
        counts_toward_performance=True,
        bootstrap_provenance=None,
    )
    canonical = "|".join(
        [
            "BROOKS",
            "LIVE",
            live.symbol.upper(),
            live.timeframe,
            live.market_snapshot_hash,
            live.direction,
            live.setup_type or "",
            live.engine_version,
            live.rule_set_version,
            live.configuration_version,
        ]
    )
    assert live.source_signal_id == "core-live"
    assert live.idempotency_key == sha256(canonical.encode("utf-8")).hexdigest()


def test_different_bootstrap_policy_fails_closed() -> None:
    command = _shadow_command()
    bad = dict(command.bootstrap_provenance or {})
    bad["policy_id"] = "OTHER_BOOTSTRAP_POLICY"
    with pytest.raises(ValueError):
        replace(command, bootstrap_provenance=bad)


def test_existing_database_has_both_independent_unique_barriers() -> None:
    constraints = {
        tuple(constraint.columns.keys()): constraint.name
        for constraint in SignalAutomationMetadata.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert constraints[("producer", "source_signal_id")] == (
        "uq_signal_automation_metadata_producer_source_signal"
    )
    assert constraints[("producer", "idempotency_key")] == (
        "uq_signal_automation_metadata_producer_idempotency"
    )


@pytest.mark.asyncio
async def test_concurrent_same_opportunity_converges_to_at_most_one_atomic_identity() -> None:
    persisted: set[tuple[str, str]] = set()
    lock = asyncio.Lock()

    async def attempt(original: str, snapshot_hash: str) -> bool:
        command = _shadow_command(
            econ="opp-race", original=original, snapshot_hash=snapshot_hash
        )
        key = (command.source_signal_id, command.idempotency_key)
        async with lock:
            if key in persisted:
                return False
            persisted.add(key)
            return True

    results = await asyncio.gather(
        *(attempt(f"core-{n}", f"hash-{n}") for n in range(12))
    )
    assert sum(results) == 1
    assert len(persisted) == 1


def test_authorized_bootstrap_shadow_requires_final_cohort_policy_and_economic_id() -> None:
    assert _is_authorized_bootstrap_shadow(_case(1, econ="opp-1")) is True
    assert _is_authorized_bootstrap_shadow(
        _case(2, econ="opp-1", cohort="OTHER")
    ) is False
    assert _is_authorized_bootstrap_shadow(
        _case(3, econ="opp-1", policy="OTHER")
    ) is False
    assert _is_authorized_bootstrap_shadow(_case(4, econ=None)) is False


def test_live_quality_metadata_exposes_existing_economic_opportunity_identity() -> None:
    metadata = {
        "risk_semantic_breakdown": {
            "structural_validation": {"economic_opportunity_id": "opp-live"}
        }
    }
    assert _stored_live_economic_opportunity_id(metadata) == "opp-live"
    assert _stored_live_economic_opportunity_id({}) is None


def test_live_wins_over_bootstrap_shadow_for_same_opportunity() -> None:
    cases = (
        _case(20, econ="opp-x", mode="SHADOW", outcome=1),
        _case(30, econ="opp-x", mode="LIVE", policy=None, outcome=0),
    )
    selected = _deduplicate_hp_economic_opportunities(cases)
    assert [case.signal_id for case in selected] == [30]
    assert selected[0].generation_mode == "LIVE"


def test_multiple_bootstrap_shadow_rows_count_once_deterministically_and_outcome_neutrally() -> None:
    first = _deduplicate_hp_economic_opportunities(
        (
            _case(9, econ="opp-y", outcome=1),
            _case(4, econ="opp-y", outcome=0),
            _case(7, econ="opp-y", outcome=1),
        )
    )
    second = _deduplicate_hp_economic_opportunities(
        (
            _case(9, econ="opp-y", outcome=0),
            _case(4, econ="opp-y", outcome=1),
            _case(7, econ="opp-y", outcome=0),
        )
    )
    assert [case.signal_id for case in first] == [4]
    assert [case.signal_id for case in second] == [4]


def test_distinct_opportunities_remain_distinct_hp_samples() -> None:
    selected = _deduplicate_hp_economic_opportunities(
        (_case(1, econ="opp-1"), _case(2, econ="opp-2"))
    )
    assert [case.signal_id for case in selected] == [1, 2]


def test_duplicate_opportunity_does_not_fake_exact_minimum() -> None:
    cases = tuple(_case(i, econ=f"opp-{i}") for i in range(1, 8)) + (
        _case(80, econ="opp-1", outcome=0),
    )
    result = HistoricalProbabilityEngine(cases).assess(_candidate())
    assert result.calibrated is False
    assert result.compatible_case_count == 7


def test_eight_genuine_deduped_opportunities_still_calibrate() -> None:
    cases = tuple(_case(i, econ=f"opp-{i}") for i in range(1, 9))
    result = HistoricalProbabilityEngine(cases).assess(_candidate())
    assert result.calibrated is True
    assert result.sample_size == 8
    assert len(result.neighbor_signal_ids) == 8


def test_nearest_neighbor_input_has_no_duplicate_economic_opportunity_sample() -> None:
    cases = tuple(_case(i, econ=f"opp-{i}") for i in range(1, 9)) + (
        _case(99, econ="opp-8", mode="LIVE", policy=None, outcome=0),
    )
    engine = HistoricalProbabilityEngine(cases)
    deduped = [c for c in engine.cases if c.semantic_cohort_id == FINAL]
    keys = [(c.semantic_cohort_id, c.economic_opportunity_id) for c in deduped]
    assert len(keys) == len(set(keys))
    assert next(c for c in deduped if c.economic_opportunity_id == "opp-8").signal_id == 99


def test_hp_thresholds_and_cohort_identity_are_unchanged() -> None:
    assert probability_module._MIN_EXACT == 8
    assert probability_module._MIN_FAMILY == 12
    assert probability_module._MIN_BROAD == 20
    assert probability_module._MAX_NEIGHBORS == 20
    assert FINAL == "BROOKS_HP_SEMANTIC_COHORT_W01_W19_V1"
    assert POLICY == "BROOKS_HP_COLD_START_SHADOW_W01_W19_V1"
