"""Runtime wiring for Brooks Trilogy Full Core v3.

Modes:
- PAPER: private test delivery only.
- LIVE: VIP publication only, with a persistent cutover watermark.

No exchange order execution exists in this coordinator.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from decimal import Decimal
from pathlib import Path
from time import monotonic
from typing import Any

from telegram.ext import Application

from app.core.config import Settings
from app.modules.ai_council.service import AICouncilService
from app.modules.brooks_core.analyzer_adapter import BrooksCoreAnalyzerAdapter
from app.modules.brooks_core.books_full_engine import BrooksTrilogyFullCoreEngine
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.brooks_core.context_classifier import assess_books_context
from app.modules.brooks_core.mapper import to_paper_candidate
from app.modules.brooks_core_v3.governance import BrooksRuntimeGovernanceAuditor
from app.modules.charting.matplotlib_renderer import MatplotlibSignalChartRenderer
from app.modules.live_vip_runtime.publisher import TelegramLiveVipPublisher
from app.modules.live_vip_runtime.service import LiveVipRuntimeService
from app.modules.market_data.binance_futures import BinanceFuturesMarketDataProvider
from app.modules.market_data.entities import MarketSnapshot
from app.modules.operations.approval_evidence import record_approved_candidate
from app.modules.paper_runtime.publisher import TelegramPaperPublisher
from app.modules.paper_runtime.service import PaperRuntimeService
from app.modules.risk_engine.service import RiskEngineService
from app.modules.scale_in.runtime_observer import ShadowScaleInObserver
from app.modules.signal_automation.entities import (
    BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1,
    FINAL_BROOKS_HP_SEMANTIC_COHORT_ID,
    HP_COLD_START_BOOTSTRAP_POLICY_ID,
    BrooksSignalImport,
    hp_cold_start_shadow_source_signal_id,
)
from app.modules.signal_automation.service import BrooksSignalIntegrationService
from app.modules.signal_gate.service import SignalGateService
from app.modules.signal_intelligence.probability import load_probability_engine
from app.modules.signal_intelligence.service import SignalIntelligenceService
from app.modules.signal_quality.repository import SQLAlchemySignalQualityRepository
from app.modules.signal_quality.service import SignalQualityService

logger = logging.getLogger(__name__)

_REALIZED_R_LEVERAGE_POLICY_ID = "BROOKS_REALIZED_R_BASELINE_ONLY_LEVERAGE_V1"
_REALIZED_R_BASELINE_LEVERAGE_CONFIDENCE = 0.0


def _leverage_confidence_input(
    outcome_policy_id: str | None,
    signal_quality_confidence: float,
) -> tuple[float, str]:
    """Route only the private leverage-confidence input by HP outcome policy."""
    if outcome_policy_id == BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1:
        return (
            _REALIZED_R_BASELINE_LEVERAGE_CONFIDENCE,
            _REALIZED_R_LEVERAGE_POLICY_ID,
        )
    if outcome_policy_id in {None, "LEGACY_LATEST_TERMINAL_EVENT_V1"}:
        return float(signal_quality_confidence), "LEGACY_SIGNAL_QUALITY_CONFIDENCE"
    return 0.0, "UNKNOWN_POLICY_FAIL_CLOSED_NO_UPLIFT"


def _risk_semantic_breakdown(risk_assessment: object) -> dict[str, object]:
    """Return the Risk-produced semantic breakdown without recomputation."""
    metadata = getattr(risk_assessment, "metadata", {})
    if not isinstance(metadata, dict):
        return {}
    breakdown = metadata.get("risk_semantic_breakdown")
    return breakdown if isinstance(breakdown, dict) else {}


def _risk_semantic_observability_payload(
    candidate: object,
    risk_assessment: object,
) -> dict[str, object]:
    """Build a bounded transport-only view of already-computed Risk diagnostics."""
    breakdown = _risk_semantic_breakdown(risk_assessment)
    structural = breakdown.get("structural_validation", {})
    if not isinstance(structural, dict):
        structural = {}
    plan_reward = breakdown.get("plan_reward", {})
    if not isinstance(plan_reward, dict):
        plan_reward = {}
    return {
        "market_snapshot_id": getattr(candidate, "market_snapshot_id", None),
        "economic_opportunity_id": getattr(candidate, "economic_opportunity_id", None),
        "semantic_cohort_id": getattr(candidate, "semantic_cohort_id", None),
        "symbol": getattr(candidate, "symbol", None),
        "timeframe": getattr(candidate, "timeframe", None),
        "setup_type": getattr(candidate, "setup_type", None),
        "direction": getattr(candidate, "direction", None),
        "risk_score": getattr(risk_assessment, "risk_score", None),
        "approved": getattr(risk_assessment, "approved", None),
        "reasons": getattr(risk_assessment, "reasons", None),
        "plan_rr": breakdown.get("plan_rr"),
        "rr_points": breakdown.get("rr_points"),
        "entry_method": structural.get("entry_method"),
        "structural_validation_mode": structural.get("validation_mode"),
        "structural_points": breakdown.get("structural_points"),
        "runner_policy": plan_reward.get("runner_policy"),
        "weighted_runner_r": plan_reward.get("weighted_runner_r"),
        "target_plan_state": plan_reward.get("target_plan_state"),
    }


def _attach_risk_semantic_breakdown(
    signal_quality: object,
    risk_assessment: object,
) -> None:
    """Add exact Risk diagnostics to existing quality metadata for persistence."""
    breakdown = _risk_semantic_breakdown(risk_assessment)
    metadata = getattr(signal_quality, "metadata", None)
    if isinstance(metadata, dict) and breakdown:
        metadata["risk_semantic_breakdown"] = breakdown


class BrooksFullCoreCoordinator:
    """Own the optional full-core polling loop and its external resources."""

    def __init__(self, *, settings: Settings, database: Any) -> None:
        self.settings = settings
        self.database = database
        self._task: asyncio.Task[None] | None = None
        self._provider: BinanceFuturesMarketDataProvider | None = None
        self._analyzer: BrooksCoreAnalyzerAdapter | None = None
        self._publisher: TelegramPaperPublisher | TelegramLiveVipPublisher | None = None
        self._last_snapshot_id: dict[tuple[str, str], str] = {}
        self._ai_council = AICouncilService()
        self._risk_engine = RiskEngineService()
        self._signal_intelligence = SignalIntelligenceService()
        self._signal_gate = SignalGateService()
        self._governance_auditor = BrooksRuntimeGovernanceAuditor()
        self._scale_in_shadow_observer = (
            ShadowScaleInObserver(database) if settings.brooks_scale_in_mode == "shadow" else None
        )

    async def _collect_hp_cold_start_bootstrap(
        self,
        *,
        candidate,
        council_decision,
        risk_assessment,
        probability_assessment,
        signal_quality,
        leverage: Decimal,
    ):
        """Persist one isolated empirical SHADOW observation for HP cold start."""
        if self.settings.brooks_runtime_mode != "live":
            return None
        if getattr(candidate, "semantic_cohort_id", None) != FINAL_BROOKS_HP_SEMANTIC_COHORT_ID:
            return None
        # Collection stops only at calibrated favorable economic evidence.
        readiness_state = getattr(probability_assessment, "readiness_state", None)
        if readiness_state == "CALIBRATED_FAVORABLE":
            return None
        if readiness_state is not None and readiness_state not in {
            "UNBOOTSTRAPPED",
            "MATURING",
            "CALIBRATED_UNFAVORABLE",
            "STATISTICAL_ASSESSMENT_INVALID",
        }:
            return None
        if not probability_assessment.cohort_isolation_applied:
            return None

        shadow_gate = self._signal_gate.evaluate(signal_quality)
        failures = tuple(shadow_gate.metadata.get("failures", ()) or ())
        expected_failure = (
            "REALIZED_R_EVIDENCE_NOT_FAVORABLE"
            if readiness_state is not None
            else "PROBABILITY_UNCALIBRATED"
        )
        if failures != (expected_failure,):
            return None

        risk_breakdown = _risk_semantic_breakdown(risk_assessment)
        structural = risk_breakdown.get("structural_validation", {})
        if not isinstance(structural, dict):
            return None
        entry_method = structural.get("entry_method")
        if entry_method != "STOP_TRIGGER_CONFIRMATION":
            logger.info(
                "HP cold-start SHADOW collection skipped for ambiguous entry method",
                extra={
                    "event": "hp_cold_start_bootstrap_entry_method_skipped",
                    "symbol": candidate.symbol,
                    "timeframe": candidate.timeframe,
                    "setup_type": candidate.setup_type,
                    "entry_method": entry_method,
                },
            )
            return None

        economic_opportunity_id = structural.get("economic_opportunity_id")
        if not isinstance(economic_opportunity_id, str) or not economic_opportunity_id.strip():
            logger.info(
                "HP cold-start SHADOW collection skipped without economic opportunity identity",
                extra={
                    "event": "hp_cold_start_bootstrap_opportunity_identity_missing",
                    "symbol": candidate.symbol,
                    "timeframe": candidate.timeframe,
                    "setup_type": candidate.setup_type,
                },
            )
            return None

        source_signal_id = hp_cold_start_shadow_source_signal_id(
            candidate.source_signal_id,
            candidate.semantic_cohort_id,
            economic_opportunity_id=economic_opportunity_id,
            symbol=candidate.symbol,
            timeframe=candidate.timeframe,
            direction=candidate.direction,
        )
        provenance = {
            "bootstrap": True,
            "policy_id": HP_COLD_START_BOOTSTRAP_POLICY_ID,
            "generation_mode": "SHADOW",
            "semantic_cohort_id": candidate.semantic_cohort_id,
            "original_source_signal_id": candidate.source_signal_id,
            "mode_scoped_source_signal_id": source_signal_id,
            "market_snapshot_id": candidate.market_snapshot_id,
            "market_snapshot_hash": candidate.market_snapshot_hash,
            "engine_version": candidate.engine_version,
            "rule_set_version": candidate.rule_set_version,
            "configuration_version": candidate.configuration_version,
            "setup_type": candidate.setup_type,
            "timeframe": candidate.timeframe,
            "direction": candidate.direction,
            "entry_method": entry_method,
            "entry_trigger_semantic": structural.get("entry_trigger_semantic"),
            "economic_opportunity_id": economic_opportunity_id,
            "evaluated_at": candidate.snapshot.captured_at.isoformat(),
            "state": "BOOTSTRAP_ENTRY_PENDING",
            "hp_eligible": False,
        }
        command = BrooksSignalImport(
            source_signal_id=source_signal_id,
            symbol=candidate.symbol,
            direction=candidate.direction,
            entry_price=candidate.entry_price,
            stop_loss=candidate.stop_loss,
            targets=candidate.targets,
            leverage=leverage,
            exchange=candidate.exchange,
            market_type=candidate.market_type,
            timeframe=candidate.timeframe,
            setup_type=candidate.setup_type,
            market_snapshot_id=candidate.market_snapshot_id,
            market_snapshot_hash=candidate.market_snapshot_hash,
            engine_version=candidate.engine_version,
            rule_set_version=candidate.rule_set_version,
            configuration_version=candidate.configuration_version,
            reasoning=candidate.reasoning,
            rule_ids=candidate.rule_ids,
            failed_rules=candidate.failed_rules,
            rule_evidence=candidate.rule_evidence,
            target_source_identities=candidate.target_source_identities,
            stop_source_identity=candidate.stop_source_identity,
            target_plan_lifecycle=candidate.target_plan_lifecycle,
            reversal_outcome_context=candidate.reversal_outcome_context,
            semantic_cohort_id=candidate.semantic_cohort_id,
            generation_mode="SHADOW",
            publication_scope="INTERNAL",
            counts_toward_performance=False,
            description="Brooks HP cold-start causal SHADOW observation",
            bootstrap_provenance=provenance,
        )
        async with self.database.session() as session:
            imported = await BrooksSignalIntegrationService(session).import_signal(command)

        if imported.created:
            async with self.database.session() as quality_session:
                quality_service = SignalQualityService(
                    SQLAlchemySignalQualityRepository(quality_session)
                )
                await quality_service.save_quality_assessment(
                    signal_id=imported.signal_id,
                    ai_score=council_decision.final_score,
                    risk_score=risk_assessment.risk_score,
                    final_score=signal_quality.final_score,
                    confidence=signal_quality.confidence,
                    quality_grade=signal_quality.quality_grade,
                    market_regime=signal_quality.metadata.get("market_regime"),
                    gate_approved=False,
                    gate_reason=shadow_gate.reason,
                    metadata=dict(signal_quality.metadata),
                )

        logger.info(
            "HP cold-start SHADOW observation persisted",
            extra={
                "event": "hp_cold_start_bootstrap_persisted",
                "signal_id": imported.signal_id,
                "signal_created": imported.created,
                "symbol": candidate.symbol,
                "timeframe": candidate.timeframe,
                "setup_type": candidate.setup_type,
                "semantic_cohort_id": candidate.semantic_cohort_id,
                "bootstrap_policy_id": HP_COLD_START_BOOTSTRAP_POLICY_ID,
            },
        )
        return imported

    async def start(self, application: Application) -> None:
        if not self.settings.brooks_runtime_enabled:
            logger.info(
                "Brooks full-core runtime is disabled",
                extra={"event": "brooks_full_core_runtime_disabled"},
            )
            return
        if self._task is not None:
            raise RuntimeError("Brooks full-core runtime is already started")

        self._provider = self._build_provider()
        engine = BrooksTrilogyFullCoreEngine(
            policy=BrooksFullCorePolicy(enable_trade_decisions=True)
        )
        self._analyzer = BrooksCoreAnalyzerAdapter(
            engine=engine,
            renderer=MatplotlibSignalChartRenderer(max_candles=120),
            chart_directory=Path("/tmp/brooks-full-core-v3-charts"),
        )

        if self.settings.brooks_runtime_mode == "paper":
            self._publisher = TelegramPaperPublisher(
                bot=application.bot,
                private_test_channel_id=self.settings.paper_private_test_channel_id or 0,
            )
        else:
            self._publisher = TelegramLiveVipPublisher(
                bot=application.bot,
                vip_channel_id=self.settings.brooks_vip_channel_id or 0,
            )

        self._task = asyncio.create_task(
            self._run_loop(),
            name=f"brooks-full-core-v3-{self.settings.brooks_runtime_mode}-runtime",
        )
        logger.info(
            "Brooks full-core runtime started",
            extra={
                "event": "brooks_full_core_runtime_started",
                "runtime_mode": self.settings.brooks_runtime_mode.upper(),
                "exchange": self.settings.brooks_exchange,
                "market_type": self.settings.brooks_market_type,
                "symbols": list(self.settings.brooks_symbols),
                "timeframes": list(self.settings.brooks_timeframes),
                "poll_interval_seconds": self.settings.brooks_poll_interval_seconds,
                "live_cutover_at": (
                    self.settings.brooks_live_cutover_at.isoformat()
                    if self.settings.brooks_live_cutover_at is not None
                    else None
                ),
            },
        )

    async def shutdown(self, application: Application) -> None:
        del application
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        provider = self._provider
        self._provider = None
        if provider is not None:
            await provider.aclose()

        self._analyzer = None
        self._publisher = None
        self._last_snapshot_id.clear()
        logger.info(
            "Brooks full-core runtime stopped",
            extra={
                "event": "brooks_full_core_runtime_stopped",
                "runtime_mode": self.settings.brooks_runtime_mode.upper(),
            },
        )

    def _build_provider(self) -> BinanceFuturesMarketDataProvider:
        if (
            self.settings.brooks_exchange != "binance"
            or self.settings.brooks_market_type != "futures"
        ):
            raise RuntimeError("Brooks production runtime requires binance/futures")
        return BinanceFuturesMarketDataProvider()

    async def _run_loop(self) -> None:
        while True:
            started = monotonic()
            try:
                await self.scan_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "Brooks full-core scan iteration failed",
                    extra={"event": "brooks_full_core_scan_failed"},
                )

            elapsed = monotonic() - started
            delay = max(
                1.0,
                float(self.settings.brooks_poll_interval_seconds) - elapsed,
            )
            await asyncio.sleep(delay)

    async def scan_once(self) -> None:
        if self._provider is None or self._analyzer is None or self._publisher is None:
            raise RuntimeError("Brooks full-core runtime is not started")

        for symbol in self.settings.brooks_symbols:
            for timeframe in self.settings.brooks_timeframes:
                try:
                    await self._process_market(symbol=symbol, timeframe=timeframe)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception(
                        "Brooks full-core market scan failed",
                        extra={
                            "event": "brooks_full_core_market_scan_failed",
                            "runtime_mode": self.settings.brooks_runtime_mode.upper(),
                            "symbol": symbol,
                            "timeframe": timeframe,
                        },
                    )

    async def _process_market(self, *, symbol: str, timeframe: str) -> None:
        assert self._provider is not None
        assert self._analyzer is not None
        assert self._publisher is not None

        live_snapshot = await self._provider.get_snapshot(
            symbol=symbol,
            timeframe=timeframe,
            limit=self.settings.brooks_snapshot_limit,
            market_type=self.settings.brooks_market_type,
        )

        snapshot = MarketSnapshot(
            exchange=live_snapshot.exchange,
            market_type=live_snapshot.market_type,
            symbol=live_snapshot.symbol,
            timeframe=live_snapshot.timeframe,
            candles=live_snapshot.candles,
            captured_at=live_snapshot.candles[-1].close_time,
            source="BROOKS_FULL_CORE_V3_RUNTIME",
        )

        market_key = (symbol, timeframe)
        if self._last_snapshot_id.get(market_key) == snapshot.snapshot_id:
            return
        self._last_snapshot_id[market_key] = snapshot.snapshot_id

        if self.settings.brooks_runtime_mode == "live":
            cutover = self.settings.brooks_live_cutover_at
            if cutover is None:
                raise RuntimeError("LIVE runtime requires cutover watermark")
            if snapshot.captured_at <= cutover:
                logger.info(
                    "Brooks LIVE snapshot skipped by cutover watermark",
                    extra={
                        "event": "brooks_full_core_live_cutover_skip",
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "snapshot_id": snapshot.snapshot_id,
                        "snapshot_closed_at": snapshot.captured_at.isoformat(),
                        "cutover_at": cutover.isoformat(),
                    },
                )
                return

        decision = await self._analyzer.analyze(snapshot)
        candidate = to_paper_candidate(snapshot=snapshot, decision=decision)
        if candidate is None:
            logger.info(
                "Brooks full-core scan completed without tradeable candidate",
                extra={
                    "event": "brooks_full_core_no_candidate",
                    "runtime_mode": self.settings.brooks_runtime_mode.upper(),
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "setup_type": decision.setup_type,
                    "snapshot_id": snapshot.snapshot_id,
                },
            )
            return

        council_decision = self._ai_council.evaluate(candidate)

        logger.info(
            "AI Council evaluated candidate",
            extra={
                "event": "ai_council_candidate_evaluated",
                "symbol": symbol,
                "timeframe": timeframe,
                "setup_type": candidate.setup_type,
                "direction": candidate.direction,
                "approved": council_decision.approved,
                "score": council_decision.final_score,
                "summary": council_decision.summary,
            },
        )

        if not council_decision.approved:
            logger.info(
                "AI Council rejected candidate",
                extra={
                    "event": "ai_council_candidate_rejected",
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "setup_type": candidate.setup_type,
                    "score": council_decision.final_score,
                    "summary": council_decision.summary,
                },
            )
            return

        risk_assessment = self._risk_engine.evaluate(candidate)

        logger.info(
            "Risk Engine evaluated candidate",
            extra={
                "event": "risk_engine_candidate_evaluated",
                **_risk_semantic_observability_payload(candidate, risk_assessment),
            },
        )

        if not risk_assessment.approved:
            logger.info(
                "Risk Engine rejected candidate",
                extra={
                    "event": "risk_engine_candidate_rejected",
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "risk_score": risk_assessment.risk_score,
                },
            )
            return

        async with self.database.session() as probability_session:
            probability_engine = await load_probability_engine(
                probability_session,
                data_domain=self.settings.brooks_historical_probability_domain,
                candidate=candidate,
            )
            probability_assessment = await probability_engine.assess_async(candidate)

        logger.info(
            "Historical Probability evaluated candidate",
            extra={
                "event": "historical_probability_candidate_evaluated",
                "symbol": symbol,
                "timeframe": timeframe,
                "setup_type": candidate.setup_type,
                "calibrated": probability_assessment.calibrated,
                "probability": probability_assessment.probability,
                "empirical_win_rate": probability_assessment.empirical_win_rate,
                "sample_size": probability_assessment.sample_size,
                "scope": probability_assessment.scope,
                "semantic_cohort_id": probability_assessment.semantic_cohort_id,
                "cohort_isolation_applied": probability_assessment.cohort_isolation_applied,
                "compatible_case_count": probability_assessment.compatible_case_count,
                "required_sample_size": probability_assessment.required_sample_size,
                "trader_equation_favorable": probability_assessment.trader_equation_favorable,
            },
        )

        signal_quality = self._signal_intelligence.evaluate(
            candidate,
            ai_score=council_decision.final_score,
            risk_score=risk_assessment.risk_score,
            council_confidence=council_decision.confidence,
            probability=probability_assessment,
        )
        _attach_risk_semantic_breakdown(signal_quality, risk_assessment)

        leverage_confidence, leverage_policy_id = _leverage_confidence_input(
            probability_assessment.outcome_policy_id,
            signal_quality.confidence,
        )
        dynamic_leverage = self._risk_engine.calculator.calculate_leverage(
            entry_price=candidate.entry_price,
            stop_loss=candidate.stop_loss,
            confidence=leverage_confidence,
            quality_grade=signal_quality.quality_grade,
            risk_score=risk_assessment.risk_score,
            market_regime=signal_quality.metadata.get("market_regime"),
        )

        logger.info(
            "Signal Intelligence evaluated candidate",
            extra={
                "event": "signal_intelligence_candidate_evaluated",
                "symbol": symbol,
                "timeframe": timeframe,
                "final_score": signal_quality.final_score,
                "confidence": signal_quality.confidence,
                "leverage_policy_id": leverage_policy_id,
                "leverage_confidence_input": leverage_confidence,
                "quality_grade": signal_quality.quality_grade,
                "approved": signal_quality.approved,
                "metadata": signal_quality.metadata,
            },
        )

        if not signal_quality.approved:
            await self._collect_hp_cold_start_bootstrap(
                candidate=candidate,
                council_decision=council_decision,
                risk_assessment=risk_assessment,
                probability_assessment=probability_assessment,
                signal_quality=signal_quality,
                leverage=dynamic_leverage,
            )
            logger.info(
                "Signal Intelligence rejected candidate",
                extra={
                    "event": "signal_intelligence_candidate_rejected",
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "final_score": signal_quality.final_score,
                    "quality_grade": signal_quality.quality_grade,
                },
            )
            return

        gate_decision = self._signal_gate.evaluate(
            signal_quality,
        )

        logger.info(
            "Final Signal Gate evaluated candidate",
            extra={
                "event": "signal_gate_candidate_evaluated",
                "symbol": symbol,
                "timeframe": timeframe,
                "approved": gate_decision.approved,
                "quality_grade": gate_decision.quality_grade,
                "confidence": gate_decision.confidence,
                "reason": gate_decision.reason,
            },
        )

        try:
            governance_audit = self._governance_auditor.assess(
                candidate=candidate,
                council_approved=council_decision.approved,
                risk_approved=risk_assessment.approved,
                probability_calibrated=probability_assessment.calibrated,
                trader_equation_favorable=probability_assessment.trader_equation_favorable,
                quality_approved=signal_quality.approved,
                gate_approved=gate_decision.approved,
            )
            logger.info(
                "Brooks institutional governance shadow evaluated candidate",
                extra={
                    "event": "brooks_v3_governance_shadow_evaluated",
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "status": governance_audit.status,
                    "mapped_rule_count": len(governance_audit.mapped_rule_ids),
                    "unmapped_rule_ids": governance_audit.unmapped_rule_ids,
                    "blockers": governance_audit.blockers,
                    "production_behavior_changed": False,
                },
            )
        except Exception:
            logger.exception(
                "Brooks institutional governance shadow failed",
                extra={"event": "brooks_v3_governance_shadow_failed"},
            )

        if not gate_decision.approved:
            logger.info(
                "Final Signal Gate rejected candidate",
                extra={
                    "event": "signal_gate_candidate_rejected",
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "quality_grade": gate_decision.quality_grade,
                    "confidence": gate_decision.confidence,
                    "reason": gate_decision.reason,
                },
            )
            return

        if self._scale_in_shadow_observer is not None:
            try:
                shadow_result = await self._scale_in_shadow_observer.observe(
                    candidate=candidate, signal_quality=signal_quality
                )
                logger.info(
                    "Brooks Scale-In SHADOW observer evaluated candidate",
                    extra={
                        "event": "brooks_scale_in_shadow_evaluated",
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "setup_type": candidate.setup_type,
                        "shadow_result": shadow_result,
                        "production_behavior_changed": False,
                    },
                )
            except Exception:
                logger.exception(
                    "Brooks Scale-In SHADOW observer failed without changing baseline behavior",
                    extra={
                        "event": "brooks_scale_in_shadow_failed",
                        "symbol": symbol,
                        "timeframe": timeframe,
                    },
                )

        if self.settings.brooks_runtime_mode == "live":
            context = assess_books_context(snapshot, policy=self._analyzer.engine.policy.context)
            async with self.database.session() as evidence_session, evidence_session.begin():
                await record_approved_candidate(
                    evidence_session,
                    candidate=candidate,
                    context=context,
                    council=council_decision,
                    risk=risk_assessment,
                    quality=signal_quality,
                    gate=gate_decision,
                )

        async with self.database.session() as session:
            if self.settings.brooks_runtime_mode == "paper":
                runtime = PaperRuntimeService(
                    session,
                    publisher=self._publisher,
                    private_test_channel_id=self.settings.paper_private_test_channel_id or 0,
                    default_leverage=Decimal(str(self.settings.paper_default_leverage)),
                )
                result = await runtime.process(
                    candidate,
                    signal_quality=signal_quality,
                )
                event = "brooks_full_core_paper_processed"
                message = "Brooks full-core PAPER candidate processed"
            else:
                runtime = LiveVipRuntimeService(
                    session,
                    publisher=self._publisher,
                    vip_channel_id=self.settings.brooks_vip_channel_id or 0,
                    default_leverage=dynamic_leverage,
                )
                result = await runtime.process(
                    candidate,
                    signal_quality=signal_quality,
                    leverage=dynamic_leverage,
                )
                event = "brooks_full_core_live_vip_processed"
                message = "Brooks full-core LIVE VIP candidate processed"

            async with self.database.session() as quality_session:
                quality_service = SignalQualityService(
                    SQLAlchemySignalQualityRepository(quality_session)
                )

                await quality_service.save_quality_assessment(
                    signal_id=result.signal_id,
                    ai_score=council_decision.final_score,
                    risk_score=risk_assessment.risk_score,
                    final_score=signal_quality.final_score,
                    confidence=signal_quality.confidence,
                    quality_grade=signal_quality.quality_grade,
                    market_regime=signal_quality.metadata.get("market_regime"),
                    gate_approved=gate_decision.approved,
                    gate_reason=gate_decision.reason,
                    metadata=signal_quality.metadata,
                )

                await quality_session.commit()

        logger.info(
            message,
            extra={
                "event": event,
                "runtime_mode": self.settings.brooks_runtime_mode.upper(),
                "symbol": symbol,
                "timeframe": timeframe,
                "setup_type": candidate.setup_type,
                "direction": candidate.direction,
                "signal_id": result.signal_id,
                "signal_created": result.signal_created,
                "delivery_status": result.delivery_status,
                "snapshot_id": candidate.market_snapshot_id,
            },
        )


# Backward-compatible import name for any external references.
BrooksFullCorePaperCoordinator = BrooksFullCoreCoordinator
