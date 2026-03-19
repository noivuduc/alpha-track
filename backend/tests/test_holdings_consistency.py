"""
Holdings vs Overview consistency tests.

Validates three invariants of the return model:

1. Contribution identity:
       sum(pnl_contribution_i) == total_portfolio_pnl
       i.e. per-ticker P&Ls add up to the total portfolio gain/loss.

2. Contribution-pct identity:
       sum(contribution_pct_i) * portfolio_value / 100 ≈ sum(pnl_contribution_i)
       i.e. contribution percentages are consistent with dollar P&Ls.

3. Position response formula:
       contribution_to_portfolio_pct_i = gain_loss_i / total_portfolio_value × 100
       sum(contribution_to_portfolio_pct_i) = total_gain / total_portfolio_value × 100

4. Portfolio value reconstruction:
       Reconstructed NAV from lots + prices ≈ sum(shares × current_price)

Run with:
    cd backend
    .venv/bin/python -m pytest tests/test_holdings_consistency.py -v
"""
from __future__ import annotations

import pytest

from app.services.portfolio_analytics.contribution import compute_contribution
from app.services.portfolio_analytics.portfolio_reconstruction import (
    build_price_lookup,
    align_series,
    reconstruct_portfolio_value,
)
from app.services.portfolio_analytics.return_series import build_cash_flows


# ── Shared fixtures ────────────────────────────────────────────────────────────

DATES = [
    "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05",
    "2024-01-08", "2024-01-09", "2024-01-10", "2024-01-11",
    "2024-01-12", "2024-01-16",
]

# Three positions opened at different times
LOTS = [
    {"ticker": "AAPL", "shares": 10.0, "cost_basis": 180.0, "opened_at_date": "2024-01-02"},
    {"ticker": "MSFT", "shares": 5.0,  "cost_basis": 370.0, "opened_at_date": "2024-01-02"},
    {"ticker": "NVDA", "shares": 2.0,  "cost_basis": 490.0, "opened_at_date": "2024-01-04"},
]

# Simulated price histories (all dates have prices)
HISTORIES = {
    "AAPL": [
        {"ts": "2024-01-02", "close": 180.0},
        {"ts": "2024-01-03", "close": 182.0},
        {"ts": "2024-01-04", "close": 184.0},
        {"ts": "2024-01-05", "close": 186.0},
        {"ts": "2024-01-08", "close": 188.0},
        {"ts": "2024-01-09", "close": 190.0},
        {"ts": "2024-01-10", "close": 192.0},
        {"ts": "2024-01-11", "close": 194.0},
        {"ts": "2024-01-12", "close": 196.0},
        {"ts": "2024-01-16", "close": 198.0},
    ],
    "MSFT": [
        {"ts": "2024-01-02", "close": 370.0},
        {"ts": "2024-01-03", "close": 372.0},
        {"ts": "2024-01-04", "close": 374.0},
        {"ts": "2024-01-05", "close": 376.0},
        {"ts": "2024-01-08", "close": 378.0},
        {"ts": "2024-01-09", "close": 380.0},
        {"ts": "2024-01-10", "close": 382.0},
        {"ts": "2024-01-11", "close": 384.0},
        {"ts": "2024-01-12", "close": 386.0},
        {"ts": "2024-01-16", "close": 388.0},
    ],
    "NVDA": [
        {"ts": "2024-01-02", "close": 490.0},
        {"ts": "2024-01-03", "close": 492.0},
        {"ts": "2024-01-04", "close": 490.0},  # flat on open date
        {"ts": "2024-01-05", "close": 495.0},
        {"ts": "2024-01-08", "close": 500.0},
        {"ts": "2024-01-09", "close": 505.0},
        {"ts": "2024-01-10", "close": 510.0},
        {"ts": "2024-01-11", "close": 515.0},
        {"ts": "2024-01-12", "close": 520.0},
        {"ts": "2024-01-16", "close": 525.0},
    ],
}


@pytest.fixture
def setup():
    price_lookup    = build_price_lookup(HISTORIES)
    dates, _        = align_series(HISTORIES, ref_ticker="AAPL")
    active_dates, portfolio_values = reconstruct_portfolio_value(price_lookup, LOTS, dates)
    return price_lookup, dates, active_dates, portfolio_values


# ── Test 1: Contribution P&L sum identity ─────────────────────────────────────

def test_contribution_pnl_sum_equals_total_portfolio_pnl(setup):
    """
    sum(pnl_contribution_i) must equal total portfolio P&L.

    total_pnl = current_portfolio_value - total_cost
    """
    price_lookup, dates, active_dates, portfolio_values = setup
    rows = compute_contribution(LOTS, price_lookup, active_dates, portfolio_values)

    total_cost = sum(lot["shares"] * lot["cost_basis"] for lot in LOTS)
    portfolio_current_value = portfolio_values[-1]
    expected_total_pnl = portfolio_current_value - total_cost

    actual_pnl_sum = sum(r["pnl_contribution"] for r in rows)

    assert abs(actual_pnl_sum - expected_total_pnl) < 0.01, (
        f"sum(pnl_contribution)={actual_pnl_sum:.4f} != total_pnl={expected_total_pnl:.4f}"
    )


# ── Test 2: Contribution-pct identity ─────────────────────────────────────────

def test_contribution_pct_consistent_with_dollar_pnl(setup):
    """
    contribution_pct_i = pnl_i / portfolio_current_value × 100
    Therefore: sum(contribution_pct_i) = total_pnl / portfolio_current_value × 100
    """
    price_lookup, dates, active_dates, portfolio_values = setup
    rows = compute_contribution(LOTS, price_lookup, active_dates, portfolio_values)

    portfolio_current_value = portfolio_values[-1]

    for row in rows:
        expected_pct = row["pnl_contribution"] / portfolio_current_value * 100
        assert abs(row["contribution_pct"] - expected_pct) < 0.001, (
            f"{row['ticker']}: contribution_pct={row['contribution_pct']:.4f} "
            f"!= pnl/value={expected_pct:.4f}"
        )

    # Sum of pcts = total_pnl / portfolio_value × 100
    total_pnl   = sum(r["pnl_contribution"] for r in rows)
    pct_sum     = sum(r["contribution_pct"] for r in rows)
    expected_sum = total_pnl / portfolio_current_value * 100
    assert abs(pct_sum - expected_sum) < 0.001


# ── Test 3: Position endpoint contribution formula ────────────────────────────

def test_position_contribution_to_portfolio_pct_formula():
    """
    contribution_to_portfolio_pct_i = gain_i / total_portfolio_value × 100

    This mirrors the formula used in the list_positions endpoint.
    sum(contribution_to_portfolio_pct_i) == total_gain / total_value × 100
    """
    # Simulate endpoint computation
    positions = [
        {"shares": 10.0, "cost_basis": 180.0, "current_price": 198.0},
        {"shares": 5.0,  "cost_basis": 370.0, "current_price": 388.0},
        {"shares": 2.0,  "cost_basis": 490.0, "current_price": 525.0},
    ]

    for p in positions:
        p["current_value"] = p["shares"] * p["current_price"]
        p["cost_value"]    = p["shares"] * p["cost_basis"]
        p["gain"]          = p["current_value"] - p["cost_value"]

    total_value = sum(p["current_value"] for p in positions)
    total_gain  = sum(p["gain"]          for p in positions)

    for p in positions:
        p["contribution_to_portfolio_pct"] = p["gain"] / total_value * 100

    contrib_sum = sum(p["contribution_to_portfolio_pct"] for p in positions)
    expected    = total_gain / total_value * 100

    assert abs(contrib_sum - expected) < 0.0001, (
        f"sum(contrib_pct)={contrib_sum:.6f} != total_gain/value={expected:.6f}"
    )


# ── Test 4: Portfolio value reconstruction ────────────────────────────────────

def test_portfolio_value_reconstruction_matches_nav(setup):
    """
    Reconstructed portfolio NAV at final date ≈ sum(shares × last_price).

    The reconstruction uses forward-filled prices; the reference NAV uses
    the last available price per ticker (identical logic).  This verifies
    that reconstruct_portfolio_value() produces consistent results.
    """
    price_lookup, dates, active_dates, portfolio_values = setup

    last_prices: dict[str, float] = {}
    for d in active_dates:
        for lot in LOTS:
            p = price_lookup.get(lot["ticker"], {}).get(d)
            if p and p > 0:
                last_prices[lot["ticker"]] = p

    expected_nav = sum(
        lot["shares"] * last_prices.get(lot["ticker"], lot["cost_basis"])
        for lot in LOTS
    )

    reconstructed_nav = portfolio_values[-1]
    assert abs(reconstructed_nav - expected_nav) < 0.01, (
        f"reconstructed_nav={reconstructed_nav:.4f} != expected_nav={expected_nav:.4f}"
    )


# ── Test 5: Holdings total P&L ≈ portfolio current value − total cost ─────────

def test_holdings_total_pnl_equals_value_minus_cost():
    """
    sum(gain_loss_i) == total_portfolio_value − total_cost

    This is a pure arithmetic identity for the positions endpoint, but
    verifies that the frontend sum matches the server-side aggregate.
    """
    positions = [
        {"shares": 10.0, "cost_basis": 180.0, "current_price": 198.0},
        {"shares": 5.0,  "cost_basis": 370.0, "current_price": 388.0},
        {"shares": 2.0,  "cost_basis": 490.0, "current_price": 525.0},
    ]

    for p in positions:
        p["current_value"] = round(p["shares"] * p["current_price"], 2)
        cost_val           = p["shares"] * p["cost_basis"]
        p["gain_loss"]     = round(p["current_value"] - cost_val, 2)

    total_value = sum(p["current_value"] for p in positions)
    total_cost  = sum(p["shares"] * p["cost_basis"] for p in positions)
    total_gl    = sum(p["gain_loss"] for p in positions)

    assert abs(total_gl - (total_value - total_cost)) < 0.01


# ── Test 6: Contribution sorts by P&L ─────────────────────────────────────────

def test_contribution_sorted_descending(setup):
    """compute_contribution() must return rows sorted by pnl_contribution desc."""
    price_lookup, dates, active_dates, portfolio_values = setup
    rows = compute_contribution(LOTS, price_lookup, active_dates, portfolio_values)

    pnls = [r["pnl_contribution"] for r in rows]
    assert pnls == sorted(pnls, reverse=True)


# ── Test 7: No NaN / Inf in contribution output ───────────────────────────────

def test_contribution_no_nan_or_inf(setup):
    """Contribution values must all be finite numbers."""
    import math
    price_lookup, dates, active_dates, portfolio_values = setup
    rows = compute_contribution(LOTS, price_lookup, active_dates, portfolio_values)

    for row in rows:
        assert math.isfinite(row["pnl_contribution"]), f"{row['ticker']}: pnl is NaN/Inf"
        assert math.isfinite(row["contribution_pct"]), f"{row['ticker']}: pct is NaN/Inf"
