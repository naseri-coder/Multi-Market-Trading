from decimal import Decimal
import pytest

from app.modules.brooks_core.fundamentals_policy import FundamentalsExecutionPolicy


def test_autonomous_decisions_are_disabled_by_default():
    assert FundamentalsExecutionPolicy().enable_trade_decisions is False


def test_configuration_version_contains_engineering_parameters():
    policy = FundamentalsExecutionPolicy(
        swing_left_bars=3,
        swing_right_bars=2,
        target_r_multiples=(Decimal("1.5"), Decimal("2")),
    )
    assert "swingL3R2" in policy.configuration_version
    assert "targets1.5-2" in policy.configuration_version


def test_invalid_target_policy_rejected():
    with pytest.raises(ValueError):
        FundamentalsExecutionPolicy(target_r_multiples=(Decimal("0"),))
