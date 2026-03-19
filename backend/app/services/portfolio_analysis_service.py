"""
Portfolio Analysis Service — Phase 1 decision engine.

Provides three pure-computation functions plus an async orchestrator:

  compute_portfolio_health()          → 0–100 score across 5 dimensions
  generate_rebalancing_suggestions()  → explainable, data-driven actions
  cluster_portfolio()                 → correlation-based asset groupings
  run_portfolio_analysis()            → async orchestrator (I/O + coord)

All three computation functions are PURE (no I/O, no logging at call-time).
The async orchestrator handles data fetching and calls all three.

Performance target: <100ms for 20–30 assets on warm cache.
Correlation matrix: O(n²) — trivially fast at ≤30 assets.
"""
from __future__ import annotations

import asyncio
import logging
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone

import numpy as np

from app.services.data_reader import DataReader
from app.services.portfolio_analytics.portfolio_metrics import (
    compute_snapshot,
    build_price_lookup,
    align_series,
    reconstruct_portfolio_value,
    build_cash_flows,
    compute_twr_returns,
    cumulative_series,
    daily_returns,
    pearson_corr,
    RF_ANNUAL,
)

log = logging.getLogger(__name__)


# ── Configurable thresholds (data-driven, not hardcoded per-company) ──────────

WEIGHT_CONCENTRATION_THRESHOLD  = 0.25   # single position >25% = concentrated
SECTOR_CONCENTRATION_THRESHOLD  = 0.40   # single sector   >40% = imbalanced
CORRELATION_CLUSTER_THRESHOLD   = 0.70   # pairwise corr   >0.70 = same cluster
SHARPE_POOR_THRESHOLD           = 0.50   # Sharpe <0.50 = poor risk adjustment
VOLATILITY_HIGH_THRESHOLD       = 20.0   # annualized vol >20% = high
DRAWDOWN_SEVERE_THRESHOLD       = 25.0   # |max drawdown| >25% = severe
MIN_RETURNS_FOR_CORRELATION      = 20    # need ≥20 overlapping days

HEALTH_WEIGHTS = {
    "diversification":      0.25,
    "concentration":        0.20,
    "risk_adjusted_return": 0.25,
    "drawdown":             0.15,
    "correlation":          0.15,
}

ANALYSIS_CACHE_TTL = 900   # 15 minutes


# ─────────────────────────────────────────────────────────────────────────────
# PART 1 — Portfolio Health Score
# ─────────────────────────────────────────────────────────────────────────────

def _sector_weights(
    position_weights: dict[str, float],
    sector_map:       dict[str, str],
) -> dict[str, float]:
    """Aggregate position weights into sector weights (sum to 1)."""
    out: dict[str, float] = {}
    for ticker, w in position_weights.items():
        sec = sector_map.get(ticker, "Unknown")
        out[sec] = out.get(sec, 0.0) + w
    return out


def _diversification_score(
    position_weights: dict[str, float],
    sector_map:       dict[str, str],
) -> float:
    """
    Shannon entropy of sector distribution, normalized to [0, 100].

    H = −Σ p·log(p)   over sectors with p > 0
    score = H / H_max × 100    where H_max = log(n_sectors)
    """
    sw = _sector_weights(position_weights, sector_map)
    weights = [w for w in sw.values() if w > 1e-9]
    if len(weights) <= 1:
        return 0.0   # single sector → no diversification
    h     = -sum(w * math.log(w) for w in weights)
    h_max = math.log(len(weights))
    return round(h / h_max * 100, 2) if h_max > 0 else 0.0


def _concentration_score(position_weights: dict[str, float]) -> float:
    """
    HHI-based concentration score.

    HHI = Σ w_i²  (ranges 1/n → 1)
    score = (1 − HHI) / (1 − 1/n) × 100

    Perfectly split (1/n each) → 100.  Single position → 0.
    """
    n = len(position_weights)
    if n <= 1:
        return 0.0
    weights = list(position_weights.values())
    hhi      = sum(w ** 2 for w in weights)
    hhi_min  = 1.0 / n
    if (1.0 - hhi_min) < 1e-9:
        return 0.0
    return round(max(0.0, (1.0 - hhi) / (1.0 - hhi_min) * 100), 2)


def _sharpe_score(sharpe: float) -> float:
    """
    Piecewise-linear mapping from Sharpe ratio to [0, 100].

    ≤ −1 → 0,   0 → 30,   1 → 65,   2 → 85,   ≥ 3 → 100
    These breakpoints reflect empirical Sharpe distribution for diversified
    equity portfolios (RF = 2%).
    """
    BREAKPOINTS = [(-1.0, 0.0), (0.0, 30.0), (1.0, 65.0), (2.0, 85.0), (3.0, 100.0)]
    if sharpe <= BREAKPOINTS[0][0]:
        return BREAKPOINTS[0][1]
    if sharpe >= BREAKPOINTS[-1][0]:
        return BREAKPOINTS[-1][1]
    for i in range(1, len(BREAKPOINTS)):
        x0, y0 = BREAKPOINTS[i - 1]
        x1, y1 = BREAKPOINTS[i]
        if sharpe <= x1:
            t = (sharpe - x0) / (x1 - x0)
            return round(y0 + t * (y1 - y0), 2)
    return 0.0


def _drawdown_score(max_drawdown_pct: float) -> float:
    """
    Linear mapping |max_drawdown| → score.
    0% drawdown → 100.   50%+ drawdown → 0.
    max_drawdown_pct is expected as a NEGATIVE value (e.g. −15.3).
    """
    mdd = abs(max_drawdown_pct)   # now positive
    return round(max(0.0, 100.0 - mdd * 2.0), 2)


def _correlation_score(
    returns_matrix: dict[str, list[float]],
) -> tuple[float, float | None]:
    """
    Average pairwise Pearson correlation → score.

    Returns (score, avg_pairwise_corr).
    0 avg corr → 100.  1 avg corr → 0.
    Returns (50, None) if correlation cannot be computed (<2 tickers).
    """
    tickers = [t for t, r in returns_matrix.items() if len(r) >= MIN_RETURNS_FOR_CORRELATION]
    n = len(tickers)
    if n < 2:
        return 50.0, None

    min_len = min(len(returns_matrix[t]) for t in tickers)
    if min_len < MIN_RETURNS_FOR_CORRELATION:
        return 50.0, None

    data = np.array([returns_matrix[t][-min_len:] for t in tickers], dtype=np.float64)
    corr = np.corrcoef(data)

    # Average of upper triangle (excluding diagonal)
    upper_mask  = np.triu(np.ones((n, n), dtype=bool), k=1)
    corr_vals   = corr[upper_mask]
    valid        = corr_vals[~np.isnan(corr_vals)]
    if len(valid) == 0:
        return 50.0, None

    avg_corr = float(np.mean(valid))
    score    = round(max(0.0, (1.0 - avg_corr) * 100), 2)
    return score, round(avg_corr, 4)


def _health_grade(score: float) -> str:
    if score >= 80: return "A"
    if score >= 65: return "B"
    if score >= 50: return "C"
    if score >= 35: return "D"
    return "F"


def compute_portfolio_health(
    position_weights: dict[str, float],
    sector_map:       dict[str, str],
    returns_matrix:   dict[str, list[float]],
    risk_metrics:     dict,
) -> dict:
    """
    Compute a 0–100 portfolio health score across 5 dimensions.

    Args:
        position_weights : {ticker: market_value_weight}  (sum ≈ 1)
        sector_map       : {ticker: sector_name}
        returns_matrix   : {ticker: [daily returns]}
        risk_metrics     : output of compute_snapshot() — must include
                           sharpe, max_drawdown_pct, volatility_pct

    Returns dict compatible with HealthScore schema.
    """
    if not position_weights:
        return {
            "score": 0.0, "grade": "F",
            "breakdown": {k: 0.0 for k in HEALTH_WEIGHTS},
            "insights": ["Portfolio has no positions."],
        }

    d_score = _diversification_score(position_weights, sector_map)
    c_score = _concentration_score(position_weights)
    r_score = _sharpe_score(risk_metrics.get("sharpe", 0.0))
    dd_score = _drawdown_score(risk_metrics.get("max_drawdown_pct", 0.0))
    corr_score, avg_corr = _correlation_score(returns_matrix)

    breakdown = {
        "diversification":      d_score,
        "concentration":        c_score,
        "risk_adjusted_return": r_score,
        "drawdown":             dd_score,
        "correlation":          corr_score,
    }

    score = round(sum(
        HEALTH_WEIGHTS[k] * v for k, v in breakdown.items()
    ), 2)

    log.debug(
        "health_score: total=%.1f breakdown=%s",
        score, {k: round(v, 1) for k, v in breakdown.items()},
    )

    insights   = _health_insights(
        position_weights, sector_map, risk_metrics,
        breakdown, avg_corr,
    )
    top_issues = _top_issues(position_weights, sector_map, risk_metrics)

    return {
        "score":      score,
        "grade":      _health_grade(score),
        "breakdown":  breakdown,
        "insights":   insights,
        "top_issues": top_issues,
    }


def _health_insights(
    position_weights: dict[str, float],
    sector_map:       dict[str, str],
    risk_metrics:     dict,
    breakdown:        dict,
    avg_corr:         float | None,
) -> list[str]:
    msgs: list[str] = []

    # Diversification
    if breakdown["diversification"] < 30:
        sw = _sector_weights(position_weights, sector_map)
        dom = max(sw, key=lambda k: sw[k])
        msgs.append(
            f"Low sector diversification — {dom} accounts for "
            f"{sw[dom]*100:.0f}% of the portfolio."
        )
    elif breakdown["diversification"] >= 75:
        msgs.append("Good sector diversification across multiple sectors.")

    # Concentration
    max_w = max(position_weights.values())
    max_t = max(position_weights, key=lambda k: position_weights[k])
    if max_w > WEIGHT_CONCENTRATION_THRESHOLD:
        msgs.append(
            f"{max_t} represents {max_w*100:.1f}% of the portfolio — "
            f"single-stock concentration risk."
        )

    # Sharpe
    sharpe = risk_metrics.get("sharpe", 0.0)
    if sharpe < 0:
        msgs.append(f"Negative Sharpe ({sharpe:.2f}) — portfolio return is below the risk-free rate.")
    elif sharpe >= 1.5:
        msgs.append(f"Strong risk-adjusted returns (Sharpe {sharpe:.2f}).")

    # Drawdown
    mdd = abs(risk_metrics.get("max_drawdown_pct", 0.0))
    if mdd > DRAWDOWN_SEVERE_THRESHOLD:
        msgs.append(f"Significant maximum drawdown of −{mdd:.1f}% — elevated downside risk.")

    # Correlation
    if avg_corr is not None and avg_corr > 0.75:
        msgs.append(
            f"High average pairwise correlation ({avg_corr:.2f}) — assets tend to "
            f"move together, limiting true diversification."
        )
    elif avg_corr is not None and avg_corr < 0.30:
        msgs.append(
            f"Low average correlation ({avg_corr:.2f}) — good diversification across assets."
        )

    return msgs


def _top_issues(
    position_weights: dict[str, float],
    sector_map:       dict[str, str],
    risk_metrics:     dict,
) -> list[str]:
    """
    Up to 2 short, specific issue strings for the health card quick-view.
    Each item is a punchy single sentence naming the specific asset/sector
    and its percentage.
    """
    issues: list[str] = []

    # 1. Worst position concentration
    if position_weights:
        max_t = max(position_weights, key=lambda k: position_weights[k])
        max_w = position_weights[max_t]
        if max_w > WEIGHT_CONCENTRATION_THRESHOLD:
            issues.append(f"{max_t} overweight ({max_w*100:.0f}%)")

    # 2. Worst sector concentration
    sw = _sector_weights(position_weights, sector_map)
    if sw:
        max_sec = max(sw, key=lambda k: sw[k])
        max_sw  = sw[max_sec]
        if max_sw > SECTOR_CONCENTRATION_THRESHOLD and len(issues) < 2:
            issues.append(f"{max_sec} exposure too high ({max_sw*100:.0f}%)")

    # 3. Fallback: severe drawdown if still < 2 issues
    if len(issues) < 2:
        mdd = abs(risk_metrics.get("max_drawdown_pct", 0.0))
        if mdd > DRAWDOWN_SEVERE_THRESHOLD:
            issues.append(f"Max drawdown of −{mdd:.1f}%")

    # 4. Fallback: negative Sharpe
    if len(issues) < 2:
        sharpe = risk_metrics.get("sharpe", 0.0)
        if sharpe < 0:
            issues.append(f"Negative Sharpe ratio ({sharpe:.2f})")

    return issues[:2]


# ─────────────────────────────────────────────────────────────────────────────
# PART 2 — Rebalancing Suggestions
# ─────────────────────────────────────────────────────────────────────────────

def _raw_weighted_snapshot(
    position_weights: dict[str, float],
    returns_matrix:   dict[str, list[float]],
    spy_returns:      list[float],
) -> dict | None:
    """
    Compute a compute_snapshot() using raw per-ticker weighted daily returns.

    This is used for suggestion delta computation — both 'before' and 'after'
    snapshots use this method so the delta is internally consistent.
    Different from TWR (which is the primary display metric) but appropriate
    for relative comparisons.
    """
    active = [
        t for t in position_weights
        if t in returns_matrix and len(returns_matrix[t]) >= MIN_RETURNS_FOR_CORRELATION
    ]
    if not active:
        return None
    min_len = min(len(returns_matrix[t]) for t in active)
    if min_len < MIN_RETURNS_FOR_CORRELATION:
        return None
    total_w = sum(position_weights.get(t, 0.0) for t in active)
    if total_w <= 0:
        return None
    port_r = [
        sum((position_weights[t] / total_w) * returns_matrix[t][-min_len + i]
            for t in active)
        for i in range(min_len)
    ]
    port_v = cumulative_series(port_r)
    return compute_snapshot(port_r, port_v, spy_returns, label="raw_weighted")


def _apply_weight_change(
    position_weights: dict[str, float],
    action:           str,
    ticker:           str | None,
    sector:           str | None,
    sector_map:       dict[str, str],
) -> dict[str, float] | None:
    """
    Return a new weight dict reflecting the suggested change, or None if
    the change cannot be computed (e.g. "add" without a target ticker).

    Excess weight is redistributed proportionally across unchanged tickers.
    """
    new_w = dict(position_weights)
    n     = len(new_w)

    if action == "reduce" and ticker:
        old   = new_w.get(ticker, 0.0)
        target = min(WEIGHT_CONCENTRATION_THRESHOLD, 1.0 / max(n, 1))
        if old <= target:
            return None
        reduction = old - target
        new_w[ticker] = target
        others_total  = sum(v for t, v in position_weights.items() if t != ticker)
        if others_total > 0:
            for t in new_w:
                if t != ticker:
                    new_w[t] += reduction * (position_weights[t] / others_total)

    elif action == "reduce" and sector:
        sector_tickers = {t for t in position_weights if sector_map.get(t) == sector}
        total_sec      = sum(position_weights.get(t, 0.0) for t in sector_tickers)
        if total_sec <= SECTOR_CONCENTRATION_THRESHOLD:
            return None
        reduction = total_sec - SECTOR_CONCENTRATION_THRESHOLD
        factor    = SECTOR_CONCENTRATION_THRESHOLD / total_sec
        for t in sector_tickers:
            new_w[t] = position_weights[t] * factor
        others_total = sum(position_weights.get(t, 0.0) for t in position_weights
                           if t not in sector_tickers)
        if others_total > 0:
            for t in new_w:
                if t not in sector_tickers:
                    new_w[t] += reduction * (position_weights[t] / others_total)

    else:
        return None   # "add" without specific ticker — can't model

    return new_w


def _fmt_delta(diff: float, pct: bool = False) -> str:
    sign = "+" if diff >= 0 else ""
    return f"{sign}{diff:.1f}%" if pct else f"{sign}{diff:.2f}"


def _compute_suggestion_delta(
    action:           str,
    ticker:           str | None,
    sector:           str | None,
    position_weights: dict[str, float],
    sector_map:       dict[str, str],
    returns_matrix:   dict[str, list[float]],
    spy_returns:      list[float],
    before_snap:      dict,
) -> dict[str, str]:
    """
    Simulate the suggested weight change and return formatted metric deltas.

    Uses raw per-ticker weighted returns (not TWR) for both before and after
    so the delta is internally consistent.  Returns {} if not computable.
    """
    new_weights = _apply_weight_change(
        position_weights, action, ticker, sector, sector_map
    )
    if new_weights is None:
        return {}

    after_snap = _raw_weighted_snapshot(new_weights, returns_matrix, spy_returns)
    if after_snap is None:
        return {}

    delta: dict[str, str] = {}
    METRICS = [
        # (key,                  pct,   min_abs)
        ("sharpe",               False, 0.01),
        ("volatility_pct",       True,  0.1 ),
        ("max_drawdown_pct",     True,  0.1 ),
        ("annualized_return_pct",True,  0.1 ),
    ]
    for key, pct, min_abs in METRICS:
        b = before_snap.get(key) or 0.0
        a = after_snap.get(key)  or 0.0
        diff = a - b
        if abs(diff) >= min_abs:
            delta[key] = _fmt_delta(diff, pct=pct)

    return delta


def generate_rebalancing_suggestions(
    position_weights: dict[str, float],
    sector_map:       dict[str, str],
    risk_metrics:     dict,
    clusters:         list[dict],
    returns_matrix:   dict[str, list[float]] | None = None,
    spy_returns:      list[float] | None = None,
) -> list[dict]:
    """
    Generate explainable, data-driven rebalancing suggestions with
    quantified metric deltas.

    Rules applied (in priority order):
      1. Position concentration  (>WEIGHT_CONCENTRATION_THRESHOLD)
      2. Sector imbalance        (>SECTOR_CONCENTRATION_THRESHOLD)
      3. Risk/return inefficiency (low Sharpe + high vol)
      4. Cluster redundancy      (>2 tickers in one cluster)

    No tickers are hardcoded.  All thresholds are module-level constants.
    """
    suggestions: list[dict] = []
    n = len(position_weights)
    if n == 0:
        return suggestions

    sw = _sector_weights(position_weights, sector_map)

    # Pre-compute raw-weighted "before" snapshot once for all delta calcs
    _spy = spy_returns or []
    _rm  = returns_matrix or {}
    before_snap = _raw_weighted_snapshot(position_weights, _rm, _spy) if _rm else None

    def _delta(action: str, ticker: str | None, sector: str | None) -> dict[str, str] | None:
        if before_snap is None or not _rm:
            return None
        d = _compute_suggestion_delta(
            action, ticker, sector,
            position_weights, sector_map, _rm, _spy, before_snap,
        )
        return d if d else None

    # ── Rule 1: Position concentration ────────────────────────────────────────
    for ticker, w in sorted(position_weights.items(), key=lambda x: x[1], reverse=True):
        if w <= WEIGHT_CONCENTRATION_THRESHOLD:
            break
        target_w = min(WEIGHT_CONCENTRATION_THRESHOLD, 1.0 / n)
        suggestions.append({
            "action":        "reduce",
            "ticker":        ticker,
            "sector":        sector_map.get(ticker),
            "reason":        (
                f"{ticker} represents {w*100:.1f}% of the portfolio, above the "
                f"{WEIGHT_CONCENTRATION_THRESHOLD*100:.0f}% concentration threshold. "
                f"High single-stock weight amplifies idiosyncratic risk."
            ),
            "impact":        (
                f"Trimming to ~{target_w*100:.0f}% would reduce single-stock risk "
                f"and free capital for diversification."
            ),
            "priority":      "high" if w > 0.40 else "medium",
            "metrics_delta": _delta("reduce", ticker, None),
        })

    # ── Rule 2: Sector imbalance ───────────────────────────────────────────────
    for sector, sw_val in sorted(sw.items(), key=lambda x: x[1], reverse=True):
        if sw_val <= SECTOR_CONCENTRATION_THRESHOLD:
            break
        minor_sectors = [s for s, v in sw.items() if v < 0.05 and s != "Unknown"]
        suggestions.append({
            "action":        "reduce",
            "ticker":        None,
            "sector":        sector,
            "reason":        (
                f"{sector} accounts for {sw_val*100:.0f}% of the portfolio. "
                f"Sector over-concentration reduces protection against sector-specific downturns."
            ),
            "impact":        (
                (
                    f"Consider shifting some {sector} weight toward: "
                    f"{', '.join(minor_sectors[:3])}."
                )
                if minor_sectors else
                f"Reducing {sector} exposure below {SECTOR_CONCENTRATION_THRESHOLD*100:.0f}% "
                f"would improve sector balance."
            ),
            "priority":      "high" if sw_val > 0.60 else "medium",
            "metrics_delta": _delta("reduce", None, sector),
        })

    # ── Rule 3: Risk/return inefficiency ──────────────────────────────────────
    sharpe = risk_metrics.get("sharpe", 0.0)
    vol    = risk_metrics.get("volatility_pct", 0.0)
    if sharpe < SHARPE_POOR_THRESHOLD and vol > VOLATILITY_HIGH_THRESHOLD:
        suggestions.append({
            "action":        "add",
            "ticker":        None,
            "sector":        None,
            "reason":        (
                f"Portfolio has high volatility ({vol:.1f}% annualized) with a "
                f"poor Sharpe ratio ({sharpe:.2f}). Risk is not being adequately compensated."
            ),
            "impact":        (
                "Adding lower-volatility or negatively-correlated assets "
                "(e.g., fixed income, defensive sectors) could improve the Sharpe ratio "
                "without requiring higher returns."
            ),
            "priority":      "high" if sharpe < 0 else "medium",
            "metrics_delta": None,  # no specific ticker to model
        })

    # ── Rule 4: Cluster redundancy ────────────────────────────────────────────
    for cluster in clusters:
        assets   = cluster.get("assets", [])
        avg_corr = cluster.get("avg_correlation", 0.0)
        if len(assets) <= 2 or avg_corr < CORRELATION_CLUSTER_THRESHOLD:
            continue

        cluster_w  = sum(position_weights.get(t, 0.0) for t in assets)
        label      = cluster.get("label", "")
        by_weight  = sorted(assets, key=lambda t: position_weights.get(t, 0.0), reverse=True)
        keep, trim = by_weight[0], by_weight[1:]

        # Delta: simulate removing the smallest member and redistributing
        smallest = trim[-1] if trim else None
        suggestions.append({
            "action":        "reduce",
            "ticker":        smallest,
            "sector":        sector_map.get(assets[0]),
            "reason":        (
                f"{', '.join(assets)} are highly correlated "
                f"(avg ρ={avg_corr:.2f}{', ' + label if label else ''}). "
                f"Together they represent {cluster_w*100:.0f}% of the portfolio "
                f"but behave as a single position."
            ),
            "impact":        (
                f"Keeping {keep} (largest weight) and reducing "
                f"{', '.join(trim)} would maintain similar exposure "
                f"while freeing capital for diversification."
            ),
            "priority":      "medium",
            "metrics_delta": _delta("reduce", smallest, None) if smallest else None,
        })

    # Sort by priority and cap at 6
    suggestions = sorted(
        suggestions,
        key=lambda s: {"high": 0, "medium": 1, "low": 2}.get(s.get("priority", "low"), 2),
    )
    return suggestions[:6]


# ─────────────────────────────────────────────────────────────────────────────
# PART 3 — Correlation Clustering
# ─────────────────────────────────────────────────────────────────────────────

def _union_find_clusters(n: int, edges: list[tuple[int, int]]) -> list[list[int]]:
    """
    Union-Find (path-compressed) grouping of indices.
    Returns list of groups (each group = list of indices).
    O(n · α(n)) ≈ O(n).
    """
    parent = list(range(n))
    rank   = [0] * n

    def find(x: int) -> int:
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def union(x: int, y: int) -> None:
        px, py = find(x), find(y)
        if px == py:
            return
        if rank[px] < rank[py]:
            px, py = py, px
        parent[py] = px
        if rank[px] == rank[py]:
            rank[px] += 1

    for i, j in edges:
        union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        root = find(i)
        groups.setdefault(root, []).append(i)
    return list(groups.values())


def _cluster_label(assets: list[str], sector_map: dict[str, str], cluster_id: int) -> str:
    """
    Label a cluster by its dominant sector.
    Falls back to "Cluster N" when sector data is absent or mixed.
    """
    sectors = [sector_map.get(t, "Unknown") for t in assets]
    counts  = Counter(s for s in sectors if s != "Unknown")
    if not counts:
        return f"Cluster {cluster_id}"
    dominant, count = counts.most_common(1)[0]
    if count >= math.ceil(len(assets) * 0.5):
        return f"{dominant}"
    return f"Cluster {cluster_id}"


def cluster_portfolio(
    returns_matrix: dict[str, list[float]],
    sector_map:     dict[str, str],
    threshold:      float = CORRELATION_CLUSTER_THRESHOLD,
) -> list[dict]:
    """
    Group assets with pairwise correlation > threshold into clusters.

    Algorithm: correlation matrix → edges above threshold → Union-Find.

    Returns list of cluster dicts sorted by avg_correlation descending.
    Each asset appears in exactly one cluster.
    """
    tickers = [t for t, r in returns_matrix.items() if len(r) >= MIN_RETURNS_FOR_CORRELATION]
    n       = len(tickers)

    if n == 0:
        return []

    # ── Correlation matrix ─────────────────────────────────────────────────
    min_len = min(len(returns_matrix[t]) for t in tickers)

    # Not enough overlapping history → no meaningful clusters
    if min_len < MIN_RETURNS_FOR_CORRELATION:
        return []

    data = np.array(
        [returns_matrix[t][-min_len:] for t in tickers],
        dtype=np.float64,
    )
    corr = np.corrcoef(data)

    # ── Build edges (pairs above threshold) ───────────────────────────────
    edges: list[tuple[int, int]] = []
    for i in range(n):
        for j in range(i + 1, n):
            c = corr[i, j]
            if np.isfinite(c) and c > threshold:
                edges.append((i, j))

    # ── Cluster via Union-Find ─────────────────────────────────────────────
    groups   = _union_find_clusters(n, edges)
    clusters = []
    cid      = 0

    for group_indices in sorted(groups, key=len, reverse=True):
        # CRITICAL: skip single-asset groups — not a meaningful cluster
        if len(group_indices) < 2:
            continue

        assets = [tickers[i] for i in group_indices]

        # Average pairwise correlation within the cluster
        pairs = [
            corr[group_indices[ii], group_indices[jj]]
            for ii in range(len(group_indices))
            for jj in range(ii + 1, len(group_indices))
            if np.isfinite(corr[group_indices[ii], group_indices[jj]])
        ]
        avg_c = round(float(np.mean(pairs)) if pairs else 0.0, 4)

        label   = _cluster_label(assets, sector_map, cid + 1)
        insight = (
            f"{', '.join(assets)} are highly correlated (avg ρ={avg_c:.2f}) "
            f"and behave like a single position in {label}."
        )

        clusters.append({
            "cluster_id":      cid,
            "assets":          assets,
            "avg_correlation": avg_c,
            "label":           label,
            "insight":         insight,
        })
        cid += 1

    # Sort by avg_correlation descending (highest risk first)
    return sorted(clusters, key=lambda c: c["avg_correlation"], reverse=True)


# ─────────────────────────────────────────────────────────────────────────────
# PART 4 — Async orchestrator
# ─────────────────────────────────────────────────────────────────────────────

def _positions_to_lots(positions: list) -> list[dict]:
    lots = []
    for pos in positions:
        opened = pos.opened_at
        lots.append({
            "ticker":         pos.ticker,
            "shares":         float(pos.shares),
            "cost_basis":     float(pos.cost_basis),
            "opened_at_date": opened.date().isoformat()
                              if hasattr(opened, "date") else str(opened)[:10],
        })
    return lots


async def run_portfolio_analysis(
    positions: list,
    reader:    DataReader,
    cache,
    portfolio_id: str,
    force:        bool = False,
) -> dict:
    """
    Async orchestrator.  Fetches data, runs all three analysis functions.

    Cached at ANALYSIS_CACHE_TTL (15 min) keyed by portfolio_id.
    Returns dict compatible with PortfolioAnalysisResponse schema.
    """
    import json as _json

    cache_key = f"portfolio_analysis:{portfolio_id}"
    if not force:
        cached = await cache.get(cache_key)
        if cached:
            return _json.loads(cached)

    lots             = _positions_to_lots(positions)
    existing_tickers = list({lot["ticker"] for lot in lots})

    # ── Read data from cache (no external API calls) ───────────────────────────
    async def _hist(t: str):
        data = await reader.get_price_history(t, period="1y", interval="1d")
        return t, data or []

    async def _sector(t: str) -> tuple[str, str | None]:
        try:
            facts = await reader.get_company_facts(t)
            sec   = ((facts or {}).get("company_facts") or {}).get("sector")
            return t, sec
        except Exception:
            return t, None

    hist_results, sector_results, prices = await asyncio.gather(
        asyncio.gather(*[_hist(t) for t in existing_tickers + ["SPY"]]),
        asyncio.gather(*[_sector(t) for t in existing_tickers]),
        reader.get_prices_bulk(existing_tickers),
    )

    histories  = {t: d for t, d in hist_results if d}
    sector_map = {t: s for t, s in sector_results if s}

    # ── Position market-value weights ─────────────────────────────────────────
    mv = {
        pos.ticker: float(pos.shares) * prices.get(pos.ticker, {}).get(
            "price", float(pos.cost_basis)
        )
        for pos in positions
    }
    total_mv         = sum(mv.values()) or 1.0
    position_weights = {t: v / total_mv for t, v in mv.items()}

    # ── TWR return series for risk metrics + per-ticker returns ───────────────
    ref    = "SPY" if "SPY" in histories else (existing_tickers[0] if existing_tickers else None)
    if not ref or ref not in histories:
        return _empty_analysis(portfolio_id)

    price_lookup                    = build_price_lookup(histories)
    dates, aligned                  = align_series(histories, ref_ticker=ref)
    active_dates, portfolio_values  = reconstruct_portfolio_value(price_lookup, lots, dates)

    if not portfolio_values:
        return _empty_analysis(portfolio_id)

    cash_flows   = build_cash_flows(lots, active_dates)
    port_returns = compute_twr_returns(portfolio_values, active_dates, cash_flows)
    # NaN filter — mirrors compute_engine() so metrics are consistent
    _raw  = np.asarray(port_returns, dtype=np.float64)
    _mask = ~np.isnan(_raw)
    port_returns = _raw[_mask].tolist()
    return_dates: list[str] = [
        d for d, m in zip(active_dates[1:], _mask.tolist()) if m
    ]
    port_values  = cumulative_series(port_returns)

    if len(port_returns) < 5:
        return _empty_analysis(portfolio_id)

    # SPY returns — date-aligned via date→return map (same as compute_engine)
    spy_d2c     = price_lookup.get("SPY", {})
    _last_spy:  float | None = None
    spy_prices: list[float]  = []
    spy_pdates: list[str]    = []
    for d in active_dates:
        p = spy_d2c.get(d)
        if p and p > 0:
            _last_spy = p
        if _last_spy is not None:
            spy_prices.append(_last_spy)
            spy_pdates.append(d)
    spy_d2r: dict[str, float] = {}
    for i in range(1, len(spy_prices)):
        if spy_prices[i - 1] > 0:
            spy_d2r[spy_pdates[i]] = spy_prices[i] / spy_prices[i - 1] - 1.0
    # Intersect portfolio return dates with SPY return dates
    port_for_spy: list[float] = []
    spy_aligned:  list[float] = []
    for d, pr in zip(return_dates, port_returns):
        if d in spy_d2r:
            port_for_spy.append(pr)
            spy_aligned.append(spy_d2r[d])
    spy_returns = spy_aligned

    risk_metrics = compute_snapshot(
        port_returns, port_values, spy_aligned,
        label="analysis", port_for_spy=port_for_spy,
    )

    # Per-ticker daily returns aligned to active_dates (for correlation)
    returns_matrix: dict[str, list[float]] = {}
    for ticker in existing_tickers:
        d2c    = price_lookup.get(ticker, {})
        closes = [d2c[d] for d in active_dates if d in d2c and d2c[d] > 0]
        if len(closes) >= 2:
            returns_matrix[ticker] = daily_returns(closes)

    # ── Run all three analysis functions ──────────────────────────────────────
    clusters    = cluster_portfolio(returns_matrix, sector_map)
    health      = compute_portfolio_health(
        position_weights, sector_map, returns_matrix, risk_metrics
    )
    suggestions = generate_rebalancing_suggestions(
        position_weights, sector_map, risk_metrics, clusters,
        returns_matrix=returns_matrix,
        spy_returns=spy_returns,
    )

    result = {
        "portfolio_id": portfolio_id,
        "computed_at":  datetime.now(timezone.utc).isoformat(),
        "health":       health,
        "suggestions":  suggestions,
        "clusters":     clusters,
    }

    await cache.set(cache_key, _json.dumps(result, default=str), ANALYSIS_CACHE_TTL)
    return result


def _empty_analysis(portfolio_id: str) -> dict:
    return {
        "portfolio_id": portfolio_id,
        "computed_at":  datetime.now(timezone.utc).isoformat(),
        "health": {
            "score": 0.0, "grade": "F",
            "breakdown": {k: 0.0 for k in HEALTH_WEIGHTS},
            "insights":   ["Insufficient data to compute portfolio health."],
            "top_issues": [],
        },
        "suggestions": [],
        "clusters":    [],
    }
