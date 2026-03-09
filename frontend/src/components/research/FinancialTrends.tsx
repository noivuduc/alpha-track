"use client";
import {
  ComposedChart, Bar, Line, LineChart, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, Legend,
} from "recharts";
import { ResearchTrends } from "@/lib/api";

function fmtB(v: number) {
  if (Math.abs(v) >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (Math.abs(v) >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  return `$${v.toLocaleString()}`;
}

const TT_STYLE = {
  backgroundColor: "#18181b", border: "1px solid #3f3f46",
  borderRadius: 8, color: "#e4e4e7", fontSize: 12,
};

const AXIS_TICK = { fill: "#a1a1aa", fontSize: 11 };

const legendFormatter = (v: string) => (
  <span style={{ color: "#a1a1aa", fontSize: 11 }}>{v}</span>
);

interface Props {
  annual:    ResearchTrends;
  quarterly: ResearchTrends;
  period?:   "annual" | "quarterly";
}

export default function FinancialTrends({ annual, quarterly, period = "annual" }: Props) {
  const trends = period === "quarterly" ? quarterly : annual;
  const { revenue, eps, free_cash_flow, margins, returns } = trends;

  const hasReturns = returns.some(r => r.roe != null || r.roa != null || r.roic != null);
  const chartClass = "bg-zinc-800/40 rounded-xl p-4";

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-5">

      {/* 1. Revenue + Growth */}
      <div className={chartClass}>
        <div className="text-xs font-semibold text-zinc-300 mb-3">Revenue + YoY Growth</div>
        <ResponsiveContainer width="100%" height={240}>
          <ComposedChart data={revenue} margin={{ top: 4, right: 48, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
            <XAxis dataKey="period" tick={AXIS_TICK} axisLine={false} tickLine={false} />
            <YAxis yAxisId="left" tick={AXIS_TICK} axisLine={false} tickLine={false} tickFormatter={fmtB} width={60} />
            <YAxis yAxisId="right" orientation="right" tick={AXIS_TICK} axisLine={false} tickLine={false}
              tickFormatter={(v: number) => `${v.toFixed(0)}%`} width={48} />
            <Tooltip contentStyle={TT_STYLE} formatter={(v: unknown, name: unknown) => {
              if (name === "Revenue") return [fmtB(Number(v)), name];
              if (name === "YoY Growth") return [`${Number(v).toFixed(1)}%`, name];
              return [String(v), String(name)];
            }} />
            <Legend iconType="circle" iconSize={8} formatter={legendFormatter} />
            <Bar yAxisId="left" dataKey="value" name="Revenue" fill="#3b82f650" stroke="#3b82f6" strokeWidth={1} radius={[4,4,0,0]} />
            <Line yAxisId="right" type="monotone" dataKey="growth" name="YoY Growth" stroke="#f59e0b" strokeWidth={2} dot={false} connectNulls />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* 2. EPS + Growth */}
      <div className={chartClass}>
        <div className="text-xs font-semibold text-zinc-300 mb-3">EPS (Diluted) + YoY Growth</div>
        <ResponsiveContainer width="100%" height={240}>
          <ComposedChart data={eps} margin={{ top: 4, right: 48, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
            <XAxis dataKey="period" tick={AXIS_TICK} axisLine={false} tickLine={false} />
            <YAxis yAxisId="left" tick={AXIS_TICK} axisLine={false} tickLine={false}
              tickFormatter={(v: number) => `$${v.toFixed(2)}`} width={60} />
            <YAxis yAxisId="right" orientation="right" tick={AXIS_TICK} axisLine={false} tickLine={false}
              tickFormatter={(v: number) => `${v.toFixed(0)}%`} width={48} />
            <Tooltip contentStyle={TT_STYLE} formatter={(v: unknown, name: unknown) => {
              if (name === "EPS") return [`$${Number(v).toFixed(2)}`, name];
              if (name === "YoY Growth") return [`${Number(v).toFixed(1)}%`, name];
              return [String(v), String(name)];
            }} />
            <Legend iconType="circle" iconSize={8} formatter={legendFormatter} />
            <ReferenceLine yAxisId="left" y={0} stroke="#52525b" />
            <Bar yAxisId="left" dataKey="value" name="EPS" fill="#8b5cf650" stroke="#8b5cf6" strokeWidth={1} radius={[4,4,0,0]} />
            <Line yAxisId="right" type="monotone" dataKey="growth" name="YoY Growth" stroke="#f59e0b" strokeWidth={2} dot={false} connectNulls />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* 3. Free Cash Flow + Growth */}
      <div className={chartClass}>
        <div className="text-xs font-semibold text-zinc-300 mb-3">Free Cash Flow + YoY Growth</div>
        <ResponsiveContainer width="100%" height={240}>
          <ComposedChart data={free_cash_flow} margin={{ top: 4, right: 48, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
            <XAxis dataKey="period" tick={AXIS_TICK} axisLine={false} tickLine={false} />
            <YAxis yAxisId="left" tick={AXIS_TICK} axisLine={false} tickLine={false} tickFormatter={fmtB} width={60} />
            <YAxis yAxisId="right" orientation="right" tick={AXIS_TICK} axisLine={false} tickLine={false}
              tickFormatter={(v: number) => `${v.toFixed(0)}%`} width={48} />
            <Tooltip contentStyle={TT_STYLE} formatter={(v: unknown, name: unknown) => {
              if (name === "FCF") return [fmtB(Number(v)), name];
              if (name === "YoY Growth") return [`${Number(v).toFixed(1)}%`, name];
              return [String(v), String(name)];
            }} />
            <Legend iconType="circle" iconSize={8} formatter={legendFormatter} />
            <ReferenceLine yAxisId="left" y={0} stroke="#52525b" />
            <Bar yAxisId="left" dataKey="value" name="FCF" fill="#10b98150" stroke="#10b981" strokeWidth={1} radius={[4,4,0,0]} />
            <Line yAxisId="right" type="monotone" dataKey="growth" name="YoY Growth" stroke="#f59e0b" strokeWidth={2} dot={false} connectNulls />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* 4. Profit Margins */}
      <div className={chartClass}>
        <div className="text-xs font-semibold text-zinc-300 mb-3">Profit Margins (%)</div>
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={margins} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
            <XAxis dataKey="period" tick={AXIS_TICK} axisLine={false} tickLine={false} />
            <YAxis tick={AXIS_TICK} axisLine={false} tickLine={false}
              tickFormatter={(v: number) => `${v.toFixed(0)}%`} width={50} />
            <Tooltip contentStyle={TT_STYLE} formatter={(v: unknown) => [`${Number(v).toFixed(1)}%`]} />
            <Legend iconType="circle" iconSize={8} formatter={legendFormatter} />
            <Line type="monotone" dataKey="gross"     name="Gross"     stroke="#3b82f6" dot={false} strokeWidth={2} connectNulls />
            <Line type="monotone" dataKey="operating" name="Operating" stroke="#8b5cf6" dot={false} strokeWidth={2} connectNulls />
            <Line type="monotone" dataKey="net"       name="Net"       stroke="#10b981" dot={false} strokeWidth={2} connectNulls />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* 5. Return Metrics */}
      <div className={chartClass}>
        <div className="text-xs font-semibold text-zinc-300 mb-3">Return Metrics (ROE &amp; ROA)</div>
        {!hasReturns ? (
          <div className="flex items-center justify-center h-[240px] text-zinc-500 text-sm">
            Return metrics unavailable for this period
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={240}>
            <ComposedChart data={returns} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
              <XAxis dataKey="period" tick={AXIS_TICK} axisLine={false} tickLine={false} />
              <YAxis tick={AXIS_TICK} axisLine={false} tickLine={false}
                tickFormatter={(v: number) => `${v.toFixed(0)}%`} width={50} />
              <Tooltip contentStyle={TT_STYLE}
                formatter={(v: unknown, name: unknown) => [`${Number(v).toFixed(1)}%`, String(name)]} />
              <Legend iconType="circle" iconSize={8} formatter={legendFormatter} />
              <ReferenceLine y={0} stroke="#52525b" />
              <Line type="monotone" dataKey="roe"  name="ROE"  stroke="#f59e0b" strokeWidth={2} dot={false} connectNulls />
              <Line type="monotone" dataKey="roa"  name="ROA"  stroke="#06b6d4" strokeWidth={2} dot={false} connectNulls />
              <Line type="monotone" dataKey="roic" name="ROIC" stroke="#a78bfa" strokeWidth={2} dot={false} connectNulls />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </div>

    </div>
  );
}
