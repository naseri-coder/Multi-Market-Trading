from pathlib import Path
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.db.models import MODEL_TYPES
from app.modules.scale_in.models import (
    BrooksPosition, BrooksPositionEntryLot, BrooksPositionExitFill,
    BrooksPositionScaleEvent, BrooksPositionRiskSnapshot,
)


def base():
    return dict(telegram_bot_token="123456789:" + "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
                database_url="postgresql+asyncpg://u:p@db/test", _env_file=None)


def test_scale_in_disabled_by_default():
    assert Settings(**base()).brooks_scale_in_mode == "disabled"


def test_scale_in_shadow_requires_brooks_runtime():
    with pytest.raises(ValidationError, match="requires BROOKS_RUNTIME_ENABLED=true"):
        Settings(**base(), brooks_scale_in_mode="shadow")


def test_scale_in_live_is_fail_closed_without_execution_connector():
    with pytest.raises(ValidationError, match="no exchange execution/reconciliation connector"):
        Settings(**base(), brooks_scale_in_mode="live")


def test_scale_in_models_registered_for_alembic_metadata():
    for model in (BrooksPosition, BrooksPositionEntryLot, BrooksPositionExitFill,
                  BrooksPositionScaleEvent, BrooksPositionRiskSnapshot):
        assert model in MODEL_TYPES


def test_scale_in_migration_is_additive_and_chained():
    root=Path(__file__).resolve().parents[2]
    text=(root/"migrations/versions/20260914_0020_brooks_multi_lot_scale_in.py").read_text()
    assert 'revision = "20260914_0020"' in text
    assert 'down_revision = "20260912_0019"' in text
    for table in ("brooks_positions","brooks_position_entry_lots","brooks_position_exit_fills",
                  "brooks_position_scale_events","brooks_position_risk_snapshots"):
        assert table in text
    assert "ALTER TABLE signals" not in text.upper()


def test_scale_in_explicit_disabled_and_case_normalization():
    assert Settings(**base(), brooks_scale_in_mode=" DISABLED ").brooks_scale_in_mode == "disabled"


def test_scale_in_shadow_is_accepted_only_with_safe_runtime_context():
    settings = Settings(**base(), brooks_scale_in_mode=" ShAdOw ",
        brooks_runtime_enabled=True, brooks_runtime_mode="paper",
        brooks_timeframes=("15m",), paper_runtime_enabled=True,
        paper_private_test_channel_id=-1001234567890)
    assert settings.brooks_scale_in_mode == "shadow"


def test_scale_in_invalid_value_is_rejected():
    with pytest.raises(ValidationError):
        Settings(**base(), brooks_scale_in_mode="not-a-mode")


def test_scale_in_live_case_normalizes_then_fails_closed():
    with pytest.raises(ValidationError, match="no exchange execution/reconciliation connector"):
        Settings(**base(), brooks_scale_in_mode=" LIVE ")
