"""Typed chart evidence derived from Brooks Core rule evidence."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.modules.signal_automation.entities import BrooksRuleEvidence


@dataclass(frozen=True, slots=True)
class BrooksChartEvidence:
    signal_index: int
    setup_type: str | None

    family: str | None = None
    direction: str | None = None
    taxonomy: str | None = None
    context: str | None = None
    reasons: tuple[str, ...] = ()

    start_index: int | None = None

    breakout_index: int | None = None
    reference_swing_index: int | None = None
    reference_level: Decimal | None = None

    range_low: Decimal | None = None
    range_high: Decimal | None = None

    first_high: Decimal | None = None
    second_high: Decimal | None = None
    first_low: Decimal | None = None
    second_low: Decimal | None = None

    push_indices: tuple[int, ...] = ()

    structure_break_index: int | None = None
    old_extreme: Decimal | None = None

    source_rule_ids: tuple[str, ...] = ()


def _to_int(value: str | None) -> int | None:
    if value is None:
        return None

    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None

    return parsed if parsed >= 0 else None


def _to_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None

    try:
        parsed = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return None

    return parsed if parsed > 0 else None


def _to_indices(value: str | None) -> tuple[int, ...]:
    if not value:
        return ()

    result: list[int] = []

    for item in value.split(","):
        parsed = _to_int(item.strip())
        if parsed is not None:
            result.append(parsed)

    return tuple(result)


def _split_reasons(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()

    return tuple(
        part.strip()
        for part in value.split("|")
        if part.strip()
    )


def build_chart_evidence(
    *,
    signal_index: int | None = None,
    setup_type: str | None,
    rule_evidence: tuple[BrooksRuleEvidence, ...],
) -> BrooksChartEvidence:
    if signal_index is not None and signal_index < 0:
        raise ValueError("signal_index must be non-negative")

    merged: dict[str, str] = {}
    source_rule_ids: list[str] = []

    for item in rule_evidence:
        if item.status != "PASS":
            continue

        values = dict(item.evidence)

        evidence_setup = values.get("setup_type")

        # Candidate-specific evidence is preferred. Context evidence may
        # not contain setup_type and should not overwrite geometry.
        if (
            setup_type
            and evidence_setup
            and evidence_setup != setup_type
        ):
            continue

        source_rule_ids.append(item.rule_id)

        for key, value in item.evidence:
            if key not in merged:
                merged[key] = value

    evidence_signal_index = _to_int(
        merged.get("signal_index")
    )

    resolved_signal_index = (
        evidence_signal_index
        if evidence_signal_index is not None
        else signal_index
    )

    if resolved_signal_index is None:
        raise ValueError(
            "chart evidence requires signal_index"
        )

    return BrooksChartEvidence(
        signal_index=resolved_signal_index,
        setup_type=setup_type,
        family=merged.get("family"),
        direction=merged.get("direction"),
        taxonomy=merged.get("taxonomy"),
        context=(
            merged.get("context")
            or merged.get("regime")
        ),
        reasons=_split_reasons(
            merged.get("reasons")
        ),
        start_index=_to_int(
            merged.get("start_index")
        ),
        breakout_index=_to_int(
            merged.get("breakout_index")
        ),
        reference_swing_index=_to_int(
            merged.get("reference_swing_index")
        ),
        reference_level=_to_decimal(
            merged.get("reference_level")
        ),
        range_low=_to_decimal(
            merged.get("range_low")
        ),
        range_high=_to_decimal(
            merged.get("range_high")
        ),
        first_high=_to_decimal(
            merged.get("first_high")
        ),
        second_high=_to_decimal(
            merged.get("second_high")
        ),
        first_low=_to_decimal(
            merged.get("first_low")
        ),
        second_low=_to_decimal(
            merged.get("second_low")
        ),
        push_indices=_to_indices(
            merged.get("push_indices")
        ),
        structure_break_index=_to_int(
            merged.get("structure_break_index")
        ),
        old_extreme=_to_decimal(
            merged.get("old_extreme")
        ),
        source_rule_ids=tuple(
            dict.fromkeys(source_rule_ids)
        ),
    )
