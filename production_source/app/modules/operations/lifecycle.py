"""Automatic LIVE Brooks lifecycle with V6 post-target trade management."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Bot
from telegram.error import (
    BadRequest,
    NetworkError,
    RetryAfter,
    TelegramError,
    TimedOut,
)

from app.modules.brooks_core.books_policy import BrooksBooksPolicy
from app.modules.brooks_core.causal_structure import confirm_swings_causally
from app.modules.brooks_core.engine_contract import (
    Chapter4PostEntryBarEvidence,
    Chapter4PostEntryLifecycle,
    Chapter4SignalEntryLifecycle,
    Chapter5EntryBarEvidence,
    ReversalOutcomeContext,
    StopSourceIdentity,
    TargetPlanLifecycle,
    TargetSourceIdentity,
)
from app.modules.market_data.binance_futures import BinanceFuturesMarketDataProvider
from app.modules.market_data.entities import Candle, TIMEFRAME_SECONDS
from app.modules.operations.legacy_market_compat import build_legacy_spot_lifecycle_provider
from app.modules.operations.models import SignalLifecycleState
from app.modules.operations.approval_evidence import (
    ApprovedMarketEvidence,
    RUNNER_EVENT, apply_runner_realization, find_reversal_evidence,
    latest_runner_event, open_position_fraction, open_runner_fraction,
)
from app.modules.operations.telegram_updates import edit_live_signal_message, render_live_caption
from app.modules.operations.trade_management import (
    POLICY_VERSION,
    TradeManagementPlan,
    build_legacy_carryover_plan,
    advance_reversal_outcome_context,
    build_trade_management_plan,
    reversal_outcome_management_mode,
    validate_brooks_execution_contract,
    weighted_close_return,
)
from app.modules.paper_runtime.models import SignalDelivery
from app.modules.signal_automation.entities import HP_COLD_START_BOOTSTRAP_POLICY_ID
from app.modules.signal_automation.models import SignalAutomationMetadata, SignalRuleEvidence
from app.modules.signal_quality.models import SignalQualityAssessment
from app.modules.signals.models import Signal, SignalEvent, SignalTarget
from app.modules.signals.repository import SQLAlchemySignalRepository
from app.modules.signals.service import SignalService

logger = logging.getLogger(__name__)

# Market monitoring remains one-minute candle based.
# Only non-critical Telegram Live Price/P&L refreshes are
# staggered to reduce flood-control pressure.
LIVE_CAPTION_REFRESH_MINUTES = 3

def _hp_bootstrap_metadata(metadata: SignalAutomationMetadata) -> dict[str, object] | None:
    if metadata.generation_mode != "SHADOW":
        return None
    analysis = dict(metadata.analysis_metadata or {})
    raw = analysis.get("hp_cold_start_bootstrap")
    if not isinstance(raw, dict):
        return None
    if raw.get("bootstrap") is not True:
        return None
    if raw.get("policy_id") != HP_COLD_START_BOOTSTRAP_POLICY_ID:
        return None
    return dict(raw)

def _is_hp_bootstrap(metadata: SignalAutomationMetadata) -> bool:
    return _hp_bootstrap_metadata(metadata) is not None

def _set_hp_bootstrap_state(
    metadata: SignalAutomationMetadata,
    *,
    state: str,
    hp_eligible: bool,
) -> None:
    bootstrap = _hp_bootstrap_metadata(metadata)
    if bootstrap is None:
        return
    bootstrap["state"] = state
    bootstrap["hp_eligible"] = hp_eligible
    analysis = dict(metadata.analysis_metadata or {})
    analysis["hp_cold_start_bootstrap"] = bootstrap
    metadata.analysis_metadata = analysis

def _should_refresh_live_caption(
    *,
    signal_id: int,
    candle_close: datetime,
) -> bool:
    minute_bucket = int(candle_close.timestamp() // 60)

    return (minute_bucket + signal_id) % LIVE_CAPTION_REFRESH_MINUTES == 0


@dataclass(frozen=True, slots=True)
class LifecycleItem:
    signal: Signal
    metadata: SignalAutomationMetadata
    delivery: SignalDelivery | None
    targets: tuple[SignalTarget, ...]


def utc_now() -> datetime:
    return datetime.now(UTC)


def _return_pct(*, direction: str, entry: Decimal, price: Decimal, leverage: Decimal) -> Decimal:
    raw = (price - entry) / entry if direction == "LONG" else (entry - price) / entry
    return (raw * Decimal("100") * leverage).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)


def _aggregate_close_pct(
    *,
    signal: Signal,
    targets: tuple[SignalTarget, ...],
    terminal_price: Decimal,
    plan: TradeManagementPlan | None = None,
    runner_event=None,
) -> Decimal:
    terminal_return = _return_pct(
        direction=signal.direction,
        entry=signal.entry_price,
        price=terminal_price,
        leverage=signal.leverage,
    )
    if plan is None:
        if not targets:
            return terminal_return
        values = [
            _return_pct(
                direction=signal.direction,
                entry=signal.entry_price,
                price=(target.target_price if target.status == "HIT" else terminal_price),
                leverage=signal.leverage,
            )
            for target in targets
        ]
        result = sum(values, Decimal("0")) / Decimal(len(values))
    else:
        result = weighted_close_return(
            plan=plan,
            targets=targets,
            target_returns={
                target.target_number: _return_pct(
                    direction=signal.direction,
                    entry=signal.entry_price,
                    price=target.target_price,
                    leverage=signal.leverage,
                )
                for target in targets
                if target.status == "HIT"
            },
            terminal_return=terminal_return,
        )
    result = apply_runner_realization(result, terminal_return, runner_event)
    return result.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)


class LiveSignalLifecycleService:
    """Track entry/TP/SL using only causally closed 1m candles.

    Intrabar ordering is deliberately fail-closed: if the activation candle also
    touches any exit, or a later candle touches both stop and a pending target,
    the outcome is marked ambiguous and excluded from win-rate events.
    """

    def __init__(
        self,
        *,
        database,
        provider,
        bot: Bot,
        vip_channel_id: int,
        cutover_at: datetime,
        candle_limit: int,
    ) -> None:
        self.database = database
        self.provider = provider
        self.bot = bot
        self.vip_channel_id = vip_channel_id
        self.cutover_at = cutover_at.astimezone(UTC)
        self.candle_limit = candle_limit
        self.stop_policy = BrooksBooksPolicy()

    def _provider_for_market(self, *, exchange: str, market_type: str):
        provider_exchange = getattr(self.provider, "exchange", None)
        if (
            provider_exchange == "binance"
            and exchange == "binance"
            and isinstance(self.provider, BinanceFuturesMarketDataProvider)
            and market_type in {"futures", "linear"}
        ):
            return self.provider, False

        if exchange == "binance" and market_type == "spot":
            return build_legacy_spot_lifecycle_provider(), True
        if exchange == "binance" and market_type in {"futures", "linear"}:
            return BinanceFuturesMarketDataProvider(), True
        raise ValueError(f"unsupported lifecycle market route: {exchange}/{market_type}")

    async def run_once(self) -> dict[str, int]:
        retried = await self._retry_pending_message_updates()
        items = await self._load_items()
        by_market: dict[tuple[str, str, str], list[LifecycleItem]] = {}
        for item in items:
            key = (item.metadata.exchange, item.metadata.market_type, item.signal.symbol)
            by_market.setdefault(key, []).append(item)

        processed = 0
        changed = 0
        ambiguous = 0
        providers: dict[tuple[str, str], object] = {}
        owned_providers: list[object] = []
        try:
            for (exchange, market_type, symbol), symbol_items in by_market.items():
                provider_key = (exchange, market_type)
                provider = providers.get(provider_key)
                if provider is None:
                    provider, owned = self._provider_for_market(
                        exchange=exchange, market_type=market_type
                    )
                    providers[provider_key] = provider
                    if owned:
                        owned_providers.append(provider)
                snapshot = await provider.get_snapshot(
                    symbol=symbol,
                    timeframe="1m",
                    limit=self.candle_limit,
                    market_type=market_type,
                )
                for item in symbol_items:
                    result = await self._process_item(item, snapshot.candles)
                    processed += 1
                    changed += int(result["changed"])
                    ambiguous += int(result["ambiguous"])
        finally:
            for provider in owned_providers:
                await provider.aclose()
        return {
            "tracked": processed,
            "changed": changed,
            "ambiguous": ambiguous,
            "message_retries": retried,
        }

    async def _retry_pending_message_updates(self) -> int:
        async with self.database.session() as session:
            states = tuple(
                (
                    await session.scalars(
                        select(SignalLifecycleState)
                        .where(SignalLifecycleState.last_message_event_id.is_not(None))
                        .order_by(SignalLifecycleState.signal_id)
                    )
                ).all()
            )
        retried = 0

        for state in states:
            delivered = await self._refresh_message(
                state.signal_id,
                state.state,
                state.ambiguous_reason,
            )

            if not delivered:
                continue

            await self._clear_message_pending(state.signal_id)

            retried += 1

        return retried

    async def _load_items(self) -> tuple[LifecycleItem, ...]:
        async with self.database.session() as session:
            bootstrap = SignalAutomationMetadata.analysis_metadata["hp_cold_start_bootstrap"]
            statement = (
                select(Signal, SignalAutomationMetadata, SignalDelivery)
                .join(
                    SignalAutomationMetadata,
                    SignalAutomationMetadata.signal_id == Signal.id,
                )
                .outerjoin(
                    SignalDelivery,
                    SignalDelivery.signal_id == Signal.id,
                )
                .where(
                    Signal.status == "OPEN",
                    SignalAutomationMetadata.producer == "BROOKS",
                    SignalAutomationMetadata.created_at > self.cutover_at,
                    or_(
                        and_(
                            Signal.publication_scope == "VIP",
                            SignalAutomationMetadata.generation_mode == "LIVE",
                            SignalAutomationMetadata.counts_toward_performance.is_(True),
                            SignalDelivery.channel_kind == "TELEGRAM_VIP",
                            SignalDelivery.destination_id == str(self.vip_channel_id),
                            SignalDelivery.status == "SENT",
                        ),
                        and_(
                            Signal.publication_scope == "INTERNAL",
                            SignalAutomationMetadata.generation_mode == "SHADOW",
                            SignalAutomationMetadata.counts_toward_performance.is_(False),
                            bootstrap["bootstrap"].astext == "true",
                            bootstrap["policy_id"].astext == HP_COLD_START_BOOTSTRAP_POLICY_ID,
                        ),
                    ),
                )
                .order_by(Signal.id)
            )
            rows = (await session.execute(statement)).all()
            result: list[LifecycleItem] = []
            for signal, metadata, delivery in rows:
                targets = tuple(
                    (
                        await session.scalars(
                            select(SignalTarget)
                            .where(SignalTarget.signal_id == signal.id)
                            .order_by(SignalTarget.target_number)
                        )
                    ).all()
                )
                result.append(
                    LifecycleItem(
                        signal=signal,
                        metadata=metadata,
                        delivery=delivery,
                        targets=targets,
                    )
                )
            return tuple(result)

    @staticmethod
    def _breakeven_ready(
        targets: tuple[SignalTarget, ...],
        plan: TradeManagementPlan,
    ) -> bool:
        """V6: a target touch matters only when the precommitted plan scaled out."""
        return plan.breakeven_mode == "AFTER_PARTIAL" and plan.has_secured_partial(targets)

    def _entry_tested_then_resumed(
        self,
        *,
        signal: Signal,
        plan: TradeManagementPlan,
        candles: tuple[Candle, ...],
        candle: Candle,
        entry_activated_at: datetime | None,
    ) -> bool:
        """Detect the Brooks test-of-entry followed by a fresh favorable extreme."""
        if entry_activated_at is None:
            return False
        history = tuple(
            item for item in candles if entry_activated_at <= item.close_time <= candle.close_time
        )
        if len(history) < 4:
            return False
        tick = self.stop_policy.tick_size_for_symbol(signal.symbol)
        for index in range(2, len(history) - 1):
            before = history[:index]
            test = history[index]
            after = history[index + 1 :]
            confirmation_distance = plan.initial_risk * Decimal("0.5")
            if signal.direction == "LONG":
                prior_extreme = max(item.high for item in before)
                had_favorable_move = prior_extreme >= signal.entry_price + confirmation_distance
                tested_entry = plan.initial_stop_loss < test.low <= signal.entry_price + tick
                resumed = max(item.close for item in after) > prior_extreme
            else:
                prior_extreme = min(item.low for item in before)
                had_favorable_move = prior_extreme <= signal.entry_price - confirmation_distance
                tested_entry = plan.initial_stop_loss > test.high >= signal.entry_price - tick
                resumed = min(item.close for item in after) < prior_extreme
            if had_favorable_move and tested_entry and resumed:
                return True
        return False

    def _load_core_execution_contract(
        self,
        *,
        metadata: SignalAutomationMetadata,
    ) -> tuple[
        tuple[TargetSourceIdentity, ...],
        StopSourceIdentity | None,
        TargetPlanLifecycle | None,
        ReversalOutcomeContext | None,
    ]:
        """Restore the exact Core typed contract from additive JSONB; never infer from price."""
        raw_metadata = dict(metadata.analysis_metadata or {})
        stored = raw_metadata.get("brooks_core_typed_contract")
        if not isinstance(stored, dict):
            return (), None, None, None
        try:
            raw_targets = stored.get("target_source_identities", ())
            if not isinstance(raw_targets, (list, tuple)):
                raise ValueError("typed target identities must be a sequence")
            target_source_identities = tuple(
                TargetSourceIdentity.from_metadata(item)
                for item in raw_targets
                if isinstance(item, dict)
            )
            raw_stop = stored.get("stop_source_identity")
            stop_source_identity = (
                None
                if raw_stop is None
                else StopSourceIdentity.from_metadata(raw_stop)
            )
            raw_plan = stored.get("target_plan_lifecycle")
            target_plan_lifecycle = (
                None
                if raw_plan is None
                else TargetPlanLifecycle.from_metadata(raw_plan)
            )
            raw_outcome = stored.get("reversal_outcome_context")
            reversal_outcome_context = (
                None
                if raw_outcome is None
                else ReversalOutcomeContext.from_metadata(raw_outcome)
            )
        except (KeyError, TypeError, ValueError):
            logger.warning(
                "Invalid persisted Brooks Core typed contract; failing closed",
                extra={"signal_id": metadata.signal_id},
            )
            return (), None, None, None
        return (
            target_source_identities,
            stop_source_identity,
            target_plan_lifecycle,
            reversal_outcome_context,
        )

    @staticmethod
    def _load_chapter4_lifecycle(
        metadata: SignalAutomationMetadata,
    ) -> Chapter4SignalEntryLifecycle | None:
        raw = dict(metadata.analysis_metadata or {}).get(
            "brooks_chapter4_lifecycle"
        )
        if not isinstance(raw, dict):
            return None
        try:
            return Chapter4SignalEntryLifecycle.from_metadata(raw)
        except (KeyError, TypeError, ValueError):
            logger.warning(
                "Invalid persisted Chapter-4 lifecycle; leaving legacy lifecycle unchanged",
                extra={"signal_id": metadata.signal_id},
            )
            return None

    @staticmethod
    def _store_chapter4_lifecycle(
        metadata: SignalAutomationMetadata,
        lifecycle: Chapter4SignalEntryLifecycle,
    ) -> None:
        raw = dict(metadata.analysis_metadata or {})
        raw["brooks_chapter4_lifecycle"] = lifecycle.to_metadata()
        metadata.analysis_metadata = raw

    @staticmethod
    def _source_interval(
        timeframe: str,
        moment: datetime,
    ) -> tuple[datetime, datetime] | None:
        seconds = TIMEFRAME_SECONDS.get(timeframe)
        if seconds is None:
            return None
        moment_utc = moment.astimezone(UTC)
        bucket = int(moment_utc.timestamp()) // seconds * seconds
        opened = datetime.fromtimestamp(bucket, tz=UTC)
        closed = datetime.fromtimestamp(bucket + seconds, tz=UTC)
        return opened, closed

    @staticmethod
    def _chapter4_bar_index(
        lifecycle: Chapter4SignalEntryLifecycle,
        bar_open: datetime,
    ) -> int | None:
        seconds = TIMEFRAME_SECONDS.get(lifecycle.source_timeframe)
        if seconds is None:
            return None
        try:
            potential_open = datetime.fromisoformat(
                lifecycle.potential_signal_bar_open_time
            ).astimezone(UTC)
        except ValueError:
            return None
        delta = int((bar_open.astimezone(UTC) - potential_open).total_seconds())
        if delta < 0 or delta % seconds:
            return None
        return lifecycle.potential_signal_bar_index + delta // seconds

    def _promote_chapter4_entry(
        self,
        lifecycle: Chapter4SignalEntryLifecycle,
        candle: Candle,
        *,
        prior_closed_1m: tuple[Candle, ...] = (),
    ) -> Chapter4SignalEntryLifecycle:
        if lifecycle.state != "POTENTIAL_SIGNAL_WAITING_ENTRY":
            return lifecycle
        interval = self._source_interval(
            lifecycle.source_timeframe,
            candle.open_time,
        )
        if interval is None:
            return lifecycle
        entry_open, entry_close = interval
        entry_identity = (
            f"CH4:ENTRY:{lifecycle.source_signal_id}:"
            f"{entry_open.isoformat()}"
        )
        post_entry = Chapter4PostEntryLifecycle(
            entry_bar_identity_id=entry_identity,
            source_timeframe=lifecycle.source_timeframe,
            direction=lifecycle.direction,
        )
        promoted = replace(
            lifecycle,
            state="CONFIRMED_SIGNAL_ENTRY_ACTIVE",
            confirmed_signal_bar_identity_id=(
                lifecycle.potential_signal_bar_identity_id
            ),
            confirmed_signal_bar_index=lifecycle.potential_signal_bar_index,
            confirmed_signal_bar_confirmed_at=candle.close_time.isoformat(),
            entry_bar_identity_id=entry_identity,
            entry_bar_index=self._chapter4_bar_index(
                lifecycle,
                entry_open,
            ),
            entry_bar_open_time=entry_open.isoformat(),
            entry_bar_close_time=entry_close.isoformat(),
            activation_candle_open_time=candle.open_time.isoformat(),
            activation_candle_close_time=candle.close_time.isoformat(),
            entry_activation_observed_at=candle.close_time.isoformat(),
            fill_observation_resolution="CLOSED_1M_CANDLE_TOUCH",
            post_entry_lifecycle=post_entry,
        )
        # Only already-closed, previously available 1m candles; never future data.
        for prior in sorted(prior_closed_1m, key=lambda bar: bar.open_time):
            if (
                entry_open <= prior.open_time.astimezone(UTC)
                and prior.close_time.astimezone(UTC) <= candle.open_time.astimezone(UTC)
            ):
                promoted = self._observe_chapter5_entry_bar(
                    promoted, prior, at_activation=True
                )
        return self._observe_chapter5_entry_bar(
            promoted, candle, at_activation=True
        )

    @staticmethod
    def _terminate_chapter4_unfilled(
        lifecycle: Chapter4SignalEntryLifecycle,
        reason: str,
    ) -> Chapter4SignalEntryLifecycle:
        if lifecycle.state != "POTENTIAL_SIGNAL_WAITING_ENTRY":
            return lifecycle
        return replace(
            lifecycle,
            state="UNFILLED_TERMINAL",
            unfilled_terminal_reason=reason,
        )

    @staticmethod
    def _post_entry_relation(
        *,
        direction: str,
        open_price: Decimal,
        close_price: Decimal,
    ) -> str:
        if close_price == open_price:
            return "NEUTRAL_OR_SIDEWAYS"
        favorable = (
            close_price > open_price
            if direction == "LONG"
            else close_price < open_price
        )
        return "FAVORABLE_CONTINUATION" if favorable else "ADVERSE"

    @staticmethod
    def _chapter5_entry_quality(
        *,
        direction: str,
        open_price: Decimal,
        high_price: Decimal,
        low_price: Decimal,
        close_price: Decimal,
        prior_high: Decimal | None = None,
        prior_low: Decimal | None = None,
    ) -> tuple[str, tuple[str, ...], bool | None]:
        """Qualitative completed-entry-bar evidence, not a trading rule."""
        body = abs(close_price - open_price)
        upper = high_price - max(open_price, close_price)
        lower = min(open_price, close_price) - low_price
        inside = (
            high_price <= prior_high and low_price >= prior_low
            if prior_high is not None and prior_low is not None else None
        )
        favorable = (
            close_price > open_price if direction == "LONG"
            else close_price < open_price
        )
        rejection = lower if direction == "LONG" else upper
        adverse = upper if direction == "LONG" else lower
        doji_like = body == 0 or (body <= upper and body <= lower)
        if doji_like or inside is True:
            quality = "WEAK_DOJI_OR_INSIDE"
        elif favorable and body > adverse and body > rejection:
            quality = "STRONG_DIRECTIONAL"
        else:
            quality = "MIXED_DIRECTIONAL"
        tags = (
            "COMPLETED_ACTUAL_ENTRY_SOURCE_BAR",
            "FAVORABLE_BODY" if favorable else "NON_FAVORABLE_BODY",
            "DOJI_LIKE" if doji_like else "BODY_PRESENT",
            "INSIDE_BAR" if inside else "PRIOR_RANGE_UNAVAILABLE"
            if inside is None else "NOT_INSIDE_BAR",
            "ADVERSE_TAIL_PRESENT" if adverse > 0 else "NO_ADVERSE_TAIL",
        )
        return quality, tags, inside

    def _observe_chapter5_entry_bar(
        self,
        lifecycle: Chapter4SignalEntryLifecycle,
        candle: Candle,
        *,
        at_activation: bool = False,
    ) -> Chapter4SignalEntryLifecycle:
        """Use only contiguous closed 1m evidence in the *actual* entry interval."""
        if (
            lifecycle.state != "CONFIRMED_SIGNAL_ENTRY_ACTIVE"
            or lifecycle.entry_bar_identity_id is None
            or lifecycle.entry_bar_open_time is None
            or lifecycle.entry_bar_close_time is None
        ):
            return lifecycle
        seconds = TIMEFRAME_SECONDS.get(lifecycle.source_timeframe)
        if seconds is None or seconds < 60 or seconds % 60:
            return lifecycle
        if int((candle.close_time - candle.open_time).total_seconds()) != 60:
            return lifecycle
        opened = datetime.fromisoformat(lifecycle.entry_bar_open_time).astimezone(UTC)
        closed = datetime.fromisoformat(lifecycle.entry_bar_close_time).astimezone(UTC)
        candle_open = candle.open_time.astimezone(UTC)
        candle_close = candle.close_time.astimezone(UTC)
        if candle_open < opened or candle_close > closed:
            return lifecycle
        previous = lifecycle.chapter5_entry_bar
        if previous is not None:
            if previous.final_quality is not None:
                return lifecycle
            if previous.last_1m_close_time == candle_close.isoformat():
                return lifecycle
            if previous.last_1m_close_time != candle_open.isoformat():
                return lifecycle
        first = (
            previous.first_1m_open_time if previous is not None
            else candle_open.isoformat()
        )
        count = previous.count + 1 if previous is not None else 1
        open_price = previous.open_price if previous is not None else candle.open
        high_price = max(previous.high_price, candle.high) if previous else candle.high
        low_price = min(previous.low_price, candle.low) if previous else candle.low
        complete = (
            first == opened.isoformat()
            and candle_close == closed
            and count == seconds // 60
            and not at_activation
        )
        quality = None
        inside = None
        tags: tuple[str, ...] = ()
        if complete:
            quality, tags, inside = self._chapter5_entry_quality(
                direction=lifecycle.direction,
                open_price=open_price,
                high_price=high_price,
                low_price=low_price,
                close_price=candle.close,
            )
        evidence = Chapter5EntryBarEvidence(
            bar_identity_id=lifecycle.entry_bar_identity_id,
            open_time=opened.isoformat(),
            close_time=closed.isoformat(),
            first_1m_open_time=first,
            last_1m_close_time=candle_close.isoformat(),
            count=count,
            open_price=open_price,
            high_price=high_price,
            low_price=low_price,
            close_price=candle.close,
            final_quality=quality,
            inside_prior_range=inside,
            evidence_tags=tags,
        )
        return replace(lifecycle, chapter5_entry_bar=evidence)

    def _advance_chapter4_post_entry(
        self,
        lifecycle: Chapter4SignalEntryLifecycle,
        candle: Candle,
    ) -> Chapter4SignalEntryLifecycle:
        post = lifecycle.post_entry_lifecycle
        if (
            lifecycle.state != "CONFIRMED_SIGNAL_ENTRY_ACTIVE"
            or post is None
            or lifecycle.entry_bar_close_time is None
        ):
            return lifecycle
        seconds = TIMEFRAME_SECONDS.get(lifecycle.source_timeframe)
        if seconds is None or seconds < 60 or seconds % 60:
            return lifecycle
        if int((candle.close_time - candle.open_time).total_seconds()) != 60:
            return lifecycle
        try:
            entry_bar_close = datetime.fromisoformat(
                lifecycle.entry_bar_close_time
            ).astimezone(UTC)
        except ValueError:
            return lifecycle
        if candle.close_time.astimezone(UTC) <= entry_bar_close:
            return lifecycle
        interval = self._source_interval(
            lifecycle.source_timeframe,
            candle.open_time,
        )
        if interval is None:
            return lifecycle
        bucket_open, bucket_close = interval
        if bucket_open < entry_bar_close:
            return lifecycle
        bucket_open_iso = bucket_open.isoformat()
        bucket_close_iso = bucket_close.isoformat()
        candle_open_iso = candle.open_time.astimezone(UTC).isoformat()
        candle_close_iso = candle.close_time.astimezone(UTC).isoformat()
        bucket_identity = (
            f"CH4:POST_ENTRY:{lifecycle.source_signal_id}:"
            f"{bucket_open_iso}"
        )
        if any(
            item.bar_identity_id == bucket_identity
            for item in post.completed_bars
        ):
            return lifecycle

        if (
            post.accumulator_bucket_open_time == bucket_open_iso
            and post.accumulator_last_1m_close_time == candle_close_iso
        ):
            return lifecycle

        same_bucket = post.accumulator_bucket_open_time == bucket_open_iso
        contiguous = (
            same_bucket
            and post.accumulator_last_1m_close_time == candle_open_iso
        )
        if contiguous:
            accumulator = replace(
                post,
                accumulator_high=max(
                    post.accumulator_high or candle.high,
                    candle.high,
                ),
                accumulator_low=min(
                    post.accumulator_low or candle.low,
                    candle.low,
                ),
                accumulator_close=candle.close,
                accumulator_last_1m_close_time=candle_close_iso,
                accumulator_count=post.accumulator_count + 1,
            )
        else:
            accumulator = replace(
                post,
                accumulator_bucket_open_time=bucket_open_iso,
                accumulator_bucket_close_time=bucket_close_iso,
                accumulator_open=candle.open,
                accumulator_high=candle.high,
                accumulator_low=candle.low,
                accumulator_close=candle.close,
                accumulator_first_1m_open_time=candle_open_iso,
                accumulator_last_1m_close_time=candle_close_iso,
                accumulator_count=1,
            )

        expected_count = seconds // 60
        complete = (
            accumulator.accumulator_first_1m_open_time == bucket_open_iso
            and accumulator.accumulator_last_1m_close_time == bucket_close_iso
            and accumulator.accumulator_count == expected_count
        )
        if not complete:
            return replace(
                lifecycle,
                post_entry_lifecycle=accumulator,
            )

        bar_identity = bucket_identity
        relation = self._post_entry_relation(
            direction=lifecycle.direction,
            open_price=accumulator.accumulator_open or candle.open,
            close_price=accumulator.accumulator_close or candle.close,
        )
        evidence = Chapter4PostEntryBarEvidence(
            sequence_number=len(accumulator.completed_bars) + 1,
            bar_identity_id=bar_identity,
            bar_index=self._chapter4_bar_index(
                lifecycle,
                bucket_open,
            ),
            open_time=bucket_open_iso,
            close_time=bucket_close_iso,
            open_price=accumulator.accumulator_open or candle.open,
            high_price=accumulator.accumulator_high or candle.high,
            low_price=accumulator.accumulator_low or candle.low,
            close_price=accumulator.accumulator_close or candle.close,
            directional_relation=relation,
            available_at=bucket_close_iso,
            trade_eligible=False,
        )
        first = accumulator.first_follow_through_bar_identity_id
        second = accumulator.second_continuation_bar_identity_id
        if relation == "FAVORABLE_CONTINUATION":
            if first is None:
                first = bar_identity
            elif second is None and first != bar_identity:
                second = bar_identity
        advanced = replace(
            accumulator,
            completed_bars=accumulator.completed_bars + (evidence,),
            first_follow_through_bar_identity_id=first,
            second_continuation_bar_identity_id=second,
            accumulator_bucket_open_time=None,
            accumulator_bucket_close_time=None,
            accumulator_open=None,
            accumulator_high=None,
            accumulator_low=None,
            accumulator_close=None,
            accumulator_first_1m_open_time=None,
            accumulator_last_1m_close_time=None,
            accumulator_count=0,
        )
        return replace(lifecycle, post_entry_lifecycle=advanced)

    async def _load_reversal_outcome_context(
        self,
        *,
        session: AsyncSession,
        metadata: SignalAutomationMetadata,
        imported_context: ReversalOutcomeContext | None = None,
    ) -> ReversalOutcomeContext | None:
        """Load BROOKS-GAP-080 typed Core evidence; never infer it from price."""
        raw_metadata = dict(metadata.analysis_metadata or {})
        stored = raw_metadata.get("brooks_reversal_outcome")
        if isinstance(stored, dict):
            try:
                return ReversalOutcomeContext.from_metadata(stored)
            except (KeyError, TypeError, ValueError):
                logger.warning(
                    "Invalid persisted Brooks reversal-outcome context; failing closed",
                    extra={"signal_id": metadata.signal_id},
                )
                return None

        if imported_context is not None:
            raw_metadata["brooks_reversal_outcome"] = imported_context.to_metadata()
            metadata.analysis_metadata = raw_metadata
            await session.flush()
            return imported_context

        evidence = await session.scalar(
            select(SignalRuleEvidence)
            .where(
                SignalRuleEvidence.signal_id == metadata.signal_id,
                SignalRuleEvidence.rule_id == "BROOKS-GAP-080",
                SignalRuleEvidence.status == "PASS",
            )
            .order_by(SignalRuleEvidence.ordinal)
            .limit(1)
        )
        if evidence is None:
            return None
        pairs = {str(k): str(v) for k, v in evidence.evidence}
        required = {
            "context_id",
            "reversal_origin_id",
            "direction",
            "state",
            "evaluated_index",
            "available_at_index",
            "target_source_ids",
            "initial_stop_source_id",
            "target_plan_id",
            "target_plan_state",
        }
        if not required.issubset(pairs):
            return None
        try:
            context = ReversalOutcomeContext(
                context_id=pairs["context_id"],
                reversal_origin_id=pairs["reversal_origin_id"],
                direction=pairs["direction"],
                state=pairs["state"],
                evaluated_index=int(pairs["evaluated_index"]),
                available_at_index=int(pairs["available_at_index"]),
                target_source_ids=tuple(
                    item for item in pairs["target_source_ids"].split("|") if item
                ),
                initial_stop_source_id=pairs["initial_stop_source_id"],
                target_plan_id=pairs["target_plan_id"],
                target_plan_state=pairs["target_plan_state"],
                trade_eligible=False,
            )
        except (TypeError, ValueError):
            return None
        raw_metadata["brooks_reversal_outcome"] = context.to_metadata()
        metadata.analysis_metadata = raw_metadata
        await session.flush()
        return context

    async def _advance_reversal_outcome(
        self,
        *,
        session: AsyncSession,
        repo: SQLAlchemySignalRepository,
        signal: Signal,
        metadata: SignalAutomationMetadata,
        entry_at: datetime | None,
        candle: Candle,
        context: ReversalOutcomeContext | None,
    ) -> ReversalOutcomeContext | None:
        """Advance only from causal approved evidence available before this candle."""
        if (
            context is None
            or context.state != "PENDING_REVERSAL_OUTCOME"
            or entry_at is None
            or (
                metadata.generation_mode != "LIVE"
                and not _is_hp_bootstrap(metadata)
            )
        ):
            return context

        E = ApprovedMarketEvidence
        evidence_rows = tuple(
            (
                await session.scalars(
                    select(E)
                    .where(
                        E.exchange == metadata.exchange,
                        E.market_type == metadata.market_type,
                        E.symbol == signal.symbol,
                        E.timeframe == metadata.timeframe,
                        E.approved_at > entry_at,
                        E.candle_closed_at > entry_at,
                        E.approved_at <= candle.open_time,
                        E.candle_closed_at <= candle.open_time,
                    )
                    .order_by(E.approved_at, E.source_signal_id)
                )
            ).all()
        )
        current = context
        for evidence in evidence_rows:
            regime = None
            if isinstance(evidence.context, dict):
                regime = evidence.context.get("regime")
            advanced = advance_reversal_outcome_context(
                current,
                observed_direction=evidence.direction,
                observed_always_in=evidence.always_in,
                observed_regime=(None if regime is None else str(regime)),
                transition_available_at=evidence.candle_closed_at.isoformat(),
                transition_source_signal_id=evidence.source_signal_id,
            )
            if advanced.state == current.state:
                continue
            raw_metadata = dict(metadata.analysis_metadata or {})
            raw_metadata["brooks_reversal_outcome"] = advanced.to_metadata()
            metadata.analysis_metadata = raw_metadata
            await repo.append_event(
                signal_id=signal.id,
                event_type="UPDATED",
                metadata={
                    "reason": "BROOKS_GAP_080_REVERSAL_OUTCOME_TRANSITION",
                    "reversal_outcome_context": advanced.to_metadata(),
                    "management_mode": reversal_outcome_management_mode(advanced),
                    "evidence_source_signal_id": evidence.source_signal_id,
                    "evidence_approved_at": evidence.approved_at.isoformat(),
                    "evidence_candle_closed_at": evidence.candle_closed_at.isoformat(),
                },
                created_at=candle.close_time,
            )
            await session.flush()
            return advanced
        return current

    async def _ensure_trade_management_plan(
        self,
        *,
        session: AsyncSession,
        repo: SQLAlchemySignalRepository,
        signal: Signal,
        metadata: SignalAutomationMetadata,
        quality: SignalQualityAssessment | None,
        targets: tuple[SignalTarget, ...],
        target_source_identities: tuple[TargetSourceIdentity, ...] = (),
        stop_source_identity: StopSourceIdentity | None = None,
        target_plan_lifecycle: TargetPlanLifecycle | None = None,
        reversal_outcome_context: ReversalOutcomeContext | None = None,
    ) -> TradeManagementPlan:
        validate_brooks_execution_contract(
            direction=signal.direction,
            targets=targets,
            target_source_identities=target_source_identities,
            stop_source_identity=stop_source_identity,
            target_plan_lifecycle=target_plan_lifecycle,
            reversal_outcome_context=reversal_outcome_context,
        )
        raw_metadata = dict(metadata.analysis_metadata or {})
        stored = raw_metadata.get("trade_management_v6")
        if isinstance(stored, dict):
            try:
                return TradeManagementPlan.from_metadata(stored)
            except (KeyError, TypeError, ValueError):
                logger.warning(
                    "Invalid persisted V6 trade-management plan; rebuilding",
                    extra={"signal_id": signal.id},
                )

        created_event = await session.scalar(
            select(SignalEvent)
            .where(
                SignalEvent.signal_id == signal.id,
                SignalEvent.event_type == "CREATED",
            )
            .order_by(SignalEvent.id)
            .limit(1)
        )
        created_metadata = created_event.event_metadata if created_event is not None else {}
        initial_stop = Decimal(str(created_metadata.get("stop_loss", signal.stop_loss)))
        quality_metadata = dict(quality.extra_metadata or {}) if quality is not None else {}
        if any(target.status == "HIT" for target in targets):
            plan = build_legacy_carryover_plan(
                entry_price=signal.entry_price,
                initial_stop_loss=initial_stop,
                targets=targets,
            )
        else:
            plan = build_trade_management_plan(
                direction=signal.direction,
                entry_price=signal.entry_price,
                initial_stop_loss=initial_stop,
                targets=targets,
                market_regime=quality.market_regime if quality is not None else None,
                rule_ids=metadata.rule_ids,
                context_metadata=quality_metadata,
                reversal_outcome_context=reversal_outcome_context,
            )
        raw_metadata["trade_management_v6"] = plan.to_metadata()
        metadata.analysis_metadata = raw_metadata
        await repo.append_event(
            signal_id=signal.id,
            event_type="UPDATED",
            metadata={
                "reason": "TRADE_MANAGEMENT_PLAN_COMMITTED",
                "trade_management_plan": plan.to_metadata(),
            },
            created_at=utc_now(),
        )
        await session.flush()
        return plan

    def _structural_trailing_stop(
        self,
        *,
        signal: Signal,
        candles: tuple[Candle, ...],
        candle: Candle,
        entry_activated_at: datetime | None,
    ) -> Decimal | None:
        if entry_activated_at is None:
            return None
        history = tuple(
            item for item in candles if entry_activated_at <= item.close_time <= candle.close_time
        )
        left = self.stop_policy.swing_left_bars
        right = self.stop_policy.swing_right_bars
        if len(history) < (left + right + 5):
            return None
        scan = confirm_swings_causally(history, left_bars=left, right_bars=right)
        highs = [item for item in scan.swings if item.kind == "HIGH"]
        lows = [item for item in scan.swings if item.kind == "LOW"]
        tick = self.stop_policy.tick_size_for_symbol(signal.symbol)

        if signal.direction == "LONG":
            if len(highs) < 2 or len(lows) < 2:
                return None
            latest_low, previous_low = lows[-1], lows[-2]
            highs_before = [item for item in highs if item.candle_index < latest_low.candle_index]
            highs_after = [item for item in highs if item.candle_index > latest_low.candle_index]
            if not highs_before or not highs_after or latest_low.price <= previous_low.price:
                return None
            if highs_after[-1].price <= highs_before[-1].price:
                return None
            candidate = latest_low.price - tick
            return candidate if candidate < candle.close else None

        if len(highs) < 2 or len(lows) < 2:
            return None
        latest_high, previous_high = highs[-1], highs[-2]
        lows_before = [item for item in lows if item.candle_index < latest_high.candle_index]
        lows_after = [item for item in lows if item.candle_index > latest_high.candle_index]
        if not lows_before or not lows_after or latest_high.price >= previous_high.price:
            return None
        if lows_after[-1].price >= lows_before[-1].price:
            return None
        candidate = latest_high.price + tick
        return candidate if candidate > candle.close else None

    async def _tighten_active_stop(
        self,
        *,
        service: SignalService,
        signal: Signal,
        targets: tuple[SignalTarget, ...],
        plan: TradeManagementPlan,
        candles: tuple[Candle, ...],
        candle: Candle,
        entry_activated_at: datetime | None,
    ) -> bool:
        desired: Decimal | None = None
        reason: str | None = None
        risk_side = (signal.direction == "LONG" and signal.stop_loss < signal.entry_price) or (
            signal.direction == "SHORT" and signal.stop_loss > signal.entry_price
        )

        if risk_side and self._breakeven_ready(targets, plan):
            desired = signal.entry_price
            reason = "BREAKEVEN_AFTER_SCALE_OUT"
        elif risk_side and self._entry_tested_then_resumed(
            signal=signal,
            plan=plan,
            candles=candles,
            candle=candle,
            entry_activated_at=entry_activated_at,
        ):
            desired = signal.entry_price
            reason = "BREAKEVEN_STRUCTURE_CONFIRMED"

        structural = self._structural_trailing_stop(
            signal=signal,
            candles=candles,
            candle=candle,
            entry_activated_at=entry_activated_at,
        )
        if structural is not None:
            if signal.direction == "LONG":
                if structural > signal.stop_loss and (desired is None or structural > desired):
                    desired = structural
                    reason = "STRUCTURAL_TRAIL"
            elif structural < signal.stop_loss and (desired is None or structural < desired):
                desired = structural
                reason = "STRUCTURAL_TRAIL"

        if desired is None or reason is None:
            return False
        updated = await service.update_stop_loss(signal.id, stop_loss=desired, reason=reason)
        signal.stop_loss = updated.stop_loss
        return True

    async def _close_runner_on_reversal(
        self, *, session, repo, signal, metadata, state, targets, plan, candle, runner_event
    ):
        fraction = open_runner_fraction(plan, targets, runner_event)
        if fraction <= 0 or state.entry_activated_at is None:
            return None
        evidence = await find_reversal_evidence(
            session, signal=signal, metadata=metadata,
            entry_at=state.entry_activated_at, candle=candle,
        )
        if evidence is None:
            return None
        return_pct = _return_pct(
            direction=signal.direction, entry=signal.entry_price,
            price=candle.close, leverage=signal.leverage,
        )
        event = await repo.append_event(
            signal_id=signal.id, event_type=RUNNER_EVENT,
            metadata={
                "exit_fraction": str(fraction),
                "exit_price": str(candle.close),
                "return_pct": str(return_pct),
                "weighted_return_pct": str(fraction * return_pct),
                "remaining_fraction": str(open_position_fraction(plan, targets) - fraction),
                "evidence_source_signal_id": evidence.source_signal_id,
                "evidence_approved_at": evidence.approved_at.isoformat(),
                "evidence_candle_closed_at": evidence.candle_closed_at.isoformat(),
                "timeframe": evidence.timeframe,
                "always_in": evidence.always_in,
                "policy_version": plan.policy_version,
            },
            created_at=candle.close_time,
        )
        if open_position_fraction(plan, targets, event) == 0:
            total = _aggregate_close_pct(
                signal=signal, targets=targets, terminal_price=candle.close,
                plan=plan, runner_event=event,
            )
            await SignalService(repo, clock=lambda: candle.close_time).close_signal(
                signal.id, profit_loss=total,
            )
            state.state = "COMPLETE"
        return event

    async def _process_item(
        self,
        item: LifecycleItem,
        candles: tuple[Candle, ...],
    ) -> dict[str, bool]:
        if not candles:
            return {"changed": False, "ambiguous": False}

        changed = False
        market_refresh = False
        ambiguous = False
        message_event_id: int | None = None
        lifecycle_state = "WAITING_ENTRY"
        ambiguous_reason: str | None = None

        async with self.database.session() as session, session.begin():
            await session.execute(
                insert(SignalLifecycleState)
                .values(signal_id=item.signal.id, state="WAITING_ENTRY")
                .on_conflict_do_nothing(index_elements=[SignalLifecycleState.signal_id])
            )
            state = await session.scalar(
                select(SignalLifecycleState)
                .where(SignalLifecycleState.signal_id == item.signal.id)
                .with_for_update()
            )
            if state is None or state.state in {"COMPLETE", "AMBIGUOUS"}:
                return {
                    "changed": False,
                    "ambiguous": state is not None and state.state == "AMBIGUOUS",
                }

            signal = await session.scalar(
                select(Signal).where(Signal.id == item.signal.id).with_for_update()
            )
            if signal is None or signal.status != "OPEN":
                return {"changed": False, "ambiguous": False}
            metadata = await session.get(SignalAutomationMetadata, signal.id)
            targets = tuple(
                (
                    await session.scalars(
                        select(SignalTarget)
                        .where(SignalTarget.signal_id == signal.id)
                        .order_by(SignalTarget.target_number)
                    )
                ).all()
            )
            repo = SQLAlchemySignalRepository(session)
            service = SignalService(repo)
            if metadata is None:
                return {"changed": False, "ambiguous": False}
            bootstrap_shadow = _is_hp_bootstrap(metadata)
            quality = await session.scalar(
                select(SignalQualityAssessment).where(
                    SignalQualityAssessment.signal_id == signal.id
                )
            )
            (
                target_source_identities,
                stop_source_identity,
                target_plan_lifecycle,
                imported_reversal_outcome_context,
            ) = self._load_core_execution_contract(metadata=metadata)
            chapter4_lifecycle = self._load_chapter4_lifecycle(metadata)
            reversal_outcome_context = await self._load_reversal_outcome_context(
                session=session,
                metadata=metadata,
                imported_context=imported_reversal_outcome_context,
            )
            plan = await self._ensure_trade_management_plan(
                session=session,
                repo=repo,
                signal=signal,
                metadata=metadata,
                quality=quality,
                targets=targets,
                target_source_identities=target_source_identities,
                stop_source_identity=stop_source_identity,
                target_plan_lifecycle=target_plan_lifecycle,
                reversal_outcome_context=reversal_outcome_context,
            )

            runner_event = await latest_runner_event(session, signal.id)

            floor = state.last_processed_candle_close or max(
                signal.created_at.astimezone(UTC), self.cutover_at
            )
            available = tuple(c for c in candles if c.close_time > floor)
            if not available:
                return {"changed": False, "ambiguous": False}

            if state.last_processed_candle_close is None and floor < candles[0].open_time:
                ambiguous_reason = "MONITORING_HISTORY_GAP"
                if chapter4_lifecycle is not None:
                    chapter4_lifecycle = self._terminate_chapter4_unfilled(
                        chapter4_lifecycle,
                        ambiguous_reason,
                    )
                    self._store_chapter4_lifecycle(
                        metadata,
                        chapter4_lifecycle,
                    )
                message_event_id = await self._mark_ambiguous(
                    session=session,
                    repo=repo,
                    signal=signal,
                    state=state,
                    reason=ambiguous_reason,
                    candle=candles[0],
                )
                lifecycle_state = "AMBIGUOUS"
                changed = True
                ambiguous = True
            else:
                for candle in available:
                    state.last_market_price = candle.close
                    market_refresh = market_refresh or (
                        state.state == "ACTIVE"
                        and _should_refresh_live_caption(
                            signal_id=signal.id,
                            candle_close=candle.close_time,
                        )
                    )
                    if state.state == "WAITING_ENTRY":
                        entry_touched = candle.low <= signal.entry_price <= candle.high
                        touched_stop = self._stop_touched(signal, candle)
                        if touched_stop and not entry_touched:
                            if chapter4_lifecycle is not None:
                                chapter4_lifecycle = (
                                    self._terminate_chapter4_unfilled(
                                        chapter4_lifecycle,
                                        "PENDING_ENTRY_STRUCTURAL_STOP_TOUCHED",
                                    )
                                )
                                self._store_chapter4_lifecycle(
                                    metadata,
                                    chapter4_lifecycle,
                                )
                            message_event_id = await self._cancel_invalid_pending(
                                repo=repo, signal=signal, state=state, candle=candle
                            )
                            lifecycle_state = "COMPLETE"
                            changed = True
                            break
                        if not entry_touched:
                            state.last_processed_candle_close = candle.close_time
                            state.updated_at = utc_now()
                            continue
                        if chapter4_lifecycle is not None:
                            chapter4_lifecycle = self._promote_chapter4_entry(
                                chapter4_lifecycle,
                                candle,
                                prior_closed_1m=tuple(
                                    prior for prior in candles
                                    if prior.close_time <= candle.open_time
                                ),
                            )
                            self._store_chapter4_lifecycle(
                                metadata,
                                chapter4_lifecycle,
                            )
                        event = await repo.append_event(
                            signal_id=signal.id,
                            event_type="ENTRY_ACTIVATED",
                            metadata={
                                "entry_price": str(signal.entry_price),
                                "candle_close": candle.close_time.isoformat(),
                                "reversal_outcome_state": (
                                    reversal_outcome_context.state
                                    if reversal_outcome_context is not None
                                    else None
                                ),
                                "reversal_outcome_management_mode": (
                                    reversal_outcome_management_mode(reversal_outcome_context)
                                ),
                            },
                            created_at=candle.close_time,
                        )
                        state.state = "ACTIVE"
                        state.entry_activated_at = candle.close_time
                        if bootstrap_shadow:
                            _set_hp_bootstrap_state(
                                metadata,
                                state="BOOTSTRAP_ENTRY_ACTIVATED",
                                hp_eligible=False,
                            )
                        changed = True
                        message_event_id = event.id
                        touched_target = any(
                            self._target_touched(signal.direction, target.target_price, candle)
                            for target in targets
                            if target.status == "PENDING"
                        )
                        if touched_target or touched_stop:
                            ambiguous_reason = "ENTRY_AND_EXIT_SAME_1M_CANDLE"
                            message_event_id = await self._mark_ambiguous(
                                session=session,
                                repo=repo,
                                signal=signal,
                                state=state,
                                reason=ambiguous_reason,
                                candle=candle,
                            )
                            lifecycle_state = "AMBIGUOUS"
                            ambiguous = True
                            break
                        state.last_processed_candle_close = candle.close_time
                        state.updated_at = utc_now()
                        lifecycle_state = "ACTIVE"
                        continue

                    if chapter4_lifecycle is not None:
                        entry_observed = self._observe_chapter5_entry_bar(
                            chapter4_lifecycle,
                            candle,
                        )
                        advanced_chapter4 = self._advance_chapter4_post_entry(
                            entry_observed,
                            candle,
                        )
                        if advanced_chapter4 != chapter4_lifecycle:
                            chapter4_lifecycle = advanced_chapter4
                            self._store_chapter4_lifecycle(
                                metadata,
                                chapter4_lifecycle,
                            )

                    reversal_outcome_context = await self._advance_reversal_outcome(
                        session=session,
                        repo=repo,
                        signal=signal,
                        metadata=metadata,
                        entry_at=state.entry_activated_at,
                        candle=candle,
                        context=reversal_outcome_context,
                    )

                    pending = [t for t in targets if t.status == "PENDING"]
                    touched_targets = [
                        target
                        for target in pending
                        if self._target_touched(
                            signal.direction,
                            target.target_price,
                            candle,
                        )
                    ]
                    touched_stop = self._stop_touched(signal, candle)
                    if touched_stop and touched_targets:
                        ambiguous_reason = "STOP_AND_TARGET_SAME_1M_CANDLE"
                        message_event_id = await self._mark_ambiguous(
                            session=session,
                            repo=repo,
                            signal=signal,
                            state=state,
                            reason=ambiguous_reason,
                            candle=candle,
                        )
                        lifecycle_state = "AMBIGUOUS"
                        changed = True
                        ambiguous = True
                        break

                    if touched_targets:
                        for target in touched_targets:
                            pnl = _return_pct(
                                direction=signal.direction,
                                entry=signal.entry_price,
                                price=target.target_price,
                                leverage=signal.leverage,
                            )
                            exit_fraction = plan.fraction_for_target(target.target_number)
                            remaining_after = max(
                                Decimal("0"),
                                open_position_fraction(plan, targets, runner_event) - exit_fraction,
                            )
                            action = (
                                "REFERENCE_LEVEL_ONLY"
                                if exit_fraction == 0
                                else (
                                    "FINAL_PLANNED_EXIT"
                                    if remaining_after == 0
                                    else "SCALE_OUT_AND_RUN"
                                )
                            )
                            hit = await service.hit_target(
                                signal.id,
                                target.id,
                                profit_loss=pnl,
                                event_metadata={
                                    "policy_version": POLICY_VERSION,
                                    "context_class": plan.context_class,
                                    "management_action": action,
                                    "exit_fraction": str(exit_fraction),
                                    "remaining_fraction": str(remaining_after),
                                    "reversal_outcome_state": (
                                        reversal_outcome_context.state
                                        if reversal_outcome_context is not None
                                        else None
                                    ),
                                    "reversal_outcome_management_mode": (
                                        reversal_outcome_management_mode(reversal_outcome_context)
                                    ),
                                },
                            )
                            changed = True
                            target.status = hit.status
                            target.hit_at = hit.hit_at
                            target.profit_loss = hit.profit_loss
                            last_event = await session.scalar(
                                select(SignalEvent)
                                .where(
                                    SignalEvent.signal_id == signal.id,
                                    SignalEvent.event_type == "TARGET_HIT",
                                )
                                .order_by(SignalEvent.id.desc())
                                .limit(1)
                            )
                            if last_event is not None:
                                message_event_id = last_event.id
                        if open_position_fraction(plan, targets, runner_event) == 0:
                            aggregate = _aggregate_close_pct(
                                signal=signal,
                                targets=targets,
                                terminal_price=touched_targets[-1].target_price,
                                plan=plan, runner_event=runner_event,
                            )
                            await service.close_signal(signal.id, profit_loss=aggregate)
                            state.state = "COMPLETE"
                            lifecycle_state = "COMPLETE"
                            last_event = await session.scalar(
                                select(SignalEvent)
                                .where(SignalEvent.signal_id == signal.id)
                                .order_by(SignalEvent.id.desc())
                                .limit(1)
                            )
                            if last_event is not None:
                                message_event_id = last_event.id
                            state.last_processed_candle_close = candle.close_time
                            state.updated_at = utc_now()
                            break

                    elif touched_stop:
                        pnl = _aggregate_close_pct(
                            signal=signal,
                            targets=targets,
                            terminal_price=signal.stop_loss,
                            plan=plan, runner_event=runner_event,
                        )
                        stop_event = await repo.append_event(
                            signal_id=signal.id,
                            event_type="STOP_HIT",
                            metadata={
                                "stop_loss": str(signal.stop_loss),
                                "profit_loss": str(pnl),
                                "remaining_fraction": str(open_position_fraction(plan, targets, runner_event)),
                                "policy_version": POLICY_VERSION,
                                "candle_close": candle.close_time.isoformat(),
                            },
                            created_at=candle.close_time,
                        )
                        message_event_id = stop_event.id
                        await service.close_signal(signal.id, profit_loss=pnl)
                        state.state = "COMPLETE"
                        lifecycle_state = "COMPLETE"
                        changed = True
                        state.last_processed_candle_close = candle.close_time
                        state.updated_at = utc_now()
                        break

                    # Independent exit; stop/target ambiguity and fills retain priority.
                    new_runner_event = await self._close_runner_on_reversal(
                        session=session, repo=repo, signal=signal, metadata=metadata,
                        state=state, targets=targets, plan=plan, candle=candle,
                        runner_event=runner_event,
                    )
                    if new_runner_event is not None:
                        runner_event = new_runner_event
                        message_event_id = runner_event.id
                        changed = True
                        if state.state == "COMPLETE":
                            lifecycle_state = "COMPLETE"
                            state.last_processed_candle_close = candle.close_time
                            state.updated_at = utc_now()
                            break

                    # New Brooks stop management applies only to the active
                    # Binance Futures production domain. Legacy Spot lifecycle
                    # compatibility deliberately preserves its historical behavior.
                    stop_changed = False
                    if (
                        metadata is not None
                        and metadata.exchange == "binance"
                        and metadata.market_type in {"futures", "linear"}
                    ):
                        stop_changed = await self._tighten_active_stop(
                            service=service,
                            signal=signal,
                            targets=targets,
                            plan=plan,
                            candles=candles,
                            candle=candle,
                            entry_activated_at=state.entry_activated_at,
                        )
                    if stop_changed:
                        changed = True
                        last_event = await session.scalar(
                            select(SignalEvent)
                            .where(
                                SignalEvent.signal_id == signal.id,
                                SignalEvent.event_type == "STOP_LOSS_UPDATED",
                            )
                            .order_by(SignalEvent.id.desc())
                            .limit(1)
                        )
                        if last_event is not None:
                            message_event_id = last_event.id

                    state.last_processed_candle_close = candle.close_time
                    state.updated_at = utc_now()
                    lifecycle_state = state.state

            if bootstrap_shadow and state.state in {"COMPLETE", "AMBIGUOUS"}:
                terminal_outcome = await session.scalar(
                    select(SignalEvent)
                    .where(
                        SignalEvent.signal_id == signal.id,
                        SignalEvent.event_type.in_(("TARGET_HIT", "STOP_HIT")),
                    )
                    .order_by(SignalEvent.created_at.desc(), SignalEvent.id.desc())
                    .limit(1)
                )
                eligible = state.state == "COMPLETE" and terminal_outcome is not None
                _set_hp_bootstrap_state(
                    metadata,
                    state=(
                        "BOOTSTRAP_TERMINAL_ELIGIBLE"
                        if eligible
                        else "BOOTSTRAP_TERMINAL_INELIGIBLE"
                    ),
                    hp_eligible=eligible,
                )
            if message_event_id is not None and not bootstrap_shadow:
                state.last_message_event_id = message_event_id

        message_delivered = False

        if (changed or market_refresh) and not bootstrap_shadow:
            message_delivered = await self._refresh_message(
                item.signal.id,
                lifecycle_state,
                ambiguous_reason,
            )

        if changed and message_delivered:
            await self._clear_message_pending(item.signal.id)
        return {"changed": changed, "ambiguous": ambiguous}

    async def _cancel_invalid_pending(
        self, *, repo: SQLAlchemySignalRepository, signal: Signal,
        state: SignalLifecycleState, candle: Candle,
    ) -> int:
        now = candle.close_time
        cancelled_targets = await repo.cancel_pending_targets(signal.id, changed_at=now)
        await repo.update_signal(
            signal.id,
            values={"status": "CANCELLED", "profit_loss": None, "closed_at": now},
            updated_at=now,
        )
        event = await repo.append_event(
            signal_id=signal.id, event_type="CANCELLED",
            metadata={
                "reason": "PENDING_ENTRY_STRUCTURAL_STOP_TOUCHED",
                "stop_loss": str(signal.stop_loss),
                "cancelled_targets": cancelled_targets,
                "candle_open": candle.open_time.isoformat(),
                "candle_close": candle.close_time.isoformat(),
            },
            created_at=now,
        )
        state.state = "COMPLETE"
        state.last_processed_candle_close = candle.close_time
        state.last_market_price = candle.close
        state.updated_at = utc_now()
        return event.id

    async def _mark_ambiguous(
        self,
        *,
        session: AsyncSession,
        repo: SQLAlchemySignalRepository,
        signal: Signal,
        state: SignalLifecycleState,
        reason: str,
        candle: Candle,
    ) -> int:
        now = candle.close_time
        await repo.cancel_pending_targets(signal.id, changed_at=now)
        await repo.update_signal(
            signal.id,
            values={"status": "CANCELLED", "profit_loss": None, "closed_at": now},
            updated_at=now,
        )
        event = await repo.append_event(
            signal_id=signal.id,
            event_type="OUTCOME_AMBIGUOUS",
            metadata={
                "reason": reason,
                "candle_open": candle.open_time.isoformat(),
                "candle_close": candle.close_time.isoformat(),
                "high": str(candle.high),
                "low": str(candle.low),
            },
            created_at=now,
        )
        state.state = "AMBIGUOUS"
        state.ambiguous_reason = reason
        state.last_processed_candle_close = candle.close_time
        state.updated_at = utc_now()
        return event.id

    async def _clear_message_pending(self, signal_id: int) -> None:
        async with self.database.session() as session, session.begin():
            state = await session.get(SignalLifecycleState, signal_id)
            if state is not None:
                state.last_message_event_id = None
                state.updated_at = utc_now()

    async def _refresh_message(
        self,
        signal_id: int,
        lifecycle_state: str,
        ambiguous_reason: str | None,
    ) -> bool:
        async with self.database.session() as session:
            signal = await session.get(Signal, signal_id)
            metadata = await session.get(
                SignalAutomationMetadata,
                signal_id,
            )
            state = await session.get(
                SignalLifecycleState,
                signal_id,
            )
            quality = await session.scalar(
                select(SignalQualityAssessment).where(
                    SignalQualityAssessment.signal_id == signal_id
                )
            )
            delivery = await session.scalar(
                select(SignalDelivery).where(
                    SignalDelivery.signal_id == signal_id,
                    SignalDelivery.channel_kind == "TELEGRAM_VIP",
                    SignalDelivery.destination_id == str(self.vip_channel_id),
                    SignalDelivery.status == "SENT",
                )
            )
            targets = tuple(
                (
                    await session.scalars(
                        select(SignalTarget)
                        .where(SignalTarget.signal_id == signal_id)
                        .order_by(SignalTarget.target_number)
                    )
                ).all()
            )
            latest_stop_update = await session.scalar(
                select(SignalEvent)
                .where(
                    SignalEvent.signal_id == signal_id,
                    SignalEvent.event_type == "STOP_LOSS_UPDATED",
                )
                .order_by(SignalEvent.id.desc())
                .limit(1)
            )
            latest_target_hit = await session.scalar(
                select(SignalEvent)
                .where(
                    SignalEvent.signal_id == signal_id,
                    SignalEvent.event_type == "TARGET_HIT",
                )
                .order_by(SignalEvent.id.desc())
                .limit(1)
            )
            latest_stop_hit = await session.scalar(
                select(SignalEvent)
                .where(
                    SignalEvent.signal_id == signal_id,
                    SignalEvent.event_type == "STOP_HIT",
                )
                .order_by(SignalEvent.id.desc())
                .limit(1)
            )
            runner_event = await latest_runner_event(session, signal_id)
            stop_management_note = None
            if latest_stop_update is not None:
                stop_metadata = latest_stop_update.event_metadata or {}
                stop_reason = stop_metadata.get("reason")
                new_stop = stop_metadata.get("new_stop_loss")
                level = f" at {new_stop}" if new_stop is not None else ""
                if stop_reason in {
                    "BREAKEVEN",
                    "BREAKEVEN_AFTER_SCALE_OUT",
                    "BREAKEVEN_STRUCTURE_CONFIRMED",
                }:
                    stop_management_note = f"🛡 Stop moved to breakeven{level} ✅"
                elif stop_reason == "STRUCTURAL_TRAIL":
                    stop_management_note = f"🔒 Stop trailed{level} ✅"

            trade_management_note = None
            if latest_target_hit is not None:
                target_metadata = latest_target_hit.event_metadata or {}
                action = target_metadata.get("management_action")
                target_number = target_metadata.get("target_number")
                exit_fraction = Decimal(str(target_metadata.get("exit_fraction", "0")))
                remaining_fraction = Decimal(str(target_metadata.get("remaining_fraction", "1")))
                if action == "REFERENCE_LEVEL_ONLY":
                    trade_management_note = f"🧭 TP{target_number} reached • no early scale-out"
                elif action == "FINAL_PLANNED_EXIT":
                    trade_management_note = f"✅ TP{target_number}: final planned size closed"
                elif action == "SCALE_OUT_AND_RUN":
                    exit_pct = (exit_fraction * Decimal("100")).quantize(Decimal("1"))
                    remaining_pct = (remaining_fraction * Decimal("100")).quantize(Decimal("1"))
                    trade_management_note = (
                        f"✂️ TP{target_number}: {exit_pct}% secured • {remaining_pct}% runner active"
                    )
            if (
                signal is None
                or metadata is None
                or delivery is None
                or not delivery.external_message_id
            ):
                return False
            if runner_event is not None:
                fraction = Decimal(runner_event.event_metadata["exit_fraction"])
                trade_management_note = (
                    f"🏁 Runner {fraction * 100}% closed • confirmed Always-In reversal"
                )
            # Terminal signals are immutable after the final
            # Telegram lifecycle update has been delivered.
            #
            # CLOSED/CANCELLED signals may still be refreshed only
            # while their final lifecycle event is pending, so a
            # failed Telegram edit can be retried safely.
            if signal.status in {"CLOSED", "CANCELLED"} and (
                state is None or state.last_message_event_id is None
            ):
                return True

            caption = render_live_caption(
                signal=signal,
                metadata=metadata,
                targets=targets,
                lifecycle_state=lifecycle_state,
                ambiguous_reason=ambiguous_reason,
                last_market_price=(state.last_market_price if state is not None else None),
                entry_activated=(state is not None and state.entry_activated_at is not None),
                quality_grade=(quality.quality_grade if quality is not None else None),
                final_score=(quality.final_score if quality is not None else None),
                confidence=(quality.confidence if quality is not None else None),
                market_regime=(quality.market_regime if quality is not None else None),
                stop_management_note=stop_management_note,
                trade_management_note=trade_management_note,
                terminal_stop_hit=latest_stop_hit is not None,
                runner_reversal=runner_event is not None,
            )
        try:
            await edit_live_signal_message(
                self.bot,
                chat_id=self.vip_channel_id,
                message_id=int(delivery.external_message_id),
                caption=caption,
            )

        except BadRequest as exc:
            if "message is not modified" in str(exc).lower():
                return True

            logger.error(
                "Telegram VIP message edit rejected",
                extra={
                    "event": "signal_lifecycle_message_edit_rejected",
                    "signal_id": signal_id,
                    "message_id": delivery.external_message_id,
                    "error": str(exc),
                },
            )
            return False

        except RetryAfter as exc:
            logger.warning(
                "Telegram VIP message edit rate limited",
                extra={
                    "event": "signal_lifecycle_message_edit_rate_limited",
                    "signal_id": signal_id,
                    "message_id": delivery.external_message_id,
                    "retry_after": str(
                        getattr(
                            exc,
                            "retry_after",
                            "",
                        )
                    ),
                },
            )
            return False

        except (TimedOut, NetworkError) as exc:
            logger.warning(
                "Telegram VIP message edit temporarily failed",
                extra={
                    "event": "signal_lifecycle_message_edit_transient_failed",
                    "signal_id": signal_id,
                    "message_id": delivery.external_message_id,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            return False

        except TelegramError as exc:
            logger.error(
                "Telegram VIP message edit failed",
                extra={
                    "event": "signal_lifecycle_message_edit_failed",
                    "signal_id": signal_id,
                    "message_id": delivery.external_message_id,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            return False

        return True

    @staticmethod
    def _target_touched(direction: str, target: Decimal, candle: Candle) -> bool:
        return candle.high >= target if direction == "LONG" else candle.low <= target

    @staticmethod
    def _stop_touched(signal: Signal, candle: Candle) -> bool:
        if signal.direction == "LONG":
            return candle.low <= signal.stop_loss
        return candle.high >= signal.stop_loss

class ColdStartBootstrapLifecycleService(LiveSignalLifecycleService):
    """Track only authorized HP cold-start SHADOW observations.

    This service deliberately excludes LIVE/VIP rows and disables Telegram
    message retry/update work. It reuses the causal 1m lifecycle machinery so
    bootstrap realized-R evidence has the same entry/exit semantics as the
    production lifecycle without enabling production operations.
    """

    def __init__(
        self,
        *,
        database,
        provider,
        bot: Bot,
        candle_limit: int,
    ) -> None:
        super().__init__(
            database=database,
            provider=provider,
            bot=bot,
            vip_channel_id=0,
            cutover_at=datetime(1970, 1, 1, tzinfo=UTC),
            candle_limit=candle_limit,
        )

    async def _retry_pending_message_updates(self) -> int:
        return 0

    async def _load_items(self) -> tuple[LifecycleItem, ...]:
        async with self.database.session() as session:
            bootstrap = SignalAutomationMetadata.analysis_metadata["hp_cold_start_bootstrap"]
            statement = (
                select(Signal, SignalAutomationMetadata, SignalDelivery)
                .join(
                    SignalAutomationMetadata,
                    SignalAutomationMetadata.signal_id == Signal.id,
                )
                .outerjoin(
                    SignalDelivery,
                    SignalDelivery.signal_id == Signal.id,
                )
                .where(
                    Signal.status == "OPEN",
                    SignalAutomationMetadata.producer == "BROOKS",
                    Signal.publication_scope == "INTERNAL",
                    SignalAutomationMetadata.generation_mode == "SHADOW",
                    SignalAutomationMetadata.counts_toward_performance.is_(False),
                    bootstrap["bootstrap"].astext == "true",
                    bootstrap["policy_id"].astext == HP_COLD_START_BOOTSTRAP_POLICY_ID,
                )
                .order_by(Signal.id)
            )
            rows = (await session.execute(statement)).all()
            result: list[LifecycleItem] = []
            for signal, metadata, delivery in rows:
                targets = tuple(
                    (
                        await session.scalars(
                            select(SignalTarget)
                            .where(SignalTarget.signal_id == signal.id)
                            .order_by(SignalTarget.target_number)
                        )
                    ).all()
                )
                result.append(
                    LifecycleItem(
                        signal=signal,
                        metadata=metadata,
                        delivery=delivery,
                        targets=targets,
                    )
                )
            return tuple(result)

