"use client";
import { useMemo, useState } from "react";
import { DailyHeatmapPoint } from "@/lib/api";

const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// ── Color scale ─────────────────────────────────────────────────────────────────

function getReturnColor(returnPct: number): string {
  if (returnPct >= 2.0)  return "#15803d"; // dark green
  if (returnPct >= 0.5)  return "#22c55e"; // green
  if (returnPct > -0.5)  return "#3f3f46"; // neutral
  if (returnPct > -2.0)  return "#ef4444"; // red
  return "#b91c1c";                         // dark red
}

// ── Week grouping ───────────────────────────────────────────────────────────────

/** Returns ISO date string of the Monday that starts the week containing `date`. */
function getWeekKey(date: string): string {
  const d = new Date(date + "T00:00:00Z");
  const dow = d.getUTCDay(); // 0=Sun … 6=Sat
  const toMonday = dow === 0 ? -6 : 1 - dow;
  const monday = new Date(d);
  monday.setUTCDate(d.getUTCDate() + toMonday);
  return monday.toISOString().slice(0, 10);
}

// ── Main component ──────────────────────────────────────────────────────────────

export default function DailyReturnHeatmap({ data }: { data: DailyHeatmapPoint[] }) {
  const [hoveredDate, setHoveredDate] = useState<string | null>(null);

  // Group data by year for the year selector
  const years = useMemo(() => {
    const ys = [...new Set(data.map(pt => pt.year))].sort((a, b) => b - a);
    return ys;
  }, [data]);

  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const activeYear = selectedYear ?? (years[0] ?? null);

  // Build week grid for the selected year
  const { weekKeys, weekMap } = useMemo(() => {
    const yearData = activeYear != null ? data.filter(pt => pt.year === activeYear) : data;

    const weekMap = new Map<string, (DailyHeatmapPoint | null)[]>();
    for (const pt of yearData) {
      const key = getWeekKey(pt.date);
      if (!weekMap.has(key)) weekMap.set(key, Array(7).fill(null));
      weekMap.get(key)![pt.weekday] = pt;
    }
    const weekKeys = [...weekMap.keys()].sort();
    return { weekKeys, weekMap };
  }, [data, activeYear]);

  if (!data.length) {
    return <div className="text-zinc-500 text-sm text-center py-6">No daily return data</div>;
  }

  // Month label: show at first week of each month
  function monthLabel(wk: string, idx: number): string | null {
    const d = new Date(wk + "T00:00:00Z");
    if (idx === 0) return MONTHS_SHORT[d.getUTCMonth()];
    const prev = new Date(weekKeys[idx - 1] + "T00:00:00Z");
    if (prev.getUTCMonth() !== d.getUTCMonth()) return MONTHS_SHORT[d.getUTCMonth()];
    return null;
  }

  return (
    <div className="space-y-3">

      {/* Year selector */}
      {years.length > 1 && (
        <div className="flex gap-0.5 bg-zinc-800 rounded-lg p-0.5 self-start w-fit">
          {years.map(y => (
            <button
              key={y}
              onClick={() => setSelectedYear(y === activeYear ? null : y)}
              className={`px-3 py-1 text-xs rounded-md font-medium transition-colors ${
                y === activeYear
                  ? "bg-blue-600 text-white"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              {y}
            </button>
          ))}
        </div>
      )}

      {/* Grid */}
      <div className="overflow-x-auto scrollbar-thin">
        <table className="border-collapse">
          <thead>
            <tr>
              <th className="w-8 pr-2" />
              {DAY_LABELS.map(d => (
                <th
                  key={d}
                  className="text-zinc-600 font-medium text-center pb-1.5 text-[10px]"
                  style={{ width: 28 }}
                >
                  {d}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {weekKeys.map((wk, rowIdx) => {
              const cells = weekMap.get(wk)!;
              const label = monthLabel(wk, rowIdx);
              return (
                <tr key={wk}>
                  {/* Month label */}
                  <td
                    className="pr-2 text-right text-zinc-600 font-mono text-[9px] whitespace-nowrap py-0.5 align-middle"
                    style={{ minWidth: 28 }}
                  >
                    {label ?? ""}
                  </td>

                  {/* Day cells */}
                  {cells.map((pt, colIdx) => (
                    <td key={colIdx} className="py-0.5 px-0.5 relative">
                      {pt ? (
                        <>
                          <div
                            className="rounded cursor-default transition-opacity hover:opacity-75"
                            style={{
                              width: 24,
                              height: 24,
                              backgroundColor: getReturnColor(pt.return_pct),
                            }}
                            onMouseEnter={() => setHoveredDate(pt.date)}
                            onMouseLeave={() => setHoveredDate(null)}
                          />
                          {/* Tooltip */}
                          {hoveredDate === pt.date && (
                            <div
                              className="absolute z-30 pointer-events-none"
                              style={{
                                bottom: "calc(100% + 6px)",
                                left: "50%",
                                transform: "translateX(-50%)",
                              }}
                            >
                              <div className="bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-2 shadow-2xl whitespace-nowrap">
                                <p className="text-xs font-mono text-zinc-300 mb-0.5">
                                  {MONTHS_SHORT[pt.month - 1]} {pt.day} {pt.year}
                                </p>
                                <p className={`text-xs font-mono font-semibold ${
                                  pt.return_pct >= 0 ? "text-emerald-400" : "text-red-400"
                                }`}>
                                  Return: {pt.return_pct >= 0 ? "+" : ""}{pt.return_pct.toFixed(2)}%
                                </p>
                              </div>
                            </div>
                          )}
                        </>
                      ) : (
                        <div
                          className="rounded bg-zinc-900/40"
                          style={{ width: 24, height: 24 }}
                        />
                      )}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-[10px] text-zinc-600">Return:</span>
        {[
          { color: "#b91c1c", label: "≤ −2%" },
          { color: "#ef4444", label: "−2% to −0.5%" },
          { color: "#3f3f46", label: "±0.5%" },
          { color: "#22c55e", label: "+0.5% to +2%" },
          { color: "#15803d", label: "≥ +2%" },
        ].map(({ color, label }) => (
          <div key={label} className="flex items-center gap-1">
            <div className="rounded" style={{ width: 10, height: 10, backgroundColor: color }} />
            <span className="text-[10px] text-zinc-500">{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
