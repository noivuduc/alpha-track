"use client";
import { useMemo } from "react";
import { useRouter } from "next/navigation";
import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid,
  Tooltip, ReferenceLine, ReferenceArea, ResponsiveContainer,
} from "recharts";
import type { IncomeStatement, PeerMetrics } from "@/lib/api";

// ── Types ─────────────────────────────────────────────────────────────────────
interface ScatterPoint {
  ticker:           string;
  company:          string;
  revenue_growth:   number;   // %
  operating_margin: number;   // %
  market_cap:       number;
  isSelf:           boolean;
  r:                number;   // bubble radius px
  x:                number;   // recharts X dataKey alias
  y:                number;   // recharts Y dataKey alias
}

export interface GrowthScatterProps {
  ticker:       string;
  incomeAnnual: IncomeStatement[];
  selfMetrics:  PeerMetrics;
  peers:        PeerMetrics[];
}

// ── Computation helpers ────────────────────────────────────────────────────────
/** 3-year revenue CAGR from annual income statements → returns percentage or null */
function compute3YCAGR(income: IncomeStatement[]): number | null {
  const sorted = [...income]
    .filter(r => (r.revenue ?? 0) > 0)
    .sort((a, b) => b.report_period.localeCompare(a.report_period));
  if (sorted.length < 4) return null;
  const recent = sorted[0].revenue!;
  const base   = sorted[3].revenue!;
  if (base <= 0) return null;
  return (Math.pow(recent / base, 1 / 3) - 1) * 100;
}

/** Operating margin from the most-recent annual report → returns percentage or null */
function computeOpMargin(income: IncomeStatement[]): number | null {
  const sorted = [...income]
    .filter(r => (r.revenue ?? 0) > 0)
    .sort((a, b) => b.report_period.localeCompare(a.report_period));
  if (!sorted.length) return null;
  const { operating_income, revenue } = sorted[0];
  if (operating_income == null || !revenue) return null;
  return (operating_income / revenue) * 100;
}

/** Map market cap to bubble radius (5–22 px), relative to the peer group max */
function capToRadius(cap: number, maxCap: number): number {
  if (!cap || !maxCap) return 7;
  return Math.max(5, Math.min(22, Math.sqrt(cap / maxCap) * 20));
}

// ── Formatters ────────────────────────────────────────────────────────────────
function fmtCap(n: number): string {
  if (n >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (n >= 1e9)  return `$${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6)  return `$${(n / 1e6).toFixed(0)}M`;
  return `$${n.toLocaleString()}`;
}

// ── Custom tooltip ─────────────────────────────────────────────────────────────
const TT_STYLE: React.CSSProperties = {
  background: "#18181b",
  border: "1px solid #3f3f46",
  borderRadius: 8,
  padding: "10px 14px",
  fontSize: 12,
  lineHeight: 1.6,
};

function CustomTooltip({ active, payload }: { active?: boolean; payload?: any[] }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload as ScatterPoint;

  const growthColor = d.revenue_growth >= 10 ? "text-emerald-400" : d.revenue_growth < 0 ? "text-red-400" : "text-zinc-300";
  const marginColor = d.operating_margin >= 20 ? "text-emerald-400" : d.operating_margin < 0 ? "text-red-400" : "text-zinc-300";

  return (
    <div style={TT_STYLE}>
      <div className="font-semibold text-zinc-100 text-sm mb-2">
        {d.company}{" "}
        <span className="text-zinc-500 font-normal text-xs">({d.ticker})</span>
      </div>
      <div className="space-y-1">
        <TooltipRow label="Revenue Growth (3Y CAGR)"
          value={`${d.revenue_growth >= 0 ? "+" : ""}${d.revenue_growth.toFixed(1)}%`}
          color={growthColor} />
        <TooltipRow label="Operating Margin"
          value={`${d.operating_margin >= 0 ? "+" : ""}${d.operating_margin.toFixed(1)}%`}
          color={marginColor} />
        {d.market_cap > 0 && (
          <TooltipRow label="Market Cap" value={fmtCap(d.market_cap)} color="text-zinc-200" />
        )}
      </div>
      {!d.isSelf && (
        <div className="mt-2 text-[10px] text-zinc-600">Click to open research</div>
      )}
    </div>
  );
}

function TooltipRow({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="flex justify-between gap-8 text-xs">
      <span className="text-zinc-400">{label}</span>
      <span className={`font-mono font-medium ${color}`}>{value}</span>
    </div>
  );
}

// ── Custom bubble shape ────────────────────────────────────────────────────────
function BubbleShape(props: any) {
  const { cx, cy, payload } = props as { cx: number; cy: number; payload: ScatterPoint };
  const { r, isSelf, ticker } = payload;

  return (
    <g>
      <circle
        cx={cx}
        cy={cy}
        r={r}
        fill={isSelf ? "#3b82f6" : "#6366f1"}
        fillOpacity={isSelf ? 0.85 : 0.55}
        stroke={isSelf ? "#93c5fd" : "#818cf8"}
        strokeWidth={isSelf ? 2 : 1}
      />
      <text
        x={cx + r + 5}
        y={cy + 4}
        fontSize={isSelf ? 11 : 10}
        fill={isSelf ? "#93c5fd" : "#71717a"}
        fontFamily="ui-monospace, SFMono-Regular, monospace"
        fontWeight={isSelf ? 600 : 400}
      >
        {ticker}
      </text>
    </g>
  );
}

// ── Quadrant label helper ─────────────────────────────────────────────────────
const QL_PROPS = { fill: "#3f3f46", fontSize: 10 } as const;

// ── Main component ─────────────────────────────────────────────────────────────
export default function GrowthProfitabilityScatter({
  ticker, incomeAnnual, selfMetrics, peers,
}: GrowthScatterProps) {
  const router = useRouter();

  // Build scatter data
  const points = useMemo<ScatterPoint[]>(() => {
    const raw: Omit<ScatterPoint, "r" | "x" | "y">[] = [];

    // Selected company — compute directly from income statements for accuracy
    const selfGrowth = compute3YCAGR(incomeAnnual);
    const selfMargin = computeOpMargin(incomeAnnual);
    if (selfGrowth !== null && selfMargin !== null) {
      raw.push({
        ticker:           selfMetrics.symbol,
        company:          selfMetrics.name || selfMetrics.symbol,
        revenue_growth:   selfGrowth,
        operating_margin: selfMargin,
        market_cap:       selfMetrics.market_cap ?? 0,
        isSelf:           true,
      });
    }

    // Peers — yfinance returns revenue_growth and operating_margin as decimals (0→1)
    for (const p of peers.slice(0, 15)) {
      if (p.revenue_growth == null || p.operating_margin == null) continue;
      raw.push({
        ticker:           p.symbol,
        company:          p.name || p.symbol,
        revenue_growth:   p.revenue_growth * 100,
        operating_margin: p.operating_margin * 100,
        market_cap:       p.market_cap ?? 0,
        isSelf:           false,
      });
    }

    if (!raw.length) return [];

    const maxCap = Math.max(...raw.map(p => p.market_cap).filter(c => c > 0), 1);
    return raw.map(p => ({
      ...p,
      r: capToRadius(p.market_cap, maxCap),
      x: p.revenue_growth,
      y: p.operating_margin,
    }));
  }, [incomeAnnual, selfMetrics, peers]);

  // Axis domains with padding so bubbles aren't clipped
  const { xMin, xMax, yMin, yMax } = useMemo(() => {
    if (!points.length) return { xMin: -5, xMax: 30, yMin: -15, yMax: 55 };
    const xs = points.map(p => p.revenue_growth);
    const ys = points.map(p => p.operating_margin);
    return {
      xMin: Math.floor(Math.min(...xs, 0)  - 8),
      xMax: Math.ceil(Math.max(...xs, 15)  + 10),
      yMin: Math.floor(Math.min(...ys, -5) - 8),
      yMax: Math.ceil(Math.max(...ys, 25)  + 12),
    };
  }, [points]);

  const selfPoints  = useMemo(() => points.filter(p =>  p.isSelf), [points]);
  const peerPoints  = useMemo(() => points.filter(p => !p.isSelf), [points]);
  const hasPeers    = peerPoints.length > 0;

  if (!points.length) {
    return (
      <div className="flex items-center justify-center h-32 text-sm text-zinc-500">
        Need at least 4 years of revenue data to compute 3Y CAGR.
      </div>
    );
  }

  return (
    <div className="space-y-4">

      {/* Legend + subtitle */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-xs">
        <span className="flex items-center gap-1.5 text-zinc-300">
          <span className="inline-block w-3 h-3 rounded-full bg-blue-500" />
          {ticker}
        </span>
        {hasPeers && (
          <span className="flex items-center gap-1.5 text-zinc-400">
            <span className="inline-block w-3 h-3 rounded-full bg-indigo-400 opacity-70" />
            Peers
          </span>
        )}
        <span className="ml-auto text-zinc-600">Bubble size = market cap</span>
      </div>

      {/* Scatter chart */}
      <ResponsiveContainer width="100%" height={440}>
        <ScatterChart margin={{ top: 24, right: 56, bottom: 44, left: 20 }}>
          <CartesianGrid stroke="#27272a" strokeDasharray="3 3" />

          {/* Quadrant background tints */}
          <ReferenceArea x1={10} x2={xMax} y1={20} y2={yMax} fill="rgba(59,130,246,0.05)"  stroke="none" />
          <ReferenceArea x1={xMin} x2={10}  y1={20} y2={yMax} fill="rgba(16,185,129,0.03)" stroke="none" />
          <ReferenceArea x1={10} x2={xMax} y1={yMin} y2={20}  fill="rgba(245,158,11,0.03)" stroke="none" />
          {/* bottom-left intentionally unshaded — "weak fundamentals" */}

          {/* Threshold reference lines */}
          <ReferenceLine x={10} stroke="#52525b" strokeDasharray="5 3" strokeWidth={1.5} />
          <ReferenceLine y={20} stroke="#52525b" strokeDasharray="5 3" strokeWidth={1.5} />

          {/* Quadrant labels */}
          <ReferenceArea x1={10}   x2={xMax} y1={20}   y2={yMax} fill="none" stroke="none"
            label={{ ...QL_PROPS, value: "Quality Compounders",      position: "insideTopRight"    }} />
          <ReferenceArea x1={xMin} x2={10}   y1={20}   y2={yMax} fill="none" stroke="none"
            label={{ ...QL_PROPS, value: "Profitable · Slow Growth", position: "insideTopLeft"     }} />
          <ReferenceArea x1={10}   x2={xMax} y1={yMin} y2={20}   fill="none" stroke="none"
            label={{ ...QL_PROPS, value: "Fast Growth · Low Margin", position: "insideBottomRight" }} />
          <ReferenceArea x1={xMin} x2={10}   y1={yMin} y2={20}   fill="none" stroke="none"
            label={{ ...QL_PROPS, value: "Weak Fundamentals",        position: "insideBottomLeft"  }} />

          <XAxis
            type="number"
            dataKey="x"
            domain={[xMin, xMax]}
            tickFormatter={(v: number) => `${v}%`}
            tick={{ fill: "#71717a", fontSize: 11 }}
            stroke="#3f3f46"
            label={{
              value: "Revenue Growth (3Y CAGR)",
              position: "insideBottom",
              offset: -20,
              fill: "#71717a",
              fontSize: 11,
            }}
          />
          <YAxis
            type="number"
            dataKey="y"
            width={52}
            domain={[yMin, yMax]}
            tickFormatter={(v: number) => `${v}%`}
            tick={{ fill: "#71717a", fontSize: 11 }}
            stroke="#3f3f46"
            label={{
              value: "Operating Margin",
              angle: -90,
              position: "insideLeft",
              offset: 14,
              fill: "#71717a",
              fontSize: 11,
            }}
          />

          <Tooltip
            content={<CustomTooltip />}
            cursor={{ strokeDasharray: "3 3", stroke: "#52525b" }}
          />

          {/* Peer bubbles — rendered first so self appears on top */}
          {hasPeers && (
            <Scatter
              data={peerPoints}
              shape={<BubbleShape />}
              onClick={(d: any) => router.push(`/research/${d.ticker ?? d.payload?.ticker}`)}
              cursor="pointer"
            />
          )}

          {/* Self bubble — on top */}
          {selfPoints.length > 0 && (
            <Scatter
              data={selfPoints}
              shape={<BubbleShape />}
            />
          )}
        </ScatterChart>
      </ResponsiveContainer>

      {/* Footnote */}
      <p className="text-[11px] text-zinc-600 text-right">
        Revenue growth = 3-year CAGR from annual income statements · Operating margin = latest annual · {hasPeers ? "Peer data from Yahoo Finance" : "No peer data available"}
      </p>
    </div>
  );
}
