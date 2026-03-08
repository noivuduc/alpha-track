"use client";
import dynamic from "next/dynamic";
import { TrendingUp, TrendingDown, DollarSign, BarChart2 } from "lucide-react";
import { Position, PortfolioAnalytics } from "@/lib/api";
import { fmtCurrency, fmtPct, gainClass } from "@/lib/portfolio-math";

const PerformanceChart = dynamic(() => import("@/components/charts/PerformanceChart"), { ssr: false });
const SectorDonut      = dynamic(() => import("@/components/charts/SectorDonut"),      { ssr: false });

interface Props {
  analytics: PortfolioAnalytics | null;
  positions: Position[];
  loading:   boolean;
  period:    string;
}

function StatCard({
  label, value, sub, positive, icon,
}: {
  label: string; value: string; sub?: string; positive?: boolean; icon: React.ReactNode;
}) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
      <div className="flex items-start justify-between mb-3">
        <span className="text-zinc-500 text-sm">{label}</span>
        <span className="text-zinc-600">{icon}</span>
      </div>
      <div className="text-2xl font-bold font-mono tabular-nums text-zinc-50">{value}</div>
      {sub && (
        <div className={`text-sm font-mono mt-1 ${
          positive == null ? "text-zinc-500" : positive ? "text-emerald-400" : "text-red-400"
        }`}>
          {sub}
        </div>
      )}
    </div>
  );
}

const PERIOD_MAP: Record<string, string> = {
  "1mo": "1M", "3mo": "3M", "6mo": "6M", "ytd": "YTD", "1y": "1Y", "2y": "2Y",
};

// Build sector breakdown from position weights (uses weight_pct from API)
function buildSectorData(positions: Position[]): { name: string; value: number }[] {
  // Positions don't carry sector yet — show per-ticker allocation as fallback
  const total = positions.reduce((s, p) => s + (p.weight_pct ?? 0), 0);
  if (!total) return positions.map(p => ({ name: p.ticker, value: p.weight_pct ?? 0 }));
  return positions.map(p => ({ name: p.ticker, value: p.weight_pct ?? 0 }));
}

export default function OverviewTab({ analytics, positions, loading, period }: Props) {
  const m = analytics;
  const dayPositive  = (m?.day_gain   ?? 0) >= 0;
  const gainPositive = (m?.total_gain ?? 0) >= 0;

  // Normalise performance points to only include present benchmarks
  const chartData = (m?.performance ?? []).map(p => ({
    date:      p.date,
    portfolio: p.portfolio,
    spy:       p.spy,
    qqq:       p.qqq,
  }));

  const sectorData = buildSectorData(positions);

  return (
    <div className="space-y-6">
      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Portfolio Value"
          value={fmtCurrency(m?.total_value)}
          icon={<DollarSign size={18} />}
        />
        <StatCard
          label="Total P&L"
          value={fmtCurrency(m?.total_gain)}
          sub={fmtPct(m?.total_gain_pct)}
          positive={gainPositive}
          icon={gainPositive ? <TrendingUp size={18} /> : <TrendingDown size={18} />}
        />
        <StatCard
          label="Day P&L"
          value={fmtCurrency(m?.day_gain)}
          sub={fmtPct(m?.day_gain_pct)}
          positive={dayPositive}
          icon={dayPositive ? <TrendingUp size={18} /> : <TrendingDown size={18} />}
        />
        <StatCard
          label="Holdings"
          value={String(positions.length)}
          icon={<BarChart2 size={18} />}
        />
      </div>

      {/* Performance chart — driven by backend analytics */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
        <div className="flex items-center justify-between mb-1">
          <h3 className="text-sm font-semibold text-zinc-300">Performance vs Benchmarks</h3>
          {m?.risk_metrics.annualized_return_pct != null && (
            <span className={`text-xs font-mono ${gainClass(m.risk_metrics.annualized_return_pct)}`}>
              Ann. return: {m.risk_metrics.annualized_return_pct >= 0 ? "+" : ""}
              {m.risk_metrics.annualized_return_pct.toFixed(2)}%
            </span>
          )}
        </div>

        {loading ? (
          <div className="h-64 flex items-center justify-center">
            <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : chartData.length > 1 ? (
          <PerformanceChart
            data={chartData}
            range={PERIOD_MAP[period] ?? period}
            onRangeChange={() => {}} // period is controlled from DashboardShell header
          />
        ) : (
          <div className="h-64 flex items-center justify-center text-zinc-500 text-sm">
            {positions.length ? "Computing performance…" : "Add positions to see chart"}
          </div>
        )}
      </div>

      {/* Sector donut + P&L bars */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
          <h3 className="text-sm font-semibold text-zinc-300 mb-3">Portfolio Allocation</h3>
          {sectorData.length ? (
            <SectorDonut data={sectorData} />
          ) : (
            <div className="h-40 flex items-center justify-center text-zinc-500 text-sm">
              No positions
            </div>
          )}
        </div>

        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
          <h3 className="text-sm font-semibold text-zinc-300 mb-4">Unrealized P&L by Position</h3>
          {positions.length ? (
            <div className="space-y-2.5">
              {Object.values(
                positions.reduce<Record<string, { ticker: string; gl: number; id: string }>>((acc, p) => {
                  const key = p.ticker;
                  if (acc[key]) acc[key].gl += p.gain_loss ?? 0;
                  else acc[key] = { ticker: p.ticker, gl: p.gain_loss ?? 0, id: p.id };
                  return acc;
                }, {})
              )
                .sort((a, b) => b.gl - a.gl)
                .slice(0, 10)
                .map(({ ticker, gl, id }) => {
                  const maxAbs = Math.max(...positions.map(x => Math.abs(x.gain_loss ?? 0)), 1);
                  const barW  = Math.min(Math.abs(gl) / maxAbs * 100, 100);
                  return (
                    <div key={id} className="flex items-center gap-3">
                      <span className="text-zinc-300 font-mono text-xs w-12 shrink-0">{ticker}</span>
                      <div className="flex-1 relative h-5 bg-zinc-800 rounded overflow-hidden">
                        <div
                          className={`h-full rounded ${gl >= 0 ? "bg-emerald-500/70" : "bg-red-500/70"}`}
                          style={{ width: `${barW}%` }}
                        />
                      </div>
                      <span className={`font-mono text-xs w-20 text-right tabular-nums ${gainClass(gl)}`}>
                        {gl >= 0 ? "+" : ""}{fmtCurrency(gl)}
                      </span>
                    </div>
                  );
                })}

            </div>
          ) : (
            <div className="h-40 flex items-center justify-center text-zinc-500 text-sm">No positions</div>
          )}
        </div>
      </div>
    </div>
  );
}
