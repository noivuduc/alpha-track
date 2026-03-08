"use client";
import { MonthlyReturn } from "@/lib/portfolio-math";

const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

function cellColor(v: number): string {
  const abs = Math.abs(v);
  const intensity = Math.min(abs / 8, 1); // saturate at ±8%
  if (v > 0) {
    const l = Math.round(30 + intensity * 20);
    return `hsl(142, 72%, ${l}%)`;
  }
  if (v < 0) {
    const l = Math.round(30 + intensity * 20);
    return `hsl(0, 72%, ${l}%)`;
  }
  return "#27272a";
}

export default function MonthlyHeatmap({ data }: { data: MonthlyReturn[] }) {
  if (!data.length) {
    return <div className="text-zinc-500 text-sm text-center py-8">No return data</div>;
  }

  const years = [...new Set(data.map(d => d.year))].sort();
  const byKey: Record<string, number> = {};
  for (const d of data) byKey[`${d.year}-${d.month}`] = d.value;

  return (
    <div className="overflow-x-auto scrollbar-thin">
      <table className="text-xs w-full border-collapse min-w-[480px]">
        <thead>
          <tr>
            <th className="text-zinc-500 font-medium text-left pr-3 pb-2 w-12">Year</th>
            {MONTHS.map(m => (
              <th key={m} className="text-zinc-500 font-medium text-center pb-2 w-10">{m}</th>
            ))}
            <th className="text-zinc-500 font-medium text-center pb-2 w-14">YTD</th>
          </tr>
        </thead>
        <tbody>
          {years.map(year => {
            const ytd = Array.from({ length: 12 }, (_, i) => byKey[`${year}-${i + 1}`] ?? null)
              .filter(v => v != null)
              .reduce((acc, v) => acc * (1 + (v as number) / 100), 1);
            const ytdPct = (ytd - 1) * 100;

            return (
              <tr key={year}>
                <td className="text-zinc-400 font-mono pr-3 py-0.5">{year}</td>
                {MONTHS.map((_, mi) => {
                  const v = byKey[`${year}-${mi + 1}`];
                  return (
                    <td key={mi} className="py-0.5 px-0.5">
                      {v != null ? (
                        <div
                          title={`${v >= 0 ? '+' : ''}${v.toFixed(2)}%`}
                          className="rounded text-center py-1 px-0.5 tabular-nums font-mono cursor-default select-none transition-opacity hover:opacity-80"
                          style={{ backgroundColor: cellColor(v), color: "#fafafa" }}
                        >
                          {v >= 0 ? '+' : ''}{v.toFixed(1)}
                        </div>
                      ) : (
                        <div className="rounded bg-zinc-900 text-center py-1 text-zinc-700">–</div>
                      )}
                    </td>
                  );
                })}
                <td className="py-0.5 pl-1">
                  <div
                    className="rounded text-center py-1 px-1 tabular-nums font-mono font-semibold"
                    style={{ backgroundColor: cellColor(ytdPct), color: "#fafafa" }}
                  >
                    {ytdPct >= 0 ? '+' : ''}{ytdPct.toFixed(1)}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
