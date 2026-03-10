"""
Performance chart series and summary statistics.

Functions here generate chart-ready data structures for the frontend:
drawdown series, monthly return heatmap, benchmark comparison,
growth-of-$100, return distribution, and derived metrics summary.
"""
from __future__ import annotations

import math
import statistics as _stats

from .constants import MONTHS, TRADING_YR
from .math_utils import mean, std, pct_change


def drawdown_series(dates: list[str], closes: list[float]) -> list[dict]:
    """
    Running peak-to-trough drawdown at each date.

    Returns list of {"date": str, "drawdown": float (negative %)}.
    """
    if not closes:
        return []
    peak = closes[0]
    out  = []
    for i, v in enumerate(closes):
        if v > peak:
            peak = v
        dd = (v - peak) / peak * 100 if peak else 0.0
        out.append({
            "date":     dates[i] if i < len(dates) else "",
            "drawdown": round(dd, 4),
        })
    return out


def monthly_returns(dates: list[str], values: list[float]) -> list[dict]:
    """
    Aggregate a daily value series into monthly returns.

    Returns list of {"year", "month", "label", "value" (%)}.
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


def performance_series(
    dates:             list[str],
    portfolio_values:  list[float],
    benchmark_values:  dict[str, list[float]],
) -> list[dict]:
    """
    Normalise portfolio and benchmarks to 100 at t=0 for apples-to-apples comparison.

    Args:
        benchmark_values: {"SPY": [100, 101, ...], "QQQ": [...]}

    Returns list of {"date", "portfolio", "spy"?, "qqq"?}.
    """
    if not dates or not portfolio_values:
        return []

    base_p  = portfolio_values[0] if portfolio_values[0] else 1.0
    b_bases = {k: (v[0] if v and v[0] else 1.0) for k, v in benchmark_values.items()}

    # Map benchmark keys to canonical field names
    _key_map = {"SPY": "spy", "QQQ": "qqq"}

    out = []
    for i, d in enumerate(dates):
        pt: dict = {"date": d}
        if i < len(portfolio_values):
            pt["portfolio"] = round(portfolio_values[i] / base_p * 100, 2)
        for k, vals in benchmark_values.items():
            if i < len(vals) and vals[i]:
                field = _key_map.get(k.upper(), "benchmark")
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
    """
    if len(returns) < 4:
        return {"skewness": None, "kurtosis": None}
    n = len(returns)
    m = mean(returns)
    s = std(returns)
    if s == 0:
        return {"skewness": 0.0, "kurtosis": 0.0}
    skew = (sum((r - m) ** 3 for r in returns) / n) / (s ** 3)
    kurt = (sum((r - m) ** 4 for r in returns) / n) / (s ** 4) - 3.0
    return {"skewness": round(skew, 4), "kurtosis": round(kurt, 4)}


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
        "alpha_vs_spy_pct":     round(port_ret - spy_ret, 4) if port_ret is not None and spy_ret is not None else None,
        "alpha_vs_qqq_pct":     round(port_ret - qqq_ret, 4) if port_ret is not None and qqq_ret is not None else None,
    }

    best_day = worst_day = avg_day = median_day = None
    if port_returns:
        r_pct      = [r * 100 for r in port_returns]
        best_day   = round(max(r_pct), 4)
        worst_day  = round(min(r_pct), 4)
        avg_day    = round(sum(r_pct) / len(r_pct), 4)
        median_day = round(_stats.median(r_pct), 4)

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
