"""Executable operator-trusted public Custom PAPER MVP acceptance and security."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from naseri_markets.custom_cli import _export_demo
from naseri_markets.trusted_custom import (
    LocalCustomRefused, TRUST_ACK, TrustedLocalCustomHost,
    parse_offline_quote,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def environment(tmp_path):
    sample = _export_demo(tmp_path / "demo")
    manifest = tmp_path / "demo/descriptor.json"
    source = tmp_path / "demo/public_toy_demo.py"
    quote = tmp_path / "demo/quote.json"
    dbdir = tmp_path / "private_state"
    host = TrustedLocalCustomHost(dbdir)
    yield sample, manifest, source, quote, host, dbdir
    host.close()


def register(environment):
    sample, manifest, source, quote, host, _ = environment
    return host.register(
        manifest, source, descriptor_sha256=sample["descriptor_sha256"],
        code_sha256=sample["code_sha256"], trust_ack=TRUST_ACK)


def enable(environment):
    sample, _, _, _, host, _ = environment
    status = host.get("public_toy_demo")
    return host.toggle(
        "public_toy_demo", enabled=True, expected_revision=status.revision,
        descriptor_sha256=sample["descriptor_sha256"])


def get_quote(environment):
    return environment[3].read_bytes()


def test_real_external_python_exec_paper_duplicate_disable_restart(environment):
    sample, _, _, _, host, state_dir = environment
    assert host.list() == ()
    status = register(environment)
    assert status.engine_id == "public_toy_demo"
    assert status.revision == 1 and not status.enabled
    assert not status.sandboxed
    assert not status.publisher_authenticated
    assert not status.live_trading_permitted
    with pytest.raises(LocalCustomRefused, match="ENGINE_DISABLED"):
        host.paper(status.engine_id, get_quote(environment))
    assert enable(environment).revision == 2
    result = host.paper(status.engine_id, get_quote(environment))
    assert result["result"] == "RECORDED"
    assert result["stored"] == 1 and result["live_trading_permitted"] is False
    assert len(host.signals("public_toy_demo")) == 1
    record = host.signals("public_toy_demo")[0]
    assert record["evidence_mode"] == "paper"
    assert record["market"] == "index"
    assert record["engine_id"] == "public_toy_demo"
    assert record["direction"] == "long"
    assert host.paper(status.engine_id, get_quote(environment))["result"] == "DUPLICATE"
    assert len(host.signals()) == 1
    host.close()
    reopened = TrustedLocalCustomHost(state_dir)
    try:
        assert reopened.get(status.engine_id).enabled
        disabled = reopened.toggle(status.engine_id, enabled=False,
                                   expected_revision=2)
        assert disabled.revision == 3 and not disabled.enabled
        with pytest.raises(LocalCustomRefused, match="ENGINE_DISABLED"):
            reopened.paper(status.engine_id, get_quote(environment))
        assert len(reopened.signals()) == 1
    finally:
        reopened.close()
    # Avoid closing a same connection twice in the fixture finalizer:
    environment = None


def test_exact_separately_pinned_local_code_trust_and_private_contract_fences(environment):
    sample, manifest, source, _, host, state_dir = environment
    with pytest.raises(LocalCustomRefused, match="EXPLICIT_TRUST"):
        host.register(manifest, source,
                      descriptor_sha256=sample["descriptor_sha256"],
                      code_sha256=sample["code_sha256"], trust_ack="")
    with pytest.raises(LocalCustomRefused, match="INDEPENDENT_CODE_PIN"):
        host.register(manifest, source,
                      descriptor_sha256=sample["descriptor_sha256"],
                      code_sha256="0"*64, trust_ack=TRUST_ACK)
    document = json.loads(manifest.read_bytes())
    document["access_policy"] = "owner_only"
    private = state_dir / "owner.json"
    private.write_text(json.dumps(document))
    with pytest.raises(LocalCustomRefused, match="OWNER_PRIVATE"):
        host.register(private, source,
                      descriptor_sha256=hashlib.sha256(private.read_bytes()).hexdigest(),
                      code_sha256=sample["code_sha256"], trust_ack=TRUST_ACK)
    document["access_policy"] = "public_custom"
    document["strategy_family"] = "ny_first_reversal"
    document["engine_id"] = "ny_first_reversal"
    private.write_text(json.dumps(document))
    with pytest.raises(ValueError):
        host.register(private, source,
                      descriptor_sha256=hashlib.sha256(private.read_bytes()).hexdigest(),
                      code_sha256=sample["code_sha256"], trust_ack=TRUST_ACK)
    assert host.list() == ()


def test_code_snapshot_pinned_independent_of_mutated_original(environment):
    sample, manifest, source, quote, host, root = environment
    register(environment)
    enable(environment)
    source.write_text("raise SystemExit(5)\n")
    result = host.paper("public_toy_demo", get_quote(environment))
    assert result["stored"] == 1
    snapshot = root / "trusted_scripts" / (
        "public_toy_demo-" + sample["code_sha256"] + ".py")
    assert snapshot.stat().st_mode & 0o077 == 0
    snapshot.write_text("raise SystemExit(5)\n")
    with pytest.raises(LocalCustomRefused, match="SCRIPT_PIN_CHANGED"):
        host.paper("public_toy_demo", get_quote(environment))


@pytest.mark.parametrize("change", [
    {"origin": "live_provider"},
    {"market": "unlisted"},
    {"bid": "-1"},
    {"bid": "NaN"},
    {"ask": "42000"},
    {"timezone": "Not_A_Timezone"},
    {"symbol": ""},
    {"extra": "unauthorized"},
])
def test_live_and_invalid_market_quotes_never_execute_or_persist(environment, change):
    register(environment)
    enable(environment)
    quote = json.loads(get_quote(environment))
    quote.update(change)
    with pytest.raises(LocalCustomRefused):
        environment[4].paper(
            "public_toy_demo", json.dumps(quote).encode())
    assert environment[4].signals() == []


def test_source_symlink_and_duplicate_registration_are_denied(environment):
    sample, manifest, source, _, host, root = environment
    alias = root / "alias.py"
    alias.symlink_to(source)
    with pytest.raises(LocalCustomRefused, match="REGULAR_FILE"):
        host.register(manifest, alias,
                      descriptor_sha256=sample["descriptor_sha256"],
                      code_sha256=sample["code_sha256"], trust_ack=TRUST_ACK)
    register(environment)
    with pytest.raises(LocalCustomRefused, match="DUPLICATE_REGISTRATION"):
        register(environment)


def test_invalid_worker_quarantines_engine_and_no_paper_output(environment):
    sample, manifest, source, quote, host, root = environment
    source.write_text("import sys\nsys.stdout.write('not json')\n")
    checksum = hashlib.sha256(source.read_bytes()).hexdigest()
    host.register(manifest, source, descriptor_sha256=sample["descriptor_sha256"],
                  code_sha256=checksum, trust_ack=TRUST_ACK)
    enable(environment)
    with pytest.raises(LocalCustomRefused, match="WORKER_QUARANTINED"):
        host.paper("public_toy_demo", get_quote(environment))
    assert not host.get("public_toy_demo").enabled
    assert host.get("public_toy_demo").revision == 3
    assert host.signals() == []


def test_real_worker_timeout_quarantines_and_stops_future_invocation(environment):
    sample, manifest, source, quote, host, root = environment
    source.write_text("import time\ntime.sleep(1)\n")
    host.register(manifest, source, descriptor_sha256=sample["descriptor_sha256"],
                  code_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  trust_ack=TRUST_ACK)
    enable(environment)
    with pytest.raises(LocalCustomRefused, match="WORKER_QUARANTINED"):
        host.paper("public_toy_demo", get_quote(environment), timeout_seconds=0.1)
    assert host.get("public_toy_demo").enabled is False
    assert host.signals() == []


def test_real_independent_sqlite_disable_before_paper_commit_wins(
        environment, monkeypatch):
    sample, _, _, _, host, root = environment
    register(environment)
    enable(environment)
    original = subprocess.run

    def concurrent_revoker(*args, **kwargs):
        result = original(*args, **kwargs)
        rival = TrustedLocalCustomHost(root)
        try:
            rival.toggle("public_toy_demo", enabled=False, expected_revision=2)
        finally:
            rival.close()
        return result

    monkeypatch.setattr(
        "naseri_markets.trusted_custom.subprocess.run", concurrent_revoker)
    with pytest.raises(LocalCustomRefused, match="REVOKED_DURING_EXECUTION"):
        host.paper("public_toy_demo", get_quote(environment))
    assert host.get("public_toy_demo").enabled is False
    assert host.signals() == []


def test_real_independent_sqlite_disable_after_commit_does_not_erase_paper(
        environment, monkeypatch):
    sample, _, _, _, host, root = environment
    register(environment)
    enable(environment)
    original = host._db.execute
    # Use a separate connection after commit instead of monkeypatching an
    # SQLite read-only C attribute. This proves persisted permission and log.
    assert host.paper("public_toy_demo", get_quote(environment))["stored"] == 1
    rival = TrustedLocalCustomHost(root)
    try:
        rival.toggle("public_toy_demo", enabled=False, expected_revision=2)
    finally:
        rival.close()
    assert host.get("public_toy_demo").enabled is False
    assert len(host.signals()) == 1


def test_external_cli_complete_register_enable_paper_list_disable(environment, tmp_path):
    sample, manifest, source, quote, host, state_dir = environment
    host.close()
    def call(*argv, ok=True):
        result = subprocess.run(
            [sys.executable, "-m", "naseri_markets.custom_cli",
             "--state-dir", str(state_dir), *argv],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=9)
        assert (result.returncode == 0) == ok, result.stderr.decode()
        return json.loads(result.stdout) if ok else result.stderr.decode()
    assert call("list") == []
    assert "REFUSED" in call("paper", "public_toy_demo",
                             "--quote", str(quote), ok=False)
    no_trust = call(
        "register", "--descriptor", str(manifest), "--code", str(source),
        "--descriptor-sha256", sample["descriptor_sha256"],
        "--code-sha256", sample["code_sha256"], ok=False)
    assert "CUSTOM_PAPER_REFUSED" in no_trust
    assert not call("register", "--descriptor", str(manifest), "--code", str(source),
                    "--descriptor-sha256", sample["descriptor_sha256"],
                    "--code-sha256", sample["code_sha256"],
                    "--trust-local-code")["enabled"]
    assert call("enable", "public_toy_demo", "--revision", "1",
                "--descriptor-sha256", sample["descriptor_sha256"])["enabled"]
    assert call("paper", "public_toy_demo", "--quote", str(quote))["stored"] == 1
    assert len(call("signals", "--engine-id", "public_toy_demo")) == 1
    assert not call("disable", "public_toy_demo", "--revision", "2")["enabled"]
    assert "REFUSED" in call("paper", "public_toy_demo",
                             "--quote", str(quote), ok=False)


def test_test_only_sample_export_requires_new_non_symlink_directory(tmp_path):
    x = _export_demo(tmp_path / "first")
    assert x["trust_required"]
    with pytest.raises(LocalCustomRefused):
        _export_demo(tmp_path / "first")


def test_no_network_or_private_nyfr_in_public_example_and_local_cli():
    import ast
    import inspect
    import naseri_markets.public_demo_custom_worker as demo
    from naseri_markets import custom_cli, trusted_custom
    source = inspect.getsource(demo)
    assert "ny_first_reversal" not in source
    assert "r0_engine" not in source
    assert "MetaTrader5" not in source
    for mod in (demo, custom_cli, trusted_custom):
        ast.parse(inspect.getsource(mod))
