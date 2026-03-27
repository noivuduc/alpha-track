"use client";
import { useMemo, useState, useCallback } from "react";
import {
  PieChart, Pie, Cell, Sector, Tooltip, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Legend, LabelList,
} from "recharts";
import { SegmentedRevenuePeriod } from "@/lib/api";
import {
  ParsedSegment,
  OTHER_KEY,
  parseSegments,
  discoverAxes,
  dominantMetric,
  axisLabels,
} from "@/lib/segment_service";

// ── Palette ───────────────────────────────────────────────────────────────────
const COLORS = [
  "#3b82f6", "#8b5cf6", "#10b981", "#f59e0b", "#ef4444",
  "#06b6d4", "#ec4899", "#84cc16", "#f97316", "#6366f1",
];
const OTHER_COLOR      = "#52525b";   // zinc-600 — neutral bucket
const MAX_DONUT_SLICES = 8;

// ── Donut geometry ────────────────────────────────────────────────────────────
const DONUT_SIZE     = 280;
const INNER_R        = 77;
const OUTER_R        = 126;
const ACTIVE_OUTER_R = 132;

// ── Helpers ───────────────────────────────────────────────────────────────────
function fmtB(n: number): string {
  if (Math.abs(n) >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (Math.abs(n) >= 1e9)  return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6)  return `$${(n / 1e6).toFixed(1)}M`;
  return `$${n.toLocaleString()}`;
}

const TT_STYLE = {
  backgroundColor: "#18181b", border: "1px solid #3f3f46",
  borderRadius: 8, color: "#e4e4e7", fontSize: 12,
};

// ── Internal enriched segment type ───────────────────────────────────────────
interface SegmentWithStats extends ParsedSegment {
  pct:    number;
  growth: number | null;
}

// ── Per-axis computed data bundle ─────────────────────────────────────────────
interface AxisData {
  segs:        SegmentWithStats[];                       // latest period w/ growth
  histRows:    Record<string, number | string>[];        // one row per year, keyed by seg.key
  keyLabelMap: Record<string, string>;                   // seg.key → display label
  keys:        string[];                                 // ordered seg.key list
}

// ── Segment grouping ──────────────────────────────────────────────────────────
/**
 * Sort DESC, keep top (MAX-1) slices, collapse tail into a synthetic "Other"
 * entry with key=OTHER_KEY.  Returns at most MAX_DONUT_SLICES entries.
 */
function groupSegments(segs: SegmentWithStats[]): SegmentWithStats[] {
  const sorted = [...segs].sort((a, b) => b.value - a.value);
  if (sorted.length <= MAX_DONUT_SLICES) return sorted;

  const top  = sorted.slice(0, MAX_DONUT_SLICES - 1);
  const tail = sorted.slice(MAX_DONUT_SLICES - 1);

  const otherValue = tail.reduce((s, t) => s + t.value, 0);
  const total      = sorted.reduce((s, t) => s + t.value, 0) || 1;
  const proto      = sorted[0];

  return [
    ...top,
    {
      key:    OTHER_KEY,
      label:  "Other",
      value:  otherValue,
      pct:    (otherValue / total) * 100,
      growth: null,
      axis:   proto.axis,
      metric: proto.metric,
      period: proto.period,
    },
  ];
}

// ── Data computation ──────────────────────────────────────────────────────────

function computeGrowthForAxis(
  periods: SegmentedRevenuePeriod[],
  axis:    string,
  metric:  string,
): SegmentWithStats[] {
  const sorted = [...periods].sort((a, b) =>
    b.report_period.localeCompare(a.report_period)
  );
  if (!sorted.length) return [];

  const latest = parseSegments(sorted, { metric_name: metric, axis });
  const total  = latest.reduce((s, x) => s + x.value, 0) || 1;

  // Build prior-period map keyed by segment.key (NEVER label)
  const priorMap: Record<string, number> = {};
  if (sorted.length >= 2) {
    const prior = parseSegments(sorted, {
      metric_name: metric, axis, period: sorted[1].report_period,
    });
    for (const s of prior) priorMap[s.key] = s.value;
  }

  return latest.map(s => ({
    ...s,
    pct:    (s.value / total) * 100,
    growth: s.key in priorMap
      ? ((s.value - priorMap[s.key]) / Math.abs(priorMap[s.key])) * 100
      : null,
  }));
}

function buildHistoricalForAxis(
  periods: SegmentedRevenuePeriod[],
  axis:    string,
  metric:  string,
): { rows: Record<string, number | string>[]; keyLabelMap: Record<string, string> } {
  const sorted = [...periods].sort((a, b) =>
    a.report_period.localeCompare(b.report_period)   // ASC for chronological chart
  );

  const keyLabelMap: Record<string, string> = {};
  const rows = sorted.map(period => {
    const segs = parseSegments(sorted, {
      metric_name: metric, axis, period: period.report_period,
    });
    const row: Record<string, number | string> = {
      year: period.report_period.slice(0, 4),
    };
    for (const seg of segs) {
      row[seg.key]        = seg.value;       // KEY as dataKey — never label
      keyLabelMap[seg.key] = seg.label;       // map for display
    }
    return row;
  });

  return { rows, keyLabelMap };
}

function computeAxisData(
  periods:       SegmentedRevenuePeriod[],
  discoveredAxes: string[],
): Record<string, AxisData> {
  const result: Record<string, AxisData> = {};
  for (const axis of discoveredAxes) {
    const metric = dominantMetric(periods, axis);
    if (!metric) continue;

    const segs = computeGrowthForAxis(periods, axis, metric);
    if (!segs.length) continue;

    const { rows: histRows, keyLabelMap } = buildHistoricalForAxis(periods, axis, metric);

    result[axis] = {
      segs,
      histRows,
      keyLabelMap,
      keys: segs.map(s => s.key),
    };
  }
  return result;
}

// ── Donut active shape ────────────────────────────────────────────────────────
function ActiveShape(props: any) {
  const { cx, cy, innerRadius, startAngle, endAngle, fill } = props;
  return (
    <Sector
      cx={cx} cy={cy}
      innerRadius={innerRadius - 3}
      outerRadius={ACTIVE_OUTER_R}
      startAngle={startAngle}
      endAngle={endAngle}
      fill={fill}
    />
  );
}

// ── Donut tooltip ─────────────────────────────────────────────────────────────
function DonutTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const s: SegmentWithStats = payload[0].payload;
  return (
    <div style={{ ...TT_STYLE, padding: "10px 14px", minWidth: 210 }}>
      <p className="font-semibold text-zinc-200 mb-2 text-[13px] leading-snug">{s.label}</p>
      <div className="space-y-1 text-xs">
        <div className="flex justify-between gap-8">
          <span className="text-zinc-500">Revenue</span>
          <span className="font-mono text-zinc-300">{fmtB(s.value)}</span>
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
  displaySegs: SegmentWithStats[];
  title:       string;
  colorMap:    Record<string, string>;    // key → color
  hoveredKey:  string | null;
  onHover:     (key: string | null) => void;
}

function DonutChart({ displaySegs, title, colorMap, hoveredKey, onHover }: DonutProps) {
  if (!displaySegs.length) return null;

  const activeIndex = hoveredKey
    ? displaySegs.findIndex(s => s.key === hoveredKey)
    : -1;

  const sliceColor = (key: string, idx: number) =>
    key === OTHER_KEY ? OTHER_COLOR : (colorMap[key] ?? COLORS[idx % COLORS.length]);

  return (
    <div>
      <div className="text-xs font-semibold text-zinc-400 mb-3 text-center">{title}</div>
      <div className="flex items-center justify-center" style={{ width: DONUT_SIZE, height: DONUT_SIZE }}>
        <PieChart width={DONUT_SIZE} height={DONUT_SIZE}>
          <Pie {...{
            data: displaySegs, dataKey: "value", nameKey: "label",
            cx: DONUT_SIZE / 2, cy: DONUT_SIZE / 2,
            innerRadius: INNER_R, outerRadius: OUTER_R, paddingAngle: 1.5,
            activeIndex: activeIndex >= 0 ? activeIndex : undefined,
            activeShape: ActiveShape,
            onMouseEnter: (_: any, idx: number) => onHover(displaySegs[idx]?.key ?? null),
            onMouseLeave: () => onHover(null),
            isAnimationActive: false,
          } as any}>
            {displaySegs.map((s, i) => (
              <Cell
                key={s.key}                          // ← stable segment.key, never index
                fill={sliceColor(s.key, i)}
                opacity={hoveredKey && s.key !== hoveredKey ? 0.3 : 1}
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

// ── Segment table ─────────────────────────────────────────────────────────────
interface TableProps {
  segs:       SegmentWithStats[];
  title:      string;
  colorMap:   Record<string, string>;    // key → color
  hoveredKey: string | null;
  otherKeys:  Set<string>;
  onHover:    (key: string | null) => void;
}

function SegmentTable({ segs, title, colorMap, hoveredKey, otherKeys, onHover }: TableProps) {
  if (!segs.length) return null;

  const isHighlighted = (key: string) => {
    if (!hoveredKey) return false;
    if (hoveredKey === key) return true;
    if (hoveredKey === OTHER_KEY && otherKeys.has(key)) return true;
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
              const highlighted = isHighlighted(s.key);
              const dimmed      = !!hoveredKey && !highlighted;
              return (
                <tr
                  key={`${s.key}-${s.period}`}      // ← stable composite key
                  className={`border-b border-zinc-800/50 cursor-default transition-all duration-100
                    ${highlighted ? "bg-zinc-800/60" : "hover:bg-zinc-800/20"}
                    ${dimmed      ? "opacity-30"     : ""}`}
                  onMouseEnter={() => onHover(s.key)}
                  onMouseLeave={() => onHover(null)}
                >
                  <td className="py-2 pr-4">
                    <div className="flex items-center gap-2">
                      <span
                        className="w-2.5 h-2.5 rounded-sm shrink-0"
                        style={{
                          background: s.key === OTHER_KEY
                            ? OTHER_COLOR
                            : (colorMap[s.key] ?? COLORS[i % COLORS.length]),
                        }}
                      />
                      <span className="text-zinc-200">{s.label}</span>
                    </div>
                  </td>
                  <td className="py-2 px-3 text-right font-mono tabular-nums text-zinc-300">
                    {fmtB(s.value)}
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

// ── Section wrapper ───────────────────────────────────────────────────────────
interface SectionProps {
  segs:       SegmentWithStats[];
  donutTitle: string;
  tableTitle: string;
  colorMap:   Record<string, string>;
}

function SegmentSection({ segs, donutTitle, tableTitle, colorMap }: SectionProps) {
  const [hoveredKey, setHoveredKey] = useState<string | null>(null);

  const displaySegs = useMemo(() => groupSegments(segs), [segs]);

  // Keys visible in the donut (top-N + OTHER_KEY)
  const displayKeySet = useMemo(
    () => new Set(displaySegs.map(s => s.key)),
    [displaySegs],
  );

  // Keys collapsed into the "Other" bucket — needed for reverse-highlighting in the table
  const otherKeys = useMemo(() => {
    const s = new Set<string>();
    for (const seg of segs) {
      if (!displayKeySet.has(seg.key)) s.add(seg.key);
    }
    return s;
  }, [segs, displayKeySet]);

  // Table hover: map collapsed segments to the synthetic OTHER_KEY
  const handleTableHover = useCallback((key: string | null) => {
    if (!key) { setHoveredKey(null); return; }
    setHoveredKey(displayKeySet.has(key) ? key : OTHER_KEY);
  }, [displayKeySet]);

  return (
    <div className="flex gap-6 items-start">
      <div className="shrink-0">
        <DonutChart
          displaySegs={displaySegs}
          title={donutTitle}
          colorMap={colorMap}
          hoveredKey={hoveredKey}
          onHover={setHoveredKey}
        />
      </div>
      <div className="flex-1 min-w-0 pt-8">
        <SegmentTable
          segs={segs}
          title={tableTitle}
          colorMap={colorMap}
          hoveredKey={hoveredKey}
          otherKeys={otherKeys}
          onHover={handleTableHover}
        />
      </div>
    </div>
  );
}

// ── Historical stacked bar ────────────────────────────────────────────────────
interface HistoricalBarProps {
  data:        Record<string, number | string>[];
  keys:        string[];                     // ordered segment.key values → dataKey
  keyLabelMap: Record<string, string>;       // key → display label
  title:       string;
  colorMap:    Record<string, string>;
}

function HistoricalBar({ data, keys, keyLabelMap, title, colorMap }: HistoricalBarProps) {
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
          <Tooltip
            contentStyle={TT_STYLE}
            formatter={(v, name) => [fmtB(Number(v)), keyLabelMap[name as string] ?? name]}
          />
          <Legend
            iconType="circle" iconSize={8}
            formatter={k => (
              <span style={{ color: "#a1a1aa", fontSize: 11 }}>
                {keyLabelMap[k as string] ?? k}
              </span>
            )}
            wrapperStyle={{ paddingTop: 8 }}
          />
          {keys.map((k, i) => (
            <Bar
              key={k}                          // ← segment.key as React key
              dataKey={k}                      // segment.key as row property accessor
              name={k}                         // resolved to label in formatter above
              stackId="a"
              fill={colorMap[k] ?? COLORS[i % COLORS.length]}
              radius={i === keys.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]}
            >
              <LabelList
                dataKey={k}
                position="center"
                content={props => {
                  const { x, y, width, height, value } = props as {
                    x?: number; y?: number; width?: number; height?: number; value?: number;
                  };
                  if (!value || !width || !height || height < 18 || width < 30) return null;
                  const displayName = keyLabelMap[k] ?? k;
                  return (
                    <text
                      x={(x ?? 0) + (width ?? 0) / 2}
                      y={(y ?? 0) + (height ?? 0) / 2}
                      textAnchor="middle"
                      dominantBaseline="middle"
                      fill="rgba(255,255,255,0.85)"
                      fontSize={9}
                    >
                      {displayName.length > 12 ? displayName.slice(0, 11) + "…" : displayName}
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
  // Discover all available axes dynamically — no hardcoded axis constants
  const discoveredAxes = useMemo(() => discoverAxes(segments), [segments]);

  // Compute all per-axis data in one pass
  const axisData = useMemo(
    () => computeAxisData(segments, discoveredAxes),
    [segments, discoveredAxes],
  );

  // Build a stable colorMap keyed by segment.key (not label) across all axes
  const colorMap = useMemo(() => {
    const map: Record<string, string> = {};
    let idx = 0;
    for (const axis of discoveredAxes) {
      for (const s of axisData[axis]?.segs ?? []) {
        if (!(s.key in map)) map[s.key] = COLORS[idx++ % COLORS.length];
      }
    }
    return map;
  }, [discoveredAxes, axisData]);

  const hasData = discoveredAxes.some(ax => (axisData[ax]?.segs.length ?? 0) > 0);

  if (!hasData) {
    return (
      <div className="text-xs text-zinc-500 py-4">
        No segmentation data available for this ticker
      </div>
    );
  }

  const latestYear = segments[0]?.report_period?.slice(0, 4);

  return (
    <div className="space-y-10">
      {discoveredAxes.map(axis => {
        const data = axisData[axis];
        if (!data?.segs.length) return null;

        const labels = axisLabels(axis);

        return (
          <div key={axis} className="space-y-4">
            <div className="flex items-center gap-2">
              <div className="text-sm font-semibold text-zinc-300">{labels.title}</div>
              {latestYear && (
                <span className="text-xs text-zinc-600 bg-zinc-800 px-2 py-0.5 rounded">
                  FY{latestYear}
                </span>
              )}
            </div>

            <SegmentSection
              segs={data.segs}
              donutTitle={labels.donut}
              tableTitle="Detail"
              colorMap={colorMap}
            />

            {data.histRows.length > 1 && (
              <HistoricalBar
                data={data.histRows}
                keys={data.keys}
                keyLabelMap={data.keyLabelMap}
                title={labels.hist}
                colorMap={colorMap}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
