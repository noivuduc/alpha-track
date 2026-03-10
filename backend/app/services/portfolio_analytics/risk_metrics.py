"""
Portfolio risk and quality metrics.
All functions are pure, accepting and returning plain Python types.
"""
from __future__ import annotations

import math
import statistics as _stats

from .constants import RF_DAILY, TRADING_YR
from .math_utils import mean, std
from .return_series import annualized_return, annualized_vol


def sharpe(returns: list[float]) -> float:
    """Annualized Sharpe ratio (RF = 2 % annual)."""
    if len(returns) < 20:
        return 0.0
    m = mean(returns) - RF_DAILY
    s = std(returns)
    return round((m / s) * math.sqrt(TRADING_YR), 4) if s else 0.0


def sortino(returns: list[float]) -> float:
    """Annualized Sortino ratio (penalises downside only)."""
    if len(returns) < 20:
        return 0.0
    m    = mean(returns) - RF_DAILY
    dd_sq = sum(min(r - RF_DAILY, 0) ** 2 for r in returns) / len(returns)
    dd   = math.sqrt(dd_sq)
    return round((m / dd) * math.sqrt(TRADING_YR), 4) if dd else 0.0


def max_drawdown(closes: list[float]) -> float:
    """Maximum peak-to-trough drawdown as a negative percentage."""
    if len(closes) < 2:
        return 0.0
    peak = closes[0]
    mdd  = 0.0
    for v in closes:
        if v > peak:
            peak = v
        dd = (v - peak) / peak if peak else 0.0
        if dd < mdd:
            mdd = dd
    return round(mdd * 100, 4)


def beta(port_returns: list[float], mkt_returns: list[float]) -> float:
    """Beta of portfolio vs market (sample covariance / sample variance)."""
    n = min(len(port_returns), len(mkt_returns))
    if n < 20:
        return 1.0
    pr = port_returns[:n]
    mr = mkt_returns[:n]
    mp, mm = mean(pr), mean(mr)
    cov = sum((pr[i] - mp) * (mr[i] - mm) for i in range(n)) / (n - 1)
    var = sum((mr[i] - mm) ** 2 for i in range(n)) / (n - 1)
    return round(cov / var, 4) if var > 0 else 1.0


def alpha(port_returns: list[float], mkt_returns: list[float], b: float) -> float:
    """Jensen's alpha: compute daily excess alpha then annualize."""
    n = min(len(port_returns), len(mkt_returns))
    if n < 20:
        return 0.0
    mp = mean(port_returns[:n])
    mm = mean(mkt_returns[:n])
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
    return round(sum(1 for r in returns if r > RF_DAILY) / len(returns) * 100, 2)


def information_ratio(port_returns: list[float], bench_returns: list[float]) -> float:
    """Annualized information ratio vs benchmark."""
    n = min(len(port_returns), len(bench_returns))
    if n < 20:
        return 0.0
    active = [port_returns[i] - bench_returns[i] for i in range(n)]
    m = mean(active)
    s = std(active)
    return round((m / s) * math.sqrt(TRADING_YR), 4) if s else 0.0


def value_at_risk(returns: list[float], confidence: float = 0.95) -> float:
    """Historical VaR at `confidence` level, expressed as positive percentage."""
    if len(returns) < 20:
        return 0.0
    sorted_r = sorted(returns)
    idx = int((1 - confidence) * len(sorted_r))
    return round(abs(sorted_r[idx]) * 100, 4)


def pearson_corr(x: list[float], y: list[float]) -> float | None:
    """Pearson correlation coefficient between two return series."""
    n = min(len(x), len(y))
    if n < 20:
        return None
    xs, ys = x[:n], y[:n]
    mx, my = mean(xs), mean(ys)
    cov = sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / (n - 1)
    sx, sy = std(xs), std(ys)
    return round(cov / (sx * sy), 4) if sx and sy else None


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

    # Downside deviation: semi-deviation below risk-free, annualised
    dd_sq = sum(min(r - RF_DAILY, 0) ** 2 for r in returns) / len(returns)
    ddn   = round(math.sqrt(dd_sq) * math.sqrt(TRADING_YR) * 100, 4)

    # Ulcer Index: RMS of running drawdown from portfolio value series
    if len(values) >= 2:
        peak = values[0]
        dd_pcts: list[float] = []
        for v in values:
            if v > peak:
                peak = v
            dd_pcts.append((v - peak) / peak * 100 if peak else 0.0)
        ulcer = round(math.sqrt(sum(x * x for x in dd_pcts) / len(dd_pcts)), 4)
    else:
        ulcer = 0.0

    # Tail-loss (CVaR 95 %): average of worst 5 % daily returns
    sorted_r  = sorted(returns)
    n5        = max(1, int(0.05 * len(sorted_r)))
    tail_loss = round(abs(mean(sorted_r[:n5])) * 100, 4)

    return {
        "downside_deviation": ddn,
        "ulcer_index":        ulcer,
        "tail_loss_95":       tail_loss,
    }
