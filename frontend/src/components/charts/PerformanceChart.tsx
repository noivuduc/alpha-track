"use client";
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, Legend, CartesianGrid,
} from "recharts";

interface DataPoint {
  date: string;
  portfolio?: number;
  spy?: number;
  qqq?: number;
}

interface Props {
  data: DataPoint[];
  range: string;
  onRangeChange: (r: string) => void;
}

const RANGES = ["1M", "3M", "6M", "YTD", "1Y", "3Y"];

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-zinc-900 border border-zinc-700 rounded-lg p-3 text-xs shadow-xl">
      <p className="text-zinc-400 mb-2">{label}</p>
      {payload.map((p: any) => (
        <div key={p.dataKey} className="flex items-center gap-2 mb-1">
          <span className="w-2 h-2 rounded-full" style={{ background: p.color }} />
          <span className="text-zinc-300 capitalize">{p.dataKey}:</span>
          <span className="font-mono font-semibold" style={{ color: p.color }}>
            {p.value?.toFixed(2)}
          </span>
        </div>
      ))}
    </div>
  );
};

export default function PerformanceChart({ data, range, onRangeChange }: Props) {
  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="text-sm text-zinc-400">Performance (indexed to 100)</div>
        <div className="flex gap-1">
          {RANGES.map(r => (
            <button
              key={r}
              onClick={() => onRangeChange(r)}
              className={`px-2.5 py-1 text-xs rounded-md font-medium transition-colors ${
                range === r
                  ? "bg-blue-600 text-white"
                  : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800"
              }`}
            >
              {r}
            </button>
          ))}
        </div>
      </div>

      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
          <XAxis
            dataKey="date"
            tick={{ fill: "#71717a", fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: "#27272a" }}
            tickFormatter={d => {
              const dt = new Date(d);
              return dt.toLocaleDateString("en-US", { month: "short", day: "numeric" });
            }}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fill: "#71717a", fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={v => v.toFixed(0)}
            width={42}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend
            wrapperStyle={{ fontSize: "12px", paddingTop: "12px" }}
            formatter={(value) => (
              <span style={{ color: "#a1a1aa", textTransform: "capitalize" }}>{value}</span>
            )}
          />
          <Line
            type="monotone"
            dataKey="portfolio"
            stroke="#3b82f6"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, fill: "#3b82f6" }}
          />
          <Line
            type="monotone"
            dataKey="spy"
            stroke="#22c55e"
            strokeWidth={1.5}
            dot={false}
            strokeDasharray="4 4"
            activeDot={{ r: 3, fill: "#22c55e" }}
          />
          <Line
            type="monotone"
            dataKey="qqq"
            stroke="#a855f7"
            strokeWidth={1.5}
            dot={false}
            strokeDasharray="4 4"
            activeDot={{ r: 3, fill: "#a855f7" }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
