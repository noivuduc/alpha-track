"""
Performance chart series and summary statistics.

NumPy is used for drawdown computation, skewness/kurtosis, and
any bulk array operations.  List outputs preserve API compatibility.
"""
from __future__ import annotations

import statistics as _stats

import numpy as np

from datetime import date as _date  # noqa: E402 — used inside compute_daily_return_heatmap

from .constants import MONTHS
from .math_utils import pct_change


def drawdown_series(dates: list[str], closes: list[float]) -> list[dict]:
    """
    Running peak-to-trough drawdown at each date.

    Returns list of {"date": str, "drawdown": float (negative %)}.
    Uses np.maximum.accumulate for O(n) vectorised computation.
    """
    if not closes:
        return []
    c           = np.asarray(closes, dtype=np.float64)
    running_max = np.maximum.accumulate(c)
    dd          = np.where(running_max > 0, (c - running_max) / running_max * 100, 0.0)
    dd_r        = np.round(dd, 4)
    nd          = len(dates)
    return [
        {"date": dates[i] if i < nd else "", "drawdown": float(dd_r[i])}
        for i in range(len(c))
    ]


def monthly_returns(dates: list[str], values: list[float]) -> list[dict]:
    """
    Aggregate a daily value series into monthly returns.

    Returns list of {"year", "month", "label", "value" (%)}.

    NOTE: Use monthly_returns_twr() when a TWR daily return series is
    available — this function uses first/last NAV values and is biased by
    capital injections that occur mid-month.
    """
    if len(dates) < 2 or len(dates) != len(values):
        return []

    buckets: dict[str, tuple[float, float]] = {}
    for d, v in zip(dates, values):
        key = d[:7]
        if key not in buckets:
            buckets[key] = (v, v)
        buckets[key] = (buckets[key][0], v)

    result = []
    for key in sorted(buckets):
        start, end = buckets[key]
        y, m = int(key[:4]), int(key[5:7])
        ret  = (end - start) / start * 100 if start else 0.0
        result.append({
            "year":  y,
            "month": m,
            "label": MONTHS[m - 1],
            "value": round(ret, 4),
        })
    return result


def monthly_returns_twr(
    dates:   list[str],
    returns: list[float],
) -> list[dict]:
    """
    Aggregate daily TWR returns into calendar-month returns by compounding.

    For each month M the return is:

        R_M = product of (1 + R_t) for every trading day t in M, minus 1

    This is the correct TWR aggregation: because daily returns already have
    capital flows stripped out, compounding them gives a cash-flow-neutral
    monthly return — even when new lots were added mid-month.

    Args:
        dates:   active_dates[1:] — N-1 trading dates aligned with returns
        returns: daily TWR decimal returns from compute_twr_returns()

    Returns:
        List of {"year", "month", "label", "value" (%)} sorted chronologically.
    """
    if not dates or len(dates) != len(returns):
        return []

    # Compound gross return factor (1 + R) within each YYYY-MM bucket
    factors: dict[str, float] = {}
    order:   list[str]        = []

    for d, r in zip(dates, returns):
        key = d[:7]                         # "YYYY-MM"
        if key not in factors:
            order.append(key)
            factors[key] = 1.0
        factors[key] *= (1.0 + r)

    result = []
    for key in order:
        y, m = int(key[:4]), int(key[5:7])
        ret  = (factors[key] - 1.0) * 100.0
        result.append({
            "year":  y,
            "month": m,
            "label": MONTHS[m - 1],
            "value": round(ret, 4),
        })
    return result


def performance_series(
    dates:            list[str],
    portfolio_values: list[float],
    benchmark_values: dict[str, list[float]],
) -> list[dict]:
    """
    Normalise portfolio and benchmarks to 100 at t=0 for apples-to-apples comparison.

    Returns list of {"date", "portfolio", "spy"?, "qqq"?}.
    """
    if not dates or not portfolio_values:
        return []

    base_p  = portfolio_values[0] if portfolio_values[0] else 1.0
    b_bases = {k: (v[0] if v and v[0] else 1.0) for k, v in benchmark_values.items()}

    _key_map = {"SPY": "spy", "QQQ": "qqq"}

    out = []
    for i, d in enumerate(dates):
        pt: dict = {"date": d}
        if i < len(portfolio_values):
            pt["portfolio"] = round(portfolio_values[i] / base_p * 100, 2)
        for k, vals in benchmark_values.items():
            if i < len(vals) and vals[i]:
                field    = _key_map.get(k.upper(), "benchmark")
                pt[field] = round(vals[i] / b_bases[k] * 100, 2)
        out.append(pt)
    return out


def compute_growth_of_100(
    active_dates:     list[str],
    portfolio_values: list[float],
    spy_closes:       list[float],
    qqq_closes:       list[float],
) -> list[dict]:
    """
    Normalise portfolio and benchmark price series to 100 at inception.

    Each point: {"date", "portfolio", "spy"?, "qqq"?}.
    """
    if not active_dates or not portfolio_values:
        return []

    port_base = portfolio_values[0] or 1.0
    spy_base  = spy_closes[0]  if spy_closes  else None
    qqq_base  = qqq_closes[0]  if qqq_closes  else None

    result: list[dict] = []
    for i, d in enumerate(active_dates):
        if i >= len(portfolio_values):
            break
        pt: dict = {
            "date":      d,
            "portfolio": round(portfolio_values[i] / port_base * 100, 2),
        }
        if spy_base and i < len(spy_closes) and spy_closes[i]:
            pt["spy"] = round(spy_closes[i] / spy_base * 100, 2)
        if qqq_base and i < len(qqq_closes) and qqq_closes[i]:
            pt["qqq"] = round(qqq_closes[i] / qqq_base * 100, 2)
        result.append(pt)
    return result


def compute_return_distribution(returns: list[float]) -> dict:
    """
    Sample skewness and excess kurtosis of the daily return distribution.

    Returns {"skewness": float | None, "kurtosis": float | None}.
    Negative skewness → left tail; kurtosis > 0 → fat tails (leptokurtic).

    NumPy vectorises the moment calculations.
    """
    if len(returns) < 4:
        return {"skewness": None, "kurtosis": None}
    r = np.asarray(returns, dtype=np.float64)
    s = float(r.std(ddof=1))
    if s == 0.0:
        return {"skewness": 0.0, "kurtosis": 0.0}
    centered = r - r.mean()
    skew = float(np.mean(centered ** 3) / s ** 3)
    kurt = float(np.mean(centered ** 4) / s ** 4) - 3.0
    return {"skewness": round(skew, 4), "kurtosis": round(kurt, 4)}


def compute_daily_return_heatmap(
    dates:   list[str],
    returns: list[float],
) -> list[dict]:
    """
    Build a calendar-heatmap-ready series from daily portfolio returns.

    Each entry contains the full date decomposition so the frontend can
    render calendar, weekly, or GitHub-style contribution grids without
    any additional date parsing.

    Args:
        dates:   trading dates aligned 1-to-1 with returns (YYYY-MM-DD)
        returns: daily returns in decimal form (e.g. 0.0082 = +0.82 %)

    Returns:
        List of {"date", "year", "month", "day", "weekday", "return_pct"}
        Length equals min(len(dates), len(returns)).
        weekday: 0 = Monday … 6 = Sunday  (ISO weekday − 1).
        return_pct is rounded to 2 decimal places.
    """
    n      = min(len(dates), len(returns))
    result = []
    for i in range(n):
        d   = dates[i]
        # Parse once, avoid datetime import overhead with slicing
        y, m, day = int(d[:4]), int(d[5:7]), int(d[8:10])
        wd = _date(y, m, day).weekday()   # 0=Mon … 6=Sun
        result.append({
            "date":       d,
            "year":       y,
            "month":      m,
            "day":        day,
            "weekday":    wd,
            "return_pct": round(returns[i] * 100, 2),
        })
    return result


def compute_weekly_returns(dates: list[str], values: list[float]) -> list[dict]:
    """
    Aggregate daily portfolio values into ISO weekly returns.

    First value of each ISO week = open; last value = close.
    Returns list of {week, year, week_number, return_pct}.

    NOTE: Use weekly_returns_twr() when a TWR daily return series is
    available — this function uses first/last NAV values and is biased by
    capital injections that occur mid-week.
    """
    if len(dates) < 2 or len(dates) != len(values):
        return []

    # Use insertion order to preserve chronological sequence
    order: list[str] = []
    buckets: dict[str, tuple[float, float, int, int]] = {}

    for d_str, v in zip(dates, values):
        y, m, day = int(d_str[:4]), int(d_str[5:7]), int(d_str[8:10])
        iso_year, iso_week, _ = _date(y, m, day).isocalendar()
        key = f"{iso_year}-W{iso_week:02d}"
        if key not in buckets:
            order.append(key)
            buckets[key] = (v, v, iso_year, iso_week)
        else:
            first_v, _, yr, wk = buckets[key]
            buckets[key] = (first_v, v, yr, wk)

    result = []
    for key in order:
        first_v, last_v, yr, wk = buckets[key]
        ret = (last_v / first_v - 1) * 100 if first_v else 0.0
        result.append({
            "week":        key,
            "year":        yr,
            "week_number": wk,
            "return_pct":  round(ret, 4),
        })
    return result


def weekly_returns_twr(
    dates:   list[str],
    returns: list[float],
) -> list[dict]:
    """
    Aggregate daily TWR returns into ISO weekly returns by compounding.

    For each ISO week W the return is:

        R_W = product of (1 + R_t) for every trading day t in W, minus 1

    Compounding the already-stripped daily TWR returns ensures that capital
    injections mid-week do not inflate the week's reported return.

    Args:
        dates:   active_dates[1:] — N-1 trading dates aligned with returns
        returns: daily TWR decimal returns from compute_twr_returns()

    Returns:
        List of {"week", "year", "week_number", "return_pct"} in chronological
        order (ISO week label format: "YYYY-Www").
    """
    if not dates or len(dates) != len(returns):
        return []

    # Compound gross return factor within each ISO week bucket
    factors: dict[str, float]       = {}
    meta:    dict[str, tuple[int, int]] = {}   # key → (iso_year, iso_week)
    order:   list[str]              = []

    for d_str, r in zip(dates, returns):
        y, m, day = int(d_str[:4]), int(d_str[5:7]), int(d_str[8:10])
        iso_year, iso_week, _ = _date(y, m, day).isocalendar()
        key = f"{iso_year}-W{iso_week:02d}"
        if key not in factors:
            order.append(key)
            factors[key] = 1.0
            meta[key]    = (iso_year, iso_week)
        factors[key] *= (1.0 + r)

    result = []
    for key in order:
        yr, wk = meta[key]
        ret = (factors[key] - 1.0) * 100.0
        result.append({
            "week":        key,
            "year":        yr,
            "week_number": wk,
            "return_pct":  round(ret, 4),
        })
    return result


def compute_period_extremes(
    daily_heatmap:   list[dict],
    weekly_returns:  list[dict],
    monthly_returns: list[dict],
) -> dict:
    """
    Best and worst return for each time granularity (day / week / month).
    Returns {best_day_pct, worst_day_pct, best_week_pct, worst_week_pct,
             best_month_pct, worst_month_pct} — each float or None.
    """
    def _extremes(vals: list[float]) -> tuple[float | None, float | None]:
        if not vals:
            return None, None
        return round(max(vals), 4), round(min(vals), 4)

    best_day,   worst_day   = _extremes([d["return_pct"] for d in daily_heatmap])
    best_week,  worst_week  = _extremes([w["return_pct"] for w in weekly_returns])
    best_month, worst_month = _extremes([m["value"]      for m in monthly_returns])

    return {
        "best_day_pct":    best_day,
        "worst_day_pct":   worst_day,
        "best_week_pct":   best_week,
        "worst_week_pct":  worst_week,
        "best_month_pct":  best_month,
        "worst_month_pct": worst_month,
    }


def compute_derived_metrics(
    dates:         list[str],
    port_values:   list[float],
    port_returns:  list[float],
    spy_values:    list[float],
    qqq_values:    list[float],
    drawdown_data: list[dict],
) -> dict:
    """
    Additional analytics appended as 'derived_metrics' to the analytics response.
    All inputs are the intermediate series already computed by compute_engine().
    """
    n    = len(port_values)
    last = port_values[-1] if port_values else None

    def _lookback(k: int) -> float | None:
        if n < k + 1 or last is None:
            return None
        return pct_change(last, port_values[-(k + 1)])

    ytd_pct: float | None = None
    if dates and port_values:
        cur_year = dates[-1][:4]
        ytd_idx  = next((i for i, d in enumerate(dates) if d[:4] == cur_year), None)
        if ytd_idx is not None and ytd_idx < n:
            ytd_pct = pct_change(last, port_values[ytd_idx])

    perf_summary = {
        "1d_pct":  _lookback(1),
        "1w_pct":  _lookback(5),
        "1m_pct":  _lookback(21),
        "ytd_pct": ytd_pct,
        "1y_pct":  pct_change(last, port_values[0]) if port_values else None,
    }

    port_ret = pct_change(port_values[-1], port_values[0]) if len(port_values) >= 2 else None
    spy_ret  = pct_change(spy_values[-1],  spy_values[0])  if len(spy_values)  >= 2 else None
    qqq_ret  = pct_change(qqq_values[-1],  qqq_values[0])  if len(qqq_values)  >= 2 else None

    bench_comp = {
        "portfolio_return_pct": port_ret,
        "spy_return_pct":       spy_ret,
        "qqq_return_pct":       qqq_ret,
        "alpha_vs_spy_pct":     round(port_ret - spy_ret, 4) if port_ret is not None and spy_ret  is not None else None,
        "alpha_vs_qqq_pct":     round(port_ret - qqq_ret, 4) if port_ret is not None and qqq_ret  is not None else None,
    }

    best_day = worst_day = avg_day = median_day = None
    if port_returns:
        r_pct      = np.asarray(port_returns, dtype=np.float64) * 100
        best_day   = round(float(r_pct.max()),  4)
        worst_day  = round(float(r_pct.min()),  4)
        avg_day    = round(float(r_pct.mean()), 4)
        median_day = round(float(np.median(r_pct)), 4)

    current_dd    = drawdown_data[-1]["drawdown"] if drawdown_data else None
    recovery_days = 0
    for i in range(len(drawdown_data) - 1, -1, -1):
        if drawdown_data[i]["drawdown"] >= -0.0001:
            recovery_days = len(drawdown_data) - 1 - i
            break

    return {
        "performance_summary":      perf_summary,
        "benchmark_comparison":     bench_comp,
        "best_day_pct":             best_day,
        "worst_day_pct":            worst_day,
        "avg_daily_return_pct":     avg_day,
        "median_daily_return_pct":  median_day,
        "current_drawdown_pct":     current_dd,
        "recovery_days_since_peak": recovery_days,
    }
