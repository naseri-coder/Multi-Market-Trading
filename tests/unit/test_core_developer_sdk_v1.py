"""Stage 14: hostile package rejection and positive offline signature conformance."""
from __future__ import annotations

import ast
import hashlib
import io
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from naseri_markets.core_certification_v1 import (
    CertificationRefused, evaluate_candidate, sign_package, verify_signature,
)
from naseri_markets.core_developer_sdk_v1 import (
    DeveloperPackageRefused, _archive, _wire, build_package, inspect_package,
    inspect_source, parse_manifest,
)

_ROOT = Path(__file__).resolve().parents[2]
_EXAMPLE = _ROOT / "examples" / "sdk"
_DECL = json.loads((_EXAMPLE / "manifest_v1.json").read_text(encoding="utf-8"))
_SOURCE = (_EXAMPLE / "core_template_v1.py").read_bytes()


def bundle():
    return build_package(_DECL, _SOURCE)


def test_reproducibility_exact_bytes_and_static_inspection():
    a, b = bundle(), bundle()
    assert a == b
    x = inspect_package(a)
    assert x.source == _SOURCE
    assert x.sha256 == hashlib.sha256(a).hexdigest()
    assert x.source_sha256 == hashlib.sha256(_SOURCE).hexdigest()
    assert x.manifest.core_id == "sample_public_core"
    assert len(x.manifest.setups) == 1
    assert x.warnings == ()


def test_offline_evidence_never_authorizes():
    unsigned = evaluate_candidate(bundle())
    assert unsigned.status == "REVIEW_REQUIRED_NONPRODUCTION"
    assert "PUBLISHER_SIGNATURE_MISSING" in unsigned.blockers
    assert "ACTUAL_ISOLATED_HOST_ATTESTATION_REQUIRED" in unsigned.blockers
    assert not unsigned.approved_for_public_distribution
    assert not unsigned.approved_for_execution
    assert not unsigned.approved_for_trading
    assert not unsigned.approved_for_telegram


def test_deterministic_archive_paths_and_times():
    with zipfile.ZipFile(io.BytesIO(bundle())) as z:
        assert z.namelist() == ["manifest.json", "plugin.py"]
        assert all(x.date_time == (1980, 1, 1, 0, 0, 0) for x in z.infolist())
        assert all(x.compress_type == zipfile.ZIP_STORED for x in z.infolist())


def test_manifest_matches_existing_core_contract():
    a = bundle()
    with zipfile.ZipFile(io.BytesIO(a)) as z:
        d, x = parse_manifest(z.read("manifest.json"))
    assert x.abi_major == 1 and x.abi_minor == 0
    assert d["plugin_sha256"] == hashlib.sha256(_SOURCE).hexdigest()
    assert set(x.supported_markets) == {"crypto", "forex"}
    assert {e.value for e in x.accepted_events} == {"closed_candle"}


@pytest.mark.parametrize("overrides,code", [
    ({"abi_major": 2}, "MANIFEST_VERSION"),
    ({"abi_minor": 1}, "MANIFEST_VERSION"),
    ({"schema_version": 2}, "MANIFEST_VERSION"),
    ({"entrypoint": "../evil.py"}, "MANIFEST_VERSION"),
    ({"supported_markets": ["crypto", "crypto"]}, "MARKETS"),
    ({"supported_markets": ["unknown"]}, "MARKETS"),
    ({"accepted_events": ["live"]}, "EVENTS"),
    ({"minimum_closed_candles": 0}, "CORE_ABI"),
    ({"minimum_closed_candles": True}, "CORE_ABI"),
    ({"core_id": "not valid"}, "IDENTITY"),
    ({"setups": []}, "SETUP_LIST"),
    ({"setups": [{"setup_id": "abc", "description": "hello", "may_manage_stop": "yes"}]}, "SETUP_SCHEMA"),
])
def test_invalid_manifest_rejected(overrides, code):
    with pytest.raises(DeveloperPackageRefused, match=code):
        build_package(_DECL | overrides, _SOURCE)


@pytest.mark.parametrize("extra", ["provider", "symbol", "broker", "account_id", "leverage", "secret", "auto_trade"])
def test_core_manifest_cannot_hardcode_deployment_settings(extra):
    with pytest.raises(DeveloperPackageRefused, match="SCHEMA"):
        build_package(_DECL | {extra: "should-not-be-in-core"}, _SOURCE)


@pytest.mark.parametrize("bad", [
    b"", b"\xff\xfe", b"\xef\xbb\xbfprint(1)", b"x=0\x00", b"a = (",
    b"a=1\n" * 33000,
])
def test_malformed_or_oversized_source_rejected(bad):
    with pytest.raises(DeveloperPackageRefused):
        build_package(_DECL, bad)


@pytest.mark.parametrize("code,expected", [
    (b"import socket\n", "DISALLOWED_IMPORT"),
    (b"from os import system\n", "DISALLOWED_IMPORT"),
    (b"eval('2+2')\n", "DANGEROUS_CALL"),
    (b"open('x')\n", "DANGEROUS_CALL"),
    (b"getattr(json, 'loads')\n", "DANGEROUS_CALL"),
    (b"x.__class__\n", "DUNDER_ATTRIBUTE_ACCESS"),
    (b"client.connect()\n", "DANGEROUS_ATTRIBUTE_CALL"),
])
def test_known_static_hazards_flagged_and_build_refused(code, expected):
    assert expected in inspect_source(code)
    with pytest.raises(DeveloperPackageRefused, match="STATIC_REVIEW_BLOCKED"):
        build_package(_DECL, code)


def test_manifest_duplicate_key_and_noncanonical_rejected():
    with zipfile.ZipFile(io.BytesIO(bundle())) as z:
        source, manifest = z.read("plugin.py"), z.read("manifest.json")
    assert inspect_package(_archive(manifest, source)).source == source
    duplicates = manifest[:-1] + b',"core_id":"duplicate"}'
    with pytest.raises(DeveloperPackageRefused, match="DUPLICATE_JSON"):
        inspect_package(_archive(duplicates, source))
    pretty = json.dumps(json.loads(manifest), indent=2).encode()
    with pytest.raises(DeveloperPackageRefused, match="NONCANONICAL"):
        inspect_package(_archive(pretty, source))


def test_manifest_digest_tamper_rejected():
    with zipfile.ZipFile(io.BytesIO(bundle())) as z:
        source, manifest = z.read("plugin.py"), json.loads(z.read("manifest.json"))
    manifest["plugin_sha256"] = "a" * 64
    with pytest.raises(DeveloperPackageRefused, match="SOURCE_HASH_MISMATCH"):
        inspect_package(_archive(_wire(manifest), source))


def test_payload_changed_with_manifest_unchanged_rejected():
    with zipfile.ZipFile(io.BytesIO(bundle())) as z:
        original_manifest = z.read("manifest.json")
    with pytest.raises(DeveloperPackageRefused, match="SOURCE_HASH_MISMATCH"):
        inspect_package(_archive(original_manifest, _SOURCE + b"\n# append\n"))


@pytest.mark.parametrize("filename", ["../plugin.py", "/tmp/plugin.py", "nested/plugin.py", "link", "evil.py"])
def test_zip_traversal_or_surprise_members_blocked(filename):
    base = io.BytesIO()
    with zipfile.ZipFile(base, "w") as z:
        z.writestr("manifest.json", b"{}")
        z.writestr(filename, _SOURCE)
    with pytest.raises(DeveloperPackageRefused):
        inspect_package(base.getvalue())


def test_zip_duplicates_and_appended_junk_blocked():
    base = io.BytesIO()
    with zipfile.ZipFile(base, "w") as z:
        z.writestr("manifest.json", b"{}")
        z.writestr("plugin.py", _SOURCE)
        z.writestr("plugin.py", b"overwritten")
    with pytest.raises(DeveloperPackageRefused, match="FILE_SET"):
        inspect_package(base.getvalue())
    with pytest.raises(DeveloperPackageRefused, match="NONCANONICAL"):
        inspect_package(bundle() + b"extradata")


def test_repack_compression_or_zip_extra_data_blocked():
    base = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(bundle())) as z:
        m,s = z.read("manifest.json"),z.read("plugin.py")
    with zipfile.ZipFile(base,"w",compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json",m)
        z.writestr("plugin.py",s)
    with pytest.raises(DeveloperPackageRefused, match="NONCANONICAL"):
        inspect_package(base.getvalue())


def test_member_too_large_blocked_before_extract():
    p=io.BytesIO()
    with zipfile.ZipFile(p,"w",compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", b"{}")
        z.writestr("plugin.py", b"a" * 120_000)
    with pytest.raises(DeveloperPackageRefused):
        inspect_package(p.getvalue())


def _keypair():
    pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    key = Ed25519PrivateKey.generate()
    seed = key.private_bytes(serialization.Encoding.Raw,
                             serialization.PrivateFormat.Raw,
                             serialization.NoEncryption())
    pub = key.public_key().public_bytes(serialization.Encoding.Raw,
                                         serialization.PublicFormat.Raw)
    return seed, pub


def test_authentic_signature_and_still_review_pending():
    seed,pub=_keypair()
    p=bundle()
    sig=sign_package(p,key_id="trusted_dev",private_seed=seed)
    assert verify_signature(p,sig,trust_roots={"trusted_dev":pub})=="trusted_dev"
    r=evaluate_candidate(p,signature=sig,trust_roots={"trusted_dev":pub})
    assert r.publisher_key_id=="trusted_dev"
    assert "TRUSTED_PUBLISHER_SIGNATURE_VALID" in r.checks
    assert "PUBLISHER_SIGNATURE_MISSING" not in r.blockers
    assert not r.approved_for_execution and not r.approved_for_public_distribution


def test_wrong_key_signature_revocation_and_key_rotation():
    seed,pub=_keypair()
    _,other_pub=_keypair()
    p=bundle()
    signature=sign_package(p,key_id="alice",private_seed=seed)
    with pytest.raises(CertificationRefused,match="NOT_TRUSTED"):
        verify_signature(p,signature,trust_roots={})
    with pytest.raises(CertificationRefused,match="NOT_TRUSTED"):
        verify_signature(p,signature,trust_roots={"alice":pub},revoked_key_ids=frozenset({"alice"}))
    with pytest.raises(CertificationRefused,match="VERIFICATION_FAILED"):
        verify_signature(p,signature,trust_roots={"alice":other_pub})
    with pytest.raises(CertificationRefused,match="TRUST_ROOTS_REQUIRED"):
        evaluate_candidate(p,signature=signature)


def test_signature_does_not_cover_modified_artifact():
    seed,pub=_keypair()
    original=bundle()
    sig=sign_package(original,key_id="alice",private_seed=seed)
    altered=_DECL | {"core_version":"0.2.0"}
    newer=build_package(altered,_SOURCE)
    with pytest.raises(CertificationRefused,match="ARTIFACT_MISMATCH"):
        verify_signature(newer,sig,trust_roots={"alice":pub})


def test_signature_envelope_exact_schema_and_noncanonical_encoding():
    seed,pub=_keypair()
    p=bundle()
    sig=sign_package(p,key_id="alice",private_seed=seed)
    d=json.loads(sig)
    d["extra"]="none"
    with pytest.raises(CertificationRefused,match="SCHEMA"):
        verify_signature(p,_wire(d),trust_roots={"alice":pub})
    with pytest.raises(CertificationRefused,match="SCHEMA"):
        verify_signature(p,json.dumps(json.loads(sig),indent=2).encode(),trust_roots={"alice":pub})


def test_trust_root_wrong_size_and_signing_seed_invalid():
    seed,pub=_keypair()
    p=bundle()
    signature=sign_package(p,key_id="alice",private_seed=seed)
    with pytest.raises(CertificationRefused,match="TRUST_ROOT_INVALID"):
        verify_signature(p,signature,trust_roots={"alice":pub[:8]})
    with pytest.raises(CertificationRefused,match="SIGNER_ID_OR_KEY_INVALID"):
        sign_package(p,key_id="alice",private_seed=b"tiny")


def test_template_json_protocol_matches_stage4_parser_without_host_import():
    from datetime import UTC, datetime, timedelta
    from decimal import Decimal as D
    from naseri_markets.contracts import Instrument, Market
    from naseri_markets.core_api_v1 import (
        ClosedCandle, CoreBinding, CoreEventType, CoreInput, DataOrigin,
        _canonical, content_digest,
    )
    from naseri_markets.secure_plugin_runtime_v1 import parse_core_result
    manifest=inspect_package(bundle()).manifest
    t=datetime(2026,10,12,0,tzinfo=UTC)
    binding=CoreBinding("inst_a", "binding_a",
                        Instrument(Market.CRYPTO, "fixture_provider", "ABCUSD", "UTC", "USD"),"15m")
    bars=tuple(ClosedCandle(t+timedelta(minutes=15*i),t+timedelta(minutes=15*(i+1)),
                            D("100"),D("102"),D("98"),D("100"),D("10")) for i in range(2))
    inp=CoreInput(manifest.core_id,manifest.core_version,binding,
                  CoreEventType.CLOSED_CANDLE,bars[-1].close_at,DataOrigin.SYNTHETIC,
                  "fixture_source",bars)
    event=_canonical(inp)
    request={"abi_major":1,"abi_minor":0,"manifest_digest":content_digest(manifest),
             "input_digest":inp.input_digest,"event":event}
    # Deliberately run only the known, checked-in static example, not a submitted package.
    proc=subprocess.run([sys.executable,"-I","-S",str(_EXAMPLE/"core_template_v1.py")],
                        input=_wire(request),capture_output=True,timeout=5,check=True)
    result=parse_core_result(proc.stdout,manifest,inp)
    assert len(result.decisions)==1 and result.decisions[0].kind.value=="no_setup"


def test_cli_pack_inspect_no_execution(tmp_path):
    env=os.environ.copy()
    env["PYTHONPATH"]=str(_ROOT)
    output=tmp_path/"candidate.zip"
    p=subprocess.run([sys.executable,"-m","scripts.mmt_core_sdk_v1","pack",
                      "--manifest",str(_EXAMPLE/"manifest_v1.json"),
                      "--source",str(_EXAMPLE/"core_template_v1.py"),
                      "--output",str(output)],cwd=_ROOT,env=env,capture_output=True,text=True,timeout=5)
    assert p.returncode==0,p.stderr
    assert output.read_bytes()==bundle()
    q=subprocess.run([sys.executable,"-m","scripts.mmt_core_sdk_v1","inspect",
                      "--bundle",str(output)],cwd=_ROOT,env=env,capture_output=True,text=True,timeout=5)
    assert q.returncode==0,q.stderr
    report=json.loads(q.stdout)
    assert report["status"]=="REVIEW_REQUIRED_NONPRODUCTION"
    assert report["approved_for_execution"] is False


def test_ast_cannot_contain_public_runtime_side_effects():
    base=Path(__file__).resolve().parents[2]/"naseri_markets"
    for name in ("core_developer_sdk_v1.py","core_certification_v1.py"):
        source=(base/name).read_text()
        ast.parse(source)
        assert "import requests" not in source
        assert "import socket" not in source
        assert "telegram.send" not in source
