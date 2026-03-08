"use client";
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, Legend,
} from "recharts";
import { IncomeStatement, CashFlowStatement } from "@/lib/api";

function fmtB(v: number) {
  if (Math.abs(v) >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (Math.abs(v) >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  return `$${v.toLocaleString()}`;
}

const TT_STYLE = {
  backgroundColor: "#18181b", border: "1px solid #3f3f46",
  borderRadius: 8, color: "#e4e4e7", fontSize: 12,
};

function yoyGrowth(arr: number[]): (number | null)[] {
  return arr.map((v, i) => i === 0 ? null : arr[i - 1] !== 0 ? ((v - arr[i - 1]) / Math.abs(arr[i - 1])) * 100 : null);
}

interface Props {
  income:   IncomeStatement[];
  cashflow: CashFlowStatement[];
}

export default function FinancialCharts({ income, cashflow }: Props) {
  // Oldest → newest for chart order
  const inc = [...income].reverse();
  const cf  = [...cashflow].reverse();

  const years = inc.map(r => r.report_period.slice(0, 4));

  const revs     = inc.map(r => r.revenue       ?? 0);
  const grossArr = inc.map(r => r.gross_profit   ?? 0);
  const opArr    = inc.map(r => r.operating_income ?? 0);
  const netArr   = inc.map(r => r.net_income     ?? 0);
  const epsArr   = inc.map(r => r.earnings_per_share_diluted ?? r.earnings_per_share ?? 0);
  const fcfArr   = cf.map(r  => r.free_cash_flow ?? 0);

  const grossPct = inc.map(r => r.revenue && r.gross_profit    != null ? (r.gross_profit    / r.revenue * 100) : null);
  const opPct    = inc.map(r => r.revenue && r.operating_income != null ? (r.operating_income / r.revenue * 100) : null);
  const netPct   = inc.map(r => r.revenue && r.net_income      != null ? (r.net_income      / r.revenue * 100) : null);

  const revGrowth = yoyGrowth(revs);

  const revenueData = years.map((y, i) => ({
    year: y, revenue: revs[i], growth: revGrowth[i],
  }));
  const epsData  = years.map((y, i) => ({ year: y, eps: epsArr[i] }));
  const fcfData  = years.map((y, i) => ({ year: y, fcf: fcfArr[i] }));
  const marginData = years.map((y, i) => ({
    year: y, gross: grossPct[i], operating: opPct[i], net: netPct[i],
  }));

  const chartClass = "bg-zinc-800/40 rounded-xl p-4";

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {/* Revenue */}
      <div className={chartClass}>
        <div className="text-xs font-semibold text-zinc-400 mb-3">Revenue</div>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={revenueData} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
            <XAxis dataKey="year" tick={{ fill: "#71717a", fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: "#71717a", fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={fmtB} width={60} />
            <Tooltip contentStyle={TT_STYLE} formatter={(v) => [fmtB(Number(v)), "Revenue"]} />
            <Bar dataKey="revenue" fill="#3b82f6" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* EPS */}
      <div className={chartClass}>
        <div className="text-xs font-semibold text-zinc-400 mb-3">EPS (Diluted)</div>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={epsData} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
            <XAxis dataKey="year" tick={{ fill: "#71717a", fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: "#71717a", fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={v => `$${v.toFixed(1)}`} width={50} />
            <Tooltip contentStyle={TT_STYLE} formatter={(v) => [`$${Number(v).toFixed(2)}`, "EPS"]} />
            <ReferenceLine y={0} stroke="#52525b" />
            <Bar dataKey="eps" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Free Cash Flow */}
      <div className={chartClass}>
        <div className="text-xs font-semibold text-zinc-400 mb-3">Free Cash Flow</div>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={fcfData} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
            <XAxis dataKey="year" tick={{ fill: "#71717a", fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: "#71717a", fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={fmtB} width={60} />
            <Tooltip contentStyle={TT_STYLE} formatter={(v) => [fmtB(Number(v)), "FCF"]} />
            <ReferenceLine y={0} stroke="#52525b" />
            <Bar dataKey="fcf" fill="#10b981" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Margins */}
      <div className={chartClass}>
        <div className="text-xs font-semibold text-zinc-400 mb-3">Profit Margins (%)</div>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={marginData} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
            <XAxis dataKey="year" tick={{ fill: "#71717a", fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: "#71717a", fontSize: 11 }} axisLine={false} tickLine={false}
                   tickFormatter={v => `${v.toFixed(0)}%`} width={45} />
            <Tooltip contentStyle={TT_STYLE} formatter={(v) => [`${Number(v).toFixed(1)}%`]} />
            <Legend iconType="circle" iconSize={8}
              formatter={(v) => <span style={{ color: "#a1a1aa", fontSize: 11 }}>{v}</span>} />
            <Line type="monotone" dataKey="gross"     name="Gross"     stroke="#3b82f6" dot={false} strokeWidth={2} connectNulls />
            <Line type="monotone" dataKey="operating" name="Operating" stroke="#8b5cf6" dot={false} strokeWidth={2} connectNulls />
            <Line type="monotone" dataKey="net"       name="Net"       stroke="#10b981" dot={false} strokeWidth={2} connectNulls />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
