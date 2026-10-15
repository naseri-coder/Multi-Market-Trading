"""Stage 14: independent fixed stress grid and strictly unlinked PBO/DSR matrix."""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

from naseri_markets.core_api_v1 import content_digest
from naseri_markets.executable_walk_forward_stage13_v1 import (
    execute_frozen_walk_forward,
)
from naseri_markets.research_robustness_stage14_v1 import (
    Stage14Refused, run_stage14_robustness,
)
from test_executable_walk_forward_stage13_v1 import fixture as stage13_fixture

_START = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def _json(obj: dict) -> bytes:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()


def external_trials():
    names = ["alpha", "beta", "delta", "gamma"]
    rows = []
    for i in range(64):
        values = {
            "alpha": ((i*7+3) % 19 - 8)/1000,
            "beta": ((i*11+5) % 23 - 11)/1000,
            "delta": ((i*13+8) % 29 - 14)/1000,
            "gamma": ((i*17+2) % 31 - 15)/1000,
        }
        rows.append({
            "period_start_utc": (_START + timedelta(hours=i)).isoformat(),
            "period_end_utc": (_START + timedelta(hours=i+1)).isoformat(),
            "net_return_fraction": {
                key: format(values[key], ".3f") for key in names
            },
        })
    return {
        "schema_version": 1, "study_id": "independent_external_matrix",
        "candidate_ids": names, "selected_candidate_id": "alpha",
        "declared_total_trials": 4, "trial_inventory_complete": True,
        "cscv_blocks": 4,
        "reserved_holdout_start_utc": (_START+timedelta(days=4)).isoformat(),
        "rows": rows,
    }


def evidence(tmp_path, *, no_signal=False, fee="2", slip="3", external=False):
    path, spec, receipt, digest, plan = stage13_fixture.__wrapped__(
        tmp_path, fee=fee, slip=slip, no_signal=no_signal,
    )
    base = execute_frozen_walk_forward(
        path, spec, receipt_bytes=receipt,
        trusted_receipt_sha256=digest, plan=plan, operator_ack=True,
    )
    matrix = _json(external_trials()) if external else None
    protocol = {
        "schema_version": 1,
        "experiment_id": "st14_one_fixture_cost_robustness",
        "core_id": base["core_id"], "core_version": base["core_version"],
        "dataset_sha256": spec.expected_sha256,
        "execution_plan_sha256": content_digest(plan),
        "baseline_execution_evidence_sha256": base["evidence_sha256"],
        "claimed_preoutcome_freeze": True,
        "stress_case_ids": [
            "baseline", "fee_2x", "slippage_2x", "joint_2x",
        ],
        "external_candidate_ids": (
            external_trials()["candidate_ids"] if external else []
        ),
        "selected_external_candidate_id": "alpha" if external else None,
        "external_matrix_sha256": (
            hashlib.sha256(matrix).hexdigest() if matrix is not None else None
        ),
        "claimed_complete_external_trial_inventory": external,
    }
    return path, spec, receipt, digest, plan, protocol, matrix


def calculate(sample, *, protocol=None, raw=None, matrix=None, pin=None,
              operator_ack=True):
    path, spec, receipt, digest, plan, original, original_matrix = sample
    data = _json(original if protocol is None else protocol) if raw is None else raw
    return run_stage14_robustness(
        path, spec, receipt_bytes=receipt, trusted_receipt_sha256=digest,
        plan=plan, protocol_bytes=data,
        trusted_protocol_sha256=(
            hashlib.sha256(data).hexdigest() if pin is None else pin
        ),
        external_matrix_bytes=original_matrix if matrix is None else matrix,
        operator_ack=operator_ack,
    )


def test_complete_stress_inventory_is_executed_and_repeatable(tmp_path):
    sample = evidence(tmp_path)
    before = sample[0].read_bytes()
    result = calculate(sample)
    assert result == calculate(sample)
    assert sample[0].read_bytes() == before
    assert result["case_count"] == 4
    assert result["scenario_inventory"] == [
        "baseline", "fee_2x", "slippage_2x", "joint_2x",
    ]
    assert [case["case_id"] for case in result["cases"]] == result["scenario_inventory"]
    assert result["actual_executable_core_trial_count"] == 1
    assert result["verdict"] == "OFFLINE_COST_STRESS_DESCRIPTIVE_ONLY"
    assert result["blockers"] == []
    assert len(result["report_sha256"]) == 64
    assert result["cases"][0]["execution_evidence_sha256"] == (
        sample[5]["baseline_execution_evidence_sha256"]
    )
    assert all(len(c["execution_evidence_sha256"]) == 64 for c in result["cases"])
    assert all(c["validation_closed"] == 2 for c in result["cases"])
    assert all(c["final_holdout"]["closed"] == 2 for c in result["cases"])
    assert result["external_matrix_overfit_diagnostics"] is None
    for key in (
        "stage13_single_core_pbo_dsr_applicable",
        "pbo_dsr_computed_from_stage13_trades",
        "multiple_parameter_variants_executed",
        "external_stats_attributable_to_stage13_core",
        "claimed_protocol_freeze_independently_attested",
        "trial_inventory_independently_attested",
        "blind_final_holdout_preserved",
        "historical_source_authenticated", "real_strategy_backtested",
        "profitability_proven", "broker_orders_authorized",
        "telegram_sent", "live_trading_authorized",
    ):
        assert result[key] is False
    assert result["holdout_exposed_during_repeated_stress_runs"] is True


def test_fee_and_slippage_2x_cases_use_proper_economics(tmp_path):
    result = calculate(evidence(tmp_path, fee="2", slip="3"))
    base, fee, slippage, joint = result["cases"]
    assert [c["fee_bps_per_side"] for c in result["cases"]] == [
        "2", "4", "2", "4",
    ]
    assert [c["slippage_bps_per_side"] for c in result["cases"]] == [
        "3", "3", "6", "6",
    ]
    for variant in (fee, slippage, joint):
        assert D(variant["validation_net_pnl"]) < D(base["validation_net_pnl"])
        assert variant["validation_closed"] == base["validation_closed"] == 2


def test_no_trade_blocks_every_scenario_without_fabricating_sharpe(tmp_path):
    result = calculate(evidence(tmp_path, no_signal=True))
    assert result["verdict"] == "OFFLINE_COST_STRESS_REVIEW_BLOCKED"
    assert len(result["blockers"]) == 4
    assert all(case["validation_closed"] == 0 for case in result["cases"])
    assert all(case["validation_fold_test_receipts"][0]["mean_net_r"] is None
               for case in result["cases"])


def test_zero_cost_scenarios_remain_equal_but_record_all_trials(tmp_path):
    result = calculate(evidence(tmp_path, fee="0", slip="0"))
    assert result["case_count"] == 4
    assert len({c["validation_net_pnl"] for c in result["cases"]}) == 1
    assert result["blockers"] == []


def test_external_pbo_and_dsr_are_separate_full_matrix_diagnostics(tmp_path):
    result = calculate(evidence(tmp_path, external=True))
    ext = result["external_matrix_overfit_diagnostics"]
    assert ext["origin"] == "SEPARATE_OPERATOR_DECLARED_MULTICANDIDATE_MATRIX"
    assert ext["stage13_fixture_attribution_allowed"] is False
    assert ext["ready_for_profit_claim"] is False
    assert ext["diagnostics"]["candidate_count"] == 4
    assert ext["diagnostics"]["period_count"] == 64
    assert ext["diagnostics"]["pbo"]["split_count"] == 6
    assert 0 <= ext["diagnostics"]["pbo"]["pbo_fraction"] <= 1
    assert 0 <= ext["diagnostics"]["dsr"]["dsr_probability"] <= 1
    assert ext["diagnostics"]["holdout_rows_loaded"] == 0
    assert ext["diagnostics"]["readiness"] == "DESCRIPTIVE_ONLY_NOT_PROFITABILITY_PROOF"
    assert result["external_stats_attributable_to_stage13_core"] is False
    assert result["stage13_single_core_pbo_dsr_applicable"] is False


@pytest.mark.parametrize("mutation,code", [
    ({"claimed_preoutcome_freeze": False}, "INCOMPLETE_FROZEN"),
    ({"experiment_id": "bad id"}, "INCOMPLETE_FROZEN"),
    ({"stress_case_ids": ["baseline", "joint_2x"]}, "STRESS_INVENTORY"),
    ({"stress_case_ids": ["joint_2x", "baseline", "fee_2x", "slippage_2x"]},
     "STRESS_INVENTORY"),
    ({"dataset_sha256": "a"*64}, "BASELINE_CORE_DATA_PLAN_SCOPE_DRIFT"),
    ({"core_id": "untrusted.core"}, "BASELINE_CORE_DATA_PLAN_SCOPE_DRIFT"),
    ({"execution_plan_sha256": "b"*64}, "BASELINE_CORE_DATA_PLAN_SCOPE_DRIFT"),
    ({"baseline_execution_evidence_sha256": "c"*64},
     "FROZEN_BASELINE_EXECUTION_DIGEST_MISMATCH"),
    ({"external_candidate_ids": ["a", "b", "c"],
      "selected_external_candidate_id": None}, "EXTERNAL_TRIAL"),
    ({"external_candidate_ids": [["danger"]],
      "selected_external_candidate_id": None}, "EXTERNAL_TRIAL"),
])
def test_frozen_protocol_scope_refuses_mutation(tmp_path, mutation, code):
    sample = evidence(tmp_path)
    obj = {**sample[5], **mutation}
    with pytest.raises(Stage14Refused, match=code):
        calculate(sample, protocol=obj)


def test_duplicate_fields_float_and_nan_are_refused(tmp_path):
    sample = evidence(tmp_path)
    payload = _json(sample[5])
    corruptions = (
        payload.replace(b'"schema_version":1',
                        b'"schema_version":1,"schema_version":1'),
        payload.replace(b'"schema_version":1', b'"schema_version":1.0'),
        payload.replace(b'"schema_version":1', b'"schema_version":NaN'),
        payload.replace(b'"schema_version":1', b'"schema_version":1,"secret":"leak"'),
    )
    for corrupted in corruptions:
        with pytest.raises(Stage14Refused):
            calculate(sample, raw=corrupted)
    with pytest.raises(Stage14Refused, match="PROTOCOL_DIGEST_MISMATCH"):
        calculate(sample, pin="f"*64)


def test_complete_external_inventory_is_not_optional_when_matrix_supplied(tmp_path):
    sample = evidence(tmp_path)
    with pytest.raises(Stage14Refused, match="EXTERNAL_TRIAL_MATRIX"):
        calculate(sample, matrix=b"{}")
    with pytest.raises(Stage14Refused, match="EXTERNAL_TRIAL_MATRIX"):
        calculate(evidence(tmp_path, external=True), matrix=False)


def test_unregistered_trial_or_tampered_matrix_refused(tmp_path):
    sample = evidence(tmp_path, external=True)
    matrix = json.loads(sample[6])
    matrix["candidate_ids"] = ["alpha", "beta", "delta", "epsilon"]
    # This is an authentic digest of an INVALID edited matrix; it must not
    # bypass the separately pinned, predeclared inventory.
    invalid = _json(matrix)
    protocol = {**sample[5], "external_matrix_sha256": hashlib.sha256(invalid).hexdigest()}
    with pytest.raises(Exception, match="TRIAL|MATRIX|CANDIDATE|RESEARCH"):
        calculate(sample, protocol=protocol, matrix=invalid)
    with pytest.raises(Stage14Refused, match="EXTERNAL_MATRIX_PIN_MISMATCH"):
        calculate(sample, matrix=sample[6]+b" ")


def test_plan_and_data_pin_changes_refuse_even_with_higher_profit(tmp_path):
    sample = evidence(tmp_path)
    path = sample[0]
    path.write_bytes(path.read_bytes()+b" ")
    with pytest.raises(ValueError, match="HASH|SOURCE"):
        calculate(sample)


def test_limits_prevent_uncovered_2x_fee_or_slip_models(tmp_path):
    sample = evidence(tmp_path, fee="60")
    with pytest.raises(Stage14Refused, match="BASIS_POINT_CAP"):
        calculate(sample)
    sample = evidence(tmp_path, slip="80")
    with pytest.raises(Stage14Refused, match="BASIS_POINT_CAP"):
        calculate(sample)


def test_production_flags_and_operator_optin_are_mandatory(tmp_path, monkeypatch):
    sample = evidence(tmp_path)
    with pytest.raises(Stage14Refused, match="NONPRODUCTION"):
        calculate(sample, operator_ack=False)
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(Stage14Refused, match="NONPRODUCTION"):
        calculate(sample)
    monkeypatch.delenv("MMT_PRODUCTION")
    monkeypatch.delenv("MMT_NONPRODUCTION")
    with pytest.raises(Stage14Refused, match="NONPRODUCTION"):
        calculate(sample)


def test_external_matrix_scope_drift_refused_even_when_valid_matrix(tmp_path):
    sample = evidence(tmp_path, external=True)
    protocol = {**sample[5], "selected_external_candidate_id": "beta"}
    with pytest.raises(Stage14Refused, match="EXTERNAL_MATRIX_SCOPE_DRIFT"):
        calculate(sample, protocol=protocol)
