from pydantic import ValidationError
import pytest

from app.core.config import Settings


def base():
    return dict(
        telegram_bot_token="123456789:" + "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
        database_url="postgresql+asyncpg://u:p@db/test",
        _env_file=None,
    )


def test_paper_runtime_is_disabled_by_default() -> None:
    settings = Settings(**base())
    assert settings.paper_runtime_enabled is False


def test_enabled_paper_requires_private_test_channel() -> None:
    with pytest.raises(ValidationError):
        Settings(**base(), paper_runtime_enabled=True)


def test_enabled_paper_accepts_nonzero_private_test_channel() -> None:
    settings = Settings(
        **base(),
        paper_runtime_enabled=True,
        paper_private_test_channel_id=-1001234567890,
    )
    assert settings.paper_private_test_channel_id == -1001234567890
