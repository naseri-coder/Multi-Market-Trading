from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Any

from app.modules.brooks_core.market_context import build_market_context
from app.modules.operations.trade_management import build_trade_management_plan


@dataclass(frozen=True, slots=True)
class _RiskTarget:
    target_number: int
    target_price: Decimal
    status: str = "PENDING"


class RiskCalculator:
    _ENTRY_METHODS = frozenset(
        {
            "STOP_TRIGGER_CONFIRMATION",
            "LIMIT_OR_MARKET_FADE",
            "LIMIT_OR_MARKET_ANTICIPATION",
            "MARKET_OR_LIMIT_ANTICIPATION",
        }
    )

    @staticmethod
    def _decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
        try:
            return Decimal(str(value))
        except (TypeError, ValueError, ArithmeticError):
            return default

    @staticmethod
    def _rr_points(risk_reward: Decimal) -> Decimal:
        # Frozen Risk policy.  The semantic repair changes the pre-trade reward
        # object, not these thresholds or points.
        if risk_reward >= Decimal("2.00"):
            return Decimal("45")
        if risk_reward >= Decimal("1.50"):
            return Decimal("38.25")
        if risk_reward >= Decimal("1.25"):
            return Decimal("33.75")
        if risk_reward >= Decimal("1.00"):
            return Decimal("27")
        if risk_reward >= Decimal("0.75"):
            return Decimal("18")
        return Decimal("9")

    @classmethod
    def _geometry_points(cls, candidate: Any) -> Decimal:
        entry = cls._decimal(getattr(candidate, "entry_price", None))
        stop = cls._decimal(getattr(candidate, "stop_loss", None))
        targets = tuple(getattr(candidate, "targets", ()) or ())
        direction = str(getattr(candidate, "direction", "")).upper()
        if entry <= 0 or stop <= 0 or not targets or direction not in {"LONG", "SHORT"}:
            return Decimal("0")
        target_values = tuple(cls._decimal(item) for item in targets)
        if direction == "LONG":
            valid = stop < entry and all(item > entry for item in target_values)
        else:
            valid = stop > entry and all(item < entry for item in target_values)
        return Decimal("40") if valid else Decimal("0")

    @staticmethod
    def _matching_evidence(candidate: Any) -> tuple[dict[str, str], ...]:
        setup = str(getattr(candidate, "setup_type", "") or "")
        direction = str(getattr(candidate, "direction", "")).upper()
        rows: list[dict[str, str]] = []
        for item in tuple(getattr(candidate, "rule_evidence", ()) or ()):
            if str(getattr(item, "status", "")) != "PASS":
                continue
            data = dict(getattr(item, "evidence", ()) or ())
            if data.get("setup_type") == setup and data.get("direction") == direction:
                rows.append({str(k): str(v) for k, v in data.items()})
        return tuple(rows)

    @classmethod
    def _entry_semantics(cls, candidate: Any) -> dict[str, Any]:
        rows = cls._matching_evidence(candidate)
        explicit = tuple(row for row in rows if row.get("entry_method"))
        methods = {row["entry_method"] for row in explicit}
        if not explicit:
            return {
                "entry_method": None,
                "mode": "LEGACY_STOP_TRIGGER_COMPAT",
                "evidence": None,
                "conflict": False,
            }
        if len(methods) != 1:
            return {
                "entry_method": "CONFLICTING",
                "mode": "INVALID_EXPLICIT_ENTRY_METHOD",
                "evidence": None,
                "conflict": True,
            }
        method = next(iter(methods))
        # Prefer the candidate/source evidence row because it carries the typed
        # reference/origin metadata; the generic stop witness intentionally does not.
        ordered = sorted(
            explicit,
            key=lambda row: (
                0 if row.get("entry_reference_price") not in {None, ""} else 1,
                0 if row.get("signal_index") not in {None, ""} else 1,
            ),
        )
        return {
            "entry_method": method,
            "mode": "TYPED_ENTRY_METHOD",
            "evidence": ordered[0],
            "conflict": False,
        }

    @classmethod
    def _signal_index(cls, candidate: Any) -> int | None:
        for row in cls._matching_evidence(candidate):
            raw = row.get("signal_index")
            try:
                return int(raw) if raw not in {None, ""} else None
            except (TypeError, ValueError):
                continue
        return None

    @classmethod
    def _alternative_entry_valid(
        cls,
        *,
        candidate: Any,
        method: str,
        evidence: dict[str, str] | None,
        entry: Decimal,
        direction: str,
    ) -> bool:
        if evidence is None or method not in cls._ENTRY_METHODS:
            return False
        reference_raw = evidence.get("entry_reference_price")
        economic_id = evidence.get("economic_opportunity_id", "").strip()
        semantic = evidence.get("entry_trigger_semantic", "").strip()
        if reference_raw in {None, ""} or not economic_id or not semantic:
            return False
        reference = cls._decimal(reference_raw, Decimal("NaN"))
        if not reference.is_finite() or reference != entry:
            return False

        if method == "LIMIT_OR_MARKET_FADE":
            expected_edge = (
                "AT_LOWER_RANGE_EDGE" if direction == "LONG" else "AT_UPPER_RANGE_EDGE"
            )
            boundary_key = "range_low" if direction == "LONG" else "range_high"
            boundary = cls._decimal(evidence.get(boundary_key), Decimal("NaN"))
            return bool(
                semantic == "AT_OR_NEAR_CANONICAL_RANGE_EDGE"
                and evidence.get("canonical_gap_id") == "BROOKS-GAP-045"
                and evidence.get("range_id", "").strip()
                and evidence.get("range_edge_state") == expected_edge
                and boundary.is_finite()
                and boundary == entry
            )

        if method == "LIMIT_OR_MARKET_ANTICIPATION":
            return bool(
                semantic == "MICRO_DOUBLE_SECOND_TEST_ANTICIPATION"
                and evidence.get("canonical_gap_id") == "BROOKS-GAP-068"
                and evidence.get("structure_id", "").strip()
                and evidence.get("entry_confirmation_state") == "ANTICIPATORY_UNCONFIRMED"
            )

        if method == "MARKET_OR_LIMIT_ANTICIPATION":
            return bool(
                semantic == "FINAL_FLAG_OPPOSITE_REVERSAL_MINIMUM_BEFORE_BREAKOUT"
                and evidence.get("canonical_gap_id") == "BROOKS-GAP-068"
                and evidence.get("final_flag_id", "").strip()
                and evidence.get("entry_confirmation_state") == "ANTICIPATORY_UNCONFIRMED"
            )

        return False

    @classmethod
    def _structural_assessment(cls, candidate: Any) -> tuple[Decimal, dict[str, Any]]:
        snapshot = getattr(candidate, "snapshot", None)
        entry = cls._decimal(getattr(candidate, "entry_price", None))
        direction = str(getattr(candidate, "direction", "")).upper()
        semantics = cls._entry_semantics(candidate)
        method = semantics["entry_method"]
        evidence = semantics["evidence"]

        if snapshot is None:
            return Decimal("8"), {
                "entry_method": method,
                "validation_mode": "SNAPSHOT_UNAVAILABLE_LEGACY_FALLBACK",
                "valid": None,
            }

        signal_index = cls._signal_index(candidate)
        if signal_index is None or not 0 <= signal_index < len(snapshot.candles):
            return Decimal("8"), {
                "entry_method": method,
                "validation_mode": "SIGNAL_INDEX_UNAVAILABLE_LEGACY_FALLBACK",
                "valid": None,
            }

        bar = snapshot.candles[signal_index]
        if method is None:
            valid = entry >= bar.high if direction == "LONG" else entry <= bar.low
            return (Decimal("15") if valid else Decimal("0")), {
                "entry_method": None,
                "validation_mode": "LEGACY_STOP_TRIGGER_COMPAT",
                "valid": valid,
                "signal_index": signal_index,
            }

        if method == "STOP_TRIGGER_CONFIRMATION":
            valid = entry >= bar.high if direction == "LONG" else entry <= bar.low
            return (Decimal("15") if valid else Decimal("0")), {
                "entry_method": method,
                "validation_mode": "STOP_TRIGGER_SIGNAL_BAR_EXTREME",
                "valid": valid,
                "signal_index": signal_index,
                "economic_opportunity_id": None if evidence is None else evidence.get("economic_opportunity_id"),
            }

        if method in {
            "LIMIT_OR_MARKET_FADE",
            "LIMIT_OR_MARKET_ANTICIPATION",
            "MARKET_OR_LIMIT_ANTICIPATION",
        }:
            valid = cls._alternative_entry_valid(
                candidate=candidate,
                method=method,
                evidence=evidence,
                entry=entry,
                direction=direction,
            )
            return (Decimal("15") if valid else Decimal("0")), {
                "entry_method": method,
                "validation_mode": "TYPED_ALTERNATIVE_EXECUTION_IDENTITY",
                "valid": valid,
                "signal_index": signal_index,
                "entry_reference_price": None if evidence is None else evidence.get("entry_reference_price"),
                "entry_trigger_semantic": None if evidence is None else evidence.get("entry_trigger_semantic"),
                "economic_opportunity_id": None if evidence is None else evidence.get("economic_opportunity_id"),
            }

        return Decimal("0"), {
            "entry_method": method,
            "validation_mode": "UNKNOWN_EXPLICIT_ENTRY_METHOD_FAIL_CLOSED",
            "valid": False,
            "signal_index": signal_index,
        }

    @classmethod
    def _structural_points(cls, candidate: Any) -> Decimal:
        points, _ = cls._structural_assessment(candidate)
        return points

    @classmethod
    def _legacy_target0_rr(
        cls,
        *,
        entry: Decimal,
        stop: Decimal,
        targets: tuple[Any, ...],
        direction: str,
    ) -> tuple[Decimal, dict[str, Any]]:
        risk = abs(entry - stop)
        if not targets or risk <= 0:
            return Decimal("0"), {"mode": "LEGACY_TARGET0_COMPAT"}
        target = cls._decimal(targets[0])
        directional = target - entry if direction == "LONG" else entry - target
        rr = directional / risk if directional > 0 else Decimal("0")
        return rr, {
            "mode": "LEGACY_TARGET0_COMPAT",
            "initial_risk": str(risk),
            "target0": str(target),
            "target0_r": str(rr),
        }

    @classmethod
    def _plan_rr(cls, candidate: Any) -> tuple[Decimal, dict[str, Any]]:
        entry = cls._decimal(getattr(candidate, "entry_price", None))
        stop = cls._decimal(getattr(candidate, "stop_loss", None))
        targets_raw = tuple(getattr(candidate, "targets", ()) or ())
        direction = str(getattr(candidate, "direction", "")).upper()
        lifecycle = getattr(candidate, "target_plan_lifecycle", None)

        if entry <= 0 or stop <= 0 or entry == stop or direction not in {"LONG", "SHORT"}:
            return Decimal("0"), {"mode": "INVALID_EXECUTION_GEOMETRY"}

        if lifecycle is None:
            return cls._legacy_target0_rr(
                entry=entry,
                stop=stop,
                targets=targets_raw,
                direction=direction,
            )
        if str(getattr(lifecycle, "direction", "")).upper() != direction:
            return Decimal("0"), {
                "mode": "TARGET_PLAN_DIRECTION_MISMATCH_FAIL_CLOSED",
                "target_plan_id": getattr(lifecycle, "plan_id", None),
            }

        initial_risk = abs(entry - stop)
        targets = tuple(
            _RiskTarget(number, cls._decimal(price))
            for number, price in enumerate(targets_raw, start=1)
        )
        target_r: dict[int, Decimal] = {}
        for target in targets:
            distance = (
                target.target_price - entry
                if direction == "LONG"
                else entry - target.target_price
            )
            if distance <= 0:
                return Decimal("0"), {
                    "mode": "INVALID_DIRECTIONAL_TARGET_FAIL_CLOSED",
                    "target_plan_id": lifecycle.plan_id,
                    "target_plan_state": lifecycle.state,
                    "invalid_target_number": target.target_number,
                    "invalid_target_price": str(target.target_price),
                }
            target_r[target.target_number] = distance / initial_risk

        snapshot = getattr(candidate, "snapshot", None)
        if snapshot is None:
            return Decimal("0"), {
                "mode": "TARGET_PLAN_CONTEXT_UNAVAILABLE_FAIL_CLOSED",
                "target_plan_id": lifecycle.plan_id,
                "target_plan_state": lifecycle.state,
            }

        try:
            market_context = build_market_context(snapshot)
            # Risk is pre-entry.  Never consume a resolved future reversal outcome.
            reversal_context = getattr(candidate, "reversal_outcome_context", None)
            if (
                reversal_context is not None
                and getattr(reversal_context, "state", None) != "PENDING_REVERSAL_OUTCOME"
            ):
                reversal_context = None
            plan = build_trade_management_plan(
                direction=direction,
                entry_price=entry,
                initial_stop_loss=stop,
                targets=targets,
                market_regime=market_context.regime,
                rule_ids=tuple(getattr(candidate, "rule_ids", ()) or ()),
                context_metadata={"channel_quality": market_context.channel_quality},
                reversal_outcome_context=reversal_context,
            )
        except (TypeError, ValueError, AttributeError, IndexError):
            return Decimal("0"), {
                "mode": "PRETRADE_PLAN_BUILD_FAILED_CLOSED",
                "target_plan_id": lifecycle.plan_id,
                "target_plan_state": lifecycle.state,
            }

        fractions = dict(plan.target_exit_fractions)
        contributions: list[dict[str, str | int]] = []
        planned = Decimal("0")
        for target in targets:
            fraction = fractions.get(target.target_number, Decimal("0"))
            weighted = fraction * target_r[target.target_number]
            planned += weighted
            contributions.append(
                {
                    "target_number": target.target_number,
                    "target_price": str(target.target_price),
                    "target_r": str(target_r[target.target_number]),
                    "allocation_fraction": str(fraction),
                    "weighted_target_r": str(weighted),
                }
            )

        # The approved TradeManagementPlan exposes a runner fraction but no
        # deterministic runner objective.  Per the repair contract, undefined
        # runner reward is conservatively zero and no target is re-labelled as
        # a runner objective inside Risk.
        runner_fraction = plan.runner_fraction
        runner_objective = None
        runner_r = Decimal("0")
        weighted_runner_r = Decimal("0")
        plan_rr = planned + weighted_runner_r

        return plan_rr, {
            "mode": "PLAN_WEIGHTED_PRETRADE",
            "initial_risk": str(initial_risk),
            "entry": str(entry),
            "initial_stop": str(stop),
            "target_plan_id": lifecycle.plan_id,
            "target_plan_state": lifecycle.state,
            "tm_context_class": plan.context_class,
            "target_contributions": contributions,
            "runner_fraction": str(runner_fraction),
            "runner_objective": runner_objective,
            "runner_r": str(runner_r),
            "weighted_runner_r": str(weighted_runner_r),
            "plan_rr": str(plan_rr),
            "runner_policy": "UNDEFINED_OBJECTIVE_ZERO_CONSERVATIVE",
        }

    def calculate_with_breakdown(self, candidate: Any) -> tuple[float, dict[str, Any]]:
        entry = self._decimal(getattr(candidate, "entry_price", None))
        stop = self._decimal(getattr(candidate, "stop_loss", None))
        if entry <= 0 or stop <= 0 or entry == stop:
            return 0.0, {
                "risk_semantic_model": "PLAN_WEIGHTED_PRETRADE",
                "failure": "INVALID_ENTRY_STOP",
            }

        plan_rr, plan_metadata = self._plan_rr(candidate)
        rr_points = self._rr_points(plan_rr)
        geometry_points = self._geometry_points(candidate)
        structural_points, structural_metadata = self._structural_assessment(candidate)
        score = rr_points + geometry_points + structural_points
        score = min(max(score, Decimal("0")), Decimal("100"))
        quantized = score.quantize(Decimal("0.01"))
        return float(quantized), {
            "risk_semantic_model": (
                "PLAN_WEIGHTED_PRETRADE"
                if plan_metadata.get("mode") != "LEGACY_TARGET0_COMPAT"
                else "LEGACY_TARGET0_COMPAT"
            ),
            "plan_reward": plan_metadata,
            "plan_rr": str(plan_rr),
            "rr_points": str(rr_points),
            "geometry_points": str(geometry_points),
            "structural_points": str(structural_points),
            "structural_validation": structural_metadata,
            "total_risk_score": str(quantized),
        }

    def calculate(self, candidate: Any) -> float:
        score, _ = self.calculate_with_breakdown(candidate)
        return score

    def calculate_leverage(
        self,
        *,
        entry_price: Decimal,
        stop_loss: Decimal,
        confidence: float | Decimal | None = None,
        quality_grade: str | None = None,
        risk_score: float | None = None,
        market_regime: str | None = None,
    ) -> Decimal:
        """Calculate the existing leverage recommendation; repair leaves it unchanged."""
        if entry_price <= 0 or stop_loss <= 0:
            return Decimal("1.00")

        risk_distance = abs(entry_price - stop_loss)
        if risk_distance <= 0:
            return Decimal("1.00")

        risk_percent = risk_distance / entry_price * Decimal("100")
        conf = Decimal(str(confidence)) if confidence is not None else Decimal("0")
        risk = Decimal(str(risk_score)) if risk_score is not None else Decimal("0")
        grade = (quality_grade or "").upper()
        regime = (market_regime or "UNKNOWN").upper()

        if grade in {"A", "A+"} and risk >= Decimal("89.50") and conf >= Decimal("0.885"):
            quality_base = Decimal("5")
        elif grade in {"A", "A+"} and risk >= Decimal("87.00") and conf >= Decimal("0.875"):
            quality_base = Decimal("3")
        elif grade in {"A", "A+"} and risk >= Decimal("85.00") and conf >= Decimal("0.850"):
            quality_base = Decimal("2")
        else:
            quality_base = Decimal("1")

        if risk_percent <= Decimal("0.75"):
            stop_cap = Decimal("5")
        elif risk_percent <= Decimal("1.25"):
            stop_cap = Decimal("3")
        elif risk_percent <= Decimal("2.00"):
            stop_cap = Decimal("2")
        else:
            stop_cap = Decimal("1")

        if regime == "TREND":
            regime_cap = Decimal("5")
        elif regime in {"LOW_VOLATILITY", "RANGE"}:
            regime_cap = Decimal("2")
        else:
            regime_cap = Decimal("1")

        leverage = min(quality_base, stop_cap, regime_cap)
        return leverage.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
