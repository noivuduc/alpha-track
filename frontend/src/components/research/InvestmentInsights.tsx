"use client";
import { useMemo } from "react";
import { TrendingUp, TrendingDown, Zap, AlertTriangle } from "lucide-react";
import { ResearchData } from "@/lib/api";

interface Insight { text: string; strength?: "strong" | "moderate" | "weak"; }

function pct(n: number | undefined | null, mult = 1): number | null {
  if (n == null) return null;
  return n * mult;
}

function generateInsights(data: ResearchData): {
  bull: Insight[]; bear: Insight[]; catalysts: Insight[]; risks: Insight[];
} {
  const m  = data.metrics;
  const p  = data.profile;
  const ttm = data.income_ttm;
  const bttm = data.balance_ttm;
  const cttm = data.cashflow_ttm;
  const income = data.income;

  const bull: Insight[]     = [];
  const bear: Insight[]     = [];
  const catalysts: Insight[] = [];
  const risks: Insight[]    = [];

  // ─── Revenue & Growth ────────────────────────────────────────────────────
  const revGrowth = m?.revenue_growth ?? (p.revenue_growth != null ? p.revenue_growth : null);
  const revGrowthPct = revGrowth != null ? revGrowth * 100 : null;

  if (revGrowthPct != null && revGrowthPct > 20) {
    bull.push({ text: `Revenue growing at ${revGrowthPct.toFixed(0)}% YoY — well above average`, strength: "strong" });
  } else if (revGrowthPct != null && revGrowthPct > 8) {
    bull.push({ text: `Revenue growing at ${revGrowthPct.toFixed(0)}% YoY`, strength: "moderate" });
  } else if (revGrowthPct != null && revGrowthPct < 0) {
    bear.push({ text: `Revenue declining ${Math.abs(revGrowthPct).toFixed(0)}% YoY`, strength: "strong" });
  } else if (revGrowthPct != null && revGrowthPct < 5) {
    bear.push({ text: `Slow revenue growth of ${revGrowthPct.toFixed(0)}% YoY`, strength: "moderate" });
  }

  // Revenue deceleration
  if (income && income.length >= 3) {
    const r0 = income[0].revenue, r1 = income[1].revenue, r2 = income[2].revenue;
    if (r0 && r1 && r2 && r1 > 0 && r2 > 0) {
      const g1 = ((r1 - r2) / r2) * 100;
      const g0 = ((r0 - r1) / r1) * 100;
      if (g0 > g1 + 5) bull.push({ text: `Revenue growth accelerating (${g1.toFixed(0)}% → ${g0.toFixed(0)}%)`, strength: "moderate" });
      else if (g1 > g0 + 10) bear.push({ text: `Revenue growth decelerating (${g1.toFixed(0)}% → ${g0.toFixed(0)}%)`, strength: "moderate" });
    }
  }

  // ─── Margins ─────────────────────────────────────────────────────────────
  const grossM  = m?.gross_margin       ?? (p.gross_margins    != null ? p.gross_margins    : null);
  const opM     = m?.operating_margin   ?? (p.operating_margins != null ? p.operating_margins : null);
  const netM    = m?.net_margin         ?? (p.profit_margins   != null ? p.profit_margins   : null);

  if (grossM != null && grossM > 0.6) {
    bull.push({ text: `Exceptional gross margin of ${(grossM * 100).toFixed(0)}% indicates strong pricing power`, strength: "strong" });
  } else if (grossM != null && grossM > 0.4) {
    bull.push({ text: `Healthy gross margin of ${(grossM * 100).toFixed(0)}%`, strength: "moderate" });
  } else if (grossM != null && grossM < 0.2) {
    bear.push({ text: `Low gross margin of ${(grossM * 100).toFixed(0)}% limits profitability upside`, strength: "moderate" });
  }

  if (opM != null && opM > 0.25) {
    bull.push({ text: `High operating margin of ${(opM * 100).toFixed(0)}% demonstrating operational efficiency`, strength: "strong" });
  } else if (opM != null && opM < 0) {
    bear.push({ text: `Negative operating margin of ${(opM * 100).toFixed(0)}% — not yet operationally profitable`, strength: "strong" });
  }

  // ─── Free Cash Flow ───────────────────────────────────────────────────────
  const fcf = cttm?.free_cash_flow;
  const fcfYield = m?.free_cash_flow_yield;

  if (fcf != null && fcf > 0) {
    bull.push({ text: `Positive free cash flow generation${fcfYield != null ? ` with ${(fcfYield * 100).toFixed(1)}% FCF yield` : ""}`, strength: fcf > 1e9 ? "strong" : "moderate" });
  } else if (fcf != null && fcf < 0) {
    bear.push({ text: `Negative free cash flow — cash burn may require future financing`, strength: "moderate" });
  }

  // ─── ROIC / ROE ──────────────────────────────────────────────────────────
  const roic = m?.return_on_invested_capital;
  const roe  = m?.return_on_equity ?? (p.roe != null ? p.roe : null);

  if (roic != null && roic > 0.2) {
    bull.push({ text: `Strong ROIC of ${(roic * 100).toFixed(0)}% indicates efficient capital allocation`, strength: "strong" });
  } else if (roic != null && roic < 0.05) {
    bear.push({ text: `Low ROIC of ${(roic * 100).toFixed(0)}% suggests poor capital efficiency`, strength: "moderate" });
  }

  if (roe != null && roe > 0.25) {
    bull.push({ text: `High ROE of ${(roe * 100).toFixed(0)}%`, strength: "moderate" });
  }

  // ─── Balance Sheet ────────────────────────────────────────────────────────
  const deRatio    = m?.debt_to_equity ?? p.debt_to_equity;
  const currRatio  = m?.current_ratio  ?? p.current_ratio;
  const cash       = bttm?.cash_and_equivalents;
  const totalDebt  = bttm?.total_debt;

  if (deRatio != null && deRatio < 0.3) {
    bull.push({ text: `Low leverage (D/E: ${deRatio.toFixed(2)}) provides financial flexibility`, strength: "moderate" });
  } else if (deRatio != null && deRatio > 3) {
    bear.push({ text: `High debt-to-equity ratio of ${deRatio.toFixed(1)} increases financial risk`, strength: "strong" });
  }

  if (currRatio != null && currRatio > 2) {
    bull.push({ text: `Strong liquidity position (current ratio: ${currRatio.toFixed(1)})`, strength: "weak" });
  } else if (currRatio != null && currRatio < 1) {
    bear.push({ text: `Weak current ratio of ${currRatio.toFixed(1)} may signal near-term liquidity stress`, strength: "strong" });
  }

  // ─── Valuation ────────────────────────────────────────────────────────────
  const pe     = m?.price_to_earnings_ratio ?? p.pe_ratio;
  const fwdPe  = p.forward_pe;
  const evEb   = m?.enterprise_value_to_ebitda_ratio ?? p.ev_ebitda;
  const peg    = m?.peg_ratio ?? p.peg_ratio;

  if (pe != null && pe > 50) {
    bear.push({ text: `Premium valuation at ${pe.toFixed(0)}x P/E leaves little margin for error`, strength: "moderate" });
  }
  if (peg != null && peg < 1) {
    bull.push({ text: `PEG ratio of ${peg.toFixed(2)} suggests attractive growth-adjusted valuation`, strength: "moderate" });
  }
  if (fwdPe != null && pe != null && fwdPe < pe * 0.8) {
    bull.push({ text: `Forward P/E of ${fwdPe.toFixed(0)}x well below trailing P/E, implying earnings expansion`, strength: "moderate" });
  }

  // ─── Short Interest ──────────────────────────────────────────────────────
  const shortPct = p.short_pct_float;
  if (shortPct != null && shortPct > 0.15) {
    risks.push({ text: `High short interest of ${(shortPct * 100).toFixed(0)}% of float — elevated bearish positioning`, strength: "strong" });
    catalysts.push({ text: `Short squeeze potential if fundamentals beat expectations`, strength: "weak" });
  } else if (shortPct != null && shortPct < 0.02) {
    bull.push({ text: `Very low short interest signals broad market confidence`, strength: "weak" });
  }

  // ─── Analyst estimates ────────────────────────────────────────────────────
  if (data.estimates_annual && data.estimates_annual.length > 0) {
    const nextEst = data.estimates_annual[0];
    const ttmRev  = ttm?.revenue;
    if (nextEst.revenue && ttmRev) {
      const estGrowth = ((nextEst.revenue - ttmRev) / ttmRev) * 100;
      if (estGrowth > 10) catalysts.push({ text: `Analysts project ${estGrowth.toFixed(0)}% revenue growth in next fiscal year`, strength: "moderate" });
    }
    if (nextEst.earnings_per_share && ttm?.earnings_per_share) {
      const epsGrowth = ((nextEst.earnings_per_share - ttm.earnings_per_share) / Math.abs(ttm.earnings_per_share)) * 100;
      if (epsGrowth > 15) catalysts.push({ text: `Consensus EPS expected to grow ${epsGrowth.toFixed(0)}% next year`, strength: "moderate" });
    }
  }

  // ─── Industry/sector catalysts ───────────────────────────────────────────
  const sector = data.company?.sector || "";
  if (sector.toLowerCase().includes("tech") || sector.toLowerCase().includes("software")) {
    catalysts.push({ text: "AI and cloud adoption driving secular growth tailwinds across the technology sector", strength: "moderate" });
  }
  if (sector.toLowerCase().includes("energy")) {
    risks.push({ text: "Exposure to commodity price volatility and energy transition regulatory risk", strength: "moderate" });
  }

  // ─── Generic risks ────────────────────────────────────────────────────────
  risks.push({ text: "Macroeconomic slowdown could compress multiples and reduce consumer/enterprise spending", strength: "moderate" });
  if (p.held_pct_institutions != null && p.held_pct_institutions > 0.8) {
    risks.push({ text: `High institutional ownership (${(p.held_pct_institutions * 100).toFixed(0)}%) increases volatility on sentiment shifts`, strength: "weak" });
  }
  if (pe != null && pe > 30) {
    risks.push({ text: "Elevated valuation multiple sensitive to interest rate increases or earnings misses", strength: "moderate" });
  }

  // Earnings history risks
  const missRate = data.earnings_history?.filter(e => e.surprise_pct != null && e.surprise_pct < 0).length ?? 0;
  const totalEarnings = data.earnings_history?.filter(e => e.surprise_pct != null).length ?? 0;
  if (totalEarnings > 4 && missRate / totalEarnings > 0.4) {
    risks.push({ text: `Inconsistent earnings delivery — missed estimates ${missRate} of last ${totalEarnings} quarters`, strength: "moderate" });
  }

  // Segment concentration risk
  if (data.segments && data.segments.length > 0) {
    const topSeg = data.segments[0]?.items
      .filter((item) => item.segments.length === 1 && item.segments[0].axis === "srt:ProductOrServiceAxis")
      .sort((a, b) => b.amount - a.amount)[0];
    if (topSeg) {
      const total = data.segments[0].items
        .filter((item) => item.segments.length === 1 && item.segments[0].axis === "srt:ProductOrServiceAxis")
        .reduce((s, i) => s + i.amount, 0);
      const pctTop = total > 0 ? (topSeg.amount / total) * 100 : 0;
      if (pctTop > 60) {
        risks.push({ text: `Revenue concentration risk: "${topSeg.segments[0].label}" represents ${pctTop.toFixed(0)}% of product revenue`, strength: "moderate" });
      }
    }
  }

  // Ensure minimum items
  if (catalysts.length < 2) {
    catalysts.push({ text: "Potential margin expansion through operational leverage as revenue scales", strength: "weak" });
    if (cash != null && cash > 1e9) {
      catalysts.push({ text: `Strong cash position ($${(cash / 1e9).toFixed(1)}B) enables M&A or shareholder returns`, strength: "moderate" });
    }
  }

  return {
    bull:      bull.slice(0, 6),
    bear:      bear.slice(0, 5),
    catalysts: catalysts.slice(0, 5),
    risks:     risks.slice(0, 5),
  };
}

function InsightList({
  items,
  color,
}: {
  items: Insight[];
  color: "green" | "red" | "amber" | "blue";
}) {
  const dot = {
    green: "bg-emerald-500",
    red:   "bg-red-500",
    amber: "bg-amber-500",
    blue:  "bg-blue-500",
  }[color];
  const text = {
    green: "text-zinc-300",
    red:   "text-zinc-300",
    amber: "text-zinc-300",
    blue:  "text-zinc-300",
  }[color];

  if (!items.length) {
    return <p className="text-xs text-zinc-600 italic">Insufficient data</p>;
  }
  return (
    <ul className="space-y-2">
      {items.map((item, i) => (
        <li key={i} className="flex gap-2.5 items-start">
          <span className={`w-1.5 h-1.5 rounded-full mt-1.5 shrink-0 ${dot} ${item.strength === "weak" ? "opacity-50" : ""}`} />
          <span className={`text-xs leading-relaxed ${text} ${item.strength === "weak" ? "opacity-60" : ""}`}>
            {item.text}
          </span>
        </li>
      ))}
    </ul>
  );
}

const SECTIONS = [
  { key: "bull",      label: "Bull Case",     icon: TrendingUp,    color: "green" as const, bg: "bg-emerald-950/30 border-emerald-800/30" },
  { key: "bear",      label: "Bear Case",     icon: TrendingDown,  color: "red"   as const, bg: "bg-red-950/30 border-red-800/30"         },
  { key: "catalysts", label: "Key Catalysts", icon: Zap,           color: "amber" as const, bg: "bg-amber-950/30 border-amber-800/30"      },
  { key: "risks",     label: "Key Risks",     icon: AlertTriangle, color: "blue"  as const, bg: "bg-zinc-800/40 border-zinc-700/40"        },
] as const;

export default function InvestmentInsights({ data }: { data: ResearchData }) {
  const insights = useMemo(() => generateInsights(data), [data]);

  const iconColor = {
    green: "text-emerald-400",
    red:   "text-red-400",
    amber: "text-amber-400",
    blue:  "text-blue-400",
  };

  return (
    <div className="space-y-4">
      <div className="text-xs text-zinc-500 bg-zinc-800/40 rounded-lg px-3 py-2 border border-zinc-700/40">
        ⚠ These insights are algorithmically generated from financial data and should not be considered investment advice.
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {SECTIONS.map(({ key, label, icon: Icon, color, bg }) => (
          <div key={key} className={`rounded-xl border p-4 ${bg}`}>
            <div className={`flex items-center gap-2 mb-3 ${iconColor[color]}`}>
              <Icon size={15} />
              <span className="text-sm font-semibold">{label}</span>
            </div>
            <InsightList items={insights[key]} color={color} />
          </div>
        ))}
      </div>
    </div>
  );
}
