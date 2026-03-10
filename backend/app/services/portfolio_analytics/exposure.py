"""
Portfolio exposure and concentration metrics:
HHI, top-N weight concentration, market capture ratios, turnover.
"""
from __future__ import annotations

from .constants import TRADING_YR
from .math_utils import mean


def compute_exposure_metrics(
    lots:             list[dict],
    price_lookup:     dict[str, dict[str, float]],
    active_dates:     list[str],
    portfolio_values: list[float],
) -> dict:
    """
    Concentration statistics using end-of-period weights.

    Returns: largest_position_weight, top3_weight, top5_weight,
             herfindahl_index  (all as %).
    """
    if not portfolio_values or not active_dates:
        return {}

    portfolio_tickers = {lot["ticker"] for lot in lots}
    total_value       = portfolio_values[-1]

    last_prices: dict[str, float] = {}
    for d in active_dates:
        for ticker in portfolio_tickers:
            d2c = price_lookup.get(ticker)
            if d2c:
                p = d2c.get(d)
                if p and p > 0:
                    last_prices[ticker] = p

    by_ticker: dict[str, float] = {}
    for lot in lots:
        t   = lot["ticker"]
        p   = last_prices.get(t, lot["cost_basis"])
        val = lot["shares"] * p
        by_ticker[t] = by_ticker.get(t, 0.0) + val

    if total_value <= 0:
        return {}

    weights = sorted(
        [v / total_value for v in by_ticker.values()],
        reverse=True,
    )
    return {
        "largest_position_weight": round(weights[0] * 100, 2) if weights else 0.0,
        "top3_weight":             round(sum(weights[:3]) * 100, 2),
        "top5_weight":             round(sum(weights[:5]) * 100, 2),
        "herfindahl_index":        round(sum(w * w for w in weights), 4),
    }


def compute_capture_ratios(
    port_returns: list[float],
    mkt_returns:  list[float],
) -> dict:
    """
    Up/down-market capture ratios vs the primary benchmark.

    upside_capture_ratio  > 1 → aggressive
    downside_capture_ratio < 1 → defensive
    """
    n = min(len(port_returns), len(mkt_returns))
    empty = {"upside_capture_ratio": None, "downside_capture_ratio": None}
    if n < 20:
        return empty

    pr, mr = port_returns[:n], mkt_returns[:n]
    up_p = [pr[i] for i in range(n) if mr[i] > 0]
    up_m = [mr[i] for i in range(n) if mr[i] > 0]
    dn_p = [pr[i] for i in range(n) if mr[i] < 0]
    dn_m = [mr[i] for i in range(n) if mr[i] < 0]

    m_up = mean(up_m) if up_m else 0.0
    m_dn = mean(dn_m) if dn_m else 0.0

    upside   = round(mean(up_p) / m_up, 4) if (up_p and m_up != 0) else None
    downside = round(mean(dn_p) / m_dn, 4) if (dn_p and m_dn != 0) else None
    return {"upside_capture_ratio": upside, "downside_capture_ratio": downside}


def compute_turnover_pct(
    lots:         list[dict],
    price_lookup: dict[str, dict[str, float]],
    active_dates: list[str],
) -> float:
    """
    Estimated annualised turnover (%) from start- vs end-of-period weight drift.

    Uses half-turnover = sum(|Δw|)/2, then annualises by TRADING_YR / period_days.
    """
    if len(active_dates) < 2:
        return 0.0

    portfolio_tickers = {lot["ticker"] for lot in lots}

    def _prices_up_to(idx: int) -> dict[str, float]:
        last: dict[str, float] = {lot["ticker"]: lot["cost_basis"] for lot in lots}
        for d in active_dates[:idx + 1]:
            for t in portfolio_tickers:
                d2c = price_lookup.get(t)
                if d2c:
                    p = d2c.get(d)
                    if p and p > 0:
                        last[t] = p
        return last

    def _weights(day_idx: int) -> dict[str, float]:
        d      = active_dates[day_idx]
        prices = _prices_up_to(day_idx)
        byt: dict[str, float] = {}
        for lot in lots:
            t = lot["ticker"]
            if lot["opened_at_date"] <= d:
                byt[t] = byt.get(t, 0.0) + lot["shares"] * prices.get(t, lot["cost_basis"])
        total = sum(byt.values())
        return {t: v / total for t, v in byt.items()} if total > 0 else {}

    w_start   = _weights(0)
    w_end     = _weights(len(active_dates) - 1)
    tickers   = set(w_start) | set(w_end)
    half_turn = sum(abs(w_end.get(t, 0.0) - w_start.get(t, 0.0)) for t in tickers) / 2

    ann_factor = TRADING_YR / len(active_dates)
    return round(half_turn * ann_factor * 100, 2)
