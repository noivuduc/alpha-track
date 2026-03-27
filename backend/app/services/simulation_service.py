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
import json as _json
import logging
import uuid as _uuid
from datetime import datetime, timezone
from decimal import Decimal

import numpy as np

from app.services.data_reader import DataReader
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


def _tx_price_for_apply(
    ticker: str,
    prices_bulk: dict,
    price_lookup: dict[str, dict[str, float]],
) -> float | None:
    """Same price resolution as simulate_scenario / apply_scenario."""
    p = prices_bulk.get(ticker, {}).get("price")
    if p is not None and float(p) > 0:
        return float(p)
    tk_prices = price_lookup.get(ticker, {})
    if tk_prices:
        return float(tk_prices[max(tk_prices.keys())])
    return None


def _resolve_shares_delta(
    tx: dict,
    prices_bulk: dict,
    price_lookup: dict[str, dict[str, float]],
    mv: dict[str, float],
    total_mv: float,
) -> float:
    """Mirror apply_scenario share delta (always positive magnitude)."""
    ticker = tx["ticker"].upper()
    mode   = tx["mode"]
    value  = float(tx["value"])
    price  = _tx_price_for_apply(ticker, prices_bulk, price_lookup)
    if price is None or price <= 0:
        raise ValueError(f"No price available for {ticker}")

    if mode == "shares":
        return value
    if mode == "amount":
        return value / price
    if mode == "weight_pct":
        return (value / 100.0 * total_mv) / price
    if mode == "target_weight":
        target_w  = value / 100.0
        cur_mv    = mv.get(ticker, 0.0)
        target_mv = target_w * total_mv
        return abs(target_mv - cur_mv) / price
    raise ValueError(f"Unknown mode: {mode}")


def _apply_transactions_to_merged_shares(
    lots_merged: dict[str, dict],
    transactions: list[dict],
    prices_bulk: dict,
    price_lookup: dict[str, dict[str, float]],
    mv: dict[str, float],
    total_mv: float,
) -> dict[str, float]:
    """
    Post-trade share counts per ticker (merged lots), matching apply_scenario.

    Selling only reduces the sold ticker’s shares; other tickers’ share counts
    stay the same — only their *weight %* moves when total portfolio MV changes.
    This avoids misleading \"increased\" labels on names we did not trade.
    """
    shares: dict[str, float] = {t: float(lo["shares"]) for t, lo in lots_merged.items()}

    for tx in transactions:
        ticker = tx["ticker"].upper()
        action = tx["action"]
        shares_delta = _resolve_shares_delta(tx, prices_bulk, price_lookup, mv, total_mv)

        if action == "buy":
            shares[ticker] = shares.get(ticker, 0.0) + shares_delta
        elif action == "sell":
            total_t = shares.get(ticker, 0.0)
            if total_t <= 0:
                continue
            sell_fraction = min(shares_delta / total_t, 1.0)
            new_sh = total_t * (1.0 - sell_fraction)
            if new_sh < 1e-6:
                del shares[ticker]
            else:
                shares[ticker] = new_sh
        else:
            raise ValueError(f"Unknown action: {action}")

    return shares


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


# ── Scenario insights helper ───────────────────────────────────────────────────

def _scenario_insights(
    before:        dict,
    after:         dict,
    delta:         dict,
    summary:       dict,
    sector_before: dict[str, float],
    sector_after:  dict[str, float],
) -> list[str]:
    msgs: list[str] = []

    added   = summary["tickers_added"]
    removed = summary["tickers_removed"]

    if added:
        msgs.append(f"Adding {', '.join(added)} as new position(s).")
    if removed:
        msgs.append(f"Exiting {', '.join(removed)}.")

    if delta["sharpe"] > 0.1:
        msgs.append(f"Risk-adjusted return improves (Sharpe +{delta['sharpe']:.2f}).")
    elif delta["sharpe"] < -0.1:
        msgs.append(f"Risk-adjusted return declines (Sharpe {delta['sharpe']:.2f}).")

    if delta["volatility_pct"] > 1.0:
        msgs.append(f"Portfolio volatility increases by {delta['volatility_pct']:.1f}% (annualized).")
    elif delta["volatility_pct"] < -1.0:
        msgs.append(f"Portfolio volatility decreases by {abs(delta['volatility_pct']):.1f}% (annualized).")

    if delta["max_drawdown_pct"] < -2.0:
        msgs.append(f"Maximum drawdown worsens by {abs(delta['max_drawdown_pct']):.1f}%.")
    elif delta["max_drawdown_pct"] > 2.0:
        msgs.append(f"Maximum drawdown improves by {delta['max_drawdown_pct']:.1f}%.")

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

    top_sector = max(sector_after, key=lambda k: sector_after[k], default=None)
    if top_sector and sector_after[top_sector] > 40:
        msgs.append(
            f"Sector concentration: {top_sector} would represent "
            f"{sector_after[top_sector]:.0f}% after changes."
        )

    net_cash = summary["net_cash_delta"]
    if net_cash > 100:
        msgs.append(f"Scenario requires ~${net_cash:,.0f} in new capital.")
    elif net_cash < -100:
        msgs.append(f"Scenario frees ~${abs(net_cash):,.0f} in capital.")

    if not msgs:
        msgs.append("Scenario has minimal impact on portfolio risk metrics.")
    return msgs


# ── Multi-transaction scenario simulation ──────────────────────────────────────

async def simulate_scenario(
    positions:    list,
    transactions: list[dict],   # each: {action, ticker, mode, value}
    reader:       DataReader,
    benchmark:    str = "SPY",
) -> dict:
    """
    Simulate an arbitrary set of buy/sell transactions on the portfolio.

    Transaction modes:
      "shares"        — value is number of shares
      "amount"        — value is dollar amount
      "weight_pct"    — value is % of portfolio value to add/remove (not a target)
      "target_weight" — value is the desired final weight % for this ticker

    Returns ScenarioResponse-compatible dict:
        { before, after, delta, exposure, insights,
          holdings_before, holdings_after, scenario_summary }
    """
    # ── Step 1: Tickers ────────────────────────────────────────────────────────
    lots             = _positions_to_lots(positions)
    existing_tickers = list({lot["ticker"] for lot in lots})
    tx_tickers       = list({tx["ticker"].upper() for tx in transactions})
    all_tickers      = list({*existing_tickers, *tx_tickers})
    fetch_tickers    = list({*all_tickers, benchmark, "SPY", "QQQ"})

    # ── Step 2: Price histories ────────────────────────────────────────────────
    async def _hist(t: str):
        data = await reader.get_price_history(t, period="1y", interval="1d")
        return t, data or []

    raw      = await asyncio.gather(*[_hist(t) for t in fetch_tickers])
    histories = {t: d for t, d in raw if d}

    # ── Step 3: Align dates + price lookup ────────────────────────────────────
    ref = (
        benchmark if benchmark in histories else
        "SPY"     if "SPY"     in histories else
        existing_tickers[0]
    )
    dates, _aligned = align_series(histories, ref_ticker=ref)
    price_lookup    = build_price_lookup(histories)

    if len(dates) < 5:
        raise ValueError("Insufficient price history to run simulation")

    # ── Step 4: Reconstruct "before" portfolio value (TWR) ────────────────────
    active_dates, portfolio_values = reconstruct_portfolio_value(
        price_lookup, lots, dates
    )
    if not portfolio_values:
        raise ValueError("Could not reconstruct portfolio value — check positions")

    cash_flows  = build_cash_flows(lots, active_dates)
    before_rets = compute_twr_returns(portfolio_values, active_dates, cash_flows)
    _raw_arr    = np.asarray(before_rets, dtype=np.float64)
    _mask       = ~np.isnan(_raw_arr)
    before_rets = _raw_arr[_mask].tolist()
    return_dates: list[str] = [
        d for d, m in zip(active_dates[1:], _mask.tolist()) if m
    ]
    before_vals = cumulative_series(before_rets)

    if len(before_rets) < 5:
        raise ValueError("Insufficient active trading days in portfolio history")

    # ── Step 5: Current prices + market values ────────────────────────────────
    prices_bulk = await reader.get_prices_bulk(all_tickers)
    mv = {
        pos.ticker: float(pos.shares) * prices_bulk.get(pos.ticker, {}).get(
            "price", float(pos.cost_basis)
        )
        for pos in positions
    }
    total_mv        = sum(mv.values()) or 1.0
    current_weights = {t: v / total_mv for t, v in mv.items()}

    # ── Step 6: Apply transactions → target weights ───────────────────────────
    target_weights = dict(current_weights)
    net_cash_delta = 0.0   # positive = cash needed, negative = cash freed

    for tx in transactions:
        ticker = tx["ticker"].upper()
        action = tx["action"]
        mode   = tx["mode"]
        value  = float(tx["value"])

        # Resolve current price for ticker
        price: float | None = prices_bulk.get(ticker, {}).get("price")
        if price is None or price <= 0:
            # Fall back to last known price in history
            tk_prices = price_lookup.get(ticker, {})
            price = tk_prices[max(tk_prices.keys())] if tk_prices else None
        if price is None or price <= 0:
            raise ValueError(f"No price available for {ticker}")

        # ── target_weight mode: set ticker to exact final weight, scale others ─
        if mode == "target_weight":
            target_w = value / 100.0
            if target_w <= 0 or target_w >= 1.0:
                raise ValueError(f"target_weight must be between 0 and 100 (exclusive)")
            cur_w = target_weights.get(ticker, 0.0)
            others_total = sum(w for t, w in target_weights.items() if t != ticker)

            if action == "buy" and target_w <= cur_w:
                raise ValueError(
                    f"target_weight {value}% ≤ current weight {cur_w*100:.1f}% for {ticker}. "
                    f"Use action=sell to reduce a position."
                )
            if action == "sell" and target_w >= cur_w:
                if cur_w < 1e-6:
                    raise ValueError(f"Cannot sell {ticker}: not in portfolio")
                raise ValueError(
                    f"target_weight {value}% ≥ current weight {cur_w*100:.1f}% for {ticker}. "
                    f"Use action=buy to increase a position."
                )

            # Scale all other tickers proportionally so they still sum to (1 - target_w)
            if others_total > 1e-6:
                scale = (1.0 - target_w) / others_total
                target_weights = {t: w * scale for t, w in target_weights.items() if t != ticker}
            else:
                target_weights = {}
            target_weights[ticker] = target_w

            delta_mv = (target_w - cur_w) * total_mv   # positive=buy, negative=sell
            net_cash_delta += delta_mv
            continue

        # Resolve delta as fraction of portfolio value
        if mode == "shares":
            delta_mv = value * price
        elif mode == "amount":
            delta_mv = value
        elif mode == "weight_pct":
            delta_mv = value / 100.0 * total_mv
        else:
            raise ValueError(f"Unknown mode: {mode}")

        delta_w = delta_mv / total_mv

        if action == "buy":
            scale = max(1.0 - delta_w, 0.0)
            target_weights = {t: w * scale for t, w in target_weights.items()}
            target_weights[ticker] = target_weights.get(ticker, 0.0) + delta_w
            net_cash_delta += delta_mv

        elif action == "sell":
            cur_w = target_weights.get(ticker, 0.0)
            if cur_w < 1e-6:
                raise ValueError(f"Cannot sell {ticker}: not in portfolio")
            if delta_w > cur_w + 1e-6:
                raise ValueError(
                    f"Cannot sell {value} {mode} of {ticker}: "
                    f"only {cur_w * total_mv:.2f} available"
                )
            actual_delta_w = min(delta_w, cur_w)
            target_weights[ticker] = cur_w - actual_delta_w
            if target_weights[ticker] < 1e-4:
                del target_weights[ticker]
            net_cash_delta -= actual_delta_w * total_mv

    # Normalize to sum to 1
    total_w = sum(target_weights.values())
    if total_w < 1e-6:
        raise ValueError("Scenario removes all positions from the portfolio")
    target_weights = {t: w / total_w for t, w in target_weights.items()}

    # ── Step 7: Date→return maps for each ticker in target portfolio ──────────
    ticker_d2r: dict[str, dict[str, float]] = {}
    for t in target_weights:
        closes    = _ff_closes(t, price_lookup, active_dates)
        ff_dates2: list[str] = []
        _lp2: float | None   = None
        for d in active_dates:
            p = price_lookup.get(t, {}).get(d)
            if p and p > 0:
                _lp2 = p
            if _lp2 is not None:
                ff_dates2.append(d)
        ticker_d2r[t] = _date_return_map(closes, ff_dates2)

    # ── Step 8: "After" returns — weighted sum of constituent returns ──────────
    after_rets = [
        sum(w * ticker_d2r.get(t, {}).get(d, 0.0) for t, w in target_weights.items())
        for d in return_dates
    ]
    after_vals = cumulative_series(after_rets)

    # ── Step 9: SPY alignment ─────────────────────────────────────────────────
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

    port_for_spy_b: list[float] = []
    spy_aligned_b:  list[float] = []
    for d, pr in zip(return_dates, before_rets):
        if d in spy_d2r:
            port_for_spy_b.append(pr)
            spy_aligned_b.append(spy_d2r[d])
    port_for_spy_a: list[float] = []
    spy_aligned_a:  list[float] = []
    for d, ar in zip(return_dates, after_rets):
        if d in spy_d2r:
            port_for_spy_a.append(ar)
            spy_aligned_a.append(spy_d2r[d])

    # ── Step 10: Compute snapshots ────────────────────────────────────────────
    before_snap = compute_snapshot(
        before_rets, before_vals, spy_aligned_b,
        label="sim_before", port_for_spy=port_for_spy_b,
    )
    after_snap = compute_snapshot(
        after_rets, after_vals, spy_aligned_a,
        label="sim_after", port_for_spy=port_for_spy_a,
    )
    delta = _delta(before_snap, after_snap)

    # ── Step 11: Holdings before / after ─────────────────────────────────────
    before_tickers = {lot["ticker"] for lot in lots}
    after_tickers  = set(target_weights.keys())

    # Merge same-ticker lots for display
    lots_merged: dict[str, dict] = {}
    for lot in lots:
        t = lot["ticker"]
        if t in lots_merged:
            lots_merged[t]["shares"] += lot["shares"]
        else:
            lots_merged[t] = dict(lot)

    holdings_before = sorted([
        {
            "ticker":       t,
            "shares":       round(lo["shares"], 4),
            "weight_pct":   round(mv.get(t, 0.0) / total_mv * 100, 2),
            "market_value": round(mv.get(t, 0.0), 2),
            "change":       None,
        }
        for t, lo in lots_merged.items()
    ], key=lambda x: -x["market_value"])

    # Share counts after applying the same rules as apply_scenario (not normalized
    # target weights — those imply rebalancing others when only one name is sold).
    shares_after = _apply_transactions_to_merged_shares(
        lots_merged, transactions, prices_bulk, price_lookup, mv, total_mv,
    )

    def _px_row(t: str) -> float:
        p = _tx_price_for_apply(t, prices_bulk, price_lookup)
        if p and p > 0:
            return p
        if t in lots_merged:
            return float(lots_merged[t].get("cost_basis") or 0.0)
        return 0.0

    mv_after: dict[str, float] = {
        t: shares_after[t] * _px_row(t) for t in shares_after
    }
    total_mv_after = sum(mv_after.values()) or 1.0

    share_tickers_after = set(shares_after.keys())
    added_tickers   = sorted(share_tickers_after - set(lots_merged.keys()))
    removed_tickers = sorted(set(lots_merged.keys()) - share_tickers_after)
    changed_tickers = sorted(
        t for t in (set(lots_merged.keys()) & share_tickers_after)
        if abs(shares_after[t] - float(lots_merged[t]["shares"])) > 1e-4
    )

    def _change_label_shares(t: str) -> str | None:
        if t in added_tickers:
            return "new"
        if t not in lots_merged:
            return None
        prev_sh = float(lots_merged[t]["shares"])
        new_sh  = shares_after.get(t, 0.0)
        if abs(new_sh - prev_sh) < 1e-4:
            return None
        return "increased" if new_sh > prev_sh else "reduced"

    holdings_after = sorted([
        {
            "ticker":       t,
            "shares":       round(shares_after[t], 4),
            "weight_pct":   round(mv_after[t] / total_mv_after * 100, 2),
            "market_value": round(mv_after[t], 2),
            "change":       _change_label_shares(t),
        }
        for t in shares_after
    ], key=lambda x: -x["market_value"])

    # ── Step 12: Sector exposure ──────────────────────────────────────────────
    all_sector_tickers = list({*before_tickers, *after_tickers, *share_tickers_after})

    async def _sector(t: str) -> tuple[str, str | None]:
        try:
            facts  = await reader.get_company_facts(t)
            sector = ((facts or {}).get("company_facts") or {}).get("sector")
            return t, sector
        except Exception:
            return t, None

    sector_results = await asyncio.gather(*[_sector(t) for t in all_sector_tickers])
    ticker_sector  = {t: s for t, s in sector_results if s}

    def _sector_weights(weights: dict[str, float]) -> dict[str, float]:
        out: dict[str, float] = {}
        for t, w in weights.items():
            sec     = ticker_sector.get(t, "Unknown")
            out[sec] = round(out.get(sec, 0.0) + w * 100, 2)
        return out

    sector_before = _sector_weights(current_weights)
    sector_after  = _sector_weights(target_weights)

    # ── Step 13: Scenario summary + insights ──────────────────────────────────
    scenario_summary = {
        # User-entered transaction counts (one per input row)
        "transaction_count": len(transactions),
        "buy_count":  sum(1 for tx in transactions if tx["action"] == "buy"),
        "sell_count": sum(1 for tx in transactions if tx["action"] == "sell"),
        # Affected holdings — tickers whose *share count* changes (matches apply)
        "tickers_added":   added_tickers,
        "tickers_removed": removed_tickers,
        "tickers_changed": changed_tickers,
        "net_cash_delta":  round(net_cash_delta, 2),
    }

    insights = _scenario_insights(
        before_snap, after_snap, delta,
        scenario_summary, sector_before, sector_after,
    )

    log.info(
        "simulate_scenario [%s]: %d txns, before_sharpe=%.4f after_sharpe=%.4f "
        "delta_sharpe=%.4f n_days=%d",
        "|".join(existing_tickers[:3]),
        len(transactions),
        before_snap["sharpe"],
        after_snap["sharpe"],
        delta["sharpe"],
        len(before_rets),
    )

    return {
        "before":           before_snap,
        "after":            after_snap,
        "delta":            delta,
        "exposure": {
            "sector_before": sector_before,
            "sector_after":  sector_after,
        },
        "insights":          insights,
        "holdings_before":   holdings_before,
        "holdings_after":    holdings_after,
        "scenario_summary":  scenario_summary,
    }


# ── Main simulation function ───────────────────────────────────────────────────

async def simulate_add_position(
    positions:      list,
    new_ticker:     str,
    new_weight_pct: float,
    reader:         DataReader,
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

    # ── Step 2: Read price history from cache (no external calls) ───────────
    fetch_tickers = list({*all_tickers, benchmark, "SPY", "QQQ"})

    async def _hist(t: str):
        data = await reader.get_price_history(t, period="1y", interval="1d")
        return t, data or []

    raw       = await asyncio.gather(*[_hist(t) for t in fetch_tickers])
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
    prices = await reader.get_prices_bulk(all_tickers)
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
            facts = await reader.get_company_facts(t)
            sector = ((facts or {}).get("company_facts") or {}).get("sector")
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


# ── Scenario persistence ────────────────────────────────────────────────────────

_SCENARIO_TTL = 900  # 15 minutes


def _scenario_cache_key(scenario_id: str) -> str:
    return f"scenario:{scenario_id}"


async def store_scenario(
    cache:               object,     # app.database.Cache
    portfolio_id:        str,
    user_id:             str,
    transactions:        list[dict],
    portfolio_snapshot:  dict[str, float],  # {ticker: total_shares}
) -> str:
    """Persist the scenario in Redis for the apply step.  Returns scenario_id."""
    scenario_id = str(_uuid.uuid4())
    payload = {
        "scenario_id":        scenario_id,
        "portfolio_id":       str(portfolio_id),
        "user_id":            str(user_id),
        "transactions":       transactions,
        "portfolio_snapshot": portfolio_snapshot,
        "computed_at":        datetime.now(timezone.utc).isoformat(),
    }
    await cache.set(_scenario_cache_key(scenario_id), _json.dumps(payload), ttl=_SCENARIO_TTL)
    log.info("stored scenario %s for portfolio %s (ttl=%ds)", scenario_id, portfolio_id, _SCENARIO_TTL)
    return scenario_id


# ── Scenario apply ─────────────────────────────────────────────────────────────

async def apply_scenario(
    scenario_id:  str,
    portfolio_id: str,
    user_id:      str,
    db:           object,    # AsyncSession
    cache:        object,    # Cache
    reader:       "DataReader",
) -> dict:
    """
    Apply a previously simulated scenario to the real portfolio.

    Safety checks:
      1. Scenario exists and hasn't expired (15-min TTL)
      2. Scenario belongs to this portfolio and user
      3. Portfolio hasn't changed materially since simulation (±10% shares per ticker)
      4. All transactions are still valid at current prices

    For each BUY  → creates a new Position lot + Transaction record
    For each SELL → reduces / closes existing Position lot(s) + Transaction record

    Writes an AuditLog entry with full transaction detail.
    """
    from sqlalchemy import select
    from app.models import Position, Transaction, AuditLog

    # ── 1. Load from Redis ────────────────────────────────────────────────────
    raw = await cache.get(_scenario_cache_key(scenario_id))
    if not raw:
        raise ValueError(
            "Scenario not found or expired (15-min limit). "
            "Please re-run the simulation before applying."
        )
    scenario = _json.loads(raw)

    # ── 2. Ownership check ────────────────────────────────────────────────────
    if str(scenario["portfolio_id"]) != str(portfolio_id):
        raise PermissionError("Scenario does not belong to this portfolio")
    if str(scenario["user_id"]) != str(user_id):
        raise PermissionError("Scenario does not belong to this user")

    # ── 3. Load current open positions ────────────────────────────────────────
    pos_r = await db.execute(
        select(Position).where(
            Position.portfolio_id == portfolio_id,
            Position.closed_at    == None,
        ).order_by(Position.opened_at)
    )
    open_positions: list = pos_r.scalars().all()

    # ── 4. Staleness check: compare snapshot to current shares ────────────────
    current_shares: dict[str, float] = {}
    for pos in open_positions:
        current_shares[pos.ticker] = current_shares.get(pos.ticker, 0.0) + float(pos.shares)

    snapshot = scenario["portfolio_snapshot"]  # {ticker: shares_at_simulation_time}
    for ticker, expected in snapshot.items():
        actual = current_shares.get(ticker, 0.0)
        if expected > 0 and abs(actual - expected) / expected > 0.10:
            raise ValueError(
                f"Portfolio has changed significantly since simulation "
                f"({ticker}: expected ~{expected:.2f} shares, found {actual:.2f}). "
                "Please re-run the simulation."
            )

    # ── 5. Current prices ─────────────────────────────────────────────────────
    tx_tickers  = list({tx["ticker"].upper() for tx in scenario["transactions"]})
    all_tickers = list({pos.ticker for pos in open_positions} | set(tx_tickers))
    prices      = await reader.get_prices_bulk(all_tickers)

    mv = {
        pos.ticker: float(pos.shares) * prices.get(pos.ticker, {}).get(
            "price", float(pos.cost_basis)
        )
        for pos in open_positions
    }
    total_mv = sum(mv.values()) or 1.0

    # ── 6. Apply each transaction ─────────────────────────────────────────────
    now               = datetime.now(timezone.utc)
    positions_created = 0
    positions_updated = 0
    positions_closed  = 0
    txn_records       = 0
    applied_log       = []

    for tx in scenario["transactions"]:
        ticker = tx["ticker"].upper()
        action = tx["action"]
        mode   = tx["mode"]
        value  = float(tx["value"])

        price: float | None = prices.get(ticker, {}).get("price")
        if price is None or price <= 0:
            raise ValueError(f"No current price for {ticker} — cannot apply")

        # Resolve shares
        if mode == "shares":
            shares_delta = value
        elif mode == "amount":
            shares_delta = value / price
        elif mode == "weight_pct":
            shares_delta = (value / 100.0 * total_mv) / price
        elif mode == "target_weight":
            # target_weight: final desired portfolio weight % → delta shares from current
            target_w   = value / 100.0
            cur_mv     = mv.get(ticker, 0.0)
            target_mv  = target_w * total_mv
            shares_delta = abs(target_mv - cur_mv) / price
        else:
            raise ValueError(f"Unknown mode: {mode}")

        note_prefix = f"Scenario {scenario_id[:8]}"

        if action == "buy":
            new_pos = Position(
                portfolio_id = portfolio_id,
                ticker       = ticker,
                shares       = Decimal(str(round(shares_delta, 6))),
                cost_basis   = Decimal(str(round(price, 6))),
                notes        = note_prefix,
                opened_at    = now,
            )
            db.add(new_pos)
            positions_created += 1

            db.add(Transaction(
                portfolio_id = portfolio_id,
                ticker       = ticker,
                side         = "buy",
                shares       = Decimal(str(round(shares_delta, 6))),
                price        = Decimal(str(round(price, 6))),
                fees         = Decimal("0"),
                traded_at    = now,
                notes        = note_prefix,
            ))
            txn_records += 1

        elif action == "sell":
            ticker_lots = [p for p in open_positions if p.ticker == ticker]
            if not ticker_lots:
                raise ValueError(f"Cannot sell {ticker}: no open positions")

            total_ticker = sum(float(p.shares) for p in ticker_lots)
            if shares_delta > total_ticker + 1e-6:
                raise ValueError(
                    f"Cannot sell {shares_delta:.4f} shares of {ticker}: "
                    f"only {total_ticker:.4f} held"
                )

            sell_fraction = min(shares_delta / total_ticker, 1.0)
            for pos in ticker_lots:
                remaining = float(pos.shares) * (1.0 - sell_fraction)
                if remaining < 0.0001:
                    pos.closed_at = now
                    positions_closed += 1
                else:
                    pos.shares = Decimal(str(round(remaining, 6)))
                    positions_updated += 1

            db.add(Transaction(
                portfolio_id = portfolio_id,
                ticker       = ticker,
                side         = "sell",
                shares       = Decimal(str(round(shares_delta, 6))),
                price        = Decimal(str(round(price, 6))),
                fees         = Decimal("0"),
                traded_at    = now,
                notes        = note_prefix,
            ))
            txn_records += 1

        applied_log.append({
            "action": action, "ticker": ticker,
            "shares": round(shares_delta, 4), "price": round(price, 4),
        })

    # ── 7. Audit log ──────────────────────────────────────────────────────────
    db.add(AuditLog(
        user_id   = user_id,
        action    = "scenario_apply",
        entity    = "portfolio",
        entity_id = portfolio_id,
        meta      = {
            "scenario_id":           scenario_id,
            "transactions_count":    len(scenario["transactions"]),
            "applied_at":            now.isoformat(),
            "applied_transactions":  applied_log,
            "positions_created":     positions_created,
            "positions_updated":     positions_updated,
            "positions_closed":      positions_closed,
        },
    ))

    await db.commit()

    # Consume the scenario (prevents double-apply)
    await cache.delete(_scenario_cache_key(scenario_id))

    log.info(
        "apply_scenario [portfolio=%s scenario=%s user=%s]: "
        "created=%d updated=%d closed=%d txns=%d",
        portfolio_id, scenario_id, user_id,
        positions_created, positions_updated, positions_closed, txn_records,
    )

    return {
        "applied_transactions": txn_records,
        "positions_created":    positions_created,
        "positions_updated":    positions_updated,
        "positions_closed":     positions_closed,
        "message":              f"Applied {txn_records} transaction(s) successfully.",
    }
