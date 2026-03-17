"use client";
import { useState } from "react";
import dynamic from "next/dynamic";
import { TrendingUp, TrendingDown, DollarSign, Activity, ExternalLink } from "lucide-react";
import {
  BarChart, Bar, Cell, XAxis, YAxis, Tooltip as RTooltip, ResponsiveContainer,
  CartesianGrid, ReferenceLine,
} from "recharts";
import {
  Position, PortfolioAnalytics, ContributionEntry, PositionAnalyticsEntry,
  PortfolioNewsItem, PortfolioAnalysisResponse,
} from "@/lib/api";
import { PortfolioHealthCard, SuggestionCard } from "./AnalysisTab";
import { fmt, fmtCurrency, fmtLarge, gainClass } from "@/lib/portfolio-math";

const PerformanceChart = dynamic(() => import("@/components/charts/PerformanceChart"), { ssr: false });
const ReturnsHeatmap   = dynamic(() => import("@/components/charts/ReturnsHeatmap"),   { ssr: false });

interface Props {
  analytics:        PortfolioAnalytics | null;
  positions:        Position[];
  loading:          boolean;
  period:           string;
  analysis?:        PortfolioAnalysisResponse | null;
  onOpenSimulator?: (ticker: string) => void;
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function fmtK(v: number): string {
  const sign = v >= 0 ? "+" : "-";
  const abs = Math.abs(v);
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(2)}M`;
  if (abs >= 1_000)     return `${sign}$${(abs / 1_000).toFixed(1)}K`;
  return `${sign}$${abs.toFixed(0)}`;
}

function fmtPctVal(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : ""}${fmt(v, 2)}%`;
}

function fmtVolatility(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${fmt(v, 1)}%`;
}

type Range = "1M" | "3M" | "6M" | "YTD" | "1Y" | "3Y";

function filterByRange<T extends { date: string }>(data: T[], range: Range): T[] {
  if (!data.length) return data;
  const now = new Date(data[data.length - 1].date);
  let cutoff: Date;
  switch (range) {
    case "1M":  cutoff = new Date(now); cutoff.setMonth(now.getMonth() - 1);          break;
    case "3M":  cutoff = new Date(now); cutoff.setMonth(now.getMonth() - 3);          break;
    case "6M":  cutoff = new Date(now); cutoff.setMonth(now.getMonth() - 6);          break;
    case "YTD": cutoff = new Date(now.getFullYear(), 0, 1);                           break;
    case "3Y":  cutoff = new Date(now); cutoff.setFullYear(now.getFullYear() - 3);    break;
    default:    cutoff = new Date(now); cutoff.setFullYear(now.getFullYear() - 1);
  }
  return data.filter(d => new Date(d.date) >= cutoff);
}

function sharpeLabel(v: number): { label: string; colorClass: string } {
  if (v >= 2)   return { label: "Excellent", colorClass: "text-emerald-400" };
  if (v >= 1)   return { label: "Good",      colorClass: "text-emerald-500" };
  if (v >= 0.5) return { label: "Average",   colorClass: "text-yellow-400" };
  return              { label: "Weak",       colorClass: "text-red-400" };
}

// ── Row 1: Summary Cards ───────────────────────────────────────────────────────

function StatCard({
  label, value, sub, subColorClass, positive, icon, tooltip, large,
}: {
  label: string; value: string; sub?: string; subColorClass?: string;
  positive?: boolean; icon: React.ReactNode; tooltip?: React.ReactNode;
  large?: boolean;
}) {
  const glowRgb = positive == null ? null : positive ? "16,185,129" : "239,68,68";
  return (
    <div
      className="relative group bg-zinc-900 border rounded-xl p-5 transition-all duration-200 hover:bg-zinc-800/60"
      style={glowRgb ? {
        borderColor: `rgba(${glowRgb},0.3)`,
        boxShadow:   `0 0 0 1px rgba(${glowRgb},0.08)`,
      } : { borderColor: "rgb(39,39,42)" }}
    >
      <div className="flex items-start justify-between mb-3">
        <span className="text-zinc-500 text-sm">{label}</span>
        <span style={glowRgb ? { color: `rgba(${glowRgb},0.7)` } : { color: "rgb(82,82,91)" }}>
          {icon}
        </span>
      </div>
      <div
        className={`font-bold font-mono tabular-nums text-zinc-50 ${large ? "text-3xl" : "text-2xl"}`}
        style={glowRgb ? { filter: `drop-shadow(0 0 6px rgba(${glowRgb},0.28))` } : undefined}
      >
        {value}
      </div>
      {sub != null && (
        <div className={`text-sm font-mono mt-1 ${
          subColorClass
            ? subColorClass
            : positive == null
              ? "text-zinc-500"
              : positive ? "text-emerald-400" : "text-red-400"
        }`}>
          {sub}
        </div>
      )}
      {tooltip && (
        <div className="absolute left-0 right-0 top-full mt-1.5 z-20 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
          <div className="bg-zinc-900 border border-zinc-700 rounded-lg p-3 shadow-2xl text-xs mx-1">
            {tooltip}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Row 3: Bloomberg-style Contribution Section ────────────────────────────────

interface WaterfallBar {
  name:      string;
  base:      number;
  value:     number;
  isNeg:     boolean;
  isFinal:   boolean;
  rawChange: number;
  cumAfter:  number;
}

function buildWaterfall(rows: ContributionEntry[]): WaterfallBar[] {
  const sorted = [...rows].sort((a, b) => b.pnl_contribution - a.pnl_contribution);
  let cum = 0;
  const bars: WaterfallBar[] = sorted.map(r => {
    const change = r.pnl_contribution;
    const base = change >= 0 ? cum : cum + change;
    cum += change;
    return { name: r.ticker, base, value: Math.abs(change), isNeg: change < 0, isFinal: false, rawChange: change, cumAfter: cum };
  });
  bars.push({
    name: "Total",
    base: cum >= 0 ? 0 : cum,
    value: Math.abs(cum),
    isNeg: cum < 0,
    isFinal: true,
    rawChange: cum,
    cumAfter: cum,
  });
  return bars;
}

function WaterfallTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload as WaterfallBar;
  return (
    <div className="bg-zinc-900 border border-zinc-700 rounded-lg p-3 text-xs shadow-xl">
      <p className="font-mono font-semibold text-zinc-100 mb-1.5">{d.name}</p>
      {!d.isFinal && (
        <div className="flex justify-between gap-4">
          <span className="text-zinc-400">P&amp;L</span>
          <span className={`font-mono ${d.rawChange >= 0 ? "text-emerald-400" : "text-red-400"}`}>{fmtK(d.rawChange)}</span>
        </div>
      )}
      <div className="flex justify-between gap-4 mt-0.5">
        <span className="text-zinc-400">Cumulative</span>
        <span className={`font-mono ${d.cumAfter >= 0 ? "text-emerald-400" : "text-red-400"}`}>{fmtK(d.cumAfter)}</span>
      </div>
    </div>
  );
}

function ContributionSection({
  rows,
  posAnalytics,
  totalValue,
}: {
  rows:        ContributionEntry[];
  posAnalytics: PositionAnalyticsEntry[];
  totalValue:  number | null;
}) {
  const [hovered, setHovered] = useState<string | null>(null);
  if (!rows.length) return null;

  const sorted   = [...rows].sort((a, b) => b.pnl_contribution - a.pnl_contribution);
  const maxAbs   = Math.max(...sorted.map(r => Math.abs(r.pnl_contribution)), 1);
  const weightMap = new Map(posAnalytics.map(p => [p.ticker, p.weight]));
  const returnMap = new Map(posAnalytics.map(p => [p.ticker, p.return_pct]));
  const totalPnl  = sorted.reduce((s, r) => s + r.pnl_contribution, 0);
  const gains     = sorted.filter(r => r.pnl_contribution >= 0).reduce((s, r) => s + r.pnl_contribution, 0);
  const losses    = sorted.filter(r => r.pnl_contribution < 0).reduce((s, r) => s + r.pnl_contribution, 0);

  const waterfallData = buildWaterfall(sorted);
  const allY    = waterfallData.flatMap(b => [b.base, b.base + b.value]);
  const yPad    = (Math.max(...allY) - Math.min(...allY)) * 0.12 || 100;
  const yDomain = [Math.min(...allY) - yPad, Math.max(...allY) + yPad] as [number, number];

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-5">

      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-zinc-300">Contribution to Return</h3>
        <div className="flex items-center gap-2 text-xs font-mono">
          <span className="text-emerald-400">{fmtK(gains)}</span>
          <span className="text-zinc-600">/</span>
          <span className="text-red-400">{fmtK(losses)}</span>
          <span className="text-zinc-600 mx-1">·</span>
          <span className={totalPnl >= 0 ? "text-emerald-400" : "text-red-400"}>{fmtK(totalPnl)} net</span>
        </div>
      </div>

      {/* Column headers */}
      <div
        className="grid items-center gap-3 px-3 text-[10px] font-semibold text-zinc-600 uppercase tracking-wider"
        style={{ gridTemplateColumns: "72px 1fr 54px 1fr" }}
      >
        <span>Ticker</span>
        <span>Contribution</span>
        <span>Weight</span>
        <span>Impact</span>
      </div>

      {/* Bloomberg rows */}
      <div className="space-y-0.5">
        {sorted.map(row => {
          const weight    = weightMap.get(row.ticker);
          const ret       = returnMap.get(row.ticker);
          const isPos     = row.pnl_contribution >= 0;
          const barPct    = (Math.abs(row.pnl_contribution) / maxAbs) * 50;
          const contribPct =
            totalValue && totalValue > 0
              ? (row.pnl_contribution / totalValue) * 100
              : row.contribution_pct;

          return (
            <div
              key={row.ticker}
              className="relative group"
              onMouseEnter={() => setHovered(row.ticker)}
              onMouseLeave={() => setHovered(null)}
            >
              <div
                className="grid items-center gap-3 py-2 px-3 rounded-lg hover:bg-zinc-800/40 transition-colors cursor-default"
                style={{ gridTemplateColumns: "72px 1fr 54px 1fr" }}
              >
                {/* Ticker */}
                <span className="font-mono font-bold text-xs text-zinc-200">{row.ticker}</span>

                {/* Contribution $ + % */}
                <div className="font-mono text-xs tabular-nums">
                  <span style={{ color: isPos ? "#22c55e" : "#ef4444" }}>{fmtK(row.pnl_contribution)}</span>
                  <span className="text-zinc-600 ml-1.5">({contribPct >= 0 ? "+" : ""}{contribPct.toFixed(1)}%)</span>
                </div>

                {/* Weight */}
                <span className="font-mono text-xs text-zinc-400 tabular-nums">
                  {weight != null ? weight.toFixed(1) + "%" : "—"}
                </span>

                {/* Symmetric impact bar */}
                <div className="relative h-3.5 rounded overflow-hidden bg-zinc-800/70">
                  <div className="absolute top-0 left-1/2 w-px h-full bg-zinc-600 z-10" />
                  {isPos ? (
                    <div
                      className="absolute top-0 h-full rounded-r"
                      style={{ left: "50%", width: `${barPct}%`, backgroundColor: "#22c55e", opacity: 0.8 }}
                    />
                  ) : (
                    <div
                      className="absolute top-0 h-full rounded-l"
                      style={{ right: "50%", width: `${barPct}%`, backgroundColor: "#ef4444", opacity: 0.8 }}
                    />
                  )}
                </div>
              </div>

              {/* Hover tooltip */}
              {hovered === row.ticker && (
                <div className="absolute left-3 top-full z-30 mt-0.5 pointer-events-none">
                  <div className="bg-zinc-950 border border-zinc-700 rounded-lg p-3 shadow-2xl text-xs w-52">
                    <p className="font-mono font-bold text-zinc-100 mb-2">{row.ticker}</p>
                    <div className="space-y-1.5">
                      <div className="flex justify-between gap-4">
                        <span className="text-zinc-400">Contribution</span>
                        <span className={`font-mono ${isPos ? "text-emerald-400" : "text-red-400"}`}>{fmtK(row.pnl_contribution)}</span>
                      </div>
                      <div className="flex justify-between gap-4">
                        <span className="text-zinc-400">Contrib %</span>
                        <span className={`font-mono ${contribPct >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                          {contribPct >= 0 ? "+" : ""}{contribPct.toFixed(2)}%
                        </span>
                      </div>
                      {weight != null && (
                        <div className="flex justify-between gap-4">
                          <span className="text-zinc-400">Portfolio Weight</span>
                          <span className="font-mono text-zinc-300">{weight.toFixed(1)}%</span>
                        </div>
                      )}
                      {ret != null && (
                        <div className="flex justify-between gap-4">
                          <span className="text-zinc-400">Return</span>
                          <span className={`font-mono ${ret >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                            {ret >= 0 ? "+" : ""}{ret.toFixed(2)}%
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* P&L Waterfall chart */}
      <div>
        <p className="text-[10px] font-semibold text-zinc-600 uppercase tracking-wider mb-3">P&amp;L Waterfall</p>
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={waterfallData} margin={{ top: 8, right: 8, bottom: 4, left: 0 }} barCategoryGap="20%">
            <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
            <XAxis
              dataKey="name"
              tick={{ fill: "#71717a", fontSize: 10, fontFamily: "monospace" }}
              tickLine={false}
              axisLine={{ stroke: "#27272a" }}
            />
            <YAxis
              tick={{ fill: "#71717a", fontSize: 10 }}
              tickLine={false}
              axisLine={false}
              tickFormatter={v => {
                const abs = Math.abs(v);
                if (abs >= 1_000_000) return `${v < 0 ? "-" : ""}$${(abs / 1e6).toFixed(1)}M`;
                if (abs >= 1_000)     return `${v < 0 ? "-" : ""}$${(abs / 1e3).toFixed(0)}K`;
                return `$${v.toFixed(0)}`;
              }}
              width={48}
              domain={yDomain}
            />
            <ReferenceLine y={0} stroke="#3f3f46" strokeDasharray="2 2" />
            <RTooltip content={<WaterfallTooltip />} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
            <Bar dataKey="base" stackId="wf" fill="transparent" />
            <Bar dataKey="value" stackId="wf" radius={[3, 3, 0, 0]}>
              {waterfallData.map((entry, i) => (
                <Cell
                  key={i}
                  fill={entry.isFinal ? "#3b82f6" : entry.isNeg ? "#ef4444" : "#22c55e"}
                  fillOpacity={0.85}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

    </div>
  );
}

// ── Row 4: Position Analytics Table ───────────────────────────────────────────

function PositionAnalyticsTable({ rows }: { rows: PositionAnalyticsEntry[] }) {
  if (!rows.length) return null;
  const sorted = [...rows].sort((a, b) => b.weight - a.weight);
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
      <h3 className="text-sm font-semibold text-zinc-300 mb-3">Position Analytics</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs min-w-[560px]">
          <thead>
            <tr className="border-b border-zinc-800">
              <th className="text-left   text-zinc-500 font-medium pb-2 pr-4">Ticker</th>
              <th className="text-right  text-zinc-500 font-medium pb-2 px-2">Weight</th>
              <th className="text-right  text-zinc-500 font-medium pb-2 px-2">Return</th>
              <th className="text-right  text-zinc-500 font-medium pb-2 px-2">Daily</th>
              <th className="text-right  text-zinc-500 font-medium pb-2 px-2">Volatility</th>
              <th className="text-right  text-zinc-500 font-medium pb-2 pl-2">P&amp;L</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map(r => (
              <tr key={r.ticker} className="border-b border-zinc-800/50 last:border-0 hover:bg-zinc-800/20">
                <td className="py-2 pr-4 font-mono font-semibold text-zinc-200">{r.ticker}</td>
                <td className="py-2 px-2 text-right font-mono tabular-nums text-zinc-400">
                  {r.weight != null ? fmt(r.weight, 1) + "%" : "—"}
                </td>
                <td className={`py-2 px-2 text-right font-mono tabular-nums ${gainClass(r.return_pct)}`}>
                  {fmtPctVal(r.return_pct)}
                </td>
                <td className={`py-2 px-2 text-right font-mono tabular-nums ${gainClass(r.daily_return)}`}>
                  {fmtPctVal(r.daily_return)}
                </td>
                <td className="py-2 px-2 text-right font-mono tabular-nums text-zinc-400">
                  {fmtVolatility(r.volatility)}
                </td>
                <td className={`py-2 pl-2 text-right font-mono tabular-nums ${gainClass(r.pnl)}`}>
                  {r.pnl != null ? (r.pnl >= 0 ? "+" : "") + fmtLarge(r.pnl) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Row 5: Rolling Returns ─────────────────────────────────────────────────────

function RollingReturnsTable({ data }: {
  data: { return_1w?: number | null; return_1m?: number | null; return_3m?: number | null; return_ytd?: number | null; return_1y?: number | null } | null;
}) {
  if (!data) return null;
  const rows = [
    { label: "1 Week",  value: data.return_1w  },
    { label: "1 Month", value: data.return_1m  },
    { label: "3 Month", value: data.return_3m  },
    { label: "YTD",     value: data.return_ytd },
    { label: "1 Year",  value: data.return_1y  },
  ];
  const hasAny = rows.some(r => r.value != null);
  if (!hasAny) return null;
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
      <h3 className="text-sm font-semibold text-zinc-300 mb-3">Rolling Returns</h3>
      <div className="grid grid-cols-5 gap-3">
        {rows.map(({ label, value }) => (
          <div key={label} className="text-center">
            <div className="text-[10px] text-zinc-500 mb-1">{label}</div>
            <div className={`text-sm font-mono font-semibold tabular-nums ${gainClass(value)}`}>
              {fmtPctVal(value)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Row 6: Portfolio News ──────────────────────────────────────────────────────

function NewsItem({ item }: { item: PortfolioNewsItem }) {
  return (
    <div className="flex items-start gap-3 py-3 border-b border-zinc-800/60 last:border-0">
      <div className="shrink-0 mt-0.5">
        <span className="text-[10px] font-mono font-semibold bg-zinc-800 text-blue-400 px-1.5 py-0.5 rounded">
          {item.ticker}
        </span>
      </div>
      <div className="flex-1 min-w-0">
        {item.url ? (
          <a
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-zinc-200 hover:text-blue-400 transition-colors leading-snug line-clamp-2 flex items-start gap-1 group"
          >
            {item.headline}
            <ExternalLink size={10} className="shrink-0 mt-0.5 opacity-0 group-hover:opacity-100 transition-opacity" />
          </a>
        ) : (
          <p className="text-xs text-zinc-200 leading-snug line-clamp-2">{item.headline}</p>
        )}
        <div className="flex items-center gap-2 mt-1">
          {item.source && <span className="text-[10px] text-zinc-500">{item.source}</span>}
          {item.source && item.date && <span className="text-[10px] text-zinc-700">·</span>}
          {item.date && <span className="text-[10px] text-zinc-600">{item.date}</span>}
        </div>
      </div>
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────

export default function OverviewTab({ analytics: a, positions, loading, analysis, onOpenSimulator }: Props) {
  const [range, setRange] = useState<Range>("1Y");

  const dayPositive  = (a?.day_gain   ?? 0) >= 0;
  const gainPositive = (a?.total_gain ?? 0) >= 0;
  const sharpe       = a?.risk_metrics?.sharpe;
  const dm           = a?.derived_metrics;
  const rollingRet   = a?.rolling_returns;

  // Chart data — prefer new `performance` series (already indexed to 100)
  const allPerf   = (a?.performance ?? []).map(p => ({ date: p.date, portfolio: p.portfolio, spy: p.spy, qqq: p.qqq }));
  const chartData = filterByRange(allPerf, range);

  // Contribution — prefer new analytics.contribution, fall back to position_summary
  const contribution: ContributionEntry[] = a?.contribution
    ? [...a.contribution].sort((x, y) => y.pnl_contribution - x.pnl_contribution)
    : [];

  // Position analytics
  const posAnalytics: PositionAnalyticsEntry[] = a?.position_analytics ?? [];

  // News
  const news = (a?.portfolio_news ?? []).slice(0, 10);

  // Cards
  const sharpeInfo = sharpe != null ? sharpeLabel(sharpe) : null;
  const ytdPct     = rollingRet?.return_ytd ?? dm?.performance_summary?.ytd_pct;

  const valueTooltip = a ? (
    <div className="space-y-1.5">
      <div className="flex justify-between gap-4">
        <span className="text-zinc-400">Total Cost</span>
        <span className="font-mono text-zinc-200">{fmtCurrency(a.total_cost)}</span>
      </div>
      {dm?.performance_summary?.["1m_pct"] != null && (
        <div className="flex justify-between gap-4">
          <span className="text-zinc-400">1M Return</span>
          <span className={`font-mono ${gainClass(dm.performance_summary["1m_pct"])}`}>
            {fmtPctVal(dm.performance_summary["1m_pct"])}
          </span>
        </div>
      )}
      {a.risk_metrics?.annualized_return_pct != null && (
        <div className="flex justify-between gap-4">
          <span className="text-zinc-400">Ann. Return</span>
          <span className={`font-mono ${gainClass(a.risk_metrics.annualized_return_pct)}`}>
            {fmtPctVal(a.risk_metrics.annualized_return_pct)}
          </span>
        </div>
      )}
      {a.risk_metrics?.max_drawdown_pct != null && (
        <div className="flex justify-between gap-4">
          <span className="text-zinc-400">Max Drawdown</span>
          <span className="font-mono text-red-400">{fmtPctVal(a.risk_metrics.max_drawdown_pct)}</span>
        </div>
      )}
      {a.performance_metrics?.volatility != null && (
        <div className="flex justify-between gap-4">
          <span className="text-zinc-400">Volatility</span>
          <span className="font-mono text-zinc-300">{fmtVolatility(a.performance_metrics.volatility)}</span>
        </div>
      )}
    </div>
  ) : null;

  return (
    <div className="space-y-5">

      {/* Portfolio Health + Suggestions */}
      {analysis && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <PortfolioHealthCard health={analysis.health} />
          {analysis.suggestions.length > 0 && (
            <div className="space-y-3">
              <h2 className="text-zinc-100 font-semibold text-base">
                Suggestions
                <span className="ml-2 text-xs text-zinc-500 bg-zinc-800 px-2 py-0.5 rounded-full font-normal">
                  {analysis.suggestions.length}
                </span>
              </h2>
              <div className="space-y-3 max-h-[420px] overflow-y-auto pr-1 scrollbar-thin">
                {analysis.suggestions.map((s, i) => (
                  <SuggestionCard key={i} s={s} onSimulate={onOpenSimulator} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Row 1 — Summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Portfolio Value"
          value={fmtCurrency(a?.total_value)}
          sub={ytdPct != null ? `${fmtPctVal(ytdPct)} YTD` : undefined}
          positive={ytdPct != null ? ytdPct >= 0 : undefined}
          large
          icon={<DollarSign size={18} />}
          tooltip={valueTooltip}
        />
        <StatCard
          label="Total Gain"
          value={fmtCurrency(a?.total_gain)}
          sub={a?.total_gain_pct != null ? fmtPctVal(a.total_gain_pct) : undefined}
          positive={gainPositive}
          icon={gainPositive ? <TrendingUp size={18} /> : <TrendingDown size={18} />}
        />
        <StatCard
          label="Day Gain"
          value={fmtCurrency(a?.day_gain)}
          sub={a?.day_gain_pct != null ? fmtPctVal(a.day_gain_pct) : undefined}
          positive={dayPositive}
          icon={dayPositive ? <TrendingUp size={18} /> : <TrendingDown size={18} />}
        />
        <StatCard
          label="Sharpe Ratio"
          value={sharpe != null ? fmt(sharpe, 2) : "—"}
          sub={sharpeInfo?.label}
          subColorClass={sharpeInfo?.colorClass}
          positive={sharpe != null ? sharpe >= 1 : undefined}
          icon={<Activity size={18} />}
          tooltip={
            a?.risk_metrics ? (
              <div className="space-y-1.5">
                {a.risk_metrics.sortino != null && (
                  <div className="flex justify-between gap-4">
                    <span className="text-zinc-400">Sortino</span>
                    <span className="font-mono text-zinc-200">{fmt(a.risk_metrics.sortino, 2)}</span>
                  </div>
                )}
                {a.risk_metrics.beta != null && (
                  <div className="flex justify-between gap-4">
                    <span className="text-zinc-400">Beta</span>
                    <span className="font-mono text-zinc-200">{fmt(a.risk_metrics.beta, 2)}</span>
                  </div>
                )}
                {a.risk_metrics.calmar != null && (
                  <div className="flex justify-between gap-4">
                    <span className="text-zinc-400">Calmar</span>
                    <span className="font-mono text-zinc-200">{fmt(a.risk_metrics.calmar, 2)}</span>
                  </div>
                )}
                {a.risk_metrics.win_rate_pct != null && (
                  <div className="flex justify-between gap-4">
                    <span className="text-zinc-400">Win Rate</span>
                    <span className="font-mono text-zinc-200">{fmt(a.risk_metrics.win_rate_pct, 1)}%</span>
                  </div>
                )}
              </div>
            ) : null
          }
        />
      </div>

      {/* Row 2 — Performance chart */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
        <div className="flex items-center justify-between mb-1">
          <h3 className="text-sm font-semibold text-zinc-300">Performance vs Benchmarks</h3>
          {a?.risk_metrics?.annualized_return_pct != null && (
            <span className={`text-xs font-mono ${gainClass(a.risk_metrics.annualized_return_pct)}`}>
              Ann. {fmtPctVal(a.risk_metrics.annualized_return_pct)}
            </span>
          )}
        </div>
        {loading ? (
          <div className="h-64 flex items-center justify-center">
            <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : chartData.length > 1 ? (
          <PerformanceChart
            data={chartData}
            range={range}
            onRangeChange={r => setRange(r as Range)}
          />
        ) : (
          <div className="h-64 flex items-center justify-center text-zinc-500 text-sm">
            {positions.length ? "Computing performance…" : "Add positions to see chart"}
          </div>
        )}
      </div>

      {/* Rows 3-4 — Unified Returns Heatmap (extremes + daily/weekly/monthly grid) */}
      {a && (a.monthly_returns?.length || a.daily_heatmap?.length || a.weekly_returns?.length) ? (
        <ReturnsHeatmap
          dailyHeatmap={a.daily_heatmap   ?? []}
          weeklyReturns={a.weekly_returns ?? []}
          monthlyReturns={a.monthly_returns}
          periodExtremes={a.period_extremes}
        />
      ) : null}

      {/* Row 5 — Contribution to Return */}
      {contribution.length > 0 && (
        <ContributionSection
          rows={contribution}
          posAnalytics={posAnalytics}
          totalValue={a?.total_value ?? null}
        />
      )}

      {/* Row 6 — Position Analytics Table */}
      {posAnalytics.length > 0 && (
        <PositionAnalyticsTable rows={posAnalytics} />
      )}

      {/* Row 7 — Rolling Returns */}
      {rollingRet && (
        <RollingReturnsTable data={rollingRet} />
      )}

      {/* Row 8 — Portfolio News */}
      {news.length > 0 && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
          <h3 className="text-sm font-semibold text-zinc-300 mb-1">Portfolio News</h3>
          <div>
            {news.map((item, i) => (
              <NewsItem key={`${item.ticker}-${i}`} item={item} />
            ))}
          </div>
        </div>
      )}

    </div>
  );
}
