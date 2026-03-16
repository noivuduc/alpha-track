"use client";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid,
  Tooltip, ReferenceLine, ReferenceArea, ResponsiveContainer,
} from "recharts";
import type { IncomeStatement, PeerMetrics } from "@/lib/api";

// ── Types ──────────────────────────────────────────────────────────────────────
type ValuationMetric = "peg" | "pe" | "ev_ebitda" | "ev_sales";

interface ScatterPoint {
  ticker:           string;
  company:          string;
  revenue_growth:   number;    // %
  operating_margin: number;    // %
  market_cap:       number;
  isSelf:           boolean;
  r:                number;    // bubble radius px (log scale)
  x:                number;    // recharts X dataKey alias
  y:                number;    // recharts Y dataKey alias
  // Valuation
  pe?:       number;
  peg?:      number;
  ev_ebitda?: number;
  ev_sales?: number;
  // Computed at render time from selected metric
  color:     string;
}

export interface GrowthScatterProps {
  ticker:       string;
  incomeAnnual: IncomeStatement[];
  selfMetrics:  PeerMetrics;
  peers:        PeerMetrics[];
  selfPeg?:     number;      // profile.peg_ratio
  selfEvSales?: number;      // profile.ev_revenue
}

// ── Valuation color scale ──────────────────────────────────────────────────────
// Thresholds: [cheap→fair, fair→pricey, pricey→expensive]
const THRESHOLDS: Record<ValuationMetric, [number, number, number]> = {
  peg:      [1,  2,  3  ],
  pe:       [15, 25, 40 ],
  ev_ebitda:[10, 20, 30 ],
  ev_sales: [2,  5,  10 ],
};

const VAL_COLORS = {
  cheap:     "#10b981",   // emerald-500
  fair:      "#6b7280",   // zinc-500  — neutral
  pricey:    "#f97316",   // orange-500
  expensive: "#ef4444",   // red-500
  na:        "#3f3f46",   // zinc-700  — no data
} as const;

function valuationColor(metric: ValuationMetric, value: number | undefined): string {
  if (value == null || value <= 0) return VAL_COLORS.na;
  const [t1, t2, t3] = THRESHOLDS[metric];
  if (value <= t1) return VAL_COLORS.cheap;
  if (value <= t2) return VAL_COLORS.fair;
  if (value <= t3) return VAL_COLORS.pricey;
  return VAL_COLORS.expensive;
}

// ── Metric selector config ─────────────────────────────────────────────────────
const METRICS: { key: ValuationMetric; label: string; hint: string }[] = [
  { key: "peg",      label: "PEG",      hint: "< 1 cheap · 1–2 fair · 2–3 pricey · > 3 exp." },
  { key: "pe",       label: "P/E",      hint: "< 15 cheap · 15–25 fair · 25–40 pricey · > 40 exp." },
  { key: "ev_ebitda",label: "EV/EBITDA",hint: "< 10 cheap · 10–20 fair · 20–30 pricey · > 30 exp." },
  { key: "ev_sales", label: "EV/Sales", hint: "< 2 cheap · 2–5 fair · 5–10 pricey · > 10 exp." },
];

// ── Computation helpers ────────────────────────────────────────────────────────
/** 3-year revenue CAGR from annual income statements (%) */
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

/** Operating margin from most-recent annual report (%) */
function computeOpMargin(income: IncomeStatement[]): number | null {
  const sorted = [...income]
    .filter(r => (r.revenue ?? 0) > 0)
    .sort((a, b) => b.report_period.localeCompare(a.report_period));
  if (!sorted.length) return null;
  const { operating_income, revenue } = sorted[0];
  if (operating_income == null || !revenue) return null;
  return (operating_income / revenue) * 100;
}

/** Logarithmic bubble radius — compresses the market-cap range into 5–22 px */
function logRadius(cap: number, minCap: number, maxCap: number): number {
  if (!cap || cap <= 0 || maxCap <= minCap) return 9;
  const logVal = Math.log(Math.max(cap, 1e6));
  const logMin = Math.log(Math.max(minCap, 1e6));
  const logMax = Math.log(maxCap);
  if (logMax <= logMin) return 12;
  const t = Math.max(0, Math.min(1, (logVal - logMin) / (logMax - logMin)));
  return Math.round(5 + t * 17);
}

// ── Formatters ─────────────────────────────────────────────────────────────────
function fmtCap(n: number): string {
  if (n >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (n >= 1e9)  return `$${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6)  return `$${(n / 1e6).toFixed(0)}M`;
  return `$${n.toLocaleString()}`;
}
function fmtPct(n: number | undefined): string {
  if (n == null) return "—";
  return `${n >= 0 ? "+" : ""}${n.toFixed(1)}%`;
}
function fmtVal(n: number | undefined, dec = 1): string {
  if (n == null || n <= 0) return "—";
  return n.toFixed(dec) + "×";
}

// ── Tooltip ────────────────────────────────────────────────────────────────────
const TT: React.CSSProperties = {
  background:   "#18181b",
  border:       "1px solid #3f3f46",
  borderRadius: 8,
  padding:      "10px 14px",
  fontSize:     12,
  lineHeight:   1.65,
  minWidth:     200,
};

function Dot({ color }: { color: string }) {
  return <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: color, marginRight: 5, flexShrink: 0 }} />;
}

function CustomTooltip({ active, payload, valMetric }: {
  active?: boolean; payload?: any[]; valMetric: ValuationMetric;
}) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload as ScatterPoint;

  const growthClr = d.revenue_growth  >= 10 ? "#10b981" : d.revenue_growth  < 0 ? "#ef4444" : "#a1a1aa";
  const marginClr = d.operating_margin >= 20 ? "#10b981" : d.operating_margin < 0 ? "#ef4444" : "#a1a1aa";

  const activeMetricLabel = METRICS.find(m => m.key === valMetric)?.label ?? valMetric;
  const activeVal = d[valMetric];

  return (
    <div style={TT}>
      {/* Header */}
      <div style={{ fontWeight: 600, color: "#f4f4f5", fontSize: 13, marginBottom: 8 }}>
        <Dot color={d.color} />
        {d.company}
        <span style={{ color: "#71717a", fontWeight: 400, fontSize: 11, marginLeft: 6 }}>
          {d.ticker}
        </span>
      </div>

      {/* Growth & Profitability */}
      <div style={{ borderBottom: "1px solid #27272a", paddingBottom: 8, marginBottom: 8 }}>
        <TRow label="Revenue CAGR (3Y)"   value={fmtPct(d.revenue_growth)}   color={growthClr} />
        <TRow label="Operating Margin"    value={fmtPct(d.operating_margin)}  color={marginClr} />
        {d.market_cap > 0 && (
          <TRow label="Market Cap" value={fmtCap(d.market_cap)} color="#e4e4e7" />
        )}
      </div>

      {/* Valuation */}
      <div>
        <div style={{ color: "#52525b", fontSize: 10, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 4 }}>
          Valuation
        </div>
        <TRow label="P/E"       value={fmtVal(d.pe, 1)}        color={d.pe       ? valuationColor("pe",       d.pe)       : "#52525b"} />
        <TRow label="PEG"       value={fmtVal(d.peg, 2)}       color={d.peg      ? valuationColor("peg",      d.peg)      : "#52525b"} />
        <TRow label="EV/EBITDA" value={fmtVal(d.ev_ebitda, 1)} color={d.ev_ebitda ? valuationColor("ev_ebitda", d.ev_ebitda) : "#52525b"} />
        <TRow label="EV/Sales"  value={fmtVal(d.ev_sales, 1)}  color={d.ev_sales  ? valuationColor("ev_sales",  d.ev_sales)  : "#52525b"} />
        {activeVal != null && activeVal > 0 && (
          <div style={{ marginTop: 4, fontSize: 10, color: "#52525b" }}>
            Color = {activeMetricLabel} signal
          </div>
        )}
      </div>

      {!d.isSelf && (
        <div style={{ marginTop: 8, fontSize: 10, color: "#3f3f46", borderTop: "1px solid #27272a", paddingTop: 6 }}>
          Click to open research →
        </div>
      )}
    </div>
  );
}

function TRow({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 24, fontSize: 12 }}>
      <span style={{ color: "#71717a" }}>{label}</span>
      <span style={{ fontFamily: "ui-monospace, monospace", fontWeight: 500, color }}>{value}</span>
    </div>
  );
}

// ── Bubble shape ───────────────────────────────────────────────────────────────
function BubbleShape(props: any) {
  const { cx, cy, payload } = props as { cx: number; cy: number; payload: ScatterPoint };
  const { r, isSelf, ticker, color } = payload;

  return (
    <g style={{ cursor: isSelf ? "default" : "pointer" }}>
      {/* Outer ring for selected company */}
      {isSelf && (
        <circle
          cx={cx} cy={cy} r={r + 4}
          fill="none"
          stroke={color}
          strokeWidth={1.5}
          strokeOpacity={0.35}
        />
      )}
      <circle
        cx={cx} cy={cy} r={r}
        fill={color}
        fillOpacity={isSelf ? 0.9 : 0.45}
        stroke={color}
        strokeWidth={isSelf ? 2 : 1}
        strokeOpacity={isSelf ? 1 : 0.7}
      />
      <text
        x={cx + r + 5}
        y={cy + 4}
        fontSize={isSelf ? 11 : 10}
        fill={isSelf ? "#e4e4e7" : "#71717a"}
        fontFamily="ui-monospace, SFMono-Regular, monospace"
        fontWeight={isSelf ? 600 : 400}
        style={{ pointerEvents: "none", userSelect: "none" }}
      >
        {ticker}
      </text>
    </g>
  );
}

// ── Quadrant label styling ─────────────────────────────────────────────────────
const QL = { fill: "#3f3f46", fontSize: 10 } as const;

// ── Main component ─────────────────────────────────────────────────────────────
export default function GrowthProfitabilityScatter({
  ticker, incomeAnnual, selfMetrics, peers, selfPeg, selfEvSales,
}: GrowthScatterProps) {
  const router = useRouter();
  const [valMetric, setValMetric] = useState<ValuationMetric>("peg");

  // Build raw data points (valuation fields included, no color yet)
  const basePoints = useMemo(() => {
    type Raw = Omit<ScatterPoint, "r" | "x" | "y" | "color">;
    const raw: Raw[] = [];

    // ── Selected company ───────────────────────────────────────────────────────
    const selfGrowth = compute3YCAGR(incomeAnnual);
    const selfMargin = computeOpMargin(incomeAnnual);

    if (selfGrowth !== null && selfMargin !== null) {
      const pe        = selfMetrics.pe ?? undefined;
      const ev_ebitda = selfMetrics.ev_ebitda ?? undefined;
      const ev_sales  = selfEvSales ?? selfMetrics.ps ?? undefined;
      const peg       = selfPeg ?? (pe && selfGrowth > 0 ? pe / selfGrowth : undefined);

      raw.push({
        ticker:           selfMetrics.symbol,
        company:          selfMetrics.name || selfMetrics.symbol,
        revenue_growth:   selfGrowth,
        operating_margin: selfMargin,
        market_cap:       selfMetrics.market_cap ?? 0,
        isSelf:           true,
        pe, peg, ev_ebitda, ev_sales,
      });
    }

    // ── Peers (yfinance returns margins/growth as decimal ratios) ──────────────
    for (const p of peers.slice(0, 15)) {
      if (p.revenue_growth == null || p.operating_margin == null) continue;

      const growth_pct = p.revenue_growth * 100;
      const pe         = p.pe ?? undefined;
      const ev_ebitda  = p.ev_ebitda ?? undefined;
      const ev_sales   = p.ps ?? undefined;
      // Approximate PEG using revenue growth as proxy for EPS growth when pe available
      const peg        = (pe && growth_pct > 0) ? pe / growth_pct : undefined;

      raw.push({
        ticker:           p.symbol,
        company:          p.name || p.symbol,
        revenue_growth:   growth_pct,
        operating_margin: p.operating_margin * 100,
        market_cap:       p.market_cap ?? 0,
        isSelf:           false,
        pe, peg, ev_ebitda, ev_sales,
      });
    }

    if (!raw.length) return [];

    // Log-scale bubble radii
    const caps    = raw.map(p => p.market_cap).filter(c => c > 0);
    const minCap  = Math.min(...caps, 1e9);
    const maxCap  = Math.max(...caps, 1e9);

    return raw.map(p => ({
      ...p,
      r: logRadius(p.market_cap, minCap, maxCap),
      x: p.revenue_growth,
      y: p.operating_margin,
    }));
  }, [incomeAnnual, selfMetrics, peers, selfPeg, selfEvSales]);

  // Inject color from selected valuation metric
  const points = useMemo<ScatterPoint[]>(
    () => basePoints.map(p => ({ ...p, color: valuationColor(valMetric, p[valMetric]) })),
    [basePoints, valMetric],
  );

  // Axis domains
  const { xMin, xMax, yMin, yMax } = useMemo(() => {
    if (!points.length) return { xMin: -5, xMax: 30, yMin: -15, yMax: 55 };
    const xs = points.map(p => p.revenue_growth);
    const ys = points.map(p => p.operating_margin);
    return {
      xMin: Math.floor(Math.min(...xs, 0)  - 8),
      xMax: Math.ceil(Math.max(...xs, 15)  + 12),
      yMin: Math.floor(Math.min(...ys, -5) - 8),
      yMax: Math.ceil(Math.max(...ys, 25)  + 14),
    };
  }, [points]);

  const selfPoints = useMemo(() => points.filter(p =>  p.isSelf), [points]);
  const peerPoints = useMemo(() => points.filter(p => !p.isSelf), [points]);
  const hasPeers   = peerPoints.length > 0;

  const currentMetric = METRICS.find(m => m.key === valMetric)!;

  if (!points.length) {
    return (
      <div className="flex items-center justify-center h-32 text-sm text-zinc-500">
        Need at least 4 years of revenue data to compute 3-year CAGR.
      </div>
    );
  }

  return (
    <div className="space-y-3">

      {/* ── Controls row ─────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-4">

        {/* Metric selector */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-zinc-500 shrink-0">Color by</span>
          <div className="flex gap-0.5 bg-zinc-800 rounded-lg p-0.5">
            {METRICS.map(m => (
              <button
                key={m.key}
                onClick={() => setValMetric(m.key)}
                className={`px-2.5 py-1 text-xs rounded-md font-medium transition-colors ${
                  valMetric === m.key
                    ? "bg-zinc-600 text-zinc-100"
                    : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>
        </div>

        {/* Color scale legend */}
        <div className="flex items-center gap-3 text-[11px] text-zinc-500">
          {[
            { label: "Cheap",     color: VAL_COLORS.cheap     },
            { label: "Fair",      color: VAL_COLORS.fair      },
            { label: "Pricey",    color: VAL_COLORS.pricey    },
            { label: "Expensive", color: VAL_COLORS.expensive },
            { label: "N/A",       color: VAL_COLORS.na        },
          ].map(({ label, color }) => (
            <span key={label} className="flex items-center gap-1">
              <span style={{ background: color }} className="inline-block w-2 h-2 rounded-full" />
              {label}
            </span>
          ))}
        </div>
      </div>

      {/* Threshold hint */}
      <p className="text-[11px] text-zinc-600">{currentMetric.hint}</p>

      {/* ── Dot legend ───────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-5 text-xs text-zinc-400">
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-3 rounded-full border-2 border-zinc-300 bg-transparent" />
          {ticker}
        </span>
        {hasPeers && (
          <span className="flex items-center gap-1.5 text-zinc-500">
            <span className="inline-block w-2.5 h-2.5 rounded-full bg-zinc-600" />
            Peers
          </span>
        )}
        <span className="ml-auto text-zinc-600">Bubble size = market cap (log scale)</span>
      </div>

      {/* ── Scatter chart ─────────────────────────────────────────────────────── */}
      <ResponsiveContainer width="100%" height={440}>
        <ScatterChart margin={{ top: 24, right: 60, bottom: 44, left: 20 }}>
          <CartesianGrid stroke="#27272a" strokeDasharray="3 3" />

          {/* Quadrant background tints */}
          <ReferenceArea x1={10}   x2={xMax} y1={20}   y2={yMax} fill="rgba(59,130,246,0.04)"  stroke="none" />
          <ReferenceArea x1={xMin} x2={10}   y1={20}   y2={yMax} fill="rgba(16,185,129,0.025)" stroke="none" />
          <ReferenceArea x1={10}   x2={xMax} y1={yMin} y2={20}   fill="rgba(245,158,11,0.025)" stroke="none" />

          {/* Threshold reference lines */}
          <ReferenceLine x={10} stroke="#52525b" strokeDasharray="5 3" strokeWidth={1.5} />
          <ReferenceLine y={20} stroke="#52525b" strokeDasharray="5 3" strokeWidth={1.5} />

          {/* Quadrant labels */}
          <ReferenceArea x1={10}   x2={xMax} y1={20}   y2={yMax} fill="none" stroke="none"
            label={{ ...QL, value: "Quality Compounders",      position: "insideTopRight"    }} />
          <ReferenceArea x1={xMin} x2={10}   y1={20}   y2={yMax} fill="none" stroke="none"
            label={{ ...QL, value: "Profitable · Slow Growth", position: "insideTopLeft"     }} />
          <ReferenceArea x1={10}   x2={xMax} y1={yMin} y2={20}   fill="none" stroke="none"
            label={{ ...QL, value: "Early-Stage Growth",       position: "insideBottomRight" }} />
          <ReferenceArea x1={xMin} x2={10}   y1={yMin} y2={20}   fill="none" stroke="none"
            label={{ ...QL, value: "Weak Fundamentals",        position: "insideBottomLeft"  }} />

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
            content={<CustomTooltip valMetric={valMetric} />}
            cursor={{ strokeDasharray: "3 3", stroke: "#52525b" }}
          />

          {/* Peers rendered first → self floats on top */}
          {hasPeers && (
            <Scatter
              data={peerPoints}
              shape={<BubbleShape />}
              onClick={(d: any) => router.push(`/research/${d.ticker ?? d.payload?.ticker}`)}
              cursor="pointer"
            />
          )}

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
        Revenue CAGR = 3-year from annual filings · Operating margin = latest annual ·{" "}
        {hasPeers ? "Peer valuation from Yahoo Finance · Peer PEG uses revenue growth as EPS proxy" : "No peers available"}
      </p>
    </div>
  );
}
