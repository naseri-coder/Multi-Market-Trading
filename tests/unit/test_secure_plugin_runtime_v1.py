"""Nonproduction Stage 4 security contract; Docker/gVisor not started by tests."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

from naseri_markets.contracts import Instrument, Market
from naseri_markets.core_api_v1 import (
    ClosedCandle, CoreBinding, CoreEventType, CoreInput, DataOrigin,
)
from naseri_markets.example_dual_setup_core_v1 import DualSetupExampleCore
from naseri_markets.secure_plugin_runtime_v1 import (
    SecureOfflineCoreHost, SecurePluginPolicy, SecurePluginRefused,
    build_run_command, parse_core_result, _BOOTSTRAP,
)

CORE = DualSetupExampleCore()
SOURCE = b'import sys,json\nprint(json.dumps({"status":"unused"}))\n'
SHA = hashlib.sha256(SOURCE).hexdigest()
T = datetime(2026, 10, 11, 10, 0, tzinfo=UTC)
IMAGE = 'registry.example.invalid/verified-python@sha256:' + 'a'*64


def event(provider='venue_a', symbol='ALPHAUSD', ident='binding_a'):
    b = CoreBinding('instance_one', ident,
                    Instrument(Market.CRYPTO, provider, symbol, 'UTC', 'USD'), '15m')
    candles = (
        ClosedCandle(T, T+timedelta(minutes=15), D('100'), D('102'), D('98'), D('100'), D('10')),
        ClosedCandle(T+timedelta(minutes=15), T+timedelta(minutes=30), D('100'),
                     D('108'), D('99'), D('106'), D('10')),
    )
    return CoreInput(CORE.manifest.core_id, CORE.manifest.core_version,
                     b, CoreEventType.CLOSED_CANDLE, candles[-1].close_at,
                     DataOrigin.SYNTHETIC, 'frozen_offline_fixture', candles)


def wire(e, *, decision_override=None):
    d, = CORE.evaluate(e).decisions
    entry = dict(decision_id=d.decision_id, kind=d.kind.value,
                 setup_id=d.setup_id, direction=d.direction.value,
                 entry=str(d.entry), stop=str(d.stop),
                 targets=[str(t) for t in d.targets],
                 reason_codes=list(d.reason_codes))
    if decision_override:
        entry.update(decision_override)
    return json.dumps(dict(abi_major=1, abi_minor=0, core_id=e.core_id,
                           core_version=e.core_version, instance_id=e.binding.instance_id,
                           binding_id=e.binding.binding_id,
                           observed_at=e.observed_at.isoformat(),
                           input_digest=e.input_digest, decisions=[entry]),
                      separators=(',', ':')).encode()


def policy(monkeypatch):
    monkeypatch.setattr(os, 'geteuid', lambda: 1001)
    return SecurePluginPolicy(True, IMAGE, docker_binary='/usr/bin/docker',
                              docker_socket='unix:///run/user/1001/docker.sock')


def test_disabled_by_default(monkeypatch):
    host = SecureOfflineCoreHost(SecurePluginPolicy())
    with pytest.raises(SecurePluginRefused, match='DISABLED'):
        host.evaluate(CORE.manifest, event(), source=SOURCE, approved_source_sha256=SHA)


def test_refuse_nonroot_misconfiguration(monkeypatch):
    monkeypatch.setattr(os, 'geteuid', lambda: 0)
    with pytest.raises(SecurePluginRefused, match='UNSAFE'):
        SecurePluginPolicy(True, IMAGE, docker_socket='unix:///run/user/0/docker.sock')


@pytest.mark.parametrize('img', ['python:3.12', 'python@sha256:xxxx', '',
                                  'python@sha256:'+'G'*64])
def test_refuse_unpinned_images(monkeypatch, img):
    monkeypatch.setattr(os, 'geteuid', lambda: 1001)
    with pytest.raises(SecurePluginRefused, match='UNSAFE'):
        SecurePluginPolicy(True, img, docker_socket='unix:///run/user/1001/docker.sock')


def test_refuse_privileged_docker_socket(monkeypatch):
    monkeypatch.setattr(os, 'geteuid', lambda: 1001)
    with pytest.raises(SecurePluginRefused, match='ROOTLESS'):
        SecurePluginPolicy(True, IMAGE, docker_socket='unix:///var/run/docker.sock')


def test_hardened_oci_arguments_and_static_bootstrap(monkeypatch):
    p = policy(monkeypatch)
    name = 'mmt-core-'+'0'*24
    argv = build_run_command(p, name)
    command = ' '.join(argv)
    for switch in ('--runtime=runsc', '--network=none', '--read-only',
                   '--cap-drop=ALL', '--security-opt=no-new-privileges',
                   '--pids-limit=32', '--memory=128m', '--memory-swap=128m',
                   '--cpus=0.5', '--user=65534:65534', '--pull=never', '--ipc=none'):
        assert switch in argv
    assert not any(s.startswith('--volume') or s.startswith('--mount') or
                   s.startswith('--privileged') for s in argv)
    assert SOURCE.decode().strip() not in command
    assert argv[-1] == _BOOTSTRAP
    with pytest.raises(SecurePluginRefused):
        build_run_command(p, 'arbitrary-user-container')


def test_parse_valid_typed_entry_and_multiple_bindings():
    for e in (event(), event('broker_b', 'BETAUSD', 'binding_b')):
        result = parse_core_result(wire(e), CORE.manifest, e)
        assert result.binding_id == e.binding.binding_id
        assert result.input_digest == e.input_digest
        assert result.decisions[0].entry == D('106')


@pytest.mark.parametrize('override', [
    {'setup_id':'not_declared'}, {'direction':'short'}, {'stop':'999'},
    {'entry':123.4}, {'entry':'NaN'}, {'targets':['0']},
    {'reason_codes':[{'untrusted':'payload'}]},
    {'action':'close_position'}, {'fake_execution_permission': True},
])
def test_reject_invalid_or_malicious_decisions(override):
    e = event()
    with pytest.raises(SecurePluginRefused):
        parse_core_result(wire(e, decision_override=override), CORE.manifest, e)


def test_reject_duplicate_json_top_level():
    e = event()
    raw = wire(e).decode().replace('"abi_major":1,','"abi_major":1,"abi_major":1,')
    with pytest.raises(SecurePluginRefused, match='DUPLICATE'):
        parse_core_result(raw.encode(), CORE.manifest, e)


def test_reject_identity_and_provenance_forgery():
    e = event()
    for field, value in [('binding_id','elsewhere'), ('core_id','other_core'),
                         ('input_digest','0'*64), ('observed_at','2026-01-01T00:00:00+00:00')]:
        data = json.loads(wire(e))
        data[field] = value
        with pytest.raises(SecurePluginRefused):
            parse_core_result(json.dumps(data).encode(), CORE.manifest, e)


def test_reject_bad_abi_and_unknown_fields():
    e = event()
    for key,val in [('abi_major',2),('abi_minor',1),('abi_major',True),
                    ('broker_order_authorized',True)]:
        d = json.loads(wire(e)); d[key] = val
        with pytest.raises(SecurePluginRefused):
            parse_core_result(json.dumps(d).encode(), CORE.manifest, e)


def test_reject_oversized_output_and_unparseable():
    e=event()
    for payload in (b'', b'{'*100, b'x'*16385, b'{"abi_major":NaN}', b'[]'):
        with pytest.raises(SecurePluginRefused):
            parse_core_result(payload, CORE.manifest, e)


def test_mock_transport_accepts_only_validated_data(monkeypatch):
    from naseri_markets import secure_plugin_runtime_v1 as module
    p = policy(monkeypatch)
    good = event()
    monkeypatch.setattr(module, '_assert_rootless_socket', lambda p: None)
    monkeypatch.setattr(module, '_ensure_rootless_daemon', lambda p: None)
    seen=[]
    def stub(policy, name, framed):
        assert re.fullmatch('mmt-core-[0-9a-f]{24}', name)
        size=int.from_bytes(framed[:4], 'big')
        assert framed[4:4+size] == SOURCE
        request=json.loads(framed[4+size:])
        assert request['abi_major'] == 1
        assert request['event']['binding']['instrument']['symbol'] == 'ALPHAUSD'
        assert request['input_digest'] == good.input_digest
        assert 'account' not in request and 'api_key' not in request
        seen.append(name)
        return wire(good)
    monkeypatch.setattr(module, '_invoke', stub)
    out=SecureOfflineCoreHost(p).evaluate(CORE.manifest, good, source=SOURCE,
                                          approved_source_sha256=SHA)
    assert out.binding_id == good.binding.binding_id and len(seen)==1


def test_wrong_pin_never_invokes_child(monkeypatch):
    from naseri_markets import secure_plugin_runtime_v1 as module
    p=policy(monkeypatch)
    monkeypatch.setattr(module, '_invoke', lambda *args: pytest.fail('invoked'))
    with pytest.raises(SecurePluginRefused, match='SOURCE_PIN'):
        SecureOfflineCoreHost(p).evaluate(CORE.manifest, event(), source=SOURCE,
                                          approved_source_sha256='0'*64)


def test_bad_result_quarantines_binding_and_denies_retries(monkeypatch):
    from naseri_markets import secure_plugin_runtime_v1 as module
    p=policy(monkeypatch)
    monkeypatch.setattr(module, '_assert_rootless_socket', lambda p: None)
    monkeypatch.setattr(module, '_ensure_rootless_daemon', lambda p: None)
    times=[]
    def fake(*args):
        times.append(1)
        return b'{}'
    monkeypatch.setattr(module, '_invoke', fake)
    host=SecureOfflineCoreHost(p)
    e=event()
    with pytest.raises(SecurePluginRefused, match='QUARANTINED'):
        host.evaluate(CORE.manifest,e,source=SOURCE,approved_source_sha256=SHA)
    with pytest.raises(SecurePluginRefused, match='BINDING_QUARANTINED'):
        host.evaluate(CORE.manifest,e,source=SOURCE,approved_source_sha256=SHA)
    assert len(times)==1


def test_fail_closed_when_daemon_absent(monkeypatch):
    from naseri_markets import secure_plugin_runtime_v1 as module
    p=policy(monkeypatch)
    monkeypatch.setattr(module, '_assert_rootless_socket',
                        lambda policy: (_ for _ in ()).throw(SecurePluginRefused('NO_DAEMON')))
    host=SecureOfflineCoreHost(p)
    with pytest.raises(SecurePluginRefused, match='QUARANTINED'):
        host.evaluate(CORE.manifest,event(),source=SOURCE,approved_source_sha256=SHA)


def test_no_new_live_permissions_in_module():
    source=open(module_path(),encoding='utf-8').read()
    for bad in ('order_send(', 'send_message(', 'BROKER_API_KEY', 'TELEGRAM_BOT_TOKEN'):
        assert bad not in source


def module_path():
    from naseri_markets import secure_plugin_runtime_v1 as module
    return module.__file__


def test_static_bootstrap_with_harmless_no_setup_worker():
    """Known trusted toy worker ONLY; this is not a real sandbox/security test."""
    from naseri_markets.core_api_v1 import _canonical
    e = event()
    code = b"""import sys,json
r=json.load(sys.stdin); e=r['event']
print(json.dumps({'abi_major':1,'abi_minor':0,'core_id':e['core_id'],
'core_version':e['core_version'],'instance_id':e['binding']['instance_id'],
'binding_id':e['binding']['binding_id'],'observed_at':e['observed_at'],
'input_digest':r['input_digest'],'decisions':[{'decision_id':'no_setup_1','kind':'no_setup'}]}))
"""
    payload=json.dumps(dict(abi_major=1,abi_minor=0,input_digest=e.input_digest,
                            event=_canonical(e)),sort_keys=True).encode('utf-8')
    framed=len(code).to_bytes(4,'big')+code+payload
    proc=subprocess.run([sys.executable,'-I','-S','-c',_BOOTSTRAP],
                        input=framed,capture_output=True,timeout=4,check=False)
    assert proc.returncode == 0, proc.stderr
    out=parse_core_result(proc.stdout,CORE.manifest,e)
    assert out.decisions[0].kind.value=='no_setup'
