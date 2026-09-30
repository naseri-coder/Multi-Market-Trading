from __future__ import annotations

from decimal import Decimal, InvalidOperation
from statistics import median
from typing import Any

from app.modules.ai_council.entities import AgentDecision
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.brooks_core.evidence_weighting import summarize_candidate_evidence


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def _status(item: Any) -> str:
    raw = getattr(item, "status", "")
    raw = getattr(raw, "value", raw)
    return str(raw).upper()


def _evidence_map(item: Any) -> dict[str, str]:
    raw = getattr(item, "evidence", ()) or ()

    if isinstance(raw, dict):
        return {
            str(key): str(value)
            for key, value in raw.items()
        }

    result: dict[str, str] = {}

    for pair in raw:
        if isinstance(pair, (tuple, list)) and len(pair) >= 2:
            result[str(pair[0])] = str(pair[1])

    return result


def _evidence_items(candidate: Any) -> tuple[Any, ...]:
    return tuple(
        getattr(candidate, "rule_evidence", ()) or ()
    )


def _selected_evidence(
    candidate: Any,
) -> tuple[tuple[Any, dict[str, str]], ...]:
    setup_type = str(
        getattr(candidate, "setup_type", "") or ""
    )
    direction = str(
        getattr(candidate, "direction", "") or ""
    ).upper()

    selected: list[tuple[Any, dict[str, str]]] = []

    for item in _evidence_items(candidate):
        data = _evidence_map(item)

        if (
            str(data.get("setup_type", "")) == setup_type
            and str(data.get("direction", "")).upper() == direction
        ):
            selected.append((item, data))

    return tuple(selected)


def _context_data(candidate: Any) -> dict[str, str]:
    wanted = {
        "regime",
        "structure_direction",
        "directional_bar_fraction",
        "bar_overlap_rate",
        "adjusted_displacement",
        "always_in",
        "breakout_direction",
        "context_reason",
    }

    result: dict[str, str] = {}

    for item in _evidence_items(candidate):
        data = _evidence_map(item)

        for key in wanted:
            if key in data:
                result[key] = data[key]

    return result


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None

    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _selected_family(candidate: Any) -> str:
    for _, data in _selected_evidence(candidate):
        family = str(data.get("family", "")).upper()

        if family:
            return family

    return ""


def _selected_signal_index(candidate: Any) -> int | None:
    indices: list[int] = []

    for _, data in _selected_evidence(candidate):
        raw = data.get("signal_index")

        if raw is None:
            continue

        try:
            indices.append(int(raw))
        except (TypeError, ValueError):
            continue

    if not indices:
        return None

    return max(indices)


class MarketAgent:
    name = "market_agent"

    _RANGE_FRIENDLY_FAMILIES = {
        "FAILED_BREAKOUT",
        "FAILED_FAILURE",
        "TRADING_RANGE_FADE",
        "MAJOR_TREND_REVERSAL",
        "WEDGE_REVERSAL",
        "CLIMACTIC_REVERSAL",
        "FINAL_FLAG_REVERSAL",
        "DOUBLE_TOP_BOTTOM_REVERSAL",
    }

    def evaluate(self, candidate: Any) -> AgentDecision:
        direction = str(
            getattr(candidate, "direction", "") or ""
        ).upper()

        context = _context_data(candidate)

        if direction not in {"LONG", "SHORT"} or not context:
            return AgentDecision(
                agent_name=self.name,
                score=40.0,
                confidence=0.30,
                approved=False,
                reasoning="Market context is incomplete.",
                metadata={
                    "source": "brooks_context_evidence",
                    "context_available": False,
                },
            )

        regime = str(
            context.get("regime", "AMBIGUOUS")
        ).upper()

        structure = str(
            context.get(
                "structure_direction",
                "AMBIGUOUS",
            )
        ).upper()

        always_in = str(
            context.get(
                "always_in",
                "UNRESOLVED",
            )
        ).upper()

        breakout = str(
            context.get(
                "breakout_direction",
                "UNRESOLVED",
            )
        ).upper()

        directional_fraction = _optional_decimal(
            context.get("directional_bar_fraction")
        )

        overlap_rate = _optional_decimal(
            context.get("bar_overlap_rate")
        )

        family = _selected_family(candidate)

        range_friendly = (
            family in self._RANGE_FRIENDLY_FAMILIES
        )

        policy = BrooksFullCorePolicy().context

        score = 75.0

        if regime == "BULL_TREND" and direction == "LONG":
            score += 8.0
        elif regime == "BEAR_TREND" and direction == "SHORT":
            score += 8.0
        elif regime in {"BULL_TREND", "BEAR_TREND"}:
            score -= 12.0
        elif regime == "TRADING_RANGE" and range_friendly:
            score += 5.0

        if structure == "BULL_TREND" and direction == "LONG":
            score += 6.0
        elif structure == "BEAR_TREND" and direction == "SHORT":
            score += 6.0
        elif structure in {"BULL_TREND", "BEAR_TREND"}:
            score -= 6.0

        if always_in == direction:
            score += 8.0
        elif always_in in {"LONG", "SHORT"}:
            score -= 10.0

        if breakout == direction:
            score += 6.0
        elif breakout in {"LONG", "SHORT"}:
            score -= 8.0

        if (
            regime == "TRADING_RANGE"
            and range_friendly
            and overlap_rate is not None
            and overlap_rate >= policy.range_min_body_overlap_rate
        ):
            score += 4.0

        if (
            regime in {"BULL_TREND", "BEAR_TREND"}
            and directional_fraction is not None
        ):
            if (
                directional_fraction
                >= policy.min_directional_bar_fraction
            ):
                score += 3.0
            else:
                score -= 3.0

        score = round(
            _clamp(score, 0.0, 100.0),
            2,
        )

        confidence = 0.55

        if regime and regime != "AMBIGUOUS":
            confidence += 0.15

        if structure in {"BULL_TREND", "BEAR_TREND"}:
            confidence += 0.10

        if always_in in {"LONG", "SHORT"}:
            confidence += 0.10

        if breakout in {"LONG", "SHORT"}:
            confidence += 0.10

        confidence = round(
            _clamp(confidence, 0.0, 0.95),
            4,
        )

        return AgentDecision(
            agent_name=self.name,
            score=score,
            confidence=confidence,
            approved=score >= 45.0,
            reasoning=(
                "Brooks market context evaluated "
                "against candidate direction."
            ),
            metadata={
                "source": "brooks_context_evidence",
                "brooks_regime": regime,
                "structure_direction": structure,
                "always_in": always_in,
                "breakout_direction": breakout,
                "selected_family": family,
                "range_friendly": range_friendly,
                "directional_bar_fraction": (
                    float(directional_fraction)
                    if directional_fraction is not None
                    else None
                ),
                "bar_overlap_rate": (
                    float(overlap_rate)
                    if overlap_rate is not None
                    else None
                ),
            },
        )


class PriceActionAgent:
    name = "price_action_agent"

    def evaluate(self, candidate: Any) -> AgentDecision:
        setup_type = str(getattr(candidate, "setup_type", "") or "")
        direction = str(getattr(candidate, "direction", "") or "").upper()
        summary = summarize_candidate_evidence(candidate)
        dimensions = (
            summary.structure_quality,
            summary.context_quality,
            summary.entry_quality,
        )
        score = round(sum(dimensions) / len(dimensions), 2)
        major_conflicts = tuple(
            item for item in summary.conflicts if item.severity == "MAJOR"
        )
        approved = (
            bool(setup_type)
            and direction in {"LONG", "SHORT"}
            and not major_conflicts
            and summary.entry_quality > 0
            and summary.structure_quality > 0
            and summary.context_quality > 0
        )
        confidence = round(
            _clamp(summary.brooks_certainty, 0.0, 0.95),
            4,
        )
        reasoning = (
            "Candidate-specific Brooks evidence is structurally/contextually consistent."
            if approved
            else "Candidate-specific Brooks evidence is incomplete or materially conflicted."
        )
        return AgentDecision(
            agent_name=self.name,
            score=score,
            confidence=confidence,
            approved=approved,
            reasoning=reasoning,
            metadata={
                "source": "candidate_specific_weighted_brooks_evidence",
                "structure_quality": summary.structure_quality,
                "context_quality": summary.context_quality,
                "entry_quality": summary.entry_quality,
                "selected_rule_ids": summary.selected_rule_ids,
                "conflicts": tuple(
                    f"{item.severity}:{item.rule_id}:{item.reason}"
                    for item in summary.conflicts
                ),
                "unclassified_rule_ids": summary.unclassified_rule_ids,
            },
        )


def _verified_v5_execution_geometry(candidate: Any) -> bool:
    """Verify exceptional geometry against the existing V5 engine, not a new rule."""
    from app.modules.brooks_core.advanced_context import assess_advanced_context
    from app.modules.brooks_core.books_full_engine import BrooksTrilogyFullCoreEngine
    from app.modules.brooks_core.books_full_patterns import scan_full_brooks_patterns
    from app.modules.brooks_core.context_classifier import assess_books_context
    from app.modules.brooks_core.market_context import build_market_context

    engine = BrooksTrilogyFullCoreEngine(
        policy=BrooksFullCorePolicy(enable_trade_decisions=True)
    )
    if getattr(candidate, "engine_version", None) != engine.engine_version:
        return False
    if getattr(candidate, "configuration_version", None) != engine.policy.configuration_version:
        return False
    snapshot = getattr(candidate, "snapshot", None)
    if snapshot is None:
        return False
    context = assess_books_context(snapshot, policy=engine.policy.context)
    advanced = assess_advanced_context(snapshot, policy=engine.policy)
    market = build_market_context(snapshot, policy=engine.policy)
    scan = scan_full_brooks_patterns(snapshot, context, engine.policy)
    eligible = tuple(
        item for item in scan.candidates
        if engine._context_contract_status(item, context, market)[0] == "PASS"
        and not engine._barbwire_stop_entry_veto(snapshot, item)
    )
    chosen = engine._choose_candidate(eligible, context, advanced, market)
    if chosen is None:
        return False
    if (chosen.setup_type, chosen.direction) != (candidate.setup_type, candidate.direction):
        return False
    entry, stop, targets, _, _ = engine._execution_geometry(snapshot, chosen, advanced)
    return bool(targets) and (
        candidate.entry_price == entry
        and candidate.stop_loss == stop
        and tuple(candidate.targets) == targets
    )


class RiskAgent:
    name = "risk_agent"

    def evaluate(self, candidate: Any) -> AgentDecision:
        direction = str(
            getattr(candidate, "direction", "") or ""
        ).upper()

        entry = _optional_decimal(
            getattr(candidate, "entry_price", None)
        )

        stop = _optional_decimal(
            getattr(candidate, "stop_loss", None)
        )

        raw_targets = tuple(
            getattr(candidate, "targets", ()) or ()
        )

        targets = tuple(
            value
            for value in (
                _optional_decimal(item)
                for item in raw_targets
            )
            if value is not None
        )

        basic_prices_valid = (
            direction in {"LONG", "SHORT"}
            and entry is not None
            and stop is not None
            and entry > 0
            and stop > 0
        )

        stop_side_ok = False

        if basic_prices_valid:
            if direction == "LONG":
                stop_side_ok = stop < entry
            else:
                stop_side_ok = stop > entry

        targets_side_ok = False

        if basic_prices_valid and targets:
            if direction == "LONG":
                targets_side_ok = all(
                    target > entry
                    for target in targets
                )
            else:
                targets_side_ok = all(
                    target < entry
                    for target in targets
                )

        ladder_ok = False

        if len(targets) >= 2:
            if direction == "LONG":
                ladder_ok = all(
                    current > previous
                    for previous, current
                    in zip(targets, targets[1:])
                )
            elif direction == "SHORT":
                ladder_ok = all(
                    current < previous
                    for previous, current
                    in zip(targets, targets[1:])
                )

        snapshot = getattr(
            candidate,
            "snapshot",
            None,
        )

        candles = tuple(
            getattr(snapshot, "candles", ()) or ()
        )

        signal_index = _selected_signal_index(
            candidate
        )

        signal_index_source = "evidence"

        if signal_index is None and candles:
            signal_index = len(candles) - 1
            signal_index_source = "snapshot_last_closed"

        signal = None

        if (
            signal_index is not None
            and 0 <= signal_index < len(candles)
        ):
            signal = candles[signal_index]

        trigger_structure_ok = False

        if (
            basic_prices_valid
            and signal is not None
        ):
            if direction == "LONG":
                trigger_structure_ok = (
                    entry >= signal.high
                    and stop < signal.low
                )
            else:
                trigger_structure_ok = (
                    entry <= signal.low
                    and stop > signal.high
                )

        # V5 permits one structural target and Chapter-29 capped stops.
        # Exceptional geometry must exactly match the existing engine output.
        v5_geometry_verified = False
        if (
            basic_prices_valid and stop_side_ok and targets_side_ok
            and (len(targets) == 1 or not trigger_structure_ok)
        ):
            v5_geometry_verified = _verified_v5_execution_geometry(candidate)
        target_plan_ok = (len(targets) >= 2 and ladder_ok) or (
            len(targets) == 1 and v5_geometry_verified
        )
        if v5_geometry_verified and signal is not None:
            trigger_structure_ok = (
                entry >= signal.high if direction == "LONG" else entry <= signal.low
            )

        policy = BrooksFullCorePolicy()

        recent_window = (
            policy.context.recent_window_bars
        )

        climax_threshold = (
            policy
            .climax_range_multiple_of_recent_median
        )

        signal_range_ratio: Decimal | None = None

        if (
            signal is not None
            and signal_index is not None
            and signal_index > 0
        ):
            start = max(
                0,
                signal_index - recent_window,
            )

            prior = candles[start:signal_index]

            prior_ranges = [
                candle.high - candle.low
                for candle in prior
                if candle.high > candle.low
            ]

            signal_range = (
                signal.high - signal.low
            )

            if prior_ranges and signal_range > 0:
                typical_range = median(
                    prior_ranges
                )

                if typical_range > 0:
                    signal_range_ratio = (
                        signal_range
                        / typical_range
                    )

        score = 60.0

        if stop_side_ok:
            score += 7.0
        else:
            score -= 30.0

        if targets_side_ok:
            score += 7.0
        else:
            score -= 20.0

        if target_plan_ok:
            score += 6.0
        else:
            score -= 10.0

        if trigger_structure_ok:
            score += 5.0
        else:
            score -= 10.0

        climax_detected = False

        if signal_range_ratio is not None:
            if signal_range_ratio <= climax_threshold:
                score += 5.0
            else:
                score -= 5.0
                climax_detected = True

        score = round(
            _clamp(score, 0.0, 100.0),
            2,
        )

        confidence = 0.50

        if stop_side_ok:
            confidence += 0.07

        if targets_side_ok:
            confidence += 0.07

        if target_plan_ok:
            confidence += 0.06

        if trigger_structure_ok:
            confidence += 0.08

        if signal_range_ratio is not None:
            confidence += 0.07

        confidence = round(
            _clamp(confidence, 0.0, 0.95),
            4,
        )

        approved = (
            basic_prices_valid
            and stop_side_ok
            and targets_side_ok
            and target_plan_ok
            and trigger_structure_ok
            and score >= 60.0
        )

        return AgentDecision(
            agent_name=self.name,
            score=score,
            confidence=confidence,
            approved=approved,
            reasoning=(
                "Execution geometry and "
                "signal-bar robustness evaluated."
            ),
            metadata={
                "risk_model": "execution_robustness_v2",
                "stop_side_ok": stop_side_ok,
                "targets_side_ok": targets_side_ok,
                "target_count": len(targets),
                "target_ladder_ok": ladder_ok,
                "target_plan_ok": target_plan_ok,
                "v5_geometry_verified": v5_geometry_verified,
                "signal_index": signal_index,
                "signal_index_source": (
                    signal_index_source
                ),
                "trigger_structure_ok": (
                    trigger_structure_ok
                ),
                "signal_bar_range_ratio": (
                    round(
                        float(signal_range_ratio),
                        4,
                    )
                    if signal_range_ratio is not None
                    else None
                ),
                "climax_threshold": float(
                    climax_threshold
                ),
                "climax_detected": climax_detected,
            },
        )
