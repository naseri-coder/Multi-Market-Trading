import hashlib
import logging
from pathlib import Path
from app.modules.brooks_core.engine_contract import ActualBrooksStrategyEngine
from app.modules.brooks_core.entities import BrooksCoreDecision
from app.modules.brooks_core.chart_evidence import build_chart_evidence
from app.modules.charting.protocols import SignalChartRenderer
from app.modules.market_data.entities import MarketSnapshot

logger = logging.getLogger(__name__)


class BrooksCoreAnalyzerAdapter:
    def __init__(
        self,
        *,
        engine: ActualBrooksStrategyEngine,
        renderer: SignalChartRenderer,
        chart_directory: Path,
    ) -> None:
        self.engine = engine
        self.renderer = renderer
        self.chart_directory = chart_directory

    def _cleanup_stale_charts(self) -> None:
        if not self.chart_directory.exists():
            return
        for chart_path in self.chart_directory.glob("*.png"):
            try:
                chart_path.unlink()
            except FileNotFoundError:
                pass

    async def analyze(self, snapshot: MarketSnapshot) -> BrooksCoreDecision:
        self._cleanup_stale_charts()
        result = await self.engine.evaluate(snapshot)
        if result.decision == "NO_SIGNAL":
            return BrooksCoreDecision(
                decision="NO_SIGNAL",
                source_signal_id=None,
                entry_price=None,
                stop_loss=None,
                targets=(),
                setup_type=result.setup_type,
                reasoning=result.reasoning,
                rule_ids=result.rule_ids,
                failed_rules=result.failed_rules,
                rule_evidence=result.rule_evidence,
                engine_version=result.engine_version,
                rule_set_version=result.rule_set_version,
                configuration_version=result.configuration_version,
                market_snapshot_id=snapshot.snapshot_id,
                market_snapshot_hash=snapshot.snapshot_hash,
                chart_path=None,
                target_source_identities=(),
                stop_source_identity=None,
                target_plan_lifecycle=None,
                reversal_outcome_context=None,
            )

        seed = "|".join(
            (
                snapshot.snapshot_hash,
                result.decision,
                result.setup_type or "",
                result.engine_version,
                result.rule_set_version,
                result.configuration_version,
            )
        )
        source_signal_id = hashlib.sha256(seed.encode()).hexdigest()
        output_path = self.chart_directory / (
            f"{snapshot.exchange}_{snapshot.market_type}_{snapshot.symbol}_"
            f"{snapshot.timeframe}_{source_signal_id[:16]}.png"
        )
        chart_evidence = build_chart_evidence(
            signal_index=len(snapshot.candles) - 1,
            setup_type=result.setup_type,
            rule_evidence=result.rule_evidence,
        )

        logger.info(
            "Brooks chart evidence prepared",
            extra={
                "event": "brooks_chart_evidence_prepared",
                "symbol": snapshot.symbol,
                "timeframe": snapshot.timeframe,
                "setup_type": result.setup_type,
                "signal_index": chart_evidence.signal_index,
                "family": chart_evidence.family,
                "breakout_index": chart_evidence.breakout_index,
                "reference_swing_index": (
                    chart_evidence.reference_swing_index
                ),
                "reference_level": (
                    str(chart_evidence.reference_level)
                    if chart_evidence.reference_level is not None
                    else None
                ),
                "range_low": (
                    str(chart_evidence.range_low)
                    if chart_evidence.range_low is not None
                    else None
                ),
                "range_high": (
                    str(chart_evidence.range_high)
                    if chart_evidence.range_high is not None
                    else None
                ),
                "push_indices": chart_evidence.push_indices,
                "structure_break_index": (
                    chart_evidence.structure_break_index
                ),
                "old_extreme": (
                    str(chart_evidence.old_extreme)
                    if chart_evidence.old_extreme is not None
                    else None
                ),
            },
        )

        chart_path = self.renderer.render(
            snapshot=snapshot,
            direction=result.decision,
            entry_price=result.entry_price,
            stop_loss=result.stop_loss,
            targets=result.targets,
            setup_type=result.setup_type,
            output_path=output_path,
            chart_evidence=chart_evidence,
        )

        logger.info(
            "Signal chart rendered",
            extra={
                "event": "signal_chart_rendered",
                "symbol": snapshot.symbol,
                "timeframe": snapshot.timeframe,
                "direction": result.decision,
                "setup_type": result.setup_type,
                "chart_path": str(chart_path),
                "chart_size_bytes": (
                    chart_path.stat().st_size
                    if chart_path.is_file()
                    else None
                ),
                "snapshot_id": snapshot.snapshot_id,
            },
        )
        return BrooksCoreDecision(
            decision=result.decision,
            source_signal_id=source_signal_id,
            entry_price=result.entry_price,
            stop_loss=result.stop_loss,
            targets=result.targets,
            setup_type=result.setup_type,
            reasoning=result.reasoning,
            rule_ids=result.rule_ids,
            failed_rules=result.failed_rules,
            rule_evidence=result.rule_evidence,
            engine_version=result.engine_version,
            rule_set_version=result.rule_set_version,
            configuration_version=result.configuration_version,
            market_snapshot_id=snapshot.snapshot_id,
            market_snapshot_hash=snapshot.snapshot_hash,
            chart_path=str(chart_path),
            target_source_identities=result.target_source_identities,
            stop_source_identity=result.stop_source_identity,
            target_plan_lifecycle=result.target_plan_lifecycle,
            reversal_outcome_context=result.reversal_outcome_context,
        )
