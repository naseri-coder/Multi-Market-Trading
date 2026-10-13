"""Universal artifact intake: 15 recognised formats, zero execution rights."""
from __future__ import annotations

import io
import json
import zipfile

import pytest

from naseri_markets.core_developer_sdk_v1 import build_package
from naseri_markets.universal_artifact_intake_v1 import (
    ArtifactRole,
    InspectionLevel,
    IntakeRefused,
    inspect_artifact,
    supported_extensions,
)

CANDIDATES = {
    "algo.py": b"import json\nprint(json.dumps({'ok': True}))\n",
    "signal.json": b'{"version":1,"name":"test"}',
    "prices.csv": b"time,open,high,low,close\n2026-10-13T10:00Z,10,12,9,11\n",
    "candles.parquet": b"PAR1abc" + (3).to_bytes(4, "little") + b"PAR1",
    "algo.js": b"export function evaluate(x) { return x; }\n",
    "algo.ts": b"export const evaluate = (x: number): number => x;\n",
    "algo.mq4": b"int OnInit() { return 0; }\n",
    "algo.mq5": b"int OnInit() { return 0; }\n",
    "algo.ex5": b"\x99\x10\xfe\xedproprietary-bytes-placeholder",
    "algo.pine": b"//@version=5\nstrategy('offline')\n",
    "algo.so": b"\x7fELF\x02" + bytes(16),
    "algo.wasm": b"\x00asm\x01\x00\x00\x00",
}


def _pe() -> bytes:
    data = bytearray(256)
    data[:2] = b"MZ"
    data[0x3c:0x40] = (128).to_bytes(4, "little")
    data[128:132] = b"PE\x00\x00"
    return bytes(data)


def _zip() -> bytes:
    declaration = {
        "schema_version": 1,
        "abi_major": 1,
        "abi_minor": 0,
        "core_id": "sdk_test_core",
        "core_version": "1.0",
        "entrypoint": "plugin.py",
        "minimum_closed_candles": 2,
        "supported_markets": ["crypto"],
        "accepted_events": ["closed_candle"],
        "setups": [{
            "setup_id": "test_only",
            "description": "Intent-free fixture",
            "may_manage_stop": False,
        }],
    }
    return build_package(declaration, b"import json\nimport sys\nprint(json.dumps({}))\n")


CANDIDATES.update({"algo.dll": _pe(), "algo.exe": _pe(), "algo.zip": _zip()})


def test_exact_supported_types() -> None:
    assert set(supported_extensions()) == {
        ".py", ".json", ".zip", ".csv", ".parquet", ".js", ".ts",
        ".mq4", ".mq5", ".ex5", ".pine", ".dll", ".so", ".exe",
        ".wasm",
    }


@pytest.mark.parametrize("name", sorted(CANDIDATES))
def test_each_format_recognised_with_zero_authorization(name: str) -> None:
    raw = CANDIDATES[name]
    status = inspect_artifact(name, raw)
    assert status.extension == "." + name.rsplit(".", 1)[-1]
    assert status.filename == name
    assert status.byte_length == len(raw)
    assert len(status.sha256) == 64
    assert status.status == "UNTRUSTED_ARTIFACT_REVIEW_REQUIRED"
    assert status.proposed_adapter
    assert status.executable is False
    assert status.adapter_installed is False
    assert status.market_data_authenticated is False
    assert status.paper_enabled is False
    assert status.live_enabled is False
    assert status.telegram_enabled is False


@pytest.mark.parametrize("extension", [".csv", ".parquet"])
def test_data_files_not_engines(extension: str) -> None:
    name = "candles" + extension if extension == ".parquet" else "prices.csv"
    result = inspect_artifact(name, CANDIDATES[name])
    assert result.role is ArtifactRole.DATA
    assert result.inspection_level in {
        InspectionLevel.CSV_STRUCTURE, InspectionLevel.PARQUET_CONTAINER,
    }


def test_recognised_python_static_warning_not_safety_certificate() -> None:
    result = inspect_artifact("test.py", b"import os\nos.system('echo test')\n")
    assert "DISALLOWED_IMPORT" in result.findings
    assert result.executable is False


@pytest.mark.parametrize("path", [
    "../bad.py", "/tmp/bad.py", "folder/test.py", "folder\\test.py",
    ".hidden.py", "", "a"*150 + ".py", "malicious.py\nx",
])
def test_unsafe_names_denied(path: str) -> None:
    with pytest.raises(IntakeRefused, match="INVALID_ARTIFACT_NAME"):
        inspect_artifact(path, b"print(1)\n")


@pytest.mark.parametrize("filename", ["malware.sh", "module.dylib", "bundle.jar"])
def test_undeclared_extension_denied(filename: str) -> None:
    with pytest.raises(IntakeRefused, match="ARTIFACT_EXTENSION_UNSUPPORTED"):
        inspect_artifact(filename, b"payload")


@pytest.mark.parametrize("name,data", [
    ("x.py", b"def bad("),
    ("x.json", b'{"a":1,"a":2}'),
    ("x.json", b'{"bad":NaN}'),
    ("x.csv", b"time,price\n1\n"),
    ("x.csv", b"a,a\n1,2\n"),
    ("x.parquet", b"PAR1fakebadPAR1"),
    ("x.js", b"\xff"),
    ("x.ts", b"\x00"),
    ("x.mq4", b"\xfe"),
    ("x.mq5", b"\x00"),
    ("x.pine", b"\xff"),
    ("x.dll", b"MZbad"),
    ("x.exe", b"wrong"),
    ("x.so", b"ELFnotvalid"),
    ("x.wasm", b"\x00asm\x00\x00\x00\x00"),
    ("x.ex5", b"MZ" + bytes(64)),
    ("x.zip", b"PK\x03\x04not-really-archive"),
])
def test_malformed_or_mislabelled_artifacts_rejected(name: str, data: bytes) -> None:
    with pytest.raises(IntakeRefused):
        inspect_artifact(name, data)


def test_zip_does_not_accept_arbitrary_archives() -> None:
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w") as z:
        z.writestr("../escape.py", "print('no')")
    with pytest.raises(IntakeRefused, match="NONCANONICAL_SDK_ARCHIVE"):
        inspect_artifact("candidate.zip", mem.getvalue())


@pytest.mark.parametrize("name", ["x.py", "x.wasm", "x.json", "x.ex5"])
def test_empty_and_oversized_denied(name: str) -> None:
    with pytest.raises(IntakeRefused, match="ARTIFACT_SIZE_INVALID"):
        inspect_artifact(name, b"")
    with pytest.raises(IntakeRefused, match="ARTIFACT_SIZE_INVALID"):
        inspect_artifact(name, b"x" * (8 * 1024 * 1024 + 1))


def test_python_source_limit_matches_existing_sdk() -> None:
    with pytest.raises(IntakeRefused, match="PYTHON_SDK_SOURCE_LIMIT"):
        inspect_artifact("oversized.py", b"#" * 65537)


def test_signature_is_not_execution_authorization() -> None:
    package = inspect_artifact("candidate.ZIP", CANDIDATES["algo.zip"])
    assert package.inspection_level is InspectionLevel.SDK_PACKAGE
    assert package.adapter_installed is False
    assert package.executable is False


def test_pe_structure_not_execution_permission() -> None:
    result = inspect_artifact("stage.EXE", _pe())
    assert result.inspection_level is InspectionLevel.BINARY_MAGIC
    assert result.live_enabled is False


def test_intake_is_pure_and_does_not_write(monkeypatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("unexpected file/network/code execution")

    monkeypatch.setattr("subprocess.run", forbidden)
    monkeypatch.setattr("os.system", forbidden)
    assert inspect_artifact("alpha.js", CANDIDATES["algo.js"]).executable is False
