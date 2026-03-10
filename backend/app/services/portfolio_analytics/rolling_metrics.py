"""
Rolling analytics: rolling risk metrics, correlation, volatility regime,
and rolling max drawdown.
All functions operate on plain Python lists and return plain dicts.
"""
from __future__ import annotations

import math

from .constants import RF_DAILY, TRADING_YR
from .math_utils import mean, std


def compute_rolling_returns(
    values: list[float],
    dates:  list[str],
) -> dict:
    """
    Compute rolling period returns from a daily portfolio value series.

    Returns {"return_1w", "return_1m", "return_3m", "return_ytd", "return_1y"}
    as percentage floats (or None when insufficient history).
    """
    empty: dict[str, float | None] = {
        "return_1w": None, "return_1m": None,
        "return_3m": None, "return_ytd": None, "return_1y": None,
    }
    if len(values) < 2:
        return empty

    last = values[-1]

    def _lb(n: int) -> float | None:
        if len(values) < n + 1:
            return None
        base = values[-(n + 1)]
        return round((last / base - 1) * 100, 4) if base > 0 else None

    ytd_pct: float | None = None
    if dates:
        cur_year = dates[-1][:4]
        for i, d in enumerate(dates):
            if d[:4] == cur_year and i < len(values):
                base = values[i]
                ytd_pct = round((last / base - 1) * 100, 4) if base > 0 else None
                break

    return {
        "return_1w":  _lb(5),
        "return_1m":  _lb(21),
        "return_3m":  _lb(63),
        "return_ytd": ytd_pct,
        "return_1y":  _lb(252),
    }


def compute_rolling_risk_metrics(
    port_returns: list[float],
    spy_returns:  list[float],
    active_dates: list[str],
    windows: tuple[int, ...] = (63, 126, 252),
) -> dict[str, list[dict]]:
    """
    Rolling Sharpe, annualized volatility, beta vs SPY, and Sortino
    for each window size.

    Returns {"63d": [...], "126d": [...], "252d": [...]}.
    Each point: {"date", "rolling_sharpe", "rolling_volatility",
                 "rolling_beta", "rolling_sortino"}.
    Only points with a full window of data are emitted.
    """
    n_ret = len(port_returns)
    n_spy = len(spy_returns)
    result: dict[str, list[dict]] = {}

    for W in windows:
        series: list[dict] = []
        for i in range(W - 1, n_ret):
            pr = port_returns[i - W + 1 : i + 1]
            # return[i] is the gain earned *on* active_dates[i+1]
            d = active_dates[min(i + 1, len(active_dates) - 1)]

            s        = std(pr)
            m_excess = mean(pr) - RF_DAILY

            r_vol     = round(s * math.sqrt(TRADING_YR) * 100, 2) if s else None
            r_sharpe  = round((m_excess / s) * math.sqrt(TRADING_YR), 4) if s else None

            dd_sq    = sum(min(r - RF_DAILY, 0) ** 2 for r in pr) / W
            dd_std   = math.sqrt(dd_sq)
            r_sortino = round((m_excess / dd_std) * math.sqrt(TRADING_YR), 4) if dd_std else None

            r_beta: float | None = None
            if n_spy >= i + 1:
                mr = spy_returns[i - W + 1 : i + 1]
                if len(mr) == W:
                    mm = mean(mr)
                    mp = mean(pr)
                    cov_ = sum((pr[j] - mp) * (mr[j] - mm) for j in range(W)) / (W - 1)
                    var_ = sum((mr[j] - mm) ** 2 for j in range(W)) / (W - 1)
                    r_beta = round(cov_ / var_, 4) if var_ > 0 else None

            series.append({
                "date":               d,
                "rolling_sharpe":     r_sharpe,
                "rolling_volatility": r_vol,
                "rolling_beta":       r_beta,
                "rolling_sortino":    r_sortino,
            })
        result[f"{W}d"] = series

    return result


def compute_rolling_correlation(
    port_returns:  list[float],
    bench_returns: list[float],
    active_dates:  list[str],
    window: int = 90,
) -> list[dict]:
    """Rolling Pearson correlation vs a benchmark. Each point: {"date", "value"}."""
    n = min(len(port_returns), len(bench_returns))
    result: list[dict] = []
    for i in range(window - 1, n):
        pr = port_returns[i - window + 1 : i + 1]
        br = bench_returns[i - window + 1 : i + 1]
        d  = active_dates[min(i + 1, len(active_dates) - 1)]

        mp, mb = mean(pr), mean(br)
        cov_   = sum((pr[j] - mp) * (br[j] - mb) for j in range(window)) / (window - 1)
        sp, sb = std(pr), std(br)
        corr   = round(cov_ / (sp * sb), 4) if (sp and sb) else None
        result.append({"date": d, "value": corr})
    return result


def compute_volatility_regime(
    port_returns: list[float],
    active_dates: list[str],
    window: int = 30,
) -> list[dict]:
    """
    Classify each date into a volatility regime.

    Regime boundaries (annualised vol):
        low    < 10 %
        normal 10 – 20 %
        high   > 20 %
    Each point: {"date", "volatility", "regime"}.
    """
    n = len(port_returns)
    result: list[dict] = []
    for i in range(window - 1, n):
        pr  = port_returns[i - window + 1 : i + 1]
        d   = active_dates[min(i + 1, len(active_dates) - 1)]
        vol = std(pr) * math.sqrt(TRADING_YR) * 100
        regime = "low" if vol < 10.0 else ("high" if vol > 20.0 else "normal")
        result.append({"date": d, "volatility": round(vol, 2), "regime": regime})
    return result


def compute_rolling_max_drawdown(
    values: list[float],
    dates:  list[str],
    window: int = 126,
) -> list[dict]:
    """
    Rolling maximum drawdown over `window` trading days.

    Each point: {"date", "drawdown"} — drawdown is a negative %.
    Aligns to active_dates directly (not returns-offset).
    """
    n      = len(values)
    result: list[dict] = []
    for i in range(window - 1, n):
        wv   = values[i - window + 1 : i + 1]
        d    = dates[i] if i < len(dates) else ""
        peak = wv[0]
        mdd  = 0.0
        for v in wv:
            if v > peak:
                peak = v
            dd = (v - peak) / peak * 100 if peak else 0.0
            if dd < mdd:
                mdd = dd
        result.append({"date": d, "drawdown": round(mdd, 4)})
    return result
