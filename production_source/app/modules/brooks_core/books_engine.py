"""Brooks trilogy-grounded H2/L2 continuation engine v2.

This engine intentionally narrows scope to *with-trend H2/L2 continuation setups*.
It does not yet auto-trade trading-range H2/L2 reversals, wedges, major trend
reversals, or climactic reversals. Those concepts are classified so that a
continuation detector does not confuse them with trend pullbacks.

Primary sources:
- Al Brooks, Trading Price Action Trends
- Al Brooks, Trading Price Action Trading Ranges
- Al Brooks, Trading Price Action Reversals

Supplementary uploaded PDFs are excluded from core decision rules.

Autonomous LONG/SHORT remains OFF by default.
"""

from __future__ import annotations

from decimal import Decimal

from app.modules.brooks_core.books_policy import BrooksBooksPolicy
from app.modules.brooks_core.context_classifier import assess_books_context
from app.modules.brooks_core.causal_structure import confirm_swings_causally
from app.modules.brooks_core.engine_contract import BrooksEngineResult
from app.modules.brooks_core.second_entry_v2 import detect_book_second_entry
from app.modules.market_data.entities import MarketSnapshot
from app.modules.signal_automation.entities import BrooksRuleEvidence


class BrooksBooksH2L2Engine:
    engine_version = "brooks-books-h2l2-v2-shadow"
    rule_set_version = "brooks-trilogy-source-catalog-v2"

    def __init__(self, *, policy: BrooksBooksPolicy | None = None) -> None:
        self.policy = policy or BrooksBooksPolicy()

    async def evaluate(self, snapshot: MarketSnapshot) -> BrooksEngineResult:
        policy = self.policy
        if len(snapshot.candles) < policy.context_window_bars:
            return self._no_signal(
                reasoning=("Insufficient closed candles for book-grounded context.",),
            )

        context = assess_books_context(snapshot, policy=policy)
        metrics = context.metrics
        evidence: list[BrooksRuleEvidence] = [
            BrooksRuleEvidence(
                rule_id="BB-TRD-19-TREND-STRENGTH",
                status=(
                    "PASS"
                    if context.regime in {"BULL_TREND", "BEAR_TREND"}
                    else "AMBIGUOUS"
                ),
                source_pages=(337, 338, 339),
                evidence=(
                    ("source_book", "Trading Price Action Trends"),
                    ("regime", context.regime),
                    ("structure", context.structure_direction),
                    ("directional_bar_fraction", str(metrics.directional_bar_fraction)),
                    ("body_overlap_rate", str(metrics.body_overlap_rate)),
                    ("bar_overlap_rate", str(metrics.bar_overlap_rate)),
                    ("adjusted_displacement", str(metrics.adjusted_displacement)),
                    ("close_path_efficiency", str(metrics.close_path_efficiency)),
                    ("ema_side_fraction", str(metrics.ema_side_fraction)),
                    ("strong_bull_bars", str(metrics.strong_bull_bar_count)),
                    ("strong_bear_bars", str(metrics.strong_bear_bar_count)),
                    ("numeric_thresholds", "ENGINEERING_POLICY"),
                ),
            ),
            BrooksRuleEvidence(
                rule_id="BB-RNG-02-BREAKOUT-FOLLOWTHROUGH",
                status=("PASS" if context.breakout_direction != "UNRESOLVED" else "NOT_APPLICABLE"),
                source_pages=(39, 40, 41),
                evidence=(
                    ("source_book", "Trading Price Action Trading Ranges"),
                    ("recent_breakout_direction", context.breakout_direction),
                    ("strong_bar_streak", str(context.breakout_streak)),
                    ("strong_bar_definition", "ENGINEERING_PROXY_FOR_SOURCE_CHARACTERISTICS"),
                ),
            ),
            BrooksRuleEvidence(
                rule_id="BB-REV-15-ALWAYS-IN",
                status=("PASS" if context.always_in != "UNRESOLVED" else "AMBIGUOUS"),
                source_pages=(321, 323, 325),
                evidence=(
                    ("source_book", "Trading Price Action Reversals"),
                    ("always_in", context.always_in),
                    ("context_reason", context.reason),
                    ("typical_two_bar_followthrough", "SOURCE_RULE"),
                ),
            ),
            BrooksRuleEvidence(
                rule_id="BB-RNG-CTX-TREND-VS-RANGE",
                status=(
                    "PASS"
                    if context.regime in {"BULL_TREND", "BEAR_TREND"}
                    else "FAIL" if context.regime == "TRADING_RANGE" else "AMBIGUOUS"
                ),
                source_pages=(108, 109, 113),
                evidence=(
                    ("source_book", "Trading Price Action Trading Ranges"),
                    ("regime", context.regime),
                    ("tight_range_like", str(metrics.tight_range_like).lower()),
                    ("continuation_scope", "TREND_H2_L2_ONLY"),
                ),
                failed_conditions=(
                    ("H2/L2 continuation semantics are not valid in current non-trend context",)
                    if context.regime == "TRADING_RANGE"
                    else ()
                ),
            ),
        ]

        if context.regime == "TRANSITION":
            evidence.append(
                BrooksRuleEvidence(
                    rule_id="BB-REV-03-REVERSAL-MATURITY",
                    status="AMBIGUOUS",
                    source_pages=(111, 112, 113),
                    evidence=(
                        ("source_book", "Trading Price Action Reversals"),
                        ("state", "TRANSITION"),
                        ("reason", context.reason),
                    ),
                    failed_conditions=(
                        "opposite breakout/follow-through conflicts with prior structure; wait for more price action",
                    ),
                )
            )
            return self._no_signal(
                reasoning=(
                    "Source-grounded context is in transition/reversal territory.",
                    "Do not relabel an immature reversal as an H2/L2 trend continuation.",
                    context.reason,
                ),
                evidence=tuple(evidence),
                rule_ids=tuple(item.rule_id for item in evidence),
            )

        if context.regime == "TRADING_RANGE":
            return self._no_signal(
                reasoning=(
                    "Current context is trading-range/two-sided.",
                    "Brooks assigns different H2/L2 semantics in a range; this v2 engine only trades trend continuations.",
                ),
                evidence=tuple(evidence),
                rule_ids=tuple(item.rule_id for item in evidence),
            )

        if context.regime not in {"BULL_TREND", "BEAR_TREND"}:
            return self._no_signal(
                reasoning=(
                    "Trend context is not mature enough for a source-grounded H2/L2 continuation.",
                    context.reason,
                ),
                evidence=tuple(evidence),
                rule_ids=tuple(item.rule_id for item in evidence),
            )

        # Re-run swing scan only to obtain a causal pullback anchor. The numeric swing
        # confirmation is engineering infrastructure, not a Brooks threshold.
        scan = confirm_swings_causally(
            snapshot.candles,
            left_bars=policy.swing_left_bars,
            right_bars=policy.swing_right_bars,
        )
        wanted = "HIGH" if context.regime == "BULL_TREND" else "LOW"
        anchors = [s for s in scan.swings if s.kind == wanted]
        if not anchors:
            return self._no_signal(
                reasoning=("No causal confirmed pullback anchor is available.",),
                evidence=tuple(evidence),
                rule_ids=tuple(item.rule_id for item in evidence),
            )

        start_index = anchors[-1].candle_index
        if len(snapshot.candles) - start_index > policy.pullback_window_bars:
            start_index = len(snapshot.candles) - policy.pullback_window_bars

        assessment = detect_book_second_entry(
            snapshot.candles,
            trend_direction=context.regime,
            start_index=start_index,
        )
        evidence.append(
            BrooksRuleEvidence(
                rule_id="BB-RNG-17-HL-BAR-COUNT",
                status="PASS" if assessment.setup else "NOT_APPLICABLE",
                source_pages=(108, 109, 112, 113),
                evidence=(
                    ("source_book", "Trading Price Action Trading Ranges"),
                    ("start_index", str(start_index)),
                    ("events", ",".join(event.label for event in assessment.events) or "NONE"),
                    ("highest_entry_number", str(assessment.highest_entry_number)),
                    ("edge_policy", "DISTINCT_LATER_SECOND_EXCURSION_SOURCE_INTERPRETATION"),
                    ("equal_boundaries", "NEUTRAL_NOT_GLOBAL_BLOCK"),
                    ("inside_bars", "NEUTRAL_NOT_GLOBAL_BLOCK"),
                ),
            )
        )

        if assessment.setup is None:
            return self._no_signal(
                reasoning=(
                    f"Resolved trend context={context.regime}.",
                    assessment.reason,
                    "No source-style H2/L2 event exists on the final closed bar.",
                ),
                evidence=tuple(evidence),
                rule_ids=tuple(item.rule_id for item in evidence),
            )

        setup = assessment.setup
        signal = snapshot.candles[setup.signal_index]
        ema = _ema20(snapshot.candles)
        ma_location_supportive = (
            signal.close >= ema if setup.direction == "LONG" else signal.close <= ema
        )
        evidence.append(
            BrooksRuleEvidence(
                rule_id="BB-RNG-17-H2L2-TREND-CONTEXT",
                status="PASS",
                source_pages=(108, 109),
                evidence=(
                    ("source_book", "Trading Price Action Trading Ranges"),
                    ("setup_type", setup.setup_type),
                    ("regime", context.regime),
                    ("always_in", context.always_in),
                    ("signal_vs_ema20_supportive", str(ma_location_supportive).lower()),
                    ("ema_role", "SOURCE_CONTEXT_EVIDENCE_NOT_SOLE_GATE"),
                ),
            )
        )

        evidence.append(
            BrooksRuleEvidence(
                rule_id="BB-RNG-26-TWO-REASONS",
                status="PASS",
                source_pages=(187, 188),
                evidence=(
                    ("source_book", "Trading Price Action Trading Ranges"),
                    ("reason_1", f"SOURCE_CONTEXT:{context.regime}:{context.always_in}"),
                    ("reason_2", f"SECOND_ENTRY:{setup.setup_type}"),
                    ("note", "Brooks treats a second entry itself as an additional reason; trend context supplies independent support"),
                ),
            )
        )

        if not policy.enable_trade_decisions:
            return self._no_signal(
                setup_type=setup.setup_type,
                reasoning=(
                    f"Detected {setup.setup_type} using book-grounded bar counting in {context.regime}.",
                    "Trend/range and Always-In context were evaluated before the setup.",
                    "Autonomous trade decision remains disabled for shadow validation.",
                ),
                evidence=tuple(evidence),
                rule_ids=tuple(item.rule_id for item in evidence),
            )

        entry, stop, targets = _execution_geometry(
            snapshot=snapshot,
            signal_index=setup.signal_index,
            direction=setup.direction,
            policy=policy,
        )
        evidence.append(
            BrooksRuleEvidence(
                rule_id="BB-RNG-29-SIGNAL-BAR-STOP",
                status="PASS",
                source_pages=(202, 203, 204),
                evidence=(
                    ("source_book", "Trading Price Action Trading Ranges"),
                    ("initial_stop_concept", "BEYOND_SIGNAL_BAR"),
                    ("buffer", "ENGINEERING_CRYPTO_PROXY"),
                ),
            )
        )
        evidence.append(
            BrooksRuleEvidence(
                rule_id="ENG-BOOKS-V2-TARGETS",
                status="PASS",
                source_pages=(),
                evidence=(
                    ("source", "ENGINEERING_POLICY_NOT_UNIVERSAL_BROOKS_TARGET"),
                    ("target_r_multiples", ",".join(str(x) for x in policy.target_r_multiples)),
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
                f"Book-grounded trend context={context.regime}, Always-In={context.always_in}.",
                f"Book-grounded second entry={setup.setup_type} on final closed bar.",
                "Entry/initial stop follow the source stop-entry/signal-bar concepts with a crypto buffer.",
                "Profit targets remain explicit engineering R-multiples, not a universal Brooks rule.",
            ),
            rule_ids=tuple(item.rule_id for item in evidence),
            failed_rules=(),
            rule_evidence=tuple(evidence),
            engine_version=self.engine_version,
            rule_set_version=self.rule_set_version,
            configuration_version=policy.configuration_version,
        )

    def _no_signal(
        self,
        *,
        reasoning: tuple[str, ...],
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


def _ema20(candles) -> Decimal:
    alpha = Decimal("2") / Decimal("21")
    value = candles[0].close
    for candle in candles[1:]:
        value = candle.close * alpha + value * (Decimal("1") - alpha)
    return value


def _execution_geometry(
    *,
    snapshot: MarketSnapshot,
    signal_index: int,
    direction: str,
    policy: BrooksBooksPolicy,
) -> tuple[Decimal, Decimal, tuple[Decimal, ...]]:
    signal = snapshot.candles[signal_index]
    spread = signal.high - signal.low
    stop_buffer = spread * policy.stop_buffer_fraction_of_signal_range

    if direction == "LONG":
        entry = signal.high * (Decimal("1") + policy.entry_buffer_fraction)
        stop = signal.low - stop_buffer
        risk = entry - stop
        if risk <= 0:
            raise ValueError("invalid LONG risk geometry")
        targets = tuple(entry + risk * x for x in policy.target_r_multiples)
        return entry, stop, targets

    entry = signal.low * (Decimal("1") - policy.entry_buffer_fraction)
    stop = signal.high + stop_buffer
    risk = stop - entry
    if risk <= 0:
        raise ValueError("invalid SHORT risk geometry")
    targets = tuple(entry - risk * x for x in policy.target_r_multiples)
    return entry, stop, targets
