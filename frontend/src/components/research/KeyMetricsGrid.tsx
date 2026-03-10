"use client";
import {
  ResearchData, FinancialMetrics, CompanyProfile,
  PeerMetrics, MetricsHistory, IncomeStatement, CashFlowStatement,
} from "@/lib/api";

// --- Formatters ---
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

// --- Inline SVG Sparkline ---
function Sparkline({ values }: { values: (number | null | undefined)[] }) {
  const clean = values.filter((v): v is number => v != null && isFinite(v));
  if (clean.length < 2) return <span className="w-[60px] inline-block" />;
  const min = Math.min(...clean);
  const max = Math.max(...clean);
  const range = max - min || 1;
  const W = 60, H = 16, pad = 2;
  const pts = clean.map((v, i) => {
    const x = pad + (i / (clean.length - 1)) * (W - pad * 2);
    const y = pad + (1 - (v - min) / range) * (H - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  const up = clean[clean.length - 1] >= clean[0];
  return (
    <svg width={W} height={H} className="inline-block align-middle shrink-0">
      <polyline
        points={pts} fill="none"
        stroke={up ? "#10b981" : "#f87171"}
        strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round"
      />
    </svg>
  );
}

// --- Percentile helpers ---
function calcPctile(
  val: number | null | undefined,
  peers: number[],
  lowerBetter = false,
): number | null {
  if (val == null || peers.length === 0) return null;
  const below = peers.filter(p => lowerBetter ? p > val : p < val).length;
  return Math.round((below / peers.length) * 100);
}

function PctBadge({ p: pct }: { p: number | null }) {
  if (pct == null) return null;
  const cls =
    pct >= 70 ? "bg-emerald-900/60 text-emerald-400" :
    pct <= 30 ? "bg-red-900/60 text-red-400" :
    "bg-zinc-700/60 text-zinc-400";
  return (
    <span className={`text-[9px] font-mono px-1 py-px rounded leading-tight ${cls}`}>
      {pct}p
    </span>
  );
}

// --- Row & Table ---
type Color = "green" | "red" | "neutral" | "blue";

interface RowDef {
  label: string;
  value: string;
  color?: Color;
  sparkData?: (number | null | undefined)[];
  badge?: number | null;
}

function MetricRow({ label, value, color = "neutral", sparkData, badge }: RowDef) {
  const valCls =
    color === "green" ? "text-emerald-400" :
    color === "red"   ? "text-red-400"     :
    color === "blue"  ? "text-blue-400"    : "text-zinc-200";
  return (
    <tr className="border-b border-zinc-800/50 last:border-0 hover:bg-zinc-800/20 transition-colors">
      <td className="py-1.5 pl-3 pr-2 text-[11px] text-zinc-400 whitespace-nowrap">{label}</td>
      <td className={`py-1.5 pr-2 text-[11px] font-mono tabular-nums text-right ${valCls}`}>{value}</td>
      <td className="py-1.5 pr-2 text-right w-10">
        <PctBadge p={badge ?? null} />
      </td>
      <td className="py-1.5 pr-3 text-right w-[68px]">
        {sparkData && sparkData.filter(v => v != null).length >= 2
          ? <Sparkline values={sparkData} />
          : <span className="w-[60px] inline-block" />}
      </td>
    </tr>
  );
}

function MetricTable({ title, rows }: { title: string; rows: RowDef[] }) {
  const visible = rows.filter(r => r.value !== "—");
  if (!visible.length) return null;
  return (
    <div className="bg-zinc-800/40 rounded-xl overflow-hidden">
      <div className="px-3 py-2 border-b border-zinc-700/40">
        <span className="text-[11px] font-semibold text-zinc-300 uppercase tracking-wider">{title}</span>
      </div>
      <table className="w-full">
        <colgroup>
          <col />
          <col style={{ width: "18%" }} />
          <col style={{ width: "40px" }} />
          <col style={{ width: "68px" }} />
        </colgroup>
        <thead>
          <tr>
            <th className="pl-3 pr-2 pt-1.5 pb-0.5 text-[10px] text-zinc-600 font-normal text-left">Metric</th>
            <th className="pr-2 pt-1.5 pb-0.5 text-[10px] text-zinc-600 font-normal text-right">Value</th>
            <th className="pr-2 pt-1.5 pb-0.5 text-[10px] text-zinc-600 font-normal text-right">Peers</th>
            <th className="pr-3 pt-1.5 pb-0.5 text-[10px] text-zinc-600 font-normal text-right">Trend</th>
          </tr>
        </thead>
        <tbody>
          {visible.map(r => <MetricRow key={r.label} {...r} />)}
        </tbody>
      </table>
    </div>
  );
}

// --- Color helpers ---
function pctColor(v: number | null | undefined): Color {
  return v == null ? "neutral" : v >= 0 ? "green" : "red";
}
function threshColor(
  v: number | null | undefined,
  good: number,
  ok: number,
  lowerBetter = false,
): Color {
  if (v == null) return "neutral";
  if (lowerBetter) return v <= good ? "green" : v <= ok ? "neutral" : "red";
  return v >= good ? "green" : v >= ok ? "neutral" : "red";
}

// --- Main ---
export default function KeyMetricsGrid({ data }: { data: ResearchData }) {
  const m    = data.metrics.snapshot as FinancialMetrics | null;
  const p    = data.overview.profile as CompanyProfile;
  const ttm  = data.financials.income_ttm;
  const bttm = data.financials.balance_ttm;
  const cttm = data.financials.cashflow_ttm;

  const peers  = data.research.peers as PeerMetrics[];
  // history arrives newest-first; reverse for chronological sparklines
  const mhAnn  = [...data.metrics.history_annual].reverse()    as MetricsHistory[];
  const incAnn = [...data.financials.income_annual].reverse()  as IncomeStatement[];
  const cfAnn  = [...data.financials.cashflow_annual].reverse() as CashFlowStatement[];

  const mhSpark  = (key: keyof MetricsHistory)    => mhAnn.map(r  => r[key]  as number | null);
  const incSpark = (key: keyof IncomeStatement)   => incAnn.map(r => r[key] as number | null);
  const cfSpark  = (key: keyof CashFlowStatement) => cfAnn.map(r  => r[key] as number | null);
  const peerArr  = (key: keyof PeerMetrics) =>
    peers.map(r => r[key] as number | undefined).filter((v): v is number => v != null);

  // Derived values
  const revenue   = ttm?.revenue;
  const netIncome = ttm?.net_income;
  const ebitda    = ttm?.ebitda;
  const fcf       = cttm?.free_cash_flow;
  const eps       = ttm?.earnings_per_share_diluted ?? ttm?.earnings_per_share;
  const totalDebt = bttm?.total_debt;
  const cashEq    = bttm?.cash_and_equivalents;
  const equity    = bttm?.shareholders_equity;

  const grossMarginV  = m?.gross_margin     ?? (p.gross_margins     != null ? p.gross_margins     * 100 : null);
  const opMarginV     = m?.operating_margin ?? (p.operating_margins != null ? p.operating_margins * 100 : null);
  const netMarginV    = m?.net_margin       ?? (p.profit_margins    != null ? p.profit_margins    * 100 : null);
  const roeV          = m?.return_on_equity ?? (p.roe != null ? p.roe * 100 : null);
  const roaV          = m?.return_on_assets ?? (p.roa != null ? p.roa * 100 : null);
  const roicV         = m?.return_on_invested_capital ?? null;
  const ebitdaMarginV = ebitda != null && revenue ? (ebitda / revenue) * 100 : null;

  const revGrowthV    = m?.revenue_growth               ?? (p.revenue_growth  != null ? p.revenue_growth  * 100 : null);
  const epsGrowthV    = m?.earnings_per_share_growth    ?? null;
  const earnGrowthV   = m?.earnings_growth              ?? (p.earnings_growth != null ? p.earnings_growth * 100 : null);
  const fcfGrowthV    = m?.free_cash_flow_growth        ?? null;
  const opIncGrowthV  = m?.operating_income_growth      ?? null;
  const ebitdaGrowthV = m?.ebitda_growth                ?? null;
  const bvGrowthV     = m?.book_value_growth            ?? null;

  const peV       = m?.price_to_earnings_ratio        ?? p.pe_ratio      ?? null;
  const pbV       = m?.price_to_book_ratio            ?? p.price_to_book ?? null;
  const psV       = m?.price_to_sales_ratio           ?? p.price_to_sales ?? null;
  const evEbitdaV = m?.enterprise_value_to_ebitda_ratio ?? p.ev_ebitda   ?? null;
  const evRevV    = m?.enterprise_value_to_revenue_ratio ?? p.ev_revenue  ?? null;
  const fcfYieldV = m?.free_cash_flow_yield ?? null;
  const divYieldV = p.dividend_yield != null ? p.dividend_yield * 100 : null;

  const crV    = m?.current_ratio  ?? p.current_ratio  ?? null;
  const qrV    = m?.quick_ratio    ?? p.quick_ratio     ?? null;
  const deqV   = m?.debt_to_equity ?? p.debt_to_equity ?? null;
  const intCovV = m?.interest_coverage ?? null;

  const sections: { title: string; rows: RowDef[] }[] = [
    {
      title: "Income (TTM)",
      rows: [
        { label: "Revenue",        value: fmtLarge(revenue),    color: "blue",          sparkData: incSpark("revenue") },
        { label: "Net Income",     value: fmtLarge(netIncome),  color: pctColor(netIncome), sparkData: incSpark("net_income") },
        { label: "EBITDA",         value: fmtLarge(ebitda),     color: "neutral",       sparkData: incSpark("ebitda") },
        { label: "Free Cash Flow", value: fmtLarge(fcf),        color: pctColor(fcf),   sparkData: cfSpark("free_cash_flow") },
        { label: "EPS (Diluted)",  value: eps != null ? `$${fmtNum(eps)}` : "—", color: pctColor(eps), sparkData: incSpark("earnings_per_share_diluted") },
      ],
    },
    {
      title: "Profitability",
      rows: [
        { label: "Gross Margin",     value: fmtPct(grossMarginV),  color: threshColor(grossMarginV, 40, 20),  sparkData: mhSpark("gross_margin"),               badge: calcPctile(grossMarginV, peerArr("gross_margin")) },
        { label: "Operating Margin", value: fmtPct(opMarginV),     color: threshColor(opMarginV, 15, 5),      sparkData: mhSpark("operating_margin"),            badge: calcPctile(opMarginV, peerArr("operating_margin")) },
        { label: "Net Margin",       value: fmtPct(netMarginV),    color: threshColor(netMarginV, 10, 0),     sparkData: mhSpark("net_margin"),                  badge: calcPctile(netMarginV, peerArr("net_margin")) },
        { label: "EBITDA Margin",    value: fmtPct(ebitdaMarginV), color: threshColor(ebitdaMarginV, 20, 10) },
        { label: "ROE",              value: fmtPct(roeV),          color: threshColor(roeV, 15, 10),          sparkData: mhSpark("return_on_equity") },
        { label: "ROA",              value: fmtPct(roaV),          color: threshColor(roaV, 8, 5),            sparkData: mhSpark("return_on_assets") },
        { label: "ROIC",             value: fmtPct(roicV),         color: threshColor(roicV, 12, 8),          sparkData: mhSpark("return_on_invested_capital"),  badge: calcPctile(roicV, peerArr("roic")) },
      ],
    },
    {
      title: "Growth (YoY)",
      rows: [
        { label: "Revenue",      value: fmtPct(revGrowthV),    color: pctColor(revGrowthV),    sparkData: mhSpark("revenue_growth"),            badge: calcPctile(revGrowthV, peerArr("revenue_growth")) },
        { label: "EPS",          value: fmtPct(epsGrowthV),    color: pctColor(epsGrowthV),    sparkData: mhSpark("earnings_per_share_growth") },
        { label: "Earnings",     value: fmtPct(earnGrowthV),   color: pctColor(earnGrowthV),   sparkData: mhSpark("earnings_growth") },
        { label: "FCF",          value: fmtPct(fcfGrowthV),    color: pctColor(fcfGrowthV),    sparkData: mhSpark("free_cash_flow_growth") },
        { label: "Op. Income",   value: fmtPct(opIncGrowthV),  color: pctColor(opIncGrowthV),  sparkData: mhSpark("operating_income_growth") },
        { label: "EBITDA",       value: fmtPct(ebitdaGrowthV), color: pctColor(ebitdaGrowthV), sparkData: mhSpark("ebitda_growth") },
        { label: "Book Value",   value: fmtPct(bvGrowthV),     color: pctColor(bvGrowthV),     sparkData: mhSpark("book_value_growth") },
      ],
    },
    {
      title: "Valuation",
      rows: [
        { label: "P/E (TTM)",   value: fmtNum(peV, 1),       color: "neutral", sparkData: mhSpark("price_to_earnings_ratio"),       badge: calcPctile(peV, peerArr("pe"), true) },
        { label: "Fwd P/E",     value: fmtNum(p.forward_pe, 1), color: "neutral" },
        { label: "P/B",         value: fmtNum(pbV, 1),        color: "neutral" },
        { label: "P/S",         value: fmtNum(psV, 1),        color: "neutral", sparkData: mhSpark("price_to_sales_ratio") },
        { label: "EV/EBITDA",   value: fmtNum(evEbitdaV, 1),  color: "neutral", sparkData: mhSpark("enterprise_value_to_ebitda_ratio"), badge: calcPctile(evEbitdaV, peerArr("ev_ebitda"), true) },
        { label: "EV/Revenue",  value: fmtNum(evRevV, 1),     color: "neutral" },
        { label: "PEG",         value: fmtNum(m?.peg_ratio ?? p.peg_ratio, 2), color: (m?.peg_ratio ?? p.peg_ratio) != null ? ((m?.peg_ratio ?? p.peg_ratio)! < 1 ? "green" : (m?.peg_ratio ?? p.peg_ratio)! < 2 ? "neutral" : "red") : "neutral" },
        { label: "FCF Yield",   value: fmtPct(fcfYieldV),     color: threshColor(fcfYieldV, 5, 3), sparkData: mhSpark("free_cash_flow_yield") },
        { label: "Div. Yield",  value: fmtPct(divYieldV),     color: "neutral" },
        { label: "Payout Ratio",value: fmtPct(m?.payout_ratio), color: "neutral" },
      ],
    },
    {
      title: "Financial Health",
      rows: [
        { label: "Current Ratio",  value: fmtNum(crV, 2),       color: threshColor(crV, 1.5, 1.0),       sparkData: mhSpark("current_ratio") },
        { label: "Quick Ratio",    value: fmtNum(qrV, 2),       color: threshColor(qrV, 1.0, 0.7) },
        { label: "Cash Ratio",     value: fmtNum(m?.cash_ratio, 2), color: "neutral" },
        { label: "Debt / Equity",  value: fmtNum(deqV, 2),      color: threshColor(deqV, 1.0, 2.0, true), sparkData: mhSpark("debt_to_equity") },
        { label: "Debt / Assets",  value: fmtPct(m?.debt_to_assets), color: "neutral" },
        { label: "Int. Coverage",  value: fmtNum(intCovV, 1),   color: threshColor(intCovV, 3, 1.5),     sparkData: mhSpark("interest_coverage") },
        { label: "Net Debt",       value: totalDebt != null && cashEq != null ? fmtLarge(totalDebt - cashEq) : "—", color: "neutral" },
        { label: "Equity (BV)",    value: fmtLarge(equity),     color: "neutral" },
      ],
    },
    {
      title: "Ownership & Short",
      rows: [
        { label: "Book Value/Share", value: m?.book_value_per_share     != null ? `$${fmtNum(m.book_value_per_share, 2)}`     : "—", color: "neutral" },
        { label: "FCF/Share",        value: m?.free_cash_flow_per_share != null ? `$${fmtNum(m.free_cash_flow_per_share, 2)}` : "—", color: "neutral" },
        { label: "Inst. Ownership",  value: p.held_pct_institutions != null ? fmtPct(p.held_pct_institutions * 100) : "—",          color: "neutral" },
        { label: "Insider Ownership",value: p.held_pct_insiders     != null ? fmtPct(p.held_pct_insiders * 100)     : "—",          color: "neutral" },
        { label: "Short % Float",    value: p.short_pct_float       != null ? fmtPct(p.short_pct_float * 100)       : "—",          color: p.short_pct_float != null && p.short_pct_float * 100 > 10 ? "red" : "neutral" },
        { label: "Short Ratio",      value: p.short_ratio           != null ? fmtNum(p.short_ratio, 2)               : "—",          color: "neutral" },
      ],
    },
  ];

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {sections.map(s => <MetricTable key={s.title} title={s.title} rows={s.rows} />)}
    </div>
  );
}
