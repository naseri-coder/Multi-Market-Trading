"""Stage 3J: prove SIGNAL_ONLY and PAPER independently; no live/order network."""
from __future__ import annotations

from decimal import Decimal as D

import pytest

from naseri_markets.adapter_free_paper_runtime_v1 import PipelineRefused
from naseri_markets.offline_signal_lifecycle_v1 import OfflineSignalLifecycle
from test_adapter_free_paper_runtime_v1 import T0, _candles, _setup


def _close(control, paper, signals):
    signals.close()
    paper.close()
    control.close()


def test_signal_only_receipt_is_durable_and_cannot_create_paper_order(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    control, paper, signals, runtime, state, binding = _setup(
        tmp_path, signals_on=True, paper_on=False,
    )
    receipt = None
    try:
        status = runtime.status("fixture_instance")
        assert status.signal_preview_requested is True
        assert status.paper_requested is False
        assert status.telegram_publication_enabled is False
        assert status.broker_orders_enabled is False
        arguments = dict(
            candles=_candles(), source_ref="stage3j-offline-candles",
            expected_panel_revision=state.revision, operator_ack=True,
            dry_run_channel_id=-100123,
        )
        receipt = runtime.replay("fixture_instance", binding.binding_id, **arguments)
        assert receipt["decision_count"] == 1
        assert len(receipt["signal_keys"]) == 1
        assert receipt["paper_order_ids"] == []
        assert receipt["telegram_sent"] is False
        assert receipt["broker_order_sent"] is False
        assert runtime.replay("fixture_instance", binding.binding_id, **arguments) == receipt
        assert paper._db.execute(
            "SELECT count(*) FROM paper_core_orders"
        ).fetchone()[0] == 0
        key = receipt["signal_keys"][0]
        preview = runtime.admin_preview("fixture_instance", signal_key=key)
        assert preview["dry_run_commands"] == 1
        assert preview["telegram_sent"] is False
    finally:
        _close(control, paper, signals)

    assert receipt is not None
    with OfflineSignalLifecycle(tmp_path / "signals.sqlite", enabled=True) as restored:
        key = receipt["signal_keys"][0]
        assert restored.snapshot(key).instance_id == "fixture_instance"
        assert len(restored.commands(key)) == 1
        assert restored.snapshot(key).message_id is None


def test_paper_only_creates_simulated_order_but_no_signal_delivery(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    control, paper, signals, runtime, state, binding = _setup(
        tmp_path, signals_on=False, paper_on=True,
    )
    try:
        status = runtime.status("fixture_instance")
        assert status.paper_requested is True
        assert status.signal_preview_requested is False
        assert status.broker_orders_enabled is False
        authorized = runtime.authorize_paper(
            "fixture_instance", expected_panel_revision=state.revision,
            now=T0, operator_ack=True,
        )
        assert authorized["broker_order_sent"] is False
        params = dict(
            candles=_candles(), source_ref="stage3j-offline-candles",
            expected_panel_revision=state.revision, operator_ack=True,
            quantity=D(1),
        )
        receipt = runtime.replay("fixture_instance", binding.binding_id, **params)
        assert receipt["decision_count"] == 1
        assert len(receipt["paper_order_ids"]) == 1
        assert receipt["signal_keys"] == []
        assert receipt["telegram_sent"] is False
        assert receipt["broker_order_sent"] is False
        assert runtime.replay("fixture_instance", binding.binding_id, **params) == receipt
        assert paper._db.execute(
            "SELECT count(*) FROM paper_core_orders"
        ).fetchone()[0] == 1
        assert signals._db.execute(
            "SELECT count(*) FROM offline_signal_states"
        ).fetchone()[0] == 0
        with pytest.raises(PipelineRefused, match="SIGNAL_PREVIEW_DISABLED"):
            runtime.admin_preview("fixture_instance", signal_key="0" * 64)
    finally:
        _close(control, paper, signals)


def test_signal_and_paper_both_disabled_cannot_be_promoted(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    control, paper, signals, runtime, state, binding = _setup(
        tmp_path, signals_on=False, paper_on=False,
    )
    try:
        receipt = runtime.replay(
            "fixture_instance", binding.binding_id,
            candles=_candles(), source_ref="stage3j-offline-candles",
            expected_panel_revision=state.revision, operator_ack=True,
        )
        assert receipt["decision_count"] == 1
        assert receipt["paper_order_ids"] == []
        assert receipt["signal_keys"] == []
        assert not receipt["telegram_sent"]
        assert not receipt["broker_order_sent"]
        assert paper._db.execute(
            "SELECT count(*) FROM paper_core_orders"
        ).fetchone()[0] == 0
        assert signals._db.execute(
            "SELECT count(*) FROM offline_signal_states"
        ).fetchone()[0] == 0
    finally:
        _close(control, paper, signals)


def test_existing_live_fence_denies_both_pipelines_without_mutating_ledgers(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    control, paper, signals, runtime, state, binding = _setup(tmp_path)
    try:
        monkeypatch.setenv("MMT_PRODUCTION", "1")
        with pytest.raises(PipelineRefused, match="NONPRODUCTION_ENV_REQUIRED"):
            runtime.replay(
                "fixture_instance", binding.binding_id,
                candles=_candles(), source_ref="stage3j-offline-candles",
                expected_panel_revision=state.revision, operator_ack=True,
                quantity=D(1), dry_run_channel_id=-100123,
            )
        assert paper._db.execute(
            "SELECT count(*) FROM paper_core_orders"
        ).fetchone()[0] == 0
        assert signals._db.execute(
            "SELECT count(*) FROM offline_signal_states"
        ).fetchone()[0] == 0
    finally:
        _close(control, paper, signals)
