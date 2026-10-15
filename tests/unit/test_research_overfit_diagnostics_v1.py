"""Independent synthetic-matrix and negative research gates; never use live data."""
from __future__ import annotations

import itertools
import json
import math
import statistics
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from statistics import NormalDist

import pytest

from naseri_markets.research_overfit_diagnostics_v1 import (
    OverfitEvidenceRefused,
    analyze_overfit_fixture,
)

START = datetime(2026, 1, 1, tzinfo=UTC)
IDS = ["alpha", "beta", "delta", "gamma"]


def fixture():
    rows = []
    for i in range(64):
        # Synchronized, synthetic hourly *net portfolio return fractions*.
        values = {
            "alpha": ((i * 7 + 3) % 19 - 8) / 1000,
            "beta": ((i * 11 + 5) % 23 - 11) / 1000,
            "delta": ((i * 13 + 8) % 29 - 14) / 1000,
            "gamma": ((i * 17 + 2) % 31 - 15) / 1000,
        }
        rows.append({
            "period_start_utc": (START + timedelta(hours=i)).isoformat(),
            "period_end_utc": (START + timedelta(hours=i+1)).isoformat(),
            "net_return_fraction": {
                key: format(values[key], ".3f") for key in IDS
            },
        })
    return {
        "schema_version": 1,
        "study_id": "synthetic_diagnostic_01",
        "candidate_ids": IDS.copy(),
        "selected_candidate_id": "alpha",
        "declared_total_trials": 4,
        "trial_inventory_complete": True,
        "cscv_blocks": 4,
        "reserved_holdout_start_utc": (START + timedelta(days=4)).isoformat(),
        "rows": rows,
    }


def wire(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def inspect(obj=None):
    return analyze_overfit_fixture(wire(fixture() if obj is None else obj))


def test_exact_cscv_combinatorics_and_nonproduction_state():
    out = inspect()
    assert out == inspect()
    assert out["pbo"]["split_count"] == math.comb(4, 2)
    assert out["pbo"]["block_size"] == 16
    assert out["candidate_count"] == 4
    assert out["period_count"] == 64
    assert out["holdout_rows_loaded"] == 0
    assert out["readiness"] == "DESCRIPTIVE_ONLY_NOT_PROFITABILITY_PROOF"
    assert not out["historical_source_authenticated"]
    assert not out["selection_pre_registered_verified"]
    assert not out["serial_correlation_adjusted"]
    assert not out["trading_authorized"]
    assert not out["strategy_retraining_performed"]
    assert 0 <= out["pbo"]["pbo_fraction"] <= 1
    assert 0 <= out["dsr"]["dsr_probability"] <= 1


def test_pbo_split_count_is_exhaustive_and_not_random():
    obj = fixture()
    obj["cscv_blocks"] = 8
    out = inspect(obj)
    assert out["pbo"]["split_count"] == math.comb(8, 4)
    assert out["pbo"]["block_size"] == 8
    assert out["report_sha256"] == inspect(obj)["report_sha256"]


def test_independent_dsr_probability_reference_uses_per_period_units():
    obj = fixture()
    report = inspect(obj)["dsr"]
    samples = {
        cid: [float(r["net_return_fraction"][cid]) for r in obj["rows"]]
        for cid in IDS
    }
    sharpe = {
        cid: statistics.mean(row) / statistics.stdev(row)
        for cid, row in samples.items()
    }
    spread = statistics.stdev(sharpe.values())
    chosen = samples["alpha"]
    mean = statistics.mean(chosen)
    centered = [x - mean for x in chosen]
    m2 = statistics.mean(x**2 for x in centered)
    skew = statistics.mean(x**3 for x in centered) / m2**1.5
    kurt = statistics.mean(x**4 for x in centered) / m2**2
    gamma = 0.5772156649015329
    normal = NormalDist()
    expected_null = spread * (
        (1 - gamma) * normal.inv_cdf(1 - 1/4)
        + gamma * normal.inv_cdf(1 - 1/(4*math.e))
    )
    expected_z = (
        (sharpe["alpha"] - expected_null) * math.sqrt(len(chosen) - 1)
        / math.sqrt(1 - skew * sharpe["alpha"]
                    + ((kurt - 1) / 4) * sharpe["alpha"]**2)
    )
    assert math.isclose(report["observed_sharpe_per_period"], sharpe["alpha"], abs_tol=1e-12)
    assert math.isclose(report["cross_trial_sharpe_std"], spread, abs_tol=1e-12)
    assert math.isclose(report["selected_skewness"], skew, abs_tol=1e-12)
    assert math.isclose(report["selected_raw_kurtosis"], kurt, abs_tol=1e-12)
    assert math.isclose(report["expected_maximum_null_sharpe"], expected_null, abs_tol=1e-12)
    assert math.isclose(report["dsr_probability"], normal.cdf(expected_z), abs_tol=1e-12)


def test_cscv_pbo_reference_count_agrees_with_oos_rank_of_insample_winner():
    obj = fixture()
    results = {
        cid: [float(row["net_return_fraction"][cid]) for row in obj["rows"]]
        for cid in IDS
    }
    negatives = 0
    for blocks in itertools.combinations(range(4), 2):
        a = [i for b in blocks for i in range(b*16, (b+1)*16)]
        b = [i for k in range(4) if k not in blocks for i in range(k*16, (k+1)*16)]
        rank_is = {
            c: statistics.mean(results[c][i] for i in a)
            / statistics.stdev(results[c][i] for i in a)
            for c in IDS
        }
        top = max(rank_is, key=rank_is.get)
        rank_os = {
            c: statistics.mean(results[c][i] for i in b)
            / statistics.stdev(results[c][i] for i in b)
            for c in IDS
        }
        ordered = sorted(rank_os, key=rank_os.get)
        position = ordered.index(top) + 1
        rel = position / (len(IDS) + 1)
        negatives += rel <= 0.5
    assert inspect(obj)["pbo"]["negative_or_zero_logit_count"] == negatives
    assert inspect(obj)["pbo"]["pbo_fraction"] == negatives/6


def test_changing_nonholdout_returns_changes_digest_and_diagnostics():
    obj = fixture()
    before = inspect(obj)
    obj["rows"][7]["net_return_fraction"]["alpha"] = "-0.045"
    after = inspect(obj)
    assert before["matrix_sha256"] != after["matrix_sha256"]
    assert before["report_sha256"] != after["report_sha256"]
    assert before["dsr"]["observed_sharpe_per_period"] != (
        after["dsr"]["observed_sharpe_per_period"]
    )


def test_no_mutation_and_stable_order_in_json_properties():
    obj = fixture()
    before = deepcopy(obj)
    inspect(obj)
    assert obj == before
    out = inspect(obj)
    assert out["matrix_sha256"] == inspect(json.loads(wire(obj)))["matrix_sha256"]


@pytest.mark.parametrize("change", [
    {"declared_total_trials": 5},
    {"declared_total_trials": 3},
    {"declared_total_trials": True},
    {"trial_inventory_complete": False},
    {"trial_inventory_complete": 1},
    {"selected_candidate_id": "unknown"},
    {"candidate_ids": list(reversed(IDS))},
    {"candidate_ids": ["alpha", "beta", "beta", "gamma"]},
    {"candidate_ids": ["alpha", "beta"]},
    {"cscv_blocks": 3},
    {"cscv_blocks": 5},
    {"cscv_blocks": True},
    {"cscv_blocks": 14},
    {"schema_version": True},
    {"schema_version": 2},
])
def test_malformed_or_incomplete_trial_inventory_is_refused(change):
    obj = fixture()
    obj.update(change)
    with pytest.raises(OverfitEvidenceRefused):
        inspect(obj)


def test_trial_history_cannot_be_silently_filtered_to_winners():
    obj = fixture()
    obj["candidate_ids"] = IDS[:3]
    obj["declared_total_trials"] = 3
    with pytest.raises(OverfitEvidenceRefused, match="NONEXHAUSTIVE"):
        inspect(obj)


@pytest.mark.parametrize("key,change", [
    ("period_end_utc", (START + timedelta(days=6)).isoformat()),
    ("period_start_utc", "2026-01-01T00:00:00"),
    ("period_start_utc", "2026-01-01T00:00:00+02:00"),
    ("period_end_utc", "2025-12-31T23:00:00+00:00"),
])
def test_noncausal_or_holdout_crossing_rows_are_refused(key, change):
    obj = fixture()
    obj["rows"][0][key] = change
    with pytest.raises(OverfitEvidenceRefused):
        inspect(obj)


def test_interval_gap_and_overlap_are_refused_not_imputed():
    for hours in (0.5, 1.5):
        obj = fixture()
        obj["rows"][4]["period_start_utc"] = (
            START + timedelta(hours=3 + hours)
        ).isoformat()
        with pytest.raises(OverfitEvidenceRefused):
            inspect(obj)


def test_unequal_bin_duration_refused():
    obj = fixture()
    obj["rows"][0]["period_end_utc"] = (START + timedelta(minutes=30)).isoformat()
    with pytest.raises(OverfitEvidenceRefused):
        inspect(obj)


@pytest.mark.parametrize("change", [
    "NaN", "Infinity", "-Infinity", "1e-3", "0.0000000000001",
    ".01", "01.0", True, None, 0.1, {}, "999999999999999",
])
def test_noncanonical_or_unbounded_return_evidence_refused(change):
    obj = fixture()
    obj["rows"][0]["net_return_fraction"]["beta"] = change
    with pytest.raises(OverfitEvidenceRefused):
        inspect(obj)


def test_row_with_omitted_or_extra_trial_cannot_be_used():
    for mode in ("remove", "add"):
        obj = fixture()
        r = obj["rows"][4]["net_return_fraction"]
        if mode == "remove":
            del r["delta"]
        else:
            r["sneaky"] = "100"
        with pytest.raises(OverfitEvidenceRefused, match="NONEXHAUSTIVE"):
            inspect(obj)


def test_rows_are_never_cherry_picked_to_complete_partition():
    obj = fixture()
    obj["rows"].pop()
    with pytest.raises(OverfitEvidenceRefused, match="UNBALANCED"):
        inspect(obj)


def test_zero_variance_not_masked_as_sharpe_zero():
    obj = fixture()
    for row in obj["rows"]:
        row["net_return_fraction"]["beta"] = "0.000"
    with pytest.raises(OverfitEvidenceRefused, match="VARIANCE"):
        inspect(obj)


def test_duplicated_json_field_refused_without_disclosing_values():
    raw = wire(fixture())
    raw = raw.replace(b'"schema_version":1', b'"schema_version":1,"schema_version":1')
    with pytest.raises(OverfitEvidenceRefused, match="DUPLICATE_JSON"):
        analyze_overfit_fixture(raw)


@pytest.mark.parametrize("raw", [b"", b"{}", b"[1,2]", b"NaN", b'{"foo":NaN}', b"\xff"])
def test_bad_json_refused(raw):
    with pytest.raises(OverfitEvidenceRefused):
        analyze_overfit_fixture(raw)


def test_oversized_payload_fails_pre_parse():
    with pytest.raises(OverfitEvidenceRefused, match="SIZE_BOUND"):
        analyze_overfit_fixture(b"x" * 2_000_001)


def test_private_extra_information_cannot_enter_diagnostic_output():
    obj = fixture()
    token = "TOP_SECRET_NEVER_EXPOSE"
    obj["rows"][0]["api_key"] = token
    with pytest.raises(OverfitEvidenceRefused) as error:
        inspect(obj)
    assert token not in str(error.value)


def test_explicit_local_cli_gates_and_no_output_side_effects(tmp_path, capsys):
    from scripts.mmt_overfit_diagnostics_v1 import main

    matrix = tmp_path / "paper.json"
    matrix.write_bytes(wire(fixture()))
    original = matrix.read_bytes()
    assert main(["--matrix", str(matrix)]) == 2
    assert "ACK_REQUIRED" in capsys.readouterr().err
    assert main(["--matrix", str(matrix), "--ack-research-only"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["candidate_count"] == 4
    assert matrix.read_bytes() == original
    assert sorted(p.name for p in tmp_path.iterdir()) == ["paper.json"]
    assert main(["--matrix", str(tmp_path / "not-here"), "--ack-research-only"]) == 2
    assert "FAIL_CLOSED" in capsys.readouterr().err


def test_local_cli_refuses_symlink_without_following(tmp_path, capsys):
    from scripts.mmt_overfit_diagnostics_v1 import main

    target = tmp_path / "sample.json"
    target.write_bytes(wire(fixture()))
    link = tmp_path / "alias.json"
    link.symlink_to(target)
    assert main(["--matrix", str(link), "--ack-research-only"]) == 2
    assert "FAIL_CLOSED" in capsys.readouterr().err
