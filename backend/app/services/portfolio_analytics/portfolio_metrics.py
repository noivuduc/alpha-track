"""
portfolio_metrics — canonical, single source of truth for all portfolio metrics.

ARCHITECTURE RULE
─────────────────
Both the analytics engine (dashboard) and the simulation service MUST import
metric functions from THIS module, NOT from risk_metrics directly.

That rule ensures that if the formula or risk-free rate ever changes, it
changes in exactly one place and both systems stay consistent.

Metric definitions
──────────────────
Sharpe  = (ann_return − RF_ANNUAL) / ann_volatility
        = (mean_daily − RF_DAILY)  / std_daily  × √252     ← equivalent form

ann_return     = geometric mean daily return × 252 (via np.prod for compounding)
ann_volatility = std(daily_returns, ddof=1) × √252
RF_ANNUAL      = 0.02  (2% p.a., see constants.py)
RF_DAILY       = RF_ANNUAL / 252

All functions are PURE — no I/O, no logging at call-time.
compute_snapshot() adds structured DEBUG logging for tracing discrepancies.
"""
from __future__ import annotations

import logging
import math

import numpy as np

# ── Re-export canonical implementations ───────────────────────────────────────
# Import once here; callers use: from app.services.portfolio_analytics.portfolio_metrics import ...
from .risk_metrics import (          # noqa: F401 — intentional re-export
    sharpe,
    sortino,
    beta,
    alpha,
    max_drawdown,
    value_at_risk,
    pearson_corr,
    calmar,
    win_rate,
    win_rate_excess,
    information_ratio,
    compute_downside_risk,
)
from .return_series import (         # noqa: F401 — intentional re-export
    annualized_return,
    annualized_vol,
    cumulative_series,
    daily_returns,
    compute_twr_returns,
    build_cash_flows,
)
from .portfolio_reconstruction import (  # noqa: F401 — intentional re-export
    align_series,
    build_price_lookup,
    reconstruct_portfolio_value,
)
from .constants import RF_ANNUAL, RF_DAILY, TRADING_YR  # noqa: F401

log = logging.getLogger(__name__)


# ── Canonical scalar helpers (thin wrappers that expose the exact formula) ────

def compute_return(returns: list[float]) -> float:
    """Geometric annualized return (%)."""
    return annualized_return(returns)


def compute_volatility(returns: list[float]) -> float:
    """Annualized standard deviation of daily returns (%)."""
    return annualized_vol(returns)


def compute_sharpe(returns: list[float], rf: float = RF_ANNUAL) -> float:
    """
    Annualized Sharpe ratio.

    Formula: (ann_return − rf) / ann_vol
    Implemented as: (mean_daily − RF_DAILY) / std_daily × √252

    Both forms are mathematically identical.  We use the daily form because
    it avoids a second pass over the data.  The two-form equivalence is:

        (mean_daily × 252 − rf) / (std_daily × √252)
      = (mean_daily − rf/252)   / std_daily × √252
    """
    if rf != RF_ANNUAL:
        # Non-default rf: compute directly using the daily form
        if len(returns) < 20:
            return 0.0
        r   = np.asarray(returns, dtype=np.float64)
        std = float(r.std(ddof=1))
        if std == 0.0:
            return 0.0
        rf_daily = rf / TRADING_YR
        return round(float((r.mean() - rf_daily) / std) * math.sqrt(TRADING_YR), 4)
    return sharpe(returns)


def compute_sortino(returns: list[float]) -> float:
    return sortino(returns)


def compute_beta(port_returns: list[float], mkt_returns: list[float]) -> float:
    return beta(port_returns, mkt_returns)


def compute_max_drawdown(closes: list[float]) -> float:
    return max_drawdown(closes)


# ── Structured snapshot (used by BOTH dashboard and simulator) ────────────────

def compute_snapshot(
    port_returns: list[float],
    port_values:  list[float],
    spy_returns:  list[float],
    label:        str = "",
    *,
    port_for_spy: list[float] | None = None,
) -> dict:
    """
    Compute all standard risk/return metrics from a daily return series.

    This is the ONLY function that should construct the SimulateSnapshot /
    risk_metrics dict.  Both compute_engine() and simulate_add_position()
    call this so they are provably using the same formula and the same RF.

    Args:
        port_returns : daily return series (TWR or weight-based — must be
                       consistent within a before/after comparison)
        port_values  : cumulative value series (for max-drawdown)
        spy_returns  : SPY daily returns for beta/alpha (pass [] to skip)
        label        : "dashboard" | "sim_before" | "sim_after" — used in
                       debug logs so you can compare values across calls

    Debug logging (level=DEBUG):
        Sharpe debug [label]:
          n=252 mean_daily=0.000317 ann_return=7.88% std_daily=0.008412
          ann_vol=13.35% rf_daily=0.000079 rf_annual=2.00%
          → sharpe=0.4399
    """
    empty = {
        "sharpe": 0.0, "sortino": 0.0, "beta": 1.0, "alpha_pct": 0.0,
        "max_drawdown_pct": 0.0, "volatility_pct": 0.0,
        "annualized_return_pct": 0.0, "var_95_pct": 0.0,
        "win_rate_pct": 0.0, "win_rate_excess_pct": 0.0,
    }
    if len(port_returns) < 5:
        log.debug("compute_snapshot [%s]: insufficient data (n=%d)", label, len(port_returns))
        return empty

    r         = np.asarray(port_returns, dtype=np.float64)
    mean_d    = float(r.mean())
    std_d     = float(r.std(ddof=1))
    ann_ret   = annualized_return(port_returns)
    ann_v     = annualized_vol(port_returns)
    s         = sharpe(port_returns)

    log.debug(
        "Sharpe debug [%s]: n=%d mean_daily=%.6f ann_return=%.4f%% "
        "std_daily=%.6f ann_vol=%.4f%% rf_daily=%.6f rf_annual=%.2f%% "
        "→ sharpe=%.4f",
        label or "?",
        len(port_returns),
        mean_d,
        ann_ret,
        std_d,
        ann_v,
        RF_DAILY,
        RF_ANNUAL * 100,
        s,
    )

    _pr = port_for_spy if port_for_spy is not None else port_returns
    b = beta(_pr, spy_returns)  if spy_returns else 1.0
    a = alpha(_pr, spy_returns, b) if spy_returns else 0.0

    return {
        "sharpe":                round(s,                                    4),
        "sortino":               round(sortino(port_returns),                4),
        "beta":                  round(b,                                    4),
        "alpha_pct":             round(a,                                    4),
        "max_drawdown_pct":      round(max_drawdown(port_values),            4),
        "volatility_pct":        round(ann_v,                                4),
        "annualized_return_pct": round(ann_ret,                              4),
        "var_95_pct":            round(value_at_risk(port_returns),          4),
        "win_rate_pct":          round(win_rate(port_returns),               4),
        "win_rate_excess_pct":   round(win_rate_excess(port_returns),        4),
    }
