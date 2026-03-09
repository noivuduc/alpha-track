"use client";
import { useMemo } from "react";
import {
  ComposedChart, Line, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, Legend,
} from "recharts";
import { PeHistoryRecord } from "@/lib/api";

const TT_STYLE = {
  backgroundColor: "#18181b", border: "1px solid #3f3f46",
  borderRadius: 8, color: "#e4e4e7", fontSize: 12,
};

function fmt(n: number | undefined | null, d = 1): string {
  if (n == null) return "—";
  return n.toFixed(d);
}

export default function HistoricalValuation({
  peHistory,
  currentPe,
}: {
  peHistory: PeHistoryRecord[];
  currentPe?: number | null;
}) {
  const validPe = useMemo(
    () => peHistory.filter(r => r.pe != null && r.pe > 0 && r.pe < 200),
    [peHistory]
  );

  const stats = useMemo(() => {
    if (!validPe.length) return null;
    const pes = validPe.map(r => r.pe as number);
    const avg = pes.reduce((a, b) => a + b, 0) / pes.length;
    const min = Math.min(...pes);
    const max = Math.max(...pes);
    const std = Math.sqrt(pes.reduce((a, b) => a + (b - avg) ** 2, 0) / pes.length);
    return { avg, min, max, std };
  }, [validPe]);

  const priceData = useMemo(
    () => peHistory.filter(r => r.price != null),
    [peHistory]
  );

  if (!peHistory.length) {
    return <div className="text-xs text-zinc-500 py-4">Insufficient data for historical valuation analysis.</div>;
  }

  const peVsAvg = stats && currentPe
    ? ((currentPe - stats.avg) / stats.avg) * 100
    : null;

  return (
    <div className="space-y-5">
      {/* Summary insight */}
      {stats && currentPe && (
        <div className={`rounded-xl p-4 border ${
          peVsAvg! > 20 ? "bg-red-950/30 border-red-800/40" :
          peVsAvg! < -20 ? "bg-emerald-950/30 border-emerald-800/40" :
          "bg-zinc-800/40 border-zinc-700/40"
        }`}>
          <div className="text-xs font-semibold text-zinc-300 mb-1">Valuation vs History</div>
          <div className="text-sm text-zinc-300">
            Current P/E of{" "}
            <span className="font-mono font-semibold text-zinc-100">{fmt(currentPe)}x</span>
            {" "}is{" "}
            <span className={`font-semibold ${peVsAvg! > 0 ? "text-red-400" : "text-emerald-400"}`}>
              {Math.abs(peVsAvg!).toFixed(0)}% {peVsAvg! > 0 ? "above" : "below"}
            </span>
            {" "}the {validPe.length}-year average of{" "}
            <span className="font-mono font-semibold text-zinc-100">{fmt(stats.avg)}x</span>.
            Historical range: <span className="font-mono text-zinc-300">{fmt(stats.min)}x – {fmt(stats.max)}x</span>.
          </div>
        </div>
      )}

      {/* P/E over time */}
      {validPe.length > 1 && (
        <div className="bg-zinc-800/40 rounded-xl p-4">
          <div className="text-xs font-semibold text-zinc-300 mb-3">Historical P/E Ratio</div>
          <ResponsiveContainer width="100%" height={240}>
            <ComposedChart data={validPe} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
              <XAxis dataKey="year" tick={{ fill: "#a1a1aa", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis
                tick={{ fill: "#a1a1aa", fontSize: 11 }} axisLine={false} tickLine={false}
                tickFormatter={v => `${v}x`} width={42}
                domain={["auto", "auto"]}
              />
              <Tooltip contentStyle={TT_STYLE} formatter={(v) => [`${Number(v).toFixed(1)}x`, "P/E"]} />
              {stats && (
                <>
                  <ReferenceLine y={stats.avg} stroke="#3b82f6" strokeDasharray="4 4" label={{ value: `Avg ${fmt(stats.avg)}x`, fill: "#60a5fa", fontSize: 10, position: "insideTopRight" }} />
                  <ReferenceLine y={stats.avg + stats.std} stroke="#52525b" strokeDasharray="2 4" />
                  <ReferenceLine y={Math.max(0, stats.avg - stats.std)} stroke="#52525b" strokeDasharray="2 4" />
                </>
              )}
              {currentPe && (
                <ReferenceLine y={currentPe} stroke="#f59e0b" strokeDasharray="4 4"
                  label={{ value: `Now ${fmt(currentPe)}x`, fill: "#f59e0b", fontSize: 10, position: "insideBottomRight" }} />
              )}
              <Bar dataKey="pe" fill="#3b82f620" stroke="#3b82f6" strokeWidth={1} radius={[3, 3, 0, 0]} />
              <Line type="monotone" dataKey="pe" stroke="#3b82f6" strokeWidth={2} dot={{ r: 3, fill: "#3b82f6" }} connectNulls />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Price history */}
      {priceData.length > 1 && (
        <div className="bg-zinc-800/40 rounded-xl p-4">
          <div className="text-xs font-semibold text-zinc-300 mb-3">Year-End Price History</div>
          <ResponsiveContainer width="100%" height={200}>
            <ComposedChart data={priceData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
              <XAxis dataKey="year" tick={{ fill: "#a1a1aa", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis
                tick={{ fill: "#a1a1aa", fontSize: 11 }} axisLine={false} tickLine={false}
                tickFormatter={v => `$${v}`} width={52}
              />
              <Tooltip contentStyle={TT_STYLE} formatter={(v) => [`$${Number(v).toFixed(2)}`, "Year-End Price"]} />
              <Line type="monotone" dataKey="price" stroke="#8b5cf6" strokeWidth={2.5} dot={{ r: 3, fill: "#8b5cf6" }} connectNulls />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* EPS history */}
      {validPe.length > 1 && (
        <div className="bg-zinc-800/40 rounded-xl p-4">
          <div className="text-xs font-semibold text-zinc-300 mb-3">Annual EPS History</div>
          <ResponsiveContainer width="100%" height={180}>
            <ComposedChart data={validPe} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
              <XAxis dataKey="year" tick={{ fill: "#a1a1aa", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis
                tick={{ fill: "#a1a1aa", fontSize: 11 }} axisLine={false} tickLine={false}
                tickFormatter={v => `$${v}`} width={46}
              />
              <Tooltip contentStyle={TT_STYLE} formatter={(v) => [`$${Number(v).toFixed(2)}`, "EPS"]} />
              <ReferenceLine y={0} stroke="#52525b" />
              <Bar dataKey="eps" radius={[3, 3, 0, 0]}>
                {validPe.map((r, i) => (
                  <rect key={i} fill={(r.eps ?? 0) >= 0 ? "#10b981" : "#ef4444"} />
                ))}
              </Bar>
              <Bar dataKey="eps" fill="#10b981" radius={[3, 3, 0, 0]} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
