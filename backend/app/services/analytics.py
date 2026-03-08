"""
Portfolio Analytics Engine — pure computation, zero I/O.

All functions accept plain Python lists/dicts and return results.
Database and HTTP calls live in the router; this module only does math.

Risk-free rate: 5.25 % annual  →  RF_DAILY = 0.0525 / 252
Annualisation factor: 252 trading days/year
"""
from __future__ import annotations

import math
import statistics
from datetime import datetime

RF_DAILY   = 0.0525 / 252
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
    return round(statistics.stdev(returns) * math.sqrt(TRADING_YR) * 100, 4)


# ─── Risk / quality metrics ───────────────────────────────────────────────────

def _mean(arr: list[float]) -> float:
    return sum(arr) / len(arr) if arr else 0.0


def _std(arr: list[float]) -> float:
    return statistics.stdev(arr) if len(arr) >= 2 else 0.0


def sharpe(returns: list[float]) -> float:
    """Annualized Sharpe ratio."""
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
    """Beta of portfolio vs market."""
    n = min(len(port_returns), len(mkt_returns))
    if n < 20:
        return 1.0
    pr = port_returns[:n]
    mr = mkt_returns[:n]
    mp, mm = _mean(pr), _mean(mr)
    cov = sum((pr[i] - mp) * (mr[i] - mm) for i in range(n))
    var = sum((mr[i] - mm) ** 2 for i in range(n))
    return round(cov / var, 4) if var else 1.0


def alpha(port_returns: list[float], mkt_returns: list[float], b: float) -> float:
    """Jensen's alpha, annualized as percentage."""
    n = min(len(port_returns), len(mkt_returns))
    if n < 20:
        return 0.0
    mp = _mean(port_returns[:n])
    mm = _mean(mkt_returns[:n])
    return round((mp - RF_DAILY - b * (mm - RF_DAILY)) * TRADING_YR * 100, 4)


def calmar(returns: list[float], closes: list[float]) -> float:
    """Calmar ratio = annualized return / |max drawdown|."""
    mdd = abs(max_drawdown(closes))
    ann = annualized_return(returns)
    return round(ann / mdd, 4) if mdd else 0.0


def win_rate(returns: list[float]) -> float:
    """Percentage of days with a positive return."""
    if not returns:
        return 0.0
    return round(sum(1 for r in returns if r > 0) / len(returns) * 100, 2)


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
    return round(abs(sorted_r[max(idx - 1, 0)]) * 100, 4)


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
    # Pick reference or fall back to longest available series
    if ref_ticker not in histories or not histories[ref_ticker]:
        ref_ticker = max(histories, key=lambda t: len(histories[t]), default=None)
    if ref_ticker is None:
        return [], {}

    ref_dates = [bar["ts"][:10] for bar in histories[ref_ticker]]
    aligned: dict[str, list[float]] = {}

    for ticker, bars in histories.items():
        d2c = {bar["ts"][:10]: float(bar["close"]) for bar in bars}
        closes: list[float] = []
        for d in ref_dates:
            if d in d2c:
                closes.append(d2c[d])
            elif closes:
                closes.append(closes[-1])   # forward-fill weekend / holiday
            # else skip leading missing data — series starts later
        aligned[ticker] = closes

    return ref_dates, aligned


def build_portfolio_returns(
    aligned: dict[str, list[float]],
    weights: dict[str, float],
    n_days: int,
) -> list[float]:
    """
    Weighted portfolio daily returns from aligned close price series.

    weights must sum to ~1.0 (will be normalised if not).
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
    Aggregate a daily wealth index into monthly returns.

    Returns list of {"year", "month", "label", "value" (%)}.
    """
    if len(dates) < 2 or len(dates) != len(values):
        return []

    buckets: dict[str, tuple[float, float]] = {}
    for d, v in zip(dates, values):
        key = d[:7]
        if key not in buckets:
            buckets[key] = (v, v)
        buckets[key] = (buckets[key][0], v)  # update end-of-month value

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

    base_p = portfolio_values[0] if portfolio_values[0] else 1.0
    b_bases = {k: (v[0] if v and v[0] else 1.0) for k, v in benchmark_values.items()}

    out = []
    for i, d in enumerate(dates):
        pt: dict = {"date": d}
        if i < len(portfolio_values):
            pt["portfolio"] = round(portfolio_values[i] / base_p * 100, 2)
        for k, vals in benchmark_values.items():
            if i < len(vals) and vals[i]:
                pt[k.lower()] = round(vals[i] / b_bases[k] * 100, 2)
        out.append(pt)
    return out


# ─── High-level bundle ────────────────────────────────────────────────────────

def compute_all(
    aligned: dict[str, list[float]],
    weights: dict[str, float],
    dates: list[str],
    benchmark: str = "SPY",
) -> dict:
    """
    Convenience wrapper: build portfolio + compute every metric at once.

    Returns a dict with keys:
        risk_metrics, performance, drawdown, monthly_returns
    """
    n = len(dates)

    # Portfolio time series
    port_returns = build_portfolio_returns(aligned, weights, n)
    port_values  = cumulative_series(port_returns)
    port_dates   = dates[:len(port_values)]

    # Benchmark series
    bm_returns = daily_returns(aligned.get(benchmark, []))
    bm_values  = cumulative_series(bm_returns) if bm_returns else []

    qqq_returns = daily_returns(aligned.get("QQQ", []))
    qqq_values  = cumulative_series(qqq_returns) if qqq_returns else []

    # Risk metrics
    b   = beta(port_returns, bm_returns)  if bm_returns else 1.0
    a   = alpha(port_returns, bm_returns, b) if bm_returns else 0.0
    ir  = information_ratio(port_returns, bm_returns) if bm_returns else 0.0
    var = value_at_risk(port_returns)

    risk = {
        "sharpe":               sharpe(port_returns),
        "sortino":              sortino(port_returns),
        "beta":                 b,
        "alpha_pct":            a,
        "max_drawdown_pct":     max_drawdown(port_values),
        "volatility_pct":       annualized_vol(port_returns),
        "calmar":               calmar(port_returns, port_values),
        "win_rate_pct":         win_rate(port_returns),
        "annualized_return_pct":annualized_return(port_returns),
        "information_ratio":    ir,
        "var_95_pct":           var,
        "trading_days":         len(port_returns),
    }

    # Build benchmark dict for performance_series
    bench_vals: dict[str, list[float]] = {}
    if bm_values:
        bench_vals[benchmark] = bm_values
    if qqq_values:
        bench_vals["QQQ"] = qqq_values

    return {
        "risk_metrics":   risk,
        "performance":    performance_series(port_dates, port_values, bench_vals),
        "drawdown":       drawdown_series(port_dates, port_values),
        "monthly_returns":monthly_returns(port_dates, port_values),
    }
