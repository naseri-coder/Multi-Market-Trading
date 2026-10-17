"""An actual bundled toy worker + existing durable SQLite host, no live calls."""
from __future__ import annotations

import json
from pathlib import Path

from naseri_markets.paper_demo_cli_v1 import main


def _do(monkeypatch, capsys, folder: Path, action: str, *more: str, env: bool = True):
    if env:
        monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    code = main(["--state-dir", str(folder), action, *more])
    out = capsys.readouterr()
    return code, json.loads(out.out) if code == 0 else out.err


def _init(monkeypatch, capsys, tmp_path):
    root = tmp_path / "isolated"
    status, answer = _do(monkeypatch, capsys, root, "init", "--ack-reviewed-public-toy")
    assert status == 0
    assert not answer["enabled"] and answer["revision"] == 1
    assert not answer["telegram_sent"] and not answer["broker_order_sent"]
    assert root.stat().st_mode & 0o077 == 0
    return root, answer


def test_explicit_consent_required_and_no_implicit_state(monkeypatch, capsys, tmp_path):
    root = tmp_path / "unmade"
    monkeypatch.delenv("MMT_NONPRODUCTION", raising=False)
    assert _do(monkeypatch, capsys, root, "init", "--ack-reviewed-public-toy", env=False)[0] == 2
    assert not root.exists()
    assert _do(monkeypatch, capsys, root, "init")[0] == 2
    assert not root.exists()
    assert _do(monkeypatch, capsys, root, "inspect")[0] == 2
    assert not root.exists()


def test_full_installed_style_user_journey_and_restart(monkeypatch, capsys, tmp_path):
    root, init = _init(monkeypatch, capsys, tmp_path)
    assert _do(monkeypatch, capsys, root, "replay", "--ack-offline-replay")[0] == 2
    status, on = _do(monkeypatch, capsys, root, "enable", "--revision", "1",
                     "--descriptor-sha256", init["descriptor_sha256"])
    assert status == 0 and on["revision"] == 2 and on["enabled"]
    status, first = _do(monkeypatch, capsys, root, "replay", "--ack-offline-replay")
    assert status == 0 and first["receipt"]["result"] == "RECORDED"
    assert first["paper_signal_count"] == 1
    assert first["receipt"]["telegram_enabled"] is False
    assert first["receipt"]["live_trading_permitted"] is False
    status, duplicate = _do(monkeypatch, capsys, root, "replay", "--ack-offline-replay")
    assert status == 0 and duplicate["receipt"]["result"] == "DUPLICATE"
    assert duplicate["journal_sha256"] == first["journal_sha256"]
    status, restarted = _do(monkeypatch, capsys, root, "inspect")
    assert status == 0 and restarted["paper_signal_count"] == 1
    assert restarted["journal_sha256"] == first["journal_sha256"]
    status, off = _do(monkeypatch, capsys, root, "disable", "--revision", "2")
    assert status == 0 and not off["enabled"] and off["revision"] == 3
    assert off["paper_signal_count"] == 1
    assert _do(monkeypatch, capsys, root, "replay", "--ack-offline-replay")[0] == 2
    assert _do(monkeypatch, capsys, root, "inspect")[1]["journal_sha256"] == first["journal_sha256"]


def test_stale_revision_and_wrong_hash_fail_closed(monkeypatch, capsys, tmp_path):
    root, info = _init(monkeypatch, capsys, tmp_path)
    assert _do(monkeypatch, capsys, root, "enable", "--revision", "1",
               "--descriptor-sha256", "0" * 64)[0] == 2
    assert _do(monkeypatch, capsys, root, "enable", "--revision", "0",
               "--descriptor-sha256", info["descriptor_sha256"])[0] == 2
    assert _do(monkeypatch, capsys, root, "inspect")[1]["revision"] == 1
    assert _do(monkeypatch, capsys, root, "disable", "--revision", "2")[0] == 2


def test_reinitialization_and_unsafe_paths_refused(monkeypatch, capsys, tmp_path):
    root, _ = _init(monkeypatch, capsys, tmp_path)
    assert _do(monkeypatch, capsys, root, "init", "--ack-reviewed-public-toy")[0] == 2
    link = tmp_path / "alias"
    link.symlink_to(root, target_is_directory=True)
    assert _do(monkeypatch, capsys, link, "inspect")[0] == 2
    assert _do(monkeypatch, capsys, Path("relative"), "inspect")[0] == 2


def test_no_live_venue_quote_provenance(monkeypatch, capsys, tmp_path):
    root, info = _init(monkeypatch, capsys, tmp_path)
    assert _do(monkeypatch, capsys, root, "enable", "--revision", "1",
               "--descriptor-sha256", info["descriptor_sha256"])[0] == 0
    live = tmp_path / "live.json"
    source = json.loads((root / "sample" / "quote.json").read_text())
    source["origin"] = "live"
    live.write_text(json.dumps(source))
    assert _do(monkeypatch, capsys, root, "replay", "--quote", str(live),
               "--ack-offline-replay")[0] == 2
    assert _do(monkeypatch, capsys, root, "inspect")[1]["paper_signal_count"] == 0


def test_production_fence(monkeypatch, capsys, tmp_path):
    root = tmp_path / "blocked"
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    assert _do(monkeypatch, capsys, root, "init", "--ack-reviewed-public-toy")[0] == 2
    assert not root.exists()
    monkeypatch.delenv("MMT_PRODUCTION")


def test_tampered_pinned_worker_is_rejected(monkeypatch, capsys, tmp_path):
    root, info = _init(monkeypatch, capsys, tmp_path)
    assert _do(monkeypatch, capsys, root, "enable", "--revision", "1",
               "--descriptor-sha256", info["descriptor_sha256"])[0] == 0
    snapshot, = (root / "trusted_scripts").glob("*.py")
    snapshot.write_text("print('compromised')\n")
    assert _do(monkeypatch, capsys, root, "replay", "--ack-offline-replay")[0] == 2
    assert _do(monkeypatch, capsys, root, "inspect")[1]["paper_signal_count"] == 0


def test_fix05_partial_init_failure_removes_new_state(monkeypatch, capsys, tmp_path):
    from naseri_markets import paper_demo_cli_v1 as cli

    root = tmp_path / "aborted"
    def abort_export(sample_dir):
        sample_dir.mkdir(mode=0o700)
        (sample_dir / "partial").write_text("uncommitted")
        raise OSError("SIMULATED_DISK_WRITE_FAILURE")

    monkeypatch.setattr(cli, "_export_demo", abort_export)
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    code = cli.main(["--state-dir", str(root), "init", "--ack-reviewed-public-toy"])
    assert code == 2
    assert not root.exists()


def test_fix05_root_execution_refused_without_creating_state(
    monkeypatch, capsys, tmp_path,
):
    from naseri_markets import paper_demo_cli_v1 as cli

    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.setattr(cli.os, "geteuid", lambda: 0)
    root = tmp_path / "root-denied"
    code = cli.main(["--state-dir", str(root), "init", "--ack-reviewed-public-toy"])
    assert code == 2
    assert not root.exists()


def test_fix05_hardlinked_state_ledger_refused_on_restart(
    monkeypatch, capsys, tmp_path,
):
    import os

    root, _ = _init(monkeypatch, capsys, tmp_path)
    db = root / "custom_paper.db"
    elsewhere = tmp_path / "other.db"
    os.link(db, elsewhere)
    before = db.read_bytes()
    assert _do(monkeypatch, capsys, root, "inspect")[0] == 2
    assert _do(monkeypatch, capsys, root, "replay", "--ack-offline-replay")[0] == 2
    assert db.read_bytes() == before
