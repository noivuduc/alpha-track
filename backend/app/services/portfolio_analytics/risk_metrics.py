"""
Portfolio risk and quality metrics.
All functions are pure, accepting and returning plain Python types.

NumPy is used throughout for numerical stability and vectorised computation.
"""
from __future__ import annotations

import math

import numpy as np

from .constants import RF_DAILY, TRADING_YR
from .return_series import annualized_return, annualized_vol


def sharpe(returns: list[float]) -> float:
    """Annualized Sharpe ratio (RF = 2 % annual)."""
    if len(returns) < 20:
        return 0.0
    r  = np.asarray(returns, dtype=np.float64)
    s  = float(r.std(ddof=1))
    if s == 0.0:
        return 0.0
    return round(float((r.mean() - RF_DAILY) / s) * math.sqrt(TRADING_YR), 4)


def sortino(returns: list[float]) -> float:
    """Annualized Sortino ratio (penalises downside only)."""
    if len(returns) < 20:
        return 0.0
    r        = np.asarray(returns, dtype=np.float64)
    excess   = r - RF_DAILY
    downside = np.minimum(excess, 0.0)
    dd       = math.sqrt(float(np.mean(downside ** 2)))
    if dd == 0.0:
        return 0.0
    return round(float(excess.mean()) / dd * math.sqrt(TRADING_YR), 4)


def max_drawdown(closes: list[float]) -> float:
    """Maximum peak-to-trough drawdown as a negative percentage."""
    if len(closes) < 2:
        return 0.0
    c           = np.asarray(closes, dtype=np.float64)
    running_max = np.maximum.accumulate(c)
    dd          = np.where(running_max > 0, (c - running_max) / running_max, 0.0)
    return round(float(dd.min()) * 100, 4)


def beta(port_returns: list[float], mkt_returns: list[float]) -> float:
    """Beta of portfolio vs market (sample covariance / sample variance)."""
    n = min(len(port_returns), len(mkt_returns))
    if n < 20:
        return 1.0
    cov_matrix = np.cov(
        np.asarray(port_returns[:n], dtype=np.float64),
        np.asarray(mkt_returns[:n],  dtype=np.float64),
        ddof=1,
    )
    var = float(cov_matrix[1, 1])
    return round(float(cov_matrix[0, 1]) / var, 4) if var > 0 else 1.0


def alpha(port_returns: list[float], mkt_returns: list[float], b: float) -> float:
    """Jensen's alpha: compute daily excess alpha then annualize."""
    n = min(len(port_returns), len(mkt_returns))
    if n < 20:
        return 0.0
    mp = float(np.mean(np.asarray(port_returns[:n], dtype=np.float64)))
    mm = float(np.mean(np.asarray(mkt_returns[:n],  dtype=np.float64)))
    alpha_daily = mp - (RF_DAILY + b * (mm - RF_DAILY))
    return round(alpha_daily * TRADING_YR * 100, 4)


def calmar(returns: list[float], closes: list[float]) -> float:
    """Calmar ratio = annualized return / |max drawdown|."""
    mdd = abs(max_drawdown(closes))
    ann = annualized_return(returns)
    return round(ann / mdd, 4) if mdd else 0.0


def win_rate(returns: list[float]) -> float:
    """Percentage of days where return exceeds the daily risk-free rate."""
    if not returns:
        return 0.0
    r = np.asarray(returns, dtype=np.float64)
    return round(float(np.mean(r > RF_DAILY)) * 100, 2)


def information_ratio(port_returns: list[float], bench_returns: list[float]) -> float:
    """Annualized information ratio vs benchmark."""
    n = min(len(port_returns), len(bench_returns))
    if n < 20:
        return 0.0
    active = (
        np.asarray(port_returns[:n], dtype=np.float64)
        - np.asarray(bench_returns[:n], dtype=np.float64)
    )
    s = float(active.std(ddof=1))
    return round(float(active.mean()) / s * math.sqrt(TRADING_YR), 4) if s else 0.0


def value_at_risk(returns: list[float], confidence: float = 0.95) -> float:
    """Historical VaR at `confidence` level, expressed as positive percentage."""
    if len(returns) < 20:
        return 0.0
    r   = np.asarray(returns, dtype=np.float64)
    idx = int((1.0 - confidence) * len(r))
    return round(float(np.abs(np.sort(r)[idx])) * 100, 4)


def pearson_corr(x: list[float], y: list[float]) -> float | None:
    """Pearson correlation coefficient between two return series."""
    n = min(len(x), len(y))
    if n < 20:
        return None
    corr_matrix = np.corrcoef(
        np.asarray(x[:n], dtype=np.float64),
        np.asarray(y[:n], dtype=np.float64),
    )
    c = float(corr_matrix[0, 1])
    return round(c, 4) if np.isfinite(c) else None


def compute_downside_risk(
    returns: list[float],
    values:  list[float],
) -> dict:
    """
    Downside deviation (annualised %), Ulcer Index, and CVaR tail-loss at 95 %.

    These extend risk_metrics without modifying existing fields.
    """
    empty = {"downside_deviation": 0.0, "ulcer_index": 0.0, "tail_loss_95": 0.0}
    if len(returns) < 20:
        return empty

    r = np.asarray(returns, dtype=np.float64)

    # Downside deviation: semi-deviation below risk-free, annualised
    downside = np.minimum(r - RF_DAILY, 0.0)
    ddn      = round(float(np.sqrt(np.mean(downside ** 2))) * math.sqrt(TRADING_YR) * 100, 4)

    # Ulcer Index: RMS of running drawdown from portfolio value series
    if len(values) >= 2:
        v           = np.asarray(values, dtype=np.float64)
        running_max = np.maximum.accumulate(v)
        dd_pcts     = np.where(running_max > 0, (v - running_max) / running_max * 100, 0.0)
        ulcer       = round(float(np.sqrt(np.mean(dd_pcts ** 2))), 4)
    else:
        ulcer = 0.0

    # Tail-loss (CVaR 95 %): mean of worst 5 % daily returns
    sorted_r  = np.sort(r)
    n5        = max(1, int(0.05 * len(sorted_r)))
    tail_loss = round(float(np.abs(sorted_r[:n5].mean())) * 100, 4)

    return {
        "downside_deviation": ddn,
        "ulcer_index":        ulcer,
        "tail_loss_95":       tail_loss,
    }
