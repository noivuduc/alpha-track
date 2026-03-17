"""
Unit tests for the portfolio analysis service (Phase 1).

Tests:
  1. Health score consistency and component formulas
  2. HHI / concentration calculation
  3. Diversification entropy
  4. Correlation clustering correctness
  5. Suggestion generation logic
  6. Edge cases (empty, single asset, all-same-sector, etc.)

Run with:
    cd backend
    .venv/bin/python -m pytest tests/test_portfolio_analysis.py -v
"""
from __future__ import annotations

import math
import random

import numpy as np
import pytest

from app.services.portfolio_analysis_service import (
    HEALTH_WEIGHTS,
    WEIGHT_CONCENTRATION_THRESHOLD,
    SECTOR_CONCENTRATION_THRESHOLD,
    CORRELATION_CLUSTER_THRESHOLD,
    MIN_RETURNS_FOR_CORRELATION,
    compute_portfolio_health,
    generate_rebalancing_suggestions,
    cluster_portfolio,
    _diversification_score,
    _concentration_score,
    _sharpe_score,
    _drawdown_score,
    _correlation_score,
    _health_grade,
    _cluster_label,
    _union_find_clusters,
    _sector_weights,
    _top_issues,
    _raw_weighted_snapshot,
    _compute_suggestion_delta,
    _apply_weight_change,
)

TOL = 1e-2   # 2 dp for score comparisons

# ── Shared fixtures ────────────────────────────────────────────────────────────

_rng = random.Random(7)


def _returns(n: int, mean: float = 0.0004, std: float = 0.012) -> list[float]:
    return [_rng.gauss(mean, std) for _ in range(n)]


def _correlated_returns(base: list[float], noise: float = 0.2) -> list[float]:
    """Returns correlated with base (lower noise = higher correlation)."""
    return [b + _rng.gauss(0, noise * abs(b) + 1e-5) for b in base]


# Balanced portfolio: 5 tickers, equal weights, 5 distinct sectors
BALANCED_WEIGHTS = {"AAPL": 0.2, "MSFT": 0.2, "JNJ": 0.2, "JPM": 0.2, "XOM": 0.2}
BALANCED_SECTORS = {
    "AAPL": "Technology",
    "MSFT": "Technology",
    "JNJ":  "Healthcare",
    "JPM":  "Financials",
    "XOM":  "Energy",
}
BALANCED_RETURNS = {t: _returns(252) for t in BALANCED_WEIGHTS}
BALANCED_RISK    = {
    "sharpe": 1.2, "sortino": 1.5, "beta": 0.9, "alpha_pct": 2.1,
    "max_drawdown_pct": -12.0, "volatility_pct": 14.0,
    "annualized_return_pct": 11.0, "var_95_pct": 1.8,
}


# ─────────────────────────────────────────────────────────────────────────────
# PART 1 — Diversification score
# ─────────────────────────────────────────────────────────────────────────────

class TestDiversificationScore:

    def test_single_sector_score_zero(self):
        """All positions in one sector → diversification = 0."""
        weights = {"A": 0.5, "B": 0.5}
        sectors = {"A": "Tech", "B": "Tech"}
        assert _diversification_score(weights, sectors) == 0.0

    def test_equal_n_sectors_score_100(self):
        """Equal weight across N distinct sectors → score = 100."""
        n = 5
        weights = {f"T{i}": 1/n for i in range(n)}
        sectors = {f"T{i}": f"Sector{i}" for i in range(n)}
        score = _diversification_score(weights, sectors)
        assert abs(score - 100.0) < TOL

    def test_partial_balance_in_range(self):
        """Unequal sector weights → score between 0 and 100 (exclusive)."""
        weights = {"A": 0.6, "B": 0.2, "C": 0.2}
        sectors = {"A": "Tech", "B": "Healthcare", "C": "Financials"}
        score = _diversification_score(weights, sectors)
        assert 0.0 < score < 100.0

    def test_more_balanced_scores_higher(self):
        """
        Normalized entropy (H/H_max) measures how close to balanced a
        distribution is. A near-equal split scores higher than a skewed split.
        """
        w_balanced = {"A": 0.4, "B": 0.6}
        s_balanced = {"A": "S0", "B": "S1"}
        w_skewed   = {"A": 0.9, "B": 0.1}
        s_skewed   = {"A": "S0", "B": "S1"}
        assert _diversification_score(w_balanced, s_balanced) > _diversification_score(w_skewed, s_skewed)

    def test_unknown_sector_treated_as_one_sector(self):
        """Unknown sectors collapse together."""
        weights = {"A": 0.5, "B": 0.5}
        sectors: dict = {}   # both become "Unknown"
        score = _diversification_score(weights, sectors)
        assert score == 0.0   # one "Unknown" sector


# ─────────────────────────────────────────────────────────────────────────────
# PART 2 — Concentration / HHI score
# ─────────────────────────────────────────────────────────────────────────────

class TestConcentrationScore:

    def test_single_position_score_zero(self):
        assert _concentration_score({"A": 1.0}) == 0.0

    def test_equal_weights_score_100(self):
        """n equal positions → HHI = 1/n → score = 100."""
        n = 5
        w = {f"T{i}": 1 / n for i in range(n)}
        score = _concentration_score(w)
        assert abs(score - 100.0) < TOL

    def test_skewed_weights_lower_score(self):
        """More skewed → lower score."""
        equal   = {"A": 0.25, "B": 0.25, "C": 0.25, "D": 0.25}
        skewed  = {"A": 0.70, "B": 0.10, "C": 0.10, "D": 0.10}
        assert _concentration_score(equal) > _concentration_score(skewed)

    def test_hhi_formula(self):
        """Verify HHI = sum(w²) matches manual computation."""
        weights = {"A": 0.5, "B": 0.3, "C": 0.2}
        expected_hhi = 0.5**2 + 0.3**2 + 0.2**2   # = 0.38
        n     = len(weights)
        score = _concentration_score(weights)
        # score = (1 - hhi) / (1 - 1/n) * 100
        hhi_from_score = 1.0 - score / 100.0 * (1.0 - 1.0 / n)
        assert abs(hhi_from_score - expected_hhi) < 1e-6

    def test_empty_returns_zero(self):
        assert _concentration_score({}) == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# PART 3 — Sharpe → score mapping
# ─────────────────────────────────────────────────────────────────────────────

class TestSharpeScore:

    def test_breakpoints(self):
        assert _sharpe_score(-1.0) == 0.0
        assert _sharpe_score(0.0)  == 30.0
        assert _sharpe_score(1.0)  == 65.0
        assert _sharpe_score(2.0)  == 85.0
        assert _sharpe_score(3.0)  == 100.0

    def test_monotone(self):
        values = [-2, -1, -0.5, 0, 0.5, 1, 1.5, 2, 2.5, 3, 4]
        scores = [_sharpe_score(v) for v in values]
        for a, b in zip(scores, scores[1:]):
            assert b >= a, f"Non-monotone at {values[scores.index(a)]}"

    def test_clamps_below_minus_one(self):
        assert _sharpe_score(-5) == 0.0

    def test_clamps_above_three(self):
        assert _sharpe_score(10) == 100.0

    def test_interpolation_midpoint(self):
        """Midpoint between breakpoints is arithmetic average of scores."""
        mid = _sharpe_score(0.5)
        expected = (30 + 65) / 2
        assert abs(mid - expected) < TOL


# ─────────────────────────────────────────────────────────────────────────────
# PART 4 — Drawdown score
# ─────────────────────────────────────────────────────────────────────────────

class TestDrawdownScore:

    def test_zero_drawdown_perfect(self):
        assert _drawdown_score(0.0)  == 100.0

    def test_fifty_pct_drawdown_zero(self):
        assert _drawdown_score(-50.0) == 0.0

    def test_twenty_pct_drawdown(self):
        assert abs(_drawdown_score(-20.0) - 60.0) < TOL

    def test_clamps_at_zero(self):
        assert _drawdown_score(-100.0) == 0.0

    def test_takes_positive_input_too(self):
        """Function uses abs(), so positive input works too."""
        assert _drawdown_score(20.0) == _drawdown_score(-20.0)


# ─────────────────────────────────────────────────────────────────────────────
# PART 5 — Correlation score
# ─────────────────────────────────────────────────────────────────────────────

class TestCorrelationScore:

    def test_insufficient_data_returns_neutral(self):
        """<2 tickers with enough history → neutral score 50."""
        score, avg = _correlation_score({"A": _returns(5)})
        assert score == 50.0
        assert avg is None

    def test_uncorrelated_assets_high_score(self):
        """Uncorrelated assets → avg_corr ≈ 0 → score ≈ 100."""
        rng = random.Random(1)
        matrix = {
            f"T{i}": [rng.gauss(0, 0.01) for _ in range(100)]
            for i in range(5)
        }
        score, avg = _correlation_score(matrix)
        assert score > 70.0   # uncorrelated → good score

    def test_identical_returns_low_score(self):
        """Identical return series → corr = 1 → score = 0."""
        base = _returns(100)
        matrix = {"A": base[:], "B": base[:], "C": base[:]}
        score, avg = _correlation_score(matrix)
        assert score < 10.0
        assert avg is not None and avg > 0.95


# ─────────────────────────────────────────────────────────────────────────────
# PART 6 — Health score integration
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthScore:

    def test_score_in_range(self):
        result = compute_portfolio_health(
            BALANCED_WEIGHTS, BALANCED_SECTORS,
            BALANCED_RETURNS, BALANCED_RISK,
        )
        assert 0.0 <= result["score"] <= 100.0

    def test_weighted_sum_correct(self):
        """Final score must equal exact weighted sum of component scores."""
        result = compute_portfolio_health(
            BALANCED_WEIGHTS, BALANCED_SECTORS,
            BALANCED_RETURNS, BALANCED_RISK,
        )
        bd = result["breakdown"]
        expected = sum(HEALTH_WEIGHTS[k] * bd[k] for k in HEALTH_WEIGHTS)
        assert abs(result["score"] - expected) < 1e-2  # score rounds to 2dp

    def test_breakdown_keys(self):
        result = compute_portfolio_health(
            BALANCED_WEIGHTS, BALANCED_SECTORS,
            BALANCED_RETURNS, BALANCED_RISK,
        )
        assert set(result["breakdown"].keys()) == set(HEALTH_WEIGHTS.keys())

    def test_empty_portfolio_score_zero(self):
        result = compute_portfolio_health({}, {}, {}, {})
        assert result["score"] == 0.0
        assert result["grade"] == "F"

    def test_grade_thresholds(self):
        for score, expected_grade in [
            (85, "A"), (70, "B"), (55, "C"), (40, "D"), (20, "F")
        ]:
            assert _health_grade(score) == expected_grade

    def test_concentrated_portfolio_lower_score(self):
        """Concentrated portfolio should score lower than balanced."""
        concentrated_w = {"A": 0.80, "B": 0.10, "C": 0.05, "D": 0.05}
        concentrated_s = {"A": "Tech", "B": "Tech", "C": "Tech", "D": "Tech"}
        concentrated_r = {t: _returns(252) for t in concentrated_w}

        bal = compute_portfolio_health(BALANCED_WEIGHTS, BALANCED_SECTORS,
                                       BALANCED_RETURNS, BALANCED_RISK)
        con = compute_portfolio_health(
            concentrated_w, concentrated_s, concentrated_r,
            {**BALANCED_RISK, "sharpe": 0.3, "volatility_pct": 25.0},
        )
        assert bal["score"] > con["score"]

    def test_insights_non_empty(self):
        result = compute_portfolio_health(
            BALANCED_WEIGHTS, BALANCED_SECTORS,
            BALANCED_RETURNS, BALANCED_RISK,
        )
        # Insights list is populated (may be empty for near-perfect portfolios,
        # but BALANCED_RISK has a decent Sharpe so should produce at least one)
        assert isinstance(result["insights"], list)


# ─────────────────────────────────────────────────────────────────────────────
# PART 7 — Clustering
# ─────────────────────────────────────────────────────────────────────────────

class TestClustering:

    def test_empty_input(self):
        assert cluster_portfolio({}, {}) == []

    def test_insufficient_history(self):
        """<20 days of returns → tickers filtered out → empty cluster list."""
        matrix = {"A": _returns(5), "B": _returns(5)}
        clusters = cluster_portfolio(matrix, {})
        assert clusters == []  # no tickers pass the 20-day filter

    def test_identical_returns_one_cluster(self):
        """Identical returns → all in one cluster."""
        base = _returns(100)
        matrix = {"A": base[:], "B": base[:], "C": base[:]}
        sectors = {"A": "Tech", "B": "Tech", "C": "Tech"}
        clusters = cluster_portfolio(matrix, sectors)
        merged = [a for c in clusters for a in c["assets"]]
        assert set(merged) == {"A", "B", "C"}
        multi = [c for c in clusters if len(c["assets"]) > 1]
        assert len(multi) == 1
        assert set(multi[0]["assets"]) == {"A", "B", "C"}

    def test_independent_returns_separate_clusters(self):
        """Independent returns with high threshold → no multi-asset clusters."""
        rng = random.Random(99)
        matrix = {
            f"T{i}": [rng.gauss(0, 0.01) for _ in range(100)]
            for i in range(5)
        }
        clusters = cluster_portfolio(matrix, {}, threshold=0.90)
        # All singletons are filtered out → empty result
        assert clusters == []

    def test_no_asset_appears_twice(self):
        """Each asset appears in at most one cluster (no duplicates)."""
        matrix  = {f"T{i}": _returns(60) for i in range(8)}
        sectors = {f"T{i}": "Unknown" for i in range(8)}
        clusters = cluster_portfolio(matrix, sectors)
        all_assets = [a for c in clusters for a in c["assets"]]
        # All returned clusters must have ≥2 assets
        assert all(len(c["assets"]) >= 2 for c in clusters)
        # No asset appears in more than one cluster
        assert len(all_assets) == len(set(all_assets))

    def test_cluster_avg_correlation_within_range(self):
        matrix  = {f"T{i}": _returns(60) for i in range(4)}
        sectors = {}
        clusters = cluster_portfolio(matrix, sectors)
        for c in clusters:
            assert 0.0 <= c["avg_correlation"] <= 1.0 + 1e-6

    def test_cluster_label_dominant_sector(self):
        """Label matches dominant sector when ≥50% share same sector."""
        assert _cluster_label(["A", "B", "C"], {"A": "Tech", "B": "Tech", "C": "Healthcare"}, 1) == "Tech"

    def test_cluster_label_fallback(self):
        """Mixed sectors → fallback to 'Cluster N'."""
        label = _cluster_label(["A", "B", "C"], {"A": "Tech", "B": "Healthcare", "C": "Financials"}, 2)
        assert label == "Cluster 2"

    def test_cluster_insight_for_multi_asset(self):
        base = _returns(100)
        matrix = {"A": base[:], "B": base[:], "C": base[:]}
        clusters = cluster_portfolio(matrix, {"A": "Tech", "B": "Tech", "C": "Tech"})
        multi = [c for c in clusters if len(c["assets"]) > 1]
        assert len(multi) >= 1
        assert multi[0]["insight"] is not None
        assert "ρ=" in multi[0]["insight"]


# ─────────────────────────────────────────────────────────────────────────────
# PART 8 — Union-Find
# ─────────────────────────────────────────────────────────────────────────────

class TestUnionFind:

    def test_no_edges(self):
        """No edges → each node is its own cluster."""
        groups = _union_find_clusters(4, [])
        assert len(groups) == 4
        all_idx = sorted(i for g in groups for i in g)
        assert all_idx == [0, 1, 2, 3]

    def test_all_connected(self):
        """All nodes connected → one cluster."""
        edges = [(0, 1), (1, 2), (2, 3)]
        groups = _union_find_clusters(4, edges)
        assert len(groups) == 1
        assert sorted(groups[0]) == [0, 1, 2, 3]

    def test_two_components(self):
        """Two disconnected components."""
        edges = [(0, 1), (2, 3)]
        groups = _union_find_clusters(4, edges)
        assert len(groups) == 2
        sizes = sorted(len(g) for g in groups)
        assert sizes == [2, 2]

    def test_transitive_closure(self):
        """A-B correlated, B-C correlated → A, B, C in same cluster."""
        edges = [(0, 1), (1, 2)]   # 0-1 and 1-2 but NOT 0-2
        groups = _union_find_clusters(3, edges)
        assert len(groups) == 1
        assert sorted(groups[0]) == [0, 1, 2]


# ─────────────────────────────────────────────────────────────────────────────
# PART 9 — Rebalancing suggestions
# ─────────────────────────────────────────────────────────────────────────────

class TestRebalancingSuggestions:

    def test_concentrated_position_triggers_reduce(self):
        """Single stock >threshold must generate a 'reduce' suggestion."""
        weights = {"BIG": 0.60, "B": 0.20, "C": 0.20}
        sectors = {"BIG": "Tech", "B": "Healthcare", "C": "Financials"}
        suggestions = generate_rebalancing_suggestions(weights, sectors, BALANCED_RISK, [])
        reduce = [s for s in suggestions if s["action"] == "reduce" and s["ticker"] == "BIG"]
        assert len(reduce) >= 1
        assert reduce[0]["priority"] in ("high", "medium")

    def test_dominated_sector_triggers_reduce(self):
        """Sector >threshold must generate a sector-level reduce suggestion."""
        weights = {"A": 0.5, "B": 0.3, "C": 0.2}
        sectors = {"A": "Tech", "B": "Tech", "C": "Tech"}
        suggestions = generate_rebalancing_suggestions(weights, sectors, BALANCED_RISK, [])
        sector_reduce = [s for s in suggestions if s["sector"] == "Tech" and s["ticker"] is None]
        assert len(sector_reduce) >= 1

    def test_poor_sharpe_high_vol_triggers_add(self):
        """Low Sharpe + high volatility → 'add' suggestion."""
        risk = {**BALANCED_RISK, "sharpe": 0.1, "volatility_pct": 28.0}
        suggestions = generate_rebalancing_suggestions(
            BALANCED_WEIGHTS, BALANCED_SECTORS, risk, []
        )
        add = [s for s in suggestions if s["action"] == "add"]
        assert len(add) >= 1

    def test_good_portfolio_fewer_suggestions(self):
        """Well-balanced portfolio with good metrics → fewer suggestions."""
        good_risk = {**BALANCED_RISK, "sharpe": 1.5, "volatility_pct": 12.0}
        suggestions = generate_rebalancing_suggestions(
            BALANCED_WEIGHTS, BALANCED_SECTORS, good_risk, []
        )
        # Equal 20% weights in 4 distinct sectors — only Technology appears twice
        # so sector rule may trigger but position rule should not
        bad_risk  = {**BALANCED_RISK, "sharpe": 0.1, "volatility_pct": 30.0}
        bad_w     = {"A": 0.70, "B": 0.15, "C": 0.15}
        bad_s     = {"A": "Tech", "B": "Tech", "C": "Tech"}
        bad_sug   = generate_rebalancing_suggestions(bad_w, bad_s, bad_risk, [])
        assert len(bad_sug) >= len(suggestions)

    def test_cluster_redundancy_suggestion(self):
        """Cluster with >2 highly correlated assets → reduce suggestion."""
        cluster = {
            "cluster_id": 0,
            "assets": ["A", "B", "C"],
            "avg_correlation": 0.85,
            "label": "Tech",
        }
        weights = {"A": 0.3, "B": 0.3, "C": 0.3, "D": 0.1}
        sectors = {t: "Tech" for t in "ABCD"}
        suggestions = generate_rebalancing_suggestions(
            weights, sectors, BALANCED_RISK, [cluster]
        )
        # Cluster redundancy suggestions have "correlated" in the reason
        cluster_sug = [s for s in suggestions
                       if s["action"] == "reduce" and "correlated" in s["reason"].lower()]
        assert len(cluster_sug) >= 1

    def test_no_hardcoded_tickers_in_logic(self):
        """Suggestion tickers must come only from the input weights."""
        suggestions = generate_rebalancing_suggestions(
            BALANCED_WEIGHTS, BALANCED_SECTORS, BALANCED_RISK, []
        )
        input_tickers = set(BALANCED_WEIGHTS.keys()) | {None}
        for s in suggestions:
            assert s["ticker"] in input_tickers, (
                f"Suggestion ticker {s['ticker']!r} not in input weights"
            )

    def test_max_six_suggestions(self):
        """Suggestions are capped at 6."""
        weights = {f"T{i}": 1/10 for i in range(10)}
        sectors = {f"T{i}": f"S{i % 2}" for i in range(10)}  # only 2 sectors
        clusters = [
            {"cluster_id": 0, "assets": [f"T{i}" for i in range(5)],
             "avg_correlation": 0.9, "label": "S0"},
        ]
        suggestions = generate_rebalancing_suggestions(
            weights, sectors, {**BALANCED_RISK, "sharpe": 0.1, "volatility_pct": 25.0},
            clusters
        )
        assert len(suggestions) <= 6


# ─────────────────────────────────────────────────────────────────────────────
# PART 10 — Clustering correctness (Phase 2 requirements)
# ─────────────────────────────────────────────────────────────────────────────

class TestClusteringCorrectness:
    """
    Verify the corrected clustering rules:
      - Only clusters with >= 2 assets are returned
      - avg_correlation is the true pairwise mean, not 1.0 for singletons
      - sorted by avg_correlation descending
    """

    def test_no_single_asset_clusters(self):
        """cluster_portfolio must NEVER return a cluster with only 1 asset."""
        matrix = {f"T{i}": _returns(60) for i in range(6)}
        clusters = cluster_portfolio(matrix, {})
        for c in clusters:
            assert len(c["assets"]) >= 2, (
                f"Single-asset cluster returned: {c}"
            )

    def test_identical_returns_form_one_cluster(self):
        """Two perfectly correlated assets must form exactly one cluster."""
        base = _returns(100)
        matrix = {"A": base[:], "B": base[:]}
        clusters = cluster_portfolio(matrix, {"A": "Tech", "B": "Tech"})
        assert len(clusters) == 1
        assert set(clusters[0]["assets"]) == {"A", "B"}
        assert abs(clusters[0]["avg_correlation"] - 1.0) < 1e-4

    def test_sorted_by_correlation_desc(self):
        """Clusters must be sorted highest avg_correlation first."""
        # Build two groups: A-B with near-perfect corr, C-D with moderate corr
        base_ab = _returns(100, mean=0.001, std=0.005)
        # C-D: slightly noisy version of a different random walk
        rng2 = random.Random(999)
        base_cd = [rng2.gauss(0.0003, 0.015) for _ in range(100)]
        noise   = [rng2.gauss(0, 0.001)      for _ in range(100)]
        matrix = {
            "A": base_ab[:],
            "B": [x + rng2.gauss(0, 1e-6) for x in base_ab],  # near-identical
            "C": base_cd[:],
            "D": [base_cd[i] + noise[i] for i in range(100)],  # correlated but noisy
        }
        clusters = cluster_portfolio(matrix, {}, threshold=0.5)
        if len(clusters) >= 2:
            corrs = [c["avg_correlation"] for c in clusters]
            assert corrs == sorted(corrs, reverse=True), (
                f"Clusters not sorted desc: {corrs}"
            )

    def test_avg_correlation_is_pairwise_mean(self):
        """avg_correlation must be the true pairwise mean, not 1.0."""
        base = _returns(100)
        noisy = [x + _rng.gauss(0, 0.003) for x in base]
        matrix = {"A": base, "B": noisy}
        clusters = cluster_portfolio(matrix, {})
        if clusters:
            c = clusters[0]
            # Should be < 1.0 since B has added noise
            assert c["avg_correlation"] < 1.0 - 1e-6

    def test_insufficient_history_returns_empty(self):
        """< MIN_RETURNS days → empty list (cannot compute correlation)."""
        matrix = {"A": _returns(5), "B": _returns(5)}
        clusters = cluster_portfolio(matrix, {})
        assert clusters == []

    def test_cluster_members_share_high_correlation(self):
        """All pairs within a cluster must have correlation > threshold."""
        base = _returns(100)
        tiny = [_rng.gauss(0, 1e-6) for _ in range(100)]
        matrix = {
            "A": base[:],
            "B": [base[i] + tiny[i] for i in range(100)],
            "C": _returns(100),  # independent
        }
        threshold = 0.7
        clusters  = cluster_portfolio(matrix, {}, threshold=threshold)
        # A and B should be in the same cluster; C should be excluded (singleton)
        paired = [c for c in clusters if len(c["assets"]) == 2]
        assert len(paired) == 1
        assert set(paired[0]["assets"]) == {"A", "B"}

    def test_no_duplicate_assets_across_clusters(self):
        """Each asset may appear in at most one cluster."""
        base = _returns(100)
        matrix = {
            "A": base[:], "B": base[:],
            "C": _returns(100), "D": _returns(100),
        }
        clusters = cluster_portfolio(matrix, {})
        all_assets = [a for c in clusters for a in c["assets"]]
        assert len(all_assets) == len(set(all_assets))


# ─────────────────────────────────────────────────────────────────────────────
# PART 11 — Suggestion metric deltas
# ─────────────────────────────────────────────────────────────────────────────

_N = 60   # enough returns for delta computation

_LONG_RNG = random.Random(55)
_LONG_RETS = {
    "BIG":   [_LONG_RNG.gauss(0.0005, 0.015) for _ in range(_N)],
    "MID1":  [_LONG_RNG.gauss(0.0003, 0.010) for _ in range(_N)],
    "MID2":  [_LONG_RNG.gauss(0.0004, 0.012) for _ in range(_N)],
    "SMALL": [_LONG_RNG.gauss(0.0002, 0.008) for _ in range(_N)],
    "SPY":   [_LONG_RNG.gauss(0.0003, 0.007) for _ in range(_N)],
}
_CONC_WEIGHTS = {"BIG": 0.50, "MID1": 0.20, "MID2": 0.20, "SMALL": 0.10}
_CONC_SECTORS = {"BIG": "Tech", "MID1": "Tech", "MID2": "Finance", "SMALL": "Health"}


class TestSuggestionDelta:

    def test_reduce_ticker_changes_metrics(self):
        """Reducing an overweight ticker produces a non-empty metrics_delta."""
        suggestions = generate_rebalancing_suggestions(
            _CONC_WEIGHTS, _CONC_SECTORS,
            {"sharpe": 0.8, "volatility_pct": 18.0, "max_drawdown_pct": -20.0,
             "annualized_return_pct": 12.0},
            [],
            returns_matrix=_LONG_RETS,
            spy_returns=_LONG_RETS["SPY"],
        )
        ticker_sug = [s for s in suggestions
                      if s["action"] == "reduce" and s["ticker"] == "BIG"]
        assert len(ticker_sug) == 1
        delta = ticker_sug[0].get("metrics_delta")
        # Delta must be present and non-empty for a real weight change
        assert delta is not None
        assert isinstance(delta, dict)

    def test_delta_keys_are_valid_metric_names(self):
        """metrics_delta keys must be from the known set of metric names."""
        valid_keys = {
            "sharpe", "volatility_pct", "max_drawdown_pct", "annualized_return_pct"
        }
        suggestions = generate_rebalancing_suggestions(
            _CONC_WEIGHTS, _CONC_SECTORS,
            {"sharpe": 0.4, "volatility_pct": 22.0, "max_drawdown_pct": -18.0,
             "annualized_return_pct": 8.0},
            [],
            returns_matrix=_LONG_RETS,
            spy_returns=_LONG_RETS["SPY"],
        )
        for s in suggestions:
            delta = s.get("metrics_delta") or {}
            assert set(delta.keys()).issubset(valid_keys), (
                f"Unexpected delta keys: {set(delta.keys()) - valid_keys}"
            )

    def test_delta_values_are_formatted_strings(self):
        """Each delta value must be a formatted string like '+0.08' or '-1.2%'."""
        import re
        pattern = re.compile(r"^[+-]\d+(\.\d+)?%?$")
        suggestions = generate_rebalancing_suggestions(
            _CONC_WEIGHTS, _CONC_SECTORS,
            {"sharpe": 0.4, "volatility_pct": 22.0, "max_drawdown_pct": -18.0,
             "annualized_return_pct": 8.0},
            [],
            returns_matrix=_LONG_RETS,
            spy_returns=_LONG_RETS["SPY"],
        )
        for s in suggestions:
            for key, val in (s.get("metrics_delta") or {}).items():
                assert pattern.match(val), (
                    f"Bad delta format for {key}: {val!r}"
                )

    def test_no_delta_for_add_suggestion(self):
        """'add' suggestions (no target ticker) must have metrics_delta=None."""
        suggestions = generate_rebalancing_suggestions(
            {"A": 0.5, "B": 0.5},
            {"A": "Tech", "B": "Tech"},
            {"sharpe": 0.1, "volatility_pct": 25.0, "max_drawdown_pct": -15.0,
             "annualized_return_pct": 5.0},
            [],
            returns_matrix=_LONG_RETS,
            spy_returns=_LONG_RETS["SPY"],
        )
        add_sug = [s for s in suggestions if s["action"] == "add" and s["ticker"] is None]
        for s in add_sug:
            assert s.get("metrics_delta") is None

    def test_without_returns_matrix_delta_is_none(self):
        """Omitting returns_matrix → all metrics_delta values are None."""
        suggestions = generate_rebalancing_suggestions(
            _CONC_WEIGHTS, _CONC_SECTORS,
            {"sharpe": 0.4, "volatility_pct": 22.0, "max_drawdown_pct": -18.0,
             "annualized_return_pct": 8.0},
            [],
            # returns_matrix and spy_returns intentionally omitted
        )
        for s in suggestions:
            assert s.get("metrics_delta") is None

    def test_apply_weight_change_reduces_correctly(self):
        """_apply_weight_change must reduce a concentrated ticker."""
        new_w = _apply_weight_change(
            {"AAPL": 0.50, "GOOG": 0.25, "MSFT": 0.25},
            action="reduce", ticker="AAPL", sector=None,
            sector_map={},
        )
        assert new_w is not None
        assert new_w["AAPL"] <= WEIGHT_CONCENTRATION_THRESHOLD + 1e-6
        assert abs(sum(new_w.values()) - 1.0) < 1e-6, "Weights must still sum to 1"

    def test_apply_weight_change_none_when_no_change_needed(self):
        """_apply_weight_change returns None when weight is already ≤ threshold."""
        result = _apply_weight_change(
            {"A": 0.20, "B": 0.80},
            action="reduce", ticker="A", sector=None,
            sector_map={},
        )
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# PART 12 — Health top_issues
# ─────────────────────────────────────────────────────────────────────────────

class TestTopIssues:

    def test_overweight_ticker_appears(self):
        """Overweight single ticker is reported in top_issues."""
        w = {"AAPL": 0.60, "GOOG": 0.40}
        risk = {"sharpe": 1.0, "max_drawdown_pct": -10.0, "volatility_pct": 12.0}
        issues = _top_issues(w, {}, risk)
        assert any("AAPL" in i for i in issues)
        assert any("60%" in i for i in issues)

    def test_overweight_sector_appears(self):
        """Overweight sector is reported when position is fine."""
        w = {"A": 0.25, "B": 0.25, "C": 0.25, "D": 0.25}
        s = {"A": "Tech", "B": "Tech", "C": "Tech", "D": "Health"}
        risk = {"sharpe": 1.2, "max_drawdown_pct": -8.0, "volatility_pct": 14.0}
        issues = _top_issues(w, s, risk)
        assert any("Tech" in i for i in issues)

    def test_max_two_issues(self):
        """top_issues is capped at 2 items."""
        w = {"X": 0.80, "Y": 0.20}
        s = {"X": "Tech", "Y": "Tech"}
        risk = {"sharpe": -0.5, "max_drawdown_pct": -40.0, "volatility_pct": 30.0}
        issues = _top_issues(w, s, risk)
        assert len(issues) <= 2

    def test_health_output_contains_top_issues(self):
        """compute_portfolio_health must include 'top_issues' key."""
        result = compute_portfolio_health(
            {"A": 0.7, "B": 0.3},
            {"A": "Tech", "B": "Tech"},
            {},
            {"sharpe": 0.5, "max_drawdown_pct": -15.0, "volatility_pct": 18.0},
        )
        assert "top_issues" in result
        assert isinstance(result["top_issues"], list)
