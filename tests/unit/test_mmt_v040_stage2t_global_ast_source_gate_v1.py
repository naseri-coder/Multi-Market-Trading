"""Full-checkout 226-source production AST gate and source identity checks.

This file MUST run against the genuine checkout. Never substitute synthetic
modules for release acceptance. Reads source and metadata only, no I/O to
brokers, Telegram, production databases, or build/output directories.
"""
from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / 'docs' / 'MMT_V0_4_0_PUBLIC_MODULE_SNAPSHOT.json'
AUDITOR = ROOT / 'scripts' / 'mmt_v040_production_guard_ast_audit_v1.py'


def _locked_source() -> dict[str, bytes]:
    spec = json.loads(LOCK.read_text(encoding='utf-8'))
    assert spec['expected_module_count'] == 226
    files = spec['modules']
    assert len(files) == 226
    seen = set()
    bodies = {}
    for entry in files:
        name = entry['path']
        assert name.startswith('naseri_markets/') and name.endswith('.py')
        assert name not in seen
        seen.add(name)
        raw = (ROOT / name).read_bytes()
        assert len(raw) == entry['size'], name
        git_blob = hashlib.sha1(b'blob ' + str(len(raw)).encode('ascii') + b'\0' + raw).hexdigest()
        assert git_blob == entry['git_blob_sha1'], name
        bodies[name] = raw
    assert sum(map(len, bodies.values())) == spec['source_bytes']
    return bodies


def _audit():
    assert AUDITOR.is_file()
    return runpy.run_path(str(AUDITOR))


def test_exact_real_226_module_source_identity_and_global_ast_pass():
    bodies = _locked_source()
    verdict = _audit()['require_no_value_only_guards'](bodies)
    assert verdict['verdict'] == 'V040_SOURCE_PRODUCTION_GUARDS_PASS'
    assert verdict['module_count'] == 226
    assert verdict['value_only_guards'] == 0
    assert verdict['public_release_authorized'] is False
    assert verdict['install_authorized'] is False
    assert verdict['live_trading_authorized'] is False


def test_single_tamper_production_value_only_guard_always_rejected():
    bodies = _locked_source()
    first = sorted(bodies)[0]
    tampered = dict(bodies)
    tampered[first] += b'\ndef _unsafe_test():\n    return os.environ.get("MMT_PRODUCTION") == "1"\n'
    scanner = _audit()
    with pytest.raises(scanner['ProductionGuardRefused'], match='V040_PRODUCTION_VALUE_ONLY_GUARDS_DENIED:1'):
        scanner['require_no_value_only_guards'](tampered)


@pytest.mark.parametrize('expression', [
    'os.environ.get("MMT_PRODUCTION") == "1"',
    '"0" == os.environ.get("MMT_PRODUCTION")',
    'environment.get("MMT_PRODUCTION") == "false"',
    'os.environ["MMT_PRODUCTION"] != "1"',
])
def test_existing_scanner_denies_value_literal_comparisons(expression: str):
    src = ('def restricted():\n    return ' + expression + '\n').encode('utf-8')
    assert _audit()['scan'](src), expression


@pytest.mark.parametrize('expression', [
    '"MMT_PRODUCTION" in os.environ',
    '"MMT_PRODUCTION" not in os.environ',
])
def test_existing_scanner_accepts_presence_checks(expression: str):
    src = ('def restricted():\n    return ' + expression + '\n').encode('utf-8')
    assert _audit()['scan'](src) == ()
