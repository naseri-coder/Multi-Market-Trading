"""Broadcast validation, transitions, throttling, and delivery tests."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.broadcasts.entities import (
    BroadcastRecipientRecord,
    BroadcastRecord,
    CreateBroadcast,
)
from app.modules.broadcasts.errors import (
    BroadcastBlockedError,
    BroadcastDeliveryError,
    BroadcastRetryAfterError,
    InvalidBroadcastError,
)
from app.modules.broadcasts.models import (
    BroadcastContentType,
    BroadcastMediaType,
    BroadcastRecipientStatus,
    BroadcastStatus,
)
from app.modules.broadcasts.service import (
    BroadcastDeliveryService,
    BroadcastRateLimiter,
    BroadcastService,
)


def broadcast_record(
    *,
    broadcast_id: int = 7,
    owner_id: int = 123456789,
    status: str = BroadcastStatus.DRAFT.value,
    content_type: str = BroadcastContentType.TEXT.value,
) -> BroadcastRecord:
    timestamp = datetime(2026, 9, 1, tzinfo=UTC)
    return BroadcastRecord(
        id=broadcast_id,
        created_by_telegram_user_id=owner_id,
        content_type=content_type,
        text="Announcement" if content_type == BroadcastContentType.TEXT.value else None,
        media_type=(
            BroadcastMediaType.PHOTO.value
            if content_type == BroadcastContentType.MEDIA.value
            else None
        ),
        media_file_id="file-id" if content_type == BroadcastContentType.MEDIA.value else None,
        caption="Caption" if content_type == BroadcastContentType.MEDIA.value else None,
        status=status,
        total_recipients=3,
        sent_count=1,
        failed_count=1,
        blocked_count=1,
        confirmed_at=timestamp if status != BroadcastStatus.DRAFT.value else None,
        completed_at=timestamp if status == BroadcastStatus.COMPLETED.value else None,
        created_at=timestamp,
        updated_at=timestamp,
        source_chat_id=(123456789 if content_type == BroadcastContentType.FORWARD.value else None),
        source_message_id=(55 if content_type == BroadcastContentType.FORWARD.value else None),
    )


def recipient() -> BroadcastRecipientRecord:
    return BroadcastRecipientRecord(
        id=11,
        broadcast_id=7,
        user_id=22,
        telegram_user_id=987654321,
        status=BroadcastRecipientStatus.PENDING.value,
        attempts=0,
        last_error_code=None,
        sent_at=None,
    )


def repository() -> SimpleNamespace:
    return SimpleNamespace(
        create_draft=AsyncMock(return_value=broadcast_record()),
        get_owned=AsyncMock(return_value=broadcast_record()),
        cancel_draft=AsyncMock(
            return_value=broadcast_record(status=BroadcastStatus.CANCELLED.value)
        ),
        claim_and_snapshot=AsyncMock(
            return_value=broadcast_record(status=BroadcastStatus.PROCESSING.value)
        ),
    )


async def test_text_draft_is_trimmed_before_persistence() -> None:
    repo = repository()

    await BroadcastService(repo).create_draft(
        CreateBroadcast(
            created_by_telegram_user_id=123456789,
            content_type=BroadcastContentType.TEXT.value,
            text="  Announcement  ",
        )
    )

    submitted = repo.create_draft.await_args.args[0]
    assert submitted.text == "Announcement"
    assert submitted.media_file_id is None


@pytest.mark.parametrize(
    "draft",
    [
        CreateBroadcast(1, BroadcastContentType.TEXT.value, text=""),
        CreateBroadcast(1, BroadcastContentType.TEXT.value, text="x" * 4097),
        CreateBroadcast(1, "UNKNOWN", text="text"),
        CreateBroadcast(1, BroadcastContentType.MEDIA.value, media_type="STICKER"),
        CreateBroadcast(
            1,
            BroadcastContentType.MEDIA.value,
            media_type=BroadcastMediaType.PHOTO.value,
            media_file_id="file",
            caption="x" * 1025,
        ),
    ],
)
async def test_invalid_drafts_are_rejected_before_repository(draft: CreateBroadcast) -> None:
    repo = repository()

    with pytest.raises(InvalidBroadcastError):
        await BroadcastService(repo).create_draft(draft)

    repo.create_draft.assert_not_awaited()


@pytest.mark.parametrize("media_type", [item.value for item in BroadcastMediaType])
async def test_all_phase_eight_media_types_are_accepted(media_type: str) -> None:
    repo = repository()

    await BroadcastService(repo).create_draft(
        CreateBroadcast(
            created_by_telegram_user_id=1,
            content_type=BroadcastContentType.MEDIA.value,
            media_type=media_type,
            media_file_id=" file-id ",
            caption=" caption ",
        )
    )

    submitted = repo.create_draft.await_args.args[0]
    assert submitted.media_file_id == "file-id"
    assert submitted.caption == "caption"


async def test_forward_source_is_validated_and_persisted_without_copied_content() -> None:
    repo = repository()

    await BroadcastService(repo).create_draft(
        CreateBroadcast(
            created_by_telegram_user_id=1,
            content_type=BroadcastContentType.FORWARD.value,
            source_chat_id=123456789,
            source_message_id=55,
        )
    )

    submitted = repo.create_draft.await_args.args[0]
    assert submitted.source_chat_id == 123456789
    assert submitted.source_message_id == 55
    assert submitted.text is None
    assert submitted.media_file_id is None


@pytest.mark.parametrize(
    "draft",
    [
        CreateBroadcast(1, BroadcastContentType.FORWARD.value),
        CreateBroadcast(
            1,
            BroadcastContentType.FORWARD.value,
            source_chat_id=0,
            source_message_id=1,
        ),
        CreateBroadcast(
            1,
            BroadcastContentType.FORWARD.value,
            source_chat_id=123,
            source_message_id=0,
        ),
        CreateBroadcast(
            1,
            BroadcastContentType.FORWARD.value,
            text="copied",
            source_chat_id=123,
            source_message_id=1,
        ),
    ],
)
async def test_invalid_forward_sources_are_rejected(draft: CreateBroadcast) -> None:
    repo = repository()

    with pytest.raises(InvalidBroadcastError):
        await BroadcastService(repo).create_draft(draft)

    repo.create_draft.assert_not_awaited()


async def test_preview_confirm_and_cancel_enforce_owner_and_state() -> None:
    repo = repository()
    service = BroadcastService(repo)
    confirmed_at = datetime(2026, 9, 1, 12, tzinfo=UTC)

    preview = await service.get_preview(7, 123456789)
    await service.confirm(7, 123456789, confirmed_at=confirmed_at)
    await service.cancel(7, 123456789)

    assert preview.status == BroadcastStatus.DRAFT.value
    repo.get_owned.assert_awaited_once_with(7, 123456789)
    repo.claim_and_snapshot.assert_awaited_once_with(
        7,
        123456789,
        confirmed_at=confirmed_at,
    )
    repo.cancel_draft.assert_awaited_once_with(7, 123456789)


async def test_rate_limiter_waits_between_consecutive_sends() -> None:
    clock = SimpleNamespace(value=10.0)
    sleep = AsyncMock()
    limiter = BroadcastRateLimiter(
        10,
        sleep=sleep,
        monotonic=lambda: clock.value,
    )

    await limiter.wait()
    await limiter.wait()

    sleep.assert_awaited_once_with(pytest.approx(0.1))


@pytest.mark.parametrize(
    ("side_effect", "expected_status", "attempts", "error_code"),
    [
        (None, BroadcastRecipientStatus.SENT.value, 1, None),
        (
            BroadcastDeliveryError("BAD_REQUEST"),
            BroadcastRecipientStatus.FAILED.value,
            1,
            "BAD_REQUEST",
        ),
        (
            BroadcastBlockedError(),
            BroadcastRecipientStatus.BLOCKED.value,
            1,
            "BOT_BLOCKED",
        ),
    ],
)
async def test_delivery_maps_each_terminal_outcome(
    side_effect: Exception | None,
    expected_status: str,
    attempts: int,
    error_code: str | None,
) -> None:
    gateway = SimpleNamespace(send=AsyncMock(side_effect=side_effect))
    delivery = BroadcastDeliveryService(
        SimpleNamespace(),
        gateway,
        rate_per_second=20,
        batch_size=10,
        max_retries=2,
        retry_after_cap_seconds=60,
        sleep=AsyncMock(),
    )

    status, actual_attempts, actual_error, sent_at = await delivery._deliver_one(
        recipient(),
        broadcast_record(status=BroadcastStatus.PROCESSING.value),
    )

    assert (status, actual_attempts, actual_error) == (
        expected_status,
        attempts,
        error_code,
    )
    assert (sent_at is not None) is (expected_status == BroadcastRecipientStatus.SENT.value)


async def test_retry_after_is_bounded_and_stops_after_configured_retries() -> None:
    gateway = SimpleNamespace(send=AsyncMock(side_effect=BroadcastRetryAfterError(999)))
    sleep = AsyncMock()
    delivery = BroadcastDeliveryService(
        SimpleNamespace(),
        gateway,
        rate_per_second=20,
        batch_size=10,
        max_retries=2,
        retry_after_cap_seconds=30,
        sleep=sleep,
    )

    status, attempts, error_code, sent_at = await delivery._deliver_one(
        recipient(),
        broadcast_record(status=BroadcastStatus.PROCESSING.value),
    )

    assert status == BroadcastRecipientStatus.FAILED.value
    assert attempts == 3
    assert error_code == "RATE_LIMITED"
    assert sent_at is None
    assert [call.args for call in sleep.await_args_list].count((30,)) == 2


async def test_delivery_run_persists_outcomes_and_returns_final_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delivery = BroadcastDeliveryService(
        SimpleNamespace(),
        SimpleNamespace(send=AsyncMock()),
        rate_per_second=20,
        batch_size=10,
        max_retries=0,
        retry_after_cap_seconds=30,
        sleep=AsyncMock(),
    )
    processing = broadcast_record(status=BroadcastStatus.PROCESSING.value)
    completed = broadcast_record(status=BroadcastStatus.COMPLETED.value)
    monkeypatch.setattr(delivery, "_load_broadcast", AsyncMock(return_value=processing))
    monkeypatch.setattr(delivery, "_load_pending", AsyncMock(side_effect=[(recipient(),), ()]))
    monkeypatch.setattr(
        delivery,
        "_deliver_one",
        AsyncMock(return_value=(BroadcastRecipientStatus.SENT.value, 1, None, datetime.now(UTC))),
    )
    mark = AsyncMock()
    monkeypatch.setattr(delivery, "_mark_recipient", mark)
    monkeypatch.setattr(delivery, "_finalize", AsyncMock(return_value=completed))

    report = await delivery.run(7)

    assert report.broadcast_id == 7
    assert report.status == BroadcastStatus.COMPLETED.value
    assert report.total_recipients == 3
    mark.assert_awaited_once()
