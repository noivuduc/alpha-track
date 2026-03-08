"use client";
import { useMemo } from "react";
import {
  PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, LabelList,
} from "recharts";
import { SegmentedRevenuePeriod, SegmentedRevenueItem } from "@/lib/api";

const COLORS = [
  "#3b82f6", "#8b5cf6", "#10b981", "#f59e0b", "#ef4444",
  "#06b6d4", "#ec4899", "#84cc16", "#f97316", "#6366f1",
];

function fmtB(n: number): string {
  if (Math.abs(n) >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (Math.abs(n) >= 1e9)  return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6)  return `$${(n / 1e6).toFixed(1)}M`;
  return `$${n.toLocaleString()}`;
}

// Axis identifiers from financialdatasets
const PRODUCT_AXIS = "srt:ProductOrServiceAxis";
const GEO_AXIS     = "srt:StatementGeographicalAxis";

interface Segment { label: string; amount: number; pct: number; growth?: number | null }

function extractSegments(period: SegmentedRevenuePeriod, axis: string): Segment[] {
  const items = period.items.filter((item: SegmentedRevenueItem) =>
    item.segments.length === 1 && item.segments[0].axis === axis
  );
  if (!items.length) return [];
  const total = items.reduce((s, i) => s + i.amount, 0) || 1;
  return items.map(item => ({
    label:  item.segments[0].label,
    amount: item.amount,
    pct:    (item.amount / total) * 100,
  }));
}

function computeGrowth(periods: SegmentedRevenuePeriod[], axis: string): Segment[] {
  if (periods.length < 2) return extractSegments(periods[0], axis);
  const latest = extractSegments(periods[0], axis);
  const prior  = extractSegments(periods[1], axis);
  const priorMap = Object.fromEntries(prior.map(s => [s.label, s.amount]));
  return latest.map(s => ({
    ...s,
    growth: priorMap[s.label] != null
      ? ((s.amount - priorMap[s.label]) / Math.abs(priorMap[s.label])) * 100
      : null,
  }));
}

// Build historical stacked bar data (oldest → newest)
function buildHistorical(periods: SegmentedRevenuePeriod[], axis: string): Record<string, number | string>[] {
  return [...periods].reverse().map(p => {
    const segs = extractSegments(p, axis);
    const row: Record<string, number | string> = { year: p.report_period.slice(0, 4) };
    segs.forEach(s => { row[s.label] = s.amount; });
    return row;
  });
}

const TT_STYLE = { backgroundColor: "#18181b", border: "1px solid #3f3f46", borderRadius: 8, color: "#e4e4e7", fontSize: 12 };

function SegmentTable({ segs, title, colorMap }: { segs: Segment[]; title: string; colorMap: Record<string, string> }) {
  if (!segs.length) return null;
  return (
    <div>
      <div className="text-xs font-semibold text-zinc-400 mb-2">{title}</div>
      <div className="overflow-x-auto scrollbar-thin">
        <table className="w-full text-xs min-w-[440px]">
          <thead>
            <tr className="border-b border-zinc-700">
              {["Segment", "Revenue", "% of Total", "YoY Growth"].map(h => (
                <th key={h} className={`py-2 font-medium text-zinc-500 ${h === "Segment" ? "text-left pr-4" : "text-right px-3"}`}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {segs.map((s, i) => (
              <tr key={i} className="border-b border-zinc-800/50 hover:bg-zinc-800/30 transition-colors">
                <td className="py-2 pr-4 flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full shrink-0" style={{ background: colorMap[s.label] || COLORS[i % COLORS.length] }} />
                  <span className="text-zinc-200">{s.label}</span>
                </td>
                <td className="py-2 px-3 text-right font-mono tabular-nums text-zinc-300">{fmtB(s.amount)}</td>
                <td className="py-2 px-3 text-right font-mono tabular-nums text-zinc-400">{s.pct.toFixed(1)}%</td>
                <td className="py-2 px-3 text-right font-mono tabular-nums">
                  {s.growth != null ? (
                    <span className={s.growth >= 0 ? "text-emerald-400" : "text-red-400"}>
                      {s.growth >= 0 ? "+" : ""}{s.growth.toFixed(1)}%
                    </span>
                  ) : <span className="text-zinc-600">—</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function DonutChart({ segs, title, colorMap }: { segs: Segment[]; title: string; colorMap: Record<string, string> }) {
  if (!segs.length) return null;
  return (
    <div>
      <div className="text-xs font-semibold text-zinc-400 mb-2 text-center">{title}</div>
      <ResponsiveContainer width="100%" height={220}>
        <PieChart>
          <Pie data={segs} dataKey="amount" nameKey="label" cx="50%" cy="50%" innerRadius={55} outerRadius={90} paddingAngle={2}>
            {segs.map((s, i) => <Cell key={i} fill={colorMap[s.label] || COLORS[i % COLORS.length]} />)}
          </Pie>
          <Tooltip contentStyle={TT_STYLE} formatter={(v) => [fmtB(Number(v))]} />
          <Legend
            iconType="circle" iconSize={8}
            formatter={(v) => <span style={{ color: "#a1a1aa", fontSize: 11 }}>{v}</span>}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

function HistoricalBar({ data, keys, title, colorMap }: {
  data: Record<string, number | string>[]; keys: string[]; title: string;
  colorMap: Record<string, string>;
}) {
  if (!data.length || !keys.length) return null;
  return (
    <div>
      <div className="text-xs font-semibold text-zinc-400 mb-2">{title}</div>
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
          <XAxis dataKey="year" tick={{ fill: "#71717a", fontSize: 11 }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fill: "#71717a", fontSize: 11 }} axisLine={false} tickLine={false}
                 tickFormatter={v => fmtB(v)} width={64} />
          <Tooltip
            contentStyle={TT_STYLE}
            formatter={(v, name) => [fmtB(Number(v)), name]}
          />
          <Legend
            iconType="circle" iconSize={8}
            formatter={(v) => <span style={{ color: "#a1a1aa", fontSize: 11 }}>{v}</span>}
            wrapperStyle={{ paddingTop: 8 }}
          />
          {keys.map((k, i) => (
            <Bar
              key={k}
              dataKey={k}
              stackId="a"
              fill={colorMap[k] || COLORS[i % COLORS.length]}
              radius={i === keys.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]}
            >
              <LabelList
                dataKey={k}
                position="center"
                content={(props) => {
                  const { x, y, width, height, value } = props as {
                    x?: number; y?: number; width?: number; height?: number; value?: number;
                  };
                  if (!value || !width || !height || height < 18 || width < 30) return null;
                  return (
                    <text
                      x={(x ?? 0) + (width ?? 0) / 2}
                      y={(y ?? 0) + (height ?? 0) / 2}
                      textAnchor="middle"
                      dominantBaseline="middle"
                      fill="rgba(255,255,255,0.85)"
                      fontSize={9}
                    >
                      {k.length > 12 ? k.slice(0, 11) + "…" : k}
                    </text>
                  );
                }}
              />
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function RevenueSegmentation({ segments }: { segments: SegmentedRevenuePeriod[] }) {
  const productSegs = useMemo(() => computeGrowth(segments, PRODUCT_AXIS), [segments]);
  const geoSegs     = useMemo(() => computeGrowth(segments, GEO_AXIS),     [segments]);
  const productHist = useMemo(() => buildHistorical(segments, PRODUCT_AXIS), [segments]);
  const geoHist     = useMemo(() => buildHistorical(segments, GEO_AXIS),     [segments]);
  const productKeys = useMemo(() => productSegs.map(s => s.label), [productSegs]);
  const geoKeys     = useMemo(() => geoSegs.map(s => s.label),     [geoSegs]);

  // Build stable color map: same segment label → same color across product and geo
  const colorMap = useMemo(() => {
    const map: Record<string, string> = {};
    let idx = 0;
    [...productKeys, ...geoKeys].forEach(k => {
      if (!(k in map)) map[k] = COLORS[idx++ % COLORS.length];
    });
    return map;
  }, [productKeys, geoKeys]);

  if (!productSegs.length && !geoSegs.length) {
    return <div className="text-xs text-zinc-500 py-4">No segmentation data available for this ticker</div>;
  }

  const latestPeriod = segments[0]?.report_period?.slice(0, 4);

  return (
    <div className="space-y-8">
      {/* Product / Service */}
      {productSegs.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <div className="text-sm font-semibold text-zinc-300">Product &amp; Service Breakdown</div>
            {latestPeriod && <span className="text-xs text-zinc-600 bg-zinc-800 px-2 py-0.5 rounded">FY{latestPeriod}</span>}
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <DonutChart segs={productSegs} title="Revenue by Product" colorMap={colorMap} />
            <SegmentTable segs={productSegs} title="Detail" colorMap={colorMap} />
          </div>
          {productHist.length > 1 && (
            <HistoricalBar data={productHist} keys={productKeys} title="Historical Revenue by Product" colorMap={colorMap} />
          )}
        </div>
      )}

      {/* Geography */}
      {geoSegs.length > 0 && (
        <div className="space-y-4">
          <div className="text-sm font-semibold text-zinc-300">Geographic Breakdown</div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <DonutChart segs={geoSegs} title="Revenue by Geography" colorMap={colorMap} />
            <SegmentTable segs={geoSegs} title="Detail" colorMap={colorMap} />
          </div>
          {geoHist.length > 1 && (
            <HistoricalBar data={geoHist} keys={geoKeys} title="Historical Revenue by Geography" colorMap={colorMap} />
          )}
        </div>
      )}
    </div>
  );
}
