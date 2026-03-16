"""Build chart-ready trend datasets from financial statements + metrics history."""
import re


def build_trends(
    income: list,
    cashflow: list,
    metrics_history: list,
    is_quarterly: bool = False,
) -> dict:
    """Return aligned trend series for revenue, EPS, FCF, margins, and returns."""

    def period_label(rp: str, fp: str = "") -> str:
        if is_quarterly:
            m  = re.search(r"Q\d", fp or "")
            yr = fp[2:4] if len(fp) >= 4 else rp[2:4]
            return f"{m.group()}'{yr}" if m else rp[:7]
        return fp[:4] if len(fp) >= 4 else rp[:4]

    mh_map = {row.get("report_period", ""): row for row in metrics_history}
    cf_map = {row.get("report_period", ""): row for row in cashflow}

    revenue_trend: list[dict] = []
    eps_trend:     list[dict] = []
    fcf_trend:     list[dict] = []
    margins_trend: list[dict] = []

    for stmt in sorted(income, key=lambda x: x.get("report_period", "")):
        rp = stmt.get("report_period", "")
        fp = stmt.get("fiscal_period", "")
        pl = period_label(rp, fp)
        mh = mh_map.get(rp, {})

        rev = stmt.get("revenue")
        if rev is not None and rev > 0:
            rg = mh.get("revenue_growth")
            revenue_trend.append({
                "period": pl, "report_period": rp,
                "value":  rev,
                "growth": round(rg * 100, 1) if rg is not None else None,
            })

        eps = stmt.get("earnings_per_share_diluted") or stmt.get("earnings_per_share")
        if eps is not None:
            eg = mh.get("earnings_per_share_growth")
            eps_trend.append({
                "period": pl, "report_period": rp,
                "value":  round(float(eps), 4),
                "growth": round(eg * 100, 1) if eg is not None else None,
            })

        if rev is not None and rev > 0:
            gross  = stmt.get("gross_profit")
            op_inc = stmt.get("operating_income")
            net    = stmt.get("net_income")
            margins_trend.append({
                "period": pl, "report_period": rp,
                "gross":     round(gross  / rev * 100, 2) if gross  is not None else None,
                "operating": round(op_inc / rev * 100, 2) if op_inc is not None else None,
                "net":       round(net    / rev * 100, 2) if net    is not None else None,
            })

        cf  = cf_map.get(rp, {})
        fcf = cf.get("free_cash_flow")
        if fcf is not None:
            fg = mh.get("free_cash_flow_growth")
            fcf_trend.append({
                "period": pl, "report_period": rp,
                "value":  fcf,
                "growth": round(fg * 100, 1) if fg is not None else None,
            })

    returns_trend: list[dict] = []
    for mh in sorted(metrics_history, key=lambda x: x.get("report_period", "")):
        rp   = mh.get("report_period", "")
        fp   = mh.get("fiscal_period", "")
        roe  = mh.get("return_on_equity")
        roa  = mh.get("return_on_assets")
        roic = mh.get("return_on_invested_capital")
        if any(v is not None for v in [roe, roa, roic]):
            returns_trend.append({
                "period": period_label(rp, fp), "report_period": rp,
                "roe":  round(roe  * 100, 1) if roe  is not None else None,
                "roa":  round(roa  * 100, 1) if roa  is not None else None,
                "roic": round(roic * 100, 1) if roic is not None else None,
            })

    return {
        "revenue":        revenue_trend,
        "eps":            eps_trend,
        "free_cash_flow": fcf_trend,
        "margins":        margins_trend,
        "returns":        returns_trend,
    }
