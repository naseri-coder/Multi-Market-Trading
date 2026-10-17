"""Synthetic offline stable-artifact cryptography + negative policy acceptance."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import stat
import zipfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from scripts import mmt_v040_signed_artifact_preflight_v1 as audit


def j(obj):
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True).encode() + b"\n")


def built_wheel(mods=None, metadata=None, scripts=None, corrupt_record=False):
    mods = mods or {
        "naseri_markets/platform_cli.py": b"# inert synthetic public CLI\n",
        "naseri_markets/platform_version_policy_v1.py": b"# exact offline version gate\n",
    }
    metadata = (metadata if metadata is not None else
                ("Metadata-Version: 2.4\nName: multi-market-trading\n"
                 "Version: 0.4.0\nRequires-Python: >=3.12,<3.13\n"
                 + "".join(
                     "Requires-Dist: " + dep + '; extra == "' + extra + '"\n'
                     for extra, deps in audit._ALLOWED_REQUIREMENTS.items()
                     for dep in sorted(deps)
                 ))).encode()
    commands = scripts if scripts is not None else audit._ALLOWED_COMMANDS
    entries = "[console_scripts]\n" + "".join(f"{k} = {v}\n" for k,v in commands.items())
    vals = dict(mods)
    vals.update({
        audit.DIST+"METADATA": metadata,
        audit.DIST+"WHEEL": b"Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        audit.DIST+"entry_points.txt": entries.encode(),
        audit.DIST+"top_level.txt": b"naseri_markets\n",
    })
    lines=[]
    for k,v in vals.items():
        h=base64.urlsafe_b64encode(hashlib.sha256(v).digest()).rstrip(b"=").decode()
        lines.append((k,"sha256="+h,str(len(v))))
    lines.append((audit.DIST+"RECORD", "", ""))
    if corrupt_record:lines[0]=(lines[0][0],"sha256="+"a"*43,lines[0][2])
    with io.StringIO() as w:
        import csv
        csv.writer(w,lineterminator="\n").writerows(lines)
        record=w.getvalue().encode()
    vals[audit.DIST+"RECORD"]=record
    b=io.BytesIO()
    with zipfile.ZipFile(b,"w",zipfile.ZIP_DEFLATED) as z:
        for path, data in vals.items():
            z.writestr(path,data)
    return b.getvalue(),record


@pytest.fixture
def setup(tmp_path,monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION","1")
    monkeypatch.delenv("MMT_PRODUCTION",raising=False)
    private=tmp_path / "private"
    private.mkdir(mode=0o700)
    key=Ed25519PrivateKey.generate()
    public=key.public_key()
    pem=public.public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
    spki=public.public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
    fingerprint=hashlib.sha256(spki).hexdigest()
    (private/"signer.pem").write_bytes(pem)
    wheel,record=built_wheel()
    path=private/audit.WHEEL_NAME
    path.write_bytes(wheel)
    manifest={
        "schema":1,"distribution":audit.DIST_NAME,"version":"0.4.0",
        "purpose":"offline-paper-release-only",
        "source_commit":"c"*40,"source_date_epoch":1792100000,
        "wheel_filename":audit.WHEEL_NAME,
        "wheel_sha256":hashlib.sha256(wheel).hexdigest(),
        "wheel_size":len(wheel),
        "wheel_record_sha256":hashlib.sha256(record).hexdigest(),
    }
    policy={
        "schema":1,"revision":1,"active_signers":[fingerprint],"revoked_signers":[],
        "min_source_date_epoch":1792000000,
    }
    def rewrite():
        raw=j(manifest)
        (private/"manifest.json").write_bytes(raw)
        (private/"signature.bin").write_bytes(key.sign(audit.DOMAIN+raw))
        rawpolicy=j(policy)
        (private/"policy.json").write_bytes(rawpolicy)
        return {"manifest":private/"manifest.json", "signature":private/"signature.bin",
                "wheel":path,"trusted_public_key":private/"signer.pem",
                "trusted_public_key_spki_sha256":fingerprint,
                "policy":private/"policy.json",
                "expected_policy_sha256":hashlib.sha256(rawpolicy).hexdigest(),
                "expected_manifest_sha256":hashlib.sha256(raw).hexdigest(),
                "expected_source_commit":"c"*40}
    return private,key,manifest,policy,rewrite


def test_signed_stable_artifact_positive_is_readonly_and_no_release_grant(setup):
    private,_,_,_,rewrite=setup
    values=rewrite()
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in private.iterdir()}
    a=audit.verify(**values)
    assert a["record_verified"] and a["members_verified"]==7
    assert a["wheel_sha256"]==hashlib.sha256(values["wheel"].read_bytes()).hexdigest()
    for name in ("writes_performed","install_authorized","public_release_authorized",
                 "live_trading_authorized","telegram_publication_authorized"):
        assert a[name] is False
    assert before=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in private.iterdir()}


@pytest.mark.parametrize("value",("", "0", "false", "1"))
def test_explicit_production_denied_even_false_values(setup,monkeypatch,value):
    _,_,_,_,rewrite=setup
    v=rewrite();monkeypatch.setenv("MMT_PRODUCTION",value)
    with pytest.raises(audit.StableArtifactRefused,match="V040_NONPRODUCTION_REQUIRED"):
        audit.verify(**v)


def test_missing_explicit_nonproduction_denied(setup,monkeypatch):
    _,_,_,_,rewrite=setup;v=rewrite();monkeypatch.delenv("MMT_NONPRODUCTION")
    with pytest.raises(audit.StableArtifactRefused,match="V040_NONPRODUCTION_REQUIRED"):
        audit.verify(**v)


def test_wrong_external_manifest_pin_denied(setup):
    _,_,_,_,rewrite=setup;v=rewrite();v["expected_manifest_sha256"]="0"*64
    with pytest.raises(audit.StableArtifactRefused,match="V040_MANIFEST_EXTERNAL_PIN_MISMATCH"):
        audit.verify(**v)


def test_wrong_external_policy_pin_denied(setup):
    _,_,_,_,rewrite=setup;v=rewrite();v["expected_policy_sha256"]="0"*64
    with pytest.raises(audit.StableArtifactRefused,match="V040_POLICY_EXTERNAL_PIN_MISMATCH"):
        audit.verify(**v)


def test_old_rc_signature_domain_denied(setup):
    private,key,_,_,rewrite=setup;v=rewrite()
    raw=v["manifest"].read_bytes()
    v["signature"].write_bytes(key.sign(b"MMT-R37-OFFLINE-PREVIEW-MANIFEST-V1\n"+raw))
    with pytest.raises(audit.StableArtifactRefused,match="V040_SIGNATURE_VERIFICATION_FAILED"):
        audit.verify(**v)


def test_forged_signature_denied(setup):
    _,_,_,_,rewrite=setup;v=rewrite()
    v["signature"].write_bytes(b"x"*64)
    with pytest.raises(audit.StableArtifactRefused,match="V040_SIGNATURE_VERIFICATION_FAILED"):
        audit.verify(**v)


def test_signer_revoked_denied_even_if_signed(setup):
    _,_,_,policy,rewrite=setup;v=rewrite()
    policy["revoked_signers"]=[v["trusted_public_key_spki_sha256"]]
    policy["active_signers"]=[]
    v=rewrite()
    with pytest.raises(audit.StableArtifactRefused,match="V040_SIGNER_REVOKED"):
        audit.verify(**v)


def test_signer_absent_from_trust_allowlist(setup):
    _,_,_,policy,rewrite=setup;policy["active_signers"]=[];v=rewrite()
    with pytest.raises(audit.StableArtifactRefused,match="V040_SIGNER_NOT_TRUSTED"):
        audit.verify(**v)


def test_signature_public_key_mismatch(setup):
    private,_,_,_,rewrite=setup;v=rewrite()
    other=Ed25519PrivateKey.generate().public_key()
    v["trusted_public_key"].write_bytes(other.public_bytes(
        serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
    with pytest.raises(audit.StableArtifactRefused,match="V040_SIGNER_FINGERPRINT_MISMATCH"):
        audit.verify(**v)


def test_revocation_policy_stale_replay_denied(setup):
    _,_,_,policy,rewrite=setup;policy["min_source_date_epoch"]=1792100001
    v=rewrite()
    with pytest.raises(audit.StableArtifactRefused,match="V040_STALE_MANIFEST_DENIED"):
        audit.verify(**v)


@pytest.mark.parametrize("version",("0.4.0rc1","4.0.0","0.4.1"))
def test_signed_wrong_manifest_version_denied(setup,version):
    _,_,manifest,_,rewrite=setup;manifest["version"]=version;v=rewrite()
    with pytest.raises(audit.StableArtifactRefused,match="V040_MANIFEST_VALUE_INVALID"):
        audit.verify(**v)


def test_duplicate_manifest_json_key_denied(setup):
    _,_,_,_,rewrite=setup;v=rewrite();raw=v["manifest"].read_bytes()
    tampered=raw[:-2]+b',"schema":1}\n'
    v["manifest"].write_bytes(tampered)
    v["expected_manifest_sha256"]=hashlib.sha256(tampered).hexdigest()
    with pytest.raises(audit.StableArtifactRefused,match="V040_DUPLICATE_JSON_KEY"):
        audit.verify(**v)


def test_noncanonical_policy_denied(setup):
    _,_,_,_,rewrite=setup;v=rewrite();raw=v["policy"].read_bytes()
    bad=raw.replace(b',',b', ',1)
    v["policy"].write_bytes(bad)
    v["expected_policy_sha256"]=hashlib.sha256(bad).hexdigest()
    with pytest.raises(audit.StableArtifactRefused,match="V040_JSON_NONCANONICAL"):
        audit.verify(**v)


def test_source_commit_swap_denied(setup):
    _,_,_,_,rewrite=setup;v=rewrite();v["expected_source_commit"]="d"*40
    with pytest.raises(audit.StableArtifactRefused,match="V040_SOURCE_COMMIT_MISMATCH"):
        audit.verify(**v)


def test_wheel_tampered_denied(setup):
    _,_,_,_,rewrite=setup;v=rewrite();v["wheel"].write_bytes(b"0"*500)
    with pytest.raises(audit.StableArtifactRefused,match="V040_WHEEL_BYTES_MISMATCH"):
        audit.verify(**v)


def test_wheel_wrong_name_denied(setup,tmp_path):
    _,_,_,_,rewrite=setup;v=rewrite();other=tmp_path/"multi_market_trading-0.4.0rc1-py3-none-any.whl"
    other.write_bytes(v["wheel"].read_bytes());v["wheel"]=other
    with pytest.raises(audit.StableArtifactRefused,match="V040_STABLE_WHEEL_FILENAME_REQUIRED"):
        audit.verify(**v)


def test_wheel_metadata_old_release_rejected_even_with_valid_signature(setup):
    _,_,manifest,_,rewrite=setup;v=rewrite()
    wheel,record=built_wheel(metadata=("Metadata-Version: 2.4\nName: multi-market-trading\n"
                                      "Version: 0.4.0rc1\nRequires-Python: >=3.12,<3.13\n"))
    v["wheel"].write_bytes(wheel)
    manifest["wheel_size"]=len(wheel)
    manifest["wheel_sha256"]=hashlib.sha256(wheel).hexdigest()
    manifest["wheel_record_sha256"]=hashlib.sha256(record).hexdigest()
    v=rewrite()
    with pytest.raises(audit.StableArtifactRefused,match="V040_WHEEL_IDENTITY_INVALID"):
        audit.verify(**v)


def test_wheel_record_digest_tampered_detected(setup):
    _,_,manifest,_,rewrite=setup;v=rewrite()
    wheel,record=built_wheel(corrupt_record=True)
    v["wheel"].write_bytes(wheel)
    manifest.update(wheel_size=len(wheel),wheel_sha256=hashlib.sha256(wheel).hexdigest(),
                    wheel_record_sha256=hashlib.sha256(record).hexdigest())
    v=rewrite()
    with pytest.raises(audit.StableArtifactRefused,match="V040_RECORD_MEMBER_HASH_INVALID"):
        audit.verify(**v)


def test_forbidden_wheel_member_even_validly_signed_denied(setup):
    _,_,manifest,_,rewrite=setup;v=rewrite()
    wheel,record=built_wheel(mods={
        "naseri_markets/platform_cli.py":b"hi\n",
        "naseri_markets/platform_version_policy_v1.py":b"hi\n",
        "naseri_markets/../private_nyfr_core.py":b"stolen\n",
    })
    v["wheel"].write_bytes(wheel)
    manifest.update(wheel_size=len(wheel),wheel_sha256=hashlib.sha256(wheel).hexdigest(),
                    wheel_record_sha256=hashlib.sha256(record).hexdigest())
    v=rewrite()
    with pytest.raises(audit.StableArtifactRefused,match="V040_WHEEL_MEMBER_UNSAFE"):
        audit.verify(**v)


def test_signed_zip_symlink_member_denied(setup):
    _,_,manifest,_,rewrite=setup;v=rewrite()
    wheel, record=built_wheel()
    new=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(wheel)) as orig,zipfile.ZipFile(new,'w') as out:
        for member in orig.infolist():out.writestr(member,orig.read(member))
        z=zipfile.ZipInfo("naseri_markets/backdoor.py")
        z.create_system=3
        z.external_attr=(stat.S_IFLNK|0o777)<<16
        out.writestr(z,"/etc/passwd")
    wheel=new.getvalue()
    v["wheel"].write_bytes(wheel)
    manifest.update(wheel_size=len(wheel),wheel_sha256=hashlib.sha256(wheel).hexdigest())
    v=rewrite()
    with pytest.raises(audit.StableArtifactRefused,match="V040_WHEEL_MEMBER_UNSAFE"):
        audit.verify(**v)


def test_symlink_manifest_refused(setup):
    private,_,_,_,rewrite=setup;v=rewrite()
    alias=private/"manifest-link.json"
    alias.symlink_to(v["manifest"])
    v["manifest"]=alias
    with pytest.raises(audit.StableArtifactRefused,match="V040_ABSOLUTE_REGULAR_FILE_REQUIRED"):
        audit.verify(**v)


def test_cli_returns_no_privileges(setup,capsys,monkeypatch):
    private,_,_,_,rewrite=setup;v=rewrite()
    argv=[]
    for arg in ("manifest","signature","wheel","trusted_public_key","policy"):
        argv.extend(["--"+arg.replace("_","-"),str(v[arg])])
    for arg in ("trusted_public_key_spki_sha256","expected_policy_sha256",
                "expected_manifest_sha256","expected_source_commit"):
        argv.extend(["--"+arg.replace("_","-"),v[arg]])
    assert audit.main(argv)==0
    result=json.loads(capsys.readouterr().out)
    assert result["live_trading_authorized"] is False
    assert result["install_authorized"] is False


def test_optional_extra_marker_substring_forgery_rejected(setup):
    _,_,manifest,_,rewrite=setup
    forged=("Metadata-Version: 2.4\nName: multi-market-trading\n"
            "Version: 0.4.0\nRequires-Python: >=3.12,<3.13\n"
            'Requires-Dist: requests==1; python_version >= "3.12" '
            'and extra == "telegram-admin"\n')
    wheel,record=built_wheel(metadata=forged)
    v=rewrite();v["wheel"].write_bytes(wheel)
    manifest.update(wheel_size=len(wheel),wheel_sha256=hashlib.sha256(wheel).hexdigest(),
                    wheel_record_sha256=hashlib.sha256(record).hexdigest())
    v=rewrite()
    with pytest.raises(audit.StableArtifactRefused,
                       match="V040_WHEEL_BASE_DEPENDENCY_INVALID"):
        audit.verify(**v)


def test_signed_unreviewed_dependency_extra_rejected(setup):
    _,_,manifest,_,rewrite=setup
    bad=("Metadata-Version: 2.4\nName: multi-market-trading\n"
         "Version: 0.4.0\nRequires-Python: >=3.12,<3.13\n"
         'Requires-Dist: requests==1; extra == "brooks-offline"\n')
    wheel,record=built_wheel(metadata=bad)
    v=rewrite();v["wheel"].write_bytes(wheel)
    manifest.update(wheel_size=len(wheel),wheel_sha256=hashlib.sha256(wheel).hexdigest(),
                    wheel_record_sha256=hashlib.sha256(record).hexdigest())
    v=rewrite()
    with pytest.raises(audit.StableArtifactRefused,
                       match="V040_WHEEL_BASE_DEPENDENCY_INVALID"):
        audit.verify(**v)


def test_duplicate_version_header_rejected(setup):
    _,_,manifest,_,rewrite=setup
    bad=("Metadata-Version: 2.4\nName: multi-market-trading\n"
         "Version: 0.4.0\nVersion: 0.4.0rc1\n"
         "Requires-Python: >=3.12,<3.13\n")
    wheel,record=built_wheel(metadata=bad)
    v=rewrite();v["wheel"].write_bytes(wheel)
    manifest.update(wheel_size=len(wheel),wheel_sha256=hashlib.sha256(wheel).hexdigest(),
                    wheel_record_sha256=hashlib.sha256(record).hexdigest())
    v=rewrite()
    with pytest.raises(audit.StableArtifactRefused,
                       match="V040_WHEEL_IDENTITY_INVALID"):
        audit.verify(**v)


def test_private_engine_filename_denied_even_when_signed(setup):
    _,_,manifest,_,rewrite=setup
    wheel,record=built_wheel(mods={
        "naseri_markets/platform_cli.py":b"hi\n",
        "naseri_markets/platform_version_policy_v1.py":b"hi\n",
        "naseri_markets/private_nyfr_core.py":b"private\n",
    })
    values=rewrite();values["wheel"].write_bytes(wheel)
    manifest.update(wheel_size=len(wheel),wheel_sha256=hashlib.sha256(wheel).hexdigest(),
                    wheel_record_sha256=hashlib.sha256(record).hexdigest())
    values=rewrite()
    with pytest.raises(audit.StableArtifactRefused,match="V040_WHEEL_MEMBER_UNSAFE"):
        audit.verify(**values)


@pytest.mark.parametrize("requires_python", (
    ">=3.12,<3.13", "<3.13,>=3.12",
))
def test_exact_python_range_in_both_equivalent_metadata_orders(requires_python):
    base_metadata = (
        "Metadata-Version: 2.4\nName: multi-market-trading\n"
        "Version: 0.4.0\n"
        f"Requires-Python: {requires_python}\n"
        + "".join(
            "Requires-Dist: " + dep + '; extra == "' + extra + '"\n'
            for extra, deps in audit._ALLOWED_REQUIREMENTS.items()
            for dep in sorted(deps)
        )
    )
    wheel, record = built_wheel(metadata=base_metadata)
    assert audit._wheel(wheel, hashlib.sha256(record).hexdigest())["record_verified"] is True


@pytest.mark.parametrize("requires_python", (
    ">=3.11,<3.13", ">=3.12", "<3.14,>=3.12", ">=3.12,<3.13,>=3.11",
))
def test_changed_or_extra_python_range_remains_refused(requires_python):
    bad = (
        "Metadata-Version: 2.4\nName: multi-market-trading\n"
        "Version: 0.4.0\n"
        f"Requires-Python: {requires_python}\n"
        + "".join(
            "Requires-Dist: " + dep + '; extra == "' + extra + '"\n'
            for extra, deps in audit._ALLOWED_REQUIREMENTS.items()
            for dep in sorted(deps)
        )
    )
    wheel, record = built_wheel(metadata=bad)
    with pytest.raises(audit.StableArtifactRefused, match="V040_WHEEL_IDENTITY_INVALID"):
        audit._wheel(wheel, hashlib.sha256(record).hexdigest())
