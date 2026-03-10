"""
Time-series math functions: returns, cumulative wealth, annualised statistics.
All functions are pure with no side-effects.
"""
from __future__ import annotations

import math

from .constants import TRADING_YR
from .math_utils import std


def daily_returns(closes: list[float]) -> list[float]:
    """Arithmetic (simple) daily returns."""
    if len(closes) < 2:
        return []
    return [
        (closes[i] - closes[i - 1]) / closes[i - 1]
        for i in range(1, len(closes))
        if closes[i - 1] != 0
    ]


def cumulative_series(returns: list[float], base: float = 100.0) -> list[float]:
    """Wealth index starting at `base`, one value per return period + initial."""
    out = [base]
    v = base
    for r in returns:
        v *= (1 + r)
        out.append(round(v, 6))
    return out


def annualized_return(returns: list[float]) -> float:
    """Geometric annualized return (%)."""
    if not returns:
        return 0.0
    total = 1.0
    for r in returns:
        total *= (1 + r)
    return round((total ** (TRADING_YR / len(returns)) - 1) * 100, 4)


def annualized_vol(returns: list[float]) -> float:
    """Annualized standard deviation of daily returns (%)."""
    if len(returns) < 2:
        return 0.0
    return round(std(returns) * math.sqrt(TRADING_YR) * 100, 4)
