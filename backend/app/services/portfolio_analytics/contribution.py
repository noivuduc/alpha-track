"""
Per-ticker contribution analytics: how much each position contributed
to total portfolio return in dollar and percentage terms.
"""
from __future__ import annotations


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

    portfolio_initial_value = portfolio_values[0]
    portfolio_tickers = {lot["ticker"] for lot in lots}

    # Build latest forward-filled price for each portfolio ticker
    last_prices: dict[str, float] = {}
    for d in active_dates:
        for ticker in portfolio_tickers:
            d2c = price_lookup.get(ticker)
            if d2c:
                p = d2c.get(d)
                if p and p > 0:
                    last_prices[ticker] = p

    by_ticker: dict[str, dict[str, float]] = {}
    for lot in lots:
        t      = lot["ticker"]
        shares = lot["shares"]
        cost   = shares * lot["cost_basis"]
        price  = last_prices.get(t, lot["cost_basis"])
        val    = shares * price
        if t not in by_ticker:
            by_ticker[t] = {"cost": 0.0, "value": 0.0}
        by_ticker[t]["cost"]  += cost
        by_ticker[t]["value"] += val

    rows = []
    for ticker, d in by_ticker.items():
        pnl_contribution = d["value"] - d["cost"]
        contrib_pct = (
            pnl_contribution / portfolio_initial_value * 100
            if portfolio_initial_value > 0 else 0.0
        )
        rows.append({
            "ticker":           ticker,
            "contribution_pct": round(contrib_pct, 4),
            "pnl_contribution": round(pnl_contribution, 2),
        })

    return sorted(rows, key=lambda x: x["pnl_contribution"], reverse=True)
