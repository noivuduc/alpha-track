"use client";
import dynamic from "next/dynamic";
import { useState } from "react";
import { TrendingUp, TrendingDown, DollarSign, Activity } from "lucide-react";
import {
  ResponsiveContainer, ComposedChart,
  Line, XAxis, YAxis, Tooltip, CartesianGrid,
  ReferenceLine, ReferenceArea,
} from "recharts";
import {
  PortfolioAnalytics, DerivedMetrics, BenchmarkComparison, PerformanceSummary,
  RollingMetricPoint, RollingCorrelationPoint, VolatilityRegimePoint,
  PortfolioAnalysisResponse,
} from "@/lib/api";
import { fmt, fmtCurrency } from "@/lib/portfolio-math";
import { CorrelationClusterCard } from "./AnalysisTab";

const DrawdownChart = dynamic(() => import("@/components/charts/DrawdownChart"), { ssr: false });

type Range         = "1M" | "3M" | "6M" | "YTD" | "1Y";
type RollingWindow = "63d" | "126d" | "252d";

const RANGES:  Range[]                          = ["1M", "3M", "6M", "YTD", "1Y"];
const WINDOWS: { key: RollingWindow; label: string }[] = [
  { key: "63d",  label: "3M" },
  { key: "126d", label: "6M" },
  { key: "252d", label: "1Y" },
];

interface Props {
  analytics:  PortfolioAnalytics | null;
  loading:    boolean;
  period:     string;
  analysis?:  PortfolioAnalysisResponse | null;
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function fmtPctVal(v: number | null | undefined, sign = true): string {
  if (v == null) return "—";
  return `${sign && v >= 0 ? "+" : ""}${fmt(v, 2)}%`;
}

function pctColor(v: number | null | undefined): string {
  if (v == null) return "text-zinc-400";
  return v >= 0 ? "text-emerald-400" : "text-red-400";
}

function filterByRange<T extends { date: string }>(data: T[], range: Range): T[] {
  if (!data.length || range === "1Y") return data;
  const last = new Date(data[data.length - 1].date);
  let cutoff: Date;
  if (range === "YTD") {
    cutoff = new Date(`${last.getFullYear()}-01-01`);
  } else {
    cutoff = new Date(last);
    if (range === "1M") cutoff.setDate(cutoff.getDate() - 30);
    if (range === "3M") cutoff.setMonth(cutoff.getMonth() - 3);
    if (range === "6M") cutoff.setMonth(cutoff.getMonth() - 6);
  }
  return data.filter(d => new Date(d.date) >= cutoff);
}

const TT_STYLE = {
  backgroundColor: "#18181b", border: "1px solid #3f3f46",
  borderRadius: 8, color: "#e4e4e7", fontSize: 11,
};

function dateTick(d: string) {
  return new Date(d).toLocaleDateString("en-US", { month: "short", year: "2-digit" });
}

// ── Shared primitives ──────────────────────────────────────────────────────────

function Panel({ title, children, action, className = "" }: {
  title: string; children: React.ReactNode; action?: React.ReactNode; className?: string;
}) {
  return (
    <div className={`bg-zinc-900 border border-zinc-800 rounded-xl p-5 ${className}`}>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-zinc-300">{title}</h3>
        {action}
      </div>
      {children}
    </div>
  );
}

function MetricRow({ label, value, valueClass = "text-zinc-200" }: {
  label: string; value: string; valueClass?: string;
}) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-zinc-800/60 last:border-0">
      <span className="text-xs text-zinc-500">{label}</span>
      <span className={`text-xs font-mono tabular-nums font-semibold ${valueClass}`}>{value}</span>
    </div>
  );
}

function SummaryCard({ label, value, sub, positive, icon }: {
  label: string; value: string; sub?: string; positive?: boolean; icon: React.ReactNode;
}) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
      <div className="flex items-start justify-between mb-2">
        <span className="text-xs text-zinc-500">{label}</span>
        <span className="text-zinc-600">{icon}</span>
      </div>
      <div className="text-xl font-bold font-mono tabular-nums text-zinc-50">{value}</div>
      {sub != null && (
        <div className={`text-xs font-mono mt-1 ${
          positive == null ? "text-zinc-500" : positive ? "text-emerald-400" : "text-red-400"
        }`}>
          {sub}
        </div>
      )}
    </div>
  );
}

function WindowSelector({ value, onChange }: { value: RollingWindow; onChange: (w: RollingWindow) => void }) {
  return (
    <div className="flex gap-0.5 bg-zinc-800 rounded-lg p-0.5">
      {WINDOWS.map(w => (
        <button
          key={w.key}
          onClick={() => onChange(w.key)}
          className={`px-2.5 py-1 text-xs rounded-md font-medium transition-colors ${
            value === w.key ? "bg-blue-600 text-white" : "text-zinc-400 hover:text-zinc-200"
          }`}
        >
          {w.label}
        </button>
      ))}
    </div>
  );
}

// ── Rolling Charts ─────────────────────────────────────────────────────────────

function RollingSharpeChart({ data }: { data: RollingMetricPoint[] }) {
  if (!data.length) return <Empty />;
  return (
    <ResponsiveContainer width="100%" height={200}>
      <ComposedChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
        <defs>
          <linearGradient id="sharpeFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#3b82f6" stopOpacity={0.15} />
            <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
        <XAxis dataKey="date" tick={{ fill: "#71717a", fontSize: 10 }} tickLine={false}
          axisLine={{ stroke: "#27272a" }} tickFormatter={dateTick} interval="preserveStartEnd" />
        <YAxis tick={{ fill: "#71717a", fontSize: 10 }} tickLine={false} axisLine={false}
          tickFormatter={v => v.toFixed(1)} width={36} />
        <Tooltip contentStyle={TT_STYLE}
          formatter={(v: any) => [Number(v).toFixed(2), "Sharpe"]}
          labelStyle={{ color: "#a1a1aa" }} labelFormatter={String} />
        {/* Quality bands */}
        <ReferenceArea y1={2}   y2={6}  fill="#10b981" fillOpacity={0.06} />
        <ReferenceArea y1={1}   y2={2}  fill="#10b981" fillOpacity={0.03} />
        <ReferenceArea y1={0.5} y2={1}  fill="#f59e0b" fillOpacity={0.04} />
        <ReferenceArea y1={-4}  y2={0.5} fill="#ef4444" fillOpacity={0.04} />
        <ReferenceLine y={2} stroke="#10b981" strokeDasharray="4 4" strokeOpacity={0.5}
          label={{ value: "2 — Excellent", fill: "#10b981", fontSize: 9, position: "insideTopRight" }} />
        <ReferenceLine y={1} stroke="#f59e0b" strokeDasharray="4 4" strokeOpacity={0.5}
          label={{ value: "1 — Good", fill: "#f59e0b", fontSize: 9, position: "insideTopRight" }} />
        <ReferenceLine y={0} stroke="#52525b" strokeOpacity={0.5} />
        <Line type="monotone" dataKey="rolling_sharpe" stroke="#3b82f6" strokeWidth={2}
          dot={false} connectNulls />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

function RollingVolatilityChart({ data }: { data: RollingMetricPoint[] }) {
  if (!data.length) return <Empty />;
  const maxVol = Math.min(60, Math.max(25, ...data.map(d => d.rolling_volatility ?? 0)) + 5);
  return (
    <ResponsiveContainer width="100%" height={200}>
      <ComposedChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
        <XAxis dataKey="date" tick={{ fill: "#71717a", fontSize: 10 }} tickLine={false}
          axisLine={{ stroke: "#27272a" }} tickFormatter={dateTick} interval="preserveStartEnd" />
        <YAxis tick={{ fill: "#71717a", fontSize: 10 }} tickLine={false} axisLine={false}
          tickFormatter={v => `${v.toFixed(0)}%`} width={38} domain={[0, maxVol]} />
        <Tooltip contentStyle={TT_STYLE}
          formatter={(v: any) => [`${Number(v).toFixed(1)}%`, "Volatility"]}
          labelStyle={{ color: "#a1a1aa" }} labelFormatter={String} />
        {/* Regime zones */}
        <ReferenceArea y1={0}  y2={10}     fill="#10b981" fillOpacity={0.07} />
        <ReferenceArea y1={10} y2={20}     fill="#f59e0b" fillOpacity={0.07} />
        <ReferenceArea y1={20} y2={maxVol} fill="#ef4444" fillOpacity={0.07} />
        <ReferenceLine y={10} stroke="#f59e0b" strokeDasharray="3 3" strokeOpacity={0.45}
          label={{ value: "10%", fill: "#f59e0b", fontSize: 9, position: "insideTopRight" }} />
        <ReferenceLine y={20} stroke="#ef4444" strokeDasharray="3 3" strokeOpacity={0.45}
          label={{ value: "20%", fill: "#ef4444", fontSize: 9, position: "insideTopRight" }} />
        <Line type="monotone" dataKey="rolling_volatility" stroke="#f59e0b" strokeWidth={2}
          dot={false} connectNulls />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

function RollingBetaChart({ data }: { data: RollingMetricPoint[] }) {
  if (!data.length) return <Empty />;
  return (
    <ResponsiveContainer width="100%" height={200}>
      <ComposedChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
        <XAxis dataKey="date" tick={{ fill: "#71717a", fontSize: 10 }} tickLine={false}
          axisLine={{ stroke: "#27272a" }} tickFormatter={dateTick} interval="preserveStartEnd" />
        <YAxis tick={{ fill: "#71717a", fontSize: 10 }} tickLine={false} axisLine={false}
          tickFormatter={v => v.toFixed(1)} width={36} />
        <Tooltip contentStyle={TT_STYLE}
          formatter={(v: any) => [Number(v).toFixed(2), "Beta vs SPY"]}
          labelStyle={{ color: "#a1a1aa" }} labelFormatter={String} />
        {/* Defensive / neutral / aggressive zones */}
        <ReferenceArea y1={-2} y2={1} fill="#10b981" fillOpacity={0.04} />
        <ReferenceArea y1={1}  y2={4} fill="#ef4444" fillOpacity={0.04} />
        <ReferenceLine y={1} stroke="#a1a1aa" strokeDasharray="4 4" strokeOpacity={0.6}
          label={{ value: "β = 1", fill: "#a1a1aa", fontSize: 9, position: "insideTopRight" }} />
        <Line type="monotone" dataKey="rolling_beta" stroke="#a78bfa" strokeWidth={2}
          dot={false} connectNulls />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

function RollingCorrelationChart({ data }: { data: RollingCorrelationPoint[] }) {
  if (!data.length) return <Empty />;
  return (
    <ResponsiveContainer width="100%" height={200}>
      <ComposedChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
        <XAxis dataKey="date" tick={{ fill: "#71717a", fontSize: 10 }} tickLine={false}
          axisLine={{ stroke: "#27272a" }} tickFormatter={dateTick} interval="preserveStartEnd" />
        <YAxis tick={{ fill: "#71717a", fontSize: 10 }} tickLine={false} axisLine={false}
          tickFormatter={v => v.toFixed(1)} width={36} domain={[-1, 1]} />
        <Tooltip contentStyle={TT_STYLE}
          formatter={(v: any) => [Number(v).toFixed(3), "Corr vs SPY"]}
          labelStyle={{ color: "#a1a1aa" }} labelFormatter={String} />
        <ReferenceArea y1={-1} y2={0}   fill="#10b981" fillOpacity={0.05} />
        <ReferenceArea y1={0}  y2={0.5} fill="#f59e0b" fillOpacity={0.04} />
        <ReferenceArea y1={0.5} y2={1}  fill="#ef4444" fillOpacity={0.05} />
        <ReferenceLine y={0}   stroke="#52525b" strokeOpacity={0.6} />
        <ReferenceLine y={0.7} stroke="#ef4444" strokeDasharray="3 3" strokeOpacity={0.4}
          label={{ value: "0.7", fill: "#ef4444", fontSize: 9, position: "insideTopRight" }} />
        <Line type="monotone" dataKey="value" stroke="#06b6d4" strokeWidth={2}
          dot={false} connectNulls />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

// ── Volatility Regime Timeline ─────────────────────────────────────────────────

function VolatilityRegimeTimeline({ data }: { data: VolatilityRegimePoint[] }) {
  if (!data.length) return null;

  // Group consecutive same-regime periods
  type Group = { regime: string; count: number; start: string; end: string };
  const groups: Group[] = [];
  for (const pt of data) {
    const last = groups[groups.length - 1];
    if (last && last.regime === pt.regime) {
      last.count++;
      last.end = pt.date;
    } else {
      groups.push({ regime: pt.regime, count: 1, start: pt.date, end: pt.date });
    }
  }
  const total = data.length;
  const regimeCls: Record<string, string> = {
    low:    "bg-emerald-500",
    normal: "bg-amber-500",
    high:   "bg-red-500",
  };

  return (
    <div>
      <div className="flex h-3 rounded overflow-hidden gap-[1px]">
        {groups.map((g, i) => (
          <div
            key={i}
            className={`${regimeCls[g.regime] ?? "bg-zinc-600"} opacity-75 flex-shrink-0`}
            style={{ width: `${(g.count / total) * 100}%` }}
            title={`${g.regime.charAt(0).toUpperCase() + g.regime.slice(1)}: ${g.start} → ${g.end}`}
          />
        ))}
      </div>
      <div className="flex items-center gap-4 mt-2">
        {[
          { regime: "low",    cls: "bg-emerald-500", label: "Low (<10%)" },
          { regime: "normal", cls: "bg-amber-500",   label: "Normal (10–20%)" },
          { regime: "high",   cls: "bg-red-500",     label: "High (>20%)" },
        ].map(({ cls, label }) => (
          <div key={label} className="flex items-center gap-1.5">
            <div className={`w-2 h-2 rounded-full ${cls}`} />
            <span className="text-[10px] text-zinc-500">{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Risk Metrics Tables ────────────────────────────────────────────────────────

type Badge = "good" | "warn" | "bad" | "neutral";
const BADGE_CLS: Record<Badge, string> = {
  good: "text-emerald-400", warn: "text-amber-400", bad: "text-red-400", neutral: "text-zinc-200",
};
function score(v: number, hi: number, lo: number): Badge {
  return v >= hi ? "good" : v >= lo ? "warn" : "bad";
}

function RiskMetricsTable({ r }: { r: PortfolioAnalytics["risk_metrics"] }) {
  const rows: [string, string, string][] = [
    ["Sharpe",       r.sharpe       != null ? fmt(r.sharpe, 2)                      : "—", BADGE_CLS[r.sharpe       != null ? score(r.sharpe, 1, 0.5)            : "neutral"]],
    ["Sortino",      r.sortino      != null ? fmt(r.sortino, 2)                     : "—", BADGE_CLS[r.sortino      != null ? score(r.sortino, 1.5, 0.75)         : "neutral"]],
    ["Beta",         r.beta         != null ? fmt(r.beta, 2)                        : "—", r.beta != null ? (r.beta < 0.8 ? BADGE_CLS.good : r.beta < 1.2 ? BADGE_CLS.neutral : BADGE_CLS.warn) : BADGE_CLS.neutral],
    ["Alpha (Ann.)", r.alpha_pct    != null ? fmtPctVal(r.alpha_pct)                : "—", pctColor(r.alpha_pct)],
    ["Max Drawdown", r.max_drawdown_pct  != null ? `${fmt(r.max_drawdown_pct, 2)}%` : "—", r.max_drawdown_pct != null ? (r.max_drawdown_pct > -10 ? BADGE_CLS.good : r.max_drawdown_pct > -20 ? BADGE_CLS.warn : BADGE_CLS.bad) : BADGE_CLS.neutral],
    ["Volatility",   r.volatility_pct    != null ? `${fmt(r.volatility_pct, 1)}%`  : "—", r.volatility_pct   != null ? (r.volatility_pct < 15 ? BADGE_CLS.good : r.volatility_pct < 25 ? BADGE_CLS.warn : BADGE_CLS.bad) : BADGE_CLS.neutral],
    ["Info. Ratio",  r.information_ratio != null ? fmt(r.information_ratio, 2)     : "—", BADGE_CLS[r.information_ratio != null ? score(r.information_ratio, 0.5, 0) : "neutral"]],
    ["VaR (95%)",    r.var_95_pct        != null ? `-${fmt(r.var_95_pct, 2)}%`     : "—", r.var_95_pct != null ? (r.var_95_pct < 2 ? BADGE_CLS.good : r.var_95_pct < 4 ? BADGE_CLS.warn : BADGE_CLS.bad) : BADGE_CLS.neutral],
    ["Win Rate",     r.win_rate_pct      != null ? `${fmt(r.win_rate_pct, 1)}%`    : "—", BADGE_CLS[r.win_rate_pct != null ? score(r.win_rate_pct, 55, 48) : "neutral"]],
    ["Calmar",       r.calmar            != null ? fmt(r.calmar, 2)                : "—", BADGE_CLS[r.calmar != null ? score(r.calmar, 0.75, 0.3) : "neutral"]],
    ["Ann. Return",  r.annualized_return_pct != null ? fmtPctVal(r.annualized_return_pct) : "—", pctColor(r.annualized_return_pct)],
    // Downside risk (new)
    ["Downside Dev.",    r.downside_deviation != null ? `${fmt(r.downside_deviation, 1)}%`  : "—", r.downside_deviation != null ? (r.downside_deviation < 10 ? BADGE_CLS.good : r.downside_deviation < 20 ? BADGE_CLS.warn : BADGE_CLS.bad) : BADGE_CLS.neutral],
    ["Ulcer Index",      r.ulcer_index        != null ? fmt(r.ulcer_index, 2)               : "—", r.ulcer_index        != null ? (r.ulcer_index < 5 ? BADGE_CLS.good : r.ulcer_index < 10 ? BADGE_CLS.warn : BADGE_CLS.bad) : BADGE_CLS.neutral],
    ["Tail Loss (95%)",  r.tail_loss_95       != null ? `-${fmt(r.tail_loss_95, 2)}%`       : "—", r.tail_loss_95       != null ? (r.tail_loss_95 < 2 ? BADGE_CLS.good : r.tail_loss_95 < 4 ? BADGE_CLS.warn : BADGE_CLS.bad) : BADGE_CLS.neutral],
    ["Trading Days", r.trading_days != null ? String(r.trading_days) : "—", BADGE_CLS.neutral],
  ];
  return (
    <div>
      {rows.map(([label, val, cls]) => (
        <MetricRow key={label} label={label} value={val} valueClass={cls} />
      ))}
    </div>
  );
}

function PortfolioCharacteristicsTable({ pm }: { pm: NonNullable<PortfolioAnalytics["performance_metrics"]> }) {
  const rows: [string, string, string][] = [
    ["Corr. vs SPY",   pm.correlation_spy  != null ? fmt(pm.correlation_spy, 3)   : "—", "text-zinc-200"],
    ["Corr. vs QQQ",   pm.correlation_qqq  != null ? fmt(pm.correlation_qqq, 3)   : "—", "text-zinc-200"],
    ["Upside Capture", pm.upside_capture_ratio  != null ? fmt(pm.upside_capture_ratio, 2)  + "×" : "—",
      pm.upside_capture_ratio != null ? (pm.upside_capture_ratio >= 1 ? BADGE_CLS.good : BADGE_CLS.warn) : BADGE_CLS.neutral],
    ["Downside Capture", pm.downside_capture_ratio != null ? fmt(pm.downside_capture_ratio, 2) + "×" : "—",
      pm.downside_capture_ratio != null ? (pm.downside_capture_ratio <= 1 ? BADGE_CLS.good : BADGE_CLS.warn) : BADGE_CLS.neutral],
    ["Est. Turnover",  pm.estimated_turnover_pct != null ? `${fmt(pm.estimated_turnover_pct, 1)}%/yr` : "—", "text-zinc-200"],
    ["Largest Position", pm.largest_position_weight != null ? `${fmt(pm.largest_position_weight, 1)}%` : "—",
      pm.largest_position_weight != null ? (pm.largest_position_weight < 25 ? BADGE_CLS.good : pm.largest_position_weight < 40 ? BADGE_CLS.warn : BADGE_CLS.bad) : BADGE_CLS.neutral],
    ["Top-3 Weight",   pm.top3_weight != null ? `${fmt(pm.top3_weight, 1)}%` : "—",
      pm.top3_weight != null ? (pm.top3_weight < 50 ? BADGE_CLS.good : pm.top3_weight < 70 ? BADGE_CLS.warn : BADGE_CLS.bad) : BADGE_CLS.neutral],
    ["HHI",            pm.herfindahl_index != null ? fmt(pm.herfindahl_index, 4) : "—",
      pm.herfindahl_index != null ? (pm.herfindahl_index < 0.15 ? BADGE_CLS.good : pm.herfindahl_index < 0.25 ? BADGE_CLS.warn : BADGE_CLS.bad) : BADGE_CLS.neutral],
    ["Skewness",  pm.skewness != null ? fmt(pm.skewness, 3) : "—",
      pm.skewness != null ? (pm.skewness >= 0 ? BADGE_CLS.good : BADGE_CLS.warn) : BADGE_CLS.neutral],
    ["Kurtosis",  pm.kurtosis != null ? fmt(pm.kurtosis, 3) : "—",
      pm.kurtosis != null ? (Math.abs(pm.kurtosis) < 1 ? BADGE_CLS.good : Math.abs(pm.kurtosis) < 3 ? BADGE_CLS.warn : BADGE_CLS.bad) : BADGE_CLS.neutral],
  ];
  return (
    <div>
      {rows.map(([label, val, cls]) => (
        <MetricRow key={label} label={label} value={val} valueClass={cls} />
      ))}
    </div>
  );
}

// ── Existing sub-components ────────────────────────────────────────────────────

function PerfSummary({ ps }: { ps: PerformanceSummary }) {
  const items: [string, number | null][] = [
    ["1D",  ps["1d_pct"]], ["1W", ps["1w_pct"]], ["1M", ps["1m_pct"]],
    ["YTD", ps.ytd_pct],   ["1Y", ps["1y_pct"]],
  ];
  return (
    <div className="grid grid-cols-5 gap-2">
      {items.map(([label, val]) => (
        <div key={label} className="bg-zinc-800/50 rounded-lg p-2.5 text-center">
          <div className="text-[10px] text-zinc-500 mb-1">{label}</div>
          <div className={`text-xs font-mono font-semibold tabular-nums ${pctColor(val)}`}>
            {fmtPctVal(val)}
          </div>
        </div>
      ))}
    </div>
  );
}

function BenchComp({ bc }: { bc: BenchmarkComparison }) {
  const rows: [string, number | null, boolean][] = [
    ["Portfolio Return", bc.portfolio_return_pct, true],
    ["SPY Return",       bc.spy_return_pct,       true],
    ["QQQ Return",       bc.qqq_return_pct,       true],
    ["Alpha vs SPY",     bc.alpha_vs_spy_pct,     true],
    ["Alpha vs QQQ",     bc.alpha_vs_qqq_pct,     true],
  ];
  return (
    <div>
      {rows.map(([label, val, signed]) => (
        <MetricRow key={label} label={label} value={fmtPctVal(val, signed)} valueClass={pctColor(val)} />
      ))}
    </div>
  );
}

function DailyStats({ dm }: { dm: DerivedMetrics }) {
  const items: [string, number | null][] = [
    ["Best Day",   dm.best_day_pct], ["Worst Day",    dm.worst_day_pct],
    ["Avg Daily",  dm.avg_daily_return_pct], ["Median", dm.median_daily_return_pct],
  ];
  return (
    <div className="grid grid-cols-2 gap-3">
      {items.map(([label, val]) => (
        <div key={label} className="bg-zinc-800/50 rounded-lg p-3">
          <div className="text-[10px] text-zinc-500 mb-1">{label}</div>
          <div className={`text-sm font-mono font-semibold tabular-nums ${pctColor(val)}`}>
            {fmtPctVal(val)}
          </div>
        </div>
      ))}
    </div>
  );
}

function DrawdownStatus({ dm }: { dm: DerivedMetrics }) {
  const cur = dm.current_drawdown_pct;
  const rec = dm.recovery_days_since_peak;
  const atPeak = cur != null && cur >= -0.01;
  return (
    <div className="space-y-4">
      <div className="bg-zinc-800/50 rounded-lg p-4">
        <div className="text-[10px] text-zinc-500 mb-1">Current Drawdown</div>
        <div className={`text-2xl font-bold font-mono tabular-nums ${
          cur != null && cur < -5 ? "text-red-400" : cur != null && cur < -1 ? "text-amber-400" : "text-emerald-400"
        }`}>
          {cur != null ? `${fmt(cur, 2)}%` : "—"}
        </div>
        {atPeak && <div className="text-[10px] text-emerald-500 mt-1">Portfolio at all-time high</div>}
      </div>
      <div className="bg-zinc-800/50 rounded-lg p-4">
        <div className="text-[10px] text-zinc-500 mb-1">Days Since Peak</div>
        <div className={`text-2xl font-bold font-mono tabular-nums ${
          rec === 0 ? "text-emerald-400" : rec < 30 ? "text-amber-400" : "text-red-400"
        }`}>
          {rec}
        </div>
        <div className="text-[10px] text-zinc-600 mt-1">
          {rec === 0 ? "Currently at peak" : `${rec} trading days off peak`}
        </div>
      </div>
    </div>
  );
}

function Empty({ msg = "Not enough data" }: { msg?: string }) {
  return (
    <div className="h-[200px] flex items-center justify-center text-zinc-600 text-sm">{msg}</div>
  );
}

// ── Main ───────────────────────────────────────────────────────────────────────

export default function RiskTab({ analytics: a, loading, period, analysis }: Props) {
  const [window,    setWindow]    = useState<RollingWindow>("126d");
  const [ddRange,   setDdRange]   = useState<Range>("1Y");

  // Filter to multi-asset clusters only; computed from analysis prop
  const multiClusters = (analysis?.clusters ?? []).filter(c => c.assets.length >= 2);

  if (loading && !a) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }
  if (!a) {
    return (
      <div className="text-center py-16 text-zinc-500">
        {loading ? "Computing analytics…" : "Add positions to see portfolio analytics"}
      </div>
    );
  }

  const dm         = a.derived_metrics;
  const r          = a.risk_metrics;
  const pm         = a.performance_metrics;
  const rollingData: RollingMetricPoint[]      = a.rolling_metrics?.[window]      ?? [];
  const corrData:    RollingCorrelationPoint[]  = a.rolling_correlation_spy         ?? [];
  const regimeData:  VolatilityRegimePoint[]    = a.volatility_regime               ?? [];
  const drawdownData = filterByRange(a.drawdown, ddRange);

  const dayPos  = a.day_gain   >= 0;
  const gainPos = a.total_gain >= 0;

  return (
    <div className="space-y-5">

      {/* Row 0 — Summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <SummaryCard label="Portfolio Value" value={fmtCurrency(a.total_value)} icon={<DollarSign size={16} />} />
        <SummaryCard label="Total Gain"      value={fmtCurrency(a.total_gain)}
          sub={`${gainPos ? "+" : ""}${fmt(a.total_gain_pct, 2)}%`} positive={gainPos}
          icon={gainPos ? <TrendingUp size={16} /> : <TrendingDown size={16} />} />
        <SummaryCard label="Day Gain"        value={fmtCurrency(a.day_gain)}
          sub={`${dayPos ? "+" : ""}${fmt(a.day_gain_pct, 2)}%`} positive={dayPos}
          icon={dayPos ? <TrendingUp size={16} /> : <TrendingDown size={16} />} />
        <SummaryCard label="Sharpe Ratio"    value={r.sharpe != null ? fmt(r.sharpe, 2) : "—"}
          sub={r.sharpe != null ? (r.sharpe >= 2 ? "Excellent" : r.sharpe >= 1 ? "Good" : r.sharpe >= 0.5 ? "Average" : "Weak") : undefined}
          positive={r.sharpe != null ? r.sharpe >= 1 : undefined}
          icon={<Activity size={16} />} />
      </div>

      {/* ── Advanced Rolling Analytics ─────────────────────────────── */}
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider">Rolling Analytics</h2>
        <WindowSelector value={window} onChange={setWindow} />
      </div>

      {/* Row 1 — Rolling Sharpe | Rolling Volatility */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <Panel title="Rolling Sharpe Ratio">
          <RollingSharpeChart data={rollingData} />
        </Panel>
        <Panel title="Rolling Volatility">
          <RollingVolatilityChart data={rollingData} />
        </Panel>
      </div>

      {/* Row 2 — Rolling Beta | Rolling Correlation */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <Panel title="Rolling Beta vs SPY">
          <RollingBetaChart data={rollingData} />
        </Panel>
        <Panel title="Rolling Correlation vs SPY (90-day)">
          <RollingCorrelationChart data={corrData} />
        </Panel>
      </div>

      {/* Volatility Regime Timeline */}
      {regimeData.length > 0 && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
          <h3 className="text-sm font-semibold text-zinc-300 mb-3">Volatility Regime Timeline</h3>
          <VolatilityRegimeTimeline data={regimeData} />
        </div>
      )}

      {/* Row 3 — Drawdown chart */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-zinc-300">Drawdown History</h3>
          <div className="flex items-center gap-3">
            {r.max_drawdown_pct != null && (
              <span className="text-xs font-mono text-red-400">
                Max: {fmt(r.max_drawdown_pct, 2)}%
              </span>
            )}
            <div className="flex gap-0.5 bg-zinc-800 rounded-lg p-0.5">
              {RANGES.map(rng => (
                <button key={rng} onClick={() => setDdRange(rng)}
                  className={`px-2 py-1 text-xs rounded-md font-medium transition-colors ${
                    ddRange === rng ? "bg-blue-600 text-white" : "text-zinc-400 hover:text-zinc-200"
                  }`}>{rng}</button>
              ))}
            </div>
          </div>
        </div>
        {drawdownData.length > 1 ? (
          <DrawdownChart data={drawdownData} maxDrawdown={r.max_drawdown_pct ?? undefined} />
        ) : (
          <Empty msg="No drawdown data" />
        )}
      </div>

      {/* Row 4 — Risk Metrics | Portfolio Characteristics */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <Panel title="Risk Metrics">
          <RiskMetricsTable r={r} />
        </Panel>
        <Panel title="Portfolio Characteristics">
          {pm
            ? <PortfolioCharacteristicsTable pm={pm} />
            : <div className="text-xs text-zinc-500">Unavailable</div>}
        </Panel>
      </div>

      {/* Performance Summary | Benchmark Comparison */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-4">
          <div>
            <h3 className="text-sm font-semibold text-zinc-300 mb-3">Performance Summary</h3>
            {dm?.performance_summary
              ? <PerfSummary ps={dm.performance_summary} />
              : <div className="text-xs text-zinc-500">Unavailable</div>}
          </div>
          <div>
            <h3 className="text-sm font-semibold text-zinc-300 mb-2">Benchmark Comparison</h3>
            {dm?.benchmark_comparison
              ? <BenchComp bc={dm.benchmark_comparison} />
              : <div className="text-xs text-zinc-500">Unavailable</div>}
          </div>
        </div>

        <div className="grid grid-rows-2 gap-5">
          <Panel title="Daily Return Statistics">
            {dm ? <DailyStats dm={dm} /> : <div className="text-xs text-zinc-500">Unavailable</div>}
          </Panel>
          <Panel title="Drawdown Status">
            {dm ? <DrawdownStatus dm={dm} /> : <div className="text-xs text-zinc-500">Unavailable</div>}
          </Panel>
        </div>
      </div>

      {/* ── Correlation Clusters ─────────────────────────────────────────── */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-zinc-100 font-semibold text-base">Correlation Risk</h2>
          {multiClusters.length > 0 && (
            <span className="text-xs text-zinc-500 bg-zinc-800 px-2 py-0.5 rounded-full">
              {multiClusters.length}
            </span>
          )}
        </div>

        {!analysis ? (
          /* Analysis not yet loaded */
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {[0, 1, 2].map(i => (
              <div key={i} className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 h-32 animate-pulse" />
            ))}
          </div>
        ) : multiClusters.length === 0 ? (
          /* Analysis loaded, no correlated clusters found */
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 flex items-center gap-3">
            <span className="text-emerald-400 text-lg">✓</span>
            <p className="text-zinc-400 text-sm">
              No highly correlated asset clusters detected (threshold ≥ 0.70).
              Your portfolio positions are behaving independently.
            </p>
          </div>
        ) : (
          /* Clusters found */
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {multiClusters.map(c => (
              <CorrelationClusterCard key={c.cluster_id} cluster={c} />
            ))}
          </div>
        )}
      </div>

    </div>
  );
}
