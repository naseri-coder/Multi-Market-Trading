"""Signal lifecycle validation and transaction-safe business operations."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from app.modules.signals.entities import (
    CreateSignal,
    SignalEventRecord,
    SignalRecord,
    SignalTargetRecord,
    UpdateSignal,
)
from app.modules.signals.errors import InvalidSignalError, SignalStateError
from app.modules.signals.models import (
    SignalDirection,
    SignalEventType,
    SignalStatus,
    SignalTargetStatus,
)
from app.modules.signals.repository import SignalRepository

Clock = Callable[[], datetime]
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9._:/-]{0,31}$")
DESCRIPTION_MAX_LENGTH = 4000


def utc_now() -> datetime:
    return datetime.now(UTC)


class SignalService:
    """Own all signal rules independently from Telegram or other adapters."""

    def __init__(self, repository: SignalRepository, *, clock: Clock = utc_now) -> None:
        self.repository = repository
        self.clock = clock

    async def create_signal(self, command: CreateSignal) -> SignalRecord:
        if not isinstance(command, CreateSignal):
            raise InvalidSignalError("Create signal command is invalid")
        if not isinstance(command.as_draft, bool):
            raise InvalidSignalError("Draft flag must be boolean")

        symbol = self._normalize_symbol(command.symbol)
        direction = self._normalize_direction(command.direction)
        entry_price = self._decimal(
            command.entry_price,
            field="Entry price",
            precision=38,
            scale=18,
            positive=True,
        )
        stop_loss = self._decimal(
            command.stop_loss,
            field="Stop loss",
            precision=38,
            scale=18,
            positive=True,
        )
        leverage = self._decimal(
            command.leverage,
            field="Leverage",
            precision=8,
            scale=2,
            positive=True,
        )
        description = self._normalize_description(command.description)
        self._validate_initial_stop(direction, entry_price, stop_loss)

        now = self._now()
        status = SignalStatus.DRAFT.value if command.as_draft else SignalStatus.OPEN.value
        signal = await self.repository.create_signal(
            values={
                "symbol": symbol,
                "direction": direction,
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "leverage": leverage,
                "status": status,
                "description": description,
            },
            created_at=now,
        )
        await self.repository.append_event(
            signal_id=signal.id,
            event_type=SignalEventType.CREATED.value,
            metadata={
                "symbol": signal.symbol,
                "direction": signal.direction,
                "entry_price": str(signal.entry_price),
                "stop_loss": str(signal.stop_loss),
                "leverage": str(signal.leverage),
                "status": signal.status,
            },
            created_at=now,
        )
        return signal

    async def update_signal(self, signal_id: int, command: UpdateSignal) -> SignalRecord:
        self._validate_id(signal_id, "Signal")
        if not isinstance(command, UpdateSignal):
            raise InvalidSignalError("Update signal command is invalid")
        if not isinstance(command.clear_description, bool):
            raise InvalidSignalError("Clear-description flag must be boolean")
        if command.description is not None and command.clear_description:
            raise InvalidSignalError("Description cannot be set and cleared together")

        current = await self.repository.get_signal(signal_id, for_update=True)
        self._require_mutable(current)

        if current.status == SignalStatus.OPEN.value and any(
            value is not None
            for value in (
                command.direction,
                command.entry_price,
                command.stop_loss,
                command.leverage,
            )
        ):
            raise SignalStateError(
                "Open signal direction, entry, leverage, and stop cannot be edited here"
            )

        values: dict[str, object] = {}
        if command.symbol is not None:
            values["symbol"] = self._normalize_symbol(command.symbol)
        if command.direction is not None:
            values["direction"] = self._normalize_direction(command.direction)
        if command.entry_price is not None:
            values["entry_price"] = self._decimal(
                command.entry_price,
                field="Entry price",
                precision=38,
                scale=18,
                positive=True,
            )
        if command.stop_loss is not None:
            values["stop_loss"] = self._decimal(
                command.stop_loss,
                field="Stop loss",
                precision=38,
                scale=18,
                positive=True,
            )
        if command.leverage is not None:
            values["leverage"] = self._decimal(
                command.leverage,
                field="Leverage",
                precision=8,
                scale=2,
                positive=True,
            )
        if command.description is not None:
            values["description"] = self._normalize_description(command.description)
        elif command.clear_description:
            values["description"] = None

        effective_direction = str(values.get("direction", current.direction))
        effective_entry = self._as_decimal(values.get("entry_price", current.entry_price))
        effective_stop = self._as_decimal(values.get("stop_loss", current.stop_loss))
        if current.status == SignalStatus.DRAFT.value:
            self._validate_initial_stop(effective_direction, effective_entry, effective_stop)
            if any(key in values for key in ("direction", "entry_price")):
                targets = await self.repository.list_targets(signal_id)
                self._validate_existing_target_geometry(
                    effective_direction,
                    effective_entry,
                    targets,
                )

        changes = self._changes(current, values)
        if not changes:
            raise InvalidSignalError("Signal update does not contain any changes")

        now = self._now()
        updated = await self.repository.update_signal(
            signal_id,
            values={key: value for key, value in values.items() if key in changes},
            updated_at=now,
        )
        await self.repository.append_event(
            signal_id=signal_id,
            event_type=SignalEventType.UPDATED.value,
            metadata={"changes": changes},
            created_at=now,
        )
        return updated

    async def close_signal(
        self,
        signal_id: int,
        *,
        profit_loss: Decimal | str | int,
    ) -> SignalRecord:
        self._validate_id(signal_id, "Signal")
        current = await self.repository.get_signal(signal_id, for_update=True)
        if current.status != SignalStatus.OPEN.value:
            raise SignalStateError("Only an open signal can be closed")
        normalized_profit_loss = self._decimal(
            profit_loss,
            field="Profit/loss",
            precision=18,
            scale=8,
            positive=False,
        )
        now = self._now()
        closed = await self.repository.update_signal(
            signal_id,
            values={
                "status": SignalStatus.CLOSED.value,
                "profit_loss": normalized_profit_loss,
                "closed_at": now,
            },
            updated_at=now,
        )
        cancelled_targets = await self.repository.cancel_pending_targets(
            signal_id,
            changed_at=now,
        )
        await self.repository.append_event(
            signal_id=signal_id,
            event_type=SignalEventType.CLOSED.value,
            metadata={
                "profit_loss": str(normalized_profit_loss),
                "cancelled_targets": cancelled_targets,
            },
            created_at=now,
        )
        return closed

    async def publish_signal(self, signal_id: int) -> SignalRecord:
        """Atomically expose one draft through existing public query surfaces."""
        self._validate_id(signal_id, "Signal")
        current = await self.repository.get_signal(signal_id, for_update=True)
        if current.status != SignalStatus.DRAFT.value:
            raise SignalStateError("Only a draft signal can be published")
        now = self._now()
        published = await self.repository.update_signal(
            signal_id,
            values={"status": SignalStatus.OPEN.value},
            updated_at=now,
        )
        await self.repository.append_event(
            signal_id=signal_id,
            event_type=SignalEventType.PUBLISHED.value,
            metadata={"previous_status": SignalStatus.DRAFT.value},
            created_at=now,
        )
        return published

    async def cancel_signal(
        self,
        signal_id: int,
        *,
        reason: str | None = None,
        event_metadata: dict[str, object] | None = None,
    ) -> SignalRecord:
        self._validate_id(signal_id, "Signal")
        current = await self.repository.get_signal(signal_id, for_update=True)
        self._require_mutable(current)
        now = self._now()
        cancelled = await self.repository.update_signal(
            signal_id,
            values={
                "status": SignalStatus.CANCELLED.value,
                "profit_loss": None,
                "closed_at": now,
            },
            updated_at=now,
        )
        cancelled_targets = await self.repository.cancel_pending_targets(
            signal_id,
            changed_at=now,
        )
        metadata: dict[str, object] = {"cancelled_targets": cancelled_targets}
        if reason is not None:
            metadata["reason"] = reason
        if event_metadata:
            metadata.update(event_metadata)
        await self.repository.append_event(
            signal_id=signal_id,
            event_type=SignalEventType.CANCELLED.value,
            metadata=metadata,
            created_at=now,
        )
        return cancelled

    async def add_target(
        self,
        signal_id: int,
        *,
        target_price: Decimal | str | int,
    ) -> SignalTargetRecord:
        self._validate_id(signal_id, "Signal")
        signal = await self.repository.get_signal(signal_id, for_update=True)
        self._require_mutable(signal)
        price = self._decimal(
            target_price,
            field="Target price",
            precision=38,
            scale=18,
            positive=True,
        )
        targets = await self.repository.list_targets(signal_id)
        self._validate_new_target_geometry(signal, targets, price)
        target_number = max((target.target_number for target in targets), default=0) + 1
        now = self._now()
        target = await self.repository.create_target(
            signal_id=signal_id,
            target_number=target_number,
            target_price=price,
            created_at=now,
        )
        await self.repository.append_event(
            signal_id=signal_id,
            event_type=SignalEventType.TARGET_ADDED.value,
            metadata={
                "target_id": target.id,
                "target_number": target.target_number,
                "target_price": str(target.target_price),
            },
            created_at=now,
        )
        return target

    # V6 keeps generic target persistence while accepting audited scale-out metadata.
    async def hit_target(
        self,
        signal_id: int,
        target_id: int,
        *,
        profit_loss: Decimal | str | int,
        event_metadata: dict[str, object] | None = None,
    ) -> SignalTargetRecord:
        self._validate_id(signal_id, "Signal")
        self._validate_id(target_id, "Signal target")
        signal = await self.repository.get_signal(signal_id, for_update=True)
        if signal.status != SignalStatus.OPEN.value:
            raise SignalStateError("Targets can be hit only while a signal is open")
        target = await self.repository.get_target(signal_id, target_id, for_update=True)
        if target.status != SignalTargetStatus.PENDING.value:
            raise SignalStateError("Signal target is not pending")
        targets = await self.repository.list_targets(signal_id)
        if any(
            item.target_number < target.target_number
            and item.status == SignalTargetStatus.PENDING.value
            for item in targets
        ):
            raise SignalStateError("Earlier signal targets must be hit first")
        normalized_profit_loss = self._decimal(
            profit_loss,
            field="Profit/loss",
            precision=18,
            scale=8,
            positive=False,
        )
        now = self._now()
        hit = await self.repository.mark_target_hit(
            signal_id,
            target_id,
            hit_at=now,
            profit_loss=normalized_profit_loss,
        )
        target_event_metadata = dict(event_metadata or {})
        target_event_metadata.update(
            {
                "target_id": hit.id,
                "target_number": hit.target_number,
                "target_price": str(hit.target_price),
                "profit_loss": str(normalized_profit_loss),
            }
        )
        await self.repository.append_event(
            signal_id=signal_id,
            event_type=SignalEventType.TARGET_HIT.value,
            metadata=target_event_metadata,
            created_at=now,
        )
        return hit

    async def update_stop_loss(
        self,
        signal_id: int,
        *,
        stop_loss: Decimal | str | int,
        reason: str | None = None,
    ) -> SignalRecord:
        self._validate_id(signal_id, "Signal")
        signal = await self.repository.get_signal(signal_id, for_update=True)
        if signal.status != SignalStatus.OPEN.value:
            raise SignalStateError("Stop loss can be changed only on an open signal")
        normalized_stop = self._decimal(
            stop_loss,
            field="Stop loss",
            precision=38,
            scale=18,
            positive=True,
        )
        if signal.direction == SignalDirection.LONG.value and normalized_stop <= signal.stop_loss:
            raise SignalStateError("A long signal stop loss can only move upward")
        if signal.direction == SignalDirection.SHORT.value and normalized_stop >= signal.stop_loss:
            raise SignalStateError("A short signal stop loss can only move downward")

        now = self._now()
        updated = await self.repository.update_signal(
            signal_id,
            values={"stop_loss": normalized_stop},
            updated_at=now,
        )
        event_metadata = {
            "old_stop_loss": str(signal.stop_loss),
            "new_stop_loss": str(normalized_stop),
        }
        if reason is not None:
            event_metadata["reason"] = reason
        await self.repository.append_event(
            signal_id=signal_id,
            event_type=SignalEventType.STOP_LOSS_UPDATED.value,
            metadata=event_metadata,
            created_at=now,
        )
        return updated

    async def signal_history(
        self,
        signal_id: int,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[SignalEventRecord, ...]:
        self._validate_id(signal_id, "Signal")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise InvalidSignalError("Signal history limit must be between 1 and 100")
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise InvalidSignalError("Signal history offset cannot be negative")
        await self.repository.get_signal(signal_id)
        return await self.repository.list_events(signal_id, limit=limit, offset=offset)

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise RuntimeError("SignalService clock must return an aware datetime")
        return value.astimezone(UTC)

    @staticmethod
    def _validate_id(value: int, label: str) -> None:
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise InvalidSignalError(f"{label} identifier must be a positive integer")

    @staticmethod
    def _normalize_symbol(value: str) -> str:
        normalized = value.strip().upper() if isinstance(value, str) else ""
        if not SYMBOL_PATTERN.fullmatch(normalized):
            raise InvalidSignalError("Signal symbol format is invalid")
        return normalized

    @staticmethod
    def _normalize_direction(value: str) -> str:
        normalized = value.strip().upper() if isinstance(value, str) else ""
        if normalized not in {item.value for item in SignalDirection}:
            raise InvalidSignalError("Signal direction must be LONG or SHORT")
        return normalized

    @staticmethod
    def _normalize_description(value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise InvalidSignalError("Signal description must be text")
        normalized = value.strip()
        if len(normalized) > DESCRIPTION_MAX_LENGTH:
            raise InvalidSignalError("Signal description is too long")
        return normalized or None

    @staticmethod
    def _decimal(
        value: Decimal | str | int,
        *,
        field: str,
        precision: int,
        scale: int,
        positive: bool,
    ) -> Decimal:
        if isinstance(value, (bool, float)) or not isinstance(value, (Decimal, str, int)):
            raise InvalidSignalError(f"{field} must be an exact decimal value")
        try:
            decimal_value = Decimal(value.strip() if isinstance(value, str) else value)
        except (InvalidOperation, ValueError):
            raise InvalidSignalError(f"{field} must be an exact decimal value") from None
        if not decimal_value.is_finite():
            raise InvalidSignalError(f"{field} must be finite")
        if positive and decimal_value <= 0:
            raise InvalidSignalError(f"{field} must be greater than zero")

        normalized = decimal_value.normalize()
        fraction_digits = max(-normalized.as_tuple().exponent, 0)
        integer_digits = 0 if normalized.is_zero() else max(normalized.adjusted() + 1, 0)
        if fraction_digits > scale or integer_digits > precision - scale:
            raise InvalidSignalError(f"{field} exceeds database precision")
        return decimal_value

    @staticmethod
    def _as_decimal(value: object) -> Decimal:
        if not isinstance(value, Decimal):
            raise RuntimeError("Validated signal decimal unexpectedly changed type")
        return value

    @staticmethod
    def _validate_initial_stop(direction: str, entry_price: Decimal, stop_loss: Decimal) -> None:
        if direction == SignalDirection.LONG.value and stop_loss >= entry_price:
            raise InvalidSignalError("A new long signal stop loss must be below entry")
        if direction == SignalDirection.SHORT.value and stop_loss <= entry_price:
            raise InvalidSignalError("A new short signal stop loss must be above entry")

    @staticmethod
    def _require_mutable(signal: SignalRecord) -> None:
        if signal.status not in {SignalStatus.DRAFT.value, SignalStatus.OPEN.value}:
            raise SignalStateError("Closed or cancelled signals cannot be changed")

    @staticmethod
    def _validate_existing_target_geometry(
        direction: str,
        entry_price: Decimal,
        targets: tuple[SignalTargetRecord, ...],
    ) -> None:
        active_targets = sorted(
            (target for target in targets if target.status != SignalTargetStatus.CANCELLED.value),
            key=lambda target: target.target_number,
        )
        previous = entry_price
        for target in active_targets:
            if direction == SignalDirection.LONG.value and target.target_price <= previous:
                raise InvalidSignalError("Existing long targets conflict with this update")
            if direction == SignalDirection.SHORT.value and target.target_price >= previous:
                raise InvalidSignalError("Existing short targets conflict with this update")
            previous = target.target_price

    @staticmethod
    def _validate_new_target_geometry(
        signal: SignalRecord,
        targets: tuple[SignalTargetRecord, ...],
        target_price: Decimal,
    ) -> None:
        ordered = sorted(targets, key=lambda target: target.target_number)
        reference = ordered[-1].target_price if ordered else signal.entry_price
        if signal.direction == SignalDirection.LONG.value and target_price <= reference:
            raise InvalidSignalError("Long signal targets must increase above entry")
        if signal.direction == SignalDirection.SHORT.value and target_price >= reference:
            raise InvalidSignalError("Short signal targets must decrease below entry")

    @classmethod
    def _changes(
        cls,
        current: SignalRecord,
        values: dict[str, object],
    ) -> dict[str, dict[str, object]]:
        changes: dict[str, dict[str, object]] = {}
        for key, new_value in values.items():
            old_value = getattr(current, key)
            if old_value != new_value:
                changes[key] = {
                    "old": cls._json_value(old_value),
                    "new": cls._json_value(new_value),
                }
        return changes

    @staticmethod
    def _json_value(value: object) -> object:
        return str(value) if isinstance(value, Decimal) else value
