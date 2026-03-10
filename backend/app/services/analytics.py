"""
Portfolio Analytics Engine — pure computation, zero I/O.

All functions accept plain Python lists/dicts and return results.
Database and HTTP calls live in the router; this module only does math.

Risk-free rate: 2 % annual  (per spec; was 5.25 %)
Annualisation factor: 252 trading days/year
"""
from __future__ import annotations

import math
import statistics as _stats
from datetime import datetime

RF_ANNUAL  = 0.02
RF_DAILY   = RF_ANNUAL / 252
TRADING_YR = 252
MONTHS     = ['Jan','Feb','Mar','Apr','May','Jun',
              'Jul','Aug','Sep','Oct','Nov','Dec']


# ─── Basic series math ────────────────────────────────────────────────────────

def daily_returns(closes: list[float]) -> list[float]:
    """Arithmetic (simple) daily returns."""
    if len(closes) < 2:
        return []
    return [(closes[i] - closes[i-1]) / closes[i-1]
            for i in range(1, len(closes))
            if closes[i-1] != 0]


def cumulative_series(returns: list[float], base: float = 100.0) -> list[float]:
    """Wealth index starting at `base`, one value per return period + initial."""
    out = [base]
    v = base
    for r in returns:
        v *= (1 + r)
        out.append(round(v, 6))
    return out


def annualized_return(returns: list[float]) -> float:
    """Geometric annualized return (%)."""
    if not returns:
        return 0.0
    total = 1.0
    for r in returns:
        total *= (1 + r)
    return round((total ** (TRADING_YR / len(returns)) - 1) * 100, 4)


def annualized_vol(returns: list[float]) -> float:
    """Annualized standard deviation of daily returns (%)."""
    if len(returns) < 2:
        return 0.0
    return round(_stats.stdev(returns) * math.sqrt(TRADING_YR) * 100, 4)


# ─── Risk / quality metrics ───────────────────────────────────────────────────

def _mean(arr: list[float]) -> float:
    return sum(arr) / len(arr) if arr else 0.0


def _std(arr: list[float]) -> float:
    return _stats.stdev(arr) if len(arr) >= 2 else 0.0


def sharpe(returns: list[float]) -> float:
    """Annualized Sharpe ratio (RF = 2 % annual)."""
    if len(returns) < 20:
        return 0.0
    m = _mean(returns) - RF_DAILY
    s = _std(returns)
    return round((m / s) * math.sqrt(TRADING_YR), 4) if s else 0.0


def sortino(returns: list[float]) -> float:
    """Annualized Sortino ratio (penalises downside only)."""
    if len(returns) < 20:
        return 0.0
    m = _mean(returns) - RF_DAILY
    dd_sq = sum(min(r - RF_DAILY, 0) ** 2 for r in returns) / len(returns)
    dd = math.sqrt(dd_sq)
    return round((m / dd) * math.sqrt(TRADING_YR), 4) if dd else 0.0


def max_drawdown(closes: list[float]) -> float:
    """Maximum peak-to-trough drawdown as a negative percentage."""
    if len(closes) < 2:
        return 0.0
    peak = closes[0]
    mdd  = 0.0
    for v in closes:
        if v > peak:
            peak = v
        dd = (v - peak) / peak if peak else 0.0
        if dd < mdd:
            mdd = dd
    return round(mdd * 100, 4)


def beta(port_returns: list[float], mkt_returns: list[float]) -> float:
    """Beta of portfolio vs market (sample covariance / sample variance)."""
    n = min(len(port_returns), len(mkt_returns))
    if n < 20:
        return 1.0
    pr = port_returns[:n]
    mr = mkt_returns[:n]
    mp, mm = _mean(pr), _mean(mr)
    cov = sum((pr[i] - mp) * (mr[i] - mm) for i in range(n)) / (n - 1)
    var = sum((mr[i] - mm) ** 2 for i in range(n)) / (n - 1)
    return round(cov / var, 4) if var > 0 else 1.0


def alpha(port_returns: list[float], mkt_returns: list[float], b: float) -> float:
    """Jensen's alpha: compute daily excess alpha then annualize."""
    n = min(len(port_returns), len(mkt_returns))
    if n < 20:
        return 0.0
    mp = _mean(port_returns[:n])
    mm = _mean(mkt_returns[:n])
    alpha_daily = mp - (RF_DAILY + b * (mm - RF_DAILY))
    return round(alpha_daily * TRADING_YR * 100, 4)


def calmar(returns: list[float], closes: list[float]) -> float:
    """Calmar ratio = annualized return / |max drawdown|."""
    mdd = abs(max_drawdown(closes))
    ann = annualized_return(returns)
    return round(ann / mdd, 4) if mdd else 0.0


def _pct_change(a: float | None, b: float | None) -> float | None:
    """Return (a/b − 1) * 100, or None when either value is missing/zero."""
    if a is None or b is None or b == 0:
        return None
    return round((a / b - 1) * 100, 4)


def win_rate(returns: list[float]) -> float:
    """Percentage of days where return exceeds the daily risk-free rate."""
    if not returns:
        return 0.0
    return round(sum(1 for r in returns if r > RF_DAILY) / len(returns) * 100, 2)


def information_ratio(port_returns: list[float], bench_returns: list[float]) -> float:
    """Annualized information ratio vs benchmark."""
    n = min(len(port_returns), len(bench_returns))
    if n < 20:
        return 0.0
    active = [port_returns[i] - bench_returns[i] for i in range(n)]
    m = _mean(active)
    s = _std(active)
    return round((m / s) * math.sqrt(TRADING_YR), 4) if s else 0.0


def value_at_risk(returns: list[float], confidence: float = 0.95) -> float:
    """Historical VaR at `confidence` level, expressed as positive percentage."""
    if len(returns) < 20:
        return 0.0
    sorted_r = sorted(returns)
    idx = int((1 - confidence) * len(sorted_r))
    return round(abs(sorted_r[idx]) * 100, 4)


def pearson_corr(x: list[float], y: list[float]) -> float | None:
    """Pearson correlation coefficient between two return series."""
    n = min(len(x), len(y))
    if n < 20:
        return None
    xs, ys = x[:n], y[:n]
    mx, my = _mean(xs), _mean(ys)
    cov = sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / (n - 1)
    sx, sy = _std(xs), _std(ys)
    return round(cov / (sx * sy), 4) if sx and sy else None


# ─── Series construction ──────────────────────────────────────────────────────

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
                closes.append(last)   # forward-fill; skip dates before first valid price
        aligned[ticker] = closes

    return ref_dates, aligned


# ─── Price lookup (date-keyed) ────────────────────────────────────────────────

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


# ─── Portfolio reconstruction (Step 1) ───────────────────────────────────────

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
        (active_dates, portfolio_values)  — subset of dates starting from portfolio inception.
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


# ─── Drawdown series ──────────────────────────────────────────────────────────

def drawdown_series(dates: list[str], closes: list[float]) -> list[dict]:
    """
    Running peak-to-trough drawdown at each date.

    Returns list of {"date": str, "drawdown": float (negative %)}.
    """
    if not closes:
        return []
    peak = closes[0]
    out  = []
    for i, v in enumerate(closes):
        if v > peak:
            peak = v
        dd = (v - peak) / peak * 100 if peak else 0.0
        out.append({
            "date":     dates[i] if i < len(dates) else "",
            "drawdown": round(dd, 4),
        })
    return out


# ─── Monthly returns heatmap ──────────────────────────────────────────────────

def monthly_returns(dates: list[str], values: list[float]) -> list[dict]:
    """
    Aggregate a daily value series into monthly returns.

    Returns list of {"year", "month", "label", "value" (%)}.
    """
    if len(dates) < 2 or len(dates) != len(values):
        return []

    buckets: dict[str, tuple[float, float]] = {}
    for d, v in zip(dates, values):
        key = d[:7]
        if key not in buckets:
            buckets[key] = (v, v)
        buckets[key] = (buckets[key][0], v)

    result = []
    for key in sorted(buckets):
        start, end = buckets[key]
        y, m = int(key[:4]), int(key[5:7])
        ret  = (end - start) / start * 100 if start else 0.0
        result.append({
            "year":  y,
            "month": m,
            "label": MONTHS[m - 1],
            "value": round(ret, 4),
        })
    return result


# ─── Performance comparison series ───────────────────────────────────────────

def performance_series(
    dates: list[str],
    portfolio_values: list[float],
    benchmark_values: dict[str, list[float]],
) -> list[dict]:
    """
    Normalise portfolio and benchmarks to 100 at t=0 for apples-to-apples comparison.

    Args:
        benchmark_values: {"SPY": [100, 101, ...], "QQQ": [...]}

    Returns list of {"date", "portfolio", "spy"?, "qqq"?}.
    """
    if not dates or not portfolio_values:
        return []

    base_p  = portfolio_values[0] if portfolio_values[0] else 1.0
    b_bases = {k: (v[0] if v and v[0] else 1.0) for k, v in benchmark_values.items()}

    # Map benchmark keys to canonical field names (spy, qqq, or benchmark)
    _key_map = {"SPY": "spy", "QQQ": "qqq"}

    out = []
    for i, d in enumerate(dates):
        pt: dict = {"date": d}
        if i < len(portfolio_values):
            pt["portfolio"] = round(portfolio_values[i] / base_p * 100, 2)
        for k, vals in benchmark_values.items():
            if i < len(vals) and vals[i]:
                field = _key_map.get(k.upper(), "benchmark")
                pt[field] = round(vals[i] / b_bases[k] * 100, 2)
        out.append(pt)
    return out


# ─── Rolling returns (Step 11) ────────────────────────────────────────────────

def compute_rolling_returns(
    values: list[float],
    dates:  list[str],
) -> dict:
    """
    Compute rolling period returns from a daily portfolio value series.

    Returns {"return_1w", "return_1m", "return_3m", "return_ytd", "return_1y"}
    as percentage floats (or None when insufficient history).
    """
    empty: dict[str, float | None] = {
        "return_1w": None, "return_1m": None,
        "return_3m": None, "return_ytd": None, "return_1y": None,
    }
    if len(values) < 2:
        return empty

    last = values[-1]

    def _lb(n: int) -> float | None:
        if len(values) < n + 1:
            return None
        base = values[-(n + 1)]
        return round((last / base - 1) * 100, 4) if base > 0 else None

    ytd_pct: float | None = None
    if dates:
        cur_year = dates[-1][:4]
        for i, d in enumerate(dates):
            if d[:4] == cur_year and i < len(values):
                base = values[i]
                ytd_pct = round((last / base - 1) * 100, 4) if base > 0 else None
                break

    return {
        "return_1w":  _lb(5),
        "return_1m":  _lb(21),
        "return_3m":  _lb(63),
        "return_ytd": ytd_pct,
        "return_1y":  _lb(252),
    }


# ─── Contribution analytics (Step 10) ────────────────────────────────────────

def compute_contribution(
    lots:             list[dict],
    price_lookup:     dict[str, dict[str, float]],
    active_dates:     list[str],
    portfolio_values: list[float],
) -> list[dict]:
    """
    Per-ticker contribution to portfolio return.

    contribution_pct  = (ticker_weight) × (ticker_period_return %)
    pnl_contribution  = ticker_current_value − ticker_total_cost

    Returns a list sorted by pnl_contribution descending.
    """
    if not portfolio_values or not active_dates:
        return []

    portfolio_initial_value = portfolio_values[0]

    # Build latest forward-filled price for each portfolio ticker
    portfolio_tickers = {lot["ticker"] for lot in lots}
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
        contrib_pct = (pnl_contribution / portfolio_initial_value * 100
                       if portfolio_initial_value > 0 else 0.0)
        rows.append({
            "ticker":           ticker,
            "contribution_pct": round(contrib_pct, 4),
            "pnl_contribution": round(pnl_contribution, 2),
        })

    return sorted(rows, key=lambda x: x["pnl_contribution"], reverse=True)


# ─── Position-level analytics (Step 12) ──────────────────────────────────────

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

    total_value = portfolio_values[-1]
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
        d2c = price_lookup.get(ticker, {})
        closes = [d2c[d] for d in active_dates if d in d2c and d2c[d] > 0]
        if len(closes) >= 20:
            rets = daily_returns(closes)
            ticker_vols[ticker] = annualized_vol(rets) if rets else None
        else:
            ticker_vols[ticker] = None

    # Latest single-day return per ticker
    ticker_daily: dict[str, float | None] = {}
    for ticker in portfolio_tickers:
        d2c = price_lookup.get(ticker, {})
        dated = [(d, d2c[d]) for d in active_dates if d in d2c and d2c[d] > 0]
        if len(dated) >= 2:
            prev_p, curr_p = dated[-2][1], dated[-1][1]
            ticker_daily[ticker] = round((curr_p / prev_p - 1) * 100, 4) if prev_p > 0 else None
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


# ─── Advanced institutional analytics ────────────────────────────────────────

def compute_rolling_risk_metrics(
    port_returns: list[float],
    spy_returns:  list[float],
    active_dates: list[str],
    windows: tuple[int, ...] = (63, 126, 252),
) -> dict[str, list[dict]]:
    """
    Rolling Sharpe, annualized volatility, beta vs SPY, and Sortino
    for each window size.

    Returns {"63d": [...], "126d": [...], "252d": [...]}.
    Each point: {"date", "rolling_sharpe", "rolling_volatility",
                 "rolling_beta", "rolling_sortino"}.
    Only points with a full window of data are emitted.
    """
    n_ret = len(port_returns)
    n_spy = len(spy_returns)
    result: dict[str, list[dict]] = {}

    for W in windows:
        series: list[dict] = []
        for i in range(W - 1, n_ret):
            pr = port_returns[i - W + 1 : i + 1]
            # return[i] is the gain earned *on* active_dates[i+1]
            d = active_dates[min(i + 1, len(active_dates) - 1)]

            s        = _std(pr)
            m_excess = _mean(pr) - RF_DAILY

            r_vol     = round(s * math.sqrt(TRADING_YR) * 100, 2) if s else None
            r_sharpe  = round((m_excess / s) * math.sqrt(TRADING_YR), 4) if s else None

            dd_sq    = sum(min(r - RF_DAILY, 0) ** 2 for r in pr) / W
            dd_std   = math.sqrt(dd_sq)
            r_sortino = round((m_excess / dd_std) * math.sqrt(TRADING_YR), 4) if dd_std else None

            r_beta: float | None = None
            if n_spy >= i + 1:
                mr = spy_returns[i - W + 1 : i + 1]
                if len(mr) == W:
                    mm = _mean(mr)
                    mp = _mean(pr)
                    cov_ = sum((pr[j] - mp) * (mr[j] - mm) for j in range(W)) / (W - 1)
                    var_ = sum((mr[j] - mm) ** 2 for j in range(W)) / (W - 1)
                    r_beta = round(cov_ / var_, 4) if var_ > 0 else None

            series.append({
                "date":               d,
                "rolling_sharpe":     r_sharpe,
                "rolling_volatility": r_vol,
                "rolling_beta":       r_beta,
                "rolling_sortino":    r_sortino,
            })
        result[f"{W}d"] = series

    return result


def compute_rolling_correlation(
    port_returns:  list[float],
    bench_returns: list[float],
    active_dates:  list[str],
    window: int = 90,
) -> list[dict]:
    """Rolling Pearson correlation vs a benchmark. Each point: {"date", "value"}."""
    n = min(len(port_returns), len(bench_returns))
    result: list[dict] = []
    for i in range(window - 1, n):
        pr = port_returns[i - window + 1 : i + 1]
        br = bench_returns[i - window + 1 : i + 1]
        d  = active_dates[min(i + 1, len(active_dates) - 1)]

        mp, mb = _mean(pr), _mean(br)
        cov_   = sum((pr[j] - mp) * (br[j] - mb) for j in range(window)) / (window - 1)
        sp, sb = _std(pr), _std(br)
        corr   = round(cov_ / (sp * sb), 4) if (sp and sb) else None
        result.append({"date": d, "value": corr})
    return result


def compute_volatility_regime(
    port_returns: list[float],
    active_dates: list[str],
    window: int = 30,
) -> list[dict]:
    """
    Classify each date into a volatility regime.

    Regime boundaries (annualised vol):
        low    < 10 %
        normal 10 – 20 %
        high   > 20 %
    Each point: {"date", "volatility", "regime"}.
    """
    n = len(port_returns)
    result: list[dict] = []
    for i in range(window - 1, n):
        pr  = port_returns[i - window + 1 : i + 1]
        d   = active_dates[min(i + 1, len(active_dates) - 1)]
        vol = _std(pr) * math.sqrt(TRADING_YR) * 100
        regime = "low" if vol < 10.0 else ("high" if vol > 20.0 else "normal")
        result.append({"date": d, "volatility": round(vol, 2), "regime": regime})
    return result


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


def compute_downside_risk(
    returns: list[float],
    values:  list[float],
) -> dict:
    """
    Downside deviation (annualised %), Ulcer Index, and CVaR tail-loss at 95 %.

    These extend risk_metrics without modifying existing fields.
    """
    empty = {"downside_deviation": 0.0, "ulcer_index": 0.0, "tail_loss_95": 0.0}
    if len(returns) < 20:
        return empty

    # Downside deviation: semi-deviation below risk-free, annualised
    dd_sq = sum(min(r - RF_DAILY, 0) ** 2 for r in returns) / len(returns)
    ddn   = round(math.sqrt(dd_sq) * math.sqrt(TRADING_YR) * 100, 4)

    # Ulcer Index: RMS of running drawdown from portfolio value series
    if len(values) >= 2:
        peak = values[0]
        dd_pcts: list[float] = []
        for v in values:
            if v > peak:
                peak = v
            dd_pcts.append((v - peak) / peak * 100 if peak else 0.0)
        ulcer = round(math.sqrt(sum(x * x for x in dd_pcts) / len(dd_pcts)), 4)
    else:
        ulcer = 0.0

    # Tail-loss (CVaR 95 %): average of worst 5 % daily returns
    sorted_r  = sorted(returns)
    n5        = max(1, int(0.05 * len(sorted_r)))
    tail_loss = round(abs(_mean(sorted_r[:n5])) * 100, 4)

    return {
        "downside_deviation": ddn,
        "ulcer_index":        ulcer,
        "tail_loss_95":       tail_loss,
    }


def compute_rolling_max_drawdown(
    values: list[float],
    dates:  list[str],
    window: int = 126,
) -> list[dict]:
    """
    Rolling maximum drawdown over `window` trading days.

    Each point: {"date", "drawdown"} — drawdown is a negative %.
    Aligns to active_dates directly (not returns-offset).
    """
    n      = len(values)
    result: list[dict] = []
    for i in range(window - 1, n):
        wv   = values[i - window + 1 : i + 1]
        d    = dates[i] if i < len(dates) else ""
        peak = wv[0]
        mdd  = 0.0
        for v in wv:
            if v > peak:
                peak = v
            dd = (v - peak) / peak * 100 if peak else 0.0
            if dd < mdd:
                mdd = dd
        result.append({"date": d, "drawdown": round(mdd, 4)})
    return result


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

    m_up = _mean(up_m) if up_m else 0.0
    m_dn = _mean(dn_m) if dn_m else 0.0

    upside   = round(_mean(up_p) / m_up, 4) if (up_p and m_up != 0) else None
    downside = round(_mean(dn_p) / m_dn, 4) if (dn_p and m_dn != 0) else None
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

    w_start = _weights(0)
    w_end   = _weights(len(active_dates) - 1)
    tickers = set(w_start) | set(w_end)
    half_turn = sum(abs(w_end.get(t, 0.0) - w_start.get(t, 0.0)) for t in tickers) / 2

    ann_factor = TRADING_YR / len(active_dates)
    return round(half_turn * ann_factor * 100, 2)


def compute_growth_of_100(
    active_dates:     list[str],
    portfolio_values: list[float],
    spy_closes:       list[float],
    qqq_closes:       list[float],
) -> list[dict]:
    """
    Normalise portfolio and benchmark price series to 100 at inception.

    Each point: {"date", "portfolio", "spy"?, "qqq"?}.
    """
    if not active_dates or not portfolio_values:
        return []

    port_base = portfolio_values[0] or 1.0
    spy_base  = spy_closes[0]  if spy_closes  else None
    qqq_base  = qqq_closes[0]  if qqq_closes  else None

    result: list[dict] = []
    for i, d in enumerate(active_dates):
        if i >= len(portfolio_values):
            break
        pt: dict = {
            "date":      d,
            "portfolio": round(portfolio_values[i] / port_base * 100, 2),
        }
        if spy_base and i < len(spy_closes) and spy_closes[i]:
            pt["spy"] = round(spy_closes[i] / spy_base * 100, 2)
        if qqq_base and i < len(qqq_closes) and qqq_closes[i]:
            pt["qqq"] = round(qqq_closes[i] / qqq_base * 100, 2)
        result.append(pt)
    return result


def compute_return_distribution(returns: list[float]) -> dict:
    """
    Sample skewness and excess kurtosis of the daily return distribution.

    Returns {"skewness": float | None, "kurtosis": float | None}.
    Negative skewness → left tail; kurtosis > 0 → fat tails (leptokurtic).
    """
    if len(returns) < 4:
        return {"skewness": None, "kurtosis": None}
    n = len(returns)
    m = _mean(returns)
    s = _std(returns)
    if s == 0:
        return {"skewness": 0.0, "kurtosis": 0.0}
    skew = (sum((r - m) ** 3 for r in returns) / n) / (s ** 3)
    kurt = (sum((r - m) ** 4 for r in returns) / n) / (s ** 4) - 3.0
    return {"skewness": round(skew, 4), "kurtosis": round(kurt, 4)}


# ─── Position summary (legacy, used for best/worst performers display) ────────

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


# ─── Derived metrics ──────────────────────────────────────────────────────────

def compute_derived_metrics(
    dates:        list[str],
    port_values:  list[float],
    port_returns: list[float],
    spy_values:   list[float],
    qqq_values:   list[float],
    drawdown_data: list[dict],
) -> dict:
    """
    Additional analytics appended as 'derived_metrics' to the analytics response.
    All inputs are the intermediate series already computed by compute_engine().
    """
    n    = len(port_values)
    last = port_values[-1] if port_values else None

    def _lookback(k: int) -> float | None:
        if n < k + 1 or last is None:
            return None
        return _pct_change(last, port_values[-(k + 1)])

    ytd_pct: float | None = None
    if dates and port_values:
        cur_year = dates[-1][:4]
        ytd_idx  = next((i for i, d in enumerate(dates) if d[:4] == cur_year), None)
        if ytd_idx is not None and ytd_idx < n:
            ytd_pct = _pct_change(last, port_values[ytd_idx])

    perf_summary = {
        "1d_pct":  _lookback(1),
        "1w_pct":  _lookback(5),
        "1m_pct":  _lookback(21),
        "ytd_pct": ytd_pct,
        "1y_pct":  _pct_change(last, port_values[0]) if port_values else None,
    }

    port_ret = _pct_change(port_values[-1], port_values[0]) if len(port_values) >= 2 else None
    spy_ret  = _pct_change(spy_values[-1],  spy_values[0])  if len(spy_values)  >= 2 else None
    qqq_ret  = _pct_change(qqq_values[-1],  qqq_values[0])  if len(qqq_values)  >= 2 else None

    bench_comp = {
        "portfolio_return_pct": port_ret,
        "spy_return_pct":       spy_ret,
        "qqq_return_pct":       qqq_ret,
        "alpha_vs_spy_pct":     round(port_ret - spy_ret, 4) if port_ret is not None and spy_ret is not None else None,
        "alpha_vs_qqq_pct":     round(port_ret - qqq_ret, 4) if port_ret is not None and qqq_ret is not None else None,
    }

    best_day = worst_day = avg_day = median_day = None
    if port_returns:
        r_pct      = [r * 100 for r in port_returns]
        best_day   = round(max(r_pct), 4)
        worst_day  = round(min(r_pct), 4)
        avg_day    = round(sum(r_pct) / len(r_pct), 4)
        median_day = round(_stats.median(r_pct), 4)

    current_dd    = drawdown_data[-1]["drawdown"] if drawdown_data else None
    recovery_days = 0
    for i in range(len(drawdown_data) - 1, -1, -1):
        if drawdown_data[i]["drawdown"] >= -0.0001:
            recovery_days = len(drawdown_data) - 1 - i
            break

    return {
        "performance_summary":     perf_summary,
        "benchmark_comparison":    bench_comp,
        "best_day_pct":            best_day,
        "worst_day_pct":           worst_day,
        "avg_daily_return_pct":    avg_day,
        "median_daily_return_pct": median_day,
        "current_drawdown_pct":    current_dd,
        "recovery_days_since_peak": recovery_days,
    }


# ─── Comprehensive analytics engine ──────────────────────────────────────────

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

    Returns a dict compatible with PortfolioAnalytics schema, including both the
    existing fields (risk_metrics, performance, drawdown, monthly_returns,
    derived_metrics) and new fields (portfolio_value_series, rolling_returns,
    contribution, position_analytics, performance_metrics).
    """
    _empty_risk: dict = {
        "sharpe": 0.0, "sortino": 0.0, "beta": 1.0, "alpha_pct": 0.0,
        "max_drawdown_pct": 0.0, "volatility_pct": 0.0, "calmar": 0.0,
        "win_rate_pct": 0.0, "annualized_return_pct": 0.0,
        "information_ratio": 0.0, "var_95_pct": 0.0, "trading_days": 0,
    }
    _empty_rolling: dict = {
        "return_1w": None, "return_1m": None,
        "return_3m": None, "return_ytd": None, "return_1y": None,
    }

    # ── Step 1: Reconstruct actual portfolio value series ─────────────
    active_dates, portfolio_values = reconstruct_portfolio_value(
        price_lookup, lots, dates
    )

    if not portfolio_values:
        return {
            "risk_metrics":          _empty_risk,
            "performance":           [],
            "drawdown":              [],
            "monthly_returns":       [],
            "derived_metrics":       None,
            "portfolio_value_series": [],
            "daily_returns":         [],
            "rolling_returns":       _empty_rolling,
            "contribution":          [],
            "position_analytics":    [],
            "performance_metrics":   None,
            # Advanced fields — empty when no portfolio data
            "rolling_metrics":        {"63d": [], "126d": [], "252d": []},
            "rolling_correlation_spy": [],
            "volatility_regime":       [],
            "rolling_drawdown_6m":     [],
            "growth_of_100":           [],
        }

    # ── Step 2: Daily returns from the reconstructed value series ─────
    port_returns = daily_returns(portfolio_values)

    # ── Step 3: Benchmark closes aligned to active_dates (forward-fill)
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

    # ── Step 4: Risk metrics ──────────────────────────────────────────
    b   = beta(port_returns, bm_returns)        if bm_returns else 1.0
    a   = alpha(port_returns, bm_returns, b)    if bm_returns else 0.0
    ir  = information_ratio(port_returns, bm_returns) if bm_returns else 0.0
    var = value_at_risk(port_returns)

    risk_metrics: dict = {
        "sharpe":                sharpe(port_returns),
        "sortino":               sortino(port_returns),
        "beta":                  b,
        "alpha_pct":             a,
        "max_drawdown_pct":      max_drawdown(portfolio_values),
        "volatility_pct":        annualized_vol(port_returns),
        "calmar":                calmar(port_returns, portfolio_values),
        "win_rate_pct":          win_rate(port_returns),
        "annualized_return_pct": annualized_return(port_returns),
        "information_ratio":     ir,
        "var_95_pct":            var,
        "trading_days":          len(port_returns),
    }
    # Extend with downside risk metrics (additive, no existing keys touched)
    risk_metrics.update(compute_downside_risk(port_returns, portfolio_values))

    # ── Step 5: Summary performance metrics dict ──────────────────────
    v0, vn = portfolio_values[0], portfolio_values[-1]
    perf_metrics: dict = {
        "cumulative_return": round((_pct_change(vn, v0) or 0.0), 4),
        "annualized_return": risk_metrics["annualized_return_pct"],
        "volatility":        risk_metrics["volatility_pct"],
        "sharpe_ratio":      risk_metrics["sharpe"],
        "max_drawdown":      risk_metrics["max_drawdown_pct"],
        "beta":              b,
        "alpha":             a,
        # Populated after correlation is computed (steps 6+)
        "correlation_spy":   None,
        "correlation_qqq":   None,
    }

    # ── Step 6: Correlation (port vs SPY, port vs QQQ) ───────────────
    corr_spy = pearson_corr(port_returns, spy_returns) if spy_returns else None
    corr_qqq = pearson_corr(port_returns, qqq_returns) if qqq_returns else None

    # ── Step 7: Cumulative series for chart (indexed to 100) ──────────
    port_cumul = cumulative_series(port_returns)
    bm_cumul   = cumulative_series(bm_returns)  if bm_returns  else []
    spy_cumul  = cumulative_series(spy_returns) if spy_returns else (bm_cumul if benchmark.upper() == "SPY" else [])
    qqq_cumul  = cumulative_series(qqq_returns) if qqq_returns else (bm_cumul if benchmark.upper() == "QQQ" else [])

    # Build benchmark dict for performance_series — avoid duplicating SPY/QQQ
    bench_cumul: dict[str, list[float]] = {}
    if spy_cumul: bench_cumul["SPY"] = spy_cumul
    if qqq_cumul: bench_cumul["QQQ"] = qqq_cumul

    # ── Step 8: Time series outputs ───────────────────────────────────
    dd_data    = drawdown_series(active_dates, portfolio_values)
    perf_chart = performance_series(active_dates, port_cumul, bench_cumul)
    mo_ret     = monthly_returns(active_dates, portfolio_values)

    # ── Step 9: Derived metrics ────────────────────────────────────────
    derived = compute_derived_metrics(
        dates         = active_dates,
        port_values   = port_cumul,
        port_returns  = port_returns,
        spy_values    = spy_cumul,
        qqq_values    = qqq_cumul,
        drawdown_data = dd_data,
    )

    # ── Step 10: Rolling returns ───────────────────────────────────────
    rolling = compute_rolling_returns(portfolio_values, active_dates)

    # ── Step 11: Contribution analytics ───────────────────────────────
    contribution = compute_contribution(lots, price_lookup, active_dates, portfolio_values)

    # ── Step 12: Position-level analytics ─────────────────────────────
    pos_analytics = compute_position_analytics(lots, price_lookup, active_dates, portfolio_values)

    # ── Step 13: Rolling risk metrics (63 / 126 / 252-day windows) ────
    rolling_risk = compute_rolling_risk_metrics(
        port_returns, spy_returns, active_dates
    )

    # ── Step 14: Rolling correlation vs SPY (90-day) ──────────────────
    rolling_corr_spy = (
        compute_rolling_correlation(port_returns, spy_returns, active_dates)
        if spy_returns else []
    )

    # ── Step 15: Volatility regime (30-day window) ────────────────────
    vol_regime = compute_volatility_regime(port_returns, active_dates)

    # ── Step 16: Exposure / concentration metrics ──────────────────────
    exposure = compute_exposure_metrics(lots, price_lookup, active_dates, portfolio_values)

    # ── Step 17: Rolling 6-month max drawdown ─────────────────────────
    rolling_mdd_6m = compute_rolling_max_drawdown(portfolio_values, active_dates, window=126)

    # ── Step 18: Market capture ratios ────────────────────────────────
    captures = compute_capture_ratios(port_returns, bm_returns) if bm_returns else {}

    # ── Step 19: Turnover estimate ────────────────────────────────────
    turnover = compute_turnover_pct(lots, price_lookup, active_dates)

    # ── Step 20: Growth of $100 chart ─────────────────────────────────
    growth100 = compute_growth_of_100(active_dates, portfolio_values, spy_closes, qqq_closes)

    # ── Step 21: Return distribution (skewness / kurtosis) ────────────
    ret_dist = compute_return_distribution(port_returns)

    # ── Populate all performance_metrics additions ─────────────────────
    perf_metrics["correlation_spy"] = corr_spy
    perf_metrics["correlation_qqq"] = corr_qqq
    perf_metrics.update(exposure)
    perf_metrics.update(captures)
    perf_metrics["estimated_turnover_pct"] = turnover
    perf_metrics.update(ret_dist)

    return {
        # ─── Existing fields (backward-compatible) ──────────────────────
        "risk_metrics":    risk_metrics,
        "performance":     perf_chart,
        "drawdown":        dd_data,
        "monthly_returns": mo_ret,
        "derived_metrics": derived,
        # ─── Previous-session analytics fields ───────────────────────────
        "portfolio_value_series": [
            {"date": d, "value": v}
            for d, v in zip(active_dates, portfolio_values)
        ],
        "daily_returns":      port_returns,
        "rolling_returns":    rolling,
        "contribution":       contribution,
        "position_analytics": pos_analytics,
        "performance_metrics": perf_metrics,
        # ─── New advanced analytics fields ───────────────────────────────
        "rolling_metrics":        rolling_risk,
        "rolling_correlation_spy": rolling_corr_spy,
        "volatility_regime":       vol_regime,
        "rolling_drawdown_6m":     rolling_mdd_6m,
        "growth_of_100":           growth100,
    }


# ─── Legacy wrapper (kept for any code still calling compute_all) ─────────────

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
    aligned: dict[str, list[float]],
    weights: dict[str, float],
    dates: list[str],
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

    b   = beta(port_returns, bm_returns)  if bm_returns else 1.0
    a   = alpha(port_returns, bm_returns, b) if bm_returns else 0.0
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
    if bm_values:   bench_vals[benchmark] = bm_values
    if qqq_values:  bench_vals["QQQ"]      = qqq_values

    dd_data = drawdown_series(port_dates, port_values)

    spy_closes = aligned.get("SPY", [])
    spy_vals   = cumulative_series(daily_returns(spy_closes)) if len(spy_closes) >= 2 else []

    return {
        "risk_metrics":    risk,
        "performance":     performance_series(port_dates, port_values, bench_vals),
        "drawdown":        dd_data,
        "monthly_returns": monthly_returns(port_dates, port_values),
        "derived_metrics": compute_derived_metrics(
            dates         = port_dates,
            port_values   = port_values,
            port_returns  = port_returns,
            spy_values    = spy_vals,
            qqq_values    = qqq_values,
            drawdown_data = dd_data,
        ),
    }
