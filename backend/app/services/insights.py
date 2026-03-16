"""Rule-based equity insights engine — pure computation, no I/O.

Modular structure:
  compute_insights()             — public entry point
  _compute_growth_insights()
  _compute_profitability_insights()
  _compute_balance_sheet_insights()
  _compute_valuation_insights()
  _compute_risk_insights()
  _compute_catalyst_insights()
  _detect_compounder()
"""
from __future__ import annotations

# ── Type alias ────────────────────────────────────────────────────────────────
Insight = dict  # {"text": str, "strength": "strong" | "moderate" | "weak"}


# ── Public entry point ────────────────────────────────────────────────────────

def compute_insights(
    sym: str,
    data: dict,
    sector_stats: dict | None = None,
) -> dict:
    """
    Derive deterministic bull / bear / catalyst / risk insights from aggregated
    research data.

    sector_stats (optional):
        rev_growth_median   float  (decimal — e.g. 0.09 for 9 %)
        op_margin_median    float
        pe_median           float  (raw multiple)
        roic_median         float  (decimal)
    """
    ss = sector_stats or {}

    # ── Unpack ────────────────────────────────────────────────────────────────
    m       = (data.get("metrics") or {}).get("snapshot") or {}
    p       = (data.get("overview") or {}).get("profile")  or {}
    company = (data.get("overview") or {}).get("company")  or {}
    fin     = data.get("financials") or {}
    ttm     = fin.get("income_ttm")  or {}
    bttm    = fin.get("balance_ttm") or {}
    cttm    = fin.get("cashflow_ttm") or {}
    income  = fin.get("income_annual") or []   # newest-first
    earnings_history = data.get("earnings_history") or []
    segments         = data.get("segments")       or []
    estimates_annual = (data.get("estimates") or {}).get("annual") or []

    # ── Domain computations ───────────────────────────────────────────────────
    bull_g,  bear_g,  cat_g  = _compute_growth_insights(m, p, income, ss)
    bull_pr, bear_pr         = _compute_profitability_insights(m, p, income, cttm, ss)
    bull_bs, bear_bs         = _compute_balance_sheet_insights(m, p, bttm)
    bull_v,  bear_v          = _compute_valuation_insights(m, p, ss)
    risks                    = _compute_risk_insights(p, earnings_history, segments)
    catalysts                = _compute_catalyst_insights(estimates_annual, ttm, company, cttm, bttm)

    # Compounder signal takes priority (inserted at front of bull)
    compounder = _detect_compounder(m, p, cttm, income)

    bull = ([compounder] if compounder else []) + bull_g + bull_pr + bull_bs + bull_v
    bear = bear_g + bear_pr + bear_bs + bear_v

    # Backfill sparse catalysts
    if len(catalysts) < 2:
        catalysts.append({
            "text": "Potential margin expansion through operating leverage as revenue scales",
            "strength": "weak",
        })
        cash = bttm.get("cash_and_equivalents")
        if cash and cash > 1e9:
            catalysts.append({
                "text": f"${cash / 1e9:.1f}B cash position enables M&A or shareholder returns",
                "strength": "moderate",
            })

    return {
        "bull":      bull[:6],
        "bear":      bear[:5],
        "catalysts": catalysts[:5],
        "risks":     risks[:5],
    }


# ── Growth ────────────────────────────────────────────────────────────────────

def _compute_growth_insights(
    m: dict, p: dict, income: list, ss: dict,
) -> tuple[list, list, list]:
    bull, bear, catalysts = [], [], []

    rev_growth = m.get("revenue_growth") or p.get("revenue_growth")
    rev_med    = ss.get("rev_growth_median")

    if rev_growth is not None:
        pct = rev_growth * 100
        if rev_med is not None:
            med_pct = rev_med * 100
            delta   = pct - med_pct
            label   = f"Revenue growing at {pct:.0f}% YoY"
            if pct < 0:
                bear.append({"text": f"Revenue declining {abs(pct):.0f}% YoY vs sector median of {med_pct:.0f}%", "strength": "strong"})
            elif delta > 8:
                bull.append({"text": f"{label}, significantly above the sector median of {med_pct:.0f}%", "strength": "strong"})
            elif delta > 3:
                bull.append({"text": f"{label}, ahead of the sector median of {med_pct:.0f}%", "strength": "moderate"})
            elif delta < -8:
                bear.append({"text": f"{label}, well below the sector median of {med_pct:.0f}%", "strength": "moderate"})
        else:
            if pct > 20:
                bull.append({"text": f"Revenue growing at {pct:.0f}% YoY — well above average", "strength": "strong"})
            elif pct > 8:
                bull.append({"text": f"Revenue growing at {pct:.0f}% YoY", "strength": "moderate"})
            elif pct < 0:
                bear.append({"text": f"Revenue declining {abs(pct):.0f}% YoY", "strength": "strong"})
            elif pct < 5:
                bear.append({"text": f"Slow revenue growth of {pct:.0f}% YoY", "strength": "moderate"})

    # Revenue trajectory — trend + 3Y CAGR
    if len(income) >= 4:
        revs = [r.get("revenue") for r in income[:4]]
        if all(r and r > 0 for r in revs):
            g0   = (revs[0] - revs[1]) / revs[1] * 100
            g1   = (revs[1] - revs[2]) / revs[2] * 100
            cagr = ((revs[0] / revs[3]) ** (1 / 3) - 1) * 100

            if g0 > g1 + 5:
                bull.append({"text": f"Revenue growth re-accelerating ({g1:.0f}% → {g0:.0f}%)", "strength": "moderate"})
            elif g1 > g0 + 10:
                bear.append({"text": f"Revenue growth decelerating ({g1:.0f}% → {g0:.0f}%)", "strength": "moderate"})

            if cagr > 15:
                bull.append({"text": f"3-year revenue CAGR of {cagr:.1f}% demonstrates sustained growth momentum", "strength": "moderate"})

    elif len(income) >= 3:
        revs = [r.get("revenue") for r in income[:3]]
        if all(r and r > 0 for r in revs):
            g0 = (revs[0] - revs[1]) / revs[1] * 100
            g1 = (revs[1] - revs[2]) / revs[2] * 100
            if g0 > g1 + 5:
                bull.append({"text": f"Revenue growth accelerating ({g1:.0f}% → {g0:.0f}%)", "strength": "moderate"})
            elif g1 > g0 + 10:
                bear.append({"text": f"Revenue growth decelerating ({g1:.0f}% → {g0:.0f}%)", "strength": "moderate"})

    return bull, bear, catalysts


# ── Profitability ─────────────────────────────────────────────────────────────

def _compute_profitability_insights(
    m: dict, p: dict, income: list, cttm: dict, ss: dict,
) -> tuple[list, list]:
    bull, bear = [], []

    gross_m  = m.get("gross_margin")     or p.get("gross_margins")
    op_m     = m.get("operating_margin") or p.get("operating_margins")
    op_med   = ss.get("op_margin_median")
    roic_med = ss.get("roic_median")

    # ── Group margin signals (avoid repeating gross / op / net separately) ────
    if gross_m is not None and op_m is not None:
        gm_pct = gross_m * 100
        om_pct = op_m    * 100
        if gm_pct > 55 and om_pct > 20:
            bull.append({"text": f"Strong profitability profile — {gm_pct:.0f}% gross margin and {om_pct:.0f}% operating margin", "strength": "strong"})
        elif gm_pct > 40 and om_pct > 10:
            bull.append({"text": f"Healthy margins — {gm_pct:.0f}% gross, {om_pct:.0f}% operating", "strength": "moderate"})
        elif op_m < 0:
            bear.append({"text": f"Negative operating margin ({om_pct:.0f}%) — not yet operationally profitable", "strength": "strong"})
        elif gm_pct < 25:
            bear.append({"text": f"Low gross margin of {gm_pct:.0f}% limits profitability upside", "strength": "moderate"})
    elif gross_m is not None:
        gm_pct = gross_m * 100
        if gm_pct > 60:
            bull.append({"text": f"Exceptional gross margin of {gm_pct:.0f}% indicates strong pricing power", "strength": "strong"})
        elif gm_pct < 20:
            bear.append({"text": f"Low gross margin of {gm_pct:.0f}% limits profitability upside", "strength": "moderate"})
    elif op_m is not None:
        om_pct = op_m * 100
        if om_pct > 25:
            bull.append({"text": f"High operating margin of {om_pct:.0f}%", "strength": "strong"})
        elif om_pct < 0:
            bear.append({"text": f"Negative operating margin of {om_pct:.0f}%", "strength": "strong"})

    # ── Sector-relative operating margin ─────────────────────────────────────
    if op_m is not None and op_med is not None:
        om_pct  = op_m   * 100
        med_pct = op_med * 100
        delta   = om_pct - med_pct
        if delta > 10:
            bull.append({"text": f"Operating margin of {om_pct:.0f}% significantly exceeds sector median of {med_pct:.0f}%", "strength": "moderate"})
        elif delta < -10 and op_m >= 0:
            bear.append({"text": f"Operating margin of {om_pct:.0f}% trails sector median of {med_pct:.0f}%", "strength": "moderate"})

    # ── Margin trend (2-year operating margin expansion / compression) ────────
    if len(income) >= 3:
        om_series: list[float] = []
        for row in income[:3]:
            rev = row.get("revenue")
            oi  = row.get("operating_income")
            if rev and rev > 0 and oi is not None:
                om_series.append(oi / rev * 100)

        if len(om_series) >= 3:
            curr, mid, old = om_series
            if curr > old + 5 and curr >= mid:
                bull.append({"text": f"Operating margin expanded from {old:.0f}% to {curr:.0f}% over the last two years, indicating improving operating leverage", "strength": "moderate"})
            elif curr < old - 7 and curr <= mid:
                bear.append({"text": f"Operating margin compressed from {old:.0f}% to {curr:.0f}% over the last two years", "strength": "moderate"})
        elif len(om_series) == 2:
            curr, old = om_series
            if curr > old + 5:
                bull.append({"text": f"Operating margin expanding ({old:.0f}% → {curr:.0f}%)", "strength": "moderate"})
            elif curr < old - 7:
                bear.append({"text": f"Operating margin compressing ({old:.0f}% → {curr:.0f}%)", "strength": "moderate"})

    # ── FCF ───────────────────────────────────────────────────────────────────
    fcf       = cttm.get("free_cash_flow")
    fcf_yield = m.get("free_cash_flow_yield")
    if fcf is not None:
        if fcf > 0:
            yield_str = f" ({fcf_yield * 100:.1f}% FCF yield)" if fcf_yield else ""
            bull.append({"text": f"Positive free cash flow generation{yield_str}", "strength": "strong" if fcf > 1e9 else "moderate"})
        else:
            bear.append({"text": "Negative free cash flow — cash burn may require future financing", "strength": "moderate"})

    # ── ROIC / ROE ────────────────────────────────────────────────────────────
    roic = m.get("return_on_invested_capital")
    roe  = m.get("return_on_equity") or p.get("roe")

    if roic is not None:
        pct     = roic * 100
        med_pct = roic_med * 100 if roic_med is not None else None
        if med_pct is not None:
            if pct > med_pct + 10:
                bull.append({"text": f"ROIC of {pct:.0f}% significantly exceeds the sector median of {med_pct:.0f}%", "strength": "strong"})
            elif pct < 5:
                bear.append({"text": f"Low ROIC of {pct:.0f}% suggests poor capital efficiency", "strength": "moderate"})
        else:
            if pct > 20:
                bull.append({"text": f"Strong ROIC of {pct:.0f}% indicates efficient capital allocation", "strength": "strong"})
            elif pct < 5:
                bear.append({"text": f"Low ROIC of {pct:.0f}% suggests poor capital efficiency", "strength": "moderate"})

    # Emit ROE only when ROIC is absent to avoid redundancy
    if roic is None and roe is not None and roe > 0.25:
        bull.append({"text": f"High ROE of {roe * 100:.0f}% demonstrates effective use of shareholder equity", "strength": "moderate"})

    return bull, bear


# ── Balance sheet ─────────────────────────────────────────────────────────────

def _compute_balance_sheet_insights(
    m: dict, p: dict, bttm: dict,
) -> tuple[list, list]:
    bull, bear = [], []

    de_ratio   = m.get("debt_to_equity") or p.get("debt_to_equity")
    curr_ratio = m.get("current_ratio")  or p.get("current_ratio")

    if de_ratio is not None:
        if de_ratio < 0.3:
            bull.append({"text": f"Low leverage (D/E: {de_ratio:.2f}×) provides financial flexibility and resilience", "strength": "moderate"})
        elif de_ratio > 3:
            bear.append({"text": f"High debt-to-equity of {de_ratio:.1f}× significantly increases financial risk", "strength": "strong"})
        elif de_ratio > 1.5:
            bear.append({"text": f"Elevated leverage (D/E: {de_ratio:.1f}×) warrants monitoring in a rising-rate environment", "strength": "weak"})

    if curr_ratio is not None:
        if curr_ratio > 2:
            bull.append({"text": f"Strong liquidity position (current ratio: {curr_ratio:.1f}×)", "strength": "weak"})
        elif curr_ratio < 1:
            bear.append({"text": f"Current ratio of {curr_ratio:.1f}× may signal near-term liquidity stress", "strength": "strong"})

    return bull, bear


# ── Valuation ─────────────────────────────────────────────────────────────────

def _compute_valuation_insights(
    m: dict, p: dict, ss: dict,
) -> tuple[list, list]:
    bull, bear = [], []

    pe     = m.get("price_to_earnings_ratio") or p.get("pe_ratio")
    fwd_pe = p.get("forward_pe")
    peg_v  = m.get("peg_ratio") or p.get("peg_ratio")
    roic   = m.get("return_on_invested_capital")
    pe_med = ss.get("pe_median")

    # PEG-based signal
    if peg_v is not None and peg_v > 0:
        if peg_v < 1:
            bull.append({"text": f"PEG ratio of {peg_v:.2f} suggests growth is undervalued relative to earnings expansion", "strength": "moderate"})
        elif peg_v > 3:
            bear.append({"text": f"PEG of {peg_v:.1f}× implies significant earnings growth already priced in", "strength": "moderate"})

    # PE — sector-relative or absolute
    if pe is not None and pe > 0:
        if pe_med is not None:
            delta = pe - pe_med
            if delta > 15 and roic is not None and roic > 0.20:
                bull.append({"text": f"Premium valuation ({pe:.0f}× vs sector median {pe_med:.0f}×) appears justified by superior ROIC of {roic * 100:.0f}%", "strength": "moderate"})
            elif delta > 20:
                bear.append({"text": f"Trades at {pe:.0f}× P/E, a {delta:.0f}-point premium to the sector median of {pe_med:.0f}×", "strength": "moderate"})
        else:
            if pe > 50:
                bear.append({"text": f"Premium valuation at {pe:.0f}× P/E leaves limited margin for error", "strength": "moderate"})
            elif pe > 30:
                bear.append({"text": f"Elevated P/E of {pe:.0f}× is sensitive to earnings misses or rate increases", "strength": "weak"})

    # Forward P/E discount signals earnings growth
    if fwd_pe is not None and fwd_pe > 0 and pe is not None and pe > 0 and fwd_pe < pe * 0.80:
        bull.append({"text": f"Forward P/E of {fwd_pe:.0f}× well below trailing {pe:.0f}×, implying strong earnings expansion ahead", "strength": "moderate"})

    return bull, bear


# ── Risks ─────────────────────────────────────────────────────────────────────

def _compute_risk_insights(
    p: dict, earnings_history: list, segments: list,
) -> list:
    risks: list[Insight] = []

    # Short interest
    short_pct = p.get("short_pct_float")
    if short_pct is not None and short_pct > 0.15:
        risks.append({"text": f"High short interest of {short_pct * 100:.0f}% of float signals elevated bearish conviction", "strength": "strong"})

    # Institutional concentration risk
    held_inst = p.get("held_pct_institutions")
    if held_inst is not None and held_inst > 0.85:
        risks.append({"text": f"High institutional ownership ({held_inst * 100:.0f}%) amplifies volatility on sentiment shifts", "strength": "weak"})

    # Earnings delivery
    with_surprise = [e for e in earnings_history if e.get("surprise_pct") is not None]
    if len(with_surprise) > 4:
        miss_count = sum(1 for e in with_surprise if e["surprise_pct"] < 0)
        if miss_count / len(with_surprise) > 0.40:
            risks.append({"text": f"Inconsistent earnings delivery — missed consensus {miss_count} of last {len(with_surprise)} quarters", "strength": "moderate"})

    # Revenue concentration
    if segments:
        items = segments[0].get("items", [])
        product_items = [
            it for it in items
            if len(it.get("segments", [])) == 1
            and it["segments"][0].get("axis") == "srt:ProductOrServiceAxis"
        ]
        if product_items:
            total = sum(it["amount"] for it in product_items)
            if total > 0:
                top     = max(product_items, key=lambda x: x["amount"])
                pct_top = (top["amount"] / total) * 100
                if pct_top > 60:
                    label = top["segments"][0].get("label", "top segment")
                    risks.append({"text": f'Revenue concentration: "{label}" represents {pct_top:.0f}% of product revenue', "strength": "moderate"})

    # Macro baseline — always present
    risks.append({"text": "Macroeconomic slowdown could compress multiples and reduce enterprise / consumer spending", "strength": "moderate"})

    return risks[:5]


# ── Catalysts ─────────────────────────────────────────────────────────────────

def _compute_catalyst_insights(
    estimates: list, ttm: dict, company: dict, cttm: dict, bttm: dict,
) -> list:
    catalysts: list[Insight] = []

    # Short-squeeze potential
    # (noted here as a catalyst if high short interest detected — complementary to risk signal)

    # Analyst growth estimates
    if estimates:
        est     = estimates[0]
        ttm_rev = ttm.get("revenue")
        ttm_eps = ttm.get("earnings_per_share")
        if est.get("revenue") and ttm_rev and ttm_rev > 0:
            g = ((est["revenue"] - ttm_rev) / ttm_rev) * 100
            if g > 10:
                catalysts.append({"text": f"Consensus projects {g:.0f}% revenue growth in next fiscal year", "strength": "moderate"})
        if est.get("earnings_per_share") and ttm_eps and ttm_eps != 0:
            g = ((est["earnings_per_share"] - ttm_eps) / abs(ttm_eps)) * 100
            if g > 15:
                catalysts.append({"text": f"Consensus EPS expected to grow {g:.0f}% next fiscal year", "strength": "moderate"})

    # Sector-level tailwinds
    sector   = (company.get("sector")   or "").lower()
    industry = (company.get("industry") or "").lower()
    if any(kw in sector + " " + industry for kw in ("tech", "software", "semiconductor", "information")):
        catalysts.append({"text": "AI and cloud adoption driving secular growth tailwinds across the technology sector", "strength": "moderate"})
    elif "health" in sector or "pharma" in sector or "biotech" in industry:
        catalysts.append({"text": "Aging demographics and healthcare innovation drive multi-year demand tailwinds", "strength": "moderate"})
    elif "energy" in sector:
        catalysts.append({"text": "Energy transition and infrastructure build-out create new addressable markets", "strength": "moderate"})

    # Cash optionality
    cash = bttm.get("cash_and_equivalents")
    if cash and cash > 2e9:
        catalysts.append({"text": f"${cash / 1e9:.0f}B cash war chest enables accretive M&A, buybacks, or dividend growth", "strength": "moderate"})
    elif cash and cash > 5e8:
        catalysts.append({"text": f"${cash / 1e6:.0f}M cash balance supports share repurchases or strategic investments", "strength": "weak"})

    return catalysts[:5]


# ── Compounder detection ──────────────────────────────────────────────────────

def _detect_compounder(
    m: dict, p: dict, cttm: dict, income: list,
) -> Insight | None:
    """
    Identify high-quality compounders:
      revenue growth > 10 % AND operating margin > 20 % AND ROIC > 15 % AND positive FCF.
    Returns a single strong bull insight, or None.
    """
    rev_growth = m.get("revenue_growth") or p.get("revenue_growth")
    op_m       = m.get("operating_margin") or p.get("operating_margins")
    roic       = m.get("return_on_invested_capital")
    fcf        = cttm.get("free_cash_flow")

    if (
        rev_growth is not None and rev_growth > 0.10
        and op_m   is not None and op_m       > 0.20
        and roic   is not None and roic        > 0.15
        and fcf    is not None and fcf         > 0
    ):
        return {
            "text": (
                f"Financial profile resembles a high-quality compounder — "
                f"{rev_growth * 100:.0f}% revenue growth, "
                f"{op_m * 100:.0f}% operating margin, "
                f"and {roic * 100:.0f}% ROIC with positive free cash flow"
            ),
            "strength": "strong",
        }
    return None
