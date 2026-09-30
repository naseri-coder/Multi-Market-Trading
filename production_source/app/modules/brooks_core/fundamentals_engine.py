"""PDF-grounded Brooks fundamentals engine v1.

This is a source-grounded core for the uploaded 150-slide fundamentals PDF, not a claim
to reproduce the complete Brooks Trading Course.

Source-backed decision chain:
1. Context is more important than isolated candlestick patterns (pp. 27, 117-123).
2. Bull trend structure is HH/HL and bear trend structure is LH/LL (p. 127).
3. In a bull trend, look for H2 pullback; buy stop above signal-bar high (p. 11).
4. In a bear trend, look for L2 pullback; sell stop below signal-bar low (p. 12).
5. Inside/outside bar definitions are exact (p. 16) and unresolved counting edges
   remain fail-closed.
6. EMA 20 is the course default moving average (p. 20), but indicators remain secondary
   to bars/context (pp. 133-135).

Engineering layer:
- causal swing confirmation;
- simplified H2/L2 counting edge policy;
- entry price buffer;
- structural stop buffer;
- R-multiple targets.

The engineering layer is versioned separately and autonomous LONG/SHORT is disabled by
default. Callers must explicitly enable it in FundamentalsExecutionPolicy.
"""

from __future__ import annotations

from decimal import Decimal

from app.modules.brooks_core.causal_structure import (
    confirm_swings_causally,
    evaluate_br031_structure,
)
from app.modules.brooks_core.engine_contract import BrooksEngineResult
from app.modules.brooks_core.fundamentals_policy import FundamentalsExecutionPolicy
from app.modules.brooks_core.second_entry import detect_second_entry
from app.modules.market_data.entities import MarketSnapshot
from app.modules.signal_automation.entities import BrooksRuleEvidence


def _ema20(snapshot: MarketSnapshot) -> Decimal | None:
    candles = snapshot.candles
    if len(candles) < 20:
        return None
    alpha = Decimal("2") / Decimal("21")
    value = candles[0].close
    for candle in candles[1:]:
        value = (candle.close * alpha) + (value * (Decimal("1") - alpha))
    return value


def _engineering_execution(
    *,
    snapshot: MarketSnapshot,
    signal_index: int,
    direction: str,
    start_index: int,
    policy: FundamentalsExecutionPolicy,
) -> tuple[Decimal, Decimal, tuple[Decimal, ...]]:
    signal = snapshot.candles[signal_index]
    signal_range = signal.high - signal.low
    stop_buffer = signal_range * policy.stop_buffer_fraction_of_signal_range

    if direction == "LONG":
        entry = signal.high * (Decimal("1") + policy.entry_buffer_fraction)
        structural_low = min(c.low for c in snapshot.candles[start_index : signal_index + 1])
        stop = structural_low - stop_buffer
        risk = entry - stop
        if risk <= 0:
            raise ValueError("invalid LONG engineering risk geometry")
        targets = tuple(entry + risk * multiple for multiple in policy.target_r_multiples)
        return entry, stop, targets

    entry = signal.low * (Decimal("1") - policy.entry_buffer_fraction)
    structural_high = max(c.high for c in snapshot.candles[start_index : signal_index + 1])
    stop = structural_high + stop_buffer
    risk = stop - entry
    if risk <= 0:
        raise ValueError("invalid SHORT engineering risk geometry")
    targets = tuple(entry - risk * multiple for multiple in policy.target_r_multiples)
    return entry, stop, targets


class BrooksFundamentalsH2L2Engine:
    engine_version = "phase7c-pdf-fundamentals-h2l2-v1"
    rule_set_version = "brooks-fundamentals-slides-1-150-v1"

    def __init__(
        self,
        *,
        policy: FundamentalsExecutionPolicy | None = None,
    ) -> None:
        self.policy = policy or FundamentalsExecutionPolicy()

    async def evaluate(self, snapshot: MarketSnapshot) -> BrooksEngineResult:
        if len(snapshot.candles) < max(
            8,
            self.policy.swing_left_bars + self.policy.swing_right_bars + 4,
        ):
            return self._no_signal(
                reasoning=("Insufficient closed candles for causal market structure.",),
                configuration_version=self.policy.configuration_version,
            )

        scan = confirm_swings_causally(
            snapshot.candles,
            left_bars=self.policy.swing_left_bars,
            right_bars=self.policy.swing_right_bars,
        )
        structure = evaluate_br031_structure(scan)

        evidence: list[BrooksRuleEvidence] = [
            BrooksRuleEvidence(
                rule_id="BR-031",
                status="PASS" if structure.direction != "AMBIGUOUS" else "AMBIGUOUS",
                source_pages=(127,),
                evidence=(
                    ("structure", structure.direction),
                    ("supporting_swings", ",".join(map(str, structure.supporting_swing_indices))),
                    ("swing_algorithm", "ENGINEERING_CAUSAL_CONFIRMATION"),
                ),
                failed_conditions=()
                if structure.direction != "AMBIGUOUS"
                else ("confirmed swings do not yet resolve HH/HL or LH/LL",),
            ),
            BrooksRuleEvidence(
                rule_id="BR-012",
                status="PASS",
                source_pages=(20,),
                evidence=(
                    ("ema_length", "20"),
                    ("ema20", str(_ema20(snapshot)) if _ema20(snapshot) is not None else "INSUFFICIENT_DATA"),
                    ("decision_role", "SECONDARY_CONTEXT_ONLY"),
                ),
            ),
            BrooksRuleEvidence(
                rule_id="BR-027",
                status="PASS",
                source_pages=(116, 117, 118, 119, 120, 123),
                evidence=(("pattern_alone_insufficient", "true"),),
            ),
        ]

        if structure.direction == "AMBIGUOUS":
            return self._no_signal(
                reasoning=(
                    f"Context unresolved: {structure.reason}",
                    "PDF emphasizes context over isolated candle patterns.",
                ),
                evidence=tuple(evidence),
                rule_ids=("BR-031", "BR-012", "BR-027"),
                configuration_version=self.policy.configuration_version,
            )

        wanted_kind = "HIGH" if structure.direction == "BULL_TREND" else "LOW"
        candidate_swings = [s for s in scan.swings if s.kind == wanted_kind]
        if not candidate_swings:
            return self._no_signal(
                reasoning=("No confirmed structural pullback anchor available.",),
                evidence=tuple(evidence),
                rule_ids=("BR-031", "BR-012", "BR-027"),
                configuration_version=self.policy.configuration_version,
            )

        start_index = candidate_swings[-1].candle_index
        if len(snapshot.candles) - start_index > self.policy.pullback_window_bars:
            start_index = len(snapshot.candles) - self.policy.pullback_window_bars

        assessment = detect_second_entry(
            snapshot.candles,
            trend_direction=structure.direction,
            start_index=start_index,
        )

        if assessment.setup is None:
            return self._no_signal(
                reasoning=(
                    f"Structure={structure.direction}.",
                    f"Second-entry assessment: {assessment.reason}",
                    "No H2/L2-style signal on the final closed bar.",
                ),
                evidence=tuple(evidence),
                rule_ids=("BR-031", "BR-012", "BR-027"),
                configuration_version=self.policy.configuration_version,
            )

        setup = assessment.setup
        source_rule_id = "SRC-P11-H2" if setup.direction == "LONG" else "SRC-P12-L2"
        evidence.append(
            BrooksRuleEvidence(
                rule_id=source_rule_id,
                status="PASS",
                source_pages=setup.source_pages,
                evidence=(
                    ("setup_type", setup.setup_type),
                    ("countertrend_legs", str(setup.countertrend_legs)),
                    ("signal_index", str(setup.signal_index)),
                    ("counting_policy", "ENGINEERING_CAUSAL_STATE_MACHINE_V1"),
                ),
            )
        )

        if not self.policy.enable_trade_decisions:
            return self._no_signal(
                setup_type=setup.setup_type,
                reasoning=(
                    f"Detected {setup.setup_type} in resolved {structure.direction}.",
                    "Trade decision intentionally disabled by default.",
                    "Enable explicitly only after server-side review/backtest of engineering execution policy.",
                ),
                evidence=tuple(evidence),
                rule_ids=("BR-031", "BR-012", "BR-027", source_rule_id),
                configuration_version=self.policy.configuration_version,
            )

        entry, stop, targets = _engineering_execution(
            snapshot=snapshot,
            signal_index=setup.signal_index,
            direction=setup.direction,
            start_index=setup.start_index,
            policy=self.policy,
        )
        evidence.append(
            BrooksRuleEvidence(
                rule_id="ENG-EXEC-001",
                status="PASS",
                source_pages=(),
                evidence=(
                    ("source", "ENGINEERING_POLICY_NOT_BROOKS_RULE"),
                    ("entry_buffer_fraction", str(self.policy.entry_buffer_fraction)),
                    (
                        "stop_buffer_fraction_of_signal_range",
                        str(self.policy.stop_buffer_fraction_of_signal_range),
                    ),
                    (
                        "target_r_multiples",
                        ",".join(str(x) for x in self.policy.target_r_multiples),
                    ),
                ),
            )
        )

        return BrooksEngineResult(
            decision=setup.direction,
            entry_price=entry,
            stop_loss=stop,
            targets=targets,
            setup_type=setup.setup_type,
            reasoning=(
                f"Resolved context={structure.direction} using confirmed HH/HL or LH/LL structure.",
                f"Detected source-grounded second-entry concept: {setup.setup_type}.",
                "Entry direction follows PDF p11/p12 signal-bar stop-entry concept.",
                "Stop/target geometry is explicit engineering policy, not asserted as Brooks-authored.",
            ),
            rule_ids=("BR-031", "BR-012", "BR-027", source_rule_id, "ENG-EXEC-001"),
            failed_rules=(),
            rule_evidence=tuple(evidence),
            engine_version=self.engine_version,
            rule_set_version=self.rule_set_version,
            configuration_version=self.policy.configuration_version,
        )

    @staticmethod
    def _no_signal(
        *,
        reasoning: tuple[str, ...],
        configuration_version: str,
        setup_type: str | None = None,
        evidence: tuple[BrooksRuleEvidence, ...] = (),
        rule_ids: tuple[str, ...] = (),
    ) -> BrooksEngineResult:
        return BrooksEngineResult(
            decision="NO_SIGNAL",
            entry_price=None,
            stop_loss=None,
            targets=(),
            setup_type=setup_type,
            reasoning=reasoning,
            rule_ids=rule_ids,
            failed_rules=(),
            rule_evidence=evidence,
            engine_version="phase7c-pdf-fundamentals-h2l2-v1",
            rule_set_version="brooks-fundamentals-slides-1-150-v1",
            configuration_version=configuration_version,
        )
