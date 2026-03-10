"""
Portfolio reconstruction from lot data and price histories.

Functions build the daily NAV series from individual position lots,
honouring each lot's open date.
"""
from __future__ import annotations


def build_price_lookup(
    histories: dict[str, list[dict]],
) -> dict[str, dict[str, float]]:
    """
    Build {ticker: {YYYY-MM-DD: close_price}} from raw history bars.
    Only stores entries where close > 0.
    Used by the portfolio reconstruction engine for date-keyed access.
    """
    result: dict[str, dict[str, float]] = {}
    for ticker, bars in histories.items():
        d2c: dict[str, float] = {}
        for bar in bars:
            ds = bar.get("ts", "")[:10]
            c  = float(bar.get("close") or 0)
            if ds and c > 0:
                d2c[ds] = c
        result[ticker] = d2c
    return result


def align_series(
    histories: dict[str, list[dict]],
    ref_ticker: str = "SPY",
) -> tuple[list[str], dict[str, list[float]]]:
    """
    Align all ticker price histories to a common date calendar.

    Args:
        histories: {ticker: [{ts, close, ...}, ...]}  (sorted ascending by ts)
        ref_ticker: Ticker whose dates are used as the canonical calendar.

    Returns:
        (dates, {ticker: [close_prices]})
        Missing dates are forward-filled from the previous close.
    """
    if ref_ticker not in histories or not histories[ref_ticker]:
        ref_ticker = max(histories, key=lambda t: len(histories[t]), default=None)
    if ref_ticker is None:
        return [], {}

    ref_dates = [bar["ts"][:10] for bar in histories[ref_ticker]]
    aligned: dict[str, list[float]] = {}

    for ticker, bars in histories.items():
        d2c = {bar["ts"][:10]: float(bar["close"]) for bar in bars}
        closes: list[float] = []
        last: float | None = None
        for d in ref_dates:
            if d in d2c:
                last = d2c[d]
                closes.append(last)
            elif last is not None:
                closes.append(last)  # forward-fill; skip dates before first valid price
        aligned[ticker] = closes

    return ref_dates, aligned


def reconstruct_portfolio_value(
    price_lookup: dict[str, dict[str, float]],
    lots: list[dict],
    dates: list[str],
) -> tuple[list[str], list[float]]:
    """
    Reconstruct the true daily portfolio value, honouring each lot's opened_at date.

    For each trading day in `dates`, sums (shares × price) for every lot where
    opened_at_date <= date.  Prices are forward-filled across the date calendar;
    cost_basis is used as a warm-start price when no market price has been seen yet.
    Days with no active lots or zero total value are excluded.

    Args:
        price_lookup: {ticker: {YYYY-MM-DD: close_price}}  (build_price_lookup output)
        lots: [{"ticker": str, "shares": float, "cost_basis": float,
                "opened_at_date": str (YYYY-MM-DD)}]
        dates: full market calendar (from align_series)

    Returns:
        (active_dates, portfolio_values) — subset of dates starting from portfolio inception.
    """
    # Only track tickers that appear in lots (avoids scanning benchmarks/other tickers)
    portfolio_tickers = {lot["ticker"] for lot in lots}

    # Warm-start forward-fill with cost_basis so positions with no early price
    # history still appear in NAV from day 1.
    last_prices: dict[str, float] = {}
    for lot in lots:
        t  = lot["ticker"]
        cb = lot.get("cost_basis", 0.0)
        if t not in last_prices and cb > 0:
            last_prices[t] = cb

    active_dates:     list[str]   = []
    portfolio_values: list[float] = []

    for d in dates:
        # ── Update forward-fill with any new prices on this date ──────
        for ticker in portfolio_tickers:
            d2c = price_lookup.get(ticker)
            if d2c:
                p = d2c.get(d)
                if p and p > 0:
                    last_prices[ticker] = p

        # ── Sum value for lots active on this date ────────────────────
        day_value  = 0.0
        any_active = False
        for lot in lots:
            if lot["opened_at_date"] <= d:          # ISO string compare = chronological
                any_active = True
                price = last_prices.get(lot["ticker"])
                if price and price > 0:
                    day_value += lot["shares"] * price

        if any_active and day_value > 0:
            active_dates.append(d)
            portfolio_values.append(round(day_value, 2))

    return active_dates, portfolio_values
