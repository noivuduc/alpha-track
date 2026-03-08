"use client";
import { ResearchData, FinancialMetrics, CompanyProfile } from "@/lib/api";
import { useState } from "react";

function fmtLarge(n: number | undefined | null): string {
  if (n == null) return "—";
  if (Math.abs(n) >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (Math.abs(n) >= 1e9)  return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6)  return `$${(n / 1e6).toFixed(2)}M`;
  return `$${n.toLocaleString()}`;
}
function fmtPct(n: number | undefined | null, isDecimal = false): string {
  if (n == null) return "—";
  const v = isDecimal ? n * 100 : n;
  return `${v.toFixed(1)}%`;
}
function fmtNum(n: number | undefined | null, d = 2): string {
  if (n == null) return "—";
  return n.toFixed(d);
}

type Color = "green" | "red" | "blue" | "neutral";

interface MetricDef {
  label: string;
  value: string;
  sub?: string;
  color?: Color;
}

function colorFor(v: number | null | undefined, lowGood?: boolean): Color {
  if (v == null) return "neutral";
  if (lowGood) return v < 0.5 ? "green" : v < 1.5 ? "neutral" : "red";
  return v > 0 ? "green" : "red";
}

function MetricCard({ label, value, sub, color = "neutral" }: MetricDef) {
  const textColor =
    color === "green" ? "text-emerald-400" :
    color === "red"   ? "text-red-400"     :
    color === "blue"  ? "text-blue-400"    : "text-zinc-100";
  return (
    <div className="bg-zinc-800/60 border border-zinc-700/50 rounded-xl p-3.5 flex flex-col gap-1">
      <div className="text-xs text-zinc-500 leading-tight">{label}</div>
      <div className={`text-lg font-bold font-mono tabular-nums ${textColor}`}>{value}</div>
      {sub && <div className="text-[10px] text-zinc-600 leading-tight">{sub}</div>}
    </div>
  );
}

function Section({ title, metrics }: { title: string; metrics: MetricDef[] }) {
  const visible = metrics.filter(m => m.value !== "—");
  if (!visible.length) return null;
  return (
    <div>
      <div className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2 px-0.5">{title}</div>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-2.5">
        {visible.map(c => <MetricCard key={c.label} {...c} />)}
      </div>
    </div>
  );
}

function buildMetrics(data: ResearchData): { title: string; metrics: MetricDef[] }[] {
  const m = data.metrics as FinancialMetrics | null;
  const p = data.profile as CompanyProfile;
  const ttm  = data.income_ttm;
  const bttm = data.balance_ttm;
  const cttm = data.cashflow_ttm;

  // Helper to prefer metrics API, fallback to profile
  const pctM = (mKey: keyof FinancialMetrics, pKey: keyof CompanyProfile, decimalInProfile = true) => {
    const mv = m?.[mKey] as number | undefined;
    const pv = p[pKey] as number | undefined;
    return mv != null ? fmtPct(mv) : fmtPct(pv, decimalInProfile);
  };

  const revenue    = ttm?.revenue;
  const netIncome  = ttm?.net_income;
  const ebitda     = ttm?.ebitda;
  const fcf        = cttm?.free_cash_flow;
  const eps        = ttm?.earnings_per_share_diluted ?? ttm?.earnings_per_share;
  const totalDebt  = bttm?.total_debt;
  const cashEq     = bttm?.cash_and_equivalents;
  const equity     = bttm?.shareholders_equity;

  const grossMargin   = m?.gross_margin   != null ? fmtPct(m.gross_margin)   : fmtPct(p.gross_margins,    true);
  const opMargin      = m?.operating_margin != null ? fmtPct(m.operating_margin) : fmtPct(p.operating_margins, true);
  const netMargin     = m?.net_margin     != null ? fmtPct(m.net_margin)     : fmtPct(p.profit_margins,   true);
  const roe           = m?.return_on_equity != null ? fmtPct(m.return_on_equity) : fmtPct(p.roe, true);
  const roa           = m?.return_on_assets != null ? fmtPct(m.return_on_assets) : fmtPct(p.roa, true);
  const roic          = m?.return_on_invested_capital != null ? fmtPct(m.return_on_invested_capital) : "—";
  const ebitdaMargin  = ebitda != null && revenue ? fmtPct((ebitda / revenue) * 100) : "—";

  const revGrowth = m?.revenue_growth != null ? fmtPct(m.revenue_growth)
    : p.revenue_growth != null ? fmtPct(p.revenue_growth * 100) : "—";
  const epsGrowth = m?.earnings_per_share_growth != null ? fmtPct(m.earnings_per_share_growth) : "—";
  const earnGrowth = m?.earnings_growth != null ? fmtPct(m.earnings_growth)
    : p.earnings_growth != null ? fmtPct(p.earnings_growth * 100) : "—";
  const fcfGrowth = m?.free_cash_flow_growth != null ? fmtPct(m.free_cash_flow_growth) : "—";
  const ebitdaGrowth = m?.ebitda_growth != null ? fmtPct(m.ebitda_growth) : "—";

  const pe          = fmtNum(m?.price_to_earnings_ratio ?? p.pe_ratio, 1);
  const fwdPe       = fmtNum(p.forward_pe, 1);
  const pb          = fmtNum(m?.price_to_book_ratio ?? p.price_to_book, 1);
  const ps          = fmtNum(m?.price_to_sales_ratio ?? p.price_to_sales, 1);
  const evEbitda    = fmtNum(m?.enterprise_value_to_ebitda_ratio ?? p.ev_ebitda, 1);
  const evRev       = fmtNum(m?.enterprise_value_to_revenue_ratio ?? p.ev_revenue, 1);
  const peg         = fmtNum(m?.peg_ratio ?? p.peg_ratio, 2);
  const fcfYield    = m?.free_cash_flow_yield != null ? fmtPct(m.free_cash_flow_yield) : "—";
  const divYield    = p.dividend_yield != null ? fmtPct(p.dividend_yield * 100) : "—";
  const payoutRatio = m?.payout_ratio != null ? fmtPct(m.payout_ratio) : "—";

  const currentRatio = fmtNum(m?.current_ratio ?? p.current_ratio, 2);
  const quickRatio   = fmtNum(m?.quick_ratio ?? p.quick_ratio, 2);
  const cashRatio    = m?.cash_ratio != null ? fmtNum(m.cash_ratio, 2) : "—";
  const debtEq       = fmtNum(m?.debt_to_equity ?? p.debt_to_equity, 2);
  const debtAssets   = m?.debt_to_assets != null ? fmtPct(m.debt_to_assets) : "—";
  const intCoverage  = m?.interest_coverage != null ? fmtNum(m.interest_coverage, 1) : "—";
  const netDebt      = totalDebt != null && cashEq != null ? fmtLarge(totalDebt - cashEq) : "—";

  const bvps   = m?.book_value_per_share    != null ? `$${fmtNum(m.book_value_per_share, 2)}` : "—";
  const fcfps  = m?.free_cash_flow_per_share != null ? `$${fmtNum(m.free_cash_flow_per_share, 2)}` : "—";
  const shortRatio = p.short_ratio != null ? fmtNum(p.short_ratio, 2) : "—";
  const shortPct   = p.short_pct_float != null ? fmtPct(p.short_pct_float * 100) : "—";

  return [
    {
      title: "Income (TTM)",
      metrics: [
        { label: "Revenue",        value: fmtLarge(revenue), color: "blue" as Color },
        { label: "Net Income",     value: fmtLarge(netIncome), color: colorFor(netIncome) },
        { label: "EBITDA",         value: fmtLarge(ebitda) },
        { label: "Free Cash Flow", value: fmtLarge(fcf), color: colorFor(fcf) },
        { label: "EPS (Diluted)",  value: eps != null ? `$${fmtNum(eps)}` : "—", color: colorFor(eps) },
      ],
    },
    {
      title: "Profitability",
      metrics: [
        { label: "Gross Margin",     value: grossMargin,  color: "neutral" as Color },
        { label: "Operating Margin", value: opMargin,     color: opMargin !== "—" && parseFloat(opMargin) >= 0 ? "green" : "red" },
        { label: "Net Margin",       value: netMargin,    color: netMargin !== "—" && parseFloat(netMargin) >= 0 ? "green" : "red" },
        { label: "EBITDA Margin",    value: ebitdaMargin, color: "neutral" as Color },
        { label: "ROE",              value: roe,  color: roe  !== "—" && parseFloat(roe)  > 15 ? "green" : "neutral" },
        { label: "ROA",              value: roa,  color: roa  !== "—" && parseFloat(roa)  > 5  ? "green" : "neutral" },
        { label: "ROIC",             value: roic, color: roic !== "—" && parseFloat(roic) > 10 ? "green" : "neutral" },
      ],
    },
    {
      title: "Growth",
      metrics: [
        { label: "Revenue Growth",    value: revGrowth,   color: revGrowth   !== "—" ? (parseFloat(revGrowth)   >= 0 ? "green" : "red") : "neutral" },
        { label: "EPS Growth",        value: epsGrowth,   color: epsGrowth   !== "—" ? (parseFloat(epsGrowth)   >= 0 ? "green" : "red") : "neutral" },
        { label: "Earnings Growth",   value: earnGrowth,  color: earnGrowth  !== "—" ? (parseFloat(earnGrowth)  >= 0 ? "green" : "red") : "neutral" },
        { label: "FCF Growth",        value: fcfGrowth,   color: fcfGrowth   !== "—" ? (parseFloat(fcfGrowth)   >= 0 ? "green" : "red") : "neutral" },
        { label: "EBITDA Growth",     value: ebitdaGrowth,color: ebitdaGrowth !== "—" ? (parseFloat(ebitdaGrowth) >= 0 ? "green" : "red") : "neutral" },
      ],
    },
    {
      title: "Valuation",
      metrics: [
        { label: "P/E (TTM)",    value: pe,       color: "neutral" as Color },
        { label: "Fwd P/E",      value: fwdPe,    color: "neutral" as Color },
        { label: "P/B",          value: pb,        color: "neutral" as Color },
        { label: "P/S",          value: ps,        color: "neutral" as Color },
        { label: "EV/EBITDA",    value: evEbitda,  color: "neutral" as Color },
        { label: "EV/Revenue",   value: evRev,     color: "neutral" as Color },
        { label: "PEG",          value: peg,       color: peg !== "—" && parseFloat(peg) < 1 ? "green" : peg !== "—" && parseFloat(peg) < 2 ? "neutral" : "red" },
        { label: "FCF Yield",    value: fcfYield,  color: fcfYield !== "—" && parseFloat(fcfYield) > 3 ? "green" : "neutral" },
        { label: "Div. Yield",   value: divYield,  color: "neutral" as Color },
        { label: "Payout Ratio", value: payoutRatio, color: "neutral" as Color },
      ],
    },
    {
      title: "Financial Health",
      metrics: [
        { label: "Current Ratio",   value: currentRatio, color: currentRatio !== "—" && parseFloat(currentRatio) > 1.5 ? "green" : currentRatio !== "—" && parseFloat(currentRatio) > 1 ? "neutral" : "red" },
        { label: "Quick Ratio",     value: quickRatio,   color: quickRatio !== "—" && parseFloat(quickRatio) > 1 ? "green" : "neutral" },
        { label: "Cash Ratio",      value: cashRatio,    color: "neutral" as Color },
        { label: "Debt / Equity",   value: debtEq,       color: debtEq !== "—" && parseFloat(debtEq) < 1 ? "green" : debtEq !== "—" && parseFloat(debtEq) < 2 ? "neutral" : "red" },
        { label: "Debt / Assets",   value: debtAssets,   color: "neutral" as Color },
        { label: "Interest Coverage",value: intCoverage, color: intCoverage !== "—" && parseFloat(intCoverage) > 3 ? "green" : "neutral" },
        { label: "Net Debt",        value: netDebt,      color: "neutral" as Color },
        { label: "Equity (BV)",     value: fmtLarge(equity), color: "neutral" as Color },
      ],
    },
    {
      title: "Per Share & Short",
      metrics: [
        { label: "Book Value / Share", value: bvps,       color: "neutral" as Color },
        { label: "FCF / Share",        value: fcfps,      color: "neutral" as Color },
        { label: "Short Ratio",        value: shortRatio, color: "neutral" as Color },
        { label: "Short % Float",      value: shortPct,   color: shortPct !== "—" && parseFloat(shortPct) > 10 ? "red" : "neutral" },
        { label: "Inst. Ownership",    value: p.held_pct_institutions != null ? fmtPct(p.held_pct_institutions * 100) : "—", color: "neutral" as Color },
        { label: "Insider Ownership",  value: p.held_pct_insiders != null ? fmtPct(p.held_pct_insiders * 100) : "—", color: "neutral" as Color },
      ],
    },
  ];
}

export default function KeyMetricsGrid({ data }: { data: ResearchData }) {
  const [collapsed, setCollapsed] = useState(false);
  const sections = buildMetrics(data);

  return (
    <div className="space-y-5">
      {sections.map(s => <Section key={s.title} {...s} />)}
    </div>
  );
}
