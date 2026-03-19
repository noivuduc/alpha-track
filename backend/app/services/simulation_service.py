"""
Portfolio simulation service.

Computes "what-if" analytics for adding a new position at a given weight.

CONSISTENCY GUARANTEE
─────────────────────
The "before" snapshot is computed from the SAME TWR daily-return series that
the analytics engine (dashboard) uses for the live portfolio.  This ensures:

    simulation "before" Sharpe  ==  dashboard Sharpe    (within float rounding)

"After" returns are computed as a linear blend:

    after[i] = (1 − w) × portfolio_twr[i]  +  w × new_ticker_daily[i]

This correctly models reallocating (1−w) of each day's gain to the existing
portfolio and w to the new ticker, without requiring a new lot-level
reconstruction for the hypothetical position.

Return-series methods
─────────────────────
  "before" → compute_twr_returns()   same as dashboard
  "after"  → linear blend of TWR + simple daily (both pure market returns)
  metrics  → compute_snapshot()      single canonical formula

All metric logic lives in portfolio_analytics.portfolio_metrics (SoT).
"""
from __future__ import annotations

import asyncio
import logging

import numpy as np

from app.services.data_service import DataService
from app.services.portfolio_analytics.portfolio_metrics import (
    compute_snapshot,
    build_price_lookup,
    align_series,
    reconstruct_portfolio_value,
    build_cash_flows,
    compute_twr_returns,
    daily_returns,
    cumulative_series,
    pearson_corr,
)

log = logging.getLogger(__name__)


# ── Lots extraction ────────────────────────────────────────────────────────────

def _positions_to_lots(positions: list) -> list[dict]:
    """Convert SQLAlchemy Position objects to the lot-dict format expected
    by reconstruct_portfolio_value / build_cash_flows."""
    lots = []
    for pos in positions:
        opened = pos.opened_at
        lots.append({
            "ticker":         pos.ticker,
            "shares":         float(pos.shares),
            "cost_basis":     float(pos.cost_basis),
            "opened_at_date": opened.date().isoformat()
                              if hasattr(opened, "date")
                              else str(opened)[:10],
        })
    return lots


# ── Delta / insight helpers ────────────────────────────────────────────────────

def _delta(before: dict, after: dict) -> dict:
    return {k: round(after[k] - before[k], 4) for k in before}


def _insights(
    before:        dict,
    after:         dict,
    delta:         dict,
    new_ticker:    str,
    corr:          float | None,
    sector_before: dict[str, float],
    sector_after:  dict[str, float],
) -> list[str]:
    msgs: list[str] = []

    if delta["sharpe"] > 0.1:
        msgs.append(
            f"Adding {new_ticker} improves risk-adjusted return "
            f"(Sharpe +{delta['sharpe']:.2f})."
        )
    elif delta["sharpe"] < -0.1:
        msgs.append(
            f"Adding {new_ticker} reduces risk-adjusted return "
            f"(Sharpe {delta['sharpe']:.2f})."
        )

    if delta["volatility_pct"] > 1.0:
        msgs.append(
            f"Portfolio volatility increases by {delta['volatility_pct']:.1f}% (annualized)."
        )
    elif delta["volatility_pct"] < -1.0:
        msgs.append(
            f"Portfolio volatility decreases by {abs(delta['volatility_pct']):.1f}% (annualized)."
        )

    if delta["max_drawdown_pct"] < -2.0:
        msgs.append(
            f"Maximum drawdown worsens by {abs(delta['max_drawdown_pct']):.1f}%."
        )
    elif delta["max_drawdown_pct"] > 2.0:
        msgs.append(
            f"Maximum drawdown improves by {delta['max_drawdown_pct']:.1f}%."
        )

    if delta["beta"] > 0.1:
        msgs.append(
            f"Market sensitivity increases "
            f"(beta {before['beta']:.2f} → {after['beta']:.2f})."
        )
    elif delta["beta"] < -0.1:
        msgs.append(
            f"Market sensitivity decreases "
            f"(beta {before['beta']:.2f} → {after['beta']:.2f})."
        )

    if corr is not None:
        if corr > 0.8:
            msgs.append(
                f"{new_ticker} is highly correlated with the current portfolio "
                f"(ρ={corr:.2f}) — limited diversification benefit."
            )
        elif corr < 0.3:
            msgs.append(
                f"{new_ticker} has low correlation with the current portfolio "
                f"(ρ={corr:.2f}) — strong diversification benefit."
            )

    top_sector = max(sector_after, key=lambda k: sector_after[k], default=None)
    if top_sector and sector_after[top_sector] > 40:
        msgs.append(
            f"Sector concentration: {top_sector} would represent "
            f"{sector_after[top_sector]:.0f}% of the portfolio."
        )

    if not msgs:
        msgs.append(
            f"Adding {new_ticker} has minimal impact on portfolio risk metrics."
        )
    return msgs


# ── Price forward-fill helper ──────────────────────────────────────────────────

def _ff_closes(
    ticker:       str,
    price_lookup: dict[str, dict[str, float]],
    dates:        list[str],
) -> list[float]:
    """
    Return a forward-filled close-price series for `ticker` aligned to `dates`.
    Identical to the _bench_ff() logic inside compute_engine() so benchmark
    treatment is consistent.
    """
    d2c:   dict[str, float] = price_lookup.get(ticker, {})
    last_p: float | None    = None
    out:   list[float]      = []
    for d in dates:
        p = d2c.get(d)
        if p and p > 0:
            last_p = p
        if last_p is not None:
            out.append(last_p)
    return out


# ── Date-return map helper ─────────────────────────────────────────────────────

def _date_return_map(
    prices: list[float],
    dates:  list[str],
) -> dict[str, float]:
    """Build {date: daily_return} from a forward-filled price+date series.

    Inline loop guarantees 1-to-1 dates[i] → return correspondence.
    Avoids daily_returns() which silently skips entries when prev == 0,
    breaking the date→return mapping.
    """
    if len(prices) < 2:
        return {}
    d2r: dict[str, float] = {}
    for i in range(1, len(prices)):
        if prices[i - 1] > 0:
            d2r[dates[i]] = prices[i] / prices[i - 1] - 1.0
    return d2r


# ── Main simulation function ───────────────────────────────────────────────────

async def simulate_add_position(
    positions:      list,
    new_ticker:     str,
    new_weight_pct: float,
    ds:             DataService,
    benchmark:      str = "SPY",
) -> dict:
    """
    Simulate adding `new_ticker` at `new_weight_pct`% of portfolio value.

    CONSISTENCY GUARANTEE:
        The "before" metrics are computed from the SAME TWR return series
        that the analytics dashboard uses.  Both call compute_snapshot()
        from portfolio_metrics (single source of truth).

    Returns a dict compatible with SimulateResponse:
        { before, after, delta, exposure, insights,
          new_ticker_weight_pct, correlation_with_portfolio }
    """
    new_weight = new_weight_pct / 100.0

    # ── Step 1: Build lots from positions ─────────────────────────────────────
    lots             = _positions_to_lots(positions)
    existing_tickers = list({lot["ticker"] for lot in lots})
    all_tickers      = list({*existing_tickers, new_ticker})

    # ── Step 2: Fetch price history for all tickers + benchmark ───────────────
    fetch_tickers = list({*all_tickers, benchmark, "SPY", "QQQ"})

    async def _hist(t: str):
        try:
            data = await ds.get_price_history(t, period="1y", interval="1d")
            return t, data
        except Exception as e:
            log.warning("simulate: history fetch failed for %s: %s", t, e)
            return t, []

    raw      = await asyncio.gather(*[_hist(t) for t in fetch_tickers])
    histories = {t: d for t, d in raw if d}

    # ── Step 3: Align calendar + build price lookup ────────────────────────────
    ref = (
        benchmark if benchmark in histories else
        "SPY"     if "SPY"     in histories else
        existing_tickers[0]
    )
    dates, _aligned  = align_series(histories, ref_ticker=ref)
    price_lookup     = build_price_lookup(histories)

    if len(dates) < 5:
        raise ValueError("Insufficient price history to run simulation")

    # ── Step 4: Reconstruct portfolio value (lot-aware, same as dashboard) ────
    active_dates, portfolio_values = reconstruct_portfolio_value(
        price_lookup, lots, dates
    )
    if not portfolio_values:
        raise ValueError("Could not reconstruct portfolio value — check positions and price history")

    # ── Step 5: "Before" returns — TWR (identical to dashboard) ──────────────
    # MUST use compute_twr_returns so that simulation "before" metrics match
    # the dashboard exactly.  Simple daily_returns would inflate performance on
    # days when new lots were added (cash-flow distortion).
    cash_flows  = build_cash_flows(lots, active_dates)
    before_rets = compute_twr_returns(portfolio_values, active_dates, cash_flows)
    # NaN filter — mirrors compute_engine() so metrics are consistent
    _raw  = np.asarray(before_rets, dtype=np.float64)
    _mask = ~np.isnan(_raw)
    before_rets  = _raw[_mask].tolist()
    return_dates: list[str] = [
        d for d, m in zip(active_dates[1:], _mask.tolist()) if m
    ]
    before_vals = cumulative_series(before_rets)

    if len(before_rets) < 5:
        raise ValueError("Insufficient active trading days in portfolio history")

    # ── Step 6: New ticker returns aligned BY DATE to return_dates ────────────
    # Build a date→return map from the forward-filled price series so alignment
    # is calendar-based, not positional (avoids mixing returns from different dates).
    new_closes = _ff_closes(new_ticker, price_lookup, active_dates)
    new_ff_dates: list[str] = []
    _lp: float | None = None
    for d in active_dates:
        p = price_lookup.get(new_ticker, {}).get(d)
        if p and p > 0:
            _lp = p
        if _lp is not None:
            new_ff_dates.append(d)
    new_d2r = _date_return_map(new_closes, new_ff_dates)
    n = len(before_rets)
    new_rets_aligned: list[float] = [new_d2r.get(d, 0.0) for d in return_dates]

    # ── Step 7: "After" returns — weighted blend of TWR + simple ─────────────
    # after[i] = (1−w) × portfolio_twr[i]  +  w × new_ticker_daily[i]
    #
    # portfolio_twr is cash-flow-stripped; new_ticker_daily is simple.
    # Both represent pure daily market returns and can be linearly combined.
    after_rets = [
        (1.0 - new_weight) * before_rets[i] + new_weight * new_rets_aligned[i]
        for i in range(n)
    ]
    after_vals = cumulative_series(after_rets)

    # ── Step 8: SPY returns — date-aligned intersection ───────────────────────
    # Build a date→return map for SPY so beta/alpha use the correct calendar
    # dates, not a positional truncation with [:min(len,len)].
    spy_closes_ff = _ff_closes("SPY", price_lookup, active_dates)
    spy_ff_dates: list[str] = []
    _lsp: float | None = None
    for d in active_dates:
        p = price_lookup.get("SPY", {}).get(d)
        if p and p > 0:
            _lsp = p
        if _lsp is not None:
            spy_ff_dates.append(d)
    spy_d2r = _date_return_map(spy_closes_ff, spy_ff_dates)
    # Intersect portfolio return dates with SPY return dates (before)
    port_for_spy_b: list[float] = []
    spy_aligned_b:  list[float] = []
    for d, pr in zip(return_dates, before_rets):
        if d in spy_d2r:
            port_for_spy_b.append(pr)
            spy_aligned_b.append(spy_d2r[d])
    # Same intersection for after returns
    port_for_spy_a: list[float] = []
    spy_aligned_a:  list[float] = []
    for d, ar in zip(return_dates, after_rets):
        if d in spy_d2r:
            port_for_spy_a.append(ar)
            spy_aligned_a.append(spy_d2r[d])

    # ── Step 9: Compute snapshots via the SINGLE canonical function ────────────
    # Full port_returns → Sharpe/Sortino/vol/VaR/win_rate (portfolio-only metrics).
    # port_for_spy_* + spy_aligned_* → beta/alpha (properly date-aligned pairs).
    before_snap = compute_snapshot(
        before_rets, before_vals, spy_aligned_b,
        label="sim_before", port_for_spy=port_for_spy_b,
    )
    after_snap = compute_snapshot(
        after_rets, after_vals, spy_aligned_a,
        label="sim_after", port_for_spy=port_for_spy_a,
    )
    delta = _delta(before_snap, after_snap)

    # ── Step 10: Correlation of new ticker with current portfolio ─────────────
    # Use date-aligned new-ticker returns (same calendar as return_dates)
    new_rets_for_corr: list[float] = [new_d2r.get(d, 0.0) for d in return_dates]
    corr = pearson_corr(new_rets_for_corr, before_rets)

    # ── Step 11: Sector exposure ───────────────────────────────────────────────
    # Current market-value weights for sector allocation
    prices = await ds.get_prices_bulk(all_tickers)
    mv = {
        pos.ticker: float(pos.shares) * prices.get(pos.ticker, {}).get(
            "price", float(pos.cost_basis)
        )
        for pos in positions
    }
    total_mv       = sum(mv.values()) or 1.0
    before_weights = {t: v / total_mv for t, v in mv.items()}
    after_weights  = {t: w * (1.0 - new_weight) for t, w in before_weights.items()}
    after_weights[new_ticker] = new_weight

    async def _sector(t: str) -> tuple[str, str | None]:
        try:
            facts  = await ds.get_company_facts(t)
            sector = (facts.get("company_facts") or {}).get("sector")
            return t, sector
        except Exception:
            return t, None

    sector_results = await asyncio.gather(*[_sector(t) for t in all_tickers])
    ticker_sector  = {t: s for t, s in sector_results if s}

    def _sector_weights(weights: dict[str, float]) -> dict[str, float]:
        out: dict[str, float] = {}
        for t, w in weights.items():
            sec = ticker_sector.get(t, "Unknown")
            out[sec] = round(out.get(sec, 0.0) + w * 100, 2)
        return out

    sector_before = _sector_weights(before_weights)
    sector_after  = _sector_weights(after_weights)

    # ── Step 12: Insights ─────────────────────────────────────────────────────
    insights = _insights(
        before_snap, after_snap, delta,
        new_ticker, corr, sector_before, sector_after,
    )

    log.info(
        "simulate [%s +%s@%.0f%%]: before_sharpe=%.4f after_sharpe=%.4f "
        "delta_sharpe=%.4f n_days=%d",
        "|".join(existing_tickers[:3]),
        new_ticker,
        new_weight_pct,
        before_snap["sharpe"],
        after_snap["sharpe"],
        delta["sharpe"],
        n,
    )

    return {
        "before":                     before_snap,
        "after":                      after_snap,
        "delta":                      delta,
        "exposure": {
            "sector_before": sector_before,
            "sector_after":  sector_after,
        },
        "insights":                   insights,
        "new_ticker_weight_pct":      round(new_weight * 100, 2),
        "correlation_with_portfolio": corr,
    }
