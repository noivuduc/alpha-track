"use client";
import {
  ComposedChart, Bar, Line, LineChart, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, Legend,
} from "recharts";
import { IncomeStatement, CashFlowStatement, BalanceSheet, CompanyProfile, MetricsHistory } from "@/lib/api";

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

/** Build a report_period → MetricsHistory map for O(1) lookups */
function buildMetricsMap(arr: MetricsHistory[]): Map<string, MetricsHistory> {
  const m = new Map<string, MetricsHistory>();
  for (const row of arr) m.set(row.report_period, row);
  return m;
}

/** Convert FD decimal (0.122) to chart-ready percent (12.2), null-safe */
function toChartPct(v: number | null | undefined): number | null {
  return v != null ? v * 100 : null;
}

const legendFormatter = (v: string) => (
  <span style={{ color: "#a1a1aa", fontSize: 11 }}>{v}</span>
);

interface Props {
  income: IncomeStatement[];
  cashflow: CashFlowStatement[];
  incomeQ?: IncomeStatement[];
  cashflowQ?: CashFlowStatement[];
  balance: BalanceSheet[];
  balanceQ?: BalanceSheet[];
  profile: CompanyProfile;
  period?: "annual" | "quarterly";
  metricsHistoryAnnual?: MetricsHistory[];
  metricsHistoryQuarterly?: MetricsHistory[];
}

export default function FinancialTrends({
  income,
  cashflow,
  incomeQ = [],
  cashflowQ = [],
  balance,
  balanceQ = [],
  period = "annual",
  metricsHistoryAnnual = [],
  metricsHistoryQuarterly = [],
}: Props) {
  const isQ = period === "quarterly";

  // Oldest → newest for chart order
  const inc   = [...(isQ ? incomeQ : income)].reverse();
  const cf    = [...(isQ ? cashflowQ : cashflow)].reverse();
  const mhMap = buildMetricsMap(isQ ? metricsHistoryQuarterly : metricsHistoryAnnual);

  const years = inc.map((r) => {
    if (!isQ) return r.report_period.slice(0, 4);
    const q = r.fiscal_period?.match(/Q\d/)?.[0] ?? "Q?";
    return `${q}'${r.report_period.slice(2, 4)}`;
  });

  const revs   = inc.map((r) => r.revenue ?? 0);
  const epsArr = inc.map((r) => r.earnings_per_share_diluted ?? r.earnings_per_share ?? 0);
  const fcfArr = cf.map((r)  => r.free_cash_flow ?? 0);

  const grossPct = inc.map((r) =>
    r.revenue && r.gross_profit != null ? (r.gross_profit / r.revenue) * 100 : null
  );
  const opPct = inc.map((r) =>
    r.revenue && r.operating_income != null ? (r.operating_income / r.revenue) * 100 : null
  );
  const netPct = inc.map((r) =>
    r.revenue && r.net_income != null ? (r.net_income / r.revenue) * 100 : null
  );

  // Growth lines from FD metrics-history (decimal → %, joined by report_period)
  const revGrowth = inc.map((r) => toChartPct(mhMap.get(r.report_period)?.revenue_growth));
  const epsGrowth = inc.map((r) => toChartPct(mhMap.get(r.report_period)?.earnings_per_share_growth));
  const fcfGrowth = inc.map((r) => toChartPct(mhMap.get(r.report_period)?.free_cash_flow_growth));

  // ROE / ROA from metrics history (more accurate than manual computation)
  const roeRoaData = years.map((y, i) => {
    const mh = mhMap.get(inc[i].report_period);
    return {
      year: y,
      roe: toChartPct(mh?.return_on_equity),
      roa: toChartPct(mh?.return_on_assets),
    };
  });

  const hasRoeData  = roeRoaData.some(d => d.roe != null || d.roa != null);

  const revenueData = years.map((y, i) => ({ year: y, revenue: revs[i], growth: revGrowth[i] }));
  const epsData     = years.map((y, i) => ({ year: y, eps: epsArr[i], growth: epsGrowth[i] }));
  const fcfData     = years.map((y, i) => ({ year: y, fcf: fcfArr[i], growth: fcfGrowth[i] }));
  const marginData  = years.map((y, i) => ({
    year: y, gross: grossPct[i], operating: opPct[i], net: netPct[i],
  }));

  const chartClass = "bg-zinc-800/40 rounded-xl p-4";

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-5">

      {/* 1. Revenue + Growth */}
      <div className={chartClass}>
        <div className="text-xs font-semibold text-zinc-300 mb-3">Revenue + YoY Growth</div>
        <ResponsiveContainer width="100%" height={240}>
          <ComposedChart data={revenueData} margin={{ top: 4, right: 48, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
            <XAxis dataKey="year" tick={AXIS_TICK} axisLine={false} tickLine={false} />
            <YAxis
              yAxisId="left"
              tick={AXIS_TICK}
              axisLine={false}
              tickLine={false}
              tickFormatter={fmtB}
              width={60}
            />
            <YAxis
              yAxisId="right"
              orientation="right"
              tick={AXIS_TICK}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v: number) => `${v.toFixed(0)}%`}
              width={48}
            />
            <Tooltip
              contentStyle={TT_STYLE}
              formatter={(v: unknown, name: unknown) => {
                if (name === "Revenue") return [fmtB(Number(v)), name];
                if (name === "YoY Growth") return [`${Number(v).toFixed(1)}%`, name];
                return [String(v), String(name)];
              }}
            />
            <Legend iconType="circle" iconSize={8} formatter={legendFormatter} />
            <Bar
              yAxisId="left"
              dataKey="revenue"
              name="Revenue"
              fill="#3b82f650"
              stroke="#3b82f6"
              strokeWidth={1}
              radius={[4, 4, 0, 0]}
            />
            <Line
              yAxisId="right"
              type="monotone"
              dataKey="growth"
              name="YoY Growth"
              stroke="#f59e0b"
              strokeWidth={2}
              dot={false}
              connectNulls
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* 2. EPS + Growth */}
      <div className={chartClass}>
        <div className="text-xs font-semibold text-zinc-300 mb-3">EPS (Diluted) + YoY Growth</div>
        <ResponsiveContainer width="100%" height={240}>
          <ComposedChart data={epsData} margin={{ top: 4, right: 48, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
            <XAxis dataKey="year" tick={AXIS_TICK} axisLine={false} tickLine={false} />
            <YAxis
              yAxisId="left"
              tick={AXIS_TICK}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v: number) => `$${v.toFixed(2)}`}
              width={60}
            />
            <YAxis
              yAxisId="right"
              orientation="right"
              tick={AXIS_TICK}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v: number) => `${v.toFixed(0)}%`}
              width={48}
            />
            <Tooltip
              contentStyle={TT_STYLE}
              formatter={(v: unknown, name: unknown) => {
                if (name === "EPS") return [`$${Number(v).toFixed(2)}`, name];
                if (name === "YoY Growth") return [`${Number(v).toFixed(1)}%`, name];
                return [String(v), String(name)];
              }}
            />
            <Legend iconType="circle" iconSize={8} formatter={legendFormatter} />
            <ReferenceLine yAxisId="left" y={0} stroke="#52525b" />
            <Bar
              yAxisId="left"
              dataKey="eps"
              name="EPS"
              fill="#8b5cf650"
              stroke="#8b5cf6"
              strokeWidth={1}
              radius={[4, 4, 0, 0]}
            />
            <Line
              yAxisId="right"
              type="monotone"
              dataKey="growth"
              name="YoY Growth"
              stroke="#f59e0b"
              strokeWidth={2}
              dot={false}
              connectNulls
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* 3. Free Cash Flow + Growth */}
      <div className={chartClass}>
        <div className="text-xs font-semibold text-zinc-300 mb-3">Free Cash Flow + YoY Growth</div>
        <ResponsiveContainer width="100%" height={240}>
          <ComposedChart data={fcfData} margin={{ top: 4, right: 48, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
            <XAxis dataKey="year" tick={AXIS_TICK} axisLine={false} tickLine={false} />
            <YAxis
              yAxisId="left"
              tick={AXIS_TICK}
              axisLine={false}
              tickLine={false}
              tickFormatter={fmtB}
              width={60}
            />
            <YAxis
              yAxisId="right"
              orientation="right"
              tick={AXIS_TICK}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v: number) => `${v.toFixed(0)}%`}
              width={48}
            />
            <Tooltip
              contentStyle={TT_STYLE}
              formatter={(v: unknown, name: unknown) => {
                if (name === "FCF") return [fmtB(Number(v)), name];
                if (name === "YoY Growth") return [`${Number(v).toFixed(1)}%`, name];
                return [String(v), String(name)];
              }}
            />
            <Legend iconType="circle" iconSize={8} formatter={legendFormatter} />
            <ReferenceLine yAxisId="left" y={0} stroke="#52525b" />
            <Bar
              yAxisId="left"
              dataKey="fcf"
              name="FCF"
              fill="#10b98150"
              stroke="#10b981"
              strokeWidth={1}
              radius={[4, 4, 0, 0]}
            />
            <Line
              yAxisId="right"
              type="monotone"
              dataKey="growth"
              name="YoY Growth"
              stroke="#f59e0b"
              strokeWidth={2}
              dot={false}
              connectNulls
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* 4. Profit Margins (lines only) */}
      <div className={chartClass}>
        <div className="text-xs font-semibold text-zinc-300 mb-3">Profit Margins (%)</div>
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={marginData} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
            <XAxis dataKey="year" tick={AXIS_TICK} axisLine={false} tickLine={false} />
            <YAxis
              tick={AXIS_TICK}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v: number) => `${v.toFixed(0)}%`}
              width={50}
            />
            <Tooltip
              contentStyle={TT_STYLE}
              formatter={(v: unknown) => [`${Number(v).toFixed(1)}%`]}
            />
            <Legend iconType="circle" iconSize={8} formatter={legendFormatter} />
            <Line type="monotone" dataKey="gross"     name="Gross"     stroke="#3b82f6" dot={false} strokeWidth={2} connectNulls />
            <Line type="monotone" dataKey="operating" name="Operating" stroke="#8b5cf6" dot={false} strokeWidth={2} connectNulls />
            <Line type="monotone" dataKey="net"       name="Net"       stroke="#10b981" dot={false} strokeWidth={2} connectNulls />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* 5. Return Metrics (ROE + ROA) */}
      <div className={chartClass}>
        <div className="text-xs font-semibold text-zinc-300 mb-3">Return Metrics (ROE &amp; ROA)</div>
        {!hasRoeData ? (
          <div className="flex items-center justify-center h-[240px] text-zinc-500 text-sm">
            Return metrics unavailable for this period
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={240}>
            <ComposedChart data={roeRoaData} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
              <XAxis dataKey="year" tick={AXIS_TICK} axisLine={false} tickLine={false} />
              <YAxis
                tick={AXIS_TICK}
                axisLine={false}
                tickLine={false}
                tickFormatter={(v: number) => `${v.toFixed(0)}%`}
                width={50}
              />
              <Tooltip
                contentStyle={TT_STYLE}
                formatter={(v: unknown, name: unknown) => [`${Number(v).toFixed(1)}%`, String(name)]}
              />
              <Legend iconType="circle" iconSize={8} formatter={legendFormatter} />
              <ReferenceLine y={0} stroke="#52525b" />
              <Line type="monotone" dataKey="roe" name="ROE" stroke="#f59e0b" strokeWidth={2} dot={false} connectNulls />
              <Line type="monotone" dataKey="roa" name="ROA" stroke="#06b6d4" strokeWidth={2} dot={false} connectNulls />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </div>

    </div>
  );
}
