"""NATIVE-A1 bounded PE/ELF review tests; synthetic bytes are NEVER run."""
from __future__ import annotations

import hashlib
import os
import socket
import subprocess

import pytest

from naseri_markets.native_a1_inert_binary_preflight import (
    NativeA1Refused,
    inspect_native_bytes,
    inspect_native_file,
)
from naseri_markets.runtime_a6_dispatch_fence import (
    RuntimeA6Denied,
    require_worker_launch,
)


@pytest.fixture(autouse=True)
def nonproduction(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def _put(buf: bytearray, offset: int, value: int, width: int) -> None:
    buf[offset:offset + width] = value.to_bytes(width, "little")


def _pe(suffix: str, architecture: str = "x86_64") -> bytes:
    machines = {"x86": (0x14C, 0x10B, 224),
                "x86_64": (0x8664, 0x20B, 240),
                "aarch64": (0xAA64, 0x20B, 240)}
    machine, magic, opt_size = machines[architecture]
    raw = bytearray(1024)
    raw[:2] = b"MZ"
    _put(raw, 0x3C, 0x80, 4)
    raw[0x80:0x84] = b"PE\x00\x00"
    _put(raw, 0x84, machine, 2)
    _put(raw, 0x86, 1, 2)
    _put(raw, 0x94, opt_size, 2)
    _put(raw, 0x96, 0x0002 | (0x2000 if suffix == ".dll" else 0), 2)
    opt = 0x98
    _put(raw, opt, magic, 2)
    _put(raw, opt + 32, 0x1000, 4)
    _put(raw, opt + 36, 0x200, 4)
    _put(raw, opt + 56, 0x2000, 4)
    _put(raw, opt + 60, 0x200, 4)
    section = opt + opt_size
    raw[section:section + 5] = b".text"
    _put(raw, section + 8, 0x100, 4)
    _put(raw, section + 12, 0x1000, 4)
    _put(raw, section + 16, 0x200, 4)
    _put(raw, section + 20, 0x200, 4)
    _put(raw, section + 36, 0x60000020, 4)
    return bytes(raw)


def _elf(architecture: str = "x86_64") -> bytes:
    machine, width = {"x86": (3, 32), "x86_64": (62, 64),
                      "aarch64": (183, 64)}[architecture]
    raw = bytearray(512)
    raw[:4] = b"\x7fELF"
    raw[4:7] = bytes((1 if width == 32 else 2, 1, 1))
    _put(raw, 16, 3, 2)  # ET_DYN; might also be a PIE executable!
    _put(raw, 18, machine, 2)
    _put(raw, 20, 1, 4)
    if width == 64:
        _put(raw, 32, 64, 8)
        _put(raw, 52, 64, 2)
        _put(raw, 54, 56, 2)
        _put(raw, 56, 1, 2)
        _put(raw, 64, 1, 4)  # PT_LOAD
        _put(raw, 72, 0x100, 8)
        _put(raw, 96, 0x40, 8)
        _put(raw, 104, 0x40, 8)
        _put(raw, 112, 0x1000, 8)
    else:
        _put(raw, 28, 52, 4)
        _put(raw, 40, 52, 2)
        _put(raw, 42, 32, 2)
        _put(raw, 44, 1, 2)
        _put(raw, 52, 1, 4)
        _put(raw, 56, 0x100, 4)
        _put(raw, 68, 0x40, 4)
        _put(raw, 72, 0x40, 4)
        _put(raw, 80, 0x1000, 4)
    return bytes(raw)


def _inspect(name: str, raw: bytes, **override):
    opts = dict(expected_sha256=hashlib.sha256(raw).hexdigest(),
                operator_ack=True)
    opts.update(override)
    return inspect_native_bytes(name, raw, **opts)


@pytest.mark.parametrize(("name", "raw", "arch", "bits", "fmt"), [
    ("lib.dll", _pe(".dll"), "x86_64", 64, "PE"),
    ("host.exe", _pe(".exe", "x86"), "x86", 32, "PE"),
    ("library.dll", _pe(".dll", "aarch64"), "aarch64", 64, "PE"),
    ("host.exe", _pe(".exe"), "x86_64", 64, "PE"),
    ("lib.so", _elf(), "x86_64", 64, "ELF"),
    ("plugin.so", _elf("x86"), "x86", 32, "ELF"),
    ("plugin.so", _elf("aarch64"), "aarch64", 64, "ELF"),
])
def test_structured_header_review_never_implies_safety(name, raw, arch, bits, fmt):
    r = _inspect(name, raw)
    assert r.filename == name
    assert r.sha256 == hashlib.sha256(raw).hexdigest()
    assert r.byte_length == len(raw)
    assert r.container_format == fmt
    assert r.architecture == arch
    assert r.address_width == bits
    assert r.endianness == "little"
    assert r.mapped_regions == 1
    assert r.status == "NATIVE_A1_HEADER_STRUCTURE_ONLY_UNTRUSTED"
    assert not r.full_format_validated
    assert not r.code_signature_verified
    assert not r.publisher_authenticated
    assert not r.dependencies_verified
    assert not r.binary_safe_from_malware
    assert not r.isolated_host_certified
    assert not r.executed_in_sandbox
    assert not r.runtime_adapter_installed
    assert not r.core_api_behavior_verified
    assert not r.paper_strategy_executed
    assert not r.broker_authorized
    assert not r.telegram_authorized
    assert not r.worker_execution_authorized
    assert not r.quarantine_release_authorized


@pytest.mark.parametrize(("suffix", "content"), [
    (".dll", _pe(".dll")), (".exe", _pe(".exe")), (".so", _elf()),
])
def test_local_absolute_file_readonly_no_other_artifacts(tmp_path, suffix, content):
    path = tmp_path / ("binary" + suffix)
    path.write_bytes(content)
    initial = path.stat()
    result = inspect_native_file(
        path, expected_sha256=hashlib.sha256(content).hexdigest(),
        operator_ack=True,
    )
    assert result.filename == path.name
    assert result.sha256 == hashlib.sha256(content).hexdigest()
    assert path.read_bytes() == content
    assert path.stat().st_mtime_ns == initial.st_mtime_ns
    assert sorted(x.name for x in tmp_path.iterdir()) == [path.name]


@pytest.mark.parametrize(("filename", "raw", "error"), [
    ("foo.dll", _pe(".exe"), "PE_TYPE_OR_MACHINE_INVALID"),
    ("foo.exe", _pe(".dll"), "PE_TYPE_OR_MACHINE_INVALID"),
    ("foo.so", _pe(".exe"), "ELF_IDENTITY_INVALID"),
    ("foo.exe", _elf(), "PE_DOS_HEADER_INVALID"),
    ("foo.dll", b"MZ", "PE_DOS_HEADER_INVALID"),
    ("foo.so", b"\x7fELF", "ELF_IDENTITY_INVALID"),
])
def test_mislabeled_or_truncated_binary_refused(filename, raw, error):
    with pytest.raises(NativeA1Refused, match=error):
        _inspect(filename, raw)


@pytest.mark.parametrize(("file", "raw"), [
    ("x.txt", _pe(".exe")), ("x.sys", _pe(".dll")),
    ("x.dylib", _elf()), ("x.so.1", _elf()),
])
def test_extension_allowlist_refused(file, raw):
    with pytest.raises(NativeA1Refused, match="NATIVE_A1_UNSUPPORTED_NATIVE_EXTENSION"):
        _inspect(file, raw)


@pytest.mark.parametrize("bad", [
    "../x.exe", "dir/x.dll", "dir\\x.so", "", ".exe", "bad.exe\nx",
])
def test_unsafe_filename_refused(bad):
    with pytest.raises(NativeA1Refused, match="NATIVE_A1_PINNED_BINARY_AND_NAME_REQUIRED"):
        _inspect(bad, _pe(".exe"))


@pytest.mark.parametrize(("offset", "width", "value", "err"), [
    (0x3C, 4, 0x7FFFFFF0, "PE_SIGNATURE_INVALID"),
    (0x84, 2, 0xFFFF, "PE_TYPE_OR_MACHINE_INVALID"),
    (0x86, 2, 0, "PE_TYPE_OR_MACHINE_INVALID"),
    (0x94, 2, 0, "PE_OPTIONAL_HEADER_INVALID"),
    (0x98, 2, 0x10B, "PE_BITNESS_INVALID"),
    (0x98 + 60, 4, 0, "PE_SECTION_TABLE_INVALID"),
    (0x98 + 56, 4, 0, "PE_SECTION_TABLE_INVALID"),
    (0x98 + 240 + 20, 4, 0xFFFF0000, "PE_SECTION_OUT_OF_FILE"),
])
def test_pe_header_malformed_fields_fail_closed(offset, width, value, err):
    data = bytearray(_pe(".exe"))
    _put(data, offset, value, width)
    with pytest.raises(NativeA1Refused, match=err):
        _inspect("test.exe", bytes(data))


@pytest.mark.parametrize(("offset", "width", "value", "err"), [
    (16, 2, 2, "ELF_TYPE_OR_ARCH_INVALID"),  # ET_EXEC is not a shared object
    (18, 2, 0xFFFF, "ELF_TYPE_OR_ARCH_INVALID"),
    (56, 2, 0, "ELF_PROGRAM_TABLE_INVALID"),
    (56, 2, 0xFFFF, "ELF_PROGRAM_TABLE_INVALID"),
    (72, 8, 0xFFFFFFFFFFFFFF00, "ELF_SEGMENT_OUT_OF_FILE"),
    (96, 8, 0xFFFFFFFFFFFF0000, "ELF_SEGMENT_OUT_OF_FILE"),
    (104, 8, 0x10, "ELF_SEGMENT_OUT_OF_FILE"),
    (112, 8, 3, "ELF_SEGMENT_OUT_OF_FILE"),
    (64, 4, 0, "ELF_NO_LOAD_SEGMENT"),
])
def test_elf_invalid_program_table_and_ranges_rejected(offset, width, value, err):
    b = bytearray(_elf())
    _put(b, offset, value, width)
    with pytest.raises(NativeA1Refused, match=err):
        _inspect("test.so", bytes(b))


def test_no_false_endianness_or_unsupported_architecture():
    b = bytearray(_elf())
    b[5] = 2
    with pytest.raises(NativeA1Refused, match="ELF_IDENTITY_INVALID"):
        _inspect("test.so", bytes(b))
    b = bytearray(_elf())
    b[4] = 1
    with pytest.raises(NativeA1Refused, match="ELF_TYPE_OR_ARCH_INVALID"):
        _inspect("test.so", bytes(b))


def test_pe_two_overlapping_sections_refused():
    b = bytearray(_pe(".exe"))
    _put(b, 0x86, 2, 2)
    second = 0x98 + 240 + 40
    b[second:second + 5] = b".data"
    _put(b, second + 8, 0x100, 4)
    _put(b, second + 12, 0x1000, 4)
    _put(b, second + 16, 0x200, 4)
    _put(b, second + 20, 0x200, 4)
    with pytest.raises(NativeA1Refused, match="PE_OVERLAPPING_SECTIONS"):
        _inspect("test.exe", bytes(b))


def test_wrong_or_missing_sha_never_parsed_as_approval():
    raw = _pe(".exe")
    with pytest.raises(NativeA1Refused, match="NATIVE_A1_SHA256_MISMATCH"):
        _inspect("test.exe", raw, expected_sha256="f" * 64)
    with pytest.raises(NativeA1Refused, match="NATIVE_A1_PINNED_BINARY_AND_NAME_REQUIRED"):
        _inspect("test.exe", raw, expected_sha256="A" * 64)


@pytest.mark.parametrize("raw", [b"", b"X" * (8 * 1024 * 1024 + 1)])
def test_empty_or_oversized_refused(raw):
    with pytest.raises(NativeA1Refused, match="NATIVE_A1_PINNED_BINARY_AND_NAME_REQUIRED"):
        _inspect("test.exe", raw)


def test_symlink_hardlink_relative_and_nonregular_denied(tmp_path):
    path = tmp_path / "candidate.so"
    raw = _elf()
    path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    with pytest.raises(NativeA1Refused, match="NATIVE_A1_ABSOLUTE_PATH_REQUIRED"):
        inspect_native_file(
            __import__("pathlib").Path("relative.so"),
            expected_sha256=digest, operator_ack=True,
        )
    alias = tmp_path / "alias.so"
    alias.symlink_to(path)
    with pytest.raises(NativeA1Refused, match="NATIVE_A1_SYMLINK_FORBIDDEN"):
        inspect_native_file(alias, expected_sha256=digest, operator_ack=True)
    alias.unlink()
    os.link(path, alias)
    with pytest.raises(NativeA1Refused, match="NATIVE_A1_REGULAR_BOUNDED_FILE_REQUIRED"):
        inspect_native_file(path, expected_sha256=digest, operator_ack=True)


def test_no_ack_no_production_env_or_network_execution(tmp_path, monkeypatch):
    raw = _pe(".exe")
    with pytest.raises(NativeA1Refused, match="NATIVE_A1_NONPRODUCTION"):
        _inspect("candidate.exe", raw, operator_ack=False)
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(NativeA1Refused, match="NATIVE_A1_NONPRODUCTION"):
        _inspect("candidate.exe", raw)
    monkeypatch.delenv("MMT_PRODUCTION")
    monkeypatch.delenv("MMT_NONPRODUCTION")
    with pytest.raises(NativeA1Refused, match="NATIVE_A1_NONPRODUCTION"):
        _inspect("candidate.exe", raw)


def test_no_network_no_binary_loading_no_worker_release(tmp_path, monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("NATIVE_A1_MUST_NOT_LOAD_EXECUTE_OR_CONNECT")
    monkeypatch.setattr(subprocess, "run", blocked)
    monkeypatch.setattr(subprocess, "Popen", blocked)
    monkeypatch.setattr(socket, "socket", blocked)
    monkeypatch.setattr(os, "system", blocked)
    raw = _elf()
    path = tmp_path / "local.so"
    path.write_bytes(raw)
    report = inspect_native_file(
        path, expected_sha256=hashlib.sha256(raw).hexdigest(),
        operator_ack=True,
    )
    assert report.status.endswith("UNTRUSTED")
    assert not report.worker_execution_authorized
    with pytest.raises(RuntimeA6Denied):
        require_worker_launch(None, b"")
