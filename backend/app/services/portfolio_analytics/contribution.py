"""
Per-ticker contribution analytics: how much each position contributed
to total portfolio return in dollar and percentage terms.

NumPy is used for the final vectorised P&L and percentage calculations.
"""
from __future__ import annotations

import numpy as np


def compute_contribution(
    lots:             list[dict],
    price_lookup:     dict[str, dict[str, float]],
    active_dates:     list[str],
    portfolio_values: list[float],
) -> list[dict]:
    """
    Per-ticker contribution to portfolio return.

    contribution_pct  = pnl_contribution / portfolio_initial_value × 100
    pnl_contribution  = ticker_current_value − ticker_total_cost

    Returns a list sorted by pnl_contribution descending.
    """
    if not portfolio_values or not active_dates:
        return []

    portfolio_current_value = portfolio_values[-1]
    portfolio_tickers       = {lot["ticker"] for lot in lots}

    # Forward-fill to obtain the latest price for each ticker
    last_prices: dict[str, float] = {}
    for d in active_dates:
        for ticker in portfolio_tickers:
            d2c = price_lookup.get(ticker)
            if d2c:
                p = d2c.get(d)
                if p and p > 0:
                    last_prices[ticker] = p

    # Aggregate lots by ticker
    tickers_set: dict[str, int] = {}
    cost_acc:  list[float] = []
    value_acc: list[float] = []

    for lot in lots:
        t      = lot["ticker"]
        shares = lot["shares"]
        cost   = shares * lot["cost_basis"]
        price  = last_prices.get(t, lot["cost_basis"])
        val    = shares * price
        if t not in tickers_set:
            tickers_set[t] = len(cost_acc)
            cost_acc.append(0.0)
            value_acc.append(0.0)
        idx = tickers_set[t]
        cost_acc[idx]  += cost
        value_acc[idx] += val

    tickers_list = list(tickers_set.keys())

    # Vectorised P&L and contribution % computation
    #
    # Current method: contribution_pct = pnl / current_portfolio_value × 100
    # Using current NAV as denominator ensures recently-opened positions are
    # correctly scaled relative to the portfolio they exist in today.
    #
    # TODO: upgrade to time-weighted contribution for full accuracy:
    #   contribution_t = weight_t × return_t  (sum over all active trading days)
    # This requires daily weight and return series per position, which in turn
    # requires aligning lot open dates to the price history calendar.
    costs  = np.asarray(cost_acc,  dtype=np.float64)
    values = np.asarray(value_acc, dtype=np.float64)
    pnl    = values - costs
    contrib_pct = (
        pnl / portfolio_current_value * 100
        if portfolio_current_value > 0
        else np.zeros_like(pnl)
    )

    rows = [
        {
            "ticker":           tickers_list[i],
            "contribution_pct": round(float(contrib_pct[i]), 4),
            "pnl_contribution": round(float(pnl[i]), 2),
        }
        for i in range(len(tickers_list))
    ]
    return sorted(rows, key=lambda x: x["pnl_contribution"], reverse=True)
