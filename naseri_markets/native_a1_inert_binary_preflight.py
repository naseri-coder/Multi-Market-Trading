"""NATIVE-A1: bounded static PE/ELF *structure* review; never load binary code.

Header parsing and SHA-256 establish neither trustworthy provenance nor
absence of malware. No sandbox/host isolation is exercised here. A6 DENY.
"""
from __future__ import annotations

import hashlib
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

_LIMIT = 8 * 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\Z")
_EXTS = frozenset({".dll", ".exe", ".so"})
_PE_MACHINES = {0x014C: ("x86", 32), 0x8664: ("x86_64", 64),
                0xAA64: ("aarch64", 64)}
_ELF_MACHINES = {3: ("x86", 32), 62: ("x86_64", 64),
                 183: ("aarch64", 64)}


class NativeA1Refused(ValueError):
    """Fail-closed rejection without exposing untrusted file contents."""


@dataclass(frozen=True, slots=True)
class NativeA1Review:
    sha256: str
    byte_length: int
    filename: str
    artifact_type: str
    container_format: str
    architecture: str
    address_width: int
    endianness: str
    mapped_regions: int
    status: str = "NATIVE_A1_HEADER_STRUCTURE_ONLY_UNTRUSTED"
    full_format_validated: bool = False
    code_signature_verified: bool = False
    publisher_authenticated: bool = False
    dependencies_verified: bool = False
    binary_safe_from_malware: bool = False
    isolated_host_certified: bool = False
    executed_in_sandbox: bool = False
    runtime_adapter_installed: bool = False
    core_api_behavior_verified: bool = False
    paper_strategy_executed: bool = False
    broker_authorized: bool = False
    telegram_authorized: bool = False
    worker_execution_authorized: bool = False
    quarantine_release_authorized: bool = False


def _u(data: bytes, offset: int, width: int) -> int:
    if offset < 0 or width not in (2, 4, 8) or offset + width > len(data):
        raise NativeA1Refused("NATIVE_A1_HEADER_TRUNCATED")
    return int.from_bytes(data[offset:offset + width], "little")


def _pe(raw: bytes, suffix: str) -> tuple[str, int, int]:
    if len(raw) < 0x40 or raw[:2] != b"MZ":
        raise NativeA1Refused("NATIVE_A1_PE_DOS_HEADER_INVALID")
    pe = _u(raw, 0x3C, 4)
    if pe < 0x40 or pe + 24 > len(raw) or raw[pe:pe + 4] != b"PE\x00\x00":
        raise NativeA1Refused("NATIVE_A1_PE_SIGNATURE_INVALID")
    machine = _PE_MACHINES.get(_u(raw, pe + 4, 2))
    nsections = _u(raw, pe + 6, 2)
    option_size = _u(raw, pe + 20, 2)
    attributes = _u(raw, pe + 22, 2)
    if (machine is None or not 1 <= nsections <= 96
            or not attributes & 0x0002
            or bool(attributes & 0x2000) != (suffix == ".dll")):
        raise NativeA1Refused("NATIVE_A1_PE_TYPE_OR_MACHINE_INVALID")
    optional = pe + 24
    if optional + option_size > len(raw) or option_size < 96:
        raise NativeA1Refused("NATIVE_A1_PE_OPTIONAL_HEADER_INVALID")
    magic = _u(raw, optional, 2)
    expected_width = 32 if magic == 0x10B else 64 if magic == 0x20B else 0
    if expected_width != machine[1] or option_size < (96 if expected_width == 32 else 112):
        raise NativeA1Refused("NATIVE_A1_PE_BITNESS_INVALID")
    image_size = _u(raw, optional + 56, 4)
    header_size = _u(raw, optional + 60, 4)
    section_alignment = _u(raw, optional + 32, 4)
    file_alignment = _u(raw, optional + 36, 4)
    table = optional + option_size
    table_end = table + nsections * 40
    if (image_size == 0 or header_size == 0
            or header_size > len(raw) or table_end > header_size
            or not 1 <= section_alignment <= 65536
            or not 1 <= file_alignment <= 65536):
        raise NativeA1Refused("NATIVE_A1_PE_SECTION_TABLE_INVALID")
    raw_ranges: list[tuple[int, int]] = []
    loaded = 0
    for i in range(nsections):
        p = table + i * 40
        virtual_size, virtual_addr = _u(raw, p + 8, 4), _u(raw, p + 12, 4)
        size, offset = _u(raw, p + 16, 4), _u(raw, p + 20, 4)
        if (virtual_size == 0 and size == 0
                or virtual_addr >= image_size
                or virtual_addr + max(virtual_size, size) > image_size):
            raise NativeA1Refused("NATIVE_A1_PE_SECTION_OUT_OF_IMAGE")
        if size:
            if offset < header_size or offset + size > len(raw):
                raise NativeA1Refused("NATIVE_A1_PE_SECTION_OUT_OF_FILE")
            raw_ranges.append((offset, offset + size))
            loaded += 1
    if not loaded:
        raise NativeA1Refused("NATIVE_A1_PE_NO_FILE_BACKED_SECTION")
    raw_ranges.sort()
    if any(a[1] > b[0] for a, b in zip(raw_ranges, raw_ranges[1:])):
        raise NativeA1Refused("NATIVE_A1_PE_OVERLAPPING_SECTIONS")
    return machine[0], machine[1], loaded


def _elf(raw: bytes) -> tuple[str, int, int]:
    if (len(raw) < 52 or raw[:4] != b"\x7fELF"
            or raw[4] not in (1, 2) or raw[5] != 1
            or raw[6] != 1):
        raise NativeA1Refused("NATIVE_A1_ELF_IDENTITY_INVALID")
    width = 32 if raw[4] == 1 else 64
    if len(raw) < (52 if width == 32 else 64):
        raise NativeA1Refused("NATIVE_A1_ELF_HEADER_TRUNCATED")
    etype = _u(raw, 16, 2)
    machine = _ELF_MACHINES.get(_u(raw, 18, 2))
    if etype != 3 or machine is None or machine[1] != width or _u(raw, 20, 4) != 1:
        raise NativeA1Refused("NATIVE_A1_ELF_TYPE_OR_ARCH_INVALID")
    if width == 64:
        phoff, shoff = _u(raw, 32, 8), _u(raw, 40, 8)
        ehsize, phentsize, phnum = _u(raw, 52, 2), _u(raw, 54, 2), _u(raw, 56, 2)
        shentsize, shnum = _u(raw, 58, 2), _u(raw, 60, 2)
        ph_expected, sh_expected, eh_expected = 56, 64, 64
    else:
        phoff, shoff = _u(raw, 28, 4), _u(raw, 32, 4)
        ehsize, phentsize, phnum = _u(raw, 40, 2), _u(raw, 42, 2), _u(raw, 44, 2)
        shentsize, shnum = _u(raw, 46, 2), _u(raw, 48, 2)
        ph_expected, sh_expected, eh_expected = 32, 40, 52
    if (ehsize != eh_expected or phoff < ehsize or not 1 <= phnum <= 512
            or phentsize != ph_expected or phoff + phnum * phentsize > len(raw)):
        raise NativeA1Refused("NATIVE_A1_ELF_PROGRAM_TABLE_INVALID")
    if (shoff == 0) != (shnum == 0):
        raise NativeA1Refused("NATIVE_A1_ELF_SECTION_TABLE_INVALID")
    if shnum and (not 1 <= shnum <= 2048 or shoff < ehsize
                  or shentsize != sh_expected
                  or shoff + shnum * shentsize > len(raw)):
        raise NativeA1Refused("NATIVE_A1_ELF_SECTION_TABLE_INVALID")
    loads = 0
    for i in range(phnum):
        p = phoff + i * phentsize
        kind = _u(raw, p, 4)
        if width == 64:
            offset, filesz, memsz, align = (
                _u(raw, p + 8, 8), _u(raw, p + 32, 8),
                _u(raw, p + 40, 8), _u(raw, p + 48, 8),
            )
        else:
            offset, filesz, memsz, align = (
                _u(raw, p + 4, 4), _u(raw, p + 16, 4),
                _u(raw, p + 20, 4), _u(raw, p + 28, 4),
            )
        if (offset > len(raw) or filesz > len(raw) - offset or memsz < filesz
                or (align > 1 and align & (align - 1))):
            raise NativeA1Refused("NATIVE_A1_ELF_SEGMENT_OUT_OF_FILE")
        if kind == 1:
            loads += 1
    if not loads:
        raise NativeA1Refused("NATIVE_A1_ELF_NO_LOAD_SEGMENT")
    # ET_DYN can also be a position-independent executable, not only a .so!
    return machine[0], width, loads


def _gate(operator_ack: bool) -> None:
    if (os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"
            or operator_ack is not True):
        raise NativeA1Refused("NATIVE_A1_NONPRODUCTION_OPERATOR_ACK_REQUIRED")


def inspect_native_bytes(
    filename: str, raw: bytes, *, expected_sha256: str,
    operator_ack: bool = False,
) -> NativeA1Review:
    """Inspect untrusted bytes with only bounded Python parsing and SHA256."""
    _gate(operator_ack)
    if (type(filename) is not str or _NAME.fullmatch(filename) is None
            or type(raw) is not bytes or not 0 < len(raw) <= _LIMIT
            or type(expected_sha256) is not str
            or _SHA.fullmatch(expected_sha256) is None):
        raise NativeA1Refused("NATIVE_A1_PINNED_BINARY_AND_NAME_REQUIRED")
    suffix = Path(filename).suffix.lower()
    if suffix not in _EXTS:
        raise NativeA1Refused("NATIVE_A1_UNSUPPORTED_NATIVE_EXTENSION")
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise NativeA1Refused("NATIVE_A1_SHA256_MISMATCH")
    if suffix == ".so":
        arch, width, regions = _elf(raw)
    else:
        arch, width, regions = _pe(raw, suffix)
    return NativeA1Review(
        sha256=expected_sha256, byte_length=len(raw), filename=filename,
        artifact_type={".so": "ELF_ET_DYN_CLAIMED_LIBRARY",
                       ".dll": "PE_DLL", ".exe": "PE_EXE"}[suffix],
        container_format="ELF" if suffix == ".so" else "PE",
        architecture=arch, address_width=width, endianness="little",
        mapped_regions=regions,
    )


def inspect_native_file(
    path: Path, *, expected_sha256: str, operator_ack: bool = False,
) -> NativeA1Review:
    """Read a regular local pinned binary without following links or executing.

    This checks stable inode metadata but cannot prove immutability against
    a privileged actor who mutates then restores the source.
    """
    _gate(operator_ack)
    if not isinstance(path, Path) or not path.is_absolute():
        raise NativeA1Refused("NATIVE_A1_ABSOLUTE_PATH_REQUIRED")
    current = Path(path.anchor)
    try:
        for part in path.parts[1:]:
            current /= part
            if stat.S_ISLNK(current.lstat().st_mode):
                raise NativeA1Refused("NATIVE_A1_SYMLINK_FORBIDDEN")
        st = path.lstat()
        if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1
                or not 0 < st.st_size <= _LIMIT):
            raise NativeA1Refused("NATIVE_A1_REGULAR_BOUNDED_FILE_REQUIRED")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or (before.st_dev, before.st_ino, before.st_size,
                        before.st_mtime_ns, before.st_ctime_ns) !=
                    (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)):
                raise NativeA1Refused("NATIVE_A1_FILE_IDENTITY_CHANGED")
            pieces: list[bytes] = []
            size = 0
            while size <= _LIMIT:
                part = os.read(fd, min(128 * 1024, _LIMIT + 1 - size))
                if not part:
                    break
                size += len(part)
                pieces.append(part)
            after = os.fstat(fd)
            now = path.lstat()
            if (size != st.st_size
                    or (after.st_dev, after.st_ino, after.st_size,
                        after.st_mtime_ns, after.st_ctime_ns) !=
                    (now.st_dev, now.st_ino, now.st_size,
                     now.st_mtime_ns, now.st_ctime_ns)
                    or (before.st_dev, before.st_ino, before.st_size,
                        before.st_mtime_ns, before.st_ctime_ns) !=
                    (after.st_dev, after.st_ino, after.st_size,
                     after.st_mtime_ns, after.st_ctime_ns)):
                raise NativeA1Refused("NATIVE_A1_FILE_CHANGED_DURING_READ")
            return inspect_native_bytes(
                path.name, b"".join(pieces),
                expected_sha256=expected_sha256, operator_ack=operator_ack,
            )
        finally:
            os.close(fd)
    except NativeA1Refused:
        raise
    except OSError as exc:
        raise NativeA1Refused("NATIVE_A1_LOCAL_SOURCE_UNAVAILABLE") from exc


__all__ = [
    "NativeA1Refused", "NativeA1Review",
    "inspect_native_bytes", "inspect_native_file",
]
