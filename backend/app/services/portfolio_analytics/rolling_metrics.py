"""
Rolling analytics: rolling risk metrics, correlation, volatility regime,
and rolling max drawdown.

NumPy sliding_window_view replaces Python loops for O(n) vectorised
computation across all rolling windows simultaneously.
"""
from __future__ import annotations

import math

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from .constants import RF_DAILY, TRADING_YR


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
                base    = values[i]
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

    Uses sliding_window_view to batch-compute all windows in one pass
    instead of nested Python loops.

    Returns {"63d": [...], "126d": [...], "252d": [...]}.
    """
    pr    = np.asarray(port_returns, dtype=np.float64)
    n_ret = len(pr)
    sr    = np.asarray(spy_returns, dtype=np.float64) if spy_returns else None

    sqTR  = math.sqrt(TRADING_YR)
    result: dict[str, list[dict]] = {}

    for W in windows:
        if n_ret < W:
            result[f"{W}d"] = []
            continue

        # ── Sliding windows: shape (n_windows, W) ─────────────────────
        pw        = sliding_window_view(pr, W)          # (n_windows, W)
        n_windows = pw.shape[0]

        # Per-window mean and std
        w_mean = pw.mean(axis=1)                        # (n_windows,)
        w_std  = pw.std(axis=1, ddof=1)                 # (n_windows,)
        excess = w_mean - RF_DAILY

        r_vol    = np.where(w_std > 0, w_std * sqTR * 100, np.nan)
        r_sharpe = np.where(w_std > 0, excess / w_std * sqTR,   np.nan)

        # Sortino: downside deviation per window
        downside  = np.minimum(pw - RF_DAILY, 0.0)     # (n_windows, W)
        dd_std    = np.sqrt(np.mean(downside ** 2, axis=1))
        r_sortino = np.where(dd_std > 0, excess / dd_std * sqTR, np.nan)

        # Rolling beta vs SPY (vectorised covariance)
        r_beta = np.full(n_windows, np.nan, dtype=np.float64)
        if sr is not None and len(sr) >= W:
            sw      = sliding_window_view(sr[:n_ret], W) if len(sr) >= n_ret else \
                      sliding_window_view(sr, W)
            n_beta  = min(n_windows, sw.shape[0])
            if n_beta > 0:
                pw_b    = pw[:n_beta]                   # (n_beta, W)
                sw_b    = sw[:n_beta]                   # (n_beta, W)
                pm      = pw_b.mean(axis=1, keepdims=True)
                mm      = sw_b.mean(axis=1, keepdims=True)
                cov     = ((pw_b - pm) * (sw_b - mm)).sum(axis=1) / (W - 1)
                var_spy = ((sw_b - mm) ** 2).sum(axis=1)          / (W - 1)
                r_beta[:n_beta] = np.where(var_spy > 0, cov / var_spy, np.nan)

        # ── Assemble result list ───────────────────────────────────────
        nd = len(active_dates)
        series: list[dict] = []
        for k in range(n_windows):
            d = active_dates[min(k + W, nd - 1)]
            series.append({
                "date":               d,
                "rolling_sharpe":     _f4(r_sharpe[k]),
                "rolling_volatility": _f2(r_vol[k]),
                "rolling_beta":       _f4(r_beta[k]),
                "rolling_sortino":    _f4(r_sortino[k]),
            })
        result[f"{W}d"] = series

    return result


def compute_rolling_correlation(
    port_returns:  list[float],
    bench_returns: list[float],
    active_dates:  list[str],
    window: int = 90,
) -> list[dict]:
    """
    Rolling Pearson correlation vs a benchmark.
    Each point: {"date", "value"}.

    Uses sliding_window_view for vectorised covariance computation.
    """
    n = min(len(port_returns), len(bench_returns))
    if n < window:
        return []

    pr = np.asarray(port_returns[:n], dtype=np.float64)
    br = np.asarray(bench_returns[:n], dtype=np.float64)

    pw = sliding_window_view(pr, window)   # (n_windows, window)
    bw = sliding_window_view(br, window)

    pm  = pw.mean(axis=1, keepdims=True)
    bm  = bw.mean(axis=1, keepdims=True)
    cov = ((pw - pm) * (bw - bm)).sum(axis=1) / (window - 1)
    sp  = pw.std(axis=1, ddof=1)
    sb  = bw.std(axis=1, ddof=1)
    denom = sp * sb
    corr  = np.where(denom > 0, cov / denom, np.nan)

    nd     = len(active_dates)
    result = []
    for k in range(pw.shape[0]):
        d = active_dates[min(k + window, nd - 1)]
        result.append({"date": d, "value": _f4(corr[k])})
    return result


def compute_volatility_regime(
    port_returns: list[float],
    active_dates: list[str],
    window: int = 30,
) -> list[dict]:
    """
    Classify each date into a volatility regime (low / normal / high).

    Regime thresholds (annualised vol):
        low    < 10 %
        normal 10 – 20 %
        high   > 20 %

    Uses sliding_window_view for vectorised std computation.
    """
    n = len(port_returns)
    if n < window:
        return []

    pr   = np.asarray(port_returns, dtype=np.float64)
    pw   = sliding_window_view(pr, window)                         # (n_windows, window)
    vols = pw.std(axis=1, ddof=1) * math.sqrt(TRADING_YR) * 100   # annualised %

    nd     = len(active_dates)
    result = []
    for k in range(pw.shape[0]):
        d   = active_dates[min(k + window, nd - 1)]
        vol = float(vols[k])
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

    Uses sliding_window_view + np.maximum.accumulate along axis=1
    to vectorise the peak-to-trough computation.
    """
    n = len(values)
    if n < window:
        return []

    v  = np.asarray(values, dtype=np.float64)
    vw = sliding_window_view(v, window)                            # (n_windows, window)

    running_max = np.maximum.accumulate(vw, axis=1)
    dd          = np.where(running_max > 0,
                           (vw - running_max) / running_max * 100, 0.0)
    mdd         = dd.min(axis=1)                                   # (n_windows,)

    nd     = len(dates)
    result = []
    for k in range(vw.shape[0]):
        idx = k + window - 1
        d   = dates[idx] if idx < nd else ""
        result.append({"date": d, "drawdown": round(float(mdd[k]), 4)})
    return result


# ── Internal helpers ──────────────────────────────────────────────────────────

def _f4(v: float) -> float | None:
    """Round to 4dp, return None for non-finite values."""
    return round(float(v), 4) if np.isfinite(v) else None


def _f2(v: float) -> float | None:
    """Round to 2dp, return None for non-finite values."""
    return round(float(v), 2) if np.isfinite(v) else None
