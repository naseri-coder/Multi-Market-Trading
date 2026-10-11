"""Stage 14: deterministic, data-only Core API v1 third-party source packages.

Never imports, executes, extracts, installs, or registers the submitted source.
Static source warnings are defense in depth, NOT a Python security sandbox.
"""
from __future__ import annotations

import ast
import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass
from typing import Any

from .contracts import Market
from .core_api_v1 import ABI_MAJOR, ABI_MINOR, CoreEventType, CoreManifest, SetupSpec

MAX_SOURCE = 65_536  # Must not exceed Stage-4 _MAX_SOURCE.
MAX_BUNDLE = 80_000
MAX_MANIFEST = 8_192
_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{1,79}\Z")
_SHA = re.compile(r"[a-f0-9]{64}\Z")
_FILES = ("manifest.json", "plugin.py")
_KEYS = frozenset({
    "schema_version", "abi_major", "abi_minor", "core_id", "core_version",
    "setups", "supported_markets", "accepted_events", "minimum_closed_candles",
    "entrypoint", "plugin_sha256",
})
_SETUP_KEYS = frozenset({"setup_id", "description", "may_manage_stop"})
# This is merely a developer lint policy. A hostile script CAN bypass it.
_IMPORTS = frozenset({"json", "sys", "math", "decimal", "statistics", "datetime"})
_DENIED_CALLS = frozenset({
    "eval", "exec", "compile", "open", "__import__", "breakpoint", "input",
    "getattr", "setattr", "delattr", "globals", "locals", "vars",
})
_DENIED_ATTRIBUTES = frozenset({
    "system", "popen", "Popen", "run", "check_call", "check_output", "fork",
    "spawn", "connect", "request", "urlopen", "read_text", "write_text",
    "read_bytes", "write_bytes", "unlink", "remove", "rmtree", "execv",
})


class DeveloperPackageRefused(ValueError):
    """Refuse a noncanonical or unreviewed source package."""


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise DeveloperPackageRefused("DUPLICATE_JSON_FIELD")
        obj[key] = value
    return obj


def _wire(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def _parse_json(data: bytes, *, max_size: int) -> dict[str, Any]:
    if type(data) is not bytes or not 0 < len(data) <= max_size:
        raise DeveloperPackageRefused("JSON_SIZE_INVALID")
    try:
        result = json.loads(data.decode("utf-8"), object_pairs_hook=_unique,
                            parse_constant=lambda _: (_ for _ in ()).throw(
                                DeveloperPackageRefused("NONFINITE_JSON")))
    except DeveloperPackageRefused:
        raise
    except (ValueError, UnicodeError, TypeError) as exc:
        raise DeveloperPackageRefused("JSON_INVALID") from exc
    if type(result) is not dict:
        raise DeveloperPackageRefused("JSON_OBJECT_REQUIRED")
    return result


def _values(items: object, enum_type: type, label: str) -> frozenset:
    if (type(items) is not list or not items or len(items) > 16 or
            any(type(s) is not str for s in items) or len(set(items)) != len(items)):
        raise DeveloperPackageRefused("INVALID_" + label)
    try:
        return frozenset(enum_type(x) for x in items)
    except ValueError as exc:
        raise DeveloperPackageRefused("INVALID_" + label) from exc


def parse_manifest(data: bytes) -> tuple[dict[str, Any], CoreManifest]:
    """Strict exact-schema manifest with the *existing* Core API ABI contract."""
    d = _parse_json(data, max_size=MAX_MANIFEST)
    if set(d) != _KEYS or _wire(d) != data:
        raise DeveloperPackageRefused("MANIFEST_NONCANONICAL_OR_SCHEMA")
    if (type(d["schema_version"]) is not int or d["schema_version"] != 1 or
            type(d["abi_major"]) is not int or d["abi_major"] != ABI_MAJOR or
            type(d["abi_minor"]) is not int or d["abi_minor"] != ABI_MINOR or
            type(d["entrypoint"]) is not str or d["entrypoint"] != "plugin.py" or
            type(d["plugin_sha256"]) is not str or not _SHA.fullmatch(d["plugin_sha256"])):
        raise DeveloperPackageRefused("MANIFEST_VERSION_OR_ENTRYPOINT")
    if (type(d["core_id"]) is not str or not _NAME.fullmatch(d["core_id"]) or
            type(d["core_version"]) is not str or not 0 < len(d["core_version"]) <= 32):
        raise DeveloperPackageRefused("INVALID_CORE_IDENTITY")
    s = d["setups"]
    if type(s) is not list or not 1 <= len(s) <= 32:
        raise DeveloperPackageRefused("INVALID_SETUP_LIST")
    setups = []
    for setup in s:
        if (type(setup) is not dict or set(setup) != _SETUP_KEYS or
                type(setup["setup_id"]) is not str or
                type(setup["description"]) is not str or
                type(setup["may_manage_stop"]) is not bool):
            raise DeveloperPackageRefused("INVALID_SETUP_SCHEMA")
        try:
            setups.append(SetupSpec(**setup))
        except (TypeError, ValueError) as exc:
            raise DeveloperPackageRefused("INVALID_SETUP_VALUE") from exc
    try:
        manifest = CoreManifest(
            core_id=d["core_id"], core_version=d["core_version"],
            setups=tuple(setups),
            supported_markets=_values(d["supported_markets"], Market, "MARKETS"),
            accepted_events=_values(d["accepted_events"], CoreEventType, "EVENTS"),
            minimum_closed_candles=d["minimum_closed_candles"],
        )
    except DeveloperPackageRefused:
        raise
    except (TypeError, ValueError) as exc:
        raise DeveloperPackageRefused("CORE_ABI_CONTRACT_REJECTED") from exc
    # Require sorted stable list representations to eliminate multiple encodings.
    if (d["supported_markets"] != sorted(d["supported_markets"]) or
            d["accepted_events"] != sorted(d["accepted_events"])):
        raise DeveloperPackageRefused("NONCANONICAL_CAPABILITIES")
    return d, manifest


def inspect_source(source: bytes) -> tuple[str, ...]:
    """Conservative lint findings; NOT evidence of hostile-code containment."""
    if type(source) is not bytes or not 0 < len(source) <= MAX_SOURCE:
        raise DeveloperPackageRefused("SOURCE_SIZE_INVALID")
    try:
        decoded = source.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise DeveloperPackageRefused("SOURCE_UTF8_REQUIRED") from exc
    if "\x00" in decoded or decoded.startswith("\ufeff"):
        raise DeveloperPackageRefused("SOURCE_ENCODING_INVALID")
    try:
        tree = ast.parse(decoded, filename="<third-party-plugin>")
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise DeveloperPackageRefused("SOURCE_SYNTAX_INVALID") from exc
    findings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom) or any(a.name not in _IMPORTS
                                                        for a in node.names):
                findings.add("DISALLOWED_IMPORT")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in _DENIED_CALLS:
                findings.add("DANGEROUS_CALL")
            if isinstance(node.func, ast.Attribute) and node.func.attr in _DENIED_ATTRIBUTES:
                findings.add("DANGEROUS_ATTRIBUTE_CALL")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            findings.add("DUNDER_ATTRIBUTE_ACCESS")
    return tuple(sorted(findings))


def _archive(manifest: bytes, source: bytes) -> bytes:
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", compression=zipfile.ZIP_STORED) as z:
        for name, content in (("manifest.json", manifest), ("plugin.py", source)):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o100644 << 16
            info.create_system = 3
            z.writestr(info, content)
    return data.getvalue()


@dataclass(frozen=True, slots=True)
class PackageInspection:
    sha256: str
    source_sha256: str
    manifest: CoreManifest
    warnings: tuple[str, ...]
    source: bytes  # never execute this in the control-plane process


def build_package(declaration: dict[str, Any], source: bytes) -> bytes:
    """Build deterministic ZIP without running the plugin or importing its module."""
    findings = inspect_source(source)
    if findings:
        raise DeveloperPackageRefused("STATIC_REVIEW_BLOCKED:" + ",".join(findings))
    if type(declaration) is not dict:
        raise DeveloperPackageRefused("INVALID_MANIFEST_DECLARATION")
    spec = dict(declaration)
    spec["plugin_sha256"] = hashlib.sha256(source).hexdigest()
    body = _wire(spec)
    parse_manifest(body)
    result = _archive(body, source)
    if len(result) > MAX_BUNDLE:
        raise DeveloperPackageRefused("PACKAGE_SIZE_INVALID")
    return result


def inspect_package(raw: bytes) -> PackageInspection:
    """Reject duplicates, noncanonical zip, unknown files, changing manifests.

    Does NOT extract, open filesystem paths, or run the embedded Python.
    """
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BUNDLE:
        raise DeveloperPackageRefused("PACKAGE_SIZE_INVALID")
    try:
        with zipfile.ZipFile(io.BytesIO(raw), "r") as z:
            if tuple(i.filename for i in z.infolist()) != _FILES:
                raise DeveloperPackageRefused("PACKAGE_FILE_SET_OR_ORDER")
            if any(i.file_size > MAX_SOURCE or i.flag_bits & 0x1
                   for i in z.infolist()):
                raise DeveloperPackageRefused("PACKAGE_MEMBER_UNSAFE")
            manifest_bytes = z.read("manifest.json")
            source = z.read("plugin.py")
    except DeveloperPackageRefused:
        raise
    except (zipfile.BadZipFile, OSError, RuntimeError, KeyError, ValueError) as exc:
        raise DeveloperPackageRefused("PACKAGE_INVALID_ZIP") from exc
    if _archive(manifest_bytes, source) != raw:
        raise DeveloperPackageRefused("PACKAGE_NONCANONICAL_ZIP")
    d, manifest = parse_manifest(manifest_bytes)
    actual = hashlib.sha256(source).hexdigest()
    if d["plugin_sha256"] != actual:
        raise DeveloperPackageRefused("SOURCE_HASH_MISMATCH")
    findings = inspect_source(source)
    return PackageInspection(hashlib.sha256(raw).hexdigest(), actual,
                             manifest, findings, source)


__all__ = ["DeveloperPackageRefused", "PackageInspection", "build_package",
           "inspect_package", "inspect_source", "parse_manifest"]
