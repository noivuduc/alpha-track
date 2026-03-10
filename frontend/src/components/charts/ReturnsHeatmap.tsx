"use client";
import { useState, useMemo } from "react";
import {
  DailyHeatmapPoint, WeeklyReturn, MonthlyReturn, PeriodExtremes,
} from "@/lib/api";

// ── Types ──────────────────────────────────────────────────────────────────────

type Mode   = "Daily" | "Weekly" | "Monthly";
type Period = "1M" | "3M" | "6M" | "1Y" | "3Y" | "5Y" | "All";

type TooltipState = {
  x: number; y: number;
  line1: string; line2: string;
  positive: boolean;
} | null;

interface Props {
  dailyHeatmap:    DailyHeatmapPoint[];
  weeklyReturns:   WeeklyReturn[];
  monthlyReturns:  MonthlyReturn[];
  periodExtremes?: PeriodExtremes | null;
}

// ── Constants ──────────────────────────────────────────────────────────────────

const MONTHS_SHORT = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const DOW_INITIALS = ["M","T","W","T","F"];
const CELL_GAP     = "3px";
const DOW_LABEL_W  = 18; // px — fixed width for day-of-week labels

const PERIOD_MONTHS: Record<Exclude<Period,"All">, number> = {
  "1M": 1, "3M": 3, "6M": 6, "1Y": 12, "3Y": 36, "5Y": 60,
};

// ── Date utilities ─────────────────────────────────────────────────────────────

function getWeekKey(date: string): string {
  const d   = new Date(date + "T00:00:00Z");
  const dow = d.getUTCDay();
  const toMonday = dow === 0 ? -6 : 1 - dow;
  const monday = new Date(d);
  monday.setUTCDate(d.getUTCDate() + toMonday);
  return monday.toISOString().slice(0, 10);
}

function isoWeekToDate(year: number, week: number): Date {
  const jan4 = new Date(Date.UTC(year, 0, 4));
  const dow  = jan4.getUTCDay() || 7;
  const mondayW1 = new Date(jan4);
  mondayW1.setUTCDate(jan4.getUTCDate() - dow + 1);
  const result = new Date(mondayW1);
  result.setUTCDate(mondayW1.getUTCDate() + (week - 1) * 7);
  return result;
}

// ── Color scales ───────────────────────────────────────────────────────────────

function getReturnColor(v: number): string {
  if (v >= 2.0) return "#15803d";
  if (v >= 0.5) return "#22c55e";
  if (v > -0.5) return "#3f3f46";
  if (v > -2.0) return "#ef4444";
  return "#b91c1c";
}

function monthlyColor(v: number): string {
  const abs = Math.min(Math.abs(v) / 8, 1);
  if (v > 0) return `hsl(142,72%,${Math.round(25 + abs * 25)}%)`;
  if (v < 0) return `hsl(0,72%,${Math.round(25 + abs * 25)}%)`;
  return "#27272a";
}

function pctClass(v: number | null | undefined): string {
  if (v == null) return "text-zinc-500";
  return v >= 0 ? "text-emerald-400" : "text-red-400";
}

function fmtPct(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}

// ── Period filtering ───────────────────────────────────────────────────────────

function filterDaily(data: DailyHeatmapPoint[], period: Period): DailyHeatmapPoint[] {
  if (!data.length || period === "All") return data;
  const latest = new Date(data[data.length - 1].date + "T00:00:00Z");
  latest.setUTCMonth(latest.getUTCMonth() - PERIOD_MONTHS[period]);
  return data.filter(pt => new Date(pt.date + "T00:00:00Z") >= latest);
}

function filterWeekly(data: WeeklyReturn[], period: Period): WeeklyReturn[] {
  if (!data.length || period === "All") return data;
  const last   = data[data.length - 1];
  const cutoff = isoWeekToDate(last.year, last.week_number);
  cutoff.setUTCMonth(cutoff.getUTCMonth() - PERIOD_MONTHS[period]);
  return data.filter(w => isoWeekToDate(w.year, w.week_number) >= cutoff);
}

function filterMonthly(data: MonthlyReturn[], period: Period): MonthlyReturn[] {
  if (!data.length || period === "All") return data;
  const last   = data[data.length - 1];
  const cutoff = new Date(Date.UTC(last.year, last.month - 1, 1));
  cutoff.setUTCMonth(cutoff.getUTCMonth() - PERIOD_MONTHS[period]);
  return data.filter(m => new Date(Date.UTC(m.year, m.month - 1, 1)) >= cutoff);
}

// ── Shared primitives ──────────────────────────────────────────────────────────

function Empty() {
  return (
    <div className="h-20 flex items-center justify-center text-zinc-600 text-sm">
      Not enough data for this period
    </div>
  );
}

function ColorLegend() {
  return (
    <div className="flex items-center gap-3 flex-wrap mt-2">
      <span className="text-[10px] text-zinc-600">Return:</span>
      {[
        { color: "#b91c1c", label: "≤−2%" },
        { color: "#ef4444", label: "−2% to −0.5%" },
        { color: "#3f3f46", label: "±0.5%" },
        { color: "#22c55e", label: "+0.5% to +2%" },
        { color: "#15803d", label: "≥+2%" },
      ].map(({ color, label }) => (
        <div key={label} className="flex items-center gap-1">
          <div className="rounded" style={{ width: 8, height: 8, backgroundColor: color }} />
          <span className="text-[10px] text-zinc-500">{label}</span>
        </div>
      ))}
    </div>
  );
}

// ── Floating Tooltip (position:fixed — no z-index/overflow issues) ─────────────

function FloatingTooltip({ tip }: { tip: TooltipState }) {
  if (!tip) return null;
  return (
    <div
      className="pointer-events-none"
      style={{
        position:  "fixed",
        top:       tip.y + 16,
        left:      tip.x,
        transform: "translateX(-50%)",
        zIndex:    9999,
      }}
    >
      <div className="bg-zinc-950 border border-zinc-700 rounded-lg px-2.5 py-1.5 shadow-2xl whitespace-nowrap">
        <p className="text-[11px] font-mono text-zinc-300">{tip.line1}</p>
        <p className={`text-[11px] font-mono font-semibold ${tip.positive ? "text-emerald-400" : "text-red-400"}`}>
          {tip.line2}
        </p>
      </div>
    </div>
  );
}

// ── Period Extremes Panel ──────────────────────────────────────────────────────

function PeriodExtremesPanel({ data }: { data: PeriodExtremes }) {
  const items = [
    { label: "Day",   best: data.best_day_pct,   worst: data.worst_day_pct   },
    { label: "Week",  best: data.best_week_pct,  worst: data.worst_week_pct  },
    { label: "Month", best: data.best_month_pct, worst: data.worst_month_pct },
  ];
  if (!items.some(i => i.best != null || i.worst != null)) return null;
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
      <h3 className="text-sm font-semibold text-zinc-300 mb-4">Return Extremes</h3>
      <div className="grid grid-cols-3 gap-4">
        {items.map(({ label, best, worst }) => (
          <div key={label} className="space-y-2">
            <div className="text-[10px] font-semibold text-zinc-600 uppercase tracking-wider">{label}</div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-zinc-500">Best</span>
              <span className={`text-sm font-mono font-semibold tabular-nums ${pctClass(best)}`}>{fmtPct(best)}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-zinc-500">Worst</span>
              <span className={`text-sm font-mono font-semibold tabular-nums ${pctClass(worst)}`}>{fmtPct(worst)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Daily Grid — GitHub-style (cols = ISO weeks, rows = Mon–Fri) ──────────────
//
// Uses display:flex rows: a fixed DOW_LABEL_W label div + a flex:1 CSS grid.
// The grid uses repeat(N, minmax(0,1fr)) so cells expand to fill the container.

interface GridProps<T> { data: T; onTooltip: (t: TooltipState) => void; }

function DailyGrid({ data, onTooltip }: GridProps<DailyHeatmapPoint[]>) {
  const { weekKeys, weekGrid, monthLabels } = useMemo(() => {
    const weekMap = new Map<string, (DailyHeatmapPoint | null)[]>();
    for (const pt of data) {
      if (pt.weekday > 4) continue;
      const key = getWeekKey(pt.date);
      if (!weekMap.has(key)) weekMap.set(key, Array(5).fill(null));
      weekMap.get(key)![pt.weekday] = pt;
    }

    const weekKeys = [...weekMap.keys()].sort();

    let lastMk = "";
    const monthLabels: (string | null)[] = weekKeys.map(wk => {
      const cells   = weekMap.get(wk)!;
      const firstPt = cells.find(c => c !== null);
      const mk = firstPt
        ? `${firstPt.year}-${firstPt.month}`
        : `${wk.slice(0, 4)}-${parseInt(wk.slice(5, 7))}`;
      if (mk !== lastMk) { lastMk = mk; return mk; }
      return null;
    });

    return { weekKeys, weekGrid: weekMap, monthLabels };
  }, [data]);

  if (!weekKeys.length) return <Empty />;

  const colTemplate = `repeat(${weekKeys.length}, minmax(0, 1fr))`;

  function handleEnter(e: React.MouseEvent, pt: DailyHeatmapPoint) {
    onTooltip({
      x: e.clientX, y: e.clientY,
      line1:    `${MONTHS_SHORT[pt.month - 1]} ${pt.day}, ${pt.year}`,
      line2:    `Return: ${fmtPct(pt.return_pct)}`,
      positive: pt.return_pct >= 0,
    });
  }

  return (
    <div style={{ width: "100%" }}>
      {/* Month label header row */}
      <div style={{ display: "flex", marginBottom: CELL_GAP }}>
        <div style={{ width: DOW_LABEL_W, flexShrink: 0 }} />
        <div style={{ flex: 1, display: "grid", gridTemplateColumns: colTemplate, gap: CELL_GAP }}>
          {monthLabels.map((mk, i) => {
            let text = "";
            if (mk) {
              const [y, m] = mk.split("-");
              text = `${MONTHS_SHORT[parseInt(m) - 1]} ${y}`;
            }
            return (
              <div
                key={weekKeys[i]}
                className="text-[9px] text-zinc-500 font-mono"
                style={{ overflow: "visible", whiteSpace: "nowrap" }}
              >
                {text}
              </div>
            );
          })}
        </div>
      </div>

      {/* One flex row per day of week */}
      {DOW_INITIALS.map((initial, dow) => (
        <div key={dow} style={{ display: "flex", marginBottom: CELL_GAP }}>
          <div
            className="text-[9px] text-zinc-600 font-mono flex items-center justify-end pr-1"
            style={{ width: DOW_LABEL_W, flexShrink: 0 }}
          >
            {initial}
          </div>
          <div style={{ flex: 1, display: "grid", gridTemplateColumns: colTemplate, gap: CELL_GAP }}>
            {weekKeys.map(wk => {
              const pt = weekGrid.get(wk)![dow];
              return (
                <div
                  key={wk}
                  className="rounded cursor-default"
                  style={{
                    aspectRatio: "1",
                    backgroundColor: pt ? getReturnColor(pt.return_pct) : "rgba(39,39,42,0.3)",
                  }}
                  onMouseEnter={pt ? (e) => handleEnter(e, pt) : undefined}
                  onMouseLeave={pt ? () => onTooltip(null) : undefined}
                />
              );
            })}
          </div>
        </div>
      ))}

      <ColorLegend />
    </div>
  );
}

// ── Weekly Grid — continuous timeline (one row, N weeks) ──────────────────────
//
// Year labels float above the first week of each calendar year.
// One CSS grid row fills the full container width via repeat(N, minmax(0,1fr)).

function WeeklyGrid({ data, onTooltip }: GridProps<WeeklyReturn[]>) {
  const yearLabels = useMemo(
    () => data.map((w, i) => (i === 0 || data[i - 1].year !== w.year ? w.year : null)),
    [data],
  );

  if (!data.length) return <Empty />;

  const colTemplate = `repeat(${data.length}, minmax(0, 1fr))`;

  function handleEnter(e: React.MouseEvent, w: WeeklyReturn) {
    onTooltip({
      x: e.clientX, y: e.clientY,
      line1:    `Week ${w.week_number}, ${w.year}`,
      line2:    `Return: ${fmtPct(w.return_pct)}`,
      positive: w.return_pct >= 0,
    });
  }

  return (
    <div style={{ width: "100%" }}>
      {/* Year labels above year boundaries */}
      <div style={{ display: "grid", gridTemplateColumns: colTemplate, gap: CELL_GAP, marginBottom: CELL_GAP }}>
        {yearLabels.map((yr, i) => (
          <div
            key={i}
            className="text-[9px] text-zinc-500 font-mono"
            style={{ overflow: "visible", whiteSpace: "nowrap" }}
          >
            {yr ?? ""}
          </div>
        ))}
      </div>

      {/* Single row of cells */}
      <div style={{ display: "grid", gridTemplateColumns: colTemplate, gap: CELL_GAP }}>
        {data.map(w => (
          <div
            key={w.week}
            className="rounded cursor-default"
            style={{
              aspectRatio:     "1",
              backgroundColor: getReturnColor(w.return_pct),
            }}
            onMouseEnter={(e) => handleEnter(e, w)}
            onMouseLeave={() => onTooltip(null)}
          />
        ))}
      </div>

      <ColorLegend />
    </div>
  );
}

// ── Monthly Grid — year rows × (Jan–Dec + YTD) ────────────────────────────────
//
// Column template: "36px repeat(12, 1fr) 0.75fr"
// Each cell is square via aspect-ratio:1 and shows the return value as text.

function MonthlyGrid({ data, onTooltip }: GridProps<MonthlyReturn[]>) {
  const { years, byKey } = useMemo(() => {
    const byKey: Record<string, number> = {};
    for (const d of data) byKey[`${d.year}-${d.month}`] = d.value;
    const years = [...new Set(data.map(d => d.year))].sort();
    return { years, byKey };
  }, [data]);

  if (!years.length) return <Empty />;

  const colTemplate = "36px repeat(12, 1fr) 0.75fr";

  function handleEnter(e: React.MouseEvent, label: string, value: number) {
    onTooltip({
      x: e.clientX, y: e.clientY,
      line1:    label,
      line2:    `Return: ${fmtPct(value)}`,
      positive: value >= 0,
    });
  }

  return (
    <div style={{ width: "100%" }}>
      {/* Column headers */}
      <div style={{ display: "grid", gridTemplateColumns: colTemplate, gap: CELL_GAP, marginBottom: CELL_GAP }}>
        <div />
        {MONTHS_SHORT.map(m => (
          <div key={m} className="text-[10px] text-zinc-500 font-medium text-center">{m}</div>
        ))}
        <div className="text-[10px] text-zinc-500 font-medium text-center">YTD</div>
      </div>

      {/* Year rows */}
      {years.map(year => {
        const ytdFactor = Array.from({ length: 12 }, (_, i) => byKey[`${year}-${i + 1}`] ?? null)
          .filter((v): v is number => v != null)
          .reduce((acc, v) => acc * (1 + v / 100), 1);
        const ytd = (ytdFactor - 1) * 100;

        return (
          <div
            key={year}
            style={{ display: "grid", gridTemplateColumns: colTemplate, gap: CELL_GAP, marginBottom: CELL_GAP }}
          >
            <div className="text-[10px] text-zinc-400 font-mono flex items-center">{year}</div>

            {Array.from({ length: 12 }, (_, mi) => {
              const v = byKey[`${year}-${mi + 1}`];
              return (
                <div
                  key={mi}
                  className="rounded cursor-default flex items-center justify-center font-mono tabular-nums select-none transition-opacity hover:opacity-80"
                  style={{
                    aspectRatio:     "1",
                    backgroundColor: v != null ? monthlyColor(v) : "#18181b",
                    color:           "#fafafa",
                    fontSize:        "clamp(8px, 1vw, 11px)",
                  }}
                  onMouseEnter={v != null ? (e) => handleEnter(e, `${MONTHS_SHORT[mi]} ${year}`, v) : undefined}
                  onMouseLeave={v != null ? () => onTooltip(null) : undefined}
                >
                  {v != null ? `${v >= 0 ? "+" : ""}${v.toFixed(1)}` : ""}
                </div>
              );
            })}

            <div
              className="rounded cursor-default flex items-center justify-center font-mono tabular-nums font-semibold select-none transition-opacity hover:opacity-80"
              style={{
                aspectRatio:     "1",
                backgroundColor: monthlyColor(ytd),
                color:           "#fafafa",
                fontSize:        "clamp(8px, 1vw, 11px)",
              }}
              onMouseEnter={(e) => handleEnter(e, `YTD ${year}`, ytd)}
              onMouseLeave={() => onTooltip(null)}
            >
              {`${ytd >= 0 ? "+" : ""}${ytd.toFixed(1)}`}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

const MODES:   Mode[]   = ["Daily", "Weekly", "Monthly"];
const PERIODS: Period[] = ["1M", "3M", "6M", "1Y", "3Y", "5Y", "All"];

export default function ReturnsHeatmap({
  dailyHeatmap,
  weeklyReturns,
  monthlyReturns,
  periodExtremes,
}: Props) {
  const [mode,    setMode]    = useState<Mode>("Monthly");
  const [period,  setPeriod]  = useState<Period>("1Y");
  const [tooltip, setTooltip] = useState<TooltipState>(null);

  const filteredDaily   = useMemo(() => filterDaily(dailyHeatmap,     period), [dailyHeatmap,    period]);
  const filteredWeekly  = useMemo(() => filterWeekly(weeklyReturns,   period), [weeklyReturns,   period]);
  const filteredMonthly = useMemo(() => filterMonthly(monthlyReturns, period), [monthlyReturns,  period]);

  return (
    <div className="space-y-4">
      <FloatingTooltip tip={tooltip} />

      {periodExtremes && <PeriodExtremesPanel data={periodExtremes} />}

      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-4">
        {/* Header: title + mode toggle */}
        <div className="flex items-center justify-between flex-wrap gap-3">
          <h3 className="text-sm font-semibold text-zinc-300">Returns</h3>
          <div className="flex gap-0.5 bg-zinc-800 rounded-lg p-0.5">
            {MODES.map(m => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`px-3 py-1 text-xs rounded-md font-medium transition-colors ${
                  m === mode ? "bg-blue-600 text-white" : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                {m}
              </button>
            ))}
          </div>
        </div>

        {/* Time range selector */}
        <div className="flex gap-0.5 bg-zinc-800/60 rounded-lg p-0.5 w-fit">
          {PERIODS.map(p => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`px-2.5 py-1 text-xs rounded-md font-medium transition-colors ${
                p === period ? "bg-zinc-600 text-white" : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {p}
            </button>
          ))}
        </div>

        {/* Heatmap grid */}
        {mode === "Daily"   && <DailyGrid   data={filteredDaily}   onTooltip={setTooltip} />}
        {mode === "Weekly"  && <WeeklyGrid  data={filteredWeekly}  onTooltip={setTooltip} />}
        {mode === "Monthly" && <MonthlyGrid data={filteredMonthly} onTooltip={setTooltip} />}
      </div>
    </div>
  );
}
