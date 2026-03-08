"use client";
import { useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from "recharts";
import { AnalystEstimate } from "@/lib/api";

function fmtLarge(n: number | undefined | null): string {
  if (n == null) return "—";
  if (Math.abs(n) >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (Math.abs(n) >= 1e9)  return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6)  return `$${(n / 1e6).toFixed(1)}M`;
  return `$${n.toLocaleString()}`;
}

const TT_STYLE = {
  backgroundColor: "#18181b", border: "1px solid #3f3f46",
  borderRadius: 8, color: "#e4e4e7", fontSize: 12,
};

type Tab = "annual" | "quarterly";

function EstimateCharts({ rows }: { rows: AnalystEstimate[] }) {
  // Oldest → newest for chart
  const data = [...rows].reverse().map(r => ({
    label: r.fiscal_period,
    revenue: r.revenue ?? null,
    eps: r.earnings_per_share ?? null,
  }));

  if (!data.length) return null;

  const hasRevenue = data.some(d => d.revenue != null);
  const hasEps     = data.some(d => d.eps != null);

  return (
    <div className={`grid gap-4 ${hasRevenue && hasEps ? "grid-cols-1 md:grid-cols-2" : "grid-cols-1"}`}>
      {hasRevenue && (
        <div className="bg-zinc-800/40 rounded-xl p-4">
          <div className="text-xs font-semibold text-zinc-400 mb-3">Revenue Estimate Trend</div>
          <ResponsiveContainer width="100%" height={160}>
            <LineChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
              <XAxis dataKey="label" tick={{ fill: "#71717a", fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis
                tick={{ fill: "#71717a", fontSize: 10 }} axisLine={false} tickLine={false}
                tickFormatter={v => fmtLarge(v)} width={60}
              />
              <Tooltip contentStyle={TT_STYLE} formatter={(v) => [fmtLarge(Number(v)), "Revenue Est."]} />
              <Line type="monotone" dataKey="revenue" stroke="#3b82f6" strokeWidth={2} dot={{ r: 4, fill: "#3b82f6" }} activeDot={{ r: 5 }} connectNulls />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
      {hasEps && (
        <div className="bg-zinc-800/40 rounded-xl p-4">
          <div className="text-xs font-semibold text-zinc-400 mb-3">EPS Estimate Trend</div>
          <ResponsiveContainer width="100%" height={160}>
            <LineChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
              <XAxis dataKey="label" tick={{ fill: "#71717a", fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis
                tick={{ fill: "#71717a", fontSize: 10 }} axisLine={false} tickLine={false}
                tickFormatter={v => `$${v.toFixed(2)}`} width={52}
              />
              <Tooltip contentStyle={TT_STYLE} formatter={(v) => [`$${Number(v).toFixed(2)}`, "EPS Est."]} />
              <ReferenceLine y={0} stroke="#52525b" />
              <Line type="monotone" dataKey="eps" stroke="#8b5cf6" strokeWidth={2} dot={{ r: 4, fill: "#8b5cf6" }} activeDot={{ r: 5 }} connectNulls />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

function EstimateTable({ rows }: { rows: AnalystEstimate[] }) {
  if (!rows.length) return <div className="text-xs text-zinc-500 py-4">No estimate data available</div>;
  return (
    <div className="overflow-x-auto scrollbar-thin">
      <table className="w-full text-xs min-w-[360px]">
        <thead>
          <tr className="border-b border-zinc-700">
            {["Period", "Revenue Est.", "EPS Est."].map(h => (
              <th key={h} className={`py-2 font-medium text-zinc-500 ${h === "Period" ? "text-left pr-4" : "text-right px-3"}`}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-zinc-800/50 hover:bg-zinc-800/30 transition-colors">
              <td className="py-2 pr-4 text-zinc-300 font-mono">{r.fiscal_period}</td>
              <td className="py-2 px-3 text-right font-mono tabular-nums text-zinc-200">{fmtLarge(r.revenue)}</td>
              <td className="py-2 px-3 text-right font-mono tabular-nums text-emerald-400">
                {r.earnings_per_share != null ? `$${r.earnings_per_share.toFixed(2)}` : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function EstimatesSection({
  annual, quarterly,
}: { annual: AnalystEstimate[]; quarterly: AnalystEstimate[] }) {
  const [tab, setTab] = useState<Tab>("annual");
  const rows = tab === "annual" ? annual : quarterly;

  const tabs: { id: Tab; label: string }[] = [
    { id: "annual",    label: "Annual"    },
    { id: "quarterly", label: "Quarterly" },
  ];

  return (
    <div className="space-y-5">
      {/* Tab toggle */}
      <div className="flex gap-0.5 bg-zinc-800 rounded-lg p-0.5 w-fit">
        {tabs.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`px-3 py-1 text-xs rounded-md font-medium transition-colors ${
              tab === t.id ? "bg-blue-600 text-white" : "text-zinc-400 hover:text-zinc-200"
            }`}>
            {t.label}
          </button>
        ))}
      </div>

      {/* Trend charts */}
      <EstimateCharts rows={rows} />

      {/* Table */}
      <EstimateTable rows={rows} />
    </div>
  );
}
