"""MT-A1 local MQ4/MQ5/EX5 review-only contracts, not terminal execution."""
from __future__ import annotations

import hashlib
import os
import socket
import subprocess
from pathlib import Path

import pytest

from naseri_markets.contracts import Market
from naseri_markets.mt_a1_offline_artifact_preflight import (
    MetaTraderPlatform,
    MTArtifactRefused,
    review_metatrader_artifact,
)
from naseri_markets.runtime_a6_dispatch_fence import (
    RuntimeA6Denied,
    require_worker_launch,
)

MQ4 = b'#property strict\nint OnInit() { return(INIT_SUCCEEDED); }\n'
MQ5 = b'#property version "1.0"\nvoid OnTick() { }\n'
EX5 = b"\x00\x80\xfe\x02opaque test bytes which do NOT verify a real EX5"
SUPPORTED = [
    (".mq4", MetaTraderPlatform.MT4, MQ4, "MQL4_SOURCE"),
    (".mq5", MetaTraderPlatform.MT5, MQ5, "MQL5_SOURCE"),
    (".ex5", MetaTraderPlatform.MT5, EX5, "EX5_OPAQUE_BINARY"),
]


@pytest.fixture(autouse=True)
def _nonprod(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def _file(tmp_path: Path, extension: str, contents: bytes):
    path = tmp_path / ("operator-submitted" + extension)
    path.write_bytes(contents)
    return path


def _kwargs(platform: MetaTraderPlatform, contents: bytes, **override):
    defaults = dict(
        expected_sha256=hashlib.sha256(contents).hexdigest(),
        platform=platform, market=Market.FOREX,
        symbol="EURUSD.a", timeframe="M15", provider_claim="declared_demo_source",
        operator_ack=True,
    )
    defaults.update(override)
    return defaults


@pytest.mark.parametrize(("ext", "platform", "content", "expected"), SUPPORTED)
def test_three_file_formats_review_as_inert_bytes(tmp_path, ext, platform, content, expected):
    path = _file(tmp_path, ext, content)
    before = path.stat()
    result = review_metatrader_artifact(path, **_kwargs(platform, content))
    assert result.artifact_kind == expected
    assert result.sha256 == hashlib.sha256(content).hexdigest()
    assert result.size_bytes == len(content)
    assert result.platform == platform.value
    assert result.declared_market == Market.FOREX.value
    assert result.declared_symbol == "EURUSD.a"
    assert result.declared_timeframe == "M15"
    assert result.data_a1_timeframe == "15m"
    assert result.provider_claim == "declared_demo_source"
    assert result.status == "MT_A1_LOCAL_ARTIFACT_BYTES_REVIEWED_NO_TERMINAL_EXECUTION"
    assert not result.real_terminal_connected
    assert not result.ex5_format_verified
    assert not result.mt_source_compiled
    assert not result.broker_source_authenticated
    assert not result.platform_account_verified
    assert not result.market_data_observed
    assert not result.point_in_time_verified
    assert not result.paper_strategy_executed
    assert not result.broker_order_sent
    assert not result.telegram_sent
    assert not result.worker_execution_authorized
    assert not result.quarantine_release_authorized
    assert before.st_mtime_ns == path.stat().st_mtime_ns
    assert path.read_bytes() == content
    assert [x.name for x in tmp_path.iterdir()] == [path.name]
    if ext == ".ex5":
        assert result.source_lines is None
        assert result.source_encoding is None
    else:
        assert result.source_lines == 2
        assert result.source_encoding == "UTF-8"


@pytest.mark.parametrize(("platform", "tf", "data"), [
    (MetaTraderPlatform.MT4, "M1", "1m"),
    (MetaTraderPlatform.MT4, "M5", "5m"),
    (MetaTraderPlatform.MT4, "M15", "15m"),
    (MetaTraderPlatform.MT4, "M30", "30m"),
    (MetaTraderPlatform.MT4, "H1", "1h"),
    (MetaTraderPlatform.MT4, "H4", "4h"),
    (MetaTraderPlatform.MT4, "D1", "1d"),
    (MetaTraderPlatform.MT5, "H12", "12h"),
])
def test_broker_timeframe_to_data_a1_normalization(tmp_path, platform, tf, data):
    ext, raw = (".mq4", MQ4) if platform is MetaTraderPlatform.MT4 else (".mq5", MQ5)
    path = _file(tmp_path, ext, raw)
    result = review_metatrader_artifact(
        path, **_kwargs(platform, raw, timeframe=tf),
    )
    assert result.data_a1_timeframe == data


def test_nonstandard_mt4_h12_is_refused(tmp_path):
    path = _file(tmp_path, ".mq4", MQ4)
    with pytest.raises(MTArtifactRefused, match="MT_A1_EXACT_SYMBOL_TIMEFRAME_AND_SHA_REQUIRED"):
        review_metatrader_artifact(
            path, **_kwargs(MetaTraderPlatform.MT4, MQ4, timeframe="H12"),
        )


@pytest.mark.parametrize(("ext", "platform", "raw"), [
    (".mq4", MetaTraderPlatform.MT5, MQ4),
    (".mq5", MetaTraderPlatform.MT4, MQ5),
    (".ex5", MetaTraderPlatform.MT4, EX5),
    (".ex4", MetaTraderPlatform.MT4, EX5),
    (".exe", MetaTraderPlatform.MT5, EX5),
    (".dll", MetaTraderPlatform.MT5, EX5),
])
def test_wrong_platform_or_unapproved_extension_denied(tmp_path, ext, platform, raw):
    path = _file(tmp_path, ext, raw)
    with pytest.raises(MTArtifactRefused, match="MT_A1_PLATFORM_ARTIFACT_TYPE_MISMATCH"):
        review_metatrader_artifact(path, **_kwargs(platform, raw))


def test_utf8_bom_utf16le_and_utf16be_sources(tmp_path):
    source = '#property version "1.0"\nvoid OnTick() { }\n'
    for value, encoding in [
        (b"\xef\xbb\xbf" + source.encode("utf-8"), "UTF-8-BOM"),
        (b"\xff\xfe" + source.encode("utf-16-le"), "UTF-16-LE"),
        (b"\xfe\xff" + source.encode("utf-16-be"), "UTF-16-BE"),
    ]:
        path = _file(tmp_path, ".mq5", value)
        review = review_metatrader_artifact(
            path, **_kwargs(MetaTraderPlatform.MT5, value),
        )
        assert review.source_encoding == encoding
        assert review.source_lines == 2


@pytest.mark.parametrize("raw", [
    b"\x00not-mql",
    b"\xffinvalid-utf8",
    b"   \r\n",
    b"int x;\x00int y;",
    b"\xef\xbb\xbfint a;\xef\xbb\xbfint b;",
])
def test_invalid_mql_text_is_denied(tmp_path, raw):
    path = _file(tmp_path, ".mq5", raw)
    with pytest.raises(MTArtifactRefused, match="MT_A1_SOURCE_TEXT_"):
        review_metatrader_artifact(path, **_kwargs(MetaTraderPlatform.MT5, raw))


def test_digest_mismatch_rejected_not_compiled(tmp_path):
    path = _file(tmp_path, ".mq5", MQ5)
    with pytest.raises(MTArtifactRefused, match="MT_A1_SOURCE_SHA256_MISMATCH"):
        review_metatrader_artifact(
            path, **_kwargs(MetaTraderPlatform.MT5, MQ5,
                            expected_sha256="f" * 64),
        )


@pytest.mark.parametrize("bad", [
    "BTC/USDT", "🪙", "", " ", "\nEURUSD", "A" * 65,
])
def test_unsafe_symbol_refused(tmp_path, bad):
    path = _file(tmp_path, ".mq5", MQ5)
    with pytest.raises(MTArtifactRefused, match="MT_A1_EXACT_SYMBOL"):
        review_metatrader_artifact(
            path, **_kwargs(MetaTraderPlatform.MT5, MQ5, symbol=bad),
        )


def test_invalid_declared_scope_and_boolean_hash_refused(tmp_path):
    path = _file(tmp_path, ".mq5", MQ5)
    for update in [
        {"expected_sha256": "A" * 64},
        {"expected_sha256": True},
        {"platform": "MT5"},
        {"market": "forex"},
        {"timeframe": "M2"},
        {"provider_claim": "broker source with spaces"},
    ]:
        options = _kwargs(MetaTraderPlatform.MT5, MQ5)
        options.update(update)
        with pytest.raises(MTArtifactRefused, match="MT_A1_EXACT_SYMBOL"):
            review_metatrader_artifact(path, **options)


def test_file_symlink_hardlink_and_relative_path_rejected(tmp_path):
    path = _file(tmp_path, ".mq5", MQ5)
    with pytest.raises(MTArtifactRefused, match="MT_A1_ABSOLUTE_FILE_REQUIRED"):
        review_metatrader_artifact(
            Path("source.mq5"), **_kwargs(MetaTraderPlatform.MT5, MQ5),
        )
    alias = tmp_path / "alias.mq5"
    alias.symlink_to(path)
    with pytest.raises(MTArtifactRefused, match="MT_A1_SYMLINK_PATH_FORBIDDEN"):
        review_metatrader_artifact(
            alias, **_kwargs(MetaTraderPlatform.MT5, MQ5),
        )
    alias.unlink()
    os.link(path, alias)
    with pytest.raises(MTArtifactRefused, match="MT_A1_REGULAR_UNLINKED_FILE_REQUIRED"):
        review_metatrader_artifact(
            path, **_kwargs(MetaTraderPlatform.MT5, MQ5),
        )


@pytest.mark.parametrize("raw", [b"", b"x" * (8 * 1024 * 1024 + 1)])
def test_empty_and_oversized_mq5_denied(tmp_path, raw):
    path = _file(tmp_path, ".mq5", raw)
    with pytest.raises(MTArtifactRefused, match="MT_A1_FILE_SIZE_OR_TYPE_FORBIDDEN"):
        review_metatrader_artifact(
            path, **_kwargs(MetaTraderPlatform.MT5, raw),
        )


def test_empty_ex5_refused_without_attempt_to_open_terminal(tmp_path):
    path = _file(tmp_path, ".ex5", b"")
    with pytest.raises(MTArtifactRefused, match="MT_A1_FILE_SIZE_OR_TYPE_FORBIDDEN"):
        review_metatrader_artifact(
            path, **_kwargs(MetaTraderPlatform.MT5, b""),
        )


def test_production_env_missing_ack_and_account_not_interacted(tmp_path, monkeypatch):
    path = _file(tmp_path, ".mq5", MQ5)
    with pytest.raises(MTArtifactRefused, match="MT_A1_EXPLICIT_NONPRODUCTION_ACK_REQUIRED"):
        review_metatrader_artifact(
            path, **_kwargs(MetaTraderPlatform.MT5, MQ5, operator_ack=False),
        )
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(MTArtifactRefused, match="MT_A1_EXPLICIT_NONPRODUCTION_ACK_REQUIRED"):
        review_metatrader_artifact(path, **_kwargs(MetaTraderPlatform.MT5, MQ5))
    monkeypatch.delenv("MMT_PRODUCTION")
    monkeypatch.delenv("MMT_NONPRODUCTION")
    with pytest.raises(MTArtifactRefused, match="MT_A1_EXPLICIT_NONPRODUCTION_ACK_REQUIRED"):
        review_metatrader_artifact(path, **_kwargs(MetaTraderPlatform.MT5, MQ5))


def test_no_process_socket_broker_import_or_a6_bypass(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("MT_A1_MUST_NOT_EXECUTE_OR_OPEN_NETWORK")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    path = _file(tmp_path, ".ex5", EX5)
    result = review_metatrader_artifact(
        path, **_kwargs(MetaTraderPlatform.MT5, EX5),
    )
    assert result.artifact_kind == "EX5_OPAQUE_BINARY"
    assert not result.mt_source_compiled
    assert not result.worker_execution_authorized
    with pytest.raises(RuntimeA6Denied):
        require_worker_launch(None, b"")
