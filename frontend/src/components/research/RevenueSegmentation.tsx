"use client";
import { useMemo, useState, useCallback } from "react";
import {
  PieChart, Pie, Cell, Sector, Tooltip, Legend, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, LabelList,
} from "recharts";
import { SegmentedRevenuePeriod, SegmentedRevenueItem } from "@/lib/api";

// ── Palette ───────────────────────────────────────────────────────────────────
const COLORS = [
  "#3b82f6", "#8b5cf6", "#10b981", "#f59e0b", "#ef4444",
  "#06b6d4", "#ec4899", "#84cc16", "#f97316", "#6366f1",
];
const OTHER_COLOR     = "#52525b";   // zinc-600 — neutral bucket
const MAX_DONUT_SLICES = 8;

// ── Donut geometry (fixed px — prevents any ResponsiveContainer drift) ────────
const DONUT_SIZE    = 280;           // square canvas
const INNER_R       = 77;            // 55 % of half-size (140 px)
const OUTER_R       = 126;           // 90 % — leaves 14 px margin for hover
const ACTIVE_OUTER_R = 132;          // 94 % — expands on hover, still fits

// ── Helpers ───────────────────────────────────────────────────────────────────
function fmtB(n: number): string {
  if (Math.abs(n) >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (Math.abs(n) >= 1e9)  return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6)  return `$${(n / 1e6).toFixed(1)}M`;
  return `$${n.toLocaleString()}`;
}

const PRODUCT_AXIS = "srt:ProductOrServiceAxis";
const GEO_AXIS     = "srt:StatementGeographicalAxis";
const TT_STYLE     = {
  backgroundColor: "#18181b", border: "1px solid #3f3f46",
  borderRadius: 8, color: "#e4e4e7", fontSize: 12,
};

// ── Data types ────────────────────────────────────────────────────────────────
interface Segment { label: string; amount: number; pct: number; growth?: number | null }

// ── Segment grouping ──────────────────────────────────────────────────────────
/**
 * Sort descending, keep top (MAX-1), collapse tail into "Other".
 * Returns at most MAX_DONUT_SLICES entries — no tiny unreadable slices.
 */
function groupSegments(segs: Segment[]): Segment[] {
  const sorted = [...segs].sort((a, b) => b.amount - a.amount);
  if (sorted.length <= MAX_DONUT_SLICES) return sorted;

  const top  = sorted.slice(0, MAX_DONUT_SLICES - 1);
  const tail = sorted.slice(MAX_DONUT_SLICES - 1);

  const otherAmount = tail.reduce((s, t) => s + t.amount, 0);
  const total       = sorted.reduce((s, t) => s + t.amount, 0) || 1;

  return [
    ...top,
    { label: "Other", amount: otherAmount, pct: (otherAmount / total) * 100, growth: null },
  ];
}

// ── Data extraction / growth computation ─────────────────────────────────────
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
  const latest   = extractSegments(periods[0], axis);
  const prior    = extractSegments(periods[1], axis);
  const priorMap = Object.fromEntries(prior.map(s => [s.label, s.amount]));
  return latest.map(s => ({
    ...s,
    growth: priorMap[s.label] != null
      ? ((s.amount - priorMap[s.label]) / Math.abs(priorMap[s.label])) * 100
      : null,
  }));
}

function buildHistorical(
  periods: SegmentedRevenuePeriod[], axis: string,
): Record<string, number | string>[] {
  return [...periods].reverse().map(p => {
    const segs = extractSegments(p, axis);
    const row: Record<string, number | string> = { year: p.report_period.slice(0, 4) };
    segs.forEach(s => { row[s.label] = s.amount; });
    return row;
  });
}

// ── Donut active shape — expands the hovered slice outward ────────────────────
function ActiveShape(props: any) {
  const { cx, cy, innerRadius, startAngle, endAngle, fill } = props;
  return (
    <Sector
      cx={cx}
      cy={cy}
      innerRadius={innerRadius - 3}
      outerRadius={ACTIVE_OUTER_R}
      startAngle={startAngle}
      endAngle={endAngle}
      fill={fill}
    />
  );
}

// ── Tooltip ───────────────────────────────────────────────────────────────────
function DonutTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const s: Segment = payload[0].payload;
  return (
    <div style={{ ...TT_STYLE, padding: "10px 14px", minWidth: 210 }}>
      <p className="font-semibold text-zinc-200 mb-2 text-[13px] leading-snug">{s.label}</p>
      <div className="space-y-1 text-xs">
        <div className="flex justify-between gap-8">
          <span className="text-zinc-500">Revenue</span>
          <span className="font-mono text-zinc-300">{fmtB(s.amount)}</span>
        </div>
        <div className="flex justify-between gap-8">
          <span className="text-zinc-500">Share</span>
          <span className="font-mono text-zinc-300">{s.pct.toFixed(1)}%</span>
        </div>
        {s.growth != null && (
          <div className="flex justify-between gap-8">
            <span className="text-zinc-500">YoY Growth</span>
            <span className={`font-mono font-semibold ${s.growth >= 0 ? "text-emerald-400" : "text-red-400"}`}>
              {s.growth >= 0 ? "+" : ""}{s.growth.toFixed(1)}%
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Donut chart ───────────────────────────────────────────────────────────────
interface DonutProps {
  displaySegs:  Segment[];
  title:        string;
  colorMap:     Record<string, string>;
  hoveredLabel: string | null;
  onHover:      (label: string | null) => void;
}

function DonutChart({ displaySegs, title, colorMap, hoveredLabel, onHover }: DonutProps) {
  if (!displaySegs.length) return null;

  const activeIndex = hoveredLabel
    ? displaySegs.findIndex(s => s.label === hoveredLabel)
    : -1;

  const sliceColor = (label: string, idx: number) =>
    label === "Other" ? OTHER_COLOR : (colorMap[label] || COLORS[idx % COLORS.length]);

  return (
    <div>
      <div className="text-xs font-semibold text-zinc-400 mb-3 text-center">{title}</div>

      {/* Fixed square container — chart never shifts regardless of segment count */}
      <div
        className="flex items-center justify-center"
        style={{ width: DONUT_SIZE, height: DONUT_SIZE }}
      >
        <PieChart width={DONUT_SIZE} height={DONUT_SIZE}>
          <Pie
            data={displaySegs}
            dataKey="amount"
            nameKey="label"
            cx={DONUT_SIZE / 2}
            cy={DONUT_SIZE / 2}
            innerRadius={INNER_R}
            outerRadius={OUTER_R}
            paddingAngle={1.5}
            activeIndex={activeIndex >= 0 ? activeIndex : undefined}
            activeShape={ActiveShape}
            onMouseEnter={(_: any, index: number) => onHover(displaySegs[index]?.label ?? null)}
            onMouseLeave={() => onHover(null)}
            isAnimationActive={false}
          >
            {displaySegs.map((s, i) => (
              <Cell
                key={i}
                fill={sliceColor(s.label, i)}
                opacity={hoveredLabel && s.label !== hoveredLabel ? 0.3 : 1}
                stroke="transparent"
              />
            ))}
          </Pie>
          <Tooltip content={<DonutTooltip />} />
        </PieChart>
      </div>
    </div>
  );
}

// ── Segment table (acts as the legend + detail view) ─────────────────────────
interface TableProps {
  segs:         Segment[];
  title:        string;
  colorMap:     Record<string, string>;
  hoveredLabel: string | null;
  otherLabels:  Set<string>;
  onHover:      (label: string | null) => void;
}

function SegmentTable({ segs, title, colorMap, hoveredLabel, otherLabels, onHover }: TableProps) {
  if (!segs.length) return null;

  const isHighlighted = (label: string) => {
    if (!hoveredLabel) return false;
    if (hoveredLabel === label) return true;
    // When the "Other" bucket is active, highlight all collapsed rows
    if (hoveredLabel === "Other" && otherLabels.has(label)) return true;
    return false;
  };

  return (
    <div>
      <div className="text-xs font-semibold text-zinc-400 mb-2">{title}</div>
      <div className="overflow-x-auto scrollbar-thin">
        <table className="w-full text-xs min-w-[360px]">
          <thead>
            <tr className="border-b border-zinc-700">
              {["Segment", "Revenue", "% of Total", "YoY Growth"].map(h => (
                <th
                  key={h}
                  className={`py-2 font-medium text-zinc-500 ${h === "Segment" ? "text-left pr-4" : "text-right px-3"}`}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {segs.map((s, i) => {
              const highlighted = isHighlighted(s.label);
              const dimmed      = !!hoveredLabel && !highlighted;
              return (
                <tr
                  key={i}
                  className={`border-b border-zinc-800/50 cursor-default transition-all duration-100
                    ${highlighted ? "bg-zinc-800/60" : "hover:bg-zinc-800/20"}
                    ${dimmed      ? "opacity-30"     : ""}`}
                  onMouseEnter={() => onHover(s.label)}
                  onMouseLeave={() => onHover(null)}
                >
                  <td className="py-2 pr-4">
                    <div className="flex items-center gap-2">
                      <span
                        className="w-2.5 h-2.5 rounded-sm shrink-0"
                        style={{ background: colorMap[s.label] || COLORS[i % COLORS.length] }}
                      />
                      <span className="text-zinc-200">{s.label}</span>
                    </div>
                  </td>
                  <td className="py-2 px-3 text-right font-mono tabular-nums text-zinc-300">
                    {fmtB(s.amount)}
                  </td>
                  <td className="py-2 px-3 text-right font-mono tabular-nums text-zinc-400">
                    {s.pct.toFixed(1)}%
                  </td>
                  <td className="py-2 px-3 text-right font-mono tabular-nums">
                    {s.growth != null ? (
                      <span className={s.growth >= 0 ? "text-emerald-400" : "text-red-400"}>
                        {s.growth >= 0 ? "+" : ""}{s.growth.toFixed(1)}%
                      </span>
                    ) : (
                      <span className="text-zinc-600">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Section wrapper — owns hover state shared by chart + table ────────────────
interface SectionProps {
  segs:       Segment[];
  donutTitle: string;
  tableTitle: string;
  colorMap:   Record<string, string>;
}

function SegmentSection({ segs, donutTitle, tableTitle, colorMap }: SectionProps) {
  const [hoveredLabel, setHoveredLabel] = useState<string | null>(null);

  const displaySegs = useMemo(() => groupSegments(segs), [segs]);

  // Labels directly visible in the donut (the top-N and "Other")
  const displayLabelSet = useMemo(
    () => new Set(displaySegs.map(s => s.label)),
    [displaySegs],
  );

  // Labels collapsed into "Other" bucket — needed for table reverse-highlighting
  const otherLabels = useMemo(() => {
    const s = new Set<string>();
    for (const seg of segs) {
      if (!displayLabelSet.has(seg.label)) s.add(seg.label);
    }
    return s;
  }, [segs, displayLabelSet]);

  // Table row hover → map collapsed labels to "Other" so the correct slice lights up
  const handleTableHover = useCallback((label: string | null) => {
    if (!label) { setHoveredLabel(null); return; }
    setHoveredLabel(displayLabelSet.has(label) ? label : "Other");
  }, [displayLabelSet]);

  return (
    <div className="flex gap-6 items-start">
      {/* Fixed-width left column — chart never resizes based on table */}
      <div className="shrink-0">
        <DonutChart
          displaySegs={displaySegs}
          title={donutTitle}
          colorMap={colorMap}
          hoveredLabel={hoveredLabel}
          onHover={setHoveredLabel}
        />
      </div>

      {/* Flex right column — detail table + legend */}
      <div className="flex-1 min-w-0 pt-8">
        <SegmentTable
          segs={segs}
          title={tableTitle}
          colorMap={colorMap}
          hoveredLabel={hoveredLabel}
          otherLabels={otherLabels}
          onHover={handleTableHover}
        />
      </div>
    </div>
  );
}

// ── Historical stacked bar ────────────────────────────────────────────────────
function HistoricalBar({ data, keys, title, colorMap }: {
  data:     Record<string, number | string>[];
  keys:     string[];
  title:    string;
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
          <YAxis
            tick={{ fill: "#71717a", fontSize: 11 }} axisLine={false} tickLine={false}
            tickFormatter={v => fmtB(v)} width={64}
          />
          <Tooltip contentStyle={TT_STYLE} formatter={(v, name) => [fmtB(Number(v)), name]} />
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

// ── Main export ───────────────────────────────────────────────────────────────
export default function RevenueSegmentation({ segments }: { segments: SegmentedRevenuePeriod[] }) {
  const productSegs = useMemo(() => computeGrowth(segments, PRODUCT_AXIS), [segments]);
  const geoSegs     = useMemo(() => computeGrowth(segments, GEO_AXIS),     [segments]);
  const productHist = useMemo(() => buildHistorical(segments, PRODUCT_AXIS), [segments]);
  const geoHist     = useMemo(() => buildHistorical(segments, GEO_AXIS),     [segments]);
  const productKeys = useMemo(() => productSegs.map(s => s.label), [productSegs]);
  const geoKeys     = useMemo(() => geoSegs.map(s => s.label),     [geoSegs]);

  // Stable color map: same label → same color across both sections
  const colorMap = useMemo(() => {
    const map: Record<string, string> = {};
    let idx = 0;
    [...productKeys, ...geoKeys].forEach(k => {
      if (!(k in map)) map[k] = COLORS[idx++ % COLORS.length];
    });
    return map;
  }, [productKeys, geoKeys]);

  if (!productSegs.length && !geoSegs.length) {
    return (
      <div className="text-xs text-zinc-500 py-4">
        No segmentation data available for this ticker
      </div>
    );
  }

  const latestPeriod = segments[0]?.report_period?.slice(0, 4);

  return (
    <div className="space-y-10">

      {/* Product / Service */}
      {productSegs.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <div className="text-sm font-semibold text-zinc-300">Product &amp; Service Breakdown</div>
            {latestPeriod && (
              <span className="text-xs text-zinc-600 bg-zinc-800 px-2 py-0.5 rounded">
                FY{latestPeriod}
              </span>
            )}
          </div>
          <SegmentSection
            segs={productSegs}
            donutTitle="Revenue by Product"
            tableTitle="Detail"
            colorMap={colorMap}
          />
          {productHist.length > 1 && (
            <HistoricalBar
              data={productHist} keys={productKeys}
              title="Historical Revenue by Product" colorMap={colorMap}
            />
          )}
        </div>
      )}

      {/* Geography */}
      {geoSegs.length > 0 && (
        <div className="space-y-4">
          <div className="text-sm font-semibold text-zinc-300">Geographic Breakdown</div>
          <SegmentSection
            segs={geoSegs}
            donutTitle="Revenue by Geography"
            tableTitle="Detail"
            colorMap={colorMap}
          />
          {geoHist.length > 1 && (
            <HistoricalBar
              data={geoHist} keys={geoKeys}
              title="Historical Revenue by Geography" colorMap={colorMap}
            />
          )}
        </div>
      )}

    </div>
  );
}
