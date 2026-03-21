"use client";
import { useState, useMemo } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import { PeerMetrics } from "@/lib/api";
import { ArrowUpDown, ArrowUp, ArrowDown } from "lucide-react";
import TickerLogo from "@/components/ui/TickerLogo";

function fmtLarge(n: number | undefined | null): string {
  if (n == null) return "—";
  if (Math.abs(n) >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (Math.abs(n) >= 1e9)  return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6)  return `$${(n / 1e6).toFixed(1)}M`;
  return `$${n.toLocaleString()}`;
}
function fmtPct(n: number | undefined | null): string {
  if (n == null) return "—";
  return `${n >= 0 ? "+" : ""}${n.toFixed(1)}%`;
}
function fmtNum(n: number | undefined | null, d = 1): string {
  if (n == null) return "—";
  return n.toFixed(d);
}

const TT_STYLE = {
  backgroundColor: "#18181b", border: "1px solid #3f3f46",
  borderRadius: 8, color: "#e4e4e7", fontSize: 11,
};

type SortDir = "asc" | "desc";

interface ColDef {
  key: keyof PeerMetrics;
  label: string;
  fmt: (v: number | undefined | null) => string;
  colorThreshold?: { good: number; bad: number; higherIsBetter: boolean };
}

const COLS: ColDef[] = [
  { key: "market_cap",       label: "Mkt Cap",      fmt: fmtLarge },
  { key: "revenue_growth",   label: "Rev Growth",   fmt: v => fmtPct(v != null ? v * 100 : null),  colorThreshold: { good: 10, bad: 0,  higherIsBetter: true  } },
  { key: "gross_margin",     label: "Gross Margin", fmt: v => fmtPct(v != null ? v * 100 : null),  colorThreshold: { good: 50, bad: 20, higherIsBetter: true  } },
  { key: "operating_margin", label: "Op Margin",    fmt: v => fmtPct(v != null ? v * 100 : null),  colorThreshold: { good: 15, bad: 0,  higherIsBetter: true  } },
  { key: "net_margin",       label: "Net Margin",   fmt: v => fmtPct(v != null ? v * 100 : null),  colorThreshold: { good: 10, bad: 0,  higherIsBetter: true  } },
  { key: "roic",             label: "ROIC",         fmt: v => fmtPct(v != null ? v * 100 : null),  colorThreshold: { good: 15, bad: 5,  higherIsBetter: true  } },
  { key: "pe",               label: "P/E",          fmt: v => fmtNum(v),                           colorThreshold: { good: 15, bad: 40, higherIsBetter: false } },
  { key: "ev_ebitda",        label: "EV/EBITDA",    fmt: v => fmtNum(v),                           colorThreshold: { good: 10, bad: 25, higherIsBetter: false } },
  { key: "ps",               label: "P/S",          fmt: v => fmtNum(v),                           colorThreshold: { good: 5,  bad: 15, higherIsBetter: false } },
  { key: "fcf_yield",        label: "FCF Yield",    fmt: v => fmtPct(v != null ? v * 100 : null),  colorThreshold: { good: 3,  bad: 0,  higherIsBetter: true  } },
];

const CHART_METRICS: { key: keyof PeerMetrics; label: string; scale: number; suffix: string }[] = [
  { key: "gross_margin",     label: "Gross Margin %",   scale: 100, suffix: "%" },
  { key: "operating_margin", label: "Operating Margin %", scale: 100, suffix: "%" },
  { key: "roic",             label: "ROIC %",           scale: 100, suffix: "%" },
  { key: "pe",               label: "P/E Ratio",        scale: 1,   suffix: "x" },
];

function cellColor(col: ColDef, v: number | undefined | null): string {
  if (v == null || !col.colorThreshold) return "text-zinc-300";
  const { good, bad, higherIsBetter } = col.colorThreshold;
  // Scale % metrics
  const scaled = (col.fmt === fmtLarge) ? v : v * (col.fmt(v).includes("%") || col.key.includes("margin") || col.key === "roic" || col.key === "fcf_yield" || col.key === "revenue_growth" ? 100 : 1);
  const raw = v * (col.key.includes("margin") || col.key === "roic" || col.key === "fcf_yield" || col.key === "revenue_growth" ? 100 : 1);
  if (higherIsBetter) return raw >= good ? "text-emerald-400" : raw <= bad ? "text-red-400" : "text-zinc-300";
  return raw <= good ? "text-emerald-400" : raw >= bad ? "text-red-400" : "text-zinc-300";
}

export default function PeerComparison({
  ticker,
  selfMetrics,
  peers,
}: {
  ticker: string;
  selfMetrics: PeerMetrics;
  peers: PeerMetrics[];
}) {
  const [sortKey,  setSortKey]  = useState<keyof PeerMetrics>("market_cap");
  const [sortDir,  setSortDir]  = useState<SortDir>("desc");
  const [chartKey, setChartKey] = useState<keyof PeerMetrics>("gross_margin");

  // Combine self + peers
  const all = useMemo(() => [selfMetrics, ...peers], [selfMetrics, peers]);

  const sorted = useMemo(() => {
    return [...all].sort((a, b) => {
      const av = a[sortKey] as number | undefined;
      const bv = b[sortKey] as number | undefined;
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      return sortDir === "desc" ? bv - av : av - bv;
    });
  }, [all, sortKey, sortDir]);

  function toggleSort(key: keyof PeerMetrics) {
    if (key === sortKey) setSortDir(d => d === "desc" ? "asc" : "desc");
    else { setSortKey(key); setSortDir("desc"); }
  }

  function SortIcon({ k }: { k: keyof PeerMetrics }) {
    if (k !== sortKey) return <ArrowUpDown size={11} className="text-zinc-600" />;
    return sortDir === "desc"
      ? <ArrowDown size={11} className="text-blue-400" />
      : <ArrowUp   size={11} className="text-blue-400" />;
  }

  // Chart data
  const cm = CHART_METRICS.find(m => m.key === chartKey) ?? CHART_METRICS[0];
  const chartData = all
    .filter(p => p[chartKey] != null)
    .map(p => ({
      symbol: p.symbol,
      value:  parseFloat(((p[chartKey] as number) * cm.scale).toFixed(2)),
      isSelf: p.symbol === ticker,
    }))
    .sort((a, b) => b.value - a.value);

  if (!peers.length) {
    return <div className="text-xs text-zinc-500 py-4">No peer data available for this ticker.</div>;
  }

  return (
    <div className="space-y-5">
      {/* Bar chart comparing one metric across peers */}
      <div>
        <div className="flex items-center gap-3 mb-3">
          <span className="text-xs font-semibold text-zinc-400">Compare</span>
          <div className="flex gap-0.5 bg-zinc-800 rounded-lg p-0.5 flex-wrap">
            {CHART_METRICS.map(m => (
              <button key={String(m.key)} onClick={() => setChartKey(m.key)}
                className={`px-2.5 py-1 text-[11px] rounded-md font-medium transition-colors ${
                  chartKey === m.key ? "bg-blue-600 text-white" : "text-zinc-400 hover:text-zinc-200"
                }`}>
                {m.label}
              </button>
            ))}
          </div>
        </div>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={chartData} layout="vertical" margin={{ top: 0, right: 40, bottom: 0, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#27272a" horizontal={false} />
            <XAxis type="number" tick={{ fill: "#a1a1aa", fontSize: 11 }} axisLine={false} tickLine={false}
              tickFormatter={v => `${v}${cm.suffix}`} />
            <YAxis type="category" dataKey="symbol" tick={{ fill: "#d4d4d8", fontSize: 11 }} axisLine={false} tickLine={false} width={50} />
            <Tooltip contentStyle={TT_STYLE} formatter={v => [`${v}${cm.suffix}`, cm.label]} />
            <Bar dataKey="value" radius={[0, 4, 4, 0]}>
              {chartData.map((d, i) => (
                <Cell key={i} fill={d.isSelf ? "#3b82f6" : "#52525b"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Comparison table */}
      <div className="overflow-x-auto scrollbar-thin">
        <table className="w-full text-xs min-w-[900px]">
          <thead>
            <tr className="border-b border-zinc-700">
              <th className="text-left py-2 pr-4 font-medium text-zinc-500 w-32 sticky left-0 bg-zinc-900">Company</th>
              {COLS.map(col => (
                <th key={String(col.key)}
                  className="text-right py-2 px-2 font-medium text-zinc-500 whitespace-nowrap cursor-pointer hover:text-zinc-300 select-none"
                  onClick={() => toggleSort(col.key)}>
                  <span className="flex items-center justify-end gap-1">
                    {col.label} <SortIcon k={col.key} />
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((row) => {
              const isSelf = row.symbol === ticker;
              return (
                <tr key={row.symbol}
                  className={`border-b border-zinc-800/50 transition-colors ${
                    isSelf ? "bg-blue-600/10 hover:bg-blue-600/15" : "hover:bg-zinc-800/30"
                  }`}>
                  <td className={`py-2 pr-4 sticky left-0 ${isSelf ? "bg-blue-600/10" : "bg-zinc-900"}`}>
                    <div className="flex items-center gap-2">
                      <TickerLogo ticker={row.symbol} size={24} rounded="md" />
                      <div>
                        <div className={`font-mono font-semibold ${isSelf ? "text-blue-400" : "text-zinc-200"}`}>
                          {row.symbol} {isSelf && <span className="text-[10px] text-blue-500 ml-1">YOU</span>}
                        </div>
                        <div className="text-zinc-600 truncate max-w-[90px]">{row.name}</div>
                      </div>
                    </div>
                  </td>
                  {COLS.map(col => {
                    const v = row[col.key] as number | undefined | null;
                    return (
                      <td key={String(col.key)} className={`py-2 px-2 text-right font-mono tabular-nums ${cellColor(col, v)}`}>
                        {col.fmt(v)}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="text-[10px] text-zinc-600">
        Blue = {ticker} · Green = favorable · Red = unfavorable · Peers from Yahoo Finance recommendations
      </div>
    </div>
  );
}
