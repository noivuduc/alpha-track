"use client";
import { useState, useEffect, useMemo, memo, useCallback } from "react";
import {
  AlertTriangle, CheckCircle, Info, TrendingUp, TrendingDown,
  Minus, RefreshCw, Activity, Layers, Zap,
} from "lucide-react";
import {
  portfolios as portApi,
  PortfolioAnalysisResponse,
  HealthBreakdown,
  RebalancingSuggestion,
  CorrelationCluster,
  SimulatorPrefillRow,
} from "@/lib/api";
import { suggestionToPrefill } from "@/lib/suggestionPrefill";

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function scoreColor(score: number): { text: string; ring: string; bg: string; fill: string } {
  if (score > 75) return {
    text: "text-emerald-400", ring: "stroke-emerald-400",
    bg: "bg-emerald-400/10", fill: "fill-emerald-400",
  };
  if (score >= 50) return {
    text: "text-amber-400", ring: "stroke-amber-400",
    bg: "bg-amber-400/10", fill: "fill-amber-400",
  };
  return {
    text: "text-red-400", ring: "stroke-red-400",
    bg: "bg-red-400/10", fill: "fill-red-400",
  };
}

function corrColor(corr: number): { badge: string; bar: string } {
  if (corr > 0.7) return { badge: "bg-red-500/20 text-red-300 border-red-500/30",   bar: "bg-red-400"     };
  if (corr > 0.4) return { badge: "bg-amber-500/20 text-amber-300 border-amber-500/30", bar: "bg-amber-400" };
  return              { badge: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30", bar: "bg-emerald-400" };
}

function actionStyle(action: "reduce" | "increase" | "add") {
  switch (action) {
    case "reduce":   return { badge: "bg-red-500/20 text-red-300 border-red-500/30",   icon: <TrendingDown size={12} /> };
    case "add":      return { badge: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30", icon: <TrendingUp size={12} /> };
    case "increase": return { badge: "bg-amber-500/20 text-amber-300 border-amber-500/30",  icon: <TrendingUp size={12} /> };
  }
}

function priorityDot(p: "high" | "medium" | "low") {
  switch (p) {
    case "high":   return "bg-red-400";
    case "medium": return "bg-amber-400";
    case "low":    return "bg-zinc-500";
  }
}

const BREAKDOWN_LABELS: Record<keyof HealthBreakdown, string> = {
  diversification:      "Diversification",
  concentration:        "Concentration",
  risk_adjusted_return: "Risk-adjusted return",
  drawdown:             "Drawdown",
  correlation:          "Correlation",
};

function insightIcon(text: string) {
  if (/high|risk|concentrat|overlap/i.test(text))
    return <AlertTriangle size={14} className="text-amber-400 shrink-0 mt-0.5" />;
  if (/strong|good|excellent|well/i.test(text))
    return <CheckCircle size={14} className="text-emerald-400 shrink-0 mt-0.5" />;
  return <Info size={14} className="text-blue-400 shrink-0 mt-0.5" />;
}

// ─────────────────────────────────────────────────────────────────────────────
// PART 1 — Circular gauge (pure SVG)
// ─────────────────────────────────────────────────────────────────────────────

const HealthGauge = memo(function HealthGauge({ score, grade }: { score: number; grade: string }) {
  const R   = 44;
  const CX  = 60;
  const CY  = 60;
  const CIRC = 2 * Math.PI * R;
  const offset = CIRC * (1 - Math.min(score, 100) / 100);
  const { text, ring } = scoreColor(score);

  return (
    <svg width={120} height={120} viewBox="0 0 120 120" className="shrink-0">
      {/* Track */}
      <circle cx={CX} cy={CY} r={R} fill="none" stroke="#27272a" strokeWidth={8} />
      {/* Progress */}
      <circle
        cx={CX} cy={CY} r={R} fill="none"
        className={`${ring} transition-all duration-700 ease-out`}
        strokeWidth={8}
        strokeLinecap="round"
        strokeDasharray={CIRC}
        strokeDashoffset={offset}
        transform={`rotate(-90 ${CX} ${CY})`}
      />
      {/* Score number */}
      <text
        x={CX} y={CY - 6}
        textAnchor="middle" dominantBaseline="middle"
        className={`${text} font-bold`}
        style={{ fontSize: 22, fontWeight: 700, fill: "currentColor" }}
        fill="currentColor"
      >
        {Math.round(score)}
      </text>
      {/* Grade */}
      <text
        x={CX} y={CY + 16}
        textAnchor="middle" dominantBaseline="middle"
        style={{ fontSize: 13, fontWeight: 600, fill: "#a1a1aa" }}
      >
        Grade {grade}
      </text>
    </svg>
  );
});

// ─────────────────────────────────────────────────────────────────────────────
// PART 2 — Breakdown bars
// ─────────────────────────────────────────────────────────────────────────────

const HealthBreakdownBar = memo(function HealthBreakdownBar({
  label, value,
}: { label: string; value: number }) {
  const { text, ring } = scoreColor(value);
  // Use a CSS class that matches the stroke color for the bar fill
  const barColor =
    value > 75 ? "bg-emerald-400" :
    value >= 50 ? "bg-amber-400" :
    "bg-red-400";

  return (
    <div className="flex items-center gap-3 group">
      <span className="text-zinc-400 text-xs w-40 shrink-0 group-hover:text-zinc-200 transition-colors">
        {label}
      </span>
      <div className="flex-1 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ease-out ${barColor}`}
          style={{ width: `${Math.min(value, 100)}%` }}
        />
      </div>
      <span className={`text-xs font-medium tabular-nums w-8 text-right ${text}`}>
        {Math.round(value)}
      </span>
    </div>
  );
});

// ─────────────────────────────────────────────────────────────────────────────
// PART 3 — Portfolio Health Card
// ─────────────────────────────────────────────────────────────────────────────

export const PortfolioHealthCard = memo(function PortfolioHealthCard({
  health,
}: { health: PortfolioAnalysisResponse["health"] }) {
  const { score, grade, breakdown, insights, top_issues } = health;
  const { text } = scoreColor(score);

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 space-y-6">
      {/* Header */}
      <div className="flex items-start gap-6">
        <HealthGauge score={score} grade={grade} />
        <div className="flex-1 min-w-0 pt-1">
          <div className="flex items-center gap-2 mb-1">
            <Activity size={14} className="text-zinc-500" />
            <span className="text-zinc-500 text-xs uppercase tracking-widest font-medium">
              Portfolio Health
            </span>
          </div>
          <p className={`text-3xl font-bold tabular-nums ${text}`}>
            {Math.round(score)}<span className="text-zinc-500 text-lg font-normal"> / 100</span>
          </p>
          <p className="text-zinc-500 text-sm mt-1">
            {score > 75 ? "Well diversified with strong risk characteristics"
              : score >= 50 ? "Room to improve diversification and risk balance"
              : "Significant risks detected — review suggestions below"}
          </p>

          {/* Top issues — quick-scan pills shown right under score */}
          {top_issues && top_issues.length > 0 && (
            <div className="flex flex-wrap gap-2 mt-3">
              {top_issues.map((issue, i) => (
                <span
                  key={i}
                  className="inline-flex items-center gap-1.5 text-xs bg-red-500/10 text-red-300 border border-red-500/25 rounded-full px-2.5 py-1"
                >
                  <AlertTriangle size={11} className="shrink-0" />
                  {issue}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Breakdown */}
      <div className="space-y-2.5">
        <p className="text-zinc-500 text-xs uppercase tracking-widest font-medium">Breakdown</p>
        {(Object.keys(BREAKDOWN_LABELS) as (keyof HealthBreakdown)[]).map(key => (
          <HealthBreakdownBar
            key={key}
            label={BREAKDOWN_LABELS[key]}
            value={breakdown[key]}
          />
        ))}
      </div>

      {/* Insights */}
      {insights.length > 0 && (
        <div className="space-y-2 pt-1 border-t border-zinc-800">
          {insights.map((ins, i) => (
            <div key={i} className="flex items-start gap-2">
              {insightIcon(ins)}
              <span className="text-zinc-400 text-sm leading-snug">{ins}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
});

// ─────────────────────────────────────────────────────────────────────────────
// PART 4 — Metric delta table + Suggestion Card
// ─────────────────────────────────────────────────────────────────────────────

// Metadata: label + whether a positive delta means good (green)
const DELTA_META: Record<string, { label: string; positiveIsGood: boolean }> = {
  sharpe:                { label: "Sharpe",     positiveIsGood: true  },
  volatility_pct:        { label: "Volatility", positiveIsGood: false },
  max_drawdown_pct:      { label: "Drawdown",   positiveIsGood: true  }, // drawdown is negative; positive delta = less severe
  annualized_return_pct: { label: "Return",     positiveIsGood: true  },
};

function deltaColor(key: string, rawValue: string): string {
  const meta = DELTA_META[key];
  if (!meta) return "text-zinc-400";
  const num = parseFloat(rawValue.replace("%", ""));
  const isPositive = num > 0;
  const isGood = meta.positiveIsGood ? isPositive : !isPositive;
  return isGood ? "text-emerald-400" : "text-red-400";
}

function MetricsDeltaTable({ delta }: { delta: Record<string, string> }) {
  const entries = Object.entries(delta).filter(([k]) => k in DELTA_META);
  if (!entries.length) return null;
  return (
    <div className="grid grid-cols-2 gap-x-4 gap-y-1 bg-zinc-800/40 rounded-lg px-3 py-2">
      {entries.map(([key, val]) => (
        <div key={key} className="flex items-center justify-between gap-2">
          <span className="text-zinc-500 text-xs">{DELTA_META[key]?.label ?? key}</span>
          <span className={`text-xs font-mono font-semibold tabular-nums ${deltaColor(key, val)}`}>
            {val}
          </span>
        </div>
      ))}
    </div>
  );
}

export const SuggestionCard = memo(function SuggestionCard({
  s, onSimulate,
}: {
  s: RebalancingSuggestion;
  onSimulate?: (prefill: SimulatorPrefillRow[]) => void;
}) {
  const { badge, icon } = actionStyle(s.action);
  const dot  = priorityDot(s.priority);
  const subject = s.ticker ?? s.sector ?? "Portfolio";

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 hover:border-zinc-600 transition-all duration-150 group space-y-3">
      {/* Top row */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 flex-wrap">
          {/* Action badge */}
          <span className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full border ${badge}`}>
            {icon}
            {s.action.charAt(0).toUpperCase() + s.action.slice(1)}
          </span>
          {/* Subject */}
          <span className="text-zinc-100 font-semibold text-sm">{subject}</span>
        </div>
        {/* Priority dot */}
        <div className="flex items-center gap-1.5 shrink-0">
          <span className={`w-2 h-2 rounded-full ${dot}`} />
          <span className="text-zinc-500 text-xs capitalize">{s.priority}</span>
        </div>
      </div>

      {/* Reason */}
      <p className="text-zinc-400 text-sm leading-snug">{s.reason}</p>

      {/* Metric deltas — inline table */}
      {s.metrics_delta && Object.keys(s.metrics_delta).length > 0 && (
        <MetricsDeltaTable delta={s.metrics_delta} />
      )}

      {/* Impact */}
      <div className="flex items-start gap-2 bg-zinc-800/50 rounded-lg px-3 py-2">
        <Zap size={12} className="text-blue-400 mt-0.5 shrink-0" />
        <p className="text-zinc-400 text-xs leading-snug">{s.impact}</p>
      </div>

      {/* CTA — for ticker-level suggestions */}
      {s.ticker && onSimulate && (
        <button
          onClick={() => onSimulate(suggestionToPrefill(s))}
          className="w-full text-xs font-medium text-blue-300 hover:text-white bg-blue-600/10 hover:bg-blue-600/20 border border-blue-500/30 hover:border-blue-400/60 rounded-lg py-2 transition-all"
        >
          Apply &amp; Simulate →
        </button>
      )}
    </div>
  );
});

// ─────────────────────────────────────────────────────────────────────────────
// PART 5 — Correlation Cluster Card
// ─────────────────────────────────────────────────────────────────────────────

export const CorrelationClusterCard = memo(function CorrelationClusterCard({
  cluster,
}: { cluster: CorrelationCluster }) {
  const { badge } = corrColor(cluster.avg_correlation);
  const corrPct = Math.round(cluster.avg_correlation * 100);

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-3 hover:border-zinc-600 transition-colors">
      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <Layers size={14} className="text-zinc-500 shrink-0" />
          <span className="text-zinc-200 text-sm font-semibold truncate">{cluster.label}</span>
        </div>
        <span className={`inline-flex items-center text-xs font-medium px-2 py-0.5 rounded-full border whitespace-nowrap ${badge}`}>
          {corrPct}% corr
        </span>
      </div>

      {/* Asset chips */}
      <div className="flex flex-wrap gap-2">
        {cluster.assets.map(asset => (
          <span
            key={asset}
            className="text-xs font-mono font-semibold bg-zinc-800 text-zinc-200 border border-zinc-700 px-2.5 py-1 rounded-lg hover:border-zinc-500 transition-colors"
          >
            {asset}
          </span>
        ))}
      </div>

      {/* Correlation bar */}
      <div className="space-y-1">
        <div className="flex justify-between text-xs text-zinc-600">
          <span>Low</span>
          <span>High</span>
        </div>
        <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ${corrColor(cluster.avg_correlation).bar}`}
            style={{ width: `${Math.min(cluster.avg_correlation * 100, 100)}%` }}
          />
        </div>
      </div>

      {/* Insight */}
      {cluster.insight ? (
        <p className="text-zinc-500 text-xs leading-snug">{cluster.insight}</p>
      ) : cluster.avg_correlation > 0.7 ? (
        <p className="text-zinc-500 text-xs leading-snug">
          These assets move together — holding all of them provides less diversification than it appears.
        </p>
      ) : cluster.avg_correlation > 0.4 ? (
        <p className="text-zinc-500 text-xs leading-snug">
          Moderate correlation. These assets partially offset each other in downturns.
        </p>
      ) : (
        <p className="text-zinc-500 text-xs leading-snug">
          Low correlation — these assets diversify well against each other.
        </p>
      )}
    </div>
  );
});

// ─────────────────────────────────────────────────────────────────────────────
// PART 6 — Empty / Loading / Error states
// ─────────────────────────────────────────────────────────────────────────────

function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`bg-zinc-800 rounded-lg animate-pulse ${className}`} />;
}

function AnalysisSkeleton() {
  return (
    <div className="space-y-6">
      {/* Health card skeleton */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 space-y-6">
        <div className="flex gap-6">
          <Skeleton className="w-[120px] h-[120px] rounded-full" />
          <div className="flex-1 space-y-3 pt-1">
            <Skeleton className="h-3 w-32" />
            <Skeleton className="h-8 w-24" />
            <Skeleton className="h-4 w-64" />
          </div>
        </div>
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="flex items-center gap-3">
              <Skeleton className="h-3 w-36" />
              <Skeleton className="flex-1 h-1.5" />
              <Skeleton className="h-3 w-8" />
            </div>
          ))}
        </div>
      </div>
      {/* Suggestion skeletons */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-36 rounded-xl" />
        ))}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// PART 7 — Section header
// ─────────────────────────────────────────────────────────────────────────────

function SectionHeader({ title, count }: { title: string; count?: number }) {
  return (
    <div className="flex items-center gap-3">
      <h2 className="text-zinc-100 font-semibold text-base">{title}</h2>
      {count != null && count > 0 && (
        <span className="text-xs text-zinc-500 bg-zinc-800 px-2 py-0.5 rounded-full">
          {count}
        </span>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// ROOT — AnalysisTab
// ─────────────────────────────────────────────────────────────────────────────

interface Props {
  portfolioId: string;
  onOpenSimulator?: (prefill: SimulatorPrefillRow[]) => void;
}

export default function AnalysisTab({ portfolioId, onOpenSimulator }: Props) {
  const [data,    setData]    = useState<PortfolioAnalysisResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);

  const load = useCallback((force = false) => {
    setLoading(true);
    setError(null);
    portApi.analysis(portfolioId, force)
      .then(setData)
      .catch(e => setError(e.message ?? "Failed to load analysis"))
      .finally(() => setLoading(false));
  }, [portfolioId]);

  useEffect(() => { load(); }, [load]);

  // Separate high-priority from rest for visual hierarchy
  const { highSugs, otherSugs } = useMemo(() => {
    if (!data) return { highSugs: [], otherSugs: [] };
    return {
      highSugs:  data.suggestions.filter(s => s.priority === "high"),
      otherSugs: data.suggestions.filter(s => s.priority !== "high"),
    };
  }, [data]);

  // ── Loading ──────────────────────────────────────────────────────────────
  if (loading) return <AnalysisSkeleton />;

  // ── Error ────────────────────────────────────────────────────────────────
  if (error) return (
    <div className="flex flex-col items-center justify-center h-64 gap-3">
      <AlertTriangle size={32} className="text-red-400" />
      <p className="text-zinc-400 text-sm">{error}</p>
      <button
        onClick={() => load(true)}
        className="text-xs text-blue-400 hover:text-blue-300 border border-blue-500/30 hover:border-blue-400/50 rounded-lg px-4 py-2 transition-colors"
      >
        Retry
      </button>
    </div>
  );

  // ── Empty (no positions) ─────────────────────────────────────────────────
  if (!data) return (
    <div className="flex flex-col items-center justify-center h-64 gap-2">
      <Activity size={32} className="text-zinc-600" />
      <p className="text-zinc-400 text-sm">No analysis data</p>
    </div>
  );

  return (
    <div className="space-y-8">
      {/* Refresh control */}
      <div className="flex items-center justify-between">
        <p className="text-zinc-600 text-xs">
          Computed {new Date(data.computed_at).toLocaleString()}
        </p>
        <button
          onClick={() => load(true)}
          className="flex items-center gap-1.5 text-zinc-500 hover:text-zinc-300 text-xs transition-colors"
        >
          <RefreshCw size={12} />
          Refresh
        </button>
      </div>

      {/* ── 1. Portfolio Health ─────────────────────────────────────────── */}
      <PortfolioHealthCard health={data.health} />

      {/* ── 2. Rebalancing Suggestions ──────────────────────────────────── */}
      {data.suggestions.length > 0 && (
        <section className="space-y-4">
          <SectionHeader title="Rebalancing Suggestions" count={data.suggestions.length} />

          {/* High-priority first in full-width row */}
          {highSugs.length > 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {highSugs.map((s, i) => (
                <SuggestionCard key={i} s={s} onSimulate={onOpenSimulator} />
              ))}
            </div>
          )}

          {/* Medium/low in a slightly lighter section */}
          {otherSugs.length > 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {otherSugs.map((s, i) => (
                <SuggestionCard key={i} s={s} onSimulate={onOpenSimulator} />
              ))}
            </div>
          )}
        </section>
      )}

      {data.suggestions.length === 0 && (
        <section className="space-y-4">
          <SectionHeader title="Rebalancing Suggestions" />
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 flex items-center gap-3">
            <CheckCircle size={20} className="text-emerald-400 shrink-0" />
            <p className="text-zinc-400 text-sm">
              No rebalancing actions needed — your portfolio looks well-positioned.
            </p>
          </div>
        </section>
      )}

      {/* ── 3. Correlation Clusters ─────────────────────────────────────── */}
      {(() => {
        // Guard: only show clusters with >= 2 assets (backend filters, but be defensive)
        const multiClusters = data.clusters.filter(c => c.assets.length >= 2);
        if (!multiClusters.length) return null;
        return (
          <section className="space-y-4">
            <div className="flex items-start justify-between gap-4">
              <SectionHeader title="Correlation Risk" count={multiClusters.length} />
              <p className="text-zinc-600 text-xs text-right hidden sm:block max-w-xs">
                Assets grouped by correlation ≥ 0.70 behave similarly and reduce effective diversification.
              </p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {multiClusters.map(c => (
                <CorrelationClusterCard key={c.cluster_id} cluster={c} />
              ))}
            </div>
          </section>
        );
      })()}
    </div>
  );
}
