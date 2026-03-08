"use client";
import { ResearchData } from "@/lib/api";

function fmtLarge(n: number | undefined | null): string {
  if (n == null) return "—";
  if (Math.abs(n) >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (Math.abs(n) >= 1e9)  return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6)  return `$${(n / 1e6).toFixed(2)}M`;
  return `$${n.toLocaleString()}`;
}

function fmtPct(n: number | undefined | null, multiply = false): string {
  if (n == null) return "—";
  const v = multiply ? n * 100 : n;
  return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
}

function fmtNum(n: number | undefined | null, decimals = 2): string {
  if (n == null) return "—";
  return n.toFixed(decimals);
}

interface MetricCardProps {
  label: string; value: string; sub?: string;
  color?: "green" | "red" | "blue" | "neutral";
}

function MetricCard({ label, value, sub, color = "neutral" }: MetricCardProps) {
  const textColor = color === "green" ? "text-emerald-400" : color === "red" ? "text-red-400" : color === "blue" ? "text-blue-400" : "text-zinc-100";
  return (
    <div className="bg-zinc-800/60 border border-zinc-700/50 rounded-xl p-4">
      <div className="text-xs text-zinc-500 mb-1.5">{label}</div>
      <div className={`text-xl font-bold font-mono tabular-nums ${textColor}`}>{value}</div>
      {sub && <div className="text-xs text-zinc-600 mt-1">{sub}</div>}
    </div>
  );
}

export default function KeyMetricsGrid({ data }: { data: ResearchData }) {
  const ttm  = data.income_ttm;
  const bttm = data.balance_ttm;
  const cttm = data.cashflow_ttm;
  const m    = data.metrics;
  const p    = data.profile;

  const revenue    = ttm?.revenue;
  const netIncome  = ttm?.net_income;
  const ebitda     = ttm?.ebitda ?? (ttm && ttm.ebit != null && ttm.net_income != null ? (ttm.ebit + (ttm.net_income - (ttm.ebit ?? 0))) : undefined);
  const fcf        = cttm?.free_cash_flow;
  const eps        = ttm?.earnings_per_share_diluted ?? ttm?.earnings_per_share;

  const grossMargin = m?.gross_margin     ?? (p.gross_margins     != null ? p.gross_margins * 100 : null);
  const opMargin    = m?.operating_margin ?? (p.operating_margins != null ? p.operating_margins * 100 : null);
  const netMargin   = m?.net_margin       ?? (p.profit_margins    != null ? p.profit_margins * 100 : null);
  const roe         = m?.return_on_equity ?? (p.roe               != null ? p.roe * 100 : null);
  const roic        = m?.return_on_invested_capital;
  const de          = m?.debt_to_equity   ?? p.debt_to_equity;
  const currRatio   = m?.current_ratio    ?? p.current_ratio;
  const revGrowth   = m?.revenue_growth   ?? (p.revenue_growth  != null ? p.revenue_growth * 100 : null);

  const cards: MetricCardProps[] = [
    { label: "Revenue (TTM)",   value: fmtLarge(revenue),   sub: revGrowth != null ? `${revGrowth >= 0 ? "▲" : "▼"} ${Math.abs(revGrowth).toFixed(1)}% YoY` : undefined, color: revGrowth != null ? (revGrowth >= 0 ? "green" : "red") : "neutral" },
    { label: "Net Income (TTM)",value: fmtLarge(netIncome), color: netIncome != null ? (netIncome >= 0 ? "green" : "red") : "neutral" },
    { label: "EBITDA (TTM)",    value: fmtLarge(ebitda) },
    { label: "Free Cash Flow",  value: fmtLarge(fcf),       color: fcf != null ? (fcf >= 0 ? "green" : "red") : "neutral" },
    { label: "EPS (Diluted)",   value: eps != null ? `$${fmtNum(eps)}` : "—",   color: eps != null ? (eps >= 0 ? "green" : "red") : "neutral" },
    { label: "Gross Margin",    value: grossMargin != null ? `${fmtNum(grossMargin, 1)}%` : "—" },
    { label: "Operating Margin",value: opMargin   != null ? `${fmtNum(opMargin, 1)}%`   : "—", color: opMargin != null ? (opMargin >= 0 ? "green" : "red") : "neutral" },
    { label: "Net Margin",      value: netMargin  != null ? `${fmtNum(netMargin, 1)}%`  : "—", color: netMargin != null ? (netMargin >= 0 ? "green" : "red") : "neutral" },
    { label: "ROE",             value: roe  != null ? `${fmtNum(roe, 1)}%`  : "—", color: roe  != null ? (roe  > 15 ? "green" : roe  > 0 ? "neutral" : "red") : "neutral" },
    { label: "ROIC",            value: roic != null ? `${fmtNum(roic, 1)}%` : "—", color: roic != null ? (roic > 10 ? "green" : roic > 0 ? "neutral" : "red") : "neutral" },
    { label: "Debt / Equity",   value: de   != null ? fmtNum(de, 2)         : "—", color: de   != null ? (de   < 1  ? "green" : de   < 2  ? "neutral" : "red") : "neutral" },
    { label: "Current Ratio",   value: currRatio != null ? fmtNum(currRatio, 2) : "—", color: currRatio != null ? (currRatio > 1.5 ? "green" : currRatio > 1 ? "neutral" : "red") : "neutral" },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-3">
      {cards.map(c => <MetricCard key={c.label} {...c} />)}
    </div>
  );
}
