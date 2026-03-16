"""Detect financial anomalies from aggregated research data."""
import logging

log = logging.getLogger(__name__)


def detect_anomalies(data: dict) -> list[dict]:
    """
    Scan financial statement trends for noteworthy changes.
    Returns anomalies sorted high → medium → low, deduplicated by id.
    """
    anomalies: list[dict] = []
    fin      = data.get("financials") or {}
    income   = fin.get("income_annual")   or []
    balance  = fin.get("balance_annual")  or []
    cashflow = fin.get("cashflow_annual") or []

    # ── Revenue ───────────────────────────────────────────────────────────────
    if len(income) >= 3:
        revs = [r.get("revenue") for r in income[:4]]
        revs = [r for r in revs if r]
        if len(revs) >= 3:
            g0 = (revs[0] - revs[1]) / abs(revs[1]) * 100 if revs[1] else None
            g1 = (revs[1] - revs[2]) / abs(revs[2]) * 100 if revs[2] else None
            if g0 is not None and g1 is not None:
                delta = g0 - g1
                if delta < -15:
                    sev = "high" if delta < -25 else "medium"
                    anomalies.append({
                        "id": "revenue_slowdown", "category": "revenue",
                        "title": "Revenue Growth Slowdown",
                        "description": f"Revenue growth declined from {g1:.0f}% to {g0:.0f}% over the last two years.",
                        "severity": sev, "section_id": "sec-trends",
                        "metric_before": round(g1, 1), "metric_after": round(g0, 1), "metric_unit": "%",
                    })
                elif delta > 15:
                    anomalies.append({
                        "id": "revenue_acceleration", "category": "revenue",
                        "title": "Revenue Growth Acceleration",
                        "description": f"Revenue growth accelerated from {g1:.0f}% to {g0:.0f}% — a notable improvement.",
                        "severity": "low", "section_id": "sec-trends",
                        "metric_before": round(g1, 1), "metric_after": round(g0, 1), "metric_unit": "%",
                    })
            if revs[0] < revs[1]:
                decline_pct = (revs[1] - revs[0]) / revs[1] * 100
                if decline_pct > 10:
                    anomalies.append({
                        "id": "revenue_decline", "category": "revenue",
                        "title": "Revenue Decline",
                        "description": f"Revenue fell {decline_pct:.0f}% year over year.",
                        "severity": "high" if decline_pct > 25 else "medium",
                        "section_id": "sec-trends",
                        "metric_before": round(revs[1]/1e9, 2) if revs[1] >= 1e9 else round(revs[1]/1e6, 1),
                        "metric_after":  round(revs[0]/1e9, 2) if revs[0] >= 1e9 else round(revs[0]/1e6, 1),
                        "metric_unit": "B" if revs[1] >= 1e9 else "M",
                    })

    # ── Margins ───────────────────────────────────────────────────────────────
    if len(income) >= 2:
        def margin(r: dict, num_field: str) -> float | None:
            rev = r.get("revenue")
            num = r.get(num_field)
            return num / rev * 100 if rev and num is not None and rev > 0 else None

        gm0 = margin(income[0], "gross_profit")
        gm1 = margin(income[1], "gross_profit")
        om0 = margin(income[0], "operating_income")
        om1 = margin(income[1], "operating_income")

        if gm0 is not None and gm1 is not None and (gm0 - gm1) < -5:
            delta = gm0 - gm1
            anomalies.append({
                "id": "gross_margin_compression", "category": "margins",
                "title": "Gross Margin Compression",
                "description": f"Gross margin declined from {gm1:.1f}% to {gm0:.1f}% year over year.",
                "severity": "high" if delta < -10 else "medium",
                "section_id": "sec-trends",
                "metric_before": round(gm1, 1), "metric_after": round(gm0, 1), "metric_unit": "%",
            })

        if om0 is not None and om1 is not None and (om0 - om1) < -5:
            delta = om0 - om1
            anomalies.append({
                "id": "operating_margin_compression", "category": "margins",
                "title": "Operating Margin Compression",
                "description": f"Operating margin dropped from {om1:.1f}% to {om0:.1f}%.",
                "severity": "high" if delta < -10 else "medium",
                "section_id": "sec-trends",
                "metric_before": round(om1, 1), "metric_after": round(om0, 1), "metric_unit": "%",
            })

        if om0 is not None and om0 < 0 and (om1 is None or om1 >= 0):
            anomalies.append({
                "id": "operating_loss", "category": "profitability",
                "title": "Operating Loss Emerged",
                "description": f"Company swung to an operating loss (margin: {om0:.1f}%).",
                "severity": "high", "section_id": "sec-trends",
                "metric_before": round(om1, 1) if om1 else None,
                "metric_after":  round(om0, 1), "metric_unit": "%",
            })

        ni0 = income[0].get("net_income")
        ni1 = income[1].get("net_income")
        if ni0 is not None and ni1 is not None and ni1 > 0:
            decline = (ni1 - ni0) / abs(ni1) * 100
            if decline > 40:
                anomalies.append({
                    "id": "net_income_collapse", "category": "profitability",
                    "title": "Net Income Collapse",
                    "description": f"Net income fell {decline:.0f}% year over year.",
                    "severity": "high" if decline > 70 else "medium",
                    "section_id": "sec-trends",
                    "metric_before": round(ni1/1e9, 2) if abs(ni1) >= 1e9 else round(ni1/1e6, 1),
                    "metric_after":  round(ni0/1e9, 2) if abs(ni0) >= 1e9 else round(ni0/1e6, 1),
                    "metric_unit": "B" if abs(ni1) >= 1e9 else "M",
                })

    # ── Cash flow ─────────────────────────────────────────────────────────────
    if len(cashflow) >= 2:
        fcf0 = cashflow[0].get("free_cash_flow")
        fcf1 = cashflow[1].get("free_cash_flow")
        if fcf0 is not None and fcf1 is not None:
            if fcf0 < 0 and fcf1 > 0:
                anomalies.append({
                    "id": "fcf_negative", "category": "cashflow",
                    "title": "Free Cash Flow Turned Negative",
                    "description": f"FCF turned negative (${fcf0/1e9:.2f}B) from positive (${fcf1/1e9:.2f}B) last year.",
                    "severity": "high", "section_id": "sec-trends",
                    "metric_before": round(fcf1/1e9, 2), "metric_after": round(fcf0/1e9, 2), "metric_unit": "B",
                })
            elif fcf0 >= 0 and fcf1 != 0:
                fcf_change = (fcf0 - fcf1) / abs(fcf1) * 100
                if fcf_change < -40:
                    anomalies.append({
                        "id": "fcf_decline", "category": "cashflow",
                        "title": "Free Cash Flow Decline",
                        "description": f"Free cash flow declined {abs(fcf_change):.0f}% year over year.",
                        "severity": "medium", "section_id": "sec-trends",
                        "metric_before": round(fcf1/1e9, 2) if abs(fcf1) >= 1e9 else round(fcf1/1e6, 1),
                        "metric_after":  round(fcf0/1e9, 2) if abs(fcf0) >= 1e9 else round(fcf0/1e6, 1),
                        "metric_unit": "B" if abs(fcf1) >= 1e9 else "M",
                    })

        cap0 = cashflow[0].get("capital_expenditure")
        cap1 = cashflow[1].get("capital_expenditure")
        if cap0 and cap1 and cap1 != 0:
            cap0_abs = abs(cap0)
            cap1_abs = abs(cap1)
            if cap0_abs > 0 and cap1_abs > 0:
                capex_change = (cap0_abs - cap1_abs) / cap1_abs * 100
                if capex_change > 50:
                    anomalies.append({
                        "id": "capex_spike", "category": "cashflow",
                        "title": "Capital Expenditure Spike",
                        "description": f"CapEx increased {capex_change:.0f}% year over year, potentially impacting free cash flow.",
                        "severity": "low", "section_id": "sec-trends",
                        "metric_before": round(cap1_abs/1e9, 2) if cap1_abs >= 1e9 else round(cap1_abs/1e6, 1),
                        "metric_after":  round(cap0_abs/1e9, 2) if cap0_abs >= 1e9 else round(cap0_abs/1e6, 1),
                        "metric_unit": "B" if cap1_abs >= 1e9 else "M",
                    })

    # ── Debt ──────────────────────────────────────────────────────────────────
    if len(balance) >= 2:
        debt0 = balance[0].get("total_debt")
        debt1 = balance[1].get("total_debt")
        eq0   = balance[0].get("shareholders_equity")
        eq1   = balance[1].get("shareholders_equity")

        if debt0 is not None and debt1 is not None and debt1 > 0:
            debt_change = (debt0 - debt1) / debt1 * 100
            if debt_change > 30:
                anomalies.append({
                    "id": "debt_surge", "category": "debt",
                    "title": "Rapid Debt Increase",
                    "description": f"Total debt increased {debt_change:.0f}% year over year.",
                    "severity": "high" if debt_change > 60 else "medium",
                    "section_id": "sec-ownership",
                    "metric_before": round(debt1/1e9, 2) if debt1 >= 1e9 else round(debt1/1e6, 1),
                    "metric_after":  round(debt0/1e9, 2) if debt0 >= 1e9 else round(debt0/1e6, 1),
                    "metric_unit": "B" if debt1 >= 1e9 else "M",
                })

        if debt0 and eq0 and eq0 > 0 and debt1 and eq1 and eq1 > 0:
            de0 = debt0 / eq0
            de1 = debt1 / eq1
            if de0 > de1 * 1.5 and de0 > 1.0:
                anomalies.append({
                    "id": "de_deterioration", "category": "debt",
                    "title": "Worsening Leverage",
                    "description": f"Debt-to-equity ratio worsened from {de1:.1f}x to {de0:.1f}x.",
                    "severity": "medium", "section_id": "sec-ownership",
                    "metric_before": round(de1, 1), "metric_after": round(de0, 1), "metric_unit": "x",
                })

    # ── Working capital ───────────────────────────────────────────────────────
    if len(balance) >= 2 and len(income) >= 2:
        rec0 = balance[0].get("trade_and_non_trade_receivables")
        rec1 = balance[1].get("trade_and_non_trade_receivables")
        rev0 = income[0].get("revenue")
        rev1 = income[1].get("revenue")
        if rec0 and rec1 and rec1 > 0 and rev0 and rev1 and rev1 > 0:
            rec_growth = (rec0 - rec1) / rec1 * 100
            rev_growth = (rev0 - rev1) / rev1 * 100
            if rec_growth > rev_growth + 20 and rec_growth > 20:
                anomalies.append({
                    "id": "receivables_surge", "category": "working_capital",
                    "title": "Receivables Growing Faster Than Revenue",
                    "description": f"Receivables grew {rec_growth:.0f}% while revenue grew {rev_growth:.0f}%, which may indicate collection issues.",
                    "severity": "medium", "section_id": "sec-statements",
                    "metric_before": round(rev_growth, 1), "metric_after": round(rec_growth, 1), "metric_unit": "%",
                })

    # ── Sort & deduplicate ────────────────────────────────────────────────────
    sev_order = {"high": 0, "medium": 1, "low": 2}
    anomalies.sort(key=lambda x: sev_order.get(x["severity"], 3))
    seen:   set[str]  = set()
    unique: list[dict] = []
    for a in anomalies:
        if a["id"] not in seen:
            seen.add(a["id"])
            unique.append(a)
    return unique
