"""
Stock-level Sentiment Regime / Fear & Greed signal.

Design contract:
  - Deterministic: same inputs → same output, always
  - Explainable: every threshold is documented, every driver is traceable
  - No LLMs, no Tavily, no paid APIs
  - Returns structured dict per output contract; never raises

Score 0–100:  0 = Extreme Fear  …  100 = Extreme Greed

4-Component model
─────────────────
  momentum           (weight 30%)  trend strength and relative leadership
  volatility_stress  (weight 30%)  disorder, fear, realized vol
  positioning        (weight 25%)  overextension, crowding, washed-out conditions
  expectation_pressure (weight 15%) valuation premium, earnings bar

Normalization method: bounded linear mapping
  score = clamp(value, lo, hi) / (hi - lo) * 100
  Documented below for every sub-factor.

Version: v1
"""
from __future__ import annotations

import math
from typing import Optional

VERSION = "v1"
MIN_BARS_REQUIRED = 65   # ~3 months of trading days (needed for 3M return & MAs)


# ── Low-level math helpers ────────────────────────────────────────────────────

def _safe(val) -> Optional[float]:
    """Return float(val) or None if missing / non-finite."""
    if val is None:
        return None
    try:
        f = float(val)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return None


def _score_bounded(
    value: float,
    lo: float,
    hi: float,
    invert: bool = False,
) -> float:
    """
    Map `value` linearly to [0, 100] using [lo, hi] as bounds.

    Normalization formula:
        score = (clamp(value, lo, hi) - lo) / (hi - lo) * 100

    invert=True flips the mapping so high input → low score.
    Used when high value means more fear (e.g. high vol, deep drawdown, high short%).
    """
    if hi == lo:
        return 50.0
    clamped = max(lo, min(hi, value))
    raw = (clamped - lo) / (hi - lo) * 100.0
    return 100.0 - raw if invert else raw


def _avg(scores: list[Optional[float]]) -> Optional[float]:
    valid = [s for s in scores if s is not None]
    return sum(valid) / len(valid) if valid else None


# ── Price series helpers ──────────────────────────────────────────────────────

def _get_closes(bars: list[dict]) -> list[float]:
    """
    Extract close prices sorted chronologically from history bars.
    Each bar: {ts: ISO str, close: float, ...}
    """
    sorted_bars = sorted(bars, key=lambda b: b.get("ts", ""))
    result: list[float] = []
    for b in sorted_bars:
        c = _safe(b.get("close"))
        if c is not None and c > 0:
            result.append(c)
    return result


def _return_n_days(closes: list[float], n: int) -> Optional[float]:
    """
    (closes[-1] / closes[-n-1]) - 1, or None if fewer than n+1 bars available.
    Uses simple total return over n trading days.
    """
    if len(closes) < n + 1:
        return None
    base = closes[-n - 1]
    return closes[-1] / base - 1.0 if base > 0 else None


def _realized_vol_annualized(closes: list[float], window: int = 20) -> Optional[float]:
    """
    Compute annualized realized volatility from the last `window` log-returns.
    Uses population std-dev (not sample), consistent with market convention.

    Annualization factor: sqrt(252).
    """
    if len(closes) < window + 1:
        return None
    log_returns = [
        math.log(closes[i] / closes[i - 1])
        for i in range(len(closes) - window, len(closes))
        if closes[i - 1] > 0 and closes[i] > 0
    ]
    if len(log_returns) < 5:
        return None
    mean = sum(log_returns) / len(log_returns)
    variance = sum((r - mean) ** 2 for r in log_returns) / len(log_returns)
    return math.sqrt(variance * 252)


def _vol_1y_median(closes: list[float]) -> Optional[float]:
    """
    Compute median 20D rolling volatility over the past year.
    Used as baseline for the vol-regime ratio.
    Returns None if fewer than 40 bars.
    """
    if len(closes) < 40:
        return None
    vols: list[float] = []
    for i in range(20, len(closes) + 1):
        v = _realized_vol_annualized(closes[max(0, i - 21): i], 20)
        if v is not None:
            vols.append(v)
    if not vols:
        return None
    return sorted(vols)[len(vols) // 2]


def _moving_average(closes: list[float], n: int) -> Optional[float]:
    """Simple N-period moving average of the most recent `n` closes."""
    if len(closes) < n:
        return None
    return sum(closes[-n:]) / n


def _rsi(closes: list[float], period: int = 14) -> Optional[float]:
    """
    Classic Wilder RSI (smoothed moving average, not EMA).
    Uses the last `period+1` closes. Returns None if not enough data.

    Formula:
        RS = avg_gain / avg_loss  (over `period` changes)
        RSI = 100 - 100 / (1 + RS)
    """
    if len(closes) < period + 1:
        return None
    gains: list[float] = []
    losses: list[float] = []
    start = max(0, len(closes) - period - 1)
    for i in range(start + 1, start + period + 1):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_gain == 0 and avg_loss == 0:
        return 50.0   # Truly flat prices → neutral RSI
    if avg_loss == 0:
        return 100.0
    return 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))


def _drawdown_from_high(closes: list[float], lookback: int = 252) -> Optional[float]:
    """
    (current_price / max_price_in_lookback) - 1.
    Returns a non-positive value: e.g. -0.15 = 15% below recent peak.
    Returns None if closes is empty.
    """
    window = closes[-lookback:] if closes else []
    if not window:
        return None
    peak = max(window)
    if peak <= 0:
        return None
    return closes[-1] / peak - 1.0


# ── Component 1: Momentum (weight 30%) ───────────────────────────────────────
#
# Sub-factor normalization thresholds (all in %)
# ┌───────────────────────┬─────────────┬─────────────┬────────┐
# │ Sub-factor            │ lo (Fear)   │ hi (Greed)  │ Notes  │
# ├───────────────────────┼─────────────┼─────────────┼────────┤
# │ 1M return             │   -15%      │    +20%     │ ~1 SD  │
# │ 3M return             │   -25%      │    +35%     │ ~1 SD  │
# │ 3M relative vs SPY    │   -15%      │    +20%     │        │
# └───────────────────────┴─────────────┴─────────────┴────────┘

def compute_momentum_component(
    closes: list[float],
    spy_closes: list[float],
) -> tuple[Optional[float], list[tuple[str, float]]]:
    """
    Returns (score 0–100 | None, list of (factor_key, raw_value)).
    raw_value stores the un-normalised input for driver generation.
    """
    sub_scores: list[Optional[float]] = []
    raw: list[tuple[str, float]] = []

    ret_1m = _return_n_days(closes, 21)
    if ret_1m is not None:
        sub_scores.append(_score_bounded(ret_1m * 100, -15.0, 20.0))
        raw.append(("1m_return", ret_1m))

    ret_3m = _return_n_days(closes, 63)
    if ret_3m is not None:
        sub_scores.append(_score_bounded(ret_3m * 100, -25.0, 35.0))
        raw.append(("3m_return", ret_3m))

    spy_3m = _return_n_days(spy_closes, 63) if len(spy_closes) >= 64 else None
    if ret_3m is not None and spy_3m is not None:
        relative = ret_3m - spy_3m
        sub_scores.append(_score_bounded(relative * 100, -15.0, 20.0))
        raw.append(("3m_vs_spy", relative))

    return _avg(sub_scores), raw


# ── Component 2: Volatility / Stress (weight 30%) ────────────────────────────
#
# All sub-factors are INVERTED: high stress → low score (fear)
# ┌───────────────────────────┬─────────────┬─────────────┬─────────────────────┐
# │ Sub-factor                │ lo (Greed)  │ hi (Fear)   │ Notes               │
# ├───────────────────────────┼─────────────┼─────────────┼─────────────────────┤
# │ 20D realized vol (ann)    │   10%       │    60%      │ low vol = calm       │
# │ Vol regime ratio          │   0.5×      │    2.5×     │ spike = stress       │
# │ Drawdown from 52W high    │    0%       │   -50%      │ deep DD = fear       │
# └───────────────────────────┴─────────────┴─────────────┴─────────────────────┘

def compute_volatility_stress_component(
    closes: list[float],
) -> tuple[Optional[float], list[tuple[str, float]]]:
    sub_scores: list[Optional[float]] = []
    raw: list[tuple[str, float]] = []

    vol_20d = _realized_vol_annualized(closes, 20)
    if vol_20d is not None:
        # Inverted: high vol = fear = low score
        sub_scores.append(_score_bounded(vol_20d * 100, 10.0, 60.0, invert=True))
        raw.append(("vol_20d", vol_20d))

    vol_median = _vol_1y_median(closes)
    if vol_20d is not None and vol_median is not None and vol_median > 0:
        regime_ratio = vol_20d / vol_median
        # Inverted: vol spike vs baseline = fear
        sub_scores.append(_score_bounded(regime_ratio, 0.5, 2.5, invert=True))
        raw.append(("vol_regime_ratio", regime_ratio))

    dd = _drawdown_from_high(closes, 252)
    if dd is not None:
        # dd is negative; map [-50%, 0%] → [0, 100] (deep dd = fear = low score)
        sub_scores.append(_score_bounded(dd * 100, -50.0, 0.0))
        raw.append(("drawdown_52w", dd))

    return _avg(sub_scores), raw


# ── Component 3: Positioning / Stretch (weight 25%) ──────────────────────────
#
# ┌───────────────────────┬─────────────┬─────────────┬────────────────────────┐
# │ Sub-factor            │ lo (Fear)   │ hi (Greed)  │ Notes                  │
# ├───────────────────────┼─────────────┼─────────────┼────────────────────────┤
# │ % above 50D MA        │   -15%      │    +20%     │ above = stretched      │
# │ % above 200D MA       │   -20%      │    +25%     │ above = stretched      │
# │ RSI(14)               │    25       │     75      │ direct 0–100 mapping   │
# │ Short interest        │     0%      │    20%      │ INVERTED: high = fear  │
# └───────────────────────┴─────────────┴─────────────┴────────────────────────┘

def compute_positioning_component(
    closes: list[float],
    short_pct_float: Optional[float] = None,
) -> tuple[Optional[float], list[tuple[str, float]]]:
    sub_scores: list[Optional[float]] = []
    raw: list[tuple[str, float]] = []

    ma50 = _moving_average(closes, 50)
    if ma50 is not None and ma50 > 0:
        dist_50 = closes[-1] / ma50 - 1.0
        sub_scores.append(_score_bounded(dist_50 * 100, -15.0, 20.0))
        raw.append(("dist_50d_ma", dist_50))

    ma200 = _moving_average(closes, 200)
    if ma200 is not None and ma200 > 0:
        dist_200 = closes[-1] / ma200 - 1.0
        sub_scores.append(_score_bounded(dist_200 * 100, -20.0, 25.0))
        raw.append(("dist_200d_ma", dist_200))

    rsi_val = _rsi(closes, 14)
    if rsi_val is not None:
        sub_scores.append(_score_bounded(rsi_val, 25.0, 75.0))
        raw.append(("rsi_14", rsi_val))

    if short_pct_float is not None:
        # Inverted: high short interest = bearish positioning = lower score
        sub_scores.append(_score_bounded(short_pct_float * 100, 0.0, 20.0, invert=True))
        raw.append(("short_pct_float", short_pct_float))

    return _avg(sub_scores), raw


# ── Component 4: Expectation Pressure (weight 15%) ───────────────────────────
#
# ┌──────────────────────────────┬───────────┬───────────┬──────────────────────┐
# │ Sub-factor                   │ lo (Fear) │ hi (Greed)│ Notes                │
# ├──────────────────────────────┼───────────┼───────────┼──────────────────────┤
# │ Fwd P/E premium vs own hist  │  -30%     │   +50%    │ above history = greed│
# │ Earnings surprise streak     │   -3      │    +3     │ beats = greed        │
# │ Estimate revision (EPS %)    │  -20%     │   +20%    │ upward = greed       │
# └──────────────────────────────┴───────────┴───────────┴──────────────────────┘

def compute_expectation_pressure_component(
    profile: dict,
    valuation: dict,
    earnings_history: list[dict],
    estimates_annual: list[dict],
) -> tuple[Optional[float], list[tuple[str, float]]]:
    sub_scores: list[Optional[float]] = []
    raw: list[tuple[str, float]] = []

    # Forward P/E premium vs own historical P/E median
    forward_pe = _safe(profile.get("forward_pe"))
    pe_hist = valuation.get("pe_history") or []
    if forward_pe and forward_pe > 0 and pe_hist:
        hist_pes = [_safe(r.get("pe")) for r in pe_hist]
        hist_pes = [v for v in hist_pes if v and v > 0]
        if hist_pes:
            median_pe = sorted(hist_pes)[len(hist_pes) // 2]
            if median_pe > 0:
                premium = (forward_pe - median_pe) / median_pe
                sub_scores.append(_score_bounded(premium * 100, -30.0, 50.0))
                raw.append(("fwd_pe_premium_vs_history", premium))

    # Earnings beat/miss streak
    # Count consecutive beats or misses from the most recent quarter
    if earnings_history:
        surprises = [_safe(e.get("surprise_pct")) for e in earnings_history[-6:]]
        surprises = [s for s in surprises if s is not None]
        if surprises:
            # Positive streak: consecutive beats counted from most recent
            beat_streak = 0
            for s in reversed(surprises):
                if s > 0:
                    beat_streak += 1
                else:
                    break
            # Negative streak: consecutive misses
            miss_streak = 0
            for s in reversed(surprises):
                if s < 0:
                    miss_streak -= 1
                else:
                    break
            streak = beat_streak if beat_streak > 0 else miss_streak
            sub_scores.append(_score_bounded(float(streak), -3.0, 3.0))
            raw.append(("earnings_surprise_streak", float(streak)))

    # Estimate revision: latest EPS estimate vs prior period
    if len(estimates_annual) >= 2:
        r_eps = _safe(estimates_annual[0].get("earnings_per_share"))
        o_eps = _safe(estimates_annual[1].get("earnings_per_share"))
        if r_eps is not None and o_eps is not None and o_eps != 0:
            revision = (r_eps - o_eps) / abs(o_eps)
            sub_scores.append(_score_bounded(revision * 100, -20.0, 20.0))
            raw.append(("eps_revision_pct", revision))

    return _avg(sub_scores), raw


# ── Driver / Warning text generation ─────────────────────────────────────────
# Rules:
#   - Deterministic: same raw inputs → same text
#   - Human-readable, factual, non-advisory
#   - Drivers: positive contributors to greed reading
#   - Warnings: risk signals or extensions that may reverse

def _generate_drivers_warnings(
    momentum_raw:    list[tuple[str, float]],
    volatility_raw:  list[tuple[str, float]],
    positioning_raw: list[tuple[str, float]],
    expectation_raw: list[tuple[str, float]],
) -> tuple[list[str], list[str]]:
    drivers: list[str] = []
    warnings: list[str] = []

    # Build lookup
    raw: dict[str, float] = {}
    for key, val in momentum_raw + volatility_raw + positioning_raw + expectation_raw:
        raw[key] = val

    # ── Momentum ─────────────────────────────────────────────────────────────
    ret_3m = raw.get("3m_return")
    vs_spy  = raw.get("3m_vs_spy")
    ret_1m  = raw.get("1m_return")

    if ret_3m is not None:
        if ret_3m > 0.10:
            drivers.append(f"Up {ret_3m*100:.1f}% over 3 months")
        elif ret_3m < -0.12:
            warnings.append(f"Down {abs(ret_3m)*100:.1f}% over 3 months")

    if vs_spy is not None:
        if vs_spy > 0.05:
            drivers.append(f"Outperformed SPY by {vs_spy*100:.1f}% over 3 months")
        elif vs_spy < -0.07:
            warnings.append(f"Underperformed SPY by {abs(vs_spy)*100:.1f}% over 3 months")

    # ── Volatility / Stress ───────────────────────────────────────────────────
    vol_20d       = raw.get("vol_20d")
    vol_regime    = raw.get("vol_regime_ratio")
    dd            = raw.get("drawdown_52w")

    if vol_20d is not None:
        if vol_20d > 0.40:
            warnings.append(f"Realized volatility elevated at {vol_20d*100:.0f}% annualized")
        elif vol_20d < 0.18:
            drivers.append(f"Low realized volatility ({vol_20d*100:.0f}%) — calm price environment")

    if vol_regime is not None and vol_regime > 1.8:
        warnings.append(f"Volatility {vol_regime:.1f}× above 1-year median")

    if dd is not None:
        if dd < -0.20:
            warnings.append(f"Trading {abs(dd)*100:.0f}% below 52-week high")
        elif dd > -0.05:
            drivers.append(f"Near 52-week high ({abs(dd)*100:.1f}% below peak)")

    # ── Positioning ───────────────────────────────────────────────────────────
    dist_200 = raw.get("dist_200d_ma")
    dist_50  = raw.get("dist_50d_ma")
    rsi_val  = raw.get("rsi_14")
    short    = raw.get("short_pct_float")

    if dist_200 is not None:
        if dist_200 > 0.10:
            drivers.append(f"Trading {dist_200*100:.1f}% above 200D moving average")
        elif dist_200 < -0.10:
            warnings.append(f"Trading {abs(dist_200)*100:.1f}% below 200D moving average")

    if rsi_val is not None:
        if rsi_val > 65:
            warnings.append(f"RSI at {rsi_val:.0f} — momentum extended")
        elif rsi_val < 35:
            drivers.append(f"RSI at {rsi_val:.0f} — potentially oversold")

    if short is not None:
        if short > 0.10:
            warnings.append(f"{short*100:.0f}% short interest — elevated bearish positioning")
        elif short < 0.03:
            drivers.append(f"Low short interest ({short*100:.0f}%) — limited bearish conviction")

    # ── Expectation ───────────────────────────────────────────────────────────
    fwd_pe_prem = raw.get("fwd_pe_premium_vs_history")
    streak      = raw.get("earnings_surprise_streak")

    if fwd_pe_prem is not None:
        if fwd_pe_prem > 0.20:
            warnings.append(f"Forward valuation {fwd_pe_prem*100:.0f}% above historical median P/E")
        elif fwd_pe_prem < -0.15:
            drivers.append(f"Forward valuation {abs(fwd_pe_prem)*100:.0f}% below historical median P/E")

    if streak is not None:
        if streak >= 3:
            drivers.append(f"Beat earnings estimates {int(streak)} consecutive quarter(s)")
        elif streak <= -2:
            warnings.append(f"Missed earnings estimates {int(abs(streak))} consecutive quarter(s)")

    return drivers[:3], warnings[:2]


# ── Main entry point ──────────────────────────────────────────────────────────

def compute_sentiment_regime(
    price_bars:       list[dict],
    spy_bars:         list[dict],
    profile:          dict,
    valuation:        dict,
    earnings_history: list[dict],
    estimates_annual: list[dict],
) -> dict:
    """
    Compute the stock-level sentiment regime score.

    Parameters
    ----------
    price_bars       : OHLCV bars for the target ticker [{ts, close, ...}]
    spy_bars         : OHLCV bars for SPY [{ts, close, ...}]
    profile          : company profile dict (forward_pe, short_pct_float, ...)
    valuation        : valuation dict (pe_history list)
    earnings_history : EarningsRecord list (surprise_pct)
    estimates_annual : AnalystEstimate list (earnings_per_share, by period asc)

    Returns
    -------
    Structured dict per output contract. Never raises.
    """
    closes     = _get_closes(price_bars)  if price_bars  else []
    spy_closes = _get_closes(spy_bars)    if spy_bars    else []

    _INSUF = {
        "score": None, "label": "Insufficient data", "type": "Computed",
        "drivers": [], "warnings": [], "components": {},
        "meta": {"version": VERSION, "inputs_available": False, "missing": ["price_history"]},
    }

    if len(closes) < MIN_BARS_REQUIRED:
        return _INSUF

    short_pct = _safe(profile.get("short_pct_float"))

    # ── Compute components ────────────────────────────────────────────────────
    momentum_score,    momentum_raw    = compute_momentum_component(closes, spy_closes)
    volatility_score,  volatility_raw  = compute_volatility_stress_component(closes)
    positioning_score, positioning_raw = compute_positioning_component(closes, short_pct)
    expectation_score, expectation_raw = compute_expectation_pressure_component(
        profile, valuation, earnings_history, estimates_annual,
    )

    # ── Weighted average (re-normalise for missing components) ────────────────
    weighted_pairs = [
        (momentum_score,    0.30),
        (volatility_score,  0.30),
        (positioning_score, 0.25),
        (expectation_score, 0.15),
    ]
    available = [(v, w) for v, w in weighted_pairs if v is not None]
    if not available:
        return {**_INSUF, "meta": {**_INSUF["meta"], "missing": ["all_components"]}}

    total_w     = sum(w for _, w in available)
    final_score = round(sum(v * w / total_w for v, w in available))
    final_score = max(0, min(100, final_score))

    if final_score <= 20:   label = "Extreme Fear"
    elif final_score <= 40: label = "Fear"
    elif final_score <= 60: label = "Neutral"
    elif final_score <= 80: label = "Greed"
    else:                   label = "Extreme Greed"

    # ── Drivers & warnings ────────────────────────────────────────────────────
    drivers, warnings = _generate_drivers_warnings(
        momentum_raw, volatility_raw, positioning_raw, expectation_raw,
    )

    # ── Metadata ──────────────────────────────────────────────────────────────
    missing: list[str] = []
    if len(spy_closes) < 64:
        missing.append("spy_benchmark")
    if short_pct is None:
        missing.append("short_interest")
    if not earnings_history:
        missing.append("earnings_history")
    if not estimates_annual:
        missing.append("analyst_estimates")

    return {
        "score":   final_score,
        "label":   label,
        "type":    "Computed",
        "drivers": drivers,
        "warnings":warnings,
        "components": {
            "momentum":             round(momentum_score)    if momentum_score    is not None else None,
            "volatility_stress":    round(volatility_score)  if volatility_score  is not None else None,
            "positioning":          round(positioning_score) if positioning_score is not None else None,
            "expectation_pressure": round(expectation_score) if expectation_score is not None else None,
        },
        "meta": {
            "version":          VERSION,
            "inputs_available": True,
            "missing":          missing,
        },
    }
