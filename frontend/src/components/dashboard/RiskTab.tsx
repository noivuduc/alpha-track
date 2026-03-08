"use client";
import dynamic from "next/dynamic";
import { PortfolioAnalytics } from "@/lib/api";
import { fmt } from "@/lib/portfolio-math";

const DrawdownChart  = dynamic(() => import("@/components/charts/DrawdownChart"),  { ssr: false });
const MonthlyHeatmap = dynamic(() => import("@/components/charts/MonthlyHeatmap"), { ssr: false });

interface Props {
  analytics: PortfolioAnalytics | null;
  loading:   boolean;
  period:    string;
}

interface MetricCardProps {
  label:    string;
  value:    string;
  sub?:     string;
  color?:   string;
  tooltip?: string;
  badge?:   "good" | "warn" | "bad" | "neutral";
}

const BADGE_CLASS = {
  good:    "bg-emerald-950 border-emerald-800 text-emerald-400",
  warn:    "bg-amber-950  border-amber-800  text-amber-400",
  bad:     "bg-red-950    border-red-800    text-red-400",
  neutral: "bg-zinc-800   border-zinc-700   text-zinc-400",
};

function MetricCard({ label, value, sub, tooltip, badge = "neutral" }: MetricCardProps) {
  return (
    <div
      className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 cursor-default"
      title={tooltip}
    >
      <div className="text-xs text-zinc-500 mb-2">{label}</div>
      <div className={`text-2xl font-bold font-mono tabular-nums border rounded-lg px-3 py-1 inline-block ${BADGE_CLASS[badge]}`}>
        {value}
      </div>
      {sub && <div className="text-xs text-zinc-500 mt-2">{sub}</div>}
    </div>
  );
}

function scoreBadge(value: number, thresholds: [number, number]): "good" | "warn" | "bad" {
  if (value >= thresholds[0]) return "good";
  if (value >= thresholds[1]) return "warn";
  return "bad";
}

function formatMetric(v: number | null | undefined, suffix = "", prefix = ""): string {
  if (v == null) return "—";
  return `${prefix}${fmt(v, 2)}${suffix}`;
}

export default function RiskTab({ analytics, loading, period }: Props) {
  if (loading && !analytics) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!analytics) {
    return (
      <div className="text-center py-16 text-zinc-500">
        {loading ? "Computing risk metrics…" : "Add positions to see risk analytics"}
      </div>
    );
  }

  const r = analytics.risk_metrics;
  const dd = analytics.drawdown;
  const mh = analytics.monthly_returns;

  // Build metric cards configuration
  const metrics: MetricCardProps[] = [
    {
      label:   "Sharpe Ratio",
      value:   formatMetric(r.sharpe),
      sub:     "Excess return per unit of risk",
      badge:   r.sharpe != null ? scoreBadge(r.sharpe, [1, 0.5]) : "neutral",
      tooltip: "(Portfolio − RF) / σ × √252 · RF = 5.25%",
    },
    {
      label:   "Sortino Ratio",
      value:   formatMetric(r.sortino),
      sub:     "Downside-adjusted return",
      badge:   r.sortino != null ? scoreBadge(r.sortino, [1.5, 0.75]) : "neutral",
      tooltip: "Like Sharpe but penalises only negative returns",
    },
    {
      label:   "Beta (vs SPY)",
      value:   formatMetric(r.beta),
      sub:     "Market sensitivity",
      badge:   r.beta != null
                 ? (r.beta < 0.8 ? "good" : r.beta < 1.2 ? "neutral" : "warn")
                 : "neutral",
      tooltip: "Covariance(portfolio, SPY) / Variance(SPY)",
    },
    {
      label:   "Alpha (Ann.)",
      value:   r.alpha_pct != null ? `${r.alpha_pct >= 0 ? "+" : ""}${fmt(r.alpha_pct, 2)}%` : "—",
      sub:     "Return above beta-explained",
      badge:   r.alpha_pct != null ? scoreBadge(r.alpha_pct, [1, 0]) : "neutral",
      tooltip: "Jensen's alpha: annualized excess return vs market",
    },
    {
      label:   "Max Drawdown",
      value:   r.max_drawdown_pct != null ? `${fmt(r.max_drawdown_pct, 2)}%` : "—",
      sub:     "Peak-to-trough",
      badge:   r.max_drawdown_pct != null
                 ? (r.max_drawdown_pct > -10 ? "good" : r.max_drawdown_pct > -20 ? "warn" : "bad")
                 : "neutral",
      tooltip: "Maximum peak-to-trough portfolio decline",
    },
    {
      label:   "Volatility",
      value:   r.volatility_pct != null ? `${fmt(r.volatility_pct, 1)}%` : "—",
      sub:     "Annualized daily σ",
      badge:   r.volatility_pct != null
                 ? (r.volatility_pct < 15 ? "good" : r.volatility_pct < 25 ? "warn" : "bad")
                 : "neutral",
      tooltip: "σ(daily returns) × √252",
    },
    {
      label:   "Calmar Ratio",
      value:   formatMetric(r.calmar),
      sub:     "Ann. return / |max DD|",
      badge:   r.calmar != null ? scoreBadge(r.calmar, [0.75, 0.3]) : "neutral",
      tooltip: "Annualized return divided by absolute max drawdown",
    },
    {
      label:   "Win Rate",
      value:   r.win_rate_pct != null ? `${fmt(r.win_rate_pct, 1)}%` : "—",
      sub:     "% positive return days",
      badge:   r.win_rate_pct != null ? scoreBadge(r.win_rate_pct, [55, 48]) : "neutral",
      tooltip: "Fraction of trading days with a positive return",
    },
    {
      label:   "Ann. Return",
      value:   r.annualized_return_pct != null
                 ? `${r.annualized_return_pct >= 0 ? "+" : ""}${fmt(r.annualized_return_pct, 2)}%`
                 : "—",
      sub:     "Geometric annualized",
      badge:   r.annualized_return_pct != null ? scoreBadge(r.annualized_return_pct, [10, 0]) : "neutral",
      tooltip: "(Portfolio compound return)^(252/N) − 1",
    },
    {
      label:   "Info. Ratio",
      value:   formatMetric(r.information_ratio),
      sub:     "Active return / tracking error",
      badge:   r.information_ratio != null ? scoreBadge(r.information_ratio, [0.5, 0]) : "neutral",
      tooltip: "Annualized active return vs SPY / tracking error",
    },
    {
      label:   "VaR (95%)",
      value:   r.var_95_pct != null ? `-${fmt(r.var_95_pct, 2)}%` : "—",
      sub:     "1-day historical 5th pct",
      badge:   r.var_95_pct != null ? (r.var_95_pct < 2 ? "good" : r.var_95_pct < 4 ? "warn" : "bad") : "neutral",
      tooltip: "Worst expected daily loss at 95% confidence",
    },
    {
      label:   "Trading Days",
      value:   r.trading_days != null ? String(r.trading_days) : "—",
      sub:     `${period} period`,
      badge:   "neutral",
      tooltip: "Number of trading days in the analysis window",
    },
  ];

  return (
    <div className="space-y-6">
      {/* 12 metric cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
        {metrics.map(m => (
          <MetricCard key={m.label} {...m} />
        ))}
      </div>

      {/* Drawdown chart */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-zinc-300">Drawdown History</h3>
          {r.max_drawdown_pct != null && (
            <span className="text-xs font-mono text-red-400">
              Max: {fmt(r.max_drawdown_pct, 2)}%
            </span>
          )}
        </div>
        {dd.length > 1 ? (
          <DrawdownChart data={dd} />
        ) : (
          <div className="h-40 flex items-center justify-center text-zinc-500 text-sm">
            No drawdown data
          </div>
        )}
      </div>

      {/* Monthly returns heatmap */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
        <h3 className="text-sm font-semibold text-zinc-300 mb-4">Monthly Returns</h3>
        {mh.length > 0 ? (
          <MonthlyHeatmap data={mh} />
        ) : (
          <div className="h-20 flex items-center justify-center text-zinc-500 text-sm">
            No monthly data
          </div>
        )}
      </div>
    </div>
  );
}
