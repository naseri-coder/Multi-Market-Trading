from decimal import Decimal

import pytest

from app.modules.brooks_core.books_full_engine import BrooksTrilogyFullCoreEngine
from app.modules.brooks_core.engine_contract import TargetSourceEvidence
from app.modules.signals.service import SignalService


AFFECTED_CASES = (
    ("HYPEUSDT", "94.47836930212484804798377064", "0.00100", "93.46700", "LONG", "94.47800"),
    ("ZECUSDT", "1481.193333333333333333333333", "0.01", "1491.06", "SHORT", "1481.20"),
    ("XMRUSDT", "559.0666666666666666666666667", "0.01", "569.54", "SHORT", "559.07"),
    ("NEARUSDT", "3.985090909090909090909090909", "0.0010", "4.0310", "SHORT", "3.9860"),
)


@pytest.mark.parametrize("symbol,raw,tick,entry,direction,expected", AFFECTED_CASES)
def test_affected_targets_are_tick_aligned_and_persistence_safe(
    symbol, raw, tick, entry, direction, expected
):
    del symbol
    normalized = BrooksTrilogyFullCoreEngine._normalize_executable_target(
        Decimal(raw), tick=Decimal(tick), entry=Decimal(entry), direction=direction
    )
    assert normalized == Decimal(expected)
    assert normalized % Decimal(tick) == 0
    assert (normalized > Decimal(entry)) if direction == "LONG" else (normalized < Decimal(entry))
    persisted = SignalService._decimal(
        str(normalized), field="Target price", precision=38, scale=18, positive=True
    )
    assert persisted == normalized
    assert Decimal(str(persisted)) == normalized

@pytest.mark.parametrize(
    "raw,tick,entry,direction",
    (("0.103600", "0.000010", "0.095280", "LONG"), ("85803.10", "0.10", "85000", "LONG")),
)
def test_already_aligned_targets_remain_exactly_unchanged(raw, tick, entry, direction):
    value = Decimal(raw)
    assert BrooksTrilogyFullCoreEngine._normalize_executable_target(
        value, tick=Decimal(tick), entry=Decimal(entry), direction=direction
    ) == value


def test_directional_policy_is_conservative_and_supports_non_power_of_ten_tick():
    assert BrooksTrilogyFullCoreEngine._normalize_executable_target(
        Decimal("11.37"), tick=Decimal("0.25"), entry=Decimal("10"), direction="LONG"
    ) == Decimal("11.25")
    assert BrooksTrilogyFullCoreEngine._normalize_executable_target(
        Decimal("8.63"), tick=Decimal("0.25"), entry=Decimal("10"), direction="SHORT"
    ) == Decimal("8.75")


def test_normalized_collision_preserves_all_semantic_sources():
    engine = BrooksTrilogyFullCoreEngine()
    tick = Decimal("0.01")
    entry = Decimal("100")
    first = TargetSourceEvidence("MEASURED_MOVE", "source:a", 1, 2, direction="LONG")
    second = TargetSourceEvidence("SWING_MAGNET", "source:b", 3, 4, direction="LONG")
    entries = [
        (engine._normalize_executable_target(Decimal("101.004"), tick=tick, entry=entry, direction="LONG"), first, "a"),
        (engine._normalize_executable_target(Decimal("101.009"), tick=tick, entry=entry, direction="LONG"), second, "b"),
    ]
    identities, basis = engine._coalesce_target_identities(entries, signal_index=5)
    assert len(identities) == 1
    assert identities[0].target_price == Decimal("101.00")
    assert {source.source_id for source in identities[0].sources} == {"source:a", "source:b"}
    assert basis == {"source:a": "a", "source:b": "b"}


def test_normalization_fails_closed_if_reward_would_collapse_to_entry():
    with pytest.raises(ValueError, match="remain above entry"):
        BrooksTrilogyFullCoreEngine._normalize_executable_target(
            Decimal("100.004"), tick=Decimal("0.01"), entry=Decimal("100.00"), direction="LONG"
        )
