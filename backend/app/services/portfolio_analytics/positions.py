"""
Position-level analytics: per-ticker return, P&L, weight, volatility,
and daily return.  Also contains the legacy position-summary helper.
"""
from __future__ import annotations

from .return_series import daily_returns, annualized_vol


def compute_position_analytics(
    lots:             list[dict],
    price_lookup:     dict[str, dict[str, float]],
    active_dates:     list[str],
    portfolio_values: list[float],
) -> list[dict]:
    """
    Per-position (aggregated per ticker) metrics.

    Returns [{"ticker", "return_pct", "pnl", "weight", "volatility", "daily_return"}]
    sorted by weight descending.
    """
    if not portfolio_values or not active_dates:
        return []

    total_value       = portfolio_values[-1]
    portfolio_tickers = {lot["ticker"] for lot in lots}

    # Latest forward-filled prices (only portfolio tickers)
    last_prices: dict[str, float] = {}
    for d in active_dates:
        for ticker in portfolio_tickers:
            d2c = price_lookup.get(ticker)
            if d2c:
                p = d2c.get(d)
                if p and p > 0:
                    last_prices[ticker] = p

    # Per-ticker annualized volatility from their own price history
    ticker_vols: dict[str, float | None] = {}
    for ticker in portfolio_tickers:
        d2c    = price_lookup.get(ticker, {})
        closes = [d2c[d] for d in active_dates if d in d2c and d2c[d] > 0]
        if len(closes) >= 20:
            rets = daily_returns(closes)
            ticker_vols[ticker] = annualized_vol(rets) if rets else None
        else:
            ticker_vols[ticker] = None

    # Latest single-day return per ticker
    ticker_daily: dict[str, float | None] = {}
    for ticker in portfolio_tickers:
        d2c   = price_lookup.get(ticker, {})
        dated = [(d, d2c[d]) for d in active_dates if d in d2c and d2c[d] > 0]
        if len(dated) >= 2:
            prev_p, curr_p = dated[-2][1], dated[-1][1]
            ticker_daily[ticker] = (
                round((curr_p / prev_p - 1) * 100, 4) if prev_p > 0 else None
            )
        else:
            ticker_daily[ticker] = None

    # Aggregate lots by ticker
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

    result = []
    for ticker, d in by_ticker.items():
        pnl     = d["value"] - d["cost"]
        ret_pct = (d["value"] / d["cost"] - 1) * 100 if d["cost"] > 0 else 0.0
        weight  = d["value"] / total_value * 100 if total_value > 0 else 0.0
        result.append({
            "ticker":       ticker,
            "return_pct":   round(ret_pct, 4),
            "pnl":          round(pnl, 2),
            "weight":       round(weight, 4),
            "volatility":   ticker_vols.get(ticker),
            "daily_return": ticker_daily.get(ticker),
        })

    return sorted(result, key=lambda x: x["weight"], reverse=True)


def compute_position_summary(
    positions: list,
    prices:    dict,
    histories: dict,
) -> dict:
    """
    Build position_summary for the OverviewTab (best/worst performers + ticker returns).

    Args:
        positions: list of Position ORM objects
        prices:    {ticker: {"price": float, ...}}  from get_prices_bulk
        histories: {ticker: [{"ts": str, "close": float, ...}]}  sorted ascending
    """
    by_ticker: dict[str, dict] = {}
    for pos in positions:
        t     = pos.ticker
        cost  = float(pos.shares) * float(pos.cost_basis)
        price = prices.get(t, {}).get("price", float(pos.cost_basis))
        val   = float(pos.shares) * price
        if t not in by_ticker:
            by_ticker[t] = {"cost": 0.0, "value": 0.0}
        by_ticker[t]["cost"]  += cost
        by_ticker[t]["value"] += val

    performers = []
    for ticker, d in by_ticker.items():
        pnl     = d["value"] - d["cost"]
        ret_pct = (pnl / d["cost"] * 100) if d["cost"] else 0.0
        performers.append({
            "ticker":       ticker,
            "return_pct":   round(ret_pct, 2),
            "contribution": round(pnl, 2),
        })

    best_performers  = sorted(performers, key=lambda x: x["return_pct"], reverse=True)
    worst_performers = sorted(performers, key=lambda x: x["return_pct"])

    position_tickers = set(by_ticker.keys())
    ticker_returns   = []

    for ticker, bars in histories.items():
        if ticker not in position_tickers or not bars:
            continue
        closes = [float(b["close"]) for b in bars if b.get("close") is not None]
        if not closes:
            continue
        last = closes[-1]

        def _lb(n: int) -> float | None:
            if len(closes) < n + 1:
                return None
            base = closes[-(n + 1)]
            return round((last / base - 1) * 100, 2) if base else None

        ticker_returns.append({
            "ticker":        ticker,
            "return_1w_pct": _lb(5),
            "return_1m_pct": _lb(21),
            "return_3m_pct": _lb(63),
            "return_1y_pct": _lb(252),
        })

    return {
        "best_performers":  best_performers,
        "worst_performers": worst_performers,
        "ticker_returns":   ticker_returns,
    }
