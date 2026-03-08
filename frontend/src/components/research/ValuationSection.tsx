"use client";
import { FinancialMetrics, CompanyProfile } from "@/lib/api";

function fmt(n: number | undefined | null, dec = 2): string {
  if (n == null) return "—";
  return n.toFixed(dec);
}

interface ValCard { label: string; value: string; bench?: string; color?: "green" | "red" | "neutral" }

function badge(v: number | undefined | null, good: number, bad: number, lower = false): "green" | "red" | "neutral" {
  if (v == null) return "neutral";
  if (lower) return v < good ? "green" : v > bad ? "red" : "neutral";
  return v > good ? "green" : v < bad ? "red" : "neutral";
}

export default function ValuationSection({ metrics, profile }: { metrics: FinancialMetrics | null; profile: CompanyProfile }) {
  const m = metrics;
  const p = profile;

  const cards: ValCard[] = [
    { label: "P/E Ratio",       value: fmt(m?.price_to_earnings_ratio ?? p.pe_ratio, 1),       bench: "S&P avg ~22×",   color: badge(m?.price_to_earnings_ratio ?? p.pe_ratio, 30, 10, true) },
    { label: "Forward P/E",     value: fmt(p.forward_pe, 1),                                    bench: "Fwd earnings",   color: badge(p.forward_pe, 25, 10, true) },
    { label: "PEG Ratio",       value: fmt(m?.peg_ratio ?? p.peg_ratio, 2),                     bench: "<1 undervalued", color: badge(m?.peg_ratio ?? p.peg_ratio, 1, 2, true) },
    { label: "EV / EBITDA",     value: fmt(m?.enterprise_value_to_ebitda_ratio ?? p.ev_ebitda, 1), bench: "< 15 good",  color: badge(m?.enterprise_value_to_ebitda_ratio ?? p.ev_ebitda, 10, 20, true) },
    { label: "EV / Revenue",    value: fmt(m?.enterprise_value_to_revenue_ratio ?? p.ev_revenue, 2), bench: "< 5 good", color: "neutral" },
    { label: "P / Sales",       value: fmt(m?.price_to_sales_ratio ?? p.price_to_sales, 2),     bench: "< 4 good",      color: badge(m?.price_to_sales_ratio ?? p.price_to_sales, 2, 6, true) },
    { label: "P / Book",        value: fmt(m?.price_to_book_ratio  ?? p.price_to_book, 2),      bench: "< 3 cheap",     color: "neutral" },
    { label: "FCF Yield",       value: m?.free_cash_flow_yield != null ? `${(m.free_cash_flow_yield * 100).toFixed(1)}%` : "—", bench: "> 4% good", color: badge(m?.free_cash_flow_yield != null ? m.free_cash_flow_yield * 100 : null, 4, 1) },
    { label: "Dividend Yield",  value: p.dividend_yield != null ? `${(p.dividend_yield * 100).toFixed(2)}%` : "—", color: "neutral" },
    { label: "Beta",            value: fmt(p.beta, 2),                                           bench: "vs S&P 1.0",    color: "neutral" },
    { label: "Short % Float",   value: p.short_pct_float != null ? `${(p.short_pct_float * 100).toFixed(1)}%` : "—", color: "neutral" },
    { label: "Payout Ratio",    value: m?.payout_ratio != null ? `${(m.payout_ratio * 100).toFixed(1)}%` : "—", color: "neutral" },
  ];

  const colorClass = { green: "text-emerald-400", red: "text-red-400", neutral: "text-zinc-200" };

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
      {cards.map(c => (
        <div key={c.label} className="bg-zinc-800/50 border border-zinc-700/40 rounded-xl p-4">
          <div className="text-xs text-zinc-500 mb-1">{c.label}</div>
          <div className={`text-xl font-bold font-mono tabular-nums ${colorClass[c.color ?? "neutral"]}`}>{c.value}</div>
          {c.bench && <div className="text-xs text-zinc-600 mt-1">{c.bench}</div>}
        </div>
      ))}
    </div>
  );
}
