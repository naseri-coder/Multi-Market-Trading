from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Protocol
from app.modules.market_data.entities import MarketSnapshot
from app.modules.signal_automation.entities import BrooksRuleEvidence

REVERSAL_OUTCOME_RULE_ID = "BROOKS-GAP-" + "080"

@dataclass(frozen=True, slots=True)
class EntryExecutionIntent:
    """WAVE_14 typed entry-method identity; persistence/database schema is unchanged."""

    entry_method: str
    entry_trigger_semantic: str
    reference_price: Decimal | None
    economic_opportunity_id: str
    anticipatory: bool
    confirmation_state: str

    def __post_init__(self) -> None:
        allowed = {
            "STOP_TRIGGER_CONFIRMATION",
            "LIMIT_OR_MARKET_FADE",
            "LIMIT_OR_MARKET_ANTICIPATION",
            "MARKET_OR_LIMIT_ANTICIPATION",
        }
        if self.entry_method not in allowed:
            raise ValueError("invalid Brooks entry method")
        if not self.entry_trigger_semantic:
            raise ValueError("entry trigger semantic is required")
        if not self.economic_opportunity_id:
            raise ValueError("economic opportunity identity is required")


@dataclass(frozen=True, slots=True)
class Chapter4PostEntryBarEvidence:
    """Diagnostic Book-1/Chapter-4 evidence for one finalized post-entry source bar."""

    sequence_number: int
    bar_identity_id: str
    bar_index: int | None
    open_time: str
    close_time: str
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    directional_relation: str
    available_at: str
    trade_eligible: bool = False

    def __post_init__(self) -> None:
        if self.sequence_number < 1:
            raise ValueError("post-entry sequence_number must be positive")
        if not self.bar_identity_id.strip():
            raise ValueError("post-entry bar identity is required")
        if self.bar_index is not None and self.bar_index < 0:
            raise ValueError("post-entry bar_index must be non-negative")
        if self.directional_relation not in {
            "FAVORABLE_CONTINUATION",
            "NEUTRAL_OR_SIDEWAYS",
            "ADVERSE",
        }:
            raise ValueError("invalid post-entry directional relation")
        if self.trade_eligible:
            raise ValueError("Chapter-4 post-entry evidence is diagnostic only")

    def to_metadata(self) -> dict[str, object]:
        return {
            "sequence_number": self.sequence_number,
            "bar_identity_id": self.bar_identity_id,
            "bar_index": self.bar_index,
            "open_time": self.open_time,
            "close_time": self.close_time,
            "open_price": str(self.open_price),
            "high_price": str(self.high_price),
            "low_price": str(self.low_price),
            "close_price": str(self.close_price),
            "directional_relation": self.directional_relation,
            "available_at": self.available_at,
            "trade_eligible": False,
        }

    @classmethod
    def from_metadata(
        cls, value: Mapping[str, object]
    ) -> "Chapter4PostEntryBarEvidence":
        return cls(
            sequence_number=int(value["sequence_number"]),
            bar_identity_id=str(value["bar_identity_id"]),
            bar_index=None if value.get("bar_index") is None else int(value["bar_index"]),
            open_time=str(value["open_time"]),
            close_time=str(value["close_time"]),
            open_price=Decimal(str(value["open_price"])),
            high_price=Decimal(str(value["high_price"])),
            low_price=Decimal(str(value["low_price"])),
            close_price=Decimal(str(value["close_price"])),
            directional_relation=str(value["directional_relation"]),
            available_at=str(value["available_at"]),
            trade_eligible=False,
        )


@dataclass(frozen=True, slots=True)
class Chapter4PostEntryLifecycle:
    """Book-1/Chapter-4 post-actual-entry diagnostic lifecycle."""

    entry_bar_identity_id: str
    source_timeframe: str
    direction: str
    completed_bars: tuple[Chapter4PostEntryBarEvidence, ...] = ()
    first_follow_through_bar_identity_id: str | None = None
    second_continuation_bar_identity_id: str | None = None
    accumulator_bucket_open_time: str | None = None
    accumulator_bucket_close_time: str | None = None
    accumulator_open: Decimal | None = None
    accumulator_high: Decimal | None = None
    accumulator_low: Decimal | None = None
    accumulator_close: Decimal | None = None
    accumulator_first_1m_open_time: str | None = None
    accumulator_last_1m_close_time: str | None = None
    accumulator_count: int = 0
    trade_eligible: bool = False

    def __post_init__(self) -> None:
        if not self.entry_bar_identity_id.strip() or not self.source_timeframe.strip():
            raise ValueError("post-entry entry-bar identity/timeframe is required")
        if self.direction not in {"LONG", "SHORT"}:
            raise ValueError("post-entry direction must be LONG or SHORT")
        if self.accumulator_count < 0:
            raise ValueError("post-entry accumulator count cannot be negative")
        if self.trade_eligible:
            raise ValueError("Chapter-4 post-entry lifecycle is diagnostic only")
        expected = tuple(range(1, len(self.completed_bars) + 1))
        actual = tuple(item.sequence_number for item in self.completed_bars)
        if actual != expected:
            raise ValueError("post-entry evidence sequence must be contiguous")
        ids = {item.bar_identity_id for item in self.completed_bars}
        for identity in (
            self.first_follow_through_bar_identity_id,
            self.second_continuation_bar_identity_id,
        ):
            if identity is not None and identity not in ids:
                raise ValueError(
                    "follow-through identity must reference completed evidence"
                )

    def to_metadata(self) -> dict[str, object]:
        return {
            "entry_bar_identity_id": self.entry_bar_identity_id,
            "source_timeframe": self.source_timeframe,
            "direction": self.direction,
            "completed_bars": [item.to_metadata() for item in self.completed_bars],
            "first_follow_through_bar_identity_id": (
                self.first_follow_through_bar_identity_id
            ),
            "second_continuation_bar_identity_id": (
                self.second_continuation_bar_identity_id
            ),
            "accumulator_bucket_open_time": self.accumulator_bucket_open_time,
            "accumulator_bucket_close_time": self.accumulator_bucket_close_time,
            "accumulator_open": (
                None if self.accumulator_open is None else str(self.accumulator_open)
            ),
            "accumulator_high": (
                None if self.accumulator_high is None else str(self.accumulator_high)
            ),
            "accumulator_low": (
                None if self.accumulator_low is None else str(self.accumulator_low)
            ),
            "accumulator_close": (
                None if self.accumulator_close is None else str(self.accumulator_close)
            ),
            "accumulator_first_1m_open_time": self.accumulator_first_1m_open_time,
            "accumulator_last_1m_close_time": self.accumulator_last_1m_close_time,
            "accumulator_count": self.accumulator_count,
            "trade_eligible": False,
        }

    @classmethod
    def from_metadata(
        cls, value: Mapping[str, object]
    ) -> "Chapter4PostEntryLifecycle":
        raw_bars = value.get("completed_bars", ())
        if not isinstance(raw_bars, (list, tuple)):
            raise ValueError("completed post-entry bars must be a sequence")
        return cls(
            entry_bar_identity_id=str(value["entry_bar_identity_id"]),
            source_timeframe=str(value["source_timeframe"]),
            direction=str(value["direction"]),
            completed_bars=tuple(
                Chapter4PostEntryBarEvidence.from_metadata(item)
                for item in raw_bars
                if isinstance(item, Mapping)
            ),
            first_follow_through_bar_identity_id=(
                None
                if value.get("first_follow_through_bar_identity_id") is None
                else str(value["first_follow_through_bar_identity_id"])
            ),
            second_continuation_bar_identity_id=(
                None
                if value.get("second_continuation_bar_identity_id") is None
                else str(value["second_continuation_bar_identity_id"])
            ),
            accumulator_bucket_open_time=(
                None
                if value.get("accumulator_bucket_open_time") is None
                else str(value["accumulator_bucket_open_time"])
            ),
            accumulator_bucket_close_time=(
                None
                if value.get("accumulator_bucket_close_time") is None
                else str(value["accumulator_bucket_close_time"])
            ),
            accumulator_open=(
                None
                if value.get("accumulator_open") is None
                else Decimal(str(value["accumulator_open"]))
            ),
            accumulator_high=(
                None
                if value.get("accumulator_high") is None
                else Decimal(str(value["accumulator_high"]))
            ),
            accumulator_low=(
                None
                if value.get("accumulator_low") is None
                else Decimal(str(value["accumulator_low"]))
            ),
            accumulator_close=(
                None
                if value.get("accumulator_close") is None
                else Decimal(str(value["accumulator_close"]))
            ),
            accumulator_first_1m_open_time=(
                None
                if value.get("accumulator_first_1m_open_time") is None
                else str(value["accumulator_first_1m_open_time"])
            ),
            accumulator_last_1m_close_time=(
                None
                if value.get("accumulator_last_1m_close_time") is None
                else str(value["accumulator_last_1m_close_time"])
            ),
            accumulator_count=int(value.get("accumulator_count", 0)),
            trade_eligible=False,
        )


@dataclass(frozen=True, slots=True)
class Chapter5EntryBarEvidence:
    """Optional, non-trading observation of the actual Chapter-4 entry interval."""

    bar_identity_id: str
    open_time: str
    close_time: str
    first_1m_open_time: str
    last_1m_close_time: str
    count: int
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    final_quality: str | None = None
    inside_prior_range: bool | None = None
    evidence_tags: tuple[str, ...] = ()
    trade_eligible: bool = False

    def __post_init__(self) -> None:
        if not self.bar_identity_id or self.count < 1:
            raise ValueError("entry-bar quality observation requires an actual bar")
        if self.final_quality not in {
            None, "STRONG_DIRECTIONAL", "WEAK_DOJI_OR_INSIDE",
            "MIXED_DIRECTIONAL",
        }:
            raise ValueError("invalid Chapter-5 entry-bar quality")
        if self.trade_eligible:
            raise ValueError("Chapter-5 entry-bar quality is diagnostic only")

    def to_metadata(self) -> dict[str, object]:
        return {
            "bar_identity_id": self.bar_identity_id,
            "open_time": self.open_time,
            "close_time": self.close_time,
            "first_1m_open_time": self.first_1m_open_time,
            "last_1m_close_time": self.last_1m_close_time,
            "count": self.count,
            "open_price": str(self.open_price),
            "high_price": str(self.high_price),
            "low_price": str(self.low_price),
            "close_price": str(self.close_price),
            "final_quality": self.final_quality,
            "inside_prior_range": self.inside_prior_range,
            "evidence_tags": list(self.evidence_tags),
            "trade_eligible": False,
        }

    @classmethod
    def from_metadata(
        cls, value: Mapping[str, object]
    ) -> "Chapter5EntryBarEvidence":
        return cls(
            bar_identity_id=str(value["bar_identity_id"]),
            open_time=str(value["open_time"]),
            close_time=str(value["close_time"]),
            first_1m_open_time=str(value["first_1m_open_time"]),
            last_1m_close_time=str(value["last_1m_close_time"]),
            count=int(value["count"]),
            open_price=Decimal(str(value["open_price"])),
            high_price=Decimal(str(value["high_price"])),
            low_price=Decimal(str(value["low_price"])),
            close_price=Decimal(str(value["close_price"])),
            final_quality=(
                None if value.get("final_quality") is None
                else str(value["final_quality"])
            ),
            inside_prior_range=(
                None if value.get("inside_prior_range") is None
                else bool(value["inside_prior_range"])
            ),
            evidence_tags=tuple(str(x) for x in value.get("evidence_tags", ())),
            trade_eligible=False,
        )


@dataclass(frozen=True, slots=True)
class Chapter4SignalEntryLifecycle:
    """Book-1/Chapter-4 setup to actual-entry identity contract."""

    setup_identity_id: str
    source_signal_id: str
    economic_opportunity_id: str
    market_snapshot_id: str
    market_snapshot_hash: str
    setup_type: str
    direction: str
    source_timeframe: str
    potential_signal_bar_identity_id: str
    potential_signal_bar_index: int
    potential_signal_bar_open_time: str
    potential_signal_bar_close_time: str
    state: str
    entry_intent_confirmation_scope: str
    entry_intent_confirmation_state: str
    confirmed_signal_bar_identity_id: str | None = None
    confirmed_signal_bar_index: int | None = None
    confirmed_signal_bar_confirmed_at: str | None = None
    entry_bar_identity_id: str | None = None
    entry_bar_index: int | None = None
    entry_bar_open_time: str | None = None
    entry_bar_close_time: str | None = None
    activation_candle_open_time: str | None = None
    activation_candle_close_time: str | None = None
    entry_activation_observed_at: str | None = None
    fill_observation_resolution: str | None = None
    unfilled_terminal_reason: str | None = None
    post_entry_lifecycle: Chapter4PostEntryLifecycle | None = None
    chapter5_entry_bar: Chapter5EntryBarEvidence | None = None

    def __post_init__(self) -> None:
        required = (
            self.setup_identity_id,
            self.source_signal_id,
            self.economic_opportunity_id,
            self.market_snapshot_id,
            self.market_snapshot_hash,
            self.setup_type,
            self.source_timeframe,
            self.potential_signal_bar_identity_id,
            self.potential_signal_bar_open_time,
            self.potential_signal_bar_close_time,
        )
        if any(not str(item).strip() for item in required):
            raise ValueError("Chapter-4 lifecycle requires stable source identities")
        if self.direction not in {"LONG", "SHORT"}:
            raise ValueError("Chapter-4 lifecycle direction must be LONG or SHORT")
        if self.potential_signal_bar_index < 0:
            raise ValueError("potential signal-bar index must be non-negative")
        if (
            self.entry_intent_confirmation_scope
            != "PRE_FILL_ENTRY_METHOD_OR_PATTERN_CONFIRMATION"
        ):
            raise ValueError("invalid Chapter-4 entry-intent confirmation scope")
        allowed = {
            "POTENTIAL_SIGNAL_WAITING_ENTRY",
            "CONFIRMED_SIGNAL_ENTRY_ACTIVE",
            "UNFILLED_TERMINAL",
        }
        if self.state not in allowed:
            raise ValueError("invalid Chapter-4 signal-entry lifecycle state")
        confirmed_fields = (
            self.confirmed_signal_bar_identity_id,
            self.confirmed_signal_bar_index,
            self.confirmed_signal_bar_confirmed_at,
            self.entry_bar_identity_id,
            self.entry_bar_open_time,
            self.entry_bar_close_time,
            self.activation_candle_open_time,
            self.activation_candle_close_time,
            self.entry_activation_observed_at,
            self.fill_observation_resolution,
        )
        if self.state == "POTENTIAL_SIGNAL_WAITING_ENTRY":
            if (
                any(item is not None for item in confirmed_fields)
                or self.post_entry_lifecycle is not None
                or self.chapter5_entry_bar is not None
            ):
                raise ValueError(
                    "pre-fill Chapter-4 identity cannot contain post-fill state"
                )
        elif self.state == "CONFIRMED_SIGNAL_ENTRY_ACTIVE":
            if (
                self.confirmed_signal_bar_identity_id
                != self.potential_signal_bar_identity_id
            ):
                raise ValueError(
                    "confirmed signal bar must preserve potential-bar identity"
                )
            if any(item is None for item in confirmed_fields):
                raise ValueError(
                    "confirmed Chapter-4 identity requires actual activation evidence"
                )
            if self.fill_observation_resolution != "CLOSED_1M_CANDLE_TOUCH":
                raise ValueError("invalid Chapter-4 fill observation resolution")
            if self.post_entry_lifecycle is None:
                raise ValueError(
                    "confirmed Chapter-4 identity requires post-entry lifecycle"
                )
            if (
                self.chapter5_entry_bar is not None
                and self.chapter5_entry_bar.bar_identity_id != self.entry_bar_identity_id
            ):
                raise ValueError("entry-bar quality must preserve actual entry identity")
        else:
            if (
                any(item is not None for item in confirmed_fields)
                or self.post_entry_lifecycle is not None
                or self.chapter5_entry_bar is not None
            ):
                raise ValueError(
                    "unfilled terminal identity cannot contain post-fill state"
                )
            if not self.unfilled_terminal_reason:
                raise ValueError("unfilled terminal identity requires a reason")

    def to_metadata(self) -> dict[str, object]:
        return {
            "setup_identity_id": self.setup_identity_id,
            "source_signal_id": self.source_signal_id,
            "economic_opportunity_id": self.economic_opportunity_id,
            "market_snapshot_id": self.market_snapshot_id,
            "market_snapshot_hash": self.market_snapshot_hash,
            "setup_type": self.setup_type,
            "direction": self.direction,
            "source_timeframe": self.source_timeframe,
            "potential_signal_bar_identity_id": self.potential_signal_bar_identity_id,
            "potential_signal_bar_index": self.potential_signal_bar_index,
            "potential_signal_bar_open_time": self.potential_signal_bar_open_time,
            "potential_signal_bar_close_time": self.potential_signal_bar_close_time,
            "state": self.state,
            "entry_intent_confirmation_scope": self.entry_intent_confirmation_scope,
            "entry_intent_confirmation_state": self.entry_intent_confirmation_state,
            "confirmed_signal_bar_identity_id": self.confirmed_signal_bar_identity_id,
            "confirmed_signal_bar_index": self.confirmed_signal_bar_index,
            "confirmed_signal_bar_confirmed_at": self.confirmed_signal_bar_confirmed_at,
            "entry_bar_identity_id": self.entry_bar_identity_id,
            "entry_bar_index": self.entry_bar_index,
            "entry_bar_open_time": self.entry_bar_open_time,
            "entry_bar_close_time": self.entry_bar_close_time,
            "activation_candle_open_time": self.activation_candle_open_time,
            "activation_candle_close_time": self.activation_candle_close_time,
            "entry_activation_observed_at": self.entry_activation_observed_at,
            "fill_observation_resolution": self.fill_observation_resolution,
            "unfilled_terminal_reason": self.unfilled_terminal_reason,
            "post_entry_lifecycle": (
                None
                if self.post_entry_lifecycle is None
                else self.post_entry_lifecycle.to_metadata()
            ),
            "chapter5_entry_bar": (
                None if self.chapter5_entry_bar is None
                else self.chapter5_entry_bar.to_metadata()
            ),
        }

    @classmethod
    def from_metadata(
        cls, value: Mapping[str, object]
    ) -> "Chapter4SignalEntryLifecycle":
        raw_post = value.get("post_entry_lifecycle")
        if raw_post is not None and not isinstance(raw_post, Mapping):
            raise ValueError("post_entry_lifecycle must be an object")
        raw_ch5 = value.get("chapter5_entry_bar")
        if raw_ch5 is not None and not isinstance(raw_ch5, Mapping):
            raise ValueError("chapter5_entry_bar must be an object")
        return cls(
            setup_identity_id=str(value["setup_identity_id"]),
            source_signal_id=str(value["source_signal_id"]),
            economic_opportunity_id=str(value["economic_opportunity_id"]),
            market_snapshot_id=str(value["market_snapshot_id"]),
            market_snapshot_hash=str(value["market_snapshot_hash"]),
            setup_type=str(value["setup_type"]),
            direction=str(value["direction"]),
            source_timeframe=str(value["source_timeframe"]),
            potential_signal_bar_identity_id=str(
                value["potential_signal_bar_identity_id"]
            ),
            potential_signal_bar_index=int(value["potential_signal_bar_index"]),
            potential_signal_bar_open_time=str(
                value["potential_signal_bar_open_time"]
            ),
            potential_signal_bar_close_time=str(
                value["potential_signal_bar_close_time"]
            ),
            state=str(value["state"]),
            entry_intent_confirmation_scope=str(
                value["entry_intent_confirmation_scope"]
            ),
            entry_intent_confirmation_state=str(
                value["entry_intent_confirmation_state"]
            ),
            confirmed_signal_bar_identity_id=(
                None
                if value.get("confirmed_signal_bar_identity_id") is None
                else str(value["confirmed_signal_bar_identity_id"])
            ),
            confirmed_signal_bar_index=(
                None
                if value.get("confirmed_signal_bar_index") is None
                else int(value["confirmed_signal_bar_index"])
            ),
            confirmed_signal_bar_confirmed_at=(
                None
                if value.get("confirmed_signal_bar_confirmed_at") is None
                else str(value["confirmed_signal_bar_confirmed_at"])
            ),
            entry_bar_identity_id=(
                None
                if value.get("entry_bar_identity_id") is None
                else str(value["entry_bar_identity_id"])
            ),
            entry_bar_index=(
                None
                if value.get("entry_bar_index") is None
                else int(value["entry_bar_index"])
            ),
            entry_bar_open_time=(
                None
                if value.get("entry_bar_open_time") is None
                else str(value["entry_bar_open_time"])
            ),
            entry_bar_close_time=(
                None
                if value.get("entry_bar_close_time") is None
                else str(value["entry_bar_close_time"])
            ),
            activation_candle_open_time=(
                None
                if value.get("activation_candle_open_time") is None
                else str(value["activation_candle_open_time"])
            ),
            activation_candle_close_time=(
                None
                if value.get("activation_candle_close_time") is None
                else str(value["activation_candle_close_time"])
            ),
            entry_activation_observed_at=(
                None
                if value.get("entry_activation_observed_at") is None
                else str(value["entry_activation_observed_at"])
            ),
            fill_observation_resolution=(
                None
                if value.get("fill_observation_resolution") is None
                else str(value["fill_observation_resolution"])
            ),
            unfilled_terminal_reason=(
                None
                if value.get("unfilled_terminal_reason") is None
                else str(value["unfilled_terminal_reason"])
            ),
            post_entry_lifecycle=(
                None
                if raw_post is None
                else Chapter4PostEntryLifecycle.from_metadata(raw_post)
            ),
            chapter5_entry_bar=(
                None if raw_ch5 is None
                else Chapter5EntryBarEvidence.from_metadata(raw_ch5)
            ),
        )


@dataclass(frozen=True, slots=True)
class TargetSourceEvidence:
    """One semantic source contributing to a concrete target price."""

    source_type: str
    source_id: str
    origin_index: int | None
    confirmed_at_index: int | None
    direction: str = "UNRESOLVED"
    structure_id: str | None = None
    semantic_classification: str = "SOURCE_SEMANTIC"

    def __post_init__(self) -> None:
        if not self.source_type.strip() or not self.source_id.strip():
            raise ValueError("target source type/id are required")
        if self.origin_index is not None and self.origin_index < 0:
            raise ValueError("target source origin_index must be non-negative")
        if self.confirmed_at_index is not None and self.confirmed_at_index < 0:
            raise ValueError("target source confirmed_at_index must be non-negative")
        if self.direction not in {"LONG", "SHORT", "UNRESOLVED"}:
            raise ValueError("invalid target source direction")
        if self.semantic_classification not in {
            "SOURCE_SEMANTIC",
            "ENGINEERING_CLASSIFICATION_POLICY",
        }:
            raise ValueError("invalid target source semantic classification")

    def to_metadata(self) -> dict[str, object]:
        return {
            "source_type": self.source_type,
            "source_id": self.source_id,
            "origin_index": self.origin_index,
            "confirmed_at_index": self.confirmed_at_index,
            "direction": self.direction,
            "structure_id": self.structure_id,
            "semantic_classification": self.semantic_classification,
        }

    @classmethod
    def from_metadata(cls, value: Mapping[str, object]) -> "TargetSourceEvidence":
        return cls(
            source_type=str(value["source_type"]),
            source_id=str(value["source_id"]),
            origin_index=(None if value.get("origin_index") is None else int(value["origin_index"])),
            confirmed_at_index=(
                None if value.get("confirmed_at_index") is None
                else int(value["confirmed_at_index"])
            ),
            direction=str(value.get("direction", "UNRESOLVED")),
            structure_id=(
                None if value.get("structure_id") is None else str(value["structure_id"])
            ),
            semantic_classification=str(
                value.get("semantic_classification", "SOURCE_SEMANTIC")
            ),
        )


@dataclass(frozen=True, slots=True)
class TargetSourceIdentity:
    """BROOKS-GAP-079 typed target identity preserved after geometry approval."""

    target_number: int
    target_price: Decimal
    sources: tuple[TargetSourceEvidence, ...]
    available_at_index: int
    management_role: str = "STRUCTURAL_TARGET"

    def __post_init__(self) -> None:
        if self.target_number < 1:
            raise ValueError("target_number must be positive")
        if not self.sources:
            raise ValueError("typed target identity requires at least one source")
        if self.available_at_index < 0:
            raise ValueError("target available_at_index must be non-negative")
        if not self.management_role.strip():
            raise ValueError("target management_role is required")
        for source in self.sources:
            if source.confirmed_at_index is not None and source.confirmed_at_index > self.available_at_index:
                raise ValueError("target source cannot be confirmed after target availability")

    def to_metadata(self) -> dict[str, object]:
        return {
            "target_number": self.target_number,
            "target_price": str(self.target_price),
            "sources": [source.to_metadata() for source in self.sources],
            "available_at_index": self.available_at_index,
            "management_role": self.management_role,
        }

    @classmethod
    def from_metadata(cls, value: Mapping[str, object]) -> "TargetSourceIdentity":
        raw_sources = value.get("sources", ())
        if not isinstance(raw_sources, (list, tuple)):
            raise ValueError("target sources must be a sequence")
        return cls(
            target_number=int(value["target_number"]),
            target_price=Decimal(str(value["target_price"])),
            sources=tuple(
                TargetSourceEvidence.from_metadata(source)
                for source in raw_sources
                if isinstance(source, Mapping)
            ),
            available_at_index=int(value["available_at_index"]),
            management_role=str(value.get("management_role", "STRUCTURAL_TARGET")),
        )


@dataclass(frozen=True, slots=True)
class StopSourceIdentity:
    """BROOKS-GAP-079 identity for the approved initial protective stop."""

    stop_price: Decimal
    source_type: str
    source_id: str
    structural_reference_price: Decimal
    origin_index: int
    available_at_index: int
    adjustment_policy: str
    management_role: str = "INITIAL_PROTECTIVE_STOP"
    direction: str = "UNRESOLVED"

    def __post_init__(self) -> None:
        if not self.source_type.strip() or not self.source_id.strip():
            raise ValueError("stop source type/id are required")
        if self.origin_index < 0 or self.available_at_index < 0:
            raise ValueError("stop source indices must be non-negative")
        if self.origin_index > self.available_at_index:
            raise ValueError("stop source origin cannot be after availability")
        if not self.adjustment_policy.strip() or not self.management_role.strip():
            raise ValueError("stop adjustment policy/management role are required")
        if self.direction not in {"LONG", "SHORT", "UNRESOLVED"}:
            raise ValueError("invalid stop source direction")

    def to_metadata(self) -> dict[str, object]:
        return {
            "stop_price": str(self.stop_price),
            "source_type": self.source_type,
            "source_id": self.source_id,
            "structural_reference_price": str(self.structural_reference_price),
            "origin_index": self.origin_index,
            "available_at_index": self.available_at_index,
            "adjustment_policy": self.adjustment_policy,
            "management_role": self.management_role,
            "direction": self.direction,
        }

    @classmethod
    def from_metadata(cls, value: Mapping[str, object]) -> "StopSourceIdentity":
        return cls(
            stop_price=Decimal(str(value["stop_price"])),
            source_type=str(value["source_type"]),
            source_id=str(value["source_id"]),
            structural_reference_price=Decimal(str(value["structural_reference_price"])),
            origin_index=int(value["origin_index"]),
            available_at_index=int(value["available_at_index"]),
            adjustment_policy=str(value["adjustment_policy"]),
            management_role=str(value.get("management_role", "INITIAL_PROTECTIVE_STOP")),
            direction=str(value.get("direction", "UNRESOLVED")),
        )


@dataclass(frozen=True, slots=True)
class TargetPlanLifecycle:
    """BROOKS-GAP-050 typed Core target-plan phase; no TM_V6 economic mutation."""

    plan_id: str
    state: str
    direction: str
    evaluated_index: int
    range_id: str | None = None
    breakout_id: str | None = None
    transition_index: int | None = None
    target_source_ids: tuple[str, ...] = ()
    initial_stop_source_id: str | None = None
    trade_eligible: bool = False

    def __post_init__(self) -> None:
        allowed = {
            "RANGE_TRADE",
            "BREAKOUT_TRANSITION",
            "TREND_TRADE",
            "FAILED_BREAKOUT_TRADE",
            "REVERSAL_OR_TRANSITION",
        }
        if self.state not in allowed:
            raise ValueError("invalid target-plan lifecycle state")
        if self.direction not in {"LONG", "SHORT"}:
            raise ValueError("target-plan direction must be LONG or SHORT")
        if self.evaluated_index < 0:
            raise ValueError("target-plan evaluated_index must be non-negative")
        if self.transition_index is not None and self.transition_index > self.evaluated_index:
            raise ValueError("target-plan transition cannot be in the future")
        if self.trade_eligible:
            raise ValueError("target-plan context cannot create trade eligibility")

    def to_metadata(self) -> dict[str, object]:
        return {
            "plan_id": self.plan_id,
            "state": self.state,
            "direction": self.direction,
            "evaluated_index": self.evaluated_index,
            "range_id": self.range_id,
            "breakout_id": self.breakout_id,
            "transition_index": self.transition_index,
            "target_source_ids": list(self.target_source_ids),
            "initial_stop_source_id": self.initial_stop_source_id,
            "trade_eligible": False,
        }

    @classmethod
    def from_metadata(cls, value: Mapping[str, object]) -> "TargetPlanLifecycle":
        return cls(
            plan_id=str(value["plan_id"]),
            state=str(value["state"]),
            direction=str(value["direction"]),
            evaluated_index=int(value["evaluated_index"]),
            range_id=(None if value.get("range_id") is None else str(value["range_id"])),
            breakout_id=(
                None if value.get("breakout_id") is None else str(value["breakout_id"])
            ),
            transition_index=(
                None if value.get("transition_index") is None
                else int(value["transition_index"])
            ),
            target_source_ids=tuple(str(x) for x in value.get("target_source_ids", ())),
            initial_stop_source_id=(
                None
                if value.get("initial_stop_source_id") is None
                else str(value["initial_stop_source_id"])
            ),
            trade_eligible=False,
        )


@dataclass(frozen=True, slots=True)
class ReversalOutcomeContext:
    """BROOKS-GAP-080 typed reversal-outcome context across the Core-to-TM boundary."""

    context_id: str
    reversal_origin_id: str
    direction: str
    state: str
    evaluated_index: int
    available_at_index: int
    target_source_ids: tuple[str, ...]
    initial_stop_source_id: str
    target_plan_id: str
    target_plan_state: str
    transition_available_at: str | None = None
    transition_source_signal_id: str | None = None
    trade_eligible: bool = False

    def __post_init__(self) -> None:
        allowed = {
            "PENDING_REVERSAL_OUTCOME",
            "OPPOSITE_TREND_OUTCOME",
            "TRADING_RANGE_OUTCOME",
            "FAILED_REVERSAL_OUTCOME",
        }
        if not self.context_id.strip() or not self.reversal_origin_id.strip():
            raise ValueError("reversal outcome context/origin id is required")
        if self.direction not in {"LONG", "SHORT"}:
            raise ValueError("reversal outcome direction must be LONG or SHORT")
        if self.state not in allowed:
            raise ValueError("invalid reversal outcome state")
        if self.evaluated_index < 0 or self.available_at_index < 0:
            raise ValueError("reversal outcome indices must be non-negative")
        if self.available_at_index > self.evaluated_index:
            raise ValueError("reversal outcome cannot be available after evaluation")
        if not self.target_source_ids:
            raise ValueError("reversal outcome requires typed target source identity")
        if not self.initial_stop_source_id.strip():
            raise ValueError("reversal outcome requires initial stop source identity")
        if not self.target_plan_id.strip() or not self.target_plan_state.strip():
            raise ValueError("reversal outcome requires target-plan identity/state")
        if self.trade_eligible:
            raise ValueError("reversal outcome context cannot create trade eligibility")

    def to_metadata(self) -> dict[str, object]:
        return {
            "context_id": self.context_id,
            "reversal_origin_id": self.reversal_origin_id,
            "direction": self.direction,
            "state": self.state,
            "evaluated_index": self.evaluated_index,
            "available_at_index": self.available_at_index,
            "target_source_ids": list(self.target_source_ids),
            "initial_stop_source_id": self.initial_stop_source_id,
            "target_plan_id": self.target_plan_id,
            "target_plan_state": self.target_plan_state,
            "transition_available_at": self.transition_available_at,
            "transition_source_signal_id": self.transition_source_signal_id,
            "trade_eligible": False,
        }

    @classmethod
    def from_metadata(cls, value: dict[str, object]) -> "ReversalOutcomeContext":
        return cls(
            context_id=str(value["context_id"]),
            reversal_origin_id=str(value["reversal_origin_id"]),
            direction=str(value["direction"]),
            state=str(value["state"]),
            evaluated_index=int(value["evaluated_index"]),
            available_at_index=int(value["available_at_index"]),
            target_source_ids=tuple(str(x) for x in value.get("target_source_ids", ())),
            initial_stop_source_id=str(value["initial_stop_source_id"]),
            target_plan_id=str(value["target_plan_id"]),
            target_plan_state=str(value["target_plan_state"]),
            transition_available_at=(
                None if value.get("transition_available_at") is None
                else str(value["transition_available_at"])
            ),
            transition_source_signal_id=(
                None if value.get("transition_source_signal_id") is None
                else str(value["transition_source_signal_id"])
            ),
            trade_eligible=False,
        )


@dataclass(frozen=True, slots=True)
class BrooksEngineResult:
    decision: str
    entry_price: Decimal | None
    stop_loss: Decimal | None
    targets: tuple[Decimal, ...]
    setup_type: str | None
    reasoning: tuple[str, ...]
    rule_ids: tuple[str, ...]
    failed_rules: tuple[str, ...]
    rule_evidence: tuple[BrooksRuleEvidence, ...]
    engine_version: str
    rule_set_version: str
    configuration_version: str
    target_source_identities: tuple[TargetSourceIdentity, ...] = ()
    stop_source_identity: StopSourceIdentity | None = None
    target_plan_lifecycle: TargetPlanLifecycle | None = None
    reversal_outcome_context: ReversalOutcomeContext | None = None

    def __post_init__(self) -> None:
        if self.decision not in {"LONG", "SHORT", "NO_SIGNAL"}:
            raise ValueError("invalid engine decision")
        if self.decision == "NO_SIGNAL":
            if (
                self.target_source_identities
                or self.stop_source_identity is not None
                or self.target_plan_lifecycle is not None
                or self.reversal_outcome_context is not None
            ):
                raise ValueError("NO_SIGNAL cannot carry target/stop execution identity")
            return
        if self.entry_price is None or self.stop_loss is None:
            raise ValueError("tradeable engine result requires entry and stop")
        if not self.targets:
            raise ValueError("tradeable engine result requires targets")
        if self.target_source_identities:
            if len(self.target_source_identities) != len(self.targets):
                raise ValueError("target identity count must match targets")
            for number, (price, identity) in enumerate(
                zip(self.targets, self.target_source_identities), start=1
            ):
                if identity.target_number != number or identity.target_price != price:
                    raise ValueError("target identity must preserve target number/price")
        if self.stop_source_identity is not None and self.stop_source_identity.stop_price != self.stop_loss:
            raise ValueError("stop identity must preserve stop price")
        if self.target_plan_lifecycle is not None and self.target_plan_lifecycle.direction != self.decision:
            raise ValueError("target-plan direction must preserve decision direction")
        if self.reversal_outcome_context is not None:
            if self.reversal_outcome_context.direction != self.decision:
                raise ValueError("reversal-outcome direction must preserve decision direction")
            if not self.target_source_identities or self.stop_source_identity is None:
                raise ValueError("reversal outcome requires typed target/stop identities")
            if self.target_plan_lifecycle is None:
                raise ValueError("reversal outcome requires target-plan lifecycle")
            target_source_ids = {
                source.source_id
                for target in self.target_source_identities
                for source in target.sources
            }
            if not set(self.reversal_outcome_context.target_source_ids).issubset(target_source_ids):
                raise ValueError("reversal outcome must preserve typed target source identity")
            if self.reversal_outcome_context.initial_stop_source_id != self.stop_source_identity.source_id:
                raise ValueError("reversal outcome must preserve initial stop source identity")
            if self.reversal_outcome_context.target_plan_id != self.target_plan_lifecycle.plan_id:
                raise ValueError("reversal outcome must preserve target-plan identity")

class ActualBrooksStrategyEngine(Protocol):
    async def evaluate(self, snapshot: MarketSnapshot) -> BrooksEngineResult: ...
