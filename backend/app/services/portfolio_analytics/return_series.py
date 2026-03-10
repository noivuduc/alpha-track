"""
Time-series math: returns, cumulative wealth, annualised statistics.
All functions are pure with no side-effects.

NumPy vectorization replaces Python loops for performance.
"""
from __future__ import annotations

import math

import numpy as np

from .constants import TRADING_YR


def daily_returns(closes: list[float]) -> list[float]:
    """
    Arithmetic (simple) daily returns.

    Skips any step where the previous close is zero (matches original behaviour).
    """
    if len(closes) < 2:
        return []
    c    = np.asarray(closes, dtype=np.float64)
    prev = c[:-1]
    mask = prev != 0.0
    if not np.any(mask):
        return []
    rets = np.diff(c)[mask] / prev[mask]
    return rets.tolist()


def cumulative_series(returns: list[float], base: float = 100.0) -> list[float]:
    """
    Wealth index starting at `base`, one value per return period + initial.

    Uses np.cumprod for vectorized compound growth.
    """
    if not returns:
        return [base]
    r   = np.asarray(returns, dtype=np.float64)
    cum = np.empty(len(r) + 1, dtype=np.float64)
    cum[0] = base
    cum[1:] = np.round(base * np.cumprod(1.0 + r), 6)
    return cum.tolist()


def annualized_return(returns: list[float]) -> float:
    """Geometric annualized return (%)."""
    if not returns:
        return 0.0
    r     = np.asarray(returns, dtype=np.float64)
    total = float(np.prod(1.0 + r))
    return round((total ** (TRADING_YR / len(r)) - 1) * 100, 4)


def annualized_vol(returns: list[float]) -> float:
    """Annualized standard deviation of daily returns (%)."""
    if len(returns) < 2:
        return 0.0
    r = np.asarray(returns, dtype=np.float64)
    return round(float(r.std(ddof=1)) * math.sqrt(TRADING_YR) * 100, 4)
