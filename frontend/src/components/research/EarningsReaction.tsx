"use client";
import { useMemo } from "react";
import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, Cell,
  BarChart, Bar,
} from "recharts";
import { EarningsRecord } from "@/lib/api";

const TT_STYLE = {
  backgroundColor: "#18181b", border: "1px solid #3f3f46",
  borderRadius: 8, color: "#e4e4e7", fontSize: 12,
};

function fmt(n: number | undefined | null, d = 2): string {
  if (n == null) return "—";
  return n.toFixed(d);
}

function SurpriseBadge({ pct }: { pct: number | undefined | null }) {
  if (pct == null) return <span className="text-zinc-600">—</span>;
  const color = pct > 0 ? "text-emerald-400 bg-emerald-400/10" : pct < 0 ? "text-red-400 bg-red-400/10" : "text-zinc-400 bg-zinc-700";
  return (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-mono ${color}`}>
      {pct > 0 ? "+" : ""}{pct.toFixed(1)}%
    </span>
  );
}

export default function EarningsReaction({ earnings }: { earnings: EarningsRecord[] }) {
  // Only show records with actual data
  const withData = useMemo(
    () => earnings.filter(e => e.eps_actual != null || e.eps_estimate != null),
    [earnings]
  );

  // Scatter data: surprise % vs hypothetical reaction (we don't have price reaction from backend)
  const scatterData = useMemo(
    () => withData
      .filter(e => e.surprise_pct != null && e.eps_actual != null)
      .map(e => ({
        date: e.date,
        surprise: e.surprise_pct!,
        beat: e.surprise_pct! > 0,
      })),
    [withData]
  );

  // Summary: beat/miss counts
  const beatCount = scatterData.filter(d => d.surprise > 0).length;
  const missCount = scatterData.filter(d => d.surprise <= 0).length;
  const avgBeat   = beatCount > 0
    ? scatterData.filter(d => d.surprise > 0).reduce((a, b) => a + b.surprise, 0) / beatCount
    : 0;
  const avgMiss   = missCount > 0
    ? scatterData.filter(d => d.surprise <= 0).reduce((a, b) => a + b.surprise, 0) / missCount
    : 0;

  const summaryData = [
    { label: "Beat", value: parseFloat(avgBeat.toFixed(1)), count: beatCount },
    { label: "Miss", value: parseFloat(avgMiss.toFixed(1)), count: missCount },
  ];

  if (!withData.length) {
    return <div className="text-xs text-zinc-500 py-4">No earnings history available for this ticker.</div>;
  }

  return (
    <div className="space-y-5">
      {/* Beat/miss summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="bg-zinc-800/60 border border-zinc-700/50 rounded-xl p-3">
          <div className="text-xs text-zinc-500 mb-1">Quarters Tracked</div>
          <div className="text-xl font-bold text-zinc-100">{scatterData.length}</div>
        </div>
        <div className="bg-zinc-800/60 border border-zinc-700/50 rounded-xl p-3">
          <div className="text-xs text-zinc-500 mb-1">Beat Rate</div>
          <div className="text-xl font-bold text-emerald-400">
            {scatterData.length ? `${Math.round((beatCount / scatterData.length) * 100)}%` : "—"}
          </div>
        </div>
        <div className="bg-zinc-800/60 border border-zinc-700/50 rounded-xl p-3">
          <div className="text-xs text-zinc-500 mb-1">Avg Beat</div>
          <div className="text-xl font-bold text-emerald-400">+{avgBeat.toFixed(1)}%</div>
        </div>
        <div className="bg-zinc-800/60 border border-zinc-700/50 rounded-xl p-3">
          <div className="text-xs text-zinc-500 mb-1">Avg Miss</div>
          <div className="text-xl font-bold text-red-400">{avgMiss.toFixed(1)}%</div>
        </div>
      </div>

      {/* EPS Surprise history bar chart */}
      {scatterData.length > 0 && (
        <div className="bg-zinc-800/40 rounded-xl p-4">
          <div className="text-xs font-semibold text-zinc-400 mb-3">EPS Surprise History (%)</div>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart
              data={[...scatterData].reverse()}
              margin={{ top: 4, right: 8, bottom: 0, left: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
              <XAxis dataKey="date" tick={{ fill: "#71717a", fontSize: 9 }} axisLine={false} tickLine={false}
                tickFormatter={v => v.slice(0, 7)} />
              <YAxis tick={{ fill: "#71717a", fontSize: 10 }} axisLine={false} tickLine={false}
                tickFormatter={v => `${v}%`} width={40} />
              <Tooltip contentStyle={TT_STYLE} formatter={(v) => [`${Number(v).toFixed(1)}%`, "EPS Surprise"]} />
              <ReferenceLine y={0} stroke="#52525b" />
              <Bar dataKey="surprise" radius={[3, 3, 0, 0]}>
                {[...scatterData].reverse().map((d, i) => (
                  <Cell key={i} fill={d.beat ? "#10b981" : "#ef4444"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Detailed table */}
      <div className="overflow-x-auto scrollbar-thin">
        <table className="w-full text-xs min-w-[500px]">
          <thead>
            <tr className="border-b border-zinc-700">
              {["Date", "EPS Estimate", "EPS Actual", "Surprise"].map(h => (
                <th key={h} className={`py-2 font-medium text-zinc-500 ${h === "Date" ? "text-left pr-4" : "text-right px-3"}`}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {withData.map((r, i) => (
              <tr key={i} className="border-b border-zinc-800/50 hover:bg-zinc-800/30 transition-colors">
                <td className="py-2 pr-4 text-zinc-300 font-mono">{r.date}</td>
                <td className="py-2 px-3 text-right font-mono tabular-nums text-zinc-400">
                  {r.eps_estimate != null ? `$${fmt(r.eps_estimate)}` : "—"}
                </td>
                <td className={`py-2 px-3 text-right font-mono tabular-nums ${
                  r.eps_actual != null && r.eps_estimate != null
                    ? r.eps_actual >= r.eps_estimate ? "text-emerald-400" : "text-red-400"
                    : "text-zinc-300"
                }`}>
                  {r.eps_actual != null ? `$${fmt(r.eps_actual)}` : "—"}
                </td>
                <td className="py-2 px-3 text-right">
                  <SurpriseBadge pct={r.surprise_pct} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
