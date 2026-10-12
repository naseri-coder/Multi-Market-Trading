"""Stage 21: pure fixture tests, no actual external HTTP or account access."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

from naseri_markets.contracts import Instrument, Market
from naseri_markets.core_api_v1 import (
    CoreBinding, DataOrigin, CoreEventType,
)
from naseri_markets.example_dual_setup_core_v1 import DualSetupExampleCore
from naseri_markets.kucoin_futures_replay_stage21_v1 import (
    FuturesKlineRequest, VenueReplayRefused, observe_public_futures_klines,
    offline_replay_to_core_inputs, parse_futures_klines,
)

T0 = datetime(2026, 10, 12, 10, tzinfo=UTC)
STEP = timedelta(minutes=15)
QUERY = FuturesKlineRequest("XBTUSDTM", "15m", T0, T0 + 3 * STEP)


def payload(request=QUERY, *, timestamps=None, prices=None):
    start = int(request.start.timestamp() * 1000)
    step = 15 * 60000
    if timestamps is None:
        timestamps = [start + n * step for n in range(request.expected_bars)]
    return json.dumps({"code": "200000", "data": [
        [ts, *(prices or [100, 108, 99, 106, 2, 300])]
        for ts in timestamps
    ]}).encode("utf-8")


def test_bounded_official_format_and_exact_offline_replay():
    source = payload()
    capture = parse_futures_klines(
        source, QUERY, observed_at=QUERY.end + timedelta(minutes=1))
    assert capture.raw_sha256 and capture.report()["independent_provenance_verified"] is False
    assert len(capture.candles) == 3
    assert capture.candles[0].open == D(100)
    assert capture.candles[-1].close == D(106)
    binding = CoreBinding("pilot_instance", "pilot_binding",
                          Instrument(Market.CRYPTO, "kucoin_futures",
                                     "XBTUSDTM", "UTC", "USDT"), "15m")
    events = offline_replay_to_core_inputs(
        capture, manifest=DualSetupExampleCore().manifest, binding=binding)
    assert len(events) == 2
    assert all(event.origin is DataOrigin.REPLAY for event in events)
    assert all(event.event is CoreEventType.CLOSED_CANDLE for event in events)
    assert events[-1].source_ref == capture.source_ref
    assert events[-1].observed_at == QUERY.end
    bad_binding = CoreBinding("pilot_instance", "other_binding",
                              Instrument(Market.CRYPTO, "kucoin_futures",
                                         "ETHUSDTM", "UTC", "USDT"), "15m")
    with pytest.raises(VenueReplayRefused, match="BINDING"):
        offline_replay_to_core_inputs(
            capture, manifest=DualSetupExampleCore().manifest,
            binding=bad_binding)


@pytest.mark.parametrize("raw", [
    b'{"code":"200000","data":[]}',
    b'{"code":"200000","code":"200000","data":[]}',
    b'{"code":"400100","data":[]}',
    b'{"code":"200000","data":[[1,1,1,1,1,1,1]]}',
    b'{"code":"200000","data":[[0,NaN,1,1,1,1,1]]}',
    payload(timestamps=[int(T0.timestamp()*1000)] * 3),
    payload(timestamps=[
        int(T0.timestamp()*1000),
        int((T0+STEP).timestamp()*1000),
        int((T0+3*STEP).timestamp()*1000),
    ]),
    payload(prices=[100, 95, 98, 105, 1, 2]),
])
def test_malformed_incomplete_duplicate_gap_and_bad_ohlc_fail_closed(raw):
    with pytest.raises(VenueReplayRefused):
        parse_futures_klines(raw, QUERY, observed_at=QUERY.end)


def test_reject_future_or_partial_window_and_bad_requests():
    with pytest.raises(VenueReplayRefused, match="INCOMPLETE"):
        parse_futures_klines(payload(), QUERY,
                             observed_at=QUERY.end - timedelta(seconds=1))
    with pytest.raises(VenueReplayRefused, match="ALIGNED"):
        FuturesKlineRequest("XBTUSDTM", "15m", T0 + timedelta(seconds=1),
                            T0 + 3 * STEP)
    with pytest.raises(VenueReplayRefused, match="INSTRUMENT"):
        FuturesKlineRequest("XBT/USDTM", "15m", T0, T0 + 3 * STEP)
    with pytest.raises(VenueReplayRefused, match="BOUNDED"):
        FuturesKlineRequest("XBTUSDTM", "15m", T0, T0 + 129 * STEP)


def test_opt_in_public_get_path_and_injected_transport_label(monkeypatch):
    monkeypatch.delenv("MMT_NONPRODUCTION", raising=False)
    network = []
    def transport(url):
        network.append(url)
        return payload()
    with pytest.raises(VenueReplayRefused, match="EXPLICIT_NONPRODUCTION"):
        observe_public_futures_klines(
            QUERY, observed_at=QUERY.end, operator_ack=True, transport=transport)
    assert not network
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    with pytest.raises(VenueReplayRefused, match="EXPLICIT_NONPRODUCTION"):
        observe_public_futures_klines(
            QUERY, observed_at=QUERY.end, transport=transport)
    assert not network
    result = observe_public_futures_klines(
        QUERY, observed_at=QUERY.end, operator_ack=True, transport=transport)
    assert len(network) == 1
    assert network[0].startswith(
        "https://api-futures.kucoin.com/api/v1/kline/query?")
    assert "symbol=XBTUSDTM" in network[0]
    assert result.origin == "INJECTED_TEST_TRANSPORT"
    assert result.report()["trading_authorized"] is False
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(VenueReplayRefused, match="EXPLICIT_NONPRODUCTION"):
        observe_public_futures_klines(
            QUERY, observed_at=QUERY.end, operator_ack=True, transport=transport)
    assert len(network) == 1
