"""
Time-series math: returns, cumulative wealth, annualised statistics.
All functions are pure with no side-effects.

NumPy vectorization replaces Python loops for performance.
"""
from __future__ import annotations

import bisect
import math

import numpy as np

from .constants import TRADING_YR


def daily_returns(closes: list[float]) -> list[float]:
    """
    Arithmetic (simple) daily returns.

    Skips any step where the previous close is zero (matches original behaviour).

    NOTE: Use compute_twr_returns() instead when lots are available — this
    function does not strip external cash flows and will produce inflated returns
    on dates when new positions are opened.
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


# ── True Time-Weighted Return (TWR) ───────────────────────────────────────────


def build_cash_flows(
    lots:         list[dict],
    active_dates: list[str],
) -> dict[str, float]:
    """
    Build a {YYYY-MM-DD: cash_flow} map from lot acquisition events.

    Each lot represents external capital injected into the portfolio on its
    open date.  The cash flow for a lot is:

        CF = shares × cost_basis

    This is what the investor *paid*, which is the capital that must be
    stripped out before computing the portfolio's return for that day.

    Non-trading day handling: if a lot's opened_at_date falls on a weekend
    or holiday (no NAV entry exists), the cash flow is attributed to the
    next available trading day — the same day the lot first appears in NAV.

    The first active date (portfolio inception) is intentionally *not*
    excluded; compute_twr_returns() skips it naturally because there is no
    V_{t-1} for the first day (the loop starts at index 1).

    Args:
        lots:         list of lot dicts with keys "ticker", "shares",
                      "cost_basis", "opened_at_date"
        active_dates: sorted list of trading dates from reconstruct_portfolio_value()

    Returns:
        {date_str: total_cash_flow_on_that_date}
    """
    cash_flows: dict[str, float] = {}

    if not active_dates:
        return cash_flows

    active_set = set(active_dates)

    for lot in lots:
        opened = lot["opened_at_date"]
        cf     = float(lot["shares"]) * float(lot["cost_basis"])

        if opened in active_set:
            # Lot opened on a trading day — book cash flow on that date.
            effective = opened
        else:
            # Lot opened on a non-trading day (weekend / holiday).
            # Find the first trading day on or after the open date so the
            # cash flow lands on the same day the NAV first includes this lot.
            idx = bisect.bisect_left(active_dates, opened)
            if idx >= len(active_dates):
                continue  # open date is after the last active date — ignore
            effective = active_dates[idx]

        cash_flows[effective] = cash_flows.get(effective, 0.0) + cf

    return cash_flows


def compute_twr_returns(
    portfolio_values: list[float],
    active_dates:     list[str],
    cash_flows:       dict[str, float],
) -> list[float]:
    """
    Compute daily True Time-Weighted Returns (TWR).

    Standard NAV-based returns are distorted by capital flows:

        R_naive = V_t / V_{t-1} - 1

    When shares are bought on day t, V_t includes the injected capital, so
    R_naive shows an artificial spike.  TWR strips the cash flow first:

        R_twr = (V_t - CF_t) / V_{t-1} - 1

    where CF_t is the external capital that arrived on day t.  The resulting
    return series reflects only the market performance of capital already
    invested, which is the correct input for Sharpe, Sortino, volatility,
    drawdown, and all other performance metrics.

    Edge cases:
        - V_{t-1} == 0 → period skipped (degenerate start)
        - CF_t not present → treated as 0 (no capital flow that day)
        - CF_t >= V_t → clipped to yield -100% instead of going below -1
          (rare but guards against data errors where cost_basis >> market price)

    Args:
        portfolio_values: daily NAV series from reconstruct_portfolio_value()
        active_dates:     dates aligned 1-to-1 with portfolio_values
        cash_flows:       {date: external_capital} from build_cash_flows()

    Returns:
        List of N-1 daily decimal returns, aligned with active_dates[1:].
    """
    n = len(portfolio_values)
    if n < 2 or n != len(active_dates):
        return []

    twr: list[float] = []

    for i in range(1, n):
        v_prev = portfolio_values[i - 1]

        # Skip degenerate periods (zero starting NAV)
        if v_prev <= 0.0:
            continue

        v_cur = portfolio_values[i]
        cf    = cash_flows.get(active_dates[i], 0.0)

        # Strip the external cash flow before measuring performance.
        # Clip at -1.0 to avoid nonsensical returns below -100%.
        r = max((v_cur - cf) / v_prev - 1.0, -1.0)
        twr.append(r)

    return twr


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
