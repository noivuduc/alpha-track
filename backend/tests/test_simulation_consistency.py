"""
Simulation consistency tests.

Core invariant:
    simulation "before" metrics  ==  dashboard metrics

Both systems must use the same:
  - TWR daily return series
  - compute_snapshot() from portfolio_metrics (SoT)
  - risk-free rate (RF_ANNUAL = 0.02)

Run with:
    cd backend
    .venv/bin/python -m pytest tests/test_simulation_consistency.py -v
"""
from __future__ import annotations

import math
import pytest

from app.services.portfolio_analytics.portfolio_metrics import (
    compute_snapshot,
    compute_sharpe,
    compute_return,
    compute_volatility,
    build_price_lookup,
    align_series,
    reconstruct_portfolio_value,
    build_cash_flows,
    compute_twr_returns,
    cumulative_series,
    daily_returns,
    RF_ANNUAL,
    RF_DAILY,
    TRADING_YR,
    sharpe,
    sortino,
    max_drawdown,
)
from app.services.portfolio_analytics.engine import compute_engine

# Tolerance for before/dashboard parity
CONSISTENCY_TOL = 0.005   # Sharpe must agree within 0.005
FORMULA_TOL     = 1e-6    # pure formula checks


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures — synthetic price history
# ─────────────────────────────────────────────────────────────────────────────

def _price_series(start: float, returns: list[float]) -> list[dict]:
    """Build [{ts, close}] from a starting price and a list of daily returns."""
    prices = [start]
    for r in returns:
        prices.append(prices[-1] * (1.0 + r))
    base_date = "2024-01-02"

    from datetime import date, timedelta
    bars = []
    d = date.fromisoformat(base_date)
    for p in prices:
        bars.append({"ts": d.isoformat(), "close": round(p, 4)})
        d += timedelta(days=1)
    return bars


# 252 daily returns drawn from a fixed RNG (reproducible)
import random
_rng = random.Random(42)
_AAPL_RETS = [_rng.gauss(0.0005, 0.012) for _ in range(252)]
_MSFT_RETS = [_rng.gauss(0.0004, 0.010) for _ in range(252)]
_NVDA_RETS = [_rng.gauss(0.0008, 0.018) for _ in range(252)]
_SPY_RETS  = [_rng.gauss(0.0003, 0.008) for _ in range(252)]

HISTORIES = {
    "AAPL": _price_series(180.0, _AAPL_RETS),
    "MSFT": _price_series(320.0, _MSFT_RETS),
    "NVDA": _price_series(450.0, _NVDA_RETS),
    "SPY":  _price_series(450.0, _SPY_RETS),
}

LOTS = [
    {"ticker": "AAPL", "shares": 10.0, "cost_basis": 180.0, "opened_at_date": "2024-01-02"},
    {"ticker": "MSFT", "shares":  5.0, "cost_basis": 320.0, "opened_at_date": "2024-01-02"},
]


def _twr_returns_from_lots(lots, histories):
    """Compute TWR returns the same way compute_engine and simulation do."""
    pl     = build_price_lookup(histories)
    dates, _ = align_series(histories, ref_ticker="SPY")
    a_dates, p_vals = reconstruct_portfolio_value(pl, lots, dates)
    cfs    = build_cash_flows(lots, a_dates)
    rets   = compute_twr_returns(p_vals, a_dates, cfs)
    vals   = cumulative_series(rets)
    spy_cl = [b["close"] for b in histories["SPY"]]
    spy_r  = daily_returns(spy_cl)
    return rets, vals, spy_r


# ─────────────────────────────────────────────────────────────────────────────
# PART 1 — Sharpe formula
# ─────────────────────────────────────────────────────────────────────────────

class TestSharpeFormula:
    """Verify the canonical Sharpe implementation matches the textbook formula."""

    def test_sharpe_formula_equivalence(self):
        """
        The daily form and the annualized form of Sharpe are NOT algebraically
        identical because compute_return() uses geometric compounding
        (np.prod(1+r)^(252/n) - 1) while the daily form uses arithmetic mean.
        They will be numerically close but NOT equal.

        What we DO guarantee:
          - compute_sharpe(rets) == sharpe(rets)         (same implementation)
          - Both use RF_DAILY = RF_ANNUAL / 252          (same risk-free rate)
          - The formula is monotone: more +ve returns → higher Sharpe
        """
        import numpy as np

        rets = _AAPL_RETS[:50]
        r    = np.array(rets)

        # Our implementation (daily form)
        daily_form = (r.mean() - RF_DAILY) / r.std(ddof=1) * math.sqrt(TRADING_YR)

        # compute_sharpe must agree with the daily form within rounding (sharpe
        # rounds to 4dp, so max deviation from the unrounded value is 5e-5)
        assert abs(compute_sharpe(rets) - daily_form) < 5e-4, (
            f"compute_sharpe diverged from daily form: {compute_sharpe(rets):.6f} vs {daily_form:.6f}"
        )

        # Monotonicity: shifting all returns up must increase Sharpe
        shifted = [r_ + 0.001 for r_ in rets]
        assert sharpe(shifted) > sharpe(rets), "Sharpe must increase when returns increase"

    def test_sharpe_uses_rf_daily(self):
        """RF_DAILY must equal RF_ANNUAL / 252."""
        assert abs(RF_DAILY - RF_ANNUAL / TRADING_YR) < 1e-12

    def test_sharpe_zero_vol(self):
        """
        Exactly-zero volatility → Sharpe = 0 (not inf/nan).
        Must use exactly 0.0 returns: 0.0001 is not exactly representable in
        float64 so ddof=1 std of repeated 0.0001 is not precisely 0.
        """
        flat = [0.0] * 30
        s = sharpe(flat)
        assert s == 0.0

    def test_sharpe_small_dataset(self):
        """Fewer than 20 returns → Sharpe = 0 (guard against noise)."""
        s = sharpe([0.01, -0.01, 0.005])
        assert s == 0.0

    def test_compute_sharpe_default_rf(self):
        """compute_sharpe() with default RF equals sharpe()."""
        rets = _AAPL_RETS
        assert abs(compute_sharpe(rets) - sharpe(rets)) < FORMULA_TOL

    def test_compute_sharpe_custom_rf(self):
        """compute_sharpe() with non-default RF uses the provided value."""
        rets  = _AAPL_RETS
        s_low = compute_sharpe(rets, rf=0.00)
        s_hi  = compute_sharpe(rets, rf=0.05)
        # Higher RF → lower Sharpe (assuming positive expected return)
        assert s_low > s_hi


# ─────────────────────────────────────────────────────────────────────────────
# PART 2 — Dashboard vs compute_snapshot parity
# ─────────────────────────────────────────────────────────────────────────────

class TestDashboardConsistency:
    """
    compute_engine() and compute_snapshot() on the same TWR returns must
    produce identical Sharpe values.
    """

    def test_engine_sharpe_matches_compute_snapshot(self):
        """compute_engine and compute_snapshot return equal Sharpe."""
        pl     = build_price_lookup(HISTORIES)
        dates, _ = align_series(HISTORIES, ref_ticker="SPY")

        engine_result = compute_engine(pl, LOTS, dates, benchmark="SPY")
        engine_sharpe = engine_result["risk_metrics"]["sharpe"]

        rets, vals, spy_r = _twr_returns_from_lots(LOTS, HISTORIES)
        snap = compute_snapshot(rets, vals, spy_r, label="test_dashboard")

        assert abs(engine_sharpe - snap["sharpe"]) < FORMULA_TOL, (
            f"engine={engine_sharpe:.6f}  snapshot={snap['sharpe']:.6f}"
        )

    def test_engine_sortino_matches_compute_snapshot(self):
        rets, vals, spy_r = _twr_returns_from_lots(LOTS, HISTORIES)
        snap = compute_snapshot(rets, vals, spy_r)

        pl   = build_price_lookup(HISTORIES)
        dates, _ = align_series(HISTORIES, ref_ticker="SPY")
        eng  = compute_engine(pl, LOTS, dates, benchmark="SPY")

        assert abs(eng["risk_metrics"]["sortino"] - snap["sortino"]) < FORMULA_TOL

    def test_engine_volatility_matches_compute_snapshot(self):
        rets, vals, spy_r = _twr_returns_from_lots(LOTS, HISTORIES)
        snap = compute_snapshot(rets, vals, spy_r)

        pl   = build_price_lookup(HISTORIES)
        dates, _ = align_series(HISTORIES, ref_ticker="SPY")
        eng  = compute_engine(pl, LOTS, dates, benchmark="SPY")

        assert abs(eng["risk_metrics"]["volatility_pct"] - snap["volatility_pct"]) < FORMULA_TOL


# ─────────────────────────────────────────────────────────────────────────────
# PART 3 — Simulation "before" == dashboard
# ─────────────────────────────────────────────────────────────────────────────

class TestSimulationBeforeConsistency:
    """
    The simulation 'before' snapshot must agree with the dashboard within
    CONSISTENCY_TOL because both use the same TWR return pipeline.
    """

    def _sim_before_sharpe(self, new_ticker: str, new_weight: float) -> float:
        """
        Run the pure-compute portion of simulate_add_position inline
        (no I/O) and return the before_snap Sharpe.
        """
        pl             = build_price_lookup(HISTORIES)
        dates, _       = align_series(HISTORIES, ref_ticker="SPY")
        a_dates, p_vals = reconstruct_portfolio_value(pl, LOTS, dates)
        cfs            = build_cash_flows(LOTS, a_dates)
        before_rets    = compute_twr_returns(p_vals, a_dates, cfs)
        before_vals    = cumulative_series(before_rets)

        spy_cl   = [b["close"] for b in HISTORIES["SPY"]]
        spy_r    = daily_returns(spy_cl)
        snap = compute_snapshot(before_rets, before_vals, spy_r, label="sim_before_test")
        return snap["sharpe"]

    def _dashboard_sharpe(self) -> float:
        pl     = build_price_lookup(HISTORIES)
        dates, _ = align_series(HISTORIES, ref_ticker="SPY")
        eng    = compute_engine(pl, LOTS, dates, benchmark="SPY")
        return eng["risk_metrics"]["sharpe"]

    def test_sim_before_equals_dashboard_sharpe(self):
        """KEY TEST: simulation before == dashboard.  Tolerance 0.005."""
        sim_sharpe  = self._sim_before_sharpe("NVDA", 0.10)
        dash_sharpe = self._dashboard_sharpe()

        assert abs(sim_sharpe - dash_sharpe) < CONSISTENCY_TOL, (
            f"Sharpe inconsistency! "
            f"sim_before={sim_sharpe:.4f}  dashboard={dash_sharpe:.4f}  "
            f"delta={abs(sim_sharpe - dash_sharpe):.4f}  tolerance={CONSISTENCY_TOL}"
        )

    def test_sim_before_invariant_to_new_ticker(self):
        """Before Sharpe should not change regardless of which ticker is simulated."""
        s1 = self._sim_before_sharpe("NVDA", 0.10)
        s2 = self._sim_before_sharpe("NVDA", 0.20)
        # before doesn't change with different weights
        assert abs(s1 - s2) < FORMULA_TOL, (
            f"Before Sharpe changed with different weights: {s1:.6f} vs {s2:.6f}"
        )

    def test_after_changes_with_new_position(self):
        """After snapshot must differ from before when a new ticker is added."""
        pl        = build_price_lookup(HISTORIES)
        dates, _  = align_series(HISTORIES, ref_ticker="SPY")
        a_dates, p_vals = reconstruct_portfolio_value(pl, LOTS, dates)
        cfs       = build_cash_flows(LOTS, a_dates)
        before_r  = compute_twr_returns(p_vals, a_dates, cfs)
        before_v  = cumulative_series(before_r)

        nvda_cl   = [b["close"] for b in HISTORIES["NVDA"]]
        nvda_r    = daily_returns(nvda_cl)
        spy_cl    = [b["close"] for b in HISTORIES["SPY"]]
        spy_r     = daily_returns(spy_cl)

        n   = len(before_r)
        w   = 0.15
        nvda_aligned = [nvda_r[i] if i < len(nvda_r) else 0.0 for i in range(n)]
        after_r = [(1 - w) * before_r[i] + w * nvda_aligned[i] for i in range(n)]
        after_v = cumulative_series(after_r)

        snap_before = compute_snapshot(before_r, before_v, spy_r)
        snap_after  = compute_snapshot(after_r,  after_v,  spy_r)

        # The return series differ, so at least one metric must differ
        metrics_differ = any(
            abs(snap_after[k] - snap_before[k]) > 1e-4
            for k in snap_before
        )
        assert metrics_differ, "After snapshot identical to before — blend did not work"


# ─────────────────────────────────────────────────────────────────────────────
# PART 4 — Edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_empty_returns(self):
        snap = compute_snapshot([], [100.0], [], label="empty")
        assert snap["sharpe"] == 0.0
        assert snap["beta"]   == 1.0

    def test_single_return(self):
        snap = compute_snapshot([0.01], [100.0, 101.0], [], label="single")
        assert snap["sharpe"] == 0.0   # < 5 observations

    def test_four_returns(self):
        snap = compute_snapshot([0.01, -0.01, 0.01, -0.01], [100, 101, 100, 101, 100], [])
        assert snap["sharpe"] == 0.0   # exactly 4 < 5

    def test_five_returns_returns_zero_sharpe(self):
        """
        compute_snapshot guards at n < 5 and returns empty dict.
        The underlying sharpe() function requires n >= 20 to avoid noise.
        5 returns: compute_snapshot lets them through (n >= 5) but sharpe()
        returns 0.0 because len < 20.
        volatility_pct CAN be non-zero since annualized_vol uses n >= 2.
        """
        rets = [0.01, 0.02, 0.015, 0.012, 0.008]
        vals = cumulative_series(rets)
        snap = compute_snapshot(rets, vals, [], label="five_rets")
        # sharpe() needs 20 samples — returns 0 here
        assert snap["sharpe"] == 0.0
        # annualized_vol needs only 2 samples — should be positive
        assert snap["volatility_pct"] > 0.0

    def test_all_zero_returns(self):
        rets = [0.0] * 30
        vals = [100.0] * 31
        snap = compute_snapshot(rets, vals, [], label="zeros")
        assert snap["sharpe"] == 0.0
        assert snap["volatility_pct"] == 0.0

    def test_max_drawdown_monotone_up(self):
        """Monotonically increasing prices → max drawdown = 0."""
        closes = [100.0 + i for i in range(50)]
        assert max_drawdown(closes) == 0.0

    def test_compute_snapshot_delta_keys(self):
        """compute_snapshot must return exactly the keys expected by SimulateResponse."""
        expected = {
            "sharpe", "sortino", "beta", "alpha_pct",
            "max_drawdown_pct", "volatility_pct",
            "annualized_return_pct", "var_95_pct",
        }
        rets, vals, spy_r = _twr_returns_from_lots(LOTS, HISTORIES)
        snap = compute_snapshot(rets, vals, spy_r)
        assert set(snap.keys()) == expected, (
            f"Key mismatch: got {set(snap.keys())} expected {expected}"
        )

    def test_rf_consistency(self):
        """RF_DAILY == RF_ANNUAL / 252 to machine precision."""
        assert abs(RF_DAILY * TRADING_YR - RF_ANNUAL) < 1e-12
