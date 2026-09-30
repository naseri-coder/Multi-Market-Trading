from decimal import Decimal

import pytest

from app.modules.signal_automation.entities import BrooksRuleEvidence, BrooksSignalImport


def command(**overrides):
    values = {
        "source_signal_id": "core-1",
        "symbol": "BTCUSDT",
        "direction": "LONG",
        "entry_price": Decimal("100"),
        "stop_loss": Decimal("95"),
        "targets": (Decimal("110"), Decimal("120")),
        "leverage": Decimal("1"),
        "exchange": "binance",
        "market_type": "spot",
        "timeframe": "15m",
        "setup_type": "H2",
        "market_snapshot_id": "snap-1",
        "market_snapshot_hash": "hash-1",
        "engine_version": "0.10.0",
        "rule_set_version": "phase2-catalog-v1",
        "configuration_version": "cfg-001",
        "reasoning": ("context aligned",),
        "rule_ids": ("BR-007",),
        "failed_rules": (),
        "rule_evidence": (BrooksRuleEvidence("BR-007", "PASS", (11,)),),
        "generation_mode": "PAPER",
        "publication_scope": "PRIVATE_TEST",
        "counts_toward_performance": False,
    }
    values.update(overrides)
    return BrooksSignalImport(**values)


def test_idempotency_key_is_deterministic() -> None:
    first = command()
    second = command()
    assert first.idempotency_key == second.idempotency_key
    assert len(first.idempotency_key) == 64


def test_paper_cannot_leak_publicly_or_count_performance() -> None:
    with pytest.raises(ValueError):
        command(publication_scope="PUBLIC")
    with pytest.raises(ValueError):
        command(counts_toward_performance=True)


def test_maps_to_existing_create_signal() -> None:
    mapped = command().to_create_signal()
    assert mapped.symbol == "BTCUSDT"
    assert mapped.direction == "LONG"
    assert mapped.entry_price == Decimal("100")
    assert mapped.stop_loss == Decimal("95")
    assert mapped.leverage == Decimal("1")
    assert mapped.as_draft is False


def test_configuration_version_is_mandatory() -> None:
    with pytest.raises(ValueError):
        command(configuration_version="")
