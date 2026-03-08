"use client";
import { useState, useEffect, useCallback, useRef } from "react";
import {
  ComposedChart, Area, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from "recharts";
import { market, HistoryBar } from "@/lib/api";

// ─── Range config ─────────────────────────────────────────────────────────────
type RangeKey = "1D" | "5D" | "1W" | "1M" | "3M" | "1Y" | "3Y" | "5Y" | "10Y";
const RANGES: Record<RangeKey, { period: string; interval: string; filterYears?: number }> = {
  "1D":  { period: "1d",   interval: "5m"  },
  "5D":  { period: "5d",   interval: "30m" },
  "1W":  { period: "1mo",  interval: "1h",  filterYears: 7 / 365 },
  "1M":  { period: "1mo",  interval: "1d"  },
  "3M":  { period: "3mo",  interval: "1d"  },
  "1Y":  { period: "1y",   interval: "1d"  },
  "3Y":  { period: "5y",   interval: "1wk", filterYears: 3 },
  "5Y":  { period: "5y",   interval: "1wk" },
  "10Y": { period: "10y",  interval: "1mo" },
};

// ─── Tooltip ──────────────────────────────────────────────────────────────────
function CustomTooltip({ active, payload, label, isIntraday }: {
  active?: boolean; payload?: { payload: HistoryBar & { pct: number } }[]; label?: string; isIntraday: boolean;
}) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  const fmtDate = (ts: string) => {
    const date = new Date(ts);
    return isIntraday
      ? date.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
      : date.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
  };
  const pctColor = (d.pct ?? 0) >= 0 ? "#34d399" : "#f87171";
  return (
    <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-3 text-xs shadow-xl min-w-[160px]">
      <div className="text-zinc-400 mb-2">{fmtDate(d.ts)}</div>
      <div className="space-y-1">
        <Row label="Open"   value={`$${d.open?.toFixed(2)}`} />
        <Row label="High"   value={`$${d.high?.toFixed(2)}`} />
        <Row label="Low"    value={`$${d.low?.toFixed(2)}`} />
        <Row label="Close"  value={`$${d.close?.toFixed(2)}`} />
        <Row label="Chg"    value={`${(d.pct ?? 0) >= 0 ? "+" : ""}${(d.pct ?? 0).toFixed(2)}%`} color={pctColor} />
        <Row label="Volume" value={fmtVol(d.volume)} />
      </div>
    </div>
  );
}

function Row({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-zinc-500">{label}</span>
      <span style={color ? { color } : undefined} className={color ? "" : "text-zinc-200 font-mono"}>{value}</span>
    </div>
  );
}

function fmtVol(v: number): string {
  if (!v) return "—";
  if (v >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
  return String(v);
}

function fmtXAxis(ts: string, range: RangeKey): string {
  const d = new Date(ts);
  if (range === "1D" || range === "5D" || range === "1W") {
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  if (range === "1M" || range === "3M") {
    return d.toLocaleDateString([], { month: "short", day: "numeric" });
  }
  if (range === "1Y" || range === "3Y") {
    return d.toLocaleDateString([], { month: "short", year: "2-digit" });
  }
  return d.toLocaleDateString([], { year: "numeric", month: "short" });
}

// ─── Main component ───────────────────────────────────────────────────────────
export default function StockPriceChart({ ticker }: { ticker: string }) {
  const [range,   setRange]   = useState<RangeKey>("1Y");
  const [bars,    setBars]    = useState<(HistoryBar & { pct: number; volColor: string })[]>([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState("");
  const abortRef = useRef<AbortController | null>(null);

  const fetchData = useCallback(async (r: RangeKey) => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setLoading(true);
    setError("");
    try {
      const cfg = RANGES[r];
      const res = await market.history(ticker, cfg.period, cfg.interval);
      let data = res.data ?? [];

      // Client-side date filter for 1W and 3Y
      if (cfg.filterYears) {
        const cutoff = Date.now() - cfg.filterYears * 365 * 24 * 3600 * 1000;
        data = data.filter(b => new Date(b.ts).getTime() >= cutoff);
      }

      // Enrich with % change and volume color
      const enriched = data.map((b, i) => {
        const prev  = i > 0 ? data[i - 1].close : b.open;
        const pct   = prev ? ((b.close - prev) / prev) * 100 : 0;
        return { ...b, pct, volColor: pct >= 0 ? "#10b981" : "#ef4444" };
      });

      if (!ctrl.signal.aborted) setBars(enriched);
    } catch (e: unknown) {
      if (!ctrl.signal.aborted) {
        setError(e instanceof Error ? e.message : "Failed to load price data");
      }
    } finally {
      if (!ctrl.signal.aborted) setLoading(false);
    }
  }, [ticker]);

  useEffect(() => { fetchData(range); }, [range, fetchData]);

  const isIntraday = range === "1D" || range === "5D" || range === "1W";
  const firstClose = bars[0]?.close ?? 0;
  const lastClose  = bars[bars.length - 1]?.close ?? 0;
  const totalPct   = firstClose ? ((lastClose - firstClose) / firstClose) * 100 : 0;
  const positive   = totalPct >= 0;
  const lineColor  = positive ? "#34d399" : "#f87171";
  const fillStart  = positive ? "#34d39920" : "#f8717120";
  const gradId     = `stock-grad-${ticker}`;

  const priceMin = bars.length ? Math.min(...bars.map(b => b.low))  * 0.998 : 0;
  const priceMax = bars.length ? Math.max(...bars.map(b => b.high)) * 1.002 : 1;

  const TT_STYLE = {
    backgroundColor: "transparent", border: "none", boxShadow: "none", padding: 0,
  };

  // Throttle x-axis ticks
  const tickCount = Math.min(bars.length, 8);
  const tickStep  = Math.max(1, Math.floor(bars.length / tickCount));
  const tickIdxs  = new Set(bars.map((_, i) => i).filter(i => i % tickStep === 0));

  return (
    <div className="space-y-2">
      {/* Range selector + summary */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex gap-0.5 bg-zinc-800 rounded-lg p-0.5">
          {(Object.keys(RANGES) as RangeKey[]).map(r => (
            <button
              key={r}
              onClick={() => setRange(r)}
              className={`px-2.5 py-1 text-xs rounded-md font-medium transition-colors ${
                range === r ? "bg-blue-600 text-white" : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              {r}
            </button>
          ))}
        </div>
        {bars.length > 0 && (
          <div className={`text-sm font-mono font-semibold ${positive ? "text-emerald-400" : "text-red-400"}`}>
            {positive ? "+" : ""}{totalPct.toFixed(2)}% over {range}
          </div>
        )}
      </div>

      {loading ? (
        <div className="h-72 flex items-center justify-center">
          <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : error ? (
        <div className="h-40 flex items-center justify-center text-red-400 text-sm">{error}</div>
      ) : (
        <>
          {/* Price chart */}
          <ResponsiveContainer width="100%" height={280}>
            <ComposedChart data={bars} margin={{ top: 4, right: 8, bottom: 0, left: 0 }} syncId="stock">
              <defs>
                <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor={lineColor} stopOpacity={0.3} />
                  <stop offset="95%" stopColor={lineColor} stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
              <XAxis
                dataKey="ts"
                tick={{ fill: "#71717a", fontSize: 10 }}
                axisLine={false} tickLine={false}
                tickFormatter={(v, i) => tickIdxs.has(i) ? fmtXAxis(v, range) : ""}
                interval={0}
              />
              <YAxis
                domain={[priceMin, priceMax]}
                tick={{ fill: "#71717a", fontSize: 10 }}
                axisLine={false} tickLine={false}
                tickFormatter={v => `$${v.toFixed(0)}`}
                width={52}
              />
              <Tooltip content={<CustomTooltip isIntraday={isIntraday} />} contentStyle={TT_STYLE} />
              <ReferenceLine y={firstClose} stroke="#52525b" strokeDasharray="4 4" />
              <Area
                type="monotone" dataKey="close"
                stroke={lineColor} strokeWidth={1.5}
                fill={`url(#${gradId})`}
                dot={false} activeDot={{ r: 3, fill: lineColor }}
              />
            </ComposedChart>
          </ResponsiveContainer>

          {/* Volume chart */}
          <ResponsiveContainer width="100%" height={70}>
            <ComposedChart data={bars} margin={{ top: 0, right: 8, bottom: 0, left: 0 }} syncId="stock">
              <XAxis dataKey="ts" hide />
              <YAxis tick={false} axisLine={false} tickLine={false} width={52} />
              <Tooltip content={() => null} />
              <Bar dataKey="volume" radius={[2, 2, 0, 0]} isAnimationActive={false}
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                shape={(props: any) => {
                  const { x, y, width, height, index } = props;
                  const color = bars[index]?.volColor ?? "#10b981";
                  return <rect x={x} y={y} width={Math.max(width, 1)} height={Math.max(height, 0)} fill={color} fillOpacity={0.55} rx={2} />;
                }}
              />
            </ComposedChart>
          </ResponsiveContainer>
          <div className="text-center text-xs text-zinc-700">Volume</div>
        </>
      )}
    </div>
  );
}
