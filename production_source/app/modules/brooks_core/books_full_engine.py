"""Full Brooks trilogy core engine v3.

Unlike the narrow v2 H2/L2 detector, this engine has separate detectors for the major
operational families in all three books: trend continuation, breakout / breakout
pullback / failed breakout, trading-range fades, and mature reversal families (MTR,
wedge, climax, final flag, double top/bottom).

It is additive and does not alter production wiring.  Autonomous LONG/SHORT remains
disabled by default, but pattern detection is complete and returns the best setup_type
inside a NO_SIGNAL result for integration/shadow use.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR

from app.modules.brooks_core.books_full_entities import BrooksPatternCandidate
from app.modules.brooks_core.advanced_context import assess_advanced_context
from app.modules.brooks_core.higher_probability import assess_higher_probability, ProbabilityBand
from app.modules.brooks_core.evidence_weighting import rule_profile
from app.modules.brooks_core.books_full_patterns import _ema20_values, scan_full_brooks_patterns
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.brooks_core.context_classifier import (
    assess_books_context,
    body_fraction,
    classify_tight_trading_range,
    classify_barbwire_identity,
    classify_broad_trading_range,
    is_strong_bear_bar,
    is_strong_bull_bar,
    chapter5_reversal_diagnostic,
)
from app.modules.brooks_core.causal_structure import confirm_swings_causally
from app.modules.brooks_core.correction_lifecycle import (
    build_breakout_attempt_identity,
    classify_breakout_lifecycle,
)
from app.modules.brooks_core.engine_contract import (
    BrooksEngineResult,
    EntryExecutionIntent,
    ReversalOutcomeContext,
    REVERSAL_OUTCOME_RULE_ID,
    StopSourceIdentity,
    TargetPlanLifecycle,
    TargetSourceEvidence,
    TargetSourceIdentity,
)
from app.modules.brooks_core.market_context import build_market_context
from app.modules.brooks_core.structural_geometry import (
    build_trend_channel_geometry,
    classify_channel_boundary_event,
)
from app.modules.brooks_core.volatility import average_bar_range
from app.modules.market_data.entities import MarketSnapshot
from app.modules.signal_automation.entities import BrooksRuleEvidence


_RULE_SOURCE = {
    "BB-TRD-19-TREND-STRENGTH": ("Trading Price Action Trends", (337, 338, 339)),
    "BB-RNG-02-BREAKOUT-FOLLOWTHROUGH": ("Trading Price Action Trading Ranges", (39, 40, 41)),
    "BB-RNG-05-BREAKOUT-PULLBACK": ("Trading Price Action Trading Ranges", (30, 31, 34)),
    "BB-RNG-05-FAILED-BREAKOUT": ("Trading Price Action Trading Ranges", (30, 34, 48)),
    "BB-RNG-05-FAILED-FAILURE": ("Trading Price Action Trading Ranges", (12, 30, 34)),
    "BB-RNG-17-HL-BAR-COUNT": ("Trading Price Action Trading Ranges", (29, 108, 109)),
    "BB-RNG-18-WEDGE-PULLBACK": ("Trading Price Action Trading Ranges", (4,)),
    "BB-RNG-21-BUY-LOW-SELL-HIGH": ("Trading Price Action Trading Ranges", (134, 147)),
    "BB-RNG-22-TIGHT-RANGE": ("Trading Price Action Trading Ranges", (48, 147)),
    "BB-RNG-26-TWO-REASONS": ("Trading Price Action Trading Ranges", (187, 188, 189)),
    "BB-REV-03-MAJOR-TREND-REVERSAL": ("Trading Price Action Reversals", (70, 95, 97)),
    "BB-REV-04-CLIMACTIC-REVERSAL": ("Trading Price Action Reversals", (139, 140)),
    "BB-REV-05-WEDGE-THREE-PUSH": ("Trading Price Action Reversals", (19, 25)),
    "BB-REV-05-MICRO-WEDGE": ("Trading Price Action Reversals", (151, 158, 159, 168, 176, 179, 180)),
    "BB-REV-05-PARABOLIC-WEDGE": ("Trading Price Action Reversals", (152, 153, 170, 174)),
    "BB-REV-07-FINAL-FLAG": ("Trading Price Action Reversals", (80, 83, 189)),
    "BB-REV-DOUBLE-TOP-BOTTOM": ("Trading Price Action Reversals", (86, 217)),
    "BB-REV-15-ALWAYS-IN": ("Trading Price Action Reversals", (321, 322)),
    "BB-REV-MICRO-DOUBLE-TOP-BOTTOM": ("Trading Price Action Trends / Reversals", (106, 88)),
    "BB-TRD-TIGHT-CHANNEL": ("Trading Price Action Trends", (24, 250, 258, 279)),
    "BB-TRD-SPIKE-CHANNEL": ("Trading Price Action Trends", (250, 258, 284)),
    "BB-TRD-SPIKE": ("Trading Price Action Trends", (279, 280, 281, 325, 358)),
    "BB-TRD-CHANNEL": ("Trading Price Action Trends", (195, 207, 209, 248)),
    "BB-TRD-MEASURED-MOVE": ("Trading Price Action Trends", (102, 165, 170, 172)),
    "BB-TRD-OPENING-REVERSAL": ("Trading Price Action Trends", (19, 149, 431)),
    "BB-RNG-CTX-TREND-VS-RANGE": ("Trading Price Action Trading Ranges", (108, 109, 113)),
    "BB-REV-03-REVERSAL-MATURITY": ("Trading Price Action Reversals", (111, 112, 113)),
    "BB-RNG-17-H2L2-TREND-CONTEXT": ("Trading Price Action Trading Ranges", (108, 109)),
    "BB-RNG-29-SIGNAL-BAR-STOP": ("Trading Price Action Trading Ranges", (202, 203, 204)),
}

_RULE_SOURCE.update({
    "BB-TRD-04-CANDLE-PATTERNS": ("Trading Price Action Trends", (83, 84, 85)),
    "BB-TRD-05-TWO-BAR-REVERSAL": ("Trading Price Action Trends", (102, 103, 104)),
    "BB-TRD-05-THREE-BAR-REVERSAL": ("Trading Price Action Trends", (104,)),
    "BB-TRD-06-II-III": ("Trading Price Action Trends", (105, 106)),
    "BB-TRD-06-IOI": ("Trading Price Action Trends", (105, 161)),
    "BB-TRD-06-BREAKOUT-MODE": ("Trading Price Action Trends", (105, 106)),
    "BB-TRD-06-REVERSAL-BAR-FAILURE": ("Trading Price Action Trends", (106,)),
    "BB-TRD-06-SHAVED-BAR": ("Trading Price Action Trends", (106, 152, 153)),
    "BB-TRD-06-EXHAUSTION-BAR": ("Trading Price Action Trends", (106, 115, 116)),
    "BB-TRD-06-LEDGE": ("Trading Price Action Trends", (18,)),
    "BB-TRD-07-OUTSIDE-BAR": ("Trading Price Action Trends", (155, 161)),
    "BB-RNG-06-GAPS": ("Trading Price Action Trading Ranges", (6, 7, 8)),
    "BB-RNG-12-DOUBLE-TOP-BEAR-FLAG": ("Trading Price Action Trading Ranges", (95, 96)),
    "BB-RNG-12-DOUBLE-BOTTOM-BULL-FLAG": ("Trading Price Action Trading Ranges", (95, 96)),
    "BB-RNG-13-TWENTY-GAP": ("Trading Price Action Trading Ranges", (100, 101)),
    "BB-RNG-14-FIRST-MA-GAP": ("Trading Price Action Trading Ranges", (102, 103)),
    "BB-RNG-14-SECOND-MA-GAP": ("Trading Price Action Trading Ranges", (102, 103)),
    "BB-RNG-14-GAP-BAR": ("Trading Price Action Trading Ranges", (102, 103, 104)),
    "BB-RNG-19-DUELING-LINES": ("Trading Price Action Trading Ranges", (129, 130)),
    "BB-RNG-20-HEAD-SHOULDERS-AS-RANGE": ("Trading Price Action Trading Ranges", (131, 132)),
    "BB-RNG-23-TRIANGLE": ("Trading Price Action Trading Ranges", (147, 148)),
    "BB-REV-06-EXPANDING-TRIANGLE": ("Trading Price Action Reversals", (181, 182, 183)),
    "BB-REV-08-DOUBLE-BOTTOM-PULLBACK": ("Trading Price Action Reversals", (217, 218, 219)),
    "BB-REV-08-DOUBLE-TOP-PULLBACK": ("Trading Price Action Reversals", (217, 218, 224)),
    "BB-REV-09-FAILURES": ("Trading Price Action Reversals", (225, 226, 227)),
    "BB-REV-09-MEASURED-MOVE-FAILURE": ("Trading Price Action Reversals", (225, 226)),
    "BB-REV-09-MINOR-REVERSAL": ("Trading Price Action Reversals", (226, 227)),
    "BB-TRD-23-SMALL-PULLBACK-TREND": ("Trading Price Action Trends", (383, 401)),
    "BB-TRD-23-TREND-FROM-OPEN": ("Trading Price Action Trends", (383, 401)),
    "BB-TRD-24-REVERSAL-DAY": ("Trading Price Action Trends", (415, 420)),
    "BB-TRD-25-TREND-RESUMPTION-DAY": ("Trading Price Action Trends", (423, 430)),
    "BB-TRD-TREND-RESUMPTION": ("Trading Price Action Trends", (319, 321, 423, 430)),
    "BB-TRD-26-STAIRS-BROAD-CHANNEL": ("Trading Price Action Trends", (431, 436)),
    "BB-TRD-26-SHRINKING-STAIRS": ("Trading Price Action Trends", (431, 432, 436)),
    "BB-REV-19-OPENING-REVERSAL": ("Trading Price Action Reversals", (373, 393)),
    "BB-REV-20-GAP-OPENING": ("Trading Price Action Reversals", (395, 399)),
    "BB-TRD-16-MICRO-CHANNEL": ("Trading Price Action Trends", (249, 260)),
    "BB-TRD-22-TRENDING-RANGE": ("Trading Price Action Trends", (359, 382)),
    "BB-REV-10-HUGE-VOLUME-DAILY": ("Trading Price Action Reversals", (257, 262)),
})



_REVERSAL_OUTCOME_FAMILIES = frozenset({
    "FAILED_BREAKOUT",
    "FAILED_FAILURE",
    "MAJOR_TREND_REVERSAL",
    "WEDGE_REVERSAL",
    "CLIMACTIC_REVERSAL",
    "FINAL_FLAG_REVERSAL",
    "DOUBLE_TOP_BOTTOM_REVERSAL",
})


@dataclass(frozen=True, slots=True)
class _CanonicalRangeTargetContext:
    """WAVE_18 view over an already-canonicalized WAVE_11 range identity."""

    range_id: str
    low: Decimal
    high: Decimal
    origin_index: int
    end_index: int

    @property
    def width(self) -> Decimal:
        return self.high - self.low




class BrooksTrilogyFullCoreEngine:
    # V5: BOOKS_NOTES_V5 context contracts, structural targets, and stop decision tree.
    engine_version = "brooks-trilogy-full-core-v5-context-structural"
    rule_set_version = "brooks-trilogy-full-source-catalog-v6"

    def __init__(self, *, policy: BrooksFullCorePolicy | None = None) -> None:
        self.policy = policy or BrooksFullCorePolicy()

    async def evaluate(self, snapshot: MarketSnapshot) -> BrooksEngineResult:
        policy = self.policy
        if len(snapshot.candles) < policy.context.context_window_bars:
            return self._no_signal(("Insufficient closed candles for Brooks full-core context.",))

        context = assess_books_context(snapshot, policy=policy.context)
        advanced = assess_advanced_context(snapshot, policy=policy)
        market_context = build_market_context(snapshot, policy=policy)
        scan = scan_full_brooks_patterns(snapshot, context, policy, market_context)

        # V5 invariant: only proven context contracts can trade. DEFERRED is fail-closed.
        eligible = tuple(
            candidate
            for candidate in scan.candidates
            if self._context_contract_status(candidate, context, market_context)[0] == "PASS"
            and not self._barbwire_stop_entry_veto(snapshot, candidate)
        )
        rejected_count = len(scan.candidates) - len(eligible)

        evidence = list(self._context_evidence(context, advanced, snapshot=snapshot))
        evidence.extend(self._observation_evidence(scan.observations, context))
        for candidate in eligible:
            evidence.extend(self._candidate_evidence(candidate, context))

        chosen = self._choose_candidate(eligible, context, advanced, market_context)
        if chosen is None:
            reasoning = [
                f"Brooks full-core context={context.regime}, Always-In={context.always_in}.",
                "No mature source-family setup exists on the final closed bar.",
            ]
            if rejected_count:
                reasoning.append(
                    "Canonical context contract rejected "
                    f"{rejected_count} incompatible candidate(s)."
                )
            return self._no_signal(
                tuple(reasoning),
                evidence=tuple(evidence),
                rule_ids=tuple(dict.fromkeys(e.rule_id for e in evidence)),
            )

        probability_assessment = assess_higher_probability(chosen, context, advanced)
        reasoning = (
            f"Detected {chosen.setup_type} from Brooks family {chosen.family}.",
            f"Context={context.regime}; structure={context.structure_direction}; Always-In={context.always_in}.",
            f"Source-relative probability band={probability_assessment.band.value}; "
            + "; ".join(probability_assessment.reasons),
            "Independent reasons: " + "; ".join(chosen.reasons),
        )

        if not policy.enable_trade_decisions:
            return self._no_signal(
                reasoning + ("Autonomous execution is disabled; detector output is exposed via setup_type/evidence.",),
                setup_type=chosen.setup_type,
                evidence=tuple(evidence),
                rule_ids=tuple(dict.fromkeys(e.rule_id for e in evidence)),
            )

        geometry = self._execution_geometry_with_identity(
            snapshot,
            chosen,
            advanced,
            context=context,
            market_context=market_context,
            failure_observations=scan.observations,
        )
        (
            entry,
            stop,
            targets,
            stop_basis,
            target_basis,
            target_source_identities,
            stop_source_identity,
        ) = geometry
        if not targets:
            return self._no_signal(
                reasoning + (
                    "No valid structural target with sufficient room exists; fixed-R fallback is forbidden.",
                ),
                setup_type=chosen.setup_type,
                evidence=tuple(evidence),
                rule_ids=tuple(dict.fromkeys(e.rule_id for e in evidence)),
            )
        target_plan_lifecycle = self._target_plan_lifecycle(
            snapshot,
            chosen,
            context=context,
            market_context=market_context,
            target_source_identities=target_source_identities,
            stop_source_identity=stop_source_identity,
        )
        reversal_outcome_context = self._reversal_outcome_context(
            chosen,
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            context=context,
            target_source_identities=target_source_identities,
            stop_source_identity=stop_source_identity,
            target_plan_lifecycle=target_plan_lifecycle,
        )
        entry_intent = self._entry_execution_intent(
            chosen,
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
        )
        if reversal_outcome_context is not None:
            evidence.append(BrooksRuleEvidence(
                rule_id=REVERSAL_OUTCOME_RULE_ID,
                status="PASS",
                source_pages=(),
                evidence=(
                    ("context_id", reversal_outcome_context.context_id),
                    ("reversal_origin_id", reversal_outcome_context.reversal_origin_id),
                    ("direction", reversal_outcome_context.direction),
                    ("state", reversal_outcome_context.state),
                    ("evaluated_index", str(reversal_outcome_context.evaluated_index)),
                    ("available_at_index", str(reversal_outcome_context.available_at_index)),
                    ("target_source_ids", "|".join(reversal_outcome_context.target_source_ids)),
                    ("initial_stop_source_id", reversal_outcome_context.initial_stop_source_id),
                    ("target_plan_id", reversal_outcome_context.target_plan_id),
                    ("target_plan_state", reversal_outcome_context.target_plan_state),
                    ("trade_eligible", "false"),
                ),
            ))
        potential_bar = snapshot.candles[chosen.signal_index]
        setup_identity_id = f"CH4:SETUP:{entry_intent.economic_opportunity_id}"
        potential_signal_bar_identity_id = (
            f"CH4:POTENTIAL:{snapshot.symbol}:{snapshot.timeframe}:"
            f"{potential_bar.open_time.isoformat()}:{chosen.signal_index}"
        )
        evidence.append(BrooksRuleEvidence(
            rule_id="BB-RNG-29-SIGNAL-BAR-STOP",
            status="PASS",
            source_pages=(202, 203, 204),
            evidence=(
                ("setup_type", chosen.setup_type),
                ("direction", chosen.direction),
                ("stop_basis", stop_basis),
                ("volatility_scaled_buffer", "true"),
                ("entry_method", entry_intent.entry_method),
                ("entry_trigger_semantic", entry_intent.entry_trigger_semantic),
                ("economic_opportunity_id", entry_intent.economic_opportunity_id),
                ("chapter4_setup_identity_id", setup_identity_id),
                ("chapter4_signal_bar_state", "POTENTIAL_SIGNAL_BAR"),
                (
                    "chapter4_potential_signal_bar_identity_id",
                    potential_signal_bar_identity_id,
                ),
                ("chapter4_potential_signal_bar_index", str(chosen.signal_index)),
                (
                    "chapter4_potential_signal_bar_open_time",
                    potential_bar.open_time.isoformat(),
                ),
                (
                    "chapter4_potential_signal_bar_close_time",
                    potential_bar.close_time.isoformat(),
                ),
                (
                    "entry_intent_confirmation_scope",
                    "PRE_FILL_ENTRY_METHOD_OR_PATTERN_CONFIRMATION",
                ),
                ("entry_intent_confirmation_state", entry_intent.confirmation_state),
            ),
        ))
        evidence.append(BrooksRuleEvidence(
            rule_id="ENG-V5-STRUCTURAL-TARGET",
            status="PASS",
            source_pages=(),
            evidence=(
                ("setup_type", chosen.setup_type),
                ("direction", chosen.direction),
                ("target_basis", target_basis),
                ("fixed_r_fallback", "false"),
            ),
        ))
        return BrooksEngineResult(
            decision=chosen.direction,
            entry_price=entry,
            stop_loss=stop,
            targets=targets,
            setup_type=chosen.setup_type,
            reasoning=reasoning + (
                f"V5 stop decision tree basis={stop_basis}.",
                f"Targets come from chart structure/magnets: {target_basis}.",
            ),
            rule_ids=tuple(dict.fromkeys(e.rule_id for e in evidence)),
            failed_rules=(),
            rule_evidence=tuple(evidence),
            engine_version=self.engine_version,
            rule_set_version=self.rule_set_version,
            configuration_version=policy.configuration_version,
            target_source_identities=target_source_identities,
            stop_source_identity=stop_source_identity,
            target_plan_lifecycle=target_plan_lifecycle,
            reversal_outcome_context=reversal_outcome_context,
        )

    def _choose_candidate(self, candidates, context, advanced=None, market_context=None):
        if not candidates:
            return None

        compatible = [
            candidate
            for candidate in candidates
            if self._context_contract_status(candidate, context, market_context)[0] == "PASS"
        ]
        if not compatible:
            return None
        band_rank = {
            ProbabilityBand.HIGHER: 0,
            ProbabilityBand.NORMAL: 1,
            ProbabilityBand.LOWER: 2,
        }
        return sorted(
            compatible,
            key=lambda c: (
                band_rank[assess_higher_probability(c, context, advanced).band],
                c.priority,
                -c.signal_index,
                c.setup_type,
            ),
        )[0]

    def _barbwire_stop_entry_veto(
        self,
        snapshot: MarketSnapshot,
        candidate: BrooksPatternCandidate,
    ) -> bool:
        """BROOKS-GAP-027/028: suppress weak stop entries using canonical subtype identity.

        TTR/barbwire identity is composed from WAVE_02 range evidence. Confirmed
        decisive breakout/follow-through remains a later breakout state, not an
        automatic entry generated by the range subtype itself.
        """
        if candidate.family != "BREAKOUT":
            return False
        reason_set = set(candidate.reasons)
        decisive_breakout = (
            "strong_directional_breakout_bar" in reason_set
            and "close_beyond_causal_swing_level" in reason_set
        )
        explicit_follow_through = {
            "two_consecutive_strong_bars_beyond_breakout_level",
            "breakout_follow_through_confirmed",
        }.issubset(reason_set)
        if decisive_breakout or explicit_follow_through:
            return False

        length = self.policy.barbwire_veto_window_bars  # ENGINEERING_SEARCH_POLICY
        prior = tuple(snapshot.candles[-(length + 1):-1])
        if len(prior) < 3:
            return True
        ttr = classify_tight_trading_range(prior, self.policy.context)
        barbwire = classify_barbwire_identity(prior, self.policy.context)
        return bool(
            (ttr is not None and ttr.is_tight)
            or (barbwire is not None and barbwire.is_barbwire)
        )

    def _context_contract_status(self, candidate: BrooksPatternCandidate, context, market_context=None):
        """Return a fail-closed V5 context contract (BOOKS_NOTES_V5 PHASE/TREND/MTR).

        PASS means every context dimension needed by the family is evidenced now.
        DEFERRED is deliberately never tradeable.
        """
        requirement = candidate.context_required
        metadata = dict(candidate.metadata)
        regime_direction = {
            "BULL_TREND": "LONG",
            "BEAR_TREND": "SHORT",
        }.get(context.regime)
        opposed_always_in = (
            context.always_in in {"LONG", "SHORT"}
            and context.always_in != candidate.direction
        )

        if requirement in {"BULL_TREND", "BEAR_TREND"}:
            required_direction = "LONG" if requirement == "BULL_TREND" else "SHORT"
            if (
                context.regime != requirement
                or context.always_in != required_direction
                or candidate.direction != required_direction
            ):
                return "REJECT", "exact_trend_and_always_in_context_mismatch"
            return "PASS", "exact_trend_and_always_in_context"

        if requirement == "TRADING_RANGE":
            if context.regime != "TRADING_RANGE" or market_context is None:
                return "REJECT", "trading_range_required"
            if candidate.family == "TRADING_RANGE_FADE":
                expected = "AT_LOWER_RANGE_EDGE" if candidate.direction == "LONG" else "AT_UPPER_RANGE_EDGE"
                if metadata.get("range_edge_state") != expected:
                    return "REJECT", "canonical_range_edge_missing"
                if metadata.get("range_subtype") != "BROAD_TRADING_RANGE":
                    return "REJECT", "tight_or_generic_range_has_insufficient_room"
                return "PASS", "broad_range_canonical_edge_context"
            return "PASS", "trading_range_context"

        if requirement in {"BREAKOUT_OR_TREND", "BREAKOUT_RESUMPTION"}:
            if opposed_always_in and regime_direction is not None:
                return "REJECT", "countertrend_against_established_always_in"
            if candidate.family == "BREAKOUT":
                if market_context is not None and market_context.local_breakout_relation in {
                    "LOCAL_BREAKOUT_INSIDE_ENCLOSING_RANGE",
                    "TWO_SIDED_LOCAL_BREAKOUT_ATTEMPT",
                }:
                    return "REJECT", "local_breakout_remains_inside_enclosing_range"
                reason_set = set(candidate.reasons)
                decisive = "strong_directional_breakout_bar" in reason_set
                follow_through = "breakout_follow_through_confirmed" in reason_set
                # BROOKS-GAP-004: two strong bars remain stronger follow-through
                # evidence, but are not a universal breakout prerequisite.  A trade
                # candidate must still be a decisive strong close beyond a causal
                # level; wick-only attempts never carry these candidate reasons.
                if context.breakout_direction != candidate.direction or not (decisive or follow_through):
                    return "REJECT", "breakout_context_not_confirmed"
            if (
                requirement == "BREAKOUT_RESUMPTION"
                and context.breakout_direction != "UNRESOLVED"
                and candidate.direction != context.breakout_direction
            ):
                return "REJECT", "breakout_resumption_direction_mismatch"
            return "PASS", "breakout_context_confirmed"

        if requirement == "RANGE_OR_FAILED_BREAKOUT":
            if candidate.family != "FAILED_BREAKOUT":
                return "REJECT", "failed_breakout_evidence_required"
            if opposed_always_in and regime_direction is not None:
                return "REJECT", "failed_breakout_against_strong_always_in"
            return "PASS", "failed_breakout_not_opposed_by_strong_trend"

        if requirement == "REVERSAL_MATURITY":
            # Brooks' hard MTR sequence is prior trend -> meaningful channel/trend-line
            # break -> test of the old extreme -> reversal setup.  EMA interaction is
            # useful supporting evidence but is not a universal prerequisite.
            witnesses = (
                "prior_trend", "trend_line_break",
                "extreme_retest", "second_reversal",
            )
            if all(metadata.get(key) == "true" for key in witnesses):
                return "PASS", "source_mtr_sequence_confirmed"
            return "REJECT", "mtr_witness_missing"

        if requirement in {"REVERSAL_OR_RANGE_EXTREME", "TREND_EXTREME_OR_RANGE_EXTREME"}:
            if market_context is None or opposed_always_in:
                return "REJECT", "reversal_against_unbroken_always_in"
            valid_locations = (
                {"AT_SUPPORT", "BELOW_SUPPORT"}
                if candidate.direction == "LONG"
                else {"AT_RESISTANCE", "ABOVE_RESISTANCE"}
            )
            if market_context.location not in valid_locations:
                return "REJECT", "reversal_not_at_structural_extreme"
            if context.regime not in {"TRADING_RANGE", "TRANSITION", "AMBIGUOUS"}:
                return "REJECT", "mature_reversal_or_range_context_required"
            return "PASS", "reversal_at_proven_extreme"

        if requirement == "CLIMAX_AT_EXTREME":
            if (
                metadata.get("climax_confirmed") == "true"
                and metadata.get("extreme_confirmed") == "true"
                and not opposed_always_in
            ):
                return "PASS", "climax_and_extreme_confirmed"
            return "REJECT", "climax_context_incomplete"

        if requirement == "ACTIVE_LATE_TREND_FINAL_FLAG":
            if (
                metadata.get("active_trend") == "true"
                and metadata.get("final_flag_id")
                and metadata.get("trend_episode_id")
            ):
                return "PASS", "active_final_flag_origin_and_trend_episode_confirmed"
            return "REJECT", "active_final_flag_identity_missing"

        if requirement == "LATE_TREND_TWO_SIDED":
            if (
                metadata.get("late_trend") == "true"
                and metadata.get("two_sided_flag") == "true"
                and not opposed_always_in
            ):
                return "PASS", "late_trend_two_sided_flag_confirmed"
            return "REJECT", "final_flag_context_incomplete"

        return "REJECT", f"unmapped_context_requirement:{requirement}"

    def _context_evidence(
        self,
        context,
        advanced=None,
        *,
        snapshot: MarketSnapshot | None = None,
    ):
        metrics = context.metrics
        chapter4_one_bar_evidence = ()
        if snapshot is not None and snapshot.candles:
            one_bar = snapshot.candles[-1]
            chapter4_one_bar_evidence = (
                ("chapter4_one_bar_range_state", "ONE_BAR_RANGE_VIEW"),
                ("chapter4_one_bar_index", str(len(snapshot.candles) - 1)),
                ("chapter4_one_bar_open_time", one_bar.open_time.isoformat()),
                ("chapter4_one_bar_close_time", one_bar.close_time.isoformat()),
                ("chapter4_one_bar_high", str(one_bar.high)),
                ("chapter4_one_bar_low", str(one_bar.low)),
                ("chapter4_long_breakout_potential", "ABOVE_PRIOR_HIGH"),
                ("chapter4_short_breakout_potential", "BELOW_PRIOR_LOW"),
                ("chapter4_short_fade_potential", "AT_OR_ABOVE_PRIOR_HIGH"),
                ("chapter4_long_fade_potential", "AT_OR_BELOW_PRIOR_LOW"),
                ("chapter4_one_bar_trade_eligible", "false"),
                ("chapter4_established_range_identity", "false"),
            )
        chapter5_evidence = ()
        if snapshot is not None and snapshot.candles:
            chapter5_evidence = tuple(
                (f"chapter5_{label}_{name}", value)
                for label, direction in (("bull", "LONG"), ("bear", "SHORT"))
                for name, value in chapter5_reversal_diagnostic(
                    snapshot.candles, direction=direction
                )
            )
        chapter2 = getattr(context, "chapter2_bar_context", None)
        chapter2_evidence = ()
        if chapter2 is not None:
            chapter2_evidence = (
                ("chapter2_evaluated_index", str(chapter2.evaluated_index)),
                ("chapter2_bar_state", chapter2.bar_state),
                ("chapter2_direction", chapter2.direction),
                ("chapter2_body_size", str(chapter2.body_size)),
                ("chapter2_bar_range", str(chapter2.bar_range)),
                ("chapter2_body_fraction", str(chapter2.body_fraction)),
                ("chapter2_open_location", str(chapter2.open_location)),
                ("chapter2_close_location", str(chapter2.close_location)),
                ("chapter2_upper_tail_fraction", str(chapter2.upper_tail_fraction)),
                ("chapter2_lower_tail_fraction", str(chapter2.lower_tail_fraction)),
                (
                    "chapter2_recent_median_body",
                    "none"
                    if chapter2.recent_median_body is None
                    else str(chapter2.recent_median_body),
                ),
                (
                    "chapter2_relative_body_multiple",
                    "none"
                    if chapter2.relative_body_multiple is None
                    else str(chapter2.relative_body_multiple),
                ),
                (
                    "chapter2_body_at_or_above_recent_median",
                    "true" if chapter2.body_at_or_above_recent_median else "false",
                ),
                (
                    "chapter2_strong_geometry_proxy",
                    "true" if chapter2.strong_geometry_proxy else "false",
                ),
                (
                    "chapter2_directional_prior_close_count",
                    str(chapter2.directional_prior_close_count),
                ),
                (
                    "chapter2_directional_prior_extreme_count",
                    str(chapter2.directional_prior_extreme_count),
                ),
                (
                    "chapter2_directional_prior_extreme_close_count",
                    str(chapter2.directional_prior_extreme_close_count),
                ),
                ("chapter2_trending_doji_direction", chapter2.trending_doji_direction),
                ("chapter2_trending_doji_run_length", str(chapter2.trending_doji_run_length)),
                ("chapter2_bull_body_count", str(chapter2.bull_body_count)),
                ("chapter2_bear_body_count", str(chapter2.bear_body_count)),
                ("chapter2_bull_body_total", str(chapter2.bull_body_total)),
                ("chapter2_bear_body_total", str(chapter2.bear_body_total)),
                (
                    "chapter2_lower_tail_fraction_total",
                    str(chapter2.lower_tail_fraction_total),
                ),
                (
                    "chapter2_upper_tail_fraction_total",
                    str(chapter2.upper_tail_fraction_total),
                ),
                ("chapter2_body_pressure_direction", chapter2.pressure_direction),
                ("chapter2_climax_direction", chapter2.climax_direction),
                ("chapter2_climax_run_length", str(chapter2.climax_run_length)),
                (
                    "chapter2_climax_body_progression",
                    chapter2.climax_body_progression,
                ),
                ("chapter2_climax_state", chapter2.climax_state),
                (
                    "chapter2_climax_pause_index",
                    "none"
                    if chapter2.climax_pause_index is None
                    else str(chapter2.climax_pause_index),
                ),
                (
                    "chapter2_climax_pause_kind",
                    "none"
                    if chapter2.climax_pause_kind is None
                    else chapter2.climax_pause_kind,
                ),
                ("chapter2_semantic_role", "CONTEXT_ONLY_NO_DIRECT_ENTRY"),
            )
        items = [
            BrooksRuleEvidence(
                rule_id="BB-TRD-19-TREND-STRENGTH",
                status="PASS" if context.regime in {"BULL_TREND", "BEAR_TREND"} else "AMBIGUOUS",
                source_pages=(
                    59, 60, 61, 62, 63, 64, 65, 68, 69, 71, 72, 74, 75,
                    337, 338, 339,
                ),
                evidence=(
                    ("source_book", "Trading Price Action Trends"),
                    ("regime", context.regime),
                    ("structure_direction", context.structure_direction),
                    ("directional_bar_fraction", str(metrics.directional_bar_fraction)),
                    ("bar_overlap_rate", str(metrics.bar_overlap_rate)),
                    ("adjusted_displacement", str(metrics.adjusted_displacement)),
                    ("numeric_measurements", "ENGINEERING_POLICY_FOR_QUALITATIVE_SOURCE_RULE"),
                ) + chapter2_evidence,
                confidence_components=self._weight_components("BB-TRD-19-TREND-STRENGTH"),
            ),
            BrooksRuleEvidence(
                rule_id="BB-REV-15-ALWAYS-IN",
                status="PASS" if context.always_in != "UNRESOLVED" else "AMBIGUOUS",
                source_pages=(321, 322),
                evidence=(
                    ("source_book", "Trading Price Action Reversals"),
                    ("always_in", context.always_in),
                    ("breakout_direction", context.breakout_direction),
                    ("breakout_streak", str(context.breakout_streak)),
                    ("context_reason", context.reason),
                ),
                confidence_components=self._weight_components("BB-REV-15-ALWAYS-IN"),
            ),
        ]
        if advanced is None:
            return tuple(items)

        items.append(BrooksRuleEvidence(
            rule_id="BB-V5-MARKET-PHASE",
            status="PASS",
            source_pages=(85, 86, 337, 338, 339),
            evidence=(
                ("source_book", "Trading Price Action Trends"),
                ("phase", advanced.market_phase),
                ("direction", advanced.phase_direction),
                ("ordering", "PHASE_BEFORE_PATTERN"),
            ) + chapter4_one_bar_evidence + chapter5_evidence,
        ))
        for rule_id, direction, pages, label in (
            ("BB-TRD-TIGHT-CHANNEL", advanced.tight_channel_direction, (24, 250, 258, 279), "tight_channel"),
            ("BB-TRD-SPIKE-CHANNEL", advanced.spike_channel_direction, (250, 258, 284), "spike_channel"),
        ):
            items.append(BrooksRuleEvidence(
                rule_id=rule_id,
                status="PASS" if direction != "UNRESOLVED" else "NOT_APPLICABLE",
                source_pages=pages,
                evidence=(("source_book", "Trading Price Action Trends"), (label, direction)),
                confidence_components=self._weight_components(rule_id),
            ))

        items.append(BrooksRuleEvidence(
            rule_id="BB-TRD-MEASURED-MOVE",
            status="PASS" if advanced.measured_move_target is not None else "NOT_APPLICABLE",
            source_pages=(102, 165, 170, 172),
            evidence=(
                ("source_book", "Trading Price Action Trends"),
                ("direction", advanced.measured_move_direction),
                ("target", str(advanced.measured_move_target) if advanced.measured_move_target is not None else "UNRESOLVED"),
                ("role", "CONTEXTUAL_MAGNET_NOT_UNIVERSAL_TARGET"),
            ),
            confidence_components=self._weight_components("BB-TRD-MEASURED-MOVE"),
        ))
        items.append(BrooksRuleEvidence(
            rule_id="BB-TRD-OPENING-REVERSAL",
            status="NOT_APPLICABLE",
            source_pages=(19, 149, 431),
            evidence=(("reason", "24_7_crypto_snapshot_has_no_explicit_session_open_anchor"),),
            confidence_components=self._weight_components("BB-TRD-OPENING-REVERSAL"),
        ))
        return tuple(items)

    @staticmethod
    def _weight_components(rule_id: str):
        profile = rule_profile(rule_id)
        if profile is None:
            return (("weight_class", "UNCLASSIFIED"), ("weight", "0"))
        return (
            ("weight_class", profile.strength.value),
            ("weight", str(profile.weight)),
            ("quality_dimension", profile.dimension.value),
        )

    def _observation_evidence(self, observations, context):
        out = []
        for item in observations:
            status = "NOT_APPLICABLE" if item.role.startswith("NOT_APPLICABLE") else "PASS"
            for rule_id in item.source_rule_ids:
                book, pages = _RULE_SOURCE.get(rule_id, ("Brooks trilogy", ()))
                out.append(BrooksRuleEvidence(
                    rule_id=rule_id, status=status, source_pages=pages,
                    evidence=(
                        ("source_book", book), ("pattern_id", item.pattern_id),
                        ("pattern_name", item.pattern_name), ("role", item.role),
                        ("direction", item.direction), ("context", context.regime),
                        ("signal_index", str(item.signal_index)),
                    ) + item.metadata,
                    confidence_components=self._weight_components(rule_id),
                ))
        return tuple(out)

    def _candidate_evidence(self, candidate: BrooksPatternCandidate, context):
        out = []
        for rule_id in candidate.source_rule_ids:
            book, pages = _RULE_SOURCE.get(rule_id, ("Brooks trilogy", ()))
            out.append(
                BrooksRuleEvidence(
                    rule_id=rule_id,
                    status="PASS",
                    source_pages=pages,
                    evidence=(
                        ("source_book", book),
                        ("family", candidate.family),
                        ("setup_type", candidate.setup_type),
                        ("direction", candidate.direction),
                        ("taxonomy", candidate.taxonomy),
                        ("context", context.regime),
                        ("signal_index", str(candidate.signal_index)),
                        ("reasons", " | ".join(candidate.reasons)),
                    ) + candidate.metadata,
                    confidence_components=self._weight_components(rule_id),
                )
            )
        return tuple(out)

    def _no_signal(
        self,
        reasoning: tuple[str, ...],
        *,
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
            engine_version=self.engine_version,
            rule_set_version=self.rule_set_version,
            configuration_version=self.policy.configuration_version,
        )

    def _entry_execution_intent(
        self,
        candidate: BrooksPatternCandidate,
        *,
        symbol: str | None = None,
        timeframe: str | None = None,
    ) -> EntryExecutionIntent:
        metadata = dict(candidate.metadata)
        method = metadata.get("entry_method", "STOP_TRIGGER_CONFIRMATION")
        semantic = metadata.get("entry_trigger_semantic", "SIGNAL_BAR_STOP_TRIGGER")
        reference = metadata.get("entry_reference_price")
        reference_price = Decimal(reference) if reference not in {None, ""} else None
        economic_id = metadata.get(
            "economic_opportunity_id",
            f"{candidate.family}:{candidate.setup_type}:{candidate.direction}:{candidate.signal_index}",
        )
        canonical_symbol = str(symbol or getattr(candidate, "symbol", "") or "").strip().upper()
        canonical_timeframe = str(
            timeframe or getattr(candidate, "timeframe", "") or ""
        ).strip()
        if canonical_symbol and not economic_id.startswith(f"{canonical_symbol}:"):
            economic_id = f"{canonical_symbol}:{economic_id}"
        if canonical_timeframe:
            if canonical_symbol and economic_id.startswith(f"{canonical_symbol}:"):
                remainder = economic_id[len(canonical_symbol) + 1 :]
                if not remainder.startswith(f"{canonical_timeframe}:"):
                    economic_id = f"{canonical_symbol}:{canonical_timeframe}:{remainder}"
            elif not economic_id.startswith(f"{canonical_timeframe}:"):
                economic_id = f"{canonical_timeframe}:{economic_id}"
        state = metadata.get(
            "entry_confirmation_state",
            "CONFIRMED" if method == "STOP_TRIGGER_CONFIRMATION" else "ANTICIPATORY_UNCONFIRMED",
        )
        return EntryExecutionIntent(
            method, semantic, reference_price, economic_id,
            method in {"LIMIT_OR_MARKET_ANTICIPATION","MARKET_OR_LIMIT_ANTICIPATION"},
            state,
        )

    def _canonical_range_target_context(
        self,
        snapshot: MarketSnapshot,
        candidate: BrooksPatternCandidate,
    ) -> _CanonicalRangeTargetContext | None:
        """Consume WAVE_11 range identity; bounded history is engineering search policy."""
        metadata = dict(candidate.metadata)
        if metadata.get("range_id") and metadata.get("range_low") and metadata.get("range_high"):
            low = Decimal(metadata["range_low"])
            high = Decimal(metadata["range_high"])
            if high > low:
                parts = metadata["range_id"].split(":")
                try:
                    origin = int(parts[-2])
                    end = int(parts[-1])
                except (ValueError, IndexError):
                    origin = max(0, candidate.signal_index - self.policy.range_window_bars)
                    end = max(origin, candidate.signal_index - 1)
                return _CanonicalRangeTargetContext(
                    metadata["range_id"], low, high, origin, end
                )

        candles = snapshot.candles
        metadata_breakout = metadata.get("breakout_index")
        try:
            breakout_index = int(metadata_breakout) if metadata_breakout not in {None, ""} else candidate.signal_index
        except ValueError:
            breakout_index = candidate.signal_index
        end = (
            breakout_index - 1
            if candidate.family in {"BREAKOUT", "BREAKOUT_PULLBACK", "FAILED_BREAKOUT", "FAILED_FAILURE"}
            else candidate.signal_index - 1
        )
        if end < 2:
            return None
        origin = max(0, end - self.policy.range_window_bars + 1)  # ENGINEERING_SEARCH_POLICY
        broad = classify_broad_trading_range(
            candles,
            self.policy.context,
            origin_index=origin,
            evaluated_index=end,
        )
        if broad is None or not broad.is_broad:
            return None
        return _CanonicalRangeTargetContext(
            broad.range_id, broad.low, broad.high, broad.origin_index, broad.end_index
        )

    def _range_breakout_lifecycle(
        self,
        snapshot: MarketSnapshot,
        candidate: BrooksPatternCandidate,
        range_context: _CanonicalRangeTargetContext | None,
    ):
        """Reuse WAVE_10 breakout lifecycle for WAVE_18 range-target semantics."""
        if range_context is None:
            return None
        metadata = dict(candidate.metadata)
        try:
            breakout_index = int(metadata.get("breakout_index", candidate.signal_index))
        except (TypeError, ValueError):
            breakout_index = candidate.signal_index
        if not (0 <= breakout_index <= candidate.signal_index < len(snapshot.candles)):
            return None
        breakout_direction = (
            ("SHORT" if candidate.direction == "LONG" else "LONG")
            if candidate.family == "FAILED_BREAKOUT"
            else candidate.direction
        )
        level = range_context.high if breakout_direction == "LONG" else range_context.low
        bar = snapshot.candles[breakout_index]
        strong = (
            is_strong_bull_bar(bar, self.policy.context)
            if breakout_direction == "LONG"
            else is_strong_bear_bar(bar, self.policy.context)
        )
        origin = build_breakout_attempt_identity(
            snapshot.candles,
            direction=breakout_direction,
            reference_id=range_context.range_id,
            reference_level=level,
            attempt_index=breakout_index,
            engineering_strong=strong,
        )
        if origin is None or not origin.closed_beyond:
            return None
        lifecycle = classify_breakout_lifecycle(
            snapshot.candles, origin, evaluated_index=candidate.signal_index
        )
        return origin, lifecycle

    def _reversal_outcome_context(
        self,
        candidate: BrooksPatternCandidate,
        *,
        symbol: str | None = None,
        timeframe: str | None = None,
        context,
        target_source_identities: tuple[TargetSourceIdentity, ...],
        stop_source_identity: StopSourceIdentity | None,
        target_plan_lifecycle: TargetPlanLifecycle | None,
    ) -> ReversalOutcomeContext | None:
        """WAVE_19 typed reversal-outcome context; later TM transitions stay causal."""
        if candidate.family not in _REVERSAL_OUTCOME_FAMILIES:
            return None
        if (
            not target_source_identities
            or stop_source_identity is None
            or target_plan_lifecycle is None
        ):
            return None

        regime = str(getattr(context, "regime", "")).upper()
        always_in = str(getattr(context, "always_in", "")).upper()
        if regime == "TRADING_RANGE":
            state = "TRADING_RANGE_OUTCOME"
        elif (
            candidate.direction == "LONG"
            and regime == "BULL_TREND"
            and always_in == "LONG"
        ) or (
            candidate.direction == "SHORT"
            and regime == "BEAR_TREND"
            and always_in == "SHORT"
        ):
            state = "OPPOSITE_TREND_OUTCOME"
        else:
            state = "PENDING_REVERSAL_OUTCOME"

        entry_intent = self._entry_execution_intent(
            candidate,
            symbol=symbol,
            timeframe=timeframe,
        )
        target_source_ids = tuple(dict.fromkeys(
            source.source_id
            for target in target_source_identities
            for source in target.sources
        ))
        return ReversalOutcomeContext(
            context_id=(
                f"REVERSAL_OUTCOME:{entry_intent.economic_opportunity_id}:"
                f"{candidate.signal_index}"
            ),
            reversal_origin_id=entry_intent.economic_opportunity_id,
            direction=candidate.direction,
            state=state,
            evaluated_index=candidate.signal_index,
            available_at_index=candidate.signal_index,
            target_source_ids=target_source_ids,
            initial_stop_source_id=stop_source_identity.source_id,
            target_plan_id=target_plan_lifecycle.plan_id,
            target_plan_state=target_plan_lifecycle.state,
            trade_eligible=False,
        )

    def _target_plan_lifecycle(
        self,
        snapshot: MarketSnapshot,
        candidate: BrooksPatternCandidate,
        *,
        context=None,
        market_context=None,
        target_source_identities: tuple[TargetSourceIdentity, ...] = (),
        stop_source_identity: StopSourceIdentity | None = None,
    ) -> TargetPlanLifecycle:
        """BROOKS-GAP-050 Core target-plan phase only; TM_V6 economics remain external."""
        if context is None:
            context = assess_books_context(snapshot, policy=self.policy.context)
        range_context = self._canonical_range_target_context(snapshot, candidate)
        range_breakout = self._range_breakout_lifecycle(snapshot, candidate, range_context)
        metadata = dict(candidate.metadata)
        breakout_id = metadata.get("breakout_id")
        transition_index = None

        if candidate.family == "TRADING_RANGE_FADE" and range_context is not None:
            state = "RANGE_TRADE"
        elif candidate.family == "FAILED_BREAKOUT" and range_context is not None:
            state = "FAILED_BREAKOUT_TRADE"
        elif candidate.family == "BREAKOUT" and range_breakout is not None:
            state = "BREAKOUT_TRANSITION"
            breakout_id = range_breakout[0].breakout_id
            transition_index = range_breakout[0].attempt_index
        elif candidate.family in {"BREAKOUT_PULLBACK", "FAILED_FAILURE"} and range_breakout is not None:
            state = "TREND_TRADE"
            breakout_id = range_breakout[0].breakout_id
            transition_index = range_breakout[0].attempt_index
        elif context.regime == "TRADING_RANGE" and range_context is not None:
            state = "RANGE_TRADE"
        elif context.regime in {"BULL_TREND", "BEAR_TREND"}:
            state = "TREND_TRADE"
        else:
            state = "REVERSAL_OR_TRANSITION"

        source_ids = tuple(
            source.source_id
            for target in target_source_identities
            for source in target.sources
        )
        return TargetPlanLifecycle(
            plan_id=(
                f"TARGET_PLAN:{candidate.setup_type}:{candidate.direction}:"
                f"{candidate.signal_index}:{range_context.range_id if range_context else 'NO_RANGE'}"
            ),
            state=state,
            direction=candidate.direction,
            evaluated_index=candidate.signal_index,
            range_id=range_context.range_id if range_context else None,
            breakout_id=breakout_id,
            transition_index=transition_index,
            target_source_ids=source_ids,
            initial_stop_source_id=(
                stop_source_identity.source_id if stop_source_identity is not None else None
            ),
            trade_eligible=False,
        )

    def _channel_target_sources(
        self,
        snapshot: MarketSnapshot,
        candidate: BrooksPatternCandidate,
    ) -> list[tuple[Decimal, TargetSourceEvidence, str]]:
        """BROOKS-GAP-022/023 consume WAVE_03 causal trend-channel geometry."""
        candles = snapshot.candles
        metadata = dict(candidate.metadata)
        try:
            breakout_index = int(metadata.get("breakout_index", candidate.signal_index))
        except (TypeError, ValueError):
            breakout_index = candidate.signal_index
        breakout_index = min(max(0, breakout_index), candidate.signal_index)
        prefix = tuple(candles[: breakout_index + 1])
        if len(prefix) < 5:
            return []
        scan = confirm_swings_causally(
            prefix,
            left_bars=self.policy.context.swing_left_bars,
            right_bars=self.policy.context.swing_right_bars,
        )
        trend_direction = "BULL_TREND" if candidate.direction == "LONG" else "BEAR_TREND"
        channel = build_trend_channel_geometry(
            prefix, scan, direction=trend_direction, evaluated_index=breakout_index
        )
        if channel is None:
            return []
        out: list[tuple[Decimal, TargetSourceEvidence, str]] = []
        channel_id = (
            f"CHANNEL:{trend_direction}:"
            f"{channel.trend_line.anchors[0].candle_index}:"
            f"{channel.trend_line.anchors[-1].candle_index}:"
            f"{channel.opposite_channel_line.anchors[0].candle_index}"
        )
        # BROOKS-GAP-023: visible opposite channel side and channel-start identity.
        opposite_level = (
            channel.projected_upper
            if candidate.direction == "LONG"
            else channel.projected_lower
        )
        out.append((
            opposite_level,
            TargetSourceEvidence(
                "TREND_CHANNEL_OPPOSITE_SIDE",
                f"TARGET_SOURCE:{channel_id}:OPPOSITE_SIDE:{breakout_index}",
                channel.trend_line.anchors[0].candle_index,
                breakout_index,
                candidate.direction,
                channel_id,
            ),
            "trend_channel_opposite_side",
        ))
        out.append((
            channel.trend_line.anchors[0].price,
            TargetSourceEvidence(
                "TREND_CHANNEL_START",
                f"TARGET_SOURCE:{channel_id}:START",
                channel.trend_line.anchors[0].candle_index,
                channel.trend_line.anchors[0].confirmed_at_index,
                candidate.direction,
                channel_id,
            ),
            "trend_channel_start",
        ))
        # BROOKS-GAP-022: only an actual causal channel-line close breakout owns this projection.
        if candidate.family in {"BREAKOUT", "BREAKOUT_PULLBACK"}:
            event = classify_channel_boundary_event(
                prefix, channel, evaluated_index=breakout_index
            )
            if event is not None and event.state == "CHANNEL_LINE_BREAK":
                target = (
                    event.boundary_value + channel.width
                    if candidate.direction == "LONG"
                    else event.boundary_value - channel.width
                )
                out.append((
                    target,
                    TargetSourceEvidence(
                        "CHANNEL_BREAKOUT_MEASURED_MOVE",
                        f"TARGET_SOURCE:{channel_id}:BREAKOUT_MM:{breakout_index}",
                        channel.trend_line.anchors[0].candle_index,
                        breakout_index,
                        candidate.direction,
                        channel_id,
                    ),
                    "channel_breakout_measured_move",
                ))
        return out

    def _failed_reversal_target_sources(
        self,
        snapshot: MarketSnapshot,
        candidate: BrooksPatternCandidate,
        tick: Decimal,
        failure_observations=None,
    ) -> list[tuple[Decimal, TargetSourceEvidence, str]]:
        """BROOKS-GAP-047 consumes canonical failure lifecycle observations at T."""
        candles = snapshot.candles
        observations = failure_observations
        if observations is None:
            # Compatibility/direct-call path: reuse the canonical scanner once,
            # never reconstruct a parallel failure detector.
            pctx = assess_books_context(snapshot, policy=self.policy.context)
            observations = scan_full_brooks_patterns(snapshot, pctx, self.policy, None).observations
        out: list[tuple[Decimal, TargetSourceEvidence, str]] = []
        seen: set[str] = set()
        for obs in observations:
            if obs.role != "FAILURE_CONTEXT" or obs.direction != candidate.direction:
                continue
            metadata = dict(obs.metadata)
            if metadata.get("failure_confirmed") != "true":
                continue
            attempt_id = metadata.get("attempt_id")
            raw_signal = metadata.get("origin_signal_index") or metadata.get("signal_index")
            if not attempt_id or raw_signal in {None, "", "none"} or attempt_id in seen:
                continue
            try:
                signal_index = int(raw_signal)
                failure_index = int(metadata.get("failure_index", obs.signal_index))
            except (TypeError, ValueError):
                continue
            if not (0 <= signal_index < len(candles)):
                continue
            if failure_index > candidate.signal_index:
                continue
            seen.add(attempt_id)
            original_direction = "SHORT" if candidate.direction == "LONG" else "LONG"
            signal_bar = candles[signal_index]
            trigger_level = (
                signal_bar.high + tick
                if original_direction == "LONG"
                else signal_bar.low - tick
            )
            common = dict(
                origin_index=signal_index,
                confirmed_at_index=failure_index,
                direction=candidate.direction,
                structure_id=attempt_id,
            )
            out.append((
                trigger_level,
                TargetSourceEvidence(
                    "FAILED_REVERSAL_ENTRY_PRICE",
                    f"TARGET_SOURCE:{attempt_id}:ENTRY",
                    **common,
                ),
                "failed_reversal_entry_price",
            ))
            for side, level in (("HIGH", signal_bar.high), ("LOW", signal_bar.low)):
                out.append((
                    level,
                    TargetSourceEvidence(
                        f"FAILED_REVERSAL_SIGNAL_BAR_{side}",
                        f"TARGET_SOURCE:{attempt_id}:SIGNAL_{side}",
                        **common,
                    ),
                    f"failed_reversal_signal_bar_{side.lower()}",
                ))
        return out

    def _source_target_pool(
        self,
        snapshot: MarketSnapshot,
        candidate: BrooksPatternCandidate,
        *,
        entry: Decimal,
        recent_average_range: Decimal,
        tick: Decimal,
        advanced,
        target_plan: TargetPlanLifecycle,
        failure_observations=None,
    ) -> list[tuple[Decimal, TargetSourceEvidence, str]]:
        """WAVE_18 source-specific target/magnet pool before semantic arbitration."""
        candles = snapshot.candles
        signal_index = candidate.signal_index
        metadata = dict(candidate.metadata)
        out: list[tuple[Decimal, TargetSourceEvidence, str]] = []
        range_context = self._canonical_range_target_context(snapshot, candidate)

        def add(
            level: Decimal,
            source_type: str,
            source_id: str,
            basis: str,
            origin_index: int | None,
            confirmed_at_index: int | None,
            structure_id: str | None = None,
            semantic_classification: str = "SOURCE_SEMANTIC",
        ) -> None:
            out.append((
                level,
                TargetSourceEvidence(
                    source_type,
                    source_id,
                    origin_index,
                    confirmed_at_index,
                    candidate.direction,
                    structure_id,
                    semantic_classification,
                ),
                basis,
            ))

        # Existing range boundary, now tied to the canonical range identity.
        if range_context is not None:
            boundary = range_context.high if candidate.direction == "LONG" else range_context.low
            add(
                boundary,
                "OPPOSITE_RANGE_BOUNDARY",
                f"TARGET_SOURCE:{range_context.range_id}:OPPOSITE:{candidate.direction}",
                "opposite_range_boundary",
                range_context.origin_index,
                range_context.end_index,
                range_context.range_id,
            )
            # BROOKS-GAP-046 canonical midpoint/equilibrium magnet.
            midpoint = (range_context.low + range_context.high) / Decimal("2")
            add(
                midpoint,
                "RANGE_MIDPOINT",
                f"TARGET_SOURCE:{range_context.range_id}:MIDPOINT",
                "range_midpoint",
                range_context.origin_index,
                range_context.end_index,
                range_context.range_id,
            )

        # Existing causal swing objectives remain source-typed.
        swing_scan = confirm_swings_causally(
            tuple(candles[: signal_index + 1]),
            left_bars=self.policy.context.swing_left_bars,
            right_bars=self.policy.context.swing_right_bars,
        )
        wanted = "HIGH" if candidate.direction == "LONG" else "LOW"
        for swing in swing_scan.swings:
            if swing.kind == wanted:
                add(
                    swing.price,
                    "OPPOSING_CAUSAL_SWING",
                    f"TARGET_SOURCE:SWING:{swing.kind}:{swing.candle_index}",
                    "opposing_causal_swing",
                    swing.candle_index,
                    swing.confirmed_at_index,
                    f"SWING:{swing.kind}:{swing.candle_index}",
                )

        # BROOKS-GAP-021 full-spike identity; preserve both valid source anchor variants.
        spike_identity = getattr(advanced, "spike_measured_move_identity", None)
        if spike_identity is not None and spike_identity.direction == candidate.direction:
            add(
                spike_identity.open_close_target,
                "SPIKE_MEASURED_MOVE_OPEN_CLOSE",
                f"TARGET_SOURCE:{spike_identity.spike_id}:OPEN_CLOSE",
                "spike_measured_move_open_close",
                spike_identity.start_index,
                spike_identity.available_at_index,
                spike_identity.spike_id,
            )
            add(
                spike_identity.extreme_target,
                "SPIKE_MEASURED_MOVE_EXTREMES",
                f"TARGET_SOURCE:{spike_identity.spike_id}:EXTREMES",
                "spike_measured_move_extremes",
                spike_identity.start_index,
                spike_identity.available_at_index,
                spike_identity.spike_id,
            )
        elif (
            getattr(advanced, "measured_move_target", None) is not None
            and getattr(advanced, "measured_move_direction", None) == candidate.direction
        ):
            # Compatibility for injected/legacy advanced-context fixtures.
            add(
                advanced.measured_move_target,
                "ACTIVE_MEASURED_MOVE_MAGNET",
                f"TARGET_SOURCE:LEGACY_ADVANCED_MM:{signal_index}",
                "active_measured_move_magnet",
                signal_index,
                signal_index,
                None,
            )

        # BROOKS-GAP-022/023 canonical channel targets/magnets.
        out.extend(self._channel_target_sources(snapshot, candidate))

        # BROOKS-GAP-023 moving-average and breakout/setup test magnets.
        ema = _ema20_values(tuple(candles[: signal_index + 1]))
        if ema:
            add(
                ema[-1],
                "MOVING_AVERAGE_TEST",
                f"TARGET_SOURCE:EMA20:{signal_index}",
                "moving_average_test",
                signal_index,
                signal_index,
                "EMA20",
            )
        if metadata.get("reference_level") not in {None, ""}:
            try:
                ref_index = int(metadata.get("reference_swing_index", signal_index))
            except (TypeError, ValueError):
                ref_index = signal_index
            add(
                Decimal(metadata["reference_level"]),
                "BREAKOUT_TEST_LEVEL",
                f"TARGET_SOURCE:BREAKOUT_TEST:{ref_index}:{metadata['reference_level']}",
                "breakout_test_level",
                ref_index,
                min(signal_index, ref_index),
                f"BREAKOUT_TEST:{ref_index}",
            )
        if metadata.get("old_extreme") not in {None, ""}:
            add(
                Decimal(metadata["old_extreme"]),
                "SETUP_REFERENCE_LEVEL",
                f"TARGET_SOURCE:SETUP_REFERENCE:{candidate.setup_type}:{signal_index}",
                "setup_reference_level",
                signal_index,
                signal_index,
                candidate.setup_type,
            )

        # BROOKS-GAP-047 canonical failed-reversal history.
        out.extend(
            self._failed_reversal_target_sources(
                snapshot, candidate, tick, failure_observations=failure_observations
            )
        )

        # BROOKS-GAP-049: identified-range height only after a successful range breakout.
        range_breakout = self._range_breakout_lifecycle(snapshot, candidate, range_context)
        if range_context is not None and range_breakout is not None:
            origin, lifecycle = range_breakout
            if lifecycle.reentry_index is None and lifecycle.state in {
                "BREAKOUT_ESTABLISHED",
                "FOLLOW_THROUGH_CONFIRMED",
                "BREAKOUT_TEST_HOLDING",
            }:
                target = (
                    range_context.high + range_context.width
                    if origin.direction == "LONG"
                    else range_context.low - range_context.width
                )
                if origin.direction == candidate.direction:
                    add(
                        target,
                        "RANGE_HEIGHT_MEASURED_MOVE",
                        f"TARGET_SOURCE:{range_context.range_id}:HEIGHT_MM:{origin.breakout_id}",
                        "range_height_measured_move",
                        range_context.origin_index,
                        origin.attempt_index,
                        range_context.range_id,
                    )

        # BROOKS-GAP-050: range plans do not silently consume trend-style projections.
        if target_plan.state in {"RANGE_TRADE", "FAILED_BREAKOUT_TRADE"}:
            allowed = {
                "OPPOSITE_RANGE_BOUNDARY",
                "RANGE_MIDPOINT",
                "FAILED_REVERSAL_ENTRY_PRICE",
                "FAILED_REVERSAL_SIGNAL_BAR_HIGH",
                "FAILED_REVERSAL_SIGNAL_BAR_LOW",
                "OPPOSING_CAUSAL_SWING",
                "BREAKOUT_TEST_LEVEL",
            }
            out = [item for item in out if item[1].source_type in allowed]

        minimum_room = (
            recent_average_range
            * self.policy.context.minimum_structural_reward_range_multiple
        )
        out = [
            item for item in out
            if (
                (item[0] - entry if candidate.direction == "LONG" else entry - item[0])
                >= minimum_room
            )
            and (
                item[1].confirmed_at_index is None
                or item[1].confirmed_at_index <= signal_index
            )
        ]

        # Existing generic recent-window projection is engineering fallback only.
        # It cannot displace a source-semantic target and is never called a range MM.
        if not out:
            projection_base = candles[
                max(0, signal_index - self.policy.context.recent_window_bars) : signal_index
            ]
            if projection_base:
                projection_high = max(c.high for c in projection_base)
                projection_low = min(c.low for c in projection_base)
                projection_width = projection_high - projection_low
                if projection_width > 0:
                    level = (
                        projection_high + projection_width
                        if candidate.direction == "LONG"
                        else projection_low - projection_width
                    )
                    room = level - entry if candidate.direction == "LONG" else entry - level
                    if room >= minimum_room:
                        origin = max(0, signal_index - self.policy.context.recent_window_bars)
                        add(
                            level,
                            "RECENT_STRUCTURE_MEASURED_MOVE",
                            f"TARGET_SOURCE:ENGINEERING_RECENT_STRUCTURE:{origin}:{signal_index}",
                            "recent_structure_measured_move",
                            origin,
                            signal_index,
                            f"ENGINEERING_RECENT_STRUCTURE:{origin}:{signal_index}",
                            "ENGINEERING_CLASSIFICATION_POLICY",
                        )
        return out

    @staticmethod
    def _normalize_executable_target(
        level: Decimal,
        *,
        tick: Decimal,
        entry: Decimal,
        direction: str,
    ) -> Decimal:
        """Snap a final target to its exchange tick without overstating reward."""
        if tick <= 0:
            raise ValueError("target tick size must be positive")
        if direction == "LONG":
            normalized = (level / tick).to_integral_value(rounding=ROUND_FLOOR) * tick
            if normalized <= entry:
                raise ValueError("normalized long target must remain above entry")
        elif direction == "SHORT":
            normalized = (level / tick).to_integral_value(rounding=ROUND_CEILING) * tick
            if normalized >= entry:
                raise ValueError("normalized short target must remain below entry")
        else:
            raise ValueError("target direction must be LONG or SHORT")
        return normalized

    def _coalesce_target_identities(
        self,
        entries: list[tuple[Decimal, TargetSourceEvidence, str]],
        *,
        signal_index: int,
    ) -> tuple[tuple[TargetSourceIdentity, ...], dict[str, str]]:
        """Build WAVE_17 typed identities before WAVE_18 semantic arbitration."""
        merged: dict[Decimal, list[TargetSourceEvidence]] = {}
        basis_by_source_id: dict[str, str] = {}
        for level, source, basis in entries:
            bucket = merged.setdefault(level, [])
            if all(existing.source_id != source.source_id for existing in bucket):
                bucket.append(source)
            basis_by_source_id[source.source_id] = basis
        identities = tuple(
            TargetSourceIdentity(
                target_number=number,
                target_price=level,
                sources=tuple(sources),
                available_at_index=signal_index,
                management_role="STRUCTURAL_TARGET",
            )
            for number, (level, sources) in enumerate(merged.items(), start=1)
        )
        return identities, basis_by_source_id

    def _arbitrate_target_identities(
        self,
        identities: tuple[TargetSourceIdentity, ...],
        *,
        entry: Decimal,
        direction: str,
        signal_index: int,
        basis_by_source_id: dict[str, str],
    ) -> tuple[tuple[Decimal, ...], tuple[TargetSourceIdentity, ...], str]:
        """BROOKS-GAP-048 consumes WAVE_17 identity; distance only orders, never discards."""
        ordered = sorted(
            identities,
            key=lambda item: abs(item.target_price - entry),
        )
        final = tuple(
            TargetSourceIdentity(
                target_number=number,
                target_price=item.target_price,
                sources=item.sources,
                available_at_index=signal_index,
                management_role=item.management_role,
            )
            for number, item in enumerate(ordered, start=1)
        )
        targets = tuple(item.target_price for item in final)
        basis = (
            ",".join(
                dict.fromkeys(
                    basis_by_source_id.get(source.source_id, source.source_type.lower())
                    for target in final
                    for source in target.sources
                )
            )
            if final
            else "no_structural_room"
        )
        return targets, final, basis

    def _execution_geometry(
        self,
        snapshot: MarketSnapshot,
        candidate: BrooksPatternCandidate,
        advanced=None,
    ):
        """Compatibility view of approved geometry; WAVE_17 identity is carried separately."""
        legacy_three_tuple = advanced is None
        plan = self._execution_geometry_with_identity(snapshot, candidate, advanced)
        return plan[:3] if legacy_three_tuple else plan[:5]

    def _execution_geometry_with_identity(
        self,
        snapshot: MarketSnapshot,
        candidate: BrooksPatternCandidate,
        advanced=None,
        *,
        context=None,
        market_context=None,
        failure_observations=None,
    ):
        """WAVE_17 identity foundation plus WAVE_18 source-specific target semantics.

        Stop economics remain unchanged. WAVE_18 adds source-faithful target geometry,
        semantic arbitration and Core target-plan phase; later reversal-outcome behavior remains deferred.
        """
        if advanced is None:
            advanced = assess_advanced_context(snapshot, policy=self.policy)
        candles = snapshot.candles
        signal_index = candidate.signal_index
        signal = candles[signal_index]
        signal_range = signal.high - signal.low
        if signal_range <= 0:
            raise ValueError("signal bar range must be positive")

        recent_average_range = average_bar_range(
            candles[:signal_index],
            period=self.policy.context.stop_recent_range_period,
        )
        if recent_average_range <= 0:
            raise ValueError("recent average bar range must be positive")
        tick = self.policy.context.tick_size_for_symbol(snapshot.symbol)
        volatility_buffer = max(
            tick,
            recent_average_range * self.policy.context.stop_volatility_buffer_multiple,
        )
        range_ratio = signal_range / recent_average_range
        metadata = dict(candidate.metadata)
        entry_intent = self._entry_execution_intent(
            candidate,
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
        )

        anchor_indices: list[int] = []
        for key in ("start_index", "breakout_index", "structure_break_index", "reference_swing_index"):
            try:
                anchor_indices.append(int(metadata[key]))
            except (KeyError, TypeError, ValueError):
                pass
        for raw in metadata.get("push_indices", "").split(","):
            try:
                anchor_indices.append(int(raw))
            except ValueError:
                pass
        anchor = min(anchor_indices) if anchor_indices else signal_index
        anchor = max(0, min(anchor, signal_index))
        anchor = max(anchor, signal_index - self.policy.context.pullback_window_bars)
        if candidate.family == "BREAKOUT":
            anchor = signal_index
        setup_bars = candles[anchor : signal_index + 1]

        if candidate.direction == "LONG":
            entry = (
                entry_intent.reference_price
                if entry_intent.entry_method != "STOP_TRIGGER_CONFIRMATION" and entry_intent.reference_price is not None
                else signal.high + tick
            )
            structural_level = min(c.low for c in setup_bars)
            if metadata.get("range_low"):
                structural_level = min(structural_level, Decimal(metadata["range_low"]))
            if metadata.get("old_extreme"):
                structural_level = min(structural_level, Decimal(metadata["old_extreme"]))
            structural_stop = structural_level - volatility_buffer
            risk = entry - structural_stop
            stop_basis = "setup_or_pullback_low_plus_recent_volatility_buffer"
            if range_ratio > self.policy.context.normal_signal_range_max_ratio:
                cap = (entry - signal.low) * self.policy.context.large_signal_money_management_risk_fraction
                if cap > 0:
                    risk = min(risk, cap)
                    stop_basis = "large_signal_money_management_cap"
            elif range_ratio < self.policy.context.normal_signal_range_min_ratio:
                risk = max(
                    risk,
                    recent_average_range * self.policy.context.small_signal_standard_stop_multiple,
                )
                stop_basis = "small_signal_recent_range_floor"
            stop = entry - risk
        else:
            entry = (
                entry_intent.reference_price
                if entry_intent.entry_method != "STOP_TRIGGER_CONFIRMATION" and entry_intent.reference_price is not None
                else signal.low - tick
            )
            structural_level = max(c.high for c in setup_bars)
            if metadata.get("range_high"):
                structural_level = max(structural_level, Decimal(metadata["range_high"]))
            if metadata.get("old_extreme"):
                structural_level = max(structural_level, Decimal(metadata["old_extreme"]))
            structural_stop = structural_level + volatility_buffer
            risk = structural_stop - entry
            stop_basis = "setup_or_pullback_high_plus_recent_volatility_buffer"
            if range_ratio > self.policy.context.normal_signal_range_max_ratio:
                cap = (signal.high - entry) * self.policy.context.large_signal_money_management_risk_fraction
                if cap > 0:
                    risk = min(risk, cap)
                    stop_basis = "large_signal_money_management_cap"
            elif range_ratio < self.policy.context.normal_signal_range_min_ratio:
                risk = max(
                    risk,
                    recent_average_range * self.policy.context.small_signal_standard_stop_multiple,
                )
                stop_basis = "small_signal_recent_range_floor"
            stop = entry + risk
        if risk <= 0:
            raise ValueError("invalid V5 risk geometry")

        if context is None:
            context = assess_books_context(snapshot, policy=self.policy.context)
        target_plan = self._target_plan_lifecycle(
            snapshot,
            candidate,
            context=context,
            market_context=market_context,
        )
        target_entries = self._source_target_pool(
            snapshot,
            candidate,
            entry=entry,
            recent_average_range=recent_average_range,
            tick=tick,
            advanced=advanced,
            target_plan=target_plan,
            failure_observations=failure_observations,
        )
        target_entries = [
            (
                self._normalize_executable_target(
                    level,
                    tick=tick,
                    entry=entry,
                    direction=candidate.direction,
                ),
                source,
                basis,
            )
            for level, source, basis in target_entries
        ]
        preliminary_target_identities, basis_by_source_id = self._coalesce_target_identities(
            target_entries,
            signal_index=signal_index,
        )
        targets, target_source_identities, target_basis = self._arbitrate_target_identities(
            preliminary_target_identities,
            entry=entry,
            direction=candidate.direction,
            signal_index=signal_index,
            basis_by_source_id=basis_by_source_id,
        )
        stop_source_identity = StopSourceIdentity(
            stop_price=stop,
            source_type="INITIAL_PROTECTIVE_STOP",
            source_id=(
                f"STOP_SOURCE:{candidate.setup_type}:{candidate.direction}:"
                f"{signal_index}:{stop_basis}:{anchor}"
            ),
            structural_reference_price=structural_level,
            origin_index=anchor,
            available_at_index=signal_index,
            adjustment_policy=stop_basis.upper(),
            direction=candidate.direction,
        )
        return (
            entry,
            stop,
            targets,
            stop_basis,
            target_basis,
            target_source_identities,
            stop_source_identity,
        )
