"""R29 safety tests use FAKE source custody/worker, never claim venue OOS."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from naseri_markets import brooks_future_shadow_paper_mmt_r29_v1 as r29
from naseri_markets.brooks_replay import (
    canonical_snapshot_identity, parse_candle_replay,
)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def candles(start: int, n: int) -> bytes:
    content = io.StringIO(newline="")
    writer = csv.writer(content, lineterminator="\n")
    writer.writerow(r29.HEADER)
    for k in range(start, start + n):
        opened = r29.FIRST_OPEN + timedelta(minutes=15 * k)
        closed = opened + r29.BAR
        writer.writerow([
            opened.strftime("%Y-%m-%dT%H:%M:%SZ"),
            closed.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "100", "105", "99", "102", "10",
        ])
    return content.getvalue().encode("ascii")


def staged(tmp_path, monkeypatch, sizes=(60,)):
    witness = tmp_path / "witness"
    witness.mkdir()
    folder = tmp_path / "source"
    folder.mkdir()
    history = []
    for i, n in enumerate(sizes):
        path = folder / str(i)
        path.mkdir()
        (path / "canonical-reviewed-closed-candles.csv").write_bytes(
            candles(sum(sizes[:i]), n),
        )
        history.append(path)
    state = SimpleNamespace(
        next_open_utc=r29.FIRST_OPEN + r29.BAR * sum(sizes),
        accepted_batches=len(sizes),
        last_outer_receipt_sha256="b" * 64,
        previous_batch_digest="c" * 64,
    )
    monkeypatch.setattr(
        r29, "_read_original_evidence",
        lambda directory: {"claimed-original-witness": b"TEST"},
    )
    monkeypatch.setattr(
        r29, "stage24_replay_all_previous_batches",
        lambda **kwargs: state,
    )
    monkeypatch.setattr(
        r29, "verify_legacy_source", lambda path: "a" * 64,
    )
    seen = []

    def fake_worker(source, payload, timeout):
        raw, _, normalized = parse_candle_replay(payload)
        identity, digest = canonical_snapshot_identity(raw, normalized)
        seen.append(raw)
        return {
            "snapshot_id": identity, "snapshot_hash": digest,
            "engine_version": "brooks-trilogy-full-core-v5-context-structural",
            "rule_set_version": "test_r29",
            "configuration_version": "offline_test",
            "decision": "NO_SIGNAL", "entry": None, "stop": None,
            "targets": [], "setup_type": None, "rule_ids": [],
        }

    monkeypatch.setattr(r29, "_worker", fake_worker)
    params = {
        "witness_directory": witness,
        "previous_directories": tuple(history),
        "frozen_source": tmp_path / "frozen-worker",
        "operator_ack": True,
    }
    return params, state, seen


def test_r29_waiting_before_60_real_forward_bars_without_worker(
    tmp_path, monkeypatch,
):
    args, _, calls = staged(tmp_path, monkeypatch, sizes=(59,))
    report, raw = r29.review_r29_one_closed_bar_shadow(
        **args, decision_bar_index=60,
    )
    assert raw is None and report["admitted_closed_bars"] == 59
    assert report["worker_executed"] is False
    assert not calls


def test_r29_first_and_next_decision_have_no_future_candles(
    tmp_path, monkeypatch,
):
    args, state, calls = staged(tmp_path, monkeypatch, sizes=(60, 1))
    first, first_raw = r29.review_r29_one_closed_bar_shadow(
        **args, decision_bar_index=60,
    )
    assert first["decision"] == "NO_SIGNAL"
    assert len(calls[0]["candles"]) == 60
    assert calls[0]["candles"][-1]["close_time"] == (
        "2026-10-20T15:00:00Z"
    )
    assert first["network_used"] is False
    assert first["broker_orders_sent"] is False
    assert first["net_profit_verified"] is False
    second, second_raw = r29.review_r29_one_closed_bar_shadow(
        **args, decision_bar_index=61,
        previous_r29_receipt_bytes=first_raw,
    )
    assert len(calls[1]["candles"]) == 61
    assert second["decision_bar_index"] == 61
    assert second["previous_r29_receipt_sha256"] == first["receipt_sha256"]
    assert first_raw != second_raw
    assert state.accepted_batches == 2


def test_r29_rejects_gap_replay_tampering_and_future(
    tmp_path, monkeypatch,
):
    args, _, calls = staged(tmp_path, monkeypatch, sizes=(61,))
    with pytest.raises(r29.R29ShadowRefused, match="FIRST_DECISION"):
        r29.review_r29_one_closed_bar_shadow(
            **args, decision_bar_index=61,
        )
    with pytest.raises(r29.R29ShadowRefused, match="UNCAPTURED"):
        r29.review_r29_one_closed_bar_shadow(
            **args, decision_bar_index=62,
        )
    first, first_raw = r29.review_r29_one_closed_bar_shadow(
        **args, decision_bar_index=60,
    )
    tampered = first_raw.replace(b'"decision":"NO_SIGNAL"',
                                 b'"decision":"LONG"')
    with pytest.raises(r29.R29ShadowRefused, match="PREVIOUS_CHECKPOINT"):
        r29.review_r29_one_closed_bar_shadow(
            **args, decision_bar_index=61,
            previous_r29_receipt_bytes=tampered,
        )
    assert first["actual_fills_verified"] is False
    assert len(calls) == 1


def test_r29_fails_closed_for_nonproduction_r24_drift_and_bad_csv(
    tmp_path, monkeypatch,
):
    args, state, calls = staged(tmp_path, monkeypatch, sizes=(60,))
    with pytest.raises(r29.R29ShadowRefused, match="EXPLICIT"):
        r29.review_r29_one_closed_bar_shadow(
            **{**args, "operator_ack": False},
            decision_bar_index=60,
        )
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(r29.R29ShadowRefused, match="EXPLICIT"):
        r29.review_r29_one_closed_bar_shadow(
            **args, decision_bar_index=60,
        )
    monkeypatch.delenv("MMT_PRODUCTION")
    state.next_open_utc = state.next_open_utc + r29.BAR
    with pytest.raises(r29.R29ShadowRefused, match="COVERAGE"):
        r29.review_r29_one_closed_bar_shadow(
            **args, decision_bar_index=60,
        )
    assert not calls


def test_r29_private_append_only_receipt_file(tmp_path, monkeypatch):
    args, _, _ = staged(tmp_path, monkeypatch, sizes=(60,))
    _, raw = r29.review_r29_one_closed_bar_shadow(
        **args, decision_bar_index=60,
    )
    target = tmp_path / "private"
    target.mkdir(mode=0o700)
    result = r29.save_r29_receipt_exclusive(
        directory=target.resolve(), receipt=raw, operator_ack=True,
    )
    assert result.read_bytes() == raw
    assert result.stat().st_mode & 0o077 == 0
    with pytest.raises(r29.R29ShadowRefused, match="NO_OVERWRITE"):
        r29.save_r29_receipt_exclusive(
            directory=target.resolve(), receipt=raw, operator_ack=True,
        )
    world = tmp_path / "public"
    world.mkdir(mode=0o755)
    with pytest.raises(r29.R29ShadowRefused, match="PRIVATE_OUTPUT"):
        r29.save_r29_receipt_exclusive(
            directory=world.resolve(), receipt=raw, operator_ack=True,
        )


def test_r29_saver_rejects_even_rehashed_forged_live_flags(tmp_path, monkeypatch):
    args, _, _ = staged(tmp_path, monkeypatch, sizes=(60,))
    _, raw = r29.review_r29_one_closed_bar_shadow(
        **args, decision_bar_index=60,
    )
    target = tmp_path / "private-extra"
    target.mkdir(mode=0o700)
    forged = json.loads(raw)
    forged["broker_orders_sent"] = True
    unsigned = {k: v for k, v in forged.items() if k != "receipt_sha256"}
    forged["receipt_sha256"] = hashlib.sha256(
        r29._canonical(unsigned),
    ).hexdigest()
    bytes_forged = r29._canonical(forged)
    with pytest.raises(r29.R29ShadowRefused, match="CHECKPOINT_RECEIPT_INVALID"):
        r29.save_r29_receipt_exclusive(
            directory=target.resolve(), receipt=bytes_forged,
            operator_ack=True,
        )
    assert list(target.iterdir()) == []


def test_r29_broken_r24_timegrid_is_rejected_before_worker(
    tmp_path, monkeypatch,
):
    args, _, calls = staged(tmp_path, monkeypatch, sizes=(60,))
    file = (args["previous_directories"][0]
            / "canonical-reviewed-closed-candles.csv")
    raw = file.read_bytes()
    changed = raw.replace(b"2026-10-20T00:15:00Z",
                          b"2026-10-20T00:30:00Z", 1)
    file.write_bytes(changed)
    with pytest.raises(r29.R29ShadowRefused, match="CANDLE_GAP_OR_ORDER"):
        r29.review_r29_one_closed_bar_shadow(
            **args, decision_bar_index=60,
        )
    assert not calls
