"use client";
import { useEffect, useState } from "react";
import { RefreshCw, DollarSign, TrendingUp } from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer, Cell,
} from "recharts";
import { adminApi, CostSummary, ProviderCostDay } from "@/lib/api";
import StatCard from "@/components/admin/StatCard";

const PROVIDER_COLORS: Record<string, string> = {
  financialdatasets: "#3b82f6",
  yfinance:          "#10b981",
  cache_redis:       "#a855f7",
  cache_pg:          "#f59e0b",
};
function provColor(p: string) { return PROVIDER_COLORS[p] ?? "#71717a"; }

const TT_STYLE = {
  backgroundColor: "#18181b", border: "1px solid #3f3f46",
  borderRadius: 8, color: "#e4e4e7", fontSize: 11,
};

type Days = 7 | 30 | 90;

function buildChartData(daily: ProviderCostDay[], providers: string[]) {
  const byDate: Record<string, Record<string, number>> = {};
  for (const d of daily) {
    if (!byDate[d.date]) byDate[d.date] = { date: d.date as unknown as number };
    byDate[d.date][d.provider] = (byDate[d.date][d.provider] ?? 0) + d.calls;
  }
  return Object.values(byDate).sort((a, b) => String(a.date).localeCompare(String(b.date)));
}

export default function AdminCostsPage() {
  const [summary, setSummary] = useState<CostSummary | null>(null);
  const [days,    setDays]    = useState<Days>(30);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);

  function load(d = days) {
    setLoading(true); setError(null);
    adminApi.costs(d)
      .then(setSummary)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }

  useEffect(() => { load(); }, [days]);

  const providers = summary
    ? [...new Set(summary.daily.map(d => d.provider))]
    : [];

  const chartData = summary ? buildChartData(summary.daily, providers) : [];

  // Cost-only daily
  const costByDate: Record<string, Record<string, number>> = {};
  for (const d of summary?.daily ?? []) {
    if (!costByDate[d.date]) costByDate[d.date] = { date: d.date as unknown as number };
    costByDate[d.date][d.provider] = (costByDate[d.date][d.provider] ?? 0) + d.estimated_cost_usd;
  }
  const costChartData = Object.values(costByDate).sort((a, b) => String(a.date).localeCompare(String(b.date)));

  return (
    <div className="p-6 max-w-5xl">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-xl font-bold text-zinc-50">Cost Tracking</h1>
          <p className="text-sm text-zinc-500">API usage and estimated costs by provider</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex gap-0.5 bg-zinc-800 rounded-lg p-0.5">
            {([7, 30, 90] as Days[]).map(d => (
              <button key={d} onClick={() => setDays(d)}
                className={`px-3 py-1 text-xs rounded-md font-medium transition-colors ${days === d ? "bg-blue-600 text-white" : "text-zinc-400 hover:text-zinc-200"}`}>
                {d}d
              </button>
            ))}
          </div>
          <button onClick={() => load()} className="p-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-400 transition-colors">
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {error && <div className="mb-3 text-xs text-red-400 bg-red-900/20 border border-red-800 rounded-lg px-3 py-2">{error}</div>}

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatCard title="Total Calls"    value={summary?.total_calls.toLocaleString() ?? "—"} icon={<TrendingUp size={16}/>} color="zinc"  loading={loading} sub={`${days}d`} />
        <StatCard title="Estimated Cost" value={summary ? `$${summary.total_cost_usd.toFixed(4)}` : "—"} icon={<DollarSign size={16}/>} color="amber" loading={loading} sub={`${days}d`} />
        {Object.entries(summary?.by_provider ?? {}).slice(0, 2).map(([prov, d]) => (
          <StatCard key={prov} title={prov} value={d.calls.toLocaleString()} loading={loading}
            sub={`$${d.estimated_cost_usd.toFixed(4)}`} color="zinc" />
        ))}
      </div>

      {/* Call volume chart */}
      {chartData.length > 0 && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 mb-4">
          <h2 className="text-sm font-semibold text-zinc-400 mb-4">API Calls by Provider (daily)</h2>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={chartData} margin={{ top: 0, right: 10, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
              <XAxis dataKey="date" tick={{ fill: "#71717a", fontSize: 10 }} axisLine={false} tickLine={false}
                tickFormatter={d => String(d).slice(5)} />
              <YAxis tick={{ fill: "#71717a", fontSize: 10 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={TT_STYLE} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              {providers.map(p => (
                <Bar key={p} dataKey={p} stackId="a" fill={provColor(p)} radius={[2, 2, 0, 0]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Cost chart */}
      {costChartData.length > 0 && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 mb-6">
          <h2 className="text-sm font-semibold text-zinc-400 mb-4">Estimated Cost by Provider (daily, $)</h2>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={costChartData} margin={{ top: 0, right: 10, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
              <XAxis dataKey="date" tick={{ fill: "#71717a", fontSize: 10 }} axisLine={false} tickLine={false}
                tickFormatter={d => String(d).slice(5)} />
              <YAxis tick={{ fill: "#71717a", fontSize: 10 }} axisLine={false} tickLine={false}
                tickFormatter={v => `$${Number(v).toFixed(3)}`} />
              <Tooltip contentStyle={TT_STYLE} formatter={(v: number) => [`$${v.toFixed(4)}`, ""]} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              {providers.filter(p => p === "financialdatasets").map(p => (
                <Bar key={p} dataKey={p} fill={provColor(p)} radius={[4, 4, 0, 0]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Per-provider breakdown */}
      {summary && Object.keys(summary.by_provider).length > 0 && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-zinc-800">
            <h2 className="text-sm font-semibold text-zinc-400">Breakdown by Provider</h2>
          </div>
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-zinc-800 bg-zinc-900/60">
                <th className="text-left py-2 px-4 text-zinc-500">Provider</th>
                <th className="text-right py-2 px-4 text-zinc-500">Total Calls</th>
                <th className="text-right py-2 px-4 text-zinc-500">Est. Cost</th>
                <th className="text-right py-2 px-4 text-zinc-500">% of Calls</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(summary.by_provider)
                .sort((a, b) => b[1].calls - a[1].calls)
                .map(([prov, d]) => (
                  <tr key={prov} className="border-b border-zinc-800/50">
                    <td className="py-2.5 px-4">
                      <div className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full" style={{ backgroundColor: provColor(prov) }} />
                        <span className="font-mono text-zinc-300">{prov}</span>
                      </div>
                    </td>
                    <td className="py-2.5 px-4 text-right tabular-nums text-zinc-300">{d.calls.toLocaleString()}</td>
                    <td className="py-2.5 px-4 text-right tabular-nums text-zinc-300">${d.estimated_cost_usd.toFixed(4)}</td>
                    <td className="py-2.5 px-4 text-right tabular-nums text-zinc-500">
                      {summary.total_calls > 0 ? `${((d.calls / summary.total_calls) * 100).toFixed(1)}%` : "—"}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
