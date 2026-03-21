"""
Deterministic analysis layer for the Research Overview tab.

Computes pillars, risk flags, sentiment regime, and data coverage
from the assembled research response — no external API calls, no LLM.
All outputs carry source_type = "Computed".

Scoring philosophy:
- Each metric is mapped to a 0–100 bounded score using documented thresholds.
- Scores are averaged across available inputs; missing data is excluded, not penalised.
- Components with no inputs return None, not 0.
"""
from __future__ import annotations
import math
from typing import Optional
from app.services.research.sentiment_regime import compute_sentiment_regime


# ── Low-level helpers ─────────────────────────────────────────────────────────

def _safe(val, fallback=None):
    """Return val if it is a usable number, else fallback."""
    if val is None:
        return fallback
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return fallback
    try:
        return float(val)
    except (TypeError, ValueError):
        return fallback


def _pct(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v * 100:.1f}%"


def _mult(v: Optional[float], decimals: int = 1) -> str:
    if v is None:
        return "—"
    return f"{v:.{decimals}f}x"


def _score_bounded(value: float, lo: float, hi: float, invert: bool = False) -> float:
    """Map value linearly into [0, 100] using [lo, hi] as bounds."""
    if hi == lo:
        return 50.0
    clamped = max(lo, min(hi, value))
    score = (clamped - lo) / (hi - lo) * 100.0
    return 100.0 - score if invert else score


def _avg(scores: list[float]) -> Optional[float]:
    return sum(scores) / len(scores) if scores else None


# ── Pillar: Valuation ─────────────────────────────────────────────────────────

def _valuation_pillar(data: dict) -> dict:
    m = (data.get("metrics") or {}).get("snapshot") or {}
    p = (data.get("overview") or {}).get("profile") or {}

    pe          = _safe(m.get("price_to_earnings_ratio") or p.get("pe_ratio"))
    forward_pe  = _safe(p.get("forward_pe"))
    ev_ebitda   = _safe(m.get("enterprise_value_to_ebitda_ratio") or p.get("ev_ebitda"))
    peg         = _safe(m.get("peg_ratio") or p.get("peg_ratio"))
    fcf_yield   = _safe(m.get("free_cash_flow_yield"))
    ps          = _safe(m.get("price_to_sales_ratio") or p.get("price_to_sales"))

    scores: list[float] = []

    if pe is not None:
        if pe < 0:          scores.append(20.0)
        elif pe < 12:       scores.append(90.0)
        elif pe < 20:       scores.append(70.0)
        elif pe < 30:       scores.append(50.0)
        elif pe < 50:       scores.append(25.0)
        else:               scores.append(5.0)

    if ev_ebitda is not None and ev_ebitda > 0:
        if ev_ebitda < 8:   scores.append(90.0)
        elif ev_ebitda < 15: scores.append(65.0)
        elif ev_ebitda < 25: scores.append(40.0)
        else:               scores.append(15.0)

    if peg is not None and peg > 0:
        if peg < 0.8:       scores.append(90.0)
        elif peg < 1.2:     scores.append(70.0)
        elif peg < 2.0:     scores.append(45.0)
        else:               scores.append(15.0)

    if fcf_yield is not None:
        if fcf_yield > 0.06:  scores.append(85.0)
        elif fcf_yield > 0.03: scores.append(60.0)
        elif fcf_yield > 0.0:  scores.append(40.0)
        else:                  scores.append(15.0)

    score = _avg(scores)

    if score is None:     status = "N/A"
    elif score >= 75:     status = "Attractive"
    elif score >= 55:     status = "Fair"
    elif score >= 35:     status = "Stretched"
    else:                 status = "Expensive"

    if pe is not None and pe > 0:
        primary = ("P/E", f"{pe:.1f}x")
    elif ev_ebitda is not None and ev_ebitda > 0:
        primary = ("EV/EBITDA", f"{ev_ebitda:.1f}x")
    else:
        primary = ("P/S", _mult(ps) if ps else "—")

    if forward_pe is not None and forward_pe > 0:
        secondary = ("Fwd P/E", f"{forward_pe:.1f}x")
    elif peg is not None and peg > 0:
        secondary = ("PEG", f"{peg:.2f}")
    elif fcf_yield is not None:
        secondary = ("FCF Yield", _pct(fcf_yield))
    else:
        secondary = ("", "")

    _EXPL = {
        "Attractive": "Valuation metrics appear favorable relative to typical thresholds.",
        "Fair":       "Multiples are roughly in line with historical norms.",
        "Stretched":  "Current multiples imply limited margin of safety.",
        "Expensive":  "Valuation is elevated and leaves little room for disappointment.",
        "N/A":        "Insufficient valuation data.",
    }
    return {
        "key": "valuation", "label": status,
        "score": round(score) if score is not None else None,
        "primary_metric": primary[0], "primary_value": primary[1],
        "secondary_metric": secondary[0], "secondary_value": secondary[1],
        "explanation": _EXPL[status], "type": "Computed",
    }


# ── Pillar: Growth ────────────────────────────────────────────────────────────

def _growth_pillar(data: dict) -> dict:
    m = (data.get("metrics") or {}).get("snapshot") or {}
    p = (data.get("overview") or {}).get("profile") or {}

    rev_growth = _safe(m.get("revenue_growth") or p.get("revenue_growth"))
    eps_growth = _safe(m.get("earnings_per_share_growth") or m.get("earnings_growth") or p.get("earnings_growth"))
    fcf_growth = _safe(m.get("free_cash_flow_growth"))

    scores: list[float] = []

    if rev_growth is not None:
        if rev_growth > 0.25:    scores.append(95.0)
        elif rev_growth > 0.15:  scores.append(80.0)
        elif rev_growth > 0.08:  scores.append(65.0)
        elif rev_growth > 0.02:  scores.append(50.0)
        elif rev_growth > -0.05: scores.append(35.0)
        else:                    scores.append(10.0)

    if eps_growth is not None:
        if eps_growth > 0.30:    scores.append(92.0)
        elif eps_growth > 0.15:  scores.append(78.0)
        elif eps_growth > 0.05:  scores.append(60.0)
        elif eps_growth > -0.05: scores.append(40.0)
        else:                    scores.append(15.0)

    if fcf_growth is not None:
        if fcf_growth > 0.20:   scores.append(88.0)
        elif fcf_growth > 0.10: scores.append(72.0)
        elif fcf_growth > 0.0:  scores.append(55.0)
        else:                   scores.append(25.0)

    score = _avg(scores)

    if score is None:    status = "N/A"
    elif score >= 80:    status = "Strong"
    elif score >= 60:    status = "Healthy"
    elif score >= 40:    status = "Moderate"
    elif score >= 20:    status = "Slowing"
    else:                status = "Declining"

    _EXPL = {
        "Strong":   "Revenue and earnings growing well above typical benchmarks.",
        "Healthy":  "Solid growth trajectory with positive top and bottom-line expansion.",
        "Moderate": "Growth is positive but modest — watch for acceleration or deceleration.",
        "Slowing":  "Growth rate has decelerated meaningfully from prior levels.",
        "Declining":"Revenue or earnings are contracting — warrants close monitoring.",
        "N/A":      "Insufficient growth data.",
    }
    return {
        "key": "growth", "label": status,
        "score": round(score) if score is not None else None,
        "primary_metric": "Revenue Growth", "primary_value": _pct(rev_growth),
        "secondary_metric": "EPS Growth",   "secondary_value": _pct(eps_growth),
        "explanation": _EXPL[status], "type": "Computed",
    }


# ── Pillar: Profitability ─────────────────────────────────────────────────────

def _profitability_pillar(data: dict) -> dict:
    m = (data.get("metrics") or {}).get("snapshot") or {}
    p = (data.get("overview") or {}).get("profile") or {}

    op_margin  = _safe(m.get("operating_margin") or p.get("operating_margins"))
    net_margin = _safe(m.get("net_margin") or p.get("profit_margins"))
    roic       = _safe(m.get("return_on_invested_capital"))
    roe        = _safe(m.get("return_on_equity") or p.get("roe"))
    gross_margin = _safe(m.get("gross_margin") or p.get("gross_margins"))

    scores: list[float] = []

    if op_margin is not None:
        if op_margin > 0.25:    scores.append(95.0)
        elif op_margin > 0.15:  scores.append(80.0)
        elif op_margin > 0.08:  scores.append(62.0)
        elif op_margin > 0.03:  scores.append(45.0)
        elif op_margin > 0.0:   scores.append(30.0)
        else:                   scores.append(10.0)

    if roic is not None:
        if roic > 0.20:         scores.append(95.0)
        elif roic > 0.12:       scores.append(75.0)
        elif roic > 0.07:       scores.append(55.0)
        elif roic > 0.0:        scores.append(35.0)
        else:                   scores.append(10.0)

    if net_margin is not None:
        if net_margin > 0.20:   scores.append(90.0)
        elif net_margin > 0.10: scores.append(72.0)
        elif net_margin > 0.05: scores.append(55.0)
        elif net_margin > 0.0:  scores.append(35.0)
        else:                   scores.append(10.0)

    if roe is not None and roe > 0:
        if roe > 0.25:          scores.append(88.0)
        elif roe > 0.15:        scores.append(70.0)
        elif roe > 0.08:        scores.append(50.0)
        else:                   scores.append(30.0)

    score = _avg(scores)

    if score is None:    status = "N/A"
    elif score >= 80:    status = "Exceptional"
    elif score >= 62:    status = "Strong"
    elif score >= 44:    status = "Moderate"
    elif score >= 25:    status = "Thin"
    else:                status = "Weak"

    _EXPL = {
        "Exceptional": "Profitability metrics are best-in-class — strong competitive moat indicators.",
        "Strong":   "Above-average margins and returns signal a well-run, profitable business.",
        "Moderate": "Adequate profitability with room for improvement.",
        "Thin":     "Margins are narrow; the business is vulnerable to revenue headwinds.",
        "Weak":     "Below-cost-of-capital returns or losses require close attention.",
        "N/A":      "Insufficient profitability data.",
    }
    return {
        "key": "profitability", "label": status,
        "score": round(score) if score is not None else None,
        "primary_metric": "Op. Margin",  "primary_value": _pct(op_margin),
        "secondary_metric": "ROIC",      "secondary_value": _pct(roic),
        "explanation": _EXPL[status], "type": "Computed",
    }


# ── Pillar: Balance Sheet ─────────────────────────────────────────────────────

def _balance_sheet_pillar(data: dict) -> dict:
    m = (data.get("metrics") or {}).get("snapshot") or {}
    p = (data.get("overview") or {}).get("profile") or {}

    dte          = _safe(m.get("debt_to_equity") or p.get("debt_to_equity"))
    current      = _safe(m.get("current_ratio")  or p.get("current_ratio"))
    interest_cov = _safe(m.get("interest_coverage"))

    scores: list[float] = []

    if dte is not None:
        if dte < 0.3:    scores.append(95.0)
        elif dte < 0.8:  scores.append(80.0)
        elif dte < 1.5:  scores.append(60.0)
        elif dte < 3.0:  scores.append(35.0)
        else:            scores.append(10.0)

    if current is not None:
        if current > 2.5:    scores.append(90.0)
        elif current > 1.5:  scores.append(72.0)
        elif current > 1.0:  scores.append(52.0)
        elif current > 0.75: scores.append(30.0)
        else:                scores.append(10.0)

    if interest_cov is not None and interest_cov > 0:
        if interest_cov > 10:  scores.append(92.0)
        elif interest_cov > 5: scores.append(75.0)
        elif interest_cov > 2: scores.append(50.0)
        else:                  scores.append(20.0)

    score = _avg(scores)

    if score is None:  status = "N/A"
    elif score >= 80:  status = "Fortress"
    elif score >= 60:  status = "Healthy"
    elif score >= 40:  status = "Adequate"
    elif score >= 20:  status = "Elevated"
    else:              status = "Leveraged"

    _EXPL = {
        "Fortress": "Low debt and strong liquidity — well-positioned to weather downturns.",
        "Healthy":  "Balance sheet is solid with manageable leverage.",
        "Adequate": "Leverage and liquidity are within acceptable ranges.",
        "Elevated": "Debt level or liquidity position warrants monitoring.",
        "Leveraged":"High leverage increases financial risk.",
        "N/A":      "Insufficient balance sheet data.",
    }
    return {
        "key": "balance_sheet", "label": status,
        "score": round(score) if score is not None else None,
        "primary_metric":   "D/E Ratio",      "primary_value":   _mult(dte) if dte is not None else "—",
        "secondary_metric": "Current Ratio",   "secondary_value": _mult(current) if current is not None else "—",
        "explanation": _EXPL[status], "type": "Computed",
    }


# ── Pillar: Risk ──────────────────────────────────────────────────────────────

def _risk_pillar(data: dict) -> dict:
    anomalies = (data.get("analysis") or {}).get("anomalies") or []
    p = (data.get("overview") or {}).get("profile") or {}

    high_anom = sum(1 for a in anomalies if a.get("severity") == "high")
    med_anom  = sum(1 for a in anomalies if a.get("severity") == "medium")
    weighted  = high_anom * 2 + med_anom

    short_pct = _safe(p.get("short_pct_float"))
    scores: list[float] = []

    if weighted == 0:    scores.append(90.0)
    elif weighted <= 2:  scores.append(65.0)
    elif weighted <= 4:  scores.append(40.0)
    else:                scores.append(15.0)

    if short_pct is not None:
        if short_pct < 0.03:     scores.append(85.0)
        elif short_pct < 0.08:   scores.append(65.0)
        elif short_pct < 0.15:   scores.append(40.0)
        else:                    scores.append(15.0)

    score = _avg(scores)

    if score is None:   status = "N/A"
    elif score >= 78:   status = "Low"
    elif score >= 55:   status = "Moderate"
    elif score >= 30:   status = "Elevated"
    else:               status = "High"

    anom_str  = f"{len(anomalies)} flagged" if anomalies else "None"
    short_str = f"{short_pct*100:.1f}%" if short_pct is not None else "—"

    _EXPL = {
        "Low":      "No material anomalies detected and low short interest.",
        "Moderate": "Some flags present — monitor for developments.",
        "Elevated": "Multiple anomalies or elevated short interest suggest caution.",
        "High":     "Significant risk signals across multiple dimensions.",
        "N/A":      "Insufficient risk data.",
    }
    return {
        "key": "risk", "label": status,
        "score": round(score) if score is not None else None,
        "primary_metric": "Anomalies",     "primary_value": anom_str,
        "secondary_metric": "Short Float", "secondary_value": short_str,
        "explanation": _EXPL[status], "type": "Computed",
    }


# ── Pillar: Momentum ──────────────────────────────────────────────────────────

def _momentum_pillar(data: dict) -> dict:
    p    = (data.get("overview") or {}).get("profile") or {}
    snap = (data.get("overview") or {}).get("snapshot") or {}

    price     = _safe(snap.get("price"))
    wk52_high = _safe(p.get("week52_high"))
    wk52_low  = _safe(p.get("week52_low"))

    scores: list[float] = []

    dist_from_high_str = "—"
    range_pos_str      = "—"

    if price and wk52_high and wk52_high > 0:
        dist = (price - wk52_high) / wk52_high
        dist_from_high_str = f"{dist * 100:.1f}% from 52W high"
        if dist >= -0.02:    scores.append(95.0)
        elif dist >= -0.08:  scores.append(78.0)
        elif dist >= -0.15:  scores.append(58.0)
        elif dist >= -0.25:  scores.append(38.0)
        elif dist >= -0.40:  scores.append(20.0)
        else:                scores.append(8.0)

    if price and wk52_high and wk52_low and (wk52_high - wk52_low) > 0:
        pos = (price - wk52_low) / (wk52_high - wk52_low)
        range_pos_str = f"{pos * 100:.0f}% of 52W range"
        scores.append(pos * 100)

    score = _avg(scores)

    if score is None:   status = "N/A"
    elif score >= 80:   status = "Strong"
    elif score >= 60:   status = "Positive"
    elif score >= 40:   status = "Neutral"
    elif score >= 20:   status = "Weak"
    else:               status = "Bearish"

    _EXPL = {
        "Strong":  "Price near 52-week high — strong relative momentum.",
        "Positive":"Trading well within the upper portion of the 52-week range.",
        "Neutral": "Mid-range positioning — no clear directional trend signal.",
        "Weak":    "Trading in the lower portion of the 52-week range.",
        "Bearish": "Significant distance from 52-week high — trend is under pressure.",
        "N/A":     "Insufficient price data for momentum analysis.",
    }
    return {
        "key": "momentum", "label": status,
        "score": round(score) if score is not None else None,
        "primary_metric": "vs 52W High",  "primary_value": dist_from_high_str,
        "secondary_metric": "52W Range",  "secondary_value": range_pos_str,
        "explanation": _EXPL[status], "type": "Computed",
    }


# ── Risk flags ────────────────────────────────────────────────────────────────

def _compute_risk_flags(data: dict) -> list[dict]:
    flags: list[dict] = []
    m        = (data.get("metrics") or {}).get("snapshot") or {}
    p        = (data.get("overview") or {}).get("profile") or {}
    estimates = (data.get("estimates") or {}).get("annual") or []
    earnings  = data.get("earnings_history") or []
    anomalies = (data.get("analysis") or {}).get("anomalies") or []

    # Valuation risk
    pe  = _safe(m.get("price_to_earnings_ratio") or p.get("pe_ratio"))
    peg = _safe(m.get("peg_ratio") or p.get("peg_ratio"))
    if pe is not None and pe > 40:
        flags.append({
            "category": "valuation", "type": "Computed",
            "label": "Elevated P/E",
            "severity": "high" if pe > 60 else "medium",
            "explanation": f"P/E of {pe:.1f}x implies elevated expectations. Any earnings miss could weigh on the stock.",
        })
    if peg is not None and peg > 2.5:
        flags.append({
            "category": "valuation", "type": "Computed",
            "label": "PEG Premium",
            "severity": "medium",
            "explanation": f"PEG ratio of {peg:.2f} suggests the stock may be pricing in aggressive future growth.",
        })

    # Earnings miss pattern
    if earnings:
        recent = [e.get("surprise_pct") for e in earnings[-4:] if e.get("surprise_pct") is not None]
        if recent:
            misses = [s for s in recent if s < -5]
            if len(misses) >= 2:
                flags.append({
                    "category": "estimate", "type": "Computed",
                    "label": "Earnings Miss Pattern",
                    "severity": "high" if len(misses) >= 3 else "medium",
                    "explanation": (
                        f"Missed EPS estimates by >5% in {len(misses)} of the "
                        f"last {len(recent)} quarters."
                    ),
                })

    # Leverage risk
    dte         = _safe(m.get("debt_to_equity") or p.get("debt_to_equity"))
    interest_cov= _safe(m.get("interest_coverage"))
    if dte is not None and dte > 2.5:
        flags.append({
            "category": "macro", "type": "Computed",
            "label": "High Leverage",
            "severity": "high" if dte > 4 else "medium",
            "explanation": (
                f"Debt/equity of {dte:.1f}x increases sensitivity to rate changes "
                "and earnings volatility."
            ),
        })
    elif interest_cov is not None and 0 < interest_cov < 2:
        flags.append({
            "category": "macro", "type": "Computed",
            "label": "Thin Interest Coverage",
            "severity": "high",
            "explanation": f"Interest coverage of {interest_cov:.1f}x — earnings barely cover debt service.",
        })

    # Short interest
    short_pct = _safe(p.get("short_pct_float"))
    if short_pct is not None and short_pct > 0.12:
        flags.append({
            "category": "macro", "type": "Computed",
            "label": "High Short Interest",
            "severity": "medium",
            "explanation": (
                f"{short_pct*100:.1f}% of float is short — elevated bearish positioning "
                "or potential for a short squeeze."
            ),
        })

    # Estimate exposure (informational)
    if estimates:
        nxt = next((e for e in estimates if e.get("earnings_per_share") is not None), None)
        if nxt:
            flags.append({
                "category": "earnings", "type": "Computed",
                "label": "Earnings Estimate Exposure",
                "severity": "low",
                "explanation": (
                    f"Consensus EPS estimate: ${nxt.get('earnings_per_share', 0):.2f}. "
                    "Results vs. expectation will likely drive near-term price action."
                ),
            })

    # High-severity anomalies
    high_anom = [a for a in anomalies if a.get("severity") == "high"]
    if high_anom:
        flags.append({
            "category": "concentration", "type": "Computed",
            "label": "Financial Anomalies Detected",
            "severity": "high",
            "explanation": (
                f"{len(high_anom)} high-severity flag(s): "
                + ", ".join(a["title"] for a in high_anom[:2]) + "."
            ),
        })

    sev_order = {"high": 0, "medium": 1, "low": 2}
    flags.sort(key=lambda x: sev_order.get(x["severity"], 3))
    return flags


# ── Sentiment Regime ──────────────────────────────────────────────────────────
# Delegated entirely to app.services.research.sentiment_regime.
# This thin wrapper extracts the required fields and calls compute_sentiment_regime().

def _sentiment_regime(data: dict, price_bars: list | None, spy_bars: list | None) -> dict:
    return compute_sentiment_regime(
        price_bars       = price_bars or [],
        spy_bars         = spy_bars or [],
        profile          = (data.get("overview") or {}).get("profile") or {},
        valuation        = data.get("valuation") or {},
        earnings_history = data.get("earnings_history") or [],
        estimates_annual = (data.get("estimates") or {}).get("annual") or [],
    )


# ── Data coverage ─────────────────────────────────────────────────────────────

def _coverage(data: dict) -> dict:
    snap    = (data.get("overview") or {}).get("snapshot") or {}
    m       = (data.get("metrics") or {}).get("snapshot") or {}
    income  = (data.get("financials") or {}).get("income_annual") or []
    est_ann = (data.get("estimates") or {}).get("annual") or []

    quote_available = bool(_safe(snap.get("price")))

    fund_fields = [m.get("revenue_growth"), m.get("operating_margin"), m.get("gross_margin")]
    fund_count  = sum(1 for f in fund_fields if f is not None)
    if fund_count == 3:         fundamentals_available = "full"
    elif fund_count > 0 or income: fundamentals_available = "partial"
    else:                           fundamentals_available = "none"

    if len(est_ann) >= 2:       estimates_available = "full"
    elif len(est_ann) == 1:     estimates_available = "partial"
    else:                        estimates_available = "none"

    return {
        "quote_available":        quote_available,
        "fundamentals_available": fundamentals_available,
        "estimates_available":    estimates_available,
        "fresh_context_available": False,   # updated by synthesis endpoint
    }


# ── Entry point ───────────────────────────────────────────────────────────────

def compute_analysis_layer(
    data:       dict,
    price_bars: list | None = None,
    spy_bars:   list | None = None,
) -> dict:
    """
    Compute the deterministic analysis layer from assembled research data.

    Parameters
    ----------
    data       : assembled research response dict
    price_bars : 1Y daily OHLCV bars for the ticker [{ts, close, ...}]
                 If None, sentiment_regime returns 'Insufficient data'.
    spy_bars   : 1Y daily OHLCV bars for SPY (benchmark comparison)
                 If None, relative-return sub-factor is skipped.

    No I/O. All outputs are source_type='Computed'.
    """
    return {
        "pillars": [
            _valuation_pillar(data),
            _growth_pillar(data),
            _profitability_pillar(data),
            _balance_sheet_pillar(data),
            _risk_pillar(data),
            _momentum_pillar(data),
        ],
        "risk_flags":       _compute_risk_flags(data),
        "sentiment_regime": _sentiment_regime(data, price_bars, spy_bars),
        "coverage":         _coverage(data),
    }
