"""MT-A1: local MetaTrader file/artifact intake, exclusively read-only.

This is NOT an MQL compiler, terminal launcher, EX5 verifier or connector.
Neither MQL4/MQL5 scripts nor proprietary EX5 bytes are ever evaluated.
MT5 DEMO terminal observation remains in the existing separate adapter.
"""
from __future__ import annotations

import hashlib
import os
import re
import stat
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .contracts import Market

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_SYMBOL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z")
_SOURCE_MAX = 8 * 1024 * 1024
_COMPILED_MAX = 32 * 1024 * 1024
_MAP = {
    "M1": "1m",
    "M5": "5m",
    "M15": "15m",
    "M30": "30m",
    "H1": "1h",
    "H4": "4h",
    "H12": "12h",
    "D1": "1d",
}
_NATIVE = {
    "MT4": frozenset({"M1", "M5", "M15", "M30", "H1", "H4", "D1"}),
    "MT5": frozenset(_MAP),
}
_EXTENSION = {".mq4": ("MT4", "MQL4_SOURCE"),
              ".mq5": ("MT5", "MQL5_SOURCE"),
              ".ex5": ("MT5", "EX5_OPAQUE_BINARY")}


class MTArtifactRefused(ValueError):
    """Fail closed; no local file content or account details in error."""


class MetaTraderPlatform(StrEnum):
    MT4 = "MT4"
    MT5 = "MT5"


@dataclass(frozen=True, slots=True)
class MetaTraderArtifactReview:
    sha256: str
    size_bytes: int
    platform: str
    artifact_kind: str
    declared_market: str
    declared_symbol: str
    declared_timeframe: str
    data_a1_timeframe: str
    provider_claim: str
    source_lines: int | None
    source_encoding: str | None
    status: str = "MT_A1_LOCAL_ARTIFACT_BYTES_REVIEWED_NO_TERMINAL_EXECUTION"
    mt_source_compiled: bool = False
    ex5_format_verified: bool = False
    broker_source_authenticated: bool = False
    platform_account_verified: bool = False
    real_terminal_connected: bool = False
    market_data_observed: bool = False
    point_in_time_verified: bool = False
    paper_strategy_executed: bool = False
    broker_order_sent: bool = False
    telegram_sent: bool = False
    worker_execution_authorized: bool = False
    quarantine_release_authorized: bool = False


def _scope(
    *, platform: MetaTraderPlatform, market: Market, symbol: str,
    timeframe: str, provider_claim: str, expected_sha256: str,
    operator_ack: bool,
) -> str:
    if (os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"
            or operator_ack is not True):
        raise MTArtifactRefused("MT_A1_EXPLICIT_NONPRODUCTION_ACK_REQUIRED")
    if (type(platform) is not MetaTraderPlatform or type(market) is not Market
            or type(symbol) is not str or _SYMBOL.fullmatch(symbol) is None
            or type(provider_claim) is not str
            or _LABEL.fullmatch(provider_claim) is None
            or type(timeframe) is not str
            or timeframe not in _NATIVE[platform.value]
            or type(expected_sha256) is not str
            or _SHA.fullmatch(expected_sha256) is None):
        raise MTArtifactRefused("MT_A1_EXACT_SYMBOL_TIMEFRAME_AND_SHA_REQUIRED")
    return _MAP[timeframe]


def _regular_path(path: Path) -> None:
    if not isinstance(path, Path) or not path.is_absolute():
        raise MTArtifactRefused("MT_A1_ABSOLUTE_FILE_REQUIRED")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            metadata = current.lstat()
        except OSError as exc:
            raise MTArtifactRefused("MT_A1_SOURCE_NOT_AVAILABLE") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise MTArtifactRefused("MT_A1_SYMLINK_PATH_FORBIDDEN")
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise MTArtifactRefused("MT_A1_REGULAR_UNLINKED_FILE_REQUIRED")


def _snapshot(path: Path, maximum: int) -> bytes:
    """Read bounded bytes from one inode, check metadata and identity twice.

    This does NOT establish immutable external custody against a privileged
    writer changing bytes then restoring them, nor signed source provenance.
    """
    _regular_path(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or not 0 < before.st_size <= maximum):
                raise MTArtifactRefused("MT_A1_FILE_SIZE_OR_TYPE_FORBIDDEN")
            chunks: list[bytes] = []
            used = 0
            while True:
                data = os.read(fd, min(128 * 1024, maximum + 1 - used))
                if not data:
                    break
                chunks.append(data)
                used += len(data)
                if used > maximum:
                    raise MTArtifactRefused("MT_A1_FILE_SIZE_OR_TYPE_FORBIDDEN")
            after = os.fstat(fd)
            _regular_path(path)
            current = path.stat()
            if (used != before.st_size or
                    (before.st_dev, before.st_ino, before.st_size,
                     before.st_mtime_ns, before.st_ctime_ns)
                    != (after.st_dev, after.st_ino, after.st_size,
                        after.st_mtime_ns, after.st_ctime_ns)
                    or (current.st_dev, current.st_ino, current.st_size,
                        current.st_mtime_ns, current.st_ctime_ns)
                    != (after.st_dev, after.st_ino, after.st_size,
                        after.st_mtime_ns, after.st_ctime_ns)):
                raise MTArtifactRefused("MT_A1_SOURCE_CHANGED_DURING_REVIEW")
            return b"".join(chunks)
        finally:
            os.close(fd)
    except MTArtifactRefused:
        raise
    except OSError as exc:
        raise MTArtifactRefused("MT_A1_FILE_READ_REFUSED") from exc


def _source_metrics(raw: bytes) -> tuple[str, int]:
    if raw.startswith(b"\xef\xbb\xbf"):
        encoding, data = "UTF-8-BOM", raw[3:]
        codec = "utf-8"
    elif raw.startswith(b"\xff\xfe"):
        encoding, data, codec = "UTF-16-LE", raw[2:], "utf-16-le"
    elif raw.startswith(b"\xfe\xff"):
        encoding, data, codec = "UTF-16-BE", raw[2:], "utf-16-be"
    else:
        encoding, data, codec = "UTF-8", raw, "utf-8"
    try:
        decoded = data.decode(codec, errors="strict")
    except UnicodeError as exc:
        raise MTArtifactRefused("MT_A1_SOURCE_TEXT_ENCODING_INVALID") from exc
    if (not decoded.strip() or "\x00" in decoded or "\ufeff" in decoded
            or len(decoded) > _SOURCE_MAX):
        raise MTArtifactRefused("MT_A1_SOURCE_TEXT_INVALID")
    return encoding, len(decoded.splitlines())


def review_metatrader_artifact(
    path: Path, *, expected_sha256: str, platform: MetaTraderPlatform,
    market: Market, symbol: str, timeframe: str, provider_claim: str,
    operator_ack: bool = False,
) -> MetaTraderArtifactReview:
    """Preflight a pinned MQ4/MQ5 source or opaque EX5 binary as *data*.

    Never imports, compiles, runs or dispatches the submitted artifact,
    even if text looks harmless or a binary contains a plausible header.
    """
    data_timeframe = _scope(
        platform=platform, market=market, symbol=symbol, timeframe=timeframe,
        provider_claim=provider_claim, expected_sha256=expected_sha256,
        operator_ack=operator_ack,
    )
    if not isinstance(path, Path):
        raise MTArtifactRefused("MT_A1_ABSOLUTE_FILE_REQUIRED")
    extension = path.suffix.lower()
    mapped = _EXTENSION.get(extension)
    if mapped is None or mapped[0] != platform.value:
        raise MTArtifactRefused("MT_A1_PLATFORM_ARTIFACT_TYPE_MISMATCH")
    maximum = _COMPILED_MAX if extension == ".ex5" else _SOURCE_MAX
    raw = _snapshot(path, maximum)
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise MTArtifactRefused("MT_A1_SOURCE_SHA256_MISMATCH")
    if extension == ".ex5":
        # Proprietary format: no documented header verification, compilation
        # or safe execution can be inferred from the extension or SHA.
        encoding, lines = None, None
    else:
        encoding, lines = _source_metrics(raw)
    return MetaTraderArtifactReview(
        sha256=expected_sha256, size_bytes=len(raw),
        platform=platform.value, artifact_kind=mapped[1],
        declared_market=market.value, declared_symbol=symbol,
        declared_timeframe=timeframe, data_a1_timeframe=data_timeframe,
        provider_claim=provider_claim, source_lines=lines,
        source_encoding=encoding,
    )


__all__ = [
    "MTArtifactRefused", "MetaTraderPlatform", "MetaTraderArtifactReview",
    "review_metatrader_artifact",
]
