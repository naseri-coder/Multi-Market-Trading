from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path

import pytest

from scripts import mmt_r42_offline_market_account_evidence_v1 as r


T = "2026-10-16T12:00:02Z"


def canon(d):
    return (json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


@pytest.fixture
def e(tmp_path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    objs = {
        "policy": dict(
            schema=1, scope="offline-synthetic-review-only", provider_id="fixture_feed",
            market="SPOT", symbol="BTCUSD", contract_id="BTCUSD_SPOT",
            region="TEST_REGION", eligible_regions=["TEST_REGION"], price_basis="TRADE",
            volume_semantics="TRADED", timeframe_seconds=300,
            max_market_lag_seconds=30, max_account_lag_seconds=120,
            account_alias="test_acct", currency="USD"),
        "market": dict(
            schema=1, provider_id="fixture_feed", market="SPOT", symbol="BTCUSD",
            contract_id="BTCUSD_SPOT", price_basis="TRADE", volume_semantics="TRADED",
            timeframe_seconds=300, received_at="2026-10-16T12:00:01Z",
            bars=[
                dict(sequence=100, open_at="2026-10-16T11:50:00Z",
                     close_at="2026-10-16T11:55:00Z", open="100", high="102",
                     low="99", close="101", volume="5"),
                dict(sequence=101, open_at="2026-10-16T11:55:00Z",
                     close_at="2026-10-16T12:00:00Z", open="101", high="104",
                     low="100", close="103", volume="6")]),
        "account": dict(
            schema=1, provider_id="fixture_feed", account_alias="test_acct",
            currency="USD", observed_at="2026-10-16T12:00:01Z",
            equity="1000", available="900", margin_used="100",
            positions=[dict(position_id="pos001", contract_id="BTCUSD_SPOT",
                            side="BUY", quantity="1", entry_price="101")],
            open_orders=[dict(order_id="ord001", contract_id="BTCUSD_SPOT",
                              side="SELL", quantity="0.5", limit_price="105")]),
    }
    objs["ledger"] = dict(objs["account"])
    del objs["ledger"]["provider_id"]

    def put(name):
        raw = canon(objs[name])
        path = tmp_path / (name + ".json")
        path.write_bytes(raw)
        return path, hashlib.sha256(raw).hexdigest()

    kwargs = {}
    for x in ("policy", "market", "account", "ledger"):
        path, sha = put(x)
        kwargs[x + "_path"] = path
        kwargs[x + "_sha256"] = sha
    kwargs.update(region="TEST_REGION", as_of_utc=T, operator_ack=True)

    def change(name):
        raw = canon(objs[name])
        kwargs[name + "_path"].write_bytes(raw)
        kwargs[name + "_sha256"] = hashlib.sha256(raw).hexdigest()

    return objs, kwargs, change


def test_happy(e):
    _, k, _ = e
    v = r.audit(**k)
    assert v["bars_checked"] == 2
    assert v["positions_compared"] == 1
    assert all(v[x] is False for x in (
        "provider_origin_authenticated", "account_owner_authenticated",
        "region_and_venue_legally_verified", "remote_account_reconciled",
        "live_orders_authorized", "paper_orders_authorized", "files_written"))


def test_no_writes(e):
    _, k, _ = e
    before = {k[n+"_path"]: k[n+"_path"].read_bytes()
              for n in ("market", "account", "policy", "ledger")}
    assert r.audit(**k) == r.audit(**k)
    assert before == {p: p.read_bytes() for p in before}


@pytest.mark.parametrize("field", ["policy", "market", "account", "ledger"])
def test_wrong_pin(e, field):
    _, k, _ = e
    k[field+"_sha256"] = "0"*64
    with pytest.raises(r.R42Refused, match="PIN_MISMATCH"):
        r.audit(**k)


def test_missing_ack(e):
    _, k, _ = e
    k["operator_ack"] = False
    with pytest.raises(r.R42Refused, match="NONPRODUCTION"):
        r.audit(**k)


@pytest.mark.parametrize("value", ["0", "1", "true", ""])
def test_prod_flag(e, monkeypatch, value):
    _, k, _ = e
    monkeypatch.setenv("MMT_PRODUCTION", value)
    with pytest.raises(r.R42Refused, match="NONPRODUCTION"):
        r.audit(**k)


def test_region_mismatch(e):
    _, k, _ = e
    k["region"] = "UNLISTED_REGION"
    with pytest.raises(r.R42Refused, match="REGION_POLICY"):
        r.audit(**k)


def test_missing_region_eligibility(e):
    o, k, ch = e
    o["policy"]["eligible_regions"] = ["OTHER_REGION"]
    ch("policy")
    with pytest.raises(r.R42Refused, match="REGION_POLICY"):
        r.audit(**k)


def test_market_provider(e):
    o, k, ch = e
    o["market"]["provider_id"] = "other_feed"
    ch("market")
    with pytest.raises(r.R42Refused, match="CONTRACT_OR_SOURCE"):
        r.audit(**k)


def test_market_contract(e):
    o, k, ch = e
    o["market"]["contract_id"] = "ANOTHER_CONTRACT"
    ch("market")
    with pytest.raises(r.R42Refused, match="CONTRACT_OR_SOURCE"):
        r.audit(**k)


def test_price_basis(e):
    o, k, ch = e
    o["market"]["price_basis"] = "MARK"
    ch("market")
    with pytest.raises(r.R42Refused, match="CONTRACT_OR_SOURCE"):
        r.audit(**k)


def test_seq_gap(e):
    o, k, ch = e
    o["market"]["bars"][1]["sequence"] = 104
    ch("market")
    with pytest.raises(r.R42Refused, match="SEQUENCE_GAP"):
        r.audit(**k)


def test_ohlc(e):
    o, k, ch = e
    o["market"]["bars"][1]["high"] = "100"
    ch("market")
    with pytest.raises(r.R42Refused, match="OHLC_INVALID"):
        r.audit(**k)


def test_future_receipt(e):
    o, k, ch = e
    o["market"]["received_at"] = "2026-10-16T12:00:03Z"
    ch("market")
    with pytest.raises(r.R42Refused, match="RECEIPT_IN_FUTURE"):
        r.audit(**k)


def test_stale_market(e):
    _, k, _ = e
    k["as_of_utc"] = "2026-10-16T12:01:00Z"
    with pytest.raises(r.R42Refused, match="MARKET_STALE"):
        r.audit(**k)


def test_market_time_gap(e):
    o, k, ch = e
    o["market"]["bars"][1]["open_at"] = "2026-10-16T11:54:59Z"
    ch("market")
    with pytest.raises(r.R42Refused, match="TIME_GAP"):
        r.audit(**k)


def test_account_future(e):
    o, k, ch = e
    o["account"]["observed_at"] = "2026-10-16T12:00:03Z"
    ch("account")
    with pytest.raises(r.R42Refused, match="ACCOUNT_STALE_OR_FUTURE"):
        r.audit(**k)


def test_account_balance_drift(e):
    o, k, ch = e
    o["account"]["equity"] = "1001"
    ch("account")
    with pytest.raises(r.R42Refused, match="ACCOUNT_EQUITY_OR_MARGIN_DRIFT"):
        r.audit(**k)


def test_unknown_account_position(e):
    o, k, ch = e
    o["account"]["positions"][0]["quantity"] = "2"
    ch("account")
    with pytest.raises(r.R42Refused, match="POSITION_SET"):
        r.audit(**k)


def test_unknown_account_order(e):
    o, k, ch = e
    o["account"]["open_orders"][0]["order_id"] = "ord002"
    ch("account")
    with pytest.raises(r.R42Refused, match="ORDER_SET"):
        r.audit(**k)


def test_unlisted_contract(e):
    o, k, ch = e
    o["account"]["positions"][0]["contract_id"] = "ETHUSD_SPOT"
    ch("account")
    with pytest.raises(r.R42Refused, match="UNKNOWN_CONTRACT"):
        r.audit(**k)


def test_balance_invariant(e):
    o, k, ch = e
    o["account"]["available"] = "999"
    o["account"]["margin_used"] = "200"
    ch("account")
    with pytest.raises(r.R42Refused, match="BALANCE_INCONSISTENT"):
        r.audit(**k)


def test_duplicate_json_key(e):
    _, k, _ = e
    raw = k["policy_path"].read_bytes().strip()
    raw = raw[:-1] + b',"schema":1}\n'
    k["policy_path"].write_bytes(raw)
    k["policy_sha256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(r.R42Refused, match="DUPLICATE_JSON_FIELD"):
        r.audit(**k)


def test_uncanonical_json(e):
    o, k, _ = e
    raw = json.dumps(o["policy"], indent=2).encode()
    k["policy_path"].write_bytes(raw)
    k["policy_sha256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(r.R42Refused, match="NONCANONICAL"):
        r.audit(**k)


def test_symlink(e):
    _, k, _ = e
    path = k["market_path"]
    link = path.parent/"link.json"
    link.symlink_to(path)
    k["market_path"] = link
    with pytest.raises(r.R42Refused, match="NON_SYMLINK"):
        r.audit(**k)


def test_hardlink(e):
    _, k, _ = e
    os.link(k["market_path"], k["market_path"].with_suffix(".backup"))
    with pytest.raises(r.R42Refused, match="BOUNDED_REGULAR"):
        r.audit(**k)


def test_bool_policy_timeframe(e):
    o, k, ch = e
    o["policy"]["timeframe_seconds"] = True
    ch("policy")
    with pytest.raises(r.R42Refused, match="REVIEW_POLICY_INVALID"):
        r.audit(**k)


def test_bool_sequence(e):
    o, k, ch = e
    o["market"]["bars"][1]["sequence"] = True
    ch("market")
    with pytest.raises(r.R42Refused, match="SEQUENCE_GAP"):
        r.audit(**k)


def test_price_float_refused(e):
    o, k, ch = e
    o["market"]["bars"][1]["close"] = 103.2
    ch("market")
    with pytest.raises(r.R42Refused, match="DECIMAL_STRING"):
        r.audit(**k)


def test_cli_fail_closed(e, capsys):
    _, k, _ = e
    k["policy_sha256"] = "0"*64
    args = []
    for name in ("policy", "market", "account", "ledger"):
        args += ["--"+name, str(k[name+"_path"]),
                 "--"+name+"-sha256", k[name+"_sha256"]]
    args += ["--region", k["region"], "--as-of-utc", k["as_of_utc"],
             "--ack-synthetic-offline"]
    assert r.main(args) == 2
    obj = json.loads(capsys.readouterr().out)
    assert obj["live_orders_authorized"] is False


def test_cli_success(e, capsys):
    _, k, _ = e
    args = []
    for name in ("policy", "market", "account", "ledger"):
        args += ["--"+name, str(k[name+"_path"]),
                 "--"+name+"-sha256", k[name+"_sha256"]]
    args += ["--region", k["region"], "--as-of-utc", k["as_of_utc"],
             "--ack-synthetic-offline"]
    assert r.main(args) == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["remote_account_reconciled"] is False


@pytest.mark.parametrize("field", ["market", "account", "ledger"])
def test_schema_version_spoof(e, field):
    o, k, ch = e
    o[field]["schema"] = True
    ch(field)
    with pytest.raises(r.R42Refused, match="SCHEMA_VERSION_INVALID"):
        r.audit(**k)


def test_empty_exposure_not_proof_of_remote_truth(e):
    o, k, ch = e
    for field in ("account", "ledger"):
        o[field]["positions"] = []
        o[field]["open_orders"] = []
        ch(field)
    v = r.audit(**k)
    assert v["positions_compared"] == v["orders_compared"] == 0
    assert v["remote_account_reconciled"] is False


def test_unapproved_feed_scope(e):
    o, k, ch = e
    o["policy"]["scope"] = "approved-live"
    ch("policy")
    with pytest.raises(r.R42Refused, match="REVIEW_POLICY_INVALID"):
        r.audit(**k)


def test_market_nan_volume(e):
    o, k, ch = e
    o["market"]["bars"][0]["volume"] = "NaN"
    ch("market")
    with pytest.raises(r.R42Refused, match="DECIMAL_STRING"):
        r.audit(**k)


def test_account_unknown_side(e):
    o, k, ch = e
    o["account"]["open_orders"][0]["side"] = "HOLD"
    ch("account")
    with pytest.raises(r.R42Refused, match="UNKNOWN_CONTRACT"):
        r.audit(**k)


def test_account_stale(e):
    o, k, ch = e
    o["account"]["observed_at"] = "2026-10-16T11:57:00Z"
    ch("account")
    with pytest.raises(r.R42Refused, match="ACCOUNT_STALE_OR_FUTURE"):
        r.audit(**k)


def test_distinct_pin_inputs_required(e):
    _, k, _ = e
    k["ledger_path"] = k["account_path"]
    k["ledger_sha256"] = k["account_sha256"]
    with pytest.raises(r.R42Refused, match="DISTINCT_EVIDENCE"):
        r.audit(**k)


@pytest.mark.parametrize("changed", ["account", "ledger"])
def test_r42c_rejects_mismatched_capture_epoch_even_when_values_match(e, changed):
    """Matching balances/positions/orders from different moments are not parity."""
    objects, kwargs, update = e
    objects[changed]["observed_at"] = "2026-10-16T12:00:00Z"
    update(changed)
    with pytest.raises(r.R42Refused, match="ACCOUNT_LEDGER_TIMESTAMP_DRIFT"):
        r.audit(**kwargs)


def test_r42c_mismatched_captures_cannot_claim_any_release(e):
    objects, kwargs, update = e
    objects["ledger"]["observed_at"] = "2026-10-16T11:59:59Z"
    update("ledger")
    assert r.main([
        "--policy", str(kwargs["policy_path"]),
        "--policy-sha256", kwargs["policy_sha256"],
        "--market", str(kwargs["market_path"]),
        "--market-sha256", kwargs["market_sha256"],
        "--account", str(kwargs["account_path"]),
        "--account-sha256", kwargs["account_sha256"],
        "--ledger", str(kwargs["ledger_path"]),
        "--ledger-sha256", kwargs["ledger_sha256"],
        "--region", kwargs["region"],
        "--as-of-utc", kwargs["as_of_utc"],
        "--ack-synthetic-offline",
    ]) == 2
