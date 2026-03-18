"""
Portfolio Analytics Engine — orchestration layer.

compute_engine() is the single entry point.  It calls the specialised
sub-modules in sequence and assembles the final analytics dict that maps
1-to-1 onto the PortfolioAnalytics Pydantic schema.

Zero I/O: accepts plain Python dicts/lists and returns plain Python dicts.

CONSISTENCY NOTE: All metric functions are imported from portfolio_metrics
(the single source of truth).  The simulation service imports from the same
module, guaranteeing both systems compute identical Sharpe / Sortino / beta
values when given the same return series.
"""
from __future__ import annotations

import logging

import numpy as np

log = logging.getLogger(__name__)

from .portfolio_reconstruction import reconstruct_portfolio_value
from .return_series import (
    daily_returns, cumulative_series,
    build_cash_flows, compute_twr_returns,
)
from .math_utils import pct_change
from .constants import RF_ANNUAL
# ── Import ALL metrics from the canonical SoT module ──────────────────────────
from .portfolio_metrics import (
    beta, alpha, sharpe, sortino, max_drawdown, calmar,
    win_rate, win_rate_excess, information_ratio, value_at_risk, pearson_corr,
    compute_downside_risk,
    compute_snapshot,                            # used for debug logging
    annualized_return, annualized_vol,
)
from .rolling_metrics import (
    compute_rolling_returns,
    compute_rolling_risk_metrics,
    compute_rolling_correlation,
    compute_volatility_regime,
    compute_rolling_max_drawdown,
)
from .contribution import compute_contribution
from .positions   import compute_position_analytics, compute_position_summary  # noqa: F401 (re-exported)
from .performance import (
    performance_series, drawdown_series,
    compute_growth_of_100, compute_return_distribution,
    compute_derived_metrics, compute_daily_return_heatmap,
    compute_period_extremes,
    monthly_returns_twr, weekly_returns_twr,
)
from .exposure import (
    compute_exposure_metrics,
    compute_capture_ratios,
    compute_turnover_pct,
)

# ── Empty-result sentinels ─────────────────────────────────────────────────────

_EMPTY_RISK: dict = {
    "sharpe": 0.0, "sortino": 0.0, "beta": 1.0, "alpha_pct": 0.0,
    "max_drawdown_pct": 0.0, "volatility_pct": 0.0, "calmar": 0.0,
    "win_rate_pct": 0.0, "win_rate_excess_pct": 0.0,
    "annualized_return_pct": 0.0,
    "information_ratio": 0.0, "var_95_pct": 0.0, "trading_days": 0,
}
_EMPTY_ROLLING: dict = {
    "return_1w": None, "return_1m": None,
    "return_3m": None, "return_ytd": None, "return_1y": None,
}
_EMPTY_RESULT: dict = {
    "status":                 "insufficient_data",
    "meta":                   {"rf_rate": RF_ANNUAL, "method": "TWR", "period": "1y", "version": "v2"},
    "data_quality":           0.0,
    "risk_metrics":           _EMPTY_RISK,
    "performance":            [],
    "drawdown":               [],
    "monthly_returns":        [],
    "derived_metrics":        None,
    "portfolio_value_series": [],
    "daily_returns":          [],
    "rolling_returns":        _EMPTY_ROLLING,
    "contribution":           [],
    "position_analytics":     [],
    "performance_metrics":    None,
    # Advanced fields
    "rolling_metrics":         {"63d": [], "126d": [], "252d": []},
    "rolling_correlation_spy": [],
    "volatility_regime":       [],
    "rolling_drawdown_6m":     [],
    "growth_of_100":           [],
    "daily_heatmap":           [],
    "weekly_returns":          [],
    "period_extremes":         None,
}


# ── Main entry point ───────────────────────────────────────────────────────────

def compute_engine(
    price_lookup: dict[str, dict[str, float]],
    lots:         list[dict],
    dates:        list[str],
    benchmark:    str = "SPY",
) -> dict:
    """
    Comprehensive portfolio analytics engine.

    Reconstructs the TRUE daily portfolio value from position lots (honouring
    opened_at), then computes institutional-grade performance metrics, rolling
    returns, per-position contribution, and position-level analytics.

    Args:
        price_lookup: {ticker: {YYYY-MM-DD: close}}  — output of build_price_lookup()
        lots: [{"ticker": str, "shares": float, "cost_basis": float,
                "opened_at_date": str (YYYY-MM-DD)}]
        dates: full market calendar from align_series()
        benchmark: primary benchmark ticker (SPY by default)

    Returns a dict compatible with PortfolioAnalytics schema.
    """
    # ── Step 1: Reconstruct actual portfolio value series ──────────────────────
    active_dates, portfolio_values = reconstruct_portfolio_value(
        price_lookup, lots, dates
    )
    if not portfolio_values:
        return dict(_EMPTY_RESULT)

    # Guard: all-zero portfolio (no price data resolved)
    pv_arr = np.asarray(portfolio_values, dtype=np.float64)
    if np.all(pv_arr == 0.0):
        log.warning("compute_engine: all portfolio values are zero — no price data")
        return dict(_EMPTY_RESULT)

    # ── Step 2: Build cash flows and compute TWR daily returns ────────────────
    # External cash flows (new lot purchases) are stripped before computing each
    # day's return so that capital injections do not inflate performance metrics.
    #
    #   R_t = (V_t - CF_t) / V_{t-1} - 1
    #
    # cash_flows maps each active trading date to the total capital injected on
    # that day (sum of shares × cost_basis for all lots opened on that date).
    cash_flows   = build_cash_flows(lots, active_dates)
    port_returns = compute_twr_returns(portfolio_values, active_dates, cash_flows)

    # Guard: drop NaN returns (can arise from data gaps) and require ≥ 2 points
    _pr = np.asarray(port_returns, dtype=np.float64)
    _pr = _pr[~np.isnan(_pr)]
    port_returns = _pr.tolist()
    if len(port_returns) < 2:
        log.warning("compute_engine: insufficient clean returns after NaN removal (n=%d)", len(port_returns))
        return dict(_EMPTY_RESULT)

    # Generate the cash-flow-neutral cumulative wealth index immediately
    port_cumul   = cumulative_series(port_returns)

    # ── Step 3: Benchmark price series aligned to active_dates (forward-fill) ─
    def _bench_ff(ticker: str) -> list[float]:
        d2c    = price_lookup.get(ticker, {})
        last_p: float | None = None
        out: list[float] = []
        for d in active_dates:
            p = d2c.get(d)
            if p and p > 0:
                last_p = p
            if last_p:
                out.append(last_p)
        return out

    bm_closes  = _bench_ff(benchmark)
    spy_closes = _bench_ff("SPY") if benchmark.upper() != "SPY" else bm_closes
    qqq_closes = _bench_ff("QQQ") if benchmark.upper() != "QQQ" else bm_closes

    bm_returns  = daily_returns(bm_closes)  if len(bm_closes)  >= 2 else []
    spy_returns = daily_returns(spy_closes) if len(spy_closes) >= 2 else []
    qqq_returns = daily_returns(qqq_closes) if len(qqq_closes) >= 2 else []

    # ── Step 4: Risk metrics ───────────────────────────────────────────────────
    b   = beta(port_returns, bm_returns)             if bm_returns else 1.0
    a   = alpha(port_returns, bm_returns, b)         if bm_returns else 0.0
    ir  = information_ratio(port_returns, bm_returns) if bm_returns else 0.0
    var = value_at_risk(port_returns)

    # annualized_return / annualized_vol imported at module level from portfolio_metrics
    risk_metrics: dict = {
        "sharpe":                sharpe(port_returns),
        "sortino":               sortino(port_returns),
        "beta":                  b,
        "alpha_pct":             a,
        "max_drawdown_pct":      max_drawdown(port_cumul),
        "volatility_pct":        annualized_vol(port_returns),
        "calmar":                calmar(port_returns, port_cumul),
        "win_rate_pct":          win_rate(port_returns),
        "win_rate_excess_pct":   win_rate_excess(port_returns),
        "annualized_return_pct": annualized_return(port_returns),
        "information_ratio":     ir,
        "var_95_pct":            var,
        "trading_days":          len(port_returns),
    }
    risk_metrics.update(compute_downside_risk(port_returns, port_cumul))

    # ── Step 5: Summary performance metrics ───────────────────────────────────
    v0, vn = port_cumul[0], port_cumul[-1]
    perf_metrics: dict = {
        "cumulative_return": round((pct_change(vn, v0) or 0.0), 4),
        "annualized_return": risk_metrics["annualized_return_pct"],
        "volatility":        risk_metrics["volatility_pct"],
        "sharpe_ratio":      risk_metrics["sharpe"],
        "max_drawdown":      risk_metrics["max_drawdown_pct"],
        "beta":              b,
        "alpha":             a,
        # Populated after correlation is computed (step 6)
        "correlation_spy":   None,
        "correlation_qqq":   None,
    }

    # ── Step 6: Correlation (portfolio vs SPY/QQQ) ────────────────────────────
    corr_spy = pearson_corr(port_returns, spy_returns) if spy_returns else None
    corr_qqq = pearson_corr(port_returns, qqq_returns) if qqq_returns else None

    # ── Step 7: Cumulative series for benchmark comparison chart ──────────────
    bm_cumul   = cumulative_series(bm_returns)  if bm_returns  else []
    spy_cumul  = cumulative_series(spy_returns) if spy_returns else (bm_cumul if benchmark.upper() == "SPY" else [])
    qqq_cumul  = cumulative_series(qqq_returns) if qqq_returns else (bm_cumul if benchmark.upper() == "QQQ" else [])

    bench_cumul: dict[str, list[float]] = {}
    if spy_cumul: bench_cumul["SPY"] = spy_cumul
    if qqq_cumul: bench_cumul["QQQ"] = qqq_cumul

    # ── Step 8: Time-series chart outputs ─────────────────────────────────────
    # Drawdown is computed on the TWR cumulative index (port_cumul) rather than
    # raw NAV so that capital injections don't create artificial new peaks.
    # port_cumul starts at 100 and grows purely by market performance.
    dd_data    = drawdown_series(active_dates, port_cumul)
    perf_chart = performance_series(active_dates, port_cumul, bench_cumul)
    # Monthly returns compound daily TWR returns — cash-flow-neutral aggregation.
    mo_ret     = monthly_returns_twr(active_dates[1:], port_returns)

    # ── Step 9: Derived metrics ────────────────────────────────────────────────
    derived = compute_derived_metrics(
        dates         = active_dates,
        port_values   = port_cumul,
        port_returns  = port_returns,
        spy_values    = spy_cumul,
        qqq_values    = qqq_cumul,
        drawdown_data = dd_data,
    )

    # ── Step 10: Rolling returns ───────────────────────────────────────────────
    # Use the TWR cumulative index for look-back return windows so that
    # historical cash flows don't distort the 1W/1M/3M/YTD/1Y figures.
    rolling = compute_rolling_returns(port_cumul, active_dates)

    # ── Step 11: Contribution analytics ───────────────────────────────────────
    contribution = compute_contribution(lots, price_lookup, active_dates, portfolio_values)

    # ── Step 12: Position-level analytics ─────────────────────────────────────
    pos_analytics = compute_position_analytics(lots, price_lookup, active_dates, portfolio_values)

    # ── Step 13: Rolling risk metrics (63 / 126 / 252-day windows) ────────────
    rolling_risk = compute_rolling_risk_metrics(port_returns, spy_returns, active_dates)

    # ── Steps 14–24: Advanced analytics (each wrapped to isolate failures) ──────

    def _safe(label: str, fn, *args, default=None, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            log.error("engine [metric_failed] %s: %s", label, exc, exc_info=True)
            return default if default is not None else {}

    rolling_corr_spy = _safe(
        "rolling_corr_spy",
        compute_rolling_correlation, port_returns, spy_returns, active_dates,
        default=[],
    ) if spy_returns else []

    vol_regime = _safe(
        "vol_regime",
        compute_volatility_regime, port_returns, active_dates,
        default=[],
    )

    exposure = _safe(
        "exposure",
        compute_exposure_metrics, lots, price_lookup, active_dates, portfolio_values,
    )

    rolling_mdd_6m = _safe(
        "rolling_mdd_6m",
        compute_rolling_max_drawdown, port_cumul, active_dates,
        default=[], window=126,
    )

    captures = _safe(
        "captures",
        compute_capture_ratios, port_returns, bm_returns,
    ) if bm_returns else {}

    turnover = _safe(
        "turnover",
        compute_turnover_pct, lots, price_lookup, active_dates,
        default=0.0,
    )

    growth100 = _safe(
        "growth100",
        compute_growth_of_100, active_dates, port_cumul, spy_closes, qqq_closes,
        default=[],
    )

    ret_dist = _safe(
        "ret_dist",
        compute_return_distribution, port_returns,
        default={"skewness": None, "kurtosis": None},
    )

    daily_heatmap = _safe(
        "daily_heatmap",
        compute_daily_return_heatmap, active_dates[1:], port_returns,
        default=[],
    )

    weekly_returns = _safe(
        "weekly_returns",
        weekly_returns_twr, active_dates[1:], port_returns,
        default=[],
    )

    period_extremes = _safe(
        "period_extremes",
        compute_period_extremes, daily_heatmap, weekly_returns, mo_ret,
    )

    # ── Populate all performance_metrics additions ─────────────────────────────
    perf_metrics["correlation_spy"] = corr_spy
    perf_metrics["correlation_qqq"] = corr_qqq
    perf_metrics.update(exposure)
    perf_metrics.update(captures)
    perf_metrics["estimated_turnover_pct"] = turnover
    perf_metrics.update(ret_dist)

    # ── Data quality score (0–1) ───────────────────────────────────────────────
    # Penalizes short history, high NaN ratio, and missing benchmark data.
    _all_returns = compute_twr_returns(portfolio_values, active_dates, cash_flows)
    _total        = len(_all_returns)
    _nan_count    = sum(1 for r in _all_returns if r != r)   # NaN check via reflexivity
    _nan_ratio    = _nan_count / _total if _total else 1.0
    data_quality  = 1.0
    if len(port_returns) < 60:   data_quality -= 0.2   # < 3 months of history
    if len(port_returns) < 20:   data_quality -= 0.3   # < 1 month — very unreliable
    if _nan_ratio > 0.10:        data_quality -= 0.2   # > 10 % NaN days
    if not spy_returns:          data_quality -= 0.1   # no benchmark for beta/alpha
    data_quality = round(max(0.0, data_quality), 2)

    return {
        "status": "ok",
        # ─── Metadata: method + constants used for every metric ──────────────
        "meta": {
            "rf_rate":  RF_ANNUAL,
            "method":   "TWR",
            "period":   "1y",
            "version":  "v2",
        },
        "data_quality": data_quality,
        # ─── Existing fields (backward-compatible) ──────────────────────────
        "risk_metrics":    risk_metrics,
        "performance":     perf_chart,
        "drawdown":        dd_data,
        "monthly_returns": mo_ret,
        "derived_metrics": derived,
        # ─── Comprehensive analytics fields ─────────────────────────────────
        "portfolio_value_series": [
            {"date": d, "value": v}
            for d, v in zip(active_dates, portfolio_values)
        ],
        "daily_returns":      port_returns,
        "rolling_returns":    rolling,
        "contribution":       contribution,
        "position_analytics": pos_analytics,
        "performance_metrics": perf_metrics,
        # ─── Advanced institutional analytics fields ─────────────────────────
        "rolling_metrics":         rolling_risk,
        "rolling_correlation_spy": rolling_corr_spy,
        "volatility_regime":       vol_regime,
        "rolling_drawdown_6m":     rolling_mdd_6m,
        "growth_of_100":           growth100,
        "daily_heatmap":           daily_heatmap,
        "weekly_returns":          weekly_returns,
        "period_extremes":         period_extremes,
    }


# ── Legacy wrappers (kept for any code still calling the old API) ──────────────

def build_portfolio_returns(
    aligned: dict[str, list[float]],
    weights: dict[str, float],
    n_days: int,
) -> list[float]:
    """
    Legacy weight-based portfolio return approximation.
    Prefer compute_engine() for accurate lot-aware reconstruction.
    """
    total_w = sum(weights.values())
    if total_w == 0:
        return [0.0] * max(n_days - 1, 0)

    port = [0.0] * max(n_days - 1, 0)
    for ticker, wt in weights.items():
        closes = aligned.get(ticker, [])
        frac   = wt / total_w
        for i in range(min(len(closes) - 1, n_days - 1)):
            prev = closes[i]
            if prev and prev != 0:
                port[i] += frac * (closes[i + 1] - prev) / prev
    return port


def compute_all(
    aligned:   dict[str, list[float]],
    weights:   dict[str, float],
    dates:     list[str],
    benchmark: str = "SPY",
) -> dict:
    """
    Legacy wrapper.  Uses fixed-weight approximation.
    New code should call compute_engine() instead.
    """
    n = len(dates)

    port_returns = build_portfolio_returns(aligned, weights, n)
    port_values  = cumulative_series(port_returns)
    port_dates   = dates[:len(port_values)]

    bm_returns  = daily_returns(aligned.get(benchmark, []))
    bm_values   = cumulative_series(bm_returns) if bm_returns else []
    qqq_returns = daily_returns(aligned.get("QQQ", []))
    qqq_values  = cumulative_series(qqq_returns) if qqq_returns else []

    b   = beta(port_returns, bm_returns)         if bm_returns else 1.0
    a   = alpha(port_returns, bm_returns, b)     if bm_returns else 0.0
    ir  = information_ratio(port_returns, bm_returns) if bm_returns else 0.0
    var = value_at_risk(port_returns)

    risk = {
        "sharpe":                sharpe(port_returns),
        "sortino":               sortino(port_returns),
        "beta":                  b,
        "alpha_pct":             a,
        "max_drawdown_pct":      max_drawdown(port_values),
        "volatility_pct":        annualized_vol(port_returns),
        "calmar":                calmar(port_returns, port_values),
        "win_rate_pct":          win_rate(port_returns),
        "annualized_return_pct": annualized_return(port_returns),
        "information_ratio":     ir,
        "var_95_pct":            var,
        "trading_days":          len(port_returns),
    }

    bench_vals: dict[str, list[float]] = {}
    if bm_values:  bench_vals[benchmark] = bm_values
    if qqq_values: bench_vals["QQQ"]     = qqq_values

    dd_data = drawdown_series(port_dates, port_values)

    spy_closes = aligned.get("SPY", [])
    spy_vals   = cumulative_series(daily_returns(spy_closes)) if len(spy_closes) >= 2 else []

    return {
        "meta": {"rf_rate": RF_ANNUAL, "method": "simple", "period": "1y", "version": "v2"},
        "risk_metrics":    risk,
        "performance":     performance_series(port_dates, port_values, bench_vals),
        "drawdown":        dd_data,
        "monthly_returns": monthly_returns_twr(port_dates[1:], port_returns),
        "derived_metrics": compute_derived_metrics(
            dates         = port_dates,
            port_values   = port_values,
            port_returns  = port_returns,
            spy_values    = spy_vals,
            qqq_values    = qqq_values,
            drawdown_data = dd_data,
        ),
    }
