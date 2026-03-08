"use client";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from "recharts";

interface SectorSlice { name: string; value: number; }

const COLORS = [
  "#3b82f6", "#22c55e", "#a855f7", "#f59e0b",
  "#06b6d4", "#f43f5e", "#84cc16", "#fb923c",
  "#8b5cf6", "#14b8a6",
];

const CustomTooltip = ({ active, payload }: any) => {
  if (!active || !payload?.length) return null;
  const { name, value } = payload[0].payload;
  return (
    <div className="bg-zinc-900 border border-zinc-700 rounded-lg p-3 text-xs shadow-xl">
      <p className="text-zinc-300 font-medium">{name}</p>
      <p className="text-zinc-400 mt-0.5">{value.toFixed(1)}%</p>
    </div>
  );
};

const CustomLabel = ({ cx, cy, midAngle, innerRadius, outerRadius, percent }: any) => {
  if (percent < 0.05) return null;
  const RADIAN = Math.PI / 180;
  const r = innerRadius + (outerRadius - innerRadius) * 0.5;
  const x = cx + r * Math.cos(-midAngle * RADIAN);
  const y = cy + r * Math.sin(-midAngle * RADIAN);
  return (
    <text x={x} y={y} fill="#fafafa" textAnchor="middle" dominantBaseline="central" fontSize={11} fontWeight="600">
      {(percent * 100).toFixed(0)}%
    </text>
  );
};

export default function SectorDonut({ data }: { data: SectorSlice[] }) {
  if (!data.length) {
    return <div className="text-zinc-500 text-sm text-center py-8">No sector data</div>;
  }

  return (
    <ResponsiveContainer width="100%" height={260}>
      <PieChart>
        <Pie
          data={data}
          cx="50%"
          cy="50%"
          innerRadius={65}
          outerRadius={100}
          paddingAngle={2}
          dataKey="value"
          labelLine={false}
          label={<CustomLabel />}
        >
          {data.map((_, i) => (
            <Cell key={i} fill={COLORS[i % COLORS.length]} />
          ))}
        </Pie>
        <Tooltip content={<CustomTooltip />} />
        <Legend
          iconType="circle"
          iconSize={8}
          formatter={(value) => (
            <span style={{ color: "#a1a1aa", fontSize: "11px" }}>{value}</span>
          )}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}
