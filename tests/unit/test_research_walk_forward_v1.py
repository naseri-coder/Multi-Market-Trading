"""Boundary, causality and no-false-edge tests for opt-in offline walk-forward."""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

from naseri_markets.research_walk_forward_v1 import (
    WalkForwardRefused,
    WalkForwardSettings,
    evaluate_walk_forward,
)

START = datetime(2026, 1, 1, tzinfo=UTC)
TRAIN_END = datetime(2026, 1, 10, tzinfo=UTC)
VALID_END = datetime(2026, 1, 20, tzinfo=UTC)
END = datetime(2026, 2, 1, tzinfo=UTC)


def item(name, day, net="1", *, close_hours=1, outcome="CLOSED_PAPER"):
    entry = START + timedelta(days=day - 1)
    return {
        "order_id": name,
        "entry_at": entry.isoformat(),
        "exit_at": (entry + timedelta(hours=close_hours)).isoformat()
        if close_hours is not None else None,
        "net_r": D(net) if outcome == "CLOSED_PAPER" else None,
        "outcome": outcome,
    }


def sample():
    # Jan 9 is embargoed from fold 1 but may be used after Jan 15.
    return [
        item("train_2", 2, "1"), item("train_4", 4, "-0.5"),
        item("embargo_9", 9, "-1"),
        item("valid_11", 11, "1.5"), item("valid_13", 13, "-1"),
        item("valid_16", 16, "0.5"), item("valid_18", 18, "2"),
        item("holdout_22", 22, "-1"), item("holdout_25", 25, "2"),
    ]


def run(rows=None, *, folds=2, embargo=86400, minimum=2, **kw):
    args = {
        "window_start": START,
        "training_end": TRAIN_END,
        "validation_end": VALID_END,
        "window_end": END,
        "settings": WalkForwardSettings(folds, embargo),
        "min_closed_per_segment": minimum,
    }
    args.update(kw)
    return evaluate_walk_forward(sample() if rows is None else rows, **args)


def test_expanding_time_purged_folds_and_reserved_holdout():
    report = run()
    assert report == run()
    assert report["mode"] == "OFFLINE_PAPER_OUTCOME_FOLD_AUDIT_ONLY"
    assert report["blockers"] == []
    assert report["full_study_population"] == 9
    assert report["initial_training_population"] == 3
    assert report["validation_population"] == 4
    assert report["holdout_population"] == 2
    assert report["pre_holdout_spill_count"] == 0
    f1, f2 = report["folds"]
    assert f1["test_start"] == TRAIN_END.isoformat()
    assert f1["test_end_exclusive"] == (TRAIN_END + timedelta(days=5)).isoformat()
    assert f1["train_label_cutoff_exclusive"] == (
        TRAIN_END - timedelta(days=1)
    ).isoformat()
    assert f1["embargo_entry_count"] == 1
    assert f1["training"]["eligible_closed"] == 2
    assert f1["validation"]["eligible_closed"] == 2
    assert f2["training"]["eligible_closed"] == 5
    assert f2["validation"]["eligible_closed"] == 2
    assert f2["test_end_exclusive"] == VALID_END.isoformat()
    assert report["final_holdout"]["eligible_closed"] == 2
    assert report["readiness"] == "DESCRIPTIVE_ONLY_NOT_PROFITABILITY_PROOF"
    assert not report["strategy_retraining_performed"]
    assert not report["prospective_holdout_verified"]
    assert not report["parameter_selection_performed"]
    assert report["audit_sha256"] == run()["audit_sha256"]


def test_holdout_changes_cannot_change_any_training_or_validation_fold():
    baseline = run()
    changed = sample()
    changed[-1]["net_r"] = D("900")
    updated = run(changed)
    assert baseline["folds"] == updated["folds"]
    assert baseline["final_holdout"] != updated["final_holdout"]
    assert baseline["audit_sha256"] != updated["audit_sha256"]


def test_holdout_not_available_for_folds_even_with_large_embargo():
    baseline = run(embargo=5 * 86400, minimum=1)
    assert all(f["test_end_exclusive"] <= VALID_END.isoformat()
               for f in baseline["folds"])
    assert baseline["final_holdout"]["population"] == 2


def test_cross_cutoff_training_label_is_excluded_and_blocked():
    rows = sample() + [item("late_train_label", 8, "12", close_hours=72)]
    r = run(rows)
    first = r["folds"][0]
    assert first["training"]["cross_cutoff_exit"] == 1
    assert first["training"]["excluded_from_closed_metrics"] == 1
    assert "TRAIN_LABEL_CROSSES_CUTOFF" in first["blockers"]
    assert "TRAIN_LABEL_CROSSES_CUTOFF" in r["blockers"]


def test_fold_validation_exit_crossing_test_end_is_not_a_valid_test_label():
    rows = sample()
    rows[3] = item("valid_11", 11, "40", close_hours=6 * 24)
    result = run(rows)
    assert result["folds"][0]["validation"]["cross_cutoff_exit"] == 1
    assert result["folds"][0]["validation"]["eligible_closed"] == 1
    assert "VALIDATION_LABEL_CROSSES_CUTOFF" in result["blockers"]


def test_pre_holdout_exit_overlap_is_not_hidden():
    rows = sample()
    rows[4] = item("valid_13", 13, "5", close_hours=10 * 24)
    r = run(rows)
    assert r["pre_holdout_spill_count"] == 1
    assert "PRE_HOLDOUT_LABEL_CROSSES_BOUNDARY" in r["blockers"]
    assert "VALIDATION_LABEL_CROSSES_CUTOFF" in r["blockers"]


def test_holdout_exit_beyond_window_blocks_readiness():
    rows = sample()
    rows[-1] = item("holdout_25", 25, "1", close_hours=15 * 24)
    r = run(rows)
    assert r["final_holdout"]["cross_cutoff_exit"] == 1
    assert "FINAL_HOLDOUT_LABEL_EXCEEDS_WINDOW" in r["blockers"]


def test_holdout_empty_cannot_pass_any_predeclared_minimum():
    rows = sample()[:-2]
    r = run(rows)
    assert r["holdout_population"] == 0
    assert r["final_holdout"]["mean_net_r_closed"] is None
    assert "INSUFFICIENT_FINAL_HOLDOUT_SAMPLE" in r["blockers"]


def test_fold_empty_cannot_silently_lower_sample_minimum():
    rows = [r for r in sample() if r["order_id"] != "valid_18"]
    r = run(rows)
    assert "INSUFFICIENT_FOLD_VALIDATION_SAMPLE" in r["folds"][-1]["blockers"]
    assert r["min_closed_per_segment"] == 2


def test_unfilled_and_incomplete_remain_in_population():
    rows = sample()
    rows[3] = item("valid_11", 11, outcome="UNFILLED", close_hours=None)
    rows[6] = item("valid_18", 18, outcome="INCOMPLETE", close_hours=None)
    r = run(rows)
    assert r["validation_population"] == 4
    assert r["folds"][0]["validation"]["unfilled"] == 1
    assert r["folds"][1]["validation"]["incomplete"] == 1
    assert "INCOMPLETE_FOLD_OUTCOMES" in r["blockers"]


def test_embargoed_entries_are_counted_not_hidden():
    r = run()
    assert r["folds"][0]["embargo_entry_count"] == 1
    assert r["folds"][0]["training"]["population"] == 2
    assert r["validation_population"] == 4


@pytest.mark.parametrize("folds,embargo", [
    (True, 0), (1, 0), (13, 0), ("2", 0),
    (2, True), (2, -1), (2, 604801), (2, 1.5),
])
def test_invalid_fold_parameters_fail_closed(folds, embargo):
    with pytest.raises(WalkForwardRefused):
        WalkForwardSettings(folds, embargo)


@pytest.mark.parametrize("minimum", [0, -1, True, 10001, "2"])
def test_invalid_minimum_is_never_relaxed(minimum):
    with pytest.raises(WalkForwardRefused, match="SAMPLE_MINIMUM"):
        run(minimum=minimum)


def test_embargo_wider_than_initial_training_window_refused():
    with pytest.raises(WalkForwardRefused, match="TRAINING_WINDOW"):
        run(embargo=604800, training_end=START + timedelta(days=2))


def test_microsecond_fold_splitting_preserves_half_open_boundaries():
    valid_end = TRAIN_END + timedelta(microseconds=13)
    result = run([], folds=3, embargo=0, minimum=1,
                 validation_end=valid_end, window_end=valid_end + timedelta(days=1))
    assert [x["test_start"] for x in result["folds"]] == [
        TRAIN_END.isoformat(),
        (TRAIN_END + timedelta(microseconds=4)).isoformat(),
        (TRAIN_END + timedelta(microseconds=8)).isoformat(),
    ]
    assert result["folds"][-1]["test_end_exclusive"] == valid_end.isoformat()


@pytest.mark.parametrize("corruption", [
    {"order_id": "train_2"},
    {"entry_at": "2026-01-02T00:00:00"},
    {"entry_at": "2026-01-02T00:00:00+02:00"},
    {"entry_at": "2025-12-31T23:00:00+00:00"},
    {"outcome": "LIVE"},
    {"net_r": D("NaN")},
    {"net_r": None},
    {"exit_at": "2026-01-01T00:00:00+00:00"},
])
def test_bad_or_duplicated_evidence_refused(corruption):
    rows = sample()
    rows[0] = {**rows[0], **corruption}
    if "order_id" in corruption:
        rows[0]["order_id"] = rows[1]["order_id"]
    with pytest.raises(WalkForwardRefused):
        run(rows)


def test_nonclosed_cannot_supply_fabricated_realized_r():
    rows = sample()
    rows[3]["outcome"] = "UNFILLED"
    with pytest.raises(WalkForwardRefused, match="NONCLOSED"):
        run(rows)


def test_no_order_ids_or_private_payloads_appear_in_report():
    rows = sample()
    rows[0]["order_id"] = "sensitive_opaque_id"
    report = run(rows)
    assert "sensitive_opaque_id" not in str(report)
    assert "holdout_22" not in str(report)


def test_no_input_mutation_and_chronology_independent_of_row_order():
    rows = sample()
    original = deepcopy(rows)
    normal = run(rows)
    reverse = run(list(reversed(rows)))
    assert rows == original
    assert normal == reverse
