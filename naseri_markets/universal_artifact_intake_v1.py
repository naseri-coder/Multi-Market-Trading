"""Non-executing universal artifact intake for future language-specific adapters.

Recognition or validation is NEVER installation, conversion, adapter
availability, strategy evaluation, a market-data grant, or live permission.
All submitted bytes remain in memory for this call; no file is persisted.
"""
from __future__ import annotations

import ast
import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import PurePath

from .core_developer_sdk_v1 import (
    DeveloperPackageRefused,
    inspect_package,
    inspect_source,
)

MAX_INSPECTION_BYTES = 8 * 1024 * 1024
_TEXT_MAX = 1024 * 1024
_CSV_MAX = 2 * 1024 * 1024
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\Z")


class IntakeRefused(ValueError):
    """A stable rejection without leaking the contents of the artifact."""


class ArtifactRole(StrEnum):
    STRATEGY_SOURCE = "strategy_source"
    STRATEGY_PACKAGE = "strategy_package"
    DATA = "market_data"
    DECLARATION = "declaration"
    COMPILED = "compiled_strategy_or_worker"


class InspectionLevel(StrEnum):
    SOURCE_SYNTAX = "source_syntax_checked"
    SDK_PACKAGE = "sdk_package_checked"
    JSON_STRUCTURE = "json_structure_checked"
    CSV_STRUCTURE = "csv_structure_checked"
    PARQUET_CONTAINER = "parquet_container_only"
    BINARY_MAGIC = "binary_magic_only"
    SOURCE_ENCODING = "utf8_encoding_only"
    OPAQUE_BINARY = "opaque_binary_only"


@dataclass(frozen=True, slots=True)
class ArtifactInspection:
    filename: str
    extension: str
    role: ArtifactRole
    byte_length: int
    sha256: str
    inspection_level: InspectionLevel
    proposed_adapter: str
    findings: tuple[str, ...] = ()
    # Recognition is not registration; every path must remain deny-by-default.
    executable: bool = False
    adapter_installed: bool = False
    market_data_authenticated: bool = False
    paper_enabled: bool = False
    live_enabled: bool = False
    telegram_enabled: bool = False
    status: str = "UNTRUSTED_ARTIFACT_REVIEW_REQUIRED"


# V1 recognises extensions, NOT automatic code execution or compilation.
# The manifest/worker ABI remains the separately-reviewed source of truth.
_ROUTES: dict[str, tuple[ArtifactRole, str]] = {
    ".py": (ArtifactRole.STRATEGY_SOURCE, "python_core_sdk"),
    ".json": (ArtifactRole.DECLARATION, "manifest_or_data_schema"),
    ".zip": (ArtifactRole.STRATEGY_PACKAGE, "canonical_python_sdk_package"),
    ".csv": (ArtifactRole.DATA, "csv_market_data_loader"),
    ".parquet": (ArtifactRole.DATA, "parquet_market_data_loader"),
    ".js": (ArtifactRole.STRATEGY_SOURCE, "javascript_isolated_worker"),
    ".ts": (ArtifactRole.STRATEGY_SOURCE, "typescript_build_and_worker"),
    ".mq4": (ArtifactRole.STRATEGY_SOURCE, "metatrader4_bridge"),
    ".mq5": (ArtifactRole.STRATEGY_SOURCE, "metatrader5_bridge"),
    ".ex5": (ArtifactRole.COMPILED, "metatrader5_native_terminal_bridge"),
    ".pine": (ArtifactRole.STRATEGY_SOURCE, "pine_semantic_port_and_review"),
    ".dll": (ArtifactRole.COMPILED, "windows_pe_isolated_worker"),
    ".so": (ArtifactRole.COMPILED, "linux_elf_isolated_worker"),
    ".exe": (ArtifactRole.COMPILED, "windows_pe_isolated_worker"),
    ".wasm": (ArtifactRole.COMPILED, "wasm_sandbox_worker"),
}


def supported_extensions() -> tuple[str, ...]:
    """The exact recognised artifact suffix list (not an execution grant)."""
    return tuple(sorted(_ROUTES))


def _utf8(raw: bytes) -> str:
    try:
        data = raw.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise IntakeRefused("UTF8_SOURCE_REQUIRED") from exc
    if "\x00" in data or data.startswith("\ufeff"):
        raise IntakeRefused("INVALID_TEXT_ENCODING")
    return data


def _json_document(raw: bytes) -> None:
    def distinct(items: list[tuple[str, object]]) -> dict:
        result: dict[str, object] = {}
        for key, value in items:
            if key in result:
                raise IntakeRefused("DUPLICATE_JSON_FIELD")
            result[key] = value
        return result

    try:
        data = json.loads(
            _utf8(raw), object_pairs_hook=distinct,
            parse_float=Decimal,
            parse_constant=lambda _: (_ for _ in ()).throw(
                IntakeRefused("NONFINITE_JSON_VALUE")),
        )
    except IntakeRefused:
        raise
    except (ValueError, RecursionError, TypeError) as exc:
        raise IntakeRefused("INVALID_JSON_DOCUMENT") from exc
    if not isinstance(data, (dict, list)):
        raise IntakeRefused("JSON_OBJECT_OR_ARRAY_REQUIRED")


def _csv_document(raw: bytes) -> None:
    stream = io.StringIO(_utf8(raw), newline="")
    try:
        rows = csv.reader(stream, strict=True)
        columns = next(rows)
        if (not columns or len(columns) > 128
                or any(not field or len(field) > 256 for field in columns)
                or len(set(columns)) != len(columns)):
            raise IntakeRefused("CSV_HEADER_INVALID")
        count = 0
        for row in rows:
            count += 1
            if len(row) != len(columns) or count > 100_000:
                raise IntakeRefused("CSV_ROW_SHAPE_INVALID")
    except IntakeRefused:
        raise
    except (csv.Error, StopIteration, UnicodeError) as exc:
        raise IntakeRefused("CSV_FORMAT_INVALID") from exc


def _pe(raw: bytes) -> None:
    if len(raw) < 68 or raw[:2] != b"MZ":
        raise IntakeRefused("PE_HEADER_INVALID")
    offset = int.from_bytes(raw[0x3c:0x40], "little")
    if offset < 64 or offset > len(raw) - 24 or raw[offset:offset + 4] != b"PE\x00\x00":
        raise IntakeRefused("PE_HEADER_INVALID")


def _parquet(raw: bytes) -> None:
    if len(raw) < 12 or raw[:4] != b"PAR1" or raw[-4:] != b"PAR1":
        raise IntakeRefused("PARQUET_FOOTER_INVALID")
    metadata_bytes = int.from_bytes(raw[-8:-4], "little")
    if metadata_bytes <= 0 or metadata_bytes > len(raw) - 12:
        raise IntakeRefused("PARQUET_FOOTER_INVALID")


def inspect_artifact(filename: str, raw: bytes) -> ArtifactInspection:
    """Inspect a bounded supplied byte buffer. Never load/run submitted code.

    Compiled formats receive only header/opaque recognition; authenticity,
    architecture, executable safety and actual strategy behavior remain unknown.
    """
    if (type(filename) is not str or _NAME.fullmatch(filename) is None
            or PurePath(filename).name != filename):
        raise IntakeRefused("INVALID_ARTIFACT_NAME")
    extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in _ROUTES:
        raise IntakeRefused("ARTIFACT_EXTENSION_UNSUPPORTED")
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_INSPECTION_BYTES:
        raise IntakeRefused("ARTIFACT_SIZE_INVALID")
    role, adapter = _ROUTES[extension]
    findings: tuple[str, ...] = ()
    if extension == ".py":
        if len(raw) > 65536:
            raise IntakeRefused("PYTHON_SDK_SOURCE_LIMIT")
        try:
            findings = inspect_source(raw)
        except DeveloperPackageRefused as exc:
            raise IntakeRefused("PYTHON_SOURCE_INVALID") from exc
        level = InspectionLevel.SOURCE_SYNTAX
    elif extension == ".zip":
        try:
            inspection = inspect_package(raw)
        except DeveloperPackageRefused as exc:
            raise IntakeRefused("NONCANONICAL_SDK_ARCHIVE") from exc
        findings = inspection.warnings
        level = InspectionLevel.SDK_PACKAGE
    elif extension == ".json":
        if len(raw) > _TEXT_MAX:
            raise IntakeRefused("TEXT_SIZE_INVALID")
        _json_document(raw)
        level = InspectionLevel.JSON_STRUCTURE
    elif extension == ".csv":
        if len(raw) > _CSV_MAX:
            raise IntakeRefused("CSV_SIZE_INVALID")
        _csv_document(raw)
        level = InspectionLevel.CSV_STRUCTURE
    elif extension == ".parquet":
        _parquet(raw)
        level = InspectionLevel.PARQUET_CONTAINER
    elif extension in {".js", ".ts", ".mq4", ".mq5", ".pine"}:
        if len(raw) > _TEXT_MAX:
            raise IntakeRefused("TEXT_SIZE_INVALID")
        _utf8(raw)
        level = InspectionLevel.SOURCE_ENCODING
    elif extension in {".dll", ".exe"}:
        _pe(raw)
        level = InspectionLevel.BINARY_MAGIC
    elif extension == ".so":
        if len(raw) < 16 or raw[:4] != b"\x7fELF" or raw[4] not in (1, 2):
            raise IntakeRefused("ELF_HEADER_INVALID")
        level = InspectionLevel.BINARY_MAGIC
    elif extension == ".wasm":
        if len(raw) < 8 or raw[:8] != b"\x00asm\x01\x00\x00\x00":
            raise IntakeRefused("WASM_VERSION_INVALID")
        level = InspectionLevel.BINARY_MAGIC
    else:  # .ex5 proprietary compiled MQL5, format cannot be publicly authenticated
        if len(raw) < 16 or raw.startswith((b"MZ", b"\x7fELF", b"\x00asm")):
            raise IntakeRefused("EX5_OPAQUE_BINARY_UNVERIFIED")
        level = InspectionLevel.OPAQUE_BINARY
    return ArtifactInspection(
        filename=filename, extension=extension, role=role,
        byte_length=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
        inspection_level=level, proposed_adapter=adapter, findings=findings,
    )


__all__ = [
    "ArtifactInspection", "ArtifactRole", "InspectionLevel",
    "IntakeRefused", "inspect_artifact", "supported_extensions",
]
