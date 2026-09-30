from decimal import Decimal
import pytest
from app.modules.brooks_core.engine_contract import BrooksEngineResult

def test_tradeable_engine_result_requires_targets():
    with pytest.raises(ValueError, match="requires targets"):
        BrooksEngineResult(
            decision="LONG",
            entry_price=Decimal("100"),
            stop_loss=Decimal("95"),
            targets=(),
            setup_type="H2",
            reasoning=(),
            rule_ids=(),
            failed_rules=(),
            rule_evidence=(),
            engine_version="v1",
            rule_set_version="r1",
            configuration_version="c1",
        )

def test_no_signal_is_valid_without_prices():
    result = BrooksEngineResult(
        decision="NO_SIGNAL",
        entry_price=None,
        stop_loss=None,
        targets=(),
        setup_type=None,
        reasoning=(),
        rule_ids=(),
        failed_rules=(),
        rule_evidence=(),
        engine_version="v1",
        rule_set_version="r1",
        configuration_version="c1",
    )
    assert result.decision == "NO_SIGNAL"
