"""Stage 17: bounded HTTPS capture and local quality acceptance of real USD-M archives.

Research-only. The official HTTPS endpoint and its CHECKSUM are NOT a publisher
signature or independently attested historical point-in-time market truth.
No trading, Brooks evaluation, API keys, operational database, or Telegram.
"""
from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .binance_vision_archive_stage16_v1 import (
    VisionPreparedArchive,
    prepare_vision_monthly_um_15m,
)
from .contracts import Instrument, Market
from .core_api_v1 import CoreEventType, DataOrigin
from .historical_data_loader_a1 import HistoricalFileSpec
from .historical_pit_quality_stage12_v1 import inspect_historical_pit_archive
from .market_data_engine_v1 import FeedDefinition, PriceBasis, VolumeSemantics

_ZIP_LIMIT = 8 * 1024 * 1024
_CHECKSUM_LIMIT = 256
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_HOST = "https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/15m/"
_URL_RE = re.compile(re.escape(_HOST) + r"BTCUSDT-15m-(?:202[0-9]|2030)-(?:0[1-9]|1[0-2])\.zip(?:\.CHECKSUM)?\Z")
_USER_AGENT = "NASERI-MARKETS-Research-Archive-Capture/1"


class Stage17Refused(ValueError):
    """Stable failure codes without source bytes, secrets or response body."""


@dataclass(frozen=True, slots=True)
class Stage17Capture:
    archive: VisionPreparedArchive
    original_zip: bytes = field(repr=False)
    original_checksum: bytes = field(repr=False)
    capture_started_utc: str = ""
    capture_completed_utc: str = ""
    zip_url: str = ""
    checksum_url: str = ""
    operator_hashes_preapproved: bool = False
    source_independently_authenticated: bool = False
    historical_revision_absence_proven: bool = False
    retrieval_clock_independently_attested: bool = False
    point_in_time_market_truth_proven: bool = False
    economic_backtest_run: bool = False
    trading_authorized: bool = False


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Stage17Refused("ST17_UNREVIEWED_HTTP_REDIRECT")


def _assert_nonproduction() -> None:
    if os.environ.get("MMT_NONPRODUCTION") != "1" or "MMT_PRODUCTION" in os.environ:
        raise Stage17Refused("ST17_NONPRODUCTION_ONLY")


def _url_and_month(year: int, month: int) -> tuple[str, str]:
    if type(year) is not int or not 2020 <= year <= 2030 or type(month) is not int or not 1 <= month <= 12:
        raise Stage17Refused("ST17_MONTH_OUT_OF_SCOPE")
    end = (datetime(year + 1, 1, 1, tzinfo=UTC)
           if month == 12 else datetime(year, month + 1, 1, tzinfo=UTC))
    if datetime.now(UTC) <= end:
        raise Stage17Refused("ST17_MONTH_NOT_CLOSED")
    if calendar.monthrange(year, month)[1] * 96 > 3000:
        raise Stage17Refused("ST17_MONTH_TOO_LARGE")
    base = f"BTCUSDT-15m-{year:04d}-{month:02d}.zip"
    return _HOST + base, _HOST + base + ".CHECKSUM"


def _get_exact(url: str, limit: int) -> bytes:
    """Only the hardcoded, same-origin TLS 200 response is accepted."""
    if type(url) is not str or not _URL_RE.fullmatch(url):
        raise Stage17Refused("ST17_ONLY_PINNED_OFFICIAL_ENDPOINT")
    opener = urllib.request.build_opener(_NoRedirect())
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT, "Accept-Encoding": "identity"})
    try:
        with opener.open(req, timeout=20) as reply:
            if (reply.status != 200 or reply.geturl() != url
                    or reply.headers.get("Content-Encoding", "identity").lower() != "identity"):
                raise Stage17Refused("ST17_UNEXPECTED_HTTPS_RESPONSE")
            length = reply.headers.get("Content-Length")
            if length is not None and (not length.isdecimal() or int(length) > limit):
                raise Stage17Refused("ST17_RESPONSE_TOO_LARGE")
            body = reply.read(limit + 1)
    except Stage17Refused:
        raise
    except (OSError, ValueError, TimeoutError, urllib.error.URLError) as exc:
        raise Stage17Refused("ST17_OFFICIAL_ENDPOINT_UNAVAILABLE") from exc
    if not 1 <= len(body) <= limit:
        raise Stage17Refused("ST17_RESPONSE_SIZE_REFUSED")
    return body


def capture_stage17_vision_month(
    *, year: int, month: int, operator_ack: bool,
    expected_zip_sha256: str | None = None,
    expected_checksum_sha256: str | None = None,
) -> Stage17Capture:
    """Capture a closed month over HTTPS and validate with the Stage16 parser.

    Without separate pre-approved hashes this is self-observed checksum only,
    never independent provider authentication. CI tests stub the HTTP transport
    and must never be presented as a real-market capture.
    """
    _assert_nonproduction()
    if operator_ack is not True:
        raise Stage17Refused("ST17_EXPLICIT_OPERATOR_ACK_REQUIRED")
    url, checksum_url = _url_and_month(year, month)
    pinned = expected_zip_sha256 is not None or expected_checksum_sha256 is not None
    if pinned and (
        type(expected_zip_sha256) is not str or not _SHA.fullmatch(expected_zip_sha256)
        or type(expected_checksum_sha256) is not str or not _SHA.fullmatch(expected_checksum_sha256)
    ):
        raise Stage17Refused("ST17_BOTH_PREAPPROVED_SHA256_REQUIRED")
    started = datetime.now(UTC)
    archive_bytes = _get_exact(url, _ZIP_LIMIT)
    checksum_bytes = _get_exact(checksum_url, _CHECKSUM_LIMIT)
    completed = datetime.now(UTC)
    zip_hash = hashlib.sha256(archive_bytes).hexdigest()
    checksum_hash = hashlib.sha256(checksum_bytes).hexdigest()
    if pinned and (zip_hash != expected_zip_sha256 or checksum_hash != expected_checksum_sha256):
        raise Stage17Refused("ST17_OPERATOR_SHA256_PIN_MISMATCH")
    parsed = prepare_vision_monthly_um_15m(
        archive_bytes, checksum_bytes,
        expected_zip_sha256=expected_zip_sha256 if pinned else zip_hash,
        expected_checksum_sha256=expected_checksum_sha256 if pinned else checksum_hash,
        year=year, month=month, retrieved_at_utc=completed, operator_ack=True,
    )
    return Stage17Capture(
        archive=parsed, original_zip=archive_bytes, original_checksum=checksum_bytes,
        capture_started_utc=started.isoformat(), capture_completed_utc=completed.isoformat(),
        zip_url=url, checksum_url=checksum_url, operator_hashes_preapproved=pinned,
    )



def import_stage17_vision_month_offline(
    zip_path: Path, checksum_path: Path, *, year: int, month: int,
    operator_ack: bool, expected_zip_sha256: str | None = None,
    expected_checksum_sha256: str | None = None,
) -> Stage17Capture:
    """Import original operator-supplied ZIP/CHECKSUM without ANY network access.

    Retains identical Stage16 strict month and checksum verification. A local
    import time is not the historical archive acquisition time or publisher
    signature; no independent authenticity/clock flag is ever set.
    """
    import stat

    _assert_nonproduction()
    if operator_ack is not True:
        raise Stage17Refused("ST17_EXPLICIT_OPERATOR_ACK_REQUIRED")
    url, checksum_url = _url_and_month(year, month)
    archive_name = url.rsplit("/", 1)[-1]
    if (not isinstance(zip_path, Path) or not isinstance(checksum_path, Path)
            or not zip_path.is_absolute() or not checksum_path.is_absolute()
            or zip_path.name != archive_name
            or checksum_path.name != archive_name + ".CHECKSUM"
            or zip_path.parent != checksum_path.parent
            or any(parent.is_symlink() for parent in zip_path.parents)
            or any(part in ("production_source", ".git", "secrets", "checkpoints")
                   for part in zip_path.parts)):
        raise Stage17Refused("ST17_EXACT_ISOLATED_OFFLINE_INPUT_PATHS_REQUIRED")
    pins_supplied = expected_zip_sha256 is not None or expected_checksum_sha256 is not None
    if pins_supplied and (
        type(expected_zip_sha256) is not str or not _SHA.fullmatch(expected_zip_sha256)
        or type(expected_checksum_sha256) is not str
        or not _SHA.fullmatch(expected_checksum_sha256)
    ):
        raise Stage17Refused("ST17_BOTH_PREAPPROVED_SHA256_REQUIRED")

    def read_original(path: Path, max_bytes: int) -> bytes:
        # Refuse symlink targets, directories, FIFOs and oversized files before
        # reading. O_NOFOLLOW + fstat mitigate target substitution via symlink.
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        try:
            fd = os.open(path, flags)
            with os.fdopen(fd, "rb") as source:
                metadata = os.fstat(source.fileno())
                if not stat.S_ISREG(metadata.st_mode) or not 1 <= metadata.st_size <= max_bytes:
                    raise Stage17Refused("ST17_OFFLINE_FILE_TYPE_OR_SIZE_REFUSED")
                data = source.read(max_bytes + 1)
                if len(data) != metadata.st_size:
                    raise Stage17Refused("ST17_OFFLINE_FILE_CHANGED_WHILE_READING")
                return data
        except Stage17Refused:
            raise
        except OSError as exc:
            raise Stage17Refused("ST17_OFFLINE_FILE_UNAVAILABLE") from exc

    started = datetime.now(UTC)
    archive_bytes = read_original(zip_path, _ZIP_LIMIT)
    checksum_bytes = read_original(checksum_path, _CHECKSUM_LIMIT)
    completed = datetime.now(UTC)
    zip_sha = hashlib.sha256(archive_bytes).hexdigest()
    checksum_sha = hashlib.sha256(checksum_bytes).hexdigest()
    if pins_supplied and (zip_sha != expected_zip_sha256
                          or checksum_sha != expected_checksum_sha256):
        raise Stage17Refused("ST17_OPERATOR_SHA256_PIN_MISMATCH")
    prepared = prepare_vision_monthly_um_15m(
        archive_bytes, checksum_bytes,
        expected_zip_sha256=expected_zip_sha256 if pins_supplied else zip_sha,
        expected_checksum_sha256=expected_checksum_sha256 if pins_supplied else checksum_sha,
        year=year, month=month, retrieved_at_utc=completed, operator_ack=True,
    )
    return Stage17Capture(
        archive=prepared, original_zip=archive_bytes,
        original_checksum=checksum_bytes,
        capture_started_utc=started.isoformat(),
        capture_completed_utc=completed.isoformat(),
        zip_url=url, checksum_url=checksum_url,
        operator_hashes_preapproved=pins_supplied,
    )


def _make_stage12_spec(sha256: str) -> HistoricalFileSpec:
    feed = FeedDefinition(
        "stage16_binance_vision_um_btcusdt",
        Instrument(Market.CRYPTO, "binance_replay", "BTCUSDT", "UTC", "USDT"),
        "15m", CoreEventType.CLOSED_CANDLE, DataOrigin.REPLAY,
        "hist_" + sha256[:40], PriceBasis.TRADE, VolumeSemantics.TRADED,
        max_latency_seconds=120,
    )
    return HistoricalFileSpec(feed, sha256, 5)


def persist_research_capture(capture: Stage17Capture, *, destination: Path) -> dict:
    """Create a new private research directory; never overwrite any file."""
    _assert_nonproduction()
    if type(capture) is not Stage17Capture or not isinstance(destination, Path):
        raise Stage17Refused("ST17_CAPTURE_OR_PATH_REQUIRED")
    if not destination.is_absolute() or destination.exists() or destination.is_symlink():
        raise Stage17Refused("ST17_FRESH_ABSOLUTE_DESTINATION_REQUIRED")
    if (any(p.is_symlink() for p in destination.parents)
            or any(p in ("production_source", ".git", "secrets", "checkpoints")
                   for p in destination.parts)
            or not destination.parent.is_dir()):
        raise Stage17Refused("ST17_RESEARCH_DESTINATION_UNSAFE")
    if (not _URL_RE.fullmatch(capture.zip_url)
            or not capture.zip_url.endswith(".zip")
            or capture.checksum_url != capture.zip_url + ".CHECKSUM"
            or capture.archive.official_url_claim != capture.zip_url):
        raise Stage17Refused("ST17_OFFICIAL_CAPTURE_IDENTITY_REQUIRED")
    if (hashlib.sha256(capture.original_zip).hexdigest() != capture.archive.zip_sha256
            or hashlib.sha256(capture.original_checksum).hexdigest() != capture.archive.checksum_sha256
            or hashlib.sha256(capture.archive.canonical_csv_bytes).hexdigest() != capture.archive.csv_sha256):
        raise Stage17Refused("ST17_CAPTURE_CHANGED_AFTER_VALIDATION")
    destination.mkdir(mode=0o700)
    def write_private(name: str, data: bytes) -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(destination / name, flags, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())

    basename = capture.zip_url.rsplit("/", 1)[-1]
    write_private(basename, capture.original_zip)
    write_private(basename + ".CHECKSUM", capture.original_checksum)
    write_private("canonical-month.csv", capture.archive.canonical_csv_bytes)
    write_private("stage12-receipt.json", capture.archive.stage12_receipt_bytes)
    # Validate the real persisted CSV with the existing Stage12 PIT-quality gate.
    stage12 = inspect_historical_pit_archive(
        destination / "canonical-month.csv",
        _make_stage12_spec(capture.archive.csv_sha256),
        receipt_bytes=capture.archive.stage12_receipt_bytes,
        trusted_receipt_sha256=capture.archive.receipt_sha256,
        as_of_utc=datetime.now(UTC),
        operator_ack=True,
    )
    report = {
        "stage": "STAGE17_OFFICIAL_HTTPS_CAPTURE_AND_LOCAL_QUALITY_V1",
        "status": "CAPTURED_AND_LOCALLY_VALIDATED_SOURCE_UNATTESTED",
        "captured_from_https_url": capture.zip_url,
        "checksum_url": capture.checksum_url,
        "capture_started_utc_local_clock": capture.capture_started_utc,
        "capture_completed_utc_local_clock": capture.capture_completed_utc,
        "original_zip_sha256": capture.archive.zip_sha256,
        "original_checksum_sha256": capture.archive.checksum_sha256,
        "canonical_csv_sha256": capture.archive.csv_sha256,
        "stage12_receipt_sha256": capture.archive.receipt_sha256,
        "stage12_evidence_sha256": stage12.evidence_sha256,
        "rows": stage12.rows_validated,
        "zero_volume_rows": stage12.zero_volume_rows,
        "first_open_utc": capture.archive.first_open_utc,
        "last_close_utc": capture.archive.last_close_utc,
        "preapproved_hashes_matched": capture.operator_hashes_preapproved,
        "source_independently_authenticated": False,
        "retrieval_clock_independently_attested": False,
        "historical_revisions_excluded": False,
        "mark_funding_orderbook_verified": False,
        "walk_forward_oos_executed": False,
        "profitability_proven": False,
        "production_authorized": False,
    }
    write_private("quality-report.json", (json.dumps(report, indent=2, sort_keys=True) + "\n").encode())
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage17 nonproduction official archive capture")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--zip-sha256")
    parser.add_argument("--checksum-sha256")
    parser.add_argument("--ack-nonproduction", action="store_true")
    args = parser.parse_args()
    try:
        captured = capture_stage17_vision_month(
            year=args.year, month=args.month, operator_ack=args.ack_nonproduction,
            expected_zip_sha256=args.zip_sha256,
            expected_checksum_sha256=args.checksum_sha256,
        )
        report = persist_research_capture(captured, destination=args.destination)
    except (Stage17Refused, ValueError, OSError) as exc:
        error_code = str(exc)
        if not re.fullmatch(r"(?:ST16|ST17|PIT|HIST)_[A-Z0-9_]+", error_code):
            error_code = "ST17_CAPTURE_OR_LOCAL_QUALITY_FAILURE"
        print(json.dumps({"status": "REFUSED", "reason": error_code}))
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
