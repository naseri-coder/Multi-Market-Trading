"""Stage-11 reviewed core parameters in the existing Stage-12 offline panel."""
from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from naseri_markets._contract_acceptance_fixture_v1 import OfflineContractFixture
from naseri_markets.trading_control_center_v1 import (
    ControlRefused, CoreListing, OfflineTradingControlCenter,
)
from naseri_markets.trading_control_telegram_v1 import TelegramControlPreviewPanel


MANIFEST = OfflineContractFixture().manifest
SCHEMA = {
    "schema_version": 1, "core_id": MANIFEST.core_id,
    "core_version": MANIFEST.core_version,
    "parameters": [
        {"name": "fast_period", "kind": "integer", "min": 2, "max": 50, "step": 1},
        {"name": "slow_period", "kind": "integer", "min": 4, "max": 100, "step": 1},
        {"name": "stop_buffer", "kind": "decimal",
         "min": "0.10", "max": "1.00", "step": "0.05"},
        {"name": "confirmation", "kind": "boolean"},
        {"name": "average_type", "kind": "choice", "options": ["ema", "sma"]},
    ],
    "relations": [{"left": "fast_period", "op": "lt", "right": "slow_period"}],
}
RAW_SCHEMA = json.dumps(SCHEMA, sort_keys=True, separators=(",", ":")).encode()
SCHEMA_PIN = hashlib.sha256(RAW_SCHEMA).hexdigest()
LISTING = CoreListing(
    MANIFEST.core_id, "Reviewed Fixture Core", MANIFEST.core_version,
    manifest=MANIFEST, parameter_schema_bytes=RAW_SCHEMA,
    trusted_parameter_schema_sha256=SCHEMA_PIN,
)
OWNER = 1101
OTHER = 2202


def settings(values=None, *, core_id=None, version=None):
    body = {
        "schema_version": 1, "core_id": core_id or MANIFEST.core_id,
        "core_version": version or MANIFEST.core_version,
        "values": values if values is not None else {
            "fast_period": 10, "slow_period": 26, "stop_buffer": "0.25",
            "confirmation": True, "average_type": "ema",
        },
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()


@pytest.fixture()
def store(tmp_path):
    with OfflineTradingControlCenter(
        tmp_path / "stage12.sqlite", admin_ids={OWNER, OTHER},
        listings=(LISTING,), enabled=True,
    ) as center:
        center.create_instance(
            OWNER, core_id=MANIFEST.core_id, instance_id="private_research",
            account_id="sample_acct", portfolio_id="sample_portfolio",
        )
        yield center


def submit(center, payload=None, *, revision=None, actor=OWNER):
    return center.set_core_parameters(
        actor, "private_research",
        settings_bytes=settings() if payload is None else payload,
        expected_revision=revision if revision is not None
        else center.inspect(OWNER, "private_research").revision,
    )


def test_schema_requires_externally_reviewed_paired_pin_and_core_manifest():
    with pytest.raises(ControlRefused, match="INCOMPLETE"):
        replace(LISTING, trusted_parameter_schema_sha256=None)
    with pytest.raises(ControlRefused, match="UNREVIEWED"):
        replace(LISTING, trusted_parameter_schema_sha256="f" * 64)
    with pytest.raises(ControlRefused, match="UNREVIEWED"):
        replace(LISTING, manifest=None)
    with pytest.raises(ControlRefused, match="MANIFEST_IDENTITY"):
        replace(LISTING, version="999.9")


def test_valid_settings_atomic_versioned_persistence_and_safe_receipt(store):
    before = store.inspect(OWNER, "private_research")
    rec = submit(store)
    assert rec.revision == before.revision + 1
    info = store.inspect_core_parameters(OWNER, "private_research")
    assert info["status"] == "VALIDATED_RESEARCH_SETTINGS"
    assert info["schema_sha256"] == SCHEMA_PIN
    assert info["settings_sha256"] == hashlib.sha256(settings()).hexdigest()
    assert info["count"] == 5
    assert info["trading_authorized"] is False
    audit = store.audit(OWNER, "private_research")
    assert audit[-1]["action"] == "SET_CORE_PARAMETERS"
    assert audit[-1]["revision"] == rec.revision
    assert not rec.live_trading_enabled and not rec.broker_orders_enabled


def test_missing_full_settings_refuses_without_revision_or_audit_change(store):
    before = store.inspect(OWNER, "private_research")
    count = len(store.audit(OWNER, "private_research"))
    for payload in (
        settings({"fast_period": 5}), settings(core_id="wrong_core"),
        settings(version="999"), b'{"schema_version":1,"schema_version":1}',
        b'{"values":{"api_key":"credential"}}',
    ):
        with pytest.raises(ControlRefused):
            submit(store, payload, revision=before.revision)
        assert store.inspect(OWNER, "private_research").revision == before.revision
        assert len(store.audit(OWNER, "private_research")) == count


def test_cross_field_relation_failure_refuses_without_side_effect(store):
    values = json.loads(settings())["values"]
    values["fast_period"] = 31
    values["slow_period"] = 26
    with pytest.raises(ControlRefused, match="INVALID_REVIEWED"):
        submit(store, settings(values))
    assert store.inspect_core_parameters(OWNER, "private_research")["status"] == (
        "REVIEWED_SCHEMA_UNCONFIGURED"
    )


def test_stale_cas_and_foreign_owner_refused_without_data_leak(store):
    initial = store.inspect(OWNER, "private_research").revision
    submit(store)
    with pytest.raises(ControlRefused, match="STALE"):
        submit(store, revision=initial)
    with pytest.raises(ControlRefused, match="INSTANCE_NOT_ACCESSIBLE"):
        submit(store, actor=OTHER, revision=initial+1)
    with pytest.raises(ControlRefused, match="INSTANCE_NOT_ACCESSIBLE"):
        store.inspect_core_parameters(OTHER, "private_research")


def test_edit_requires_all_execution_requests_off(store):
    submit(store)
    # Only the requested flag becomes true, NEVER execution authority.
    store._db.execute(
        "UPDATE t12_instances SET analysis=1 WHERE instance_id='private_research'"
    )
    with pytest.raises(ControlRefused, match="DISABLE_REQUESTS"):
        submit(store)
    store._db.execute(
        "UPDATE t12_instances SET analysis=0 WHERE instance_id='private_research'"
    )
    assert store.inspect_core_parameters(OWNER, "private_research")["count"] == 5


def test_schema_setting_is_required_before_positive_request(store):
    # No compatible instrument binding is needed to test schema fence: it
    # executes before the existing Stage-12 BINDING_REQUIRED condition.
    before = store.inspect(OWNER, "private_research")
    with pytest.raises(ControlRefused, match="PARAMETERS_REQUIRED"):
        store.set_request(
            OWNER, "private_research", field="analysis", requested=True,
            expected_revision=before.revision,
        )
    submit(store)
    with pytest.raises(ControlRefused, match="BINDING_REQUIRED"):
        store.set_request(
            OWNER, "private_research", field="analysis", requested=True,
            expected_revision=before.revision + 1,
        )


def test_reopen_with_same_host_pin_and_drift_or_missing_host_pin(tmp_path):
    dbpath = tmp_path / "params.sqlite"
    with OfflineTradingControlCenter(
        dbpath, admin_ids={OWNER}, listings=(LISTING,), enabled=True,
    ) as control:
        control.create_instance(
            OWNER, core_id=MANIFEST.core_id, instance_id="params_case",
            account_id="sample_acct", portfolio_id="sample_portfolio",
        )
        control.set_core_parameters(
            OWNER, "params_case", settings_bytes=settings(),
            expected_revision=1,
        )
    with OfflineTradingControlCenter(
        dbpath, admin_ids={OWNER}, listings=(LISTING,), enabled=True,
    ) as control:
        assert control.inspect_core_parameters(OWNER, "params_case")[
            "status"
        ] == "VALIDATED_RESEARCH_SETTINGS"
        control._db.execute(
            "UPDATE t12_parameter_settings SET settings_sha256=? "
            "WHERE instance_id=?", ("0" * 64, "params_case"),
        )
        with pytest.raises(ControlRefused, match="DRIFT"):
            control.inspect_core_parameters(OWNER, "params_case")
    unpinned = replace(
        LISTING, parameter_schema_bytes=None,
        trusted_parameter_schema_sha256=None,
    )
    with OfflineTradingControlCenter(
        dbpath, admin_ids={OWNER}, listings=(unpinned,), enabled=True,
    ) as control:
        with pytest.raises(ControlRefused, match="PIN_MISSING"):
            control.inspect_core_parameters(OWNER, "params_case")


def test_unreviewed_brooks_reference_cannot_accept_parameters(tmp_path):
    with OfflineTradingControlCenter(
        tmp_path / "brooks.sqlite", admin_ids={OWNER}, enabled=True,
    ) as control:
        control.create_instance(
            OWNER, core_id="brooks_price_action",
            instance_id="brooks_ref", account_id="a1", portfolio_id="p1",
        )
        with pytest.raises(ControlRefused, match="SCHEMA_REQUIRED"):
            control.set_core_parameters(
                OWNER, "brooks_ref", settings_bytes=settings(),
                expected_revision=1,
            )


class FakeMessage:
    def __init__(self, text):
        self.text = text
        self.responses = []

    async def reply_text(self, text, reply_markup=None):
        self.responses.append(text)


def context(text, actor=OWNER, private=True):
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=actor),
        effective_chat=SimpleNamespace(
            id=actor if private else -1, type="private" if private else "group",
        ),
        effective_message=FakeMessage(text), callback_query=None,
    )


def test_telegram_private_commands_and_no_reflection_of_bad_payload(store):
    panel = TelegramControlPreviewPanel(store)
    empty = context("/mmt12_params private_research")
    asyncio.run(panel.command(empty, None))
    assert "REVIEWED_SCHEMA_UNCONFIGURED" in empty.effective_message.responses[0]
    assert "fast_period" in empty.effective_message.responses[0]
    secret = "CREDENTIAL_DO_NOT_ECHO_145"
    bad = context(
        f"/mmt12_param_set private_research 1 "
        f'{{"schema_version":1,"core_id":"{MANIFEST.core_id}",'
        f'"core_version":"{MANIFEST.core_version}",'
        f'"values":{{"password":"{secret}"}}}}'
    )
    asyncio.run(panel.command(bad, None))
    assert secret not in bad.effective_message.responses[0]
    assert store.inspect(OWNER, "private_research").revision == 1
    foreign = context("/mmt12_params private_research", actor=OTHER)
    asyncio.run(panel.command(foreign, None))
    assert "غیرمجاز" in foreign.effective_message.responses[0]
    group = context("/mmt12_params private_research", private=False)
    asyncio.run(panel.command(group, None))
    assert "غیرمجاز" in group.effective_message.responses[0]
    valid = context(f"/mmt12_param_set private_research 1 {settings().decode()}")
    # Detail view uses approved widget stubs only for formatting its inline kb.
    import sys
    import types
    fake = types.ModuleType("telegram")
    fake.InlineKeyboardButton = lambda *a, **k: SimpleNamespace()
    fake.InlineKeyboardMarkup = lambda data: SimpleNamespace()
    original = sys.modules.get("telegram")
    sys.modules["telegram"] = fake
    try:
        asyncio.run(panel.command(valid, None))
    finally:
        if original is None:
            sys.modules.pop("telegram", None)
        else:
            sys.modules["telegram"] = original
    assert "VALIDATED_RESEARCH_SETTINGS" in valid.effective_message.responses[0]
