"""R33 no-LIVE regression tests; all fixtures are synthetic operator claims."""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal as D

import pytest

from naseri_markets import mmt_r33_live_hard_deny_readiness_v1 as r33
from scripts import mmt_r33_manual_live_denial_review_v1 as cli

BASELINE_SHAS = (
    "03a878b7c7f0d5955427efb2f32e3f5611afc919",
    "6031385a463adb9f544dc9250c158b23fdd2a087",
    "19f93e500ef4bc6e1854bb1efd02adebfebb4c22",
    "9658949fa2bb8d22c6ca6012e9af1bc45e6b460c",
    "f857dc66d91bffee022715fa1a00f0f5ba662f3e",
)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def evidence(*, future=False, merged=False, affirmative=False):
    prs = tuple(
        r33.R33PRObservation(
            number=n, head_sha=sha, state="closed" if merged else "open",
            draft=not merged, merged=merged,
        )
        for n, sha in zip(range(321, 326), BASELINE_SHAS, strict=True)
    )
    flags = dict.fromkeys(r33._EVIDENCE_FLAG_FIELDS, affirmative)
    return r33.R33Evidence(
        prs=prs,
        review_time_utc=(
            datetime(2026, 11, 4, tzinfo=UTC) if future
            else datetime(2026, 10, 16, tzinfo=UTC)
        ),
        **flags,
    )


def envelope():
    return r33.R33ReferencePilotEnvelope(
        assumed_equity=D("10000"),
        per_trade_risk_fraction=D("0.0025"),
        max_daily_loss_fraction=D("0.005"),
        max_notional_fraction=D("0.10"),
        max_leverage=D("1"),
        max_concurrent_positions=1,
    )


def position(**kwargs):
    data = {
        "envelope": envelope(), "entry": D("100"), "stop": D("98"),
        "quantity": D("1"), "multiplier": D("1"),
        "roundtrip_fee_fraction": D("0.001"),
        "adverse_slippage_fraction": D("0.002"),
        "already_lost_today": D("0"), "current_open_positions": 0,
        "operator_ack": True,
    }
    data.update(kwargs)
    return r33.simulate_r33_reference_position(**data)


def test_actual_oct16_draft_chain_hard_denied():
    result = r33.review_r33_live_readiness(evidence(), operator_ack=True)
    assert result["decision"] == "LIVE_HARD_DENY"
    assert result["blocker_count"] >= 20
    for number in range(321, 326):
        assert f"PR_{number}_NOT_MERGED_AND_ACCEPTED" in result["blockers"]
    assert "R29_PROSPECTIVE_WINDOW_NOT_ELAPSED" in result["blockers"]
    for gate in (
        "R33_NO_LIVE_ORDER_ROUTE_IN_THIS_STAGE",
        "R33_NO_INDEPENDENT_LIVE_RELEASE_AUTHORITY_IMPLEMENTED",
        "VENUE_JURISDICTION_AND_API_PERMISSION_VERIFIED_UNVERIFIED",
        "LIVE_ACCOUNT_BALANCES_AND_POSITIONS_RECONCILED_UNVERIFIED",
    ):
        assert gate in result["blockers"]
    for name in (
        "can_route_order", "can_enable_live", "can_unhalt_order_switch",
        "can_send_telegram_signals", "can_change_production",
        "auto_retry_unknown", "paper_or_live_trade_executed",
    ):
        assert result[name] is False
    assert len(result["report_sha256"]) == 64


def test_even_fake_all_pass_future_is_never_live_authority():
    spoof = evidence(future=True, merged=True, affirmative=True)
    report = r33.review_r33_live_readiness(spoof, operator_ack=True)
    assert report["decision"] == "LIVE_HARD_DENY"
    assert report["blockers"] == [
        "R33_NO_INDEPENDENT_LIVE_RELEASE_AUTHORITY_IMPLEMENTED",
        "R33_NO_LIVE_ORDER_ROUTE_IN_THIS_STAGE",
    ]
    assert report["operator_assertions_independently_authenticated"] is False
    assert report["live_gateway_exists"] is False


@pytest.mark.parametrize("flag", [
    "r29_prospective_complete", "r30_fault_injection_passed",
    "full_test_and_security_suite_passed",
    "r32_independent_cold_restore_passed",
    "no_unresolved_orders", "manual_specific_live_permission_provided",
])
def test_each_missing_independent_gate_is_reported(flag):
    trusted_sim = evidence(future=True, merged=True, affirmative=True)
    updated = replace(trusted_sim, **{flag: False})
    result = r33.review_r33_live_readiness(updated, operator_ack=True)
    assert flag.upper() + "_UNVERIFIED" in result["blockers"]
    assert result["can_route_order"] is False


def test_pr_chain_must_be_exact_and_ordered():
    current = evidence()
    with pytest.raises(r33.R33ReadinessRefused, match="ORDERED_PR_INVENTORY"):
        replace(current, prs=current.prs[::-1])
    with pytest.raises(r33.R33ReadinessRefused, match="ORDERED_PR_INVENTORY"):
        replace(current, prs=current.prs[:-1])
    with pytest.raises(r33.R33ReadinessRefused, match="PR_OBSERVATION"):
        replace(current.prs[0], head_sha="untrusted")


def test_review_time_requires_utc_no_naive_or_non_utc():
    current = evidence()
    with pytest.raises(r33.R33ReadinessRefused, match="UTC_REVIEW"):
        replace(current, review_time_utc=datetime(2026, 10, 16))
    with pytest.raises(r33.R33ReadinessRefused, match="UTC_REVIEW"):
        replace(current, review_time_utc="2026-10-16")


def test_production_and_missing_ack_never_run_readiness(monkeypatch):
    with pytest.raises(r33.R33ReadinessRefused, match="EXPLICIT_NONPRODUCTION"):
        r33.review_r33_live_readiness(evidence())
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(r33.R33ReadinessRefused, match="EXPLICIT_NONPRODUCTION"):
        r33.review_r33_live_readiness(evidence(), operator_ack=True)


def test_r33_linear_research_position_is_not_an_order():
    item = position()
    assert item["mode"] == "HYPOTHETICAL_LINEAR_ONLY"
    assert item["modeled_notional"] == "100"
    assert item["modeled_stop_risk_including_friction"] == "2.3"
    assert item["modeled_maximum_leverage_margin_proxy"] == "100"
    assert item["live_trading_approved"] is False
    assert item["broker_order_sent"] is False
    assert item["actual_funding_liquidation_and_fill_proven"] is False


def test_r33_reference_caps_reject_leverage_and_position_count():
    for kwargs in (
        {"max_leverage": D("1.01")},
        {"max_concurrent_positions": 2},
        {"per_trade_risk_fraction": D(".003")},
        {"max_daily_loss_fraction": D(".006")},
        {"max_notional_fraction": D(".11")},
    ):
        with pytest.raises(r33.R33ReadinessRefused, match="REFERENCE_CAP_EXCEEDED"):
            replace(envelope(), **kwargs)


def test_r33_reference_notional_and_risk_excesses_refuse():
    with pytest.raises(r33.R33ReadinessRefused, match="REFERENCE_RISK_CAP"):
        position(quantity=D("20"))
    with pytest.raises(r33.R33ReadinessRefused, match="REFERENCE_NOTIONAL_CAP"):
        position(quantity=D("12"), stop=D("99.9"),
                 roundtrip_fee_fraction=D("0"),
                 adverse_slippage_fraction=D("0"))


def test_r33_reference_daily_loss_and_unknown_positions_refuse():
    with pytest.raises(r33.R33ReadinessRefused, match="DAILY_STOP"):
        position(already_lost_today=D("50"))
    with pytest.raises(r33.R33ReadinessRefused, match="REFERENCE_RISK_CAP"):
        position(already_lost_today=D("49"))
    with pytest.raises(r33.R33ReadinessRefused, match="CONCURRENT_POSITION"):
        position(current_open_positions=1)
    with pytest.raises(r33.R33ReadinessRefused, match="INVALID_REFERENCE"):
        position(stop=D("100"))


def test_strict_cli_json_requires_full_schema_and_never_grants():
    data = evidence()
    payload = {
        "prs": [
            dict(number=p.number, head_sha=p.head_sha, state=p.state,
                 draft=p.draft, merged=p.merged) for p in data.prs
        ],
        "review_time_utc": "2026-10-16T12:00:00Z",
        "flags": {
            name: getattr(data, name) for name in r33._EVIDENCE_FLAG_FIELDS
        },
    }
    claimed = cli.decode_offline_operator_claims(
        json.dumps(payload).encode("ascii"),
    )
    report = r33.review_r33_live_readiness(claimed, operator_ack=True)
    assert report["decision"] == "LIVE_HARD_DENY"
    assert claimed.prs[0].number == 321


def test_cli_rejects_duplicate_keys_extra_fields_and_bool_int_swap():
    minimal = b'{"prs":[],"prs":[],"flags":{},"review_time_utc":"2026-10-16T12:00:00Z"}'
    with pytest.raises(r33.R33ReadinessRefused, match="DUPLICATE"):
        cli.decode_offline_operator_claims(minimal)
    with pytest.raises(r33.R33ReadinessRefused, match="EXACT_SCHEMA"):
        cli.decode_offline_operator_claims(b'{"prs":[],"flags":{},"extra":1}')
    raw = evidence()
    with pytest.raises(r33.R33ReadinessRefused, match="TYPED_EVIDENCE_FLAGS"):
        replace(raw, no_unresolved_orders=1)


def test_cli_private_source_bytes_only(tmp_path):
    folder = tmp_path / "private"
    folder.mkdir(mode=0o700)
    file = folder / "claims.json"
    file.write_text("{}")
    file.chmod(0o600)
    assert cli._read_private(file) == b"{}"
    file.chmod(0o644)
    with pytest.raises(r33.R33ReadinessRefused, match="OWNER_PRIVATE"):
        cli._read_private(file)
    file.chmod(0o600)
    linked = folder / "symlink"
    linked.symlink_to(file)
    with pytest.raises(r33.R33ReadinessRefused, match="PRIVATE_ABSOLUTE"):
        cli._read_private(linked)


def test_no_live_trade_api_is_exported():
    assert r33.LIVE_ORDERS_IMPLEMENTED is False
    for name in ("create_live_order", "send_order", "submit_order",
                 "connect_exchange", "retry_unknown"):
        assert not hasattr(r33, name)


def test_r33_public_baseline_claims_match_real_observed_sha_and_hard_deny():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2]
              / "docs/evidence/MMT_R33_OPERATOR_CLAIMS_BASELINE_20261016.json")
    read = cli.decode_offline_operator_claims(source.read_bytes())
    assert tuple(p.head_sha for p in read.prs) == BASELINE_SHAS
    assert all(p.draft and not p.merged and p.state == "open"
               for p in read.prs)
    assert not any(getattr(read, key) for key in r33._EVIDENCE_FLAG_FIELDS)
    result = r33.review_r33_live_readiness(read, operator_ack=True)
    assert result["decision"] == "LIVE_HARD_DENY"
    assert result["can_route_order"] is False


def test_cli_private_path_requires_real_path_and_owned_0700_parent(tmp_path):
    from pathlib import Path

    folder = tmp_path / "private"
    folder.mkdir(mode=0o700)
    file = folder / "claims.json"
    file.write_bytes(b"{}")
    file.chmod(0o600)
    assert isinstance(file, Path)
    assert type(file) is not Path  # Python POSIX returns PosixPath.
    assert cli._read_private(file) == b"{}"
    with pytest.raises(r33.R33ReadinessRefused, match="PRIVATE_ABSOLUTE"):
        cli._read_private(str(file))
    public = tmp_path / "public"
    public.mkdir(mode=0o755)
    public_file = public / "claims.json"
    public_file.write_bytes(b"{}")
    public_file.chmod(0o600)
    with pytest.raises(r33.R33ReadinessRefused, match="PRIVATE_PARENT"):
        cli._read_private(public_file)
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(folder, target_is_directory=True)
    with pytest.raises(r33.R33ReadinessRefused, match="PRIVATE_ABSOLUTE"):
        cli._read_private(linked_parent / file.name)


def test_cli_private_read_is_anchored_to_checked_directory_fd(
    monkeypatch, tmp_path,
):
    folder = tmp_path / "private"
    folder.mkdir(mode=0o700)
    expected = folder / "claims.json"
    expected.write_bytes(b'{"safe":true}')
    expected.chmod(0o600)
    public = tmp_path / "public"
    public.mkdir(mode=0o755)
    (public / "claims.json").write_bytes(b'{"unsafe":true}')
    moved = tmp_path / "private-original"
    real_open = cli.os.open
    swapped = []

    def redirect_path_after_dir_open(path, flags, *args, **kwargs):
        if path == folder and flags & cli.os.O_DIRECTORY and not swapped:
            fd = real_open(path, flags, *args, **kwargs)
            folder.rename(moved)
            folder.symlink_to(public, target_is_directory=True)
            swapped.append(True)
            return fd
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(cli.os, "open", redirect_path_after_dir_open)
    assert cli._read_private(expected) == b'{"safe":true}'
    assert swapped
    assert (moved / "claims.json").read_bytes() == b'{"safe":true}'
