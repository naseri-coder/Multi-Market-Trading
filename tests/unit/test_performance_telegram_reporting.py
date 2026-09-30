from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram.error import TelegramError

from app.core.config import Settings
from app.modules.performance_intelligence import (
    PerformanceAnalytics,
    PerformanceCollector,
    PerformanceReportEngine,
    PerformanceReportingPipeline,
    PerformanceReportType,
    PerformanceTelegramPublisher,
    PerformanceTelegramReportTemplate,
)
from app.modules.performance_intelligence.telegram_publisher import PerformancePublishResult


def test_performance_report_configuration_loads(valid_token: str, valid_database_url: str) -> None:
    settings = Settings(
        _env_file=None,
        telegram_bot_token=valid_token,
        database_url=valid_database_url,
        performance_reports_enabled=True,
        performance_report_channel_id=None,
        performance_report_parse_mode="html",
        performance_report_timezone="UTC",
        performance_report_max_retry=3,
    )
    assert settings.performance_reports_enabled is True
    assert settings.performance_report_channel_id is None
    assert settings.performance_report_parse_mode == "HTML"
    assert settings.performance_report_timezone == "UTC"
    assert settings.performance_report_max_retry == 3


def test_template_contains_required_sections_and_escapes_html() -> None:
    template = PerformanceTelegramReportTemplate("UTC")
    text = template.render(
        report_type=PerformanceReportType.DAILY,
        runtime_health={"cpu": "0.1%"},
        signal_performance={"note": "<safe>"},
        comparison={"agreement": "90%"},
        runtime_status={"shadow": "ACTIVE"},
        recommended_improvements=("Review weak setups",),
    )
    for heading in (
        "Performance Intelligence Report",
        "Runtime Health",
        "Signal Performance",
        "Pattern Intelligence",
        "Failure Analysis",
        "Opportunity Analysis",
        "Confidence Calibration",
        "Compare",
        "Runtime Status",
        "Recommended Improvements",
    ):
        assert heading in text
    assert "&lt;safe&gt;" in text
    assert len(text) <= 4096


@pytest.mark.asyncio
async def test_publisher_validates_private_channel_admin_and_post_permission() -> None:
    bot = AsyncMock()
    bot.get_me.return_value = SimpleNamespace(id=42)
    bot.get_chat.return_value = SimpleNamespace(type="channel")
    bot.get_chat_member.return_value = SimpleNamespace(
        status="administrator", can_post_messages=True
    )
    publisher = PerformanceTelegramPublisher(bot=bot, channel_id=-100123, max_retry=3)
    result = await publisher.validate_channel()
    assert result.valid is True
    assert result.bot_is_admin is True
    assert result.can_post_messages is True


@pytest.mark.asyncio
async def test_publisher_retries_then_succeeds() -> None:
    bot = AsyncMock()
    bot.send_message.side_effect = [
        TelegramError("temporary"),
        SimpleNamespace(message_id=77),
    ]
    publisher = PerformanceTelegramPublisher(bot=bot, channel_id=-100123, max_retry=3)
    result = await publisher.publish("<b>report</b>")
    assert result.success is True
    assert result.attempts == 2
    assert result.message_id == "77"
    assert bot.send_message.await_count == 2


@pytest.mark.asyncio
async def test_publisher_exhaustion_is_fail_open() -> None:
    bot = AsyncMock()
    bot.send_message.side_effect = TelegramError("offline")
    publisher = PerformanceTelegramPublisher(bot=bot, channel_id=-100123, max_retry=2)
    result = await publisher.publish("report")
    assert result.success is False
    assert result.attempts == 3
    assert result.error == "TelegramError"


@pytest.mark.asyncio
async def test_pipeline_is_collect_analyze_report_publish_only() -> None:
    class FakePublisher:
        def __init__(self) -> None:
            self.messages: list[str] = []

        async def publish(self, text: str) -> PerformancePublishResult:
            self.messages.append(text)
            return PerformancePublishResult(True, 1, "9")

    fake_publisher = FakePublisher()
    pipeline = PerformanceReportingPipeline(
        collector=PerformanceCollector(),
        analytics=PerformanceAnalytics(),
        report_engine=PerformanceReportEngine(timezone_name="UTC"),
        publisher=fake_publisher,  # type: ignore[arg-type]
    )
    signals = [
        SimpleNamespace(id=1, status="WIN", profit_loss=Decimal("5")),
        SimpleNamespace(id=2, status="LOSS", profit_loss=Decimal("-2")),
    ]
    result = await pipeline.run(
        signals=signals,
        report_type=PerformanceReportType.DAILY,
        comparison={"decision_agreement": "compare-only"},
        runtime_status={"mode": "shadow/read-only"},
    )
    assert result.success is True
    assert len(fake_publisher.messages) == 1
    assert "0.5" in fake_publisher.messages[0]
    assert "compare-only" in fake_publisher.messages[0]
