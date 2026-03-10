"""
Validation tests for the NumPy-upgraded portfolio analytics engine.

Each test verifies that the vectorised implementation produces results
within an acceptable tolerance (1e-4) of the reference pure-Python
values, and that the output types match what the API layer expects.

Run with:
    cd backend
    .venv/bin/python -m pytest tests/test_analytics_numpy.py -v
"""
from __future__ import annotations

import math
import random
import statistics

import numpy as np
import pytest

# ── Module under test ──────────────────────────────────────────────────────────
from app.services.portfolio_analytics import (
    align_series,
    build_price_lookup,
    compute_engine,
)
from app.services.portfolio_analytics.return_series import (
    annualized_return,
    annualized_vol,
    cumulative_series,
    daily_returns,
)
from app.services.portfolio_analytics.risk_metrics import (
    beta,
    compute_downside_risk,
    max_drawdown,
    pearson_corr,
    sharpe,
    sortino,
    value_at_risk,
    win_rate,
)
from app.services.portfolio_analytics.rolling_metrics import (
    compute_rolling_correlation,
    compute_rolling_max_drawdown,
    compute_rolling_risk_metrics,
    compute_rolling_returns,
    compute_volatility_regime,
)
from app.services.portfolio_analytics.performance import (
    compute_return_distribution,
    drawdown_series,
)
from app.services.portfolio_analytics.contribution import compute_contribution
from app.services.portfolio_analytics.exposure import (
    compute_capture_ratios,
    compute_exposure_metrics,
)

TOL = 1e-4   # absolute tolerance between numpy and reference values


# ── Reference (pure-Python) implementations used for cross-validation ─────────

RF_DAILY   = 0.02 / 252
TRADING_YR = 252


def _ref_daily_returns(closes):
    return [(closes[i] - closes[i-1]) / closes[i-1]
            for i in range(1, len(closes)) if closes[i-1] != 0]


def _ref_annualized_return(returns):
    if not returns:
        return 0.0
    total = 1.0
    for r in returns:
        total *= (1 + r)
    return round((total ** (TRADING_YR / len(returns)) - 1) * 100, 4)


def _ref_annualized_vol(returns):
    if len(returns) < 2:
        return 0.0
    return round(statistics.stdev(returns) * math.sqrt(TRADING_YR) * 100, 4)


def _mean(arr):
    return sum(arr) / len(arr) if arr else 0.0


def _std(arr):
    return statistics.stdev(arr) if len(arr) >= 2 else 0.0


def _ref_sharpe(returns):
    if len(returns) < 20:
        return 0.0
    m = _mean(returns) - RF_DAILY
    s = _std(returns)
    return round(m / s * math.sqrt(TRADING_YR), 4) if s else 0.0


def _ref_sortino(returns):
    if len(returns) < 20:
        return 0.0
    m    = _mean(returns) - RF_DAILY
    dd_sq = sum(min(r - RF_DAILY, 0)**2 for r in returns) / len(returns)
    dd   = math.sqrt(dd_sq)
    return round(m / dd * math.sqrt(TRADING_YR), 4) if dd else 0.0


def _ref_max_drawdown(closes):
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


def _ref_beta(pr, mr):
    n = min(len(pr), len(mr))
    if n < 20:
        return 1.0
    p, m = pr[:n], mr[:n]
    mp, mm = _mean(p), _mean(m)
    cov = sum((p[i]-mp)*(m[i]-mm) for i in range(n)) / (n-1)
    var = sum((m[i]-mm)**2 for i in range(n)) / (n-1)
    return round(cov / var, 4) if var > 0 else 1.0


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def price_series():
    """Deterministic price series using a seeded random walk (500 days)."""
    rng = np.random.default_rng(42)
    prices = [100.0]
    for _ in range(499):
        prices.append(prices[-1] * (1 + rng.normal(0.0003, 0.012)))
    return prices


@pytest.fixture(scope="module")
def returns_series(price_series):
    return daily_returns(price_series)


@pytest.fixture(scope="module")
def spy_series():
    rng = np.random.default_rng(7)
    prices = [100.0]
    for _ in range(499):
        prices.append(prices[-1] * (1 + rng.normal(0.0004, 0.010)))
    return prices


@pytest.fixture(scope="module")
def spy_returns(spy_series):
    return daily_returns(spy_series)


@pytest.fixture(scope="module")
def dates():
    """Generate 500 trading day date strings starting 2022-01-03."""
    from datetime import date, timedelta
    d   = date(2022, 1, 3)
    out = []
    while len(out) < 500:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


# ── Tests: return_series ───────────────────────────────────────────────────────

class TestDailyReturns:
    def test_basic(self, price_series):
        result = daily_returns(price_series)
        ref    = _ref_daily_returns(price_series)
        assert len(result) == len(ref)
        assert all(abs(a - b) < TOL for a, b in zip(result, ref))

    def test_empty(self):
        assert daily_returns([]) == []
        assert daily_returns([100.0]) == []

    def test_returns_list(self, price_series):
        assert isinstance(daily_returns(price_series), list)

    def test_zero_prev_skipped(self):
        closes = [0.0, 100.0, 110.0]
        result = daily_returns(closes)
        # index 0→1 skipped (prev=0), index 1→2 = (110-100)/100 = 0.1
        assert len(result) == 1
        assert abs(result[0] - 0.1) < TOL


class TestCumulativeSeries:
    def test_matches_manual(self, returns_series):
        r   = returns_series[:50]
        res = cumulative_series(r, base=100.0)
        assert abs(res[0] - 100.0) < TOL
        v = 100.0
        for i, ret in enumerate(r):
            v *= (1 + ret)
            assert abs(res[i + 1] - v) < 1e-3

    def test_length(self, returns_series):
        r   = returns_series[:100]
        res = cumulative_series(r)
        assert len(res) == len(r) + 1

    def test_empty_returns(self):
        assert cumulative_series([]) == [100.0]


class TestAnnualizedReturn:
    def test_matches_reference(self, returns_series):
        r     = returns_series
        res   = annualized_return(r)
        ref   = _ref_annualized_return(r)
        assert abs(res - ref) < TOL

    def test_empty(self):
        assert annualized_return([]) == 0.0


class TestAnnualizedVol:
    def test_matches_reference(self, returns_series):
        r   = returns_series
        res = annualized_vol(r)
        ref = _ref_annualized_vol(r)
        assert abs(res - ref) < TOL

    def test_short_series(self):
        assert annualized_vol([0.01]) == 0.0


# ── Tests: risk_metrics ────────────────────────────────────────────────────────

class TestSharpe:
    def test_matches_reference(self, returns_series):
        r   = returns_series
        res = sharpe(r)
        ref = _ref_sharpe(r)
        assert abs(res - ref) < TOL

    def test_short_series(self):
        assert sharpe([0.01] * 5) == 0.0

    def test_returns_float(self, returns_series):
        assert isinstance(sharpe(returns_series), float)


class TestSortino:
    def test_matches_reference(self, returns_series):
        r   = returns_series
        res = sortino(r)
        ref = _ref_sortino(r)
        assert abs(res - ref) < TOL

    def test_short_series(self):
        assert sortino([0.01] * 5) == 0.0


class TestMaxDrawdown:
    def test_matches_reference(self, price_series):
        res = max_drawdown(price_series)
        ref = _ref_max_drawdown(price_series)
        assert abs(res - ref) < TOL

    def test_monotonic_series(self):
        assert max_drawdown([100.0, 110.0, 120.0]) == 0.0

    def test_full_drawdown(self):
        dd = max_drawdown([100.0, 90.0, 80.0, 70.0])
        assert dd < -25.0


class TestBeta:
    def test_matches_reference(self, returns_series, spy_returns):
        res = beta(returns_series, spy_returns)
        ref = _ref_beta(returns_series, spy_returns)
        assert abs(res - ref) < TOL

    def test_identical_series(self, returns_series):
        b = beta(returns_series, returns_series)
        assert abs(b - 1.0) < TOL

    def test_short_series(self):
        assert beta([0.01] * 5, [0.01] * 5) == 1.0


class TestValueAtRisk:
    def test_positive_output(self, returns_series):
        v = value_at_risk(returns_series)
        assert v >= 0.0

    def test_matches_manual(self, returns_series):
        r   = sorted(returns_series)
        idx = int(0.05 * len(r))
        ref = round(abs(r[idx]) * 100, 4)
        res = value_at_risk(returns_series)
        assert abs(res - ref) < TOL


class TestWinRate:
    def test_all_positive(self):
        r = [RF_DAILY + 0.01] * 30
        assert win_rate(r) == 100.0

    def test_all_negative(self):
        r = [RF_DAILY - 0.01] * 30
        assert win_rate(r) == 0.0

    def test_range(self, returns_series):
        w = win_rate(returns_series)
        assert 0.0 <= w <= 100.0


class TestPearsonCorr:
    def test_perfect_correlation(self, returns_series):
        c = pearson_corr(returns_series, returns_series)
        assert abs(c - 1.0) < TOL

    def test_range(self, returns_series, spy_returns):
        c = pearson_corr(returns_series, spy_returns)
        assert -1.0 <= c <= 1.0

    def test_short_series(self):
        assert pearson_corr([0.01] * 5, [0.01] * 5) is None


class TestDownsideRisk:
    def test_keys(self, returns_series, price_series):
        d = compute_downside_risk(returns_series, price_series)
        assert set(d.keys()) == {"downside_deviation", "ulcer_index", "tail_loss_95"}

    def test_non_negative(self, returns_series, price_series):
        d = compute_downside_risk(returns_series, price_series)
        assert d["downside_deviation"] >= 0.0
        assert d["ulcer_index"] >= 0.0
        assert d["tail_loss_95"] >= 0.0


# ── Tests: rolling_metrics ─────────────────────────────────────────────────────

class TestComputeRollingReturns:
    def test_keys(self, price_series, dates):
        values = price_series
        result = compute_rolling_returns(values, dates[:len(values)])
        assert set(result.keys()) == {"return_1w", "return_1m", "return_3m", "return_ytd", "return_1y"}

    def test_short_series(self):
        result = compute_rolling_returns([100.0], ["2024-01-01"])
        assert all(v is None for v in result.values())


class TestRollingRiskMetrics:
    def test_windows(self, returns_series, spy_returns, dates):
        result = compute_rolling_risk_metrics(
            returns_series, spy_returns, dates[:len(returns_series)]
        )
        assert set(result.keys()) == {"63d", "126d", "252d"}

    def test_point_keys(self, returns_series, spy_returns, dates):
        result = compute_rolling_risk_metrics(
            returns_series, spy_returns, dates[:len(returns_series)]
        )
        point = result["63d"][0]
        assert set(point.keys()) == {
            "date", "rolling_sharpe", "rolling_volatility",
            "rolling_beta", "rolling_sortino"
        }

    def test_length_63d(self, returns_series, spy_returns, dates):
        result = compute_rolling_risk_metrics(
            returns_series, spy_returns, dates[:len(returns_series)]
        )
        expected = max(0, len(returns_series) - 63 + 1)
        assert len(result["63d"]) == expected

    def test_sharpe_matches_scalar(self, returns_series, spy_returns, dates):
        """Rolling Sharpe for a full-length window should match scalar sharpe()."""
        W      = len(returns_series)
        result = compute_rolling_risk_metrics(
            returns_series, spy_returns, dates[:W], windows=(W,)
        )
        key    = f"{W}d"
        if result[key]:
            rs   = result[key][0]["rolling_sharpe"]
            ref  = sharpe(returns_series)
            if rs is not None:
                assert abs(rs - ref) < 0.01


class TestRollingCorrelation:
    def test_length(self, returns_series, spy_returns, dates):
        n      = min(len(returns_series), len(spy_returns))
        result = compute_rolling_correlation(
            returns_series[:n], spy_returns[:n], dates[:n], window=90
        )
        assert len(result) == max(0, n - 90 + 1)

    def test_range(self, returns_series, spy_returns, dates):
        n      = min(len(returns_series), len(spy_returns))
        result = compute_rolling_correlation(
            returns_series[:n], spy_returns[:n], dates[:n], window=90
        )
        for pt in result:
            if pt["value"] is not None:
                assert -1.0 <= pt["value"] <= 1.0


class TestVolatilityRegime:
    def test_regime_values(self, returns_series, dates):
        result = compute_volatility_regime(returns_series, dates[:len(returns_series)])
        for pt in result:
            assert pt["regime"] in {"low", "normal", "high"}
            assert pt["volatility"] >= 0.0

    def test_length(self, returns_series, dates):
        result = compute_volatility_regime(
            returns_series, dates[:len(returns_series)], window=30
        )
        assert len(result) == max(0, len(returns_series) - 30 + 1)


class TestRollingMaxDrawdown:
    def test_non_positive(self, price_series, dates):
        result = compute_rolling_max_drawdown(price_series, dates[:len(price_series)])
        for pt in result:
            assert pt["drawdown"] <= 0.0

    def test_length(self, price_series, dates):
        result = compute_rolling_max_drawdown(
            price_series, dates[:len(price_series)], window=126
        )
        assert len(result) == max(0, len(price_series) - 126 + 1)


# ── Tests: performance ─────────────────────────────────────────────────────────

class TestDrawdownSeries:
    def test_non_positive(self, price_series, dates):
        result = drawdown_series(dates[:len(price_series)], price_series)
        for pt in result:
            assert pt["drawdown"] <= 0.0

    def test_monotonic(self, dates):
        closes = [100.0 * (1.01 ** i) for i in range(50)]
        result = drawdown_series(dates[:50], closes)
        assert all(abs(pt["drawdown"]) < TOL for pt in result)

    def test_length(self, price_series, dates):
        result = drawdown_series(dates[:len(price_series)], price_series)
        assert len(result) == len(price_series)


class TestReturnDistribution:
    def test_keys(self, returns_series):
        d = compute_return_distribution(returns_series)
        assert "skewness" in d and "kurtosis" in d

    def test_normal_approx(self):
        rng = np.random.default_rng(0)
        r   = rng.normal(0, 0.01, 5000).tolist()
        d   = compute_return_distribution(r)
        # Normal distribution → skew ≈ 0, excess kurtosis ≈ 0
        assert abs(d["skewness"]) < 0.15
        assert abs(d["kurtosis"]) < 0.5


# ── Tests: exposure ────────────────────────────────────────────────────────────

class TestCaptureRatios:
    def test_keys(self, returns_series, spy_returns):
        n   = min(len(returns_series), len(spy_returns))
        res = compute_capture_ratios(returns_series[:n], spy_returns[:n])
        assert "upside_capture_ratio" in res
        assert "downside_capture_ratio" in res

    def test_perfect_tracking(self, spy_returns):
        res = compute_capture_ratios(spy_returns, spy_returns)
        assert res["upside_capture_ratio"]   is not None
        assert res["downside_capture_ratio"] is not None
        assert abs(res["upside_capture_ratio"]   - 1.0) < TOL
        assert abs(res["downside_capture_ratio"] - 1.0) < TOL

    def test_short_series(self):
        res = compute_capture_ratios([0.01] * 5, [0.01] * 5)
        assert res["upside_capture_ratio"] is None


# ── Tests: compute_engine (integration) ────────────────────────────────────────

class TestComputeEngine:
    @pytest.fixture(scope="class")
    def engine_result(self, price_series, spy_series, dates):
        """Run compute_engine with a synthetic 1-lot portfolio."""
        tickers = ["PORT", "SPY"]
        histories = {
            "PORT": [{"ts": dates[i], "close": price_series[i]} for i in range(len(dates))],
            "SPY":  [{"ts": dates[i], "close": spy_series[i]}  for i in range(len(dates))],
        }
        pl   = build_price_lookup(histories)
        _, __ = align_series(histories, ref_ticker="SPY")
        lots = [{
            "ticker":         "PORT",
            "shares":         10.0,
            "cost_basis":     price_series[0],
            "opened_at_date": dates[0],
        }]
        return compute_engine(pl, lots, dates, benchmark="SPY")

    def test_required_keys(self, engine_result):
        required = {
            "risk_metrics", "performance", "drawdown", "monthly_returns",
            "derived_metrics", "portfolio_value_series", "daily_returns",
            "rolling_returns", "contribution", "position_analytics",
            "performance_metrics", "rolling_metrics", "rolling_correlation_spy",
            "volatility_regime", "rolling_drawdown_6m", "growth_of_100",
        }
        assert required.issubset(engine_result.keys())

    def test_risk_metrics_keys(self, engine_result):
        rm = engine_result["risk_metrics"]
        for key in ("sharpe", "sortino", "beta", "alpha_pct", "max_drawdown_pct",
                    "volatility_pct", "calmar", "win_rate_pct",
                    "annualized_return_pct", "information_ratio", "var_95_pct",
                    "trading_days", "downside_deviation", "ulcer_index", "tail_loss_95"):
            assert key in rm, f"missing risk_metrics key: {key}"

    def test_performance_metrics_keys(self, engine_result):
        pm = engine_result["performance_metrics"]
        assert pm is not None
        for key in ("correlation_spy", "herfindahl_index",
                    "upside_capture_ratio", "skewness", "kurtosis"):
            assert key in pm, f"missing performance_metrics key: {key}"

    def test_rolling_metrics_windows(self, engine_result):
        rm = engine_result["rolling_metrics"]
        assert set(rm.keys()) == {"63d", "126d", "252d"}

    def test_types_are_plain_python(self, engine_result):
        """Ensure no numpy scalars leak into the output."""
        rm = engine_result["risk_metrics"]
        for k, v in rm.items():
            if v is not None:
                assert isinstance(v, (int, float)), f"risk_metrics[{k}] is {type(v)}"

        for pt in engine_result["performance"][:3]:
            for k, v in pt.items():
                if k != "date":
                    assert isinstance(v, (int, float)), f"performance point {k} is {type(v)}"

    def test_drawdown_non_positive(self, engine_result):
        for pt in engine_result["drawdown"]:
            assert pt["drawdown"] <= 0.0 + TOL

    def test_max_drawdown_negative(self, engine_result):
        mdd = engine_result["risk_metrics"]["max_drawdown_pct"]
        assert mdd <= 0.0

    def test_sharpe_finite(self, engine_result):
        s = engine_result["risk_metrics"]["sharpe"]
        assert math.isfinite(s)

    def test_contribution_sorted(self, engine_result):
        contribs = [c["pnl_contribution"] for c in engine_result["contribution"]]
        assert contribs == sorted(contribs, reverse=True)
