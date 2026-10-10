"""Explicit market-session windows with historical IANA DST conversion.

A verified flag is a REQUIRED configuration decision by an approved operator;
this module does not discover exchange holidays or broker trading hours.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .quotes import _utc


@dataclass(frozen=True, slots=True)
class TradingWindow:
    weekday: int  # Monday=0, Sunday=6
    opens: time
    closes: time

    def __post_init__(self) -> None:
        if (
            self.weekday not in range(7)
            or not isinstance(self.opens, time) or not isinstance(self.closes, time)
            or self.opens.tzinfo is not None or self.closes.tzinfo is not None
            or self.opens == self.closes
        ):
            raise ValueError("invalid trading window")


@dataclass(frozen=True, slots=True)
class SessionPolicy:
    timezone_name: str
    windows: tuple[TradingWindow, ...]
    closed_dates: frozenset[date] = frozenset()
    verified: bool = False

    def __post_init__(self) -> None:
        try:
            ZoneInfo(self.timezone_name)
        except (ZoneInfoNotFoundError, TypeError, ValueError) as exc:
            raise ValueError("valid IANA timezone required") from exc
        if not self.windows or any(not isinstance(w, TradingWindow) for w in self.windows):
            raise ValueError("explicit daily windows required")
        if any(not isinstance(d, date) or isinstance(d, datetime) for d in self.closed_dates):
            raise ValueError("invalid closure date")

    def is_open(self, at: datetime) -> bool:
        if not self.verified:
            return False
        local = _utc(at).astimezone(ZoneInfo(self.timezone_name))
        if local.date() in self.closed_dates:
            return False
        for w in self.windows:
            if w.opens < w.closes:
                if local.weekday() == w.weekday and w.opens <= local.time() < w.closes:
                    return True
            else:
                if local.weekday() == w.weekday and local.time() >= w.opens:
                    return True
                yesterday = local.date() - timedelta(days=1)
                if (yesterday.weekday() == w.weekday and local.time() < w.closes
                        and yesterday not in self.closed_dates):
                    return True
        return False
