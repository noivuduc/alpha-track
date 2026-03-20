"""
Market calendar — determines the current US stock market state.

All times are configurable via Settings so they can be updated when
the US changes DST rules or market hours shift.

Usage::

    from app.services.market_calendar import get_market_status, is_market_open

    status = get_market_status()
    # {"state": "open", "label": "Market Open", "next_change": "...", "countdown": "Closes in 2h 15m"}
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.config import get_settings

settings = get_settings()

# US market holidays for the current year — update annually or load from a feed.
# These are *observed* dates (if holiday falls on weekend, the observed weekday).
_HOLIDAYS_2026 = {
    "2026-01-01",  # New Year's Day
    "2026-01-19",  # MLK Jr. Day
    "2026-02-16",  # Presidents' Day
    "2026-04-03",  # Good Friday
    "2026-05-25",  # Memorial Day
    "2026-07-03",  # Independence Day (observed)
    "2026-09-07",  # Labor Day
    "2026-11-26",  # Thanksgiving
    "2026-12-25",  # Christmas
}

_HOLIDAYS_2027 = {
    "2027-01-01",  # New Year's Day
    "2027-01-18",  # MLK Jr. Day
    "2027-02-15",  # Presidents' Day
    "2027-03-26",  # Good Friday
    "2027-05-31",  # Memorial Day
    "2027-07-05",  # Independence Day (observed)
    "2027-09-06",  # Labor Day
    "2027-11-25",  # Thanksgiving
    "2027-12-24",  # Christmas (observed)
}

HOLIDAYS = _HOLIDAYS_2026 | _HOLIDAYS_2027


def _tz() -> ZoneInfo:
    return ZoneInfo(settings.MARKET_TIMEZONE)


def _parse_time(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def _is_trading_day(dt: datetime) -> bool:
    if dt.weekday() >= 5:
        return False
    return dt.strftime("%Y-%m-%d") not in HOLIDAYS


def _next_trading_day(dt: datetime) -> datetime:
    """Return the start of the next trading day (midnight market tz)."""
    d = dt + timedelta(days=1)
    while not _is_trading_day(d):
        d += timedelta(days=1)
    return d.replace(hour=0, minute=0, second=0, microsecond=0)


def _countdown(seconds: float) -> str:
    s = max(0, int(seconds))
    if s < 60:
        return f"{s}s"
    m = s // 60
    if m < 60:
        return f"{m}m"
    h, m = divmod(m, 60)
    if h < 24:
        return f"{h}h {m}m" if m else f"{h}h"
    d, h = divmod(h, 24)
    return f"{d}d {h}h" if h else f"{d}d"


def get_market_status(now_utc: datetime | None = None) -> dict:
    """
    Return the current market state and next transition.

    Returns::

        {
            "state":       "pre_market" | "open" | "after_hours" | "closed",
            "label":       "Market Open",
            "next_change": "2026-03-19T20:00:00-04:00",
            "countdown":   "Closes in 2h 15m",
            "is_trading":  True,          # True if prices are updating
            "timezone":    "America/New_York",
        }
    """
    tz = _tz()
    now = (now_utc or datetime.utcnow()).astimezone(tz) if now_utc else datetime.now(tz)

    pre_open   = _parse_time(settings.MARKET_PREMARKET_OPEN)
    reg_open   = _parse_time(settings.MARKET_REGULAR_OPEN)
    reg_close  = _parse_time(settings.MARKET_REGULAR_CLOSE)
    ah_close   = _parse_time(settings.MARKET_AFTERHOURS_CLOSE)

    t = now.time()
    trading_day = _is_trading_day(now)

    if not trading_day:
        nxt = _next_trading_day(now)
        next_open = nxt.replace(hour=pre_open.hour, minute=pre_open.minute, tzinfo=tz)
        delta = (next_open - now).total_seconds()
        return _build("closed", "Market Closed", next_open, delta, False, tz)

    if t < pre_open:
        next_change = now.replace(hour=pre_open.hour, minute=pre_open.minute, second=0, microsecond=0)
        delta = (next_change - now).total_seconds()
        return _build("closed", "Market Closed", next_change, delta, False, tz)

    if t < reg_open:
        next_change = now.replace(hour=reg_open.hour, minute=reg_open.minute, second=0, microsecond=0)
        delta = (next_change - now).total_seconds()
        return _build("pre_market", "Pre-Market", next_change, delta, True, tz)

    if t < reg_close:
        next_change = now.replace(hour=reg_close.hour, minute=reg_close.minute, second=0, microsecond=0)
        delta = (next_change - now).total_seconds()
        return _build("open", "Market Open", next_change, delta, True, tz)

    if t < ah_close:
        next_change = now.replace(hour=ah_close.hour, minute=ah_close.minute, second=0, microsecond=0)
        delta = (next_change - now).total_seconds()
        return _build("after_hours", "After Hours", next_change, delta, True, tz)

    # After ah_close — closed until next trading day
    nxt = _next_trading_day(now)
    next_open = nxt.replace(hour=pre_open.hour, minute=pre_open.minute, tzinfo=tz)
    delta = (next_open - now).total_seconds()
    return _build("closed", "Market Closed", next_open, delta, False, tz)


def _build(state: str, label: str, next_change: datetime, delta: float, is_trading: bool, tz: ZoneInfo) -> dict:
    if state == "closed":
        action = "Opens in"
    elif state == "pre_market":
        action = "Opens in"
    elif state == "open":
        action = "Closes in"
    else:
        action = "Closes in"

    return {
        "state": state,
        "label": label,
        "next_change": next_change.isoformat(),
        "countdown": f"{action} {_countdown(delta)}",
        "is_trading": is_trading,
        "timezone": str(tz),
    }


def is_market_open() -> bool:
    """Quick check: should we fetch prices right now?"""
    return get_market_status()["is_trading"]


def get_price_interval() -> int:
    """Return the appropriate fetch interval in seconds for the current market state."""
    status = get_market_status()
    state = status["state"]
    if state == "open":
        return settings.PRICE_INTERVAL_REGULAR
    if state in ("pre_market", "after_hours"):
        return settings.PRICE_INTERVAL_EXTENDED
    return settings.PRICE_INTERVAL_CLOSED
