"use client";
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
} from "recharts";

export interface SectorSlice {
  name:   string;
  value:  number;         // percentage  0–100
  dollar?: number;        // optional market value in dollars
}

const COLORS = [
  "#3b82f6", "#22c55e", "#a855f7", "#f59e0b",
  "#06b6d4", "#f43f5e", "#84cc16", "#fb923c",
  "#8b5cf6", "#14b8a6",
];

function fmtDollar(n: number): string {
  const abs  = Math.abs(n);
  const sign = n < 0 ? "-" : "";
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(1)}K`;
  return `${sign}$${abs.toFixed(0)}`;
}

const CustomTooltip = ({ active, payload }: any) => {
  if (!active || !payload?.length) return null;
  const slice: SectorSlice = payload[0].payload;
  return (
    <div className="bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-xs shadow-xl">
      <p className="text-zinc-200 font-semibold mb-1">{slice.name}</p>
      <p className="text-zinc-400">{slice.value.toFixed(1)}% of portfolio</p>
      {slice.dollar != null && (
        <p className="text-zinc-500 mt-0.5">{fmtDollar(slice.dollar)}</p>
      )}
    </div>
  );
};

// Percentage label rendered on slices large enough to fit text
const SliceLabel = ({ cx, cy, midAngle, innerRadius, outerRadius, percent }: any) => {
  if (percent < 0.06) return null;
  const RADIAN = Math.PI / 180;
  const r = innerRadius + (outerRadius - innerRadius) * 0.55;
  const x = cx + r * Math.cos(-midAngle * RADIAN);
  const y = cy + r * Math.sin(-midAngle * RADIAN);
  return (
    <text
      x={x} y={y}
      fill="#fafafa"
      textAnchor="middle"
      dominantBaseline="central"
      fontSize={10}
      fontWeight={600}
    >
      {(percent * 100).toFixed(0)}%
    </text>
  );
};

interface Props {
  data:        SectorSlice[];
  height?:     number;   // default 220
  showLegend?: boolean;  // default true
}

export default function SectorDonut({ data, height = 220, showLegend = true }: Props) {
  if (!data.length) {
    return (
      <div className="flex items-center justify-center text-zinc-500 text-sm" style={{ height }}>
        No sector data
      </div>
    );
  }

  return (
    <div>
      {/* Donut chart */}
      <ResponsiveContainer width="100%" height={height}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius="52%"
            outerRadius="78%"
            paddingAngle={2}
            dataKey="value"
            labelLine={false}
            label={<SliceLabel />}
          >
            {data.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip content={<CustomTooltip />} />
        </PieChart>
      </ResponsiveContainer>

      {/* Custom legend */}
      {showLegend && (
        <div className="mt-2 space-y-1.5">
          {data.map((s, i) => (
            <div key={s.name} className="flex items-center gap-2">
              <div
                className="w-2.5 h-2.5 rounded-sm shrink-0"
                style={{ backgroundColor: COLORS[i % COLORS.length] }}
              />
              <span className="text-xs text-zinc-400 flex-1 truncate min-w-0">{s.name}</span>
              <span className="text-xs font-mono tabular-nums text-zinc-300 shrink-0">
                {s.value.toFixed(1)}%
              </span>
              {s.dollar != null && (
                <span className="text-xs font-mono tabular-nums text-zinc-600 w-16 text-right shrink-0">
                  {fmtDollar(s.dollar)}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
