"use client";
import { AnalystEstimate } from "@/lib/api";

function fmtLarge(n: number | undefined | null): string {
  if (n == null) return "—";
  if (Math.abs(n) >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  return `$${n.toLocaleString()}`;
}

export default function EstimatesSection({
  annual, quarterly,
}: { annual: AnalystEstimate[]; quarterly: AnalystEstimate[] }) {

  function renderTable(rows: AnalystEstimate[]) {
    if (!rows.length) return <div className="text-xs text-zinc-500 py-4">No estimate data available</div>;
    return (
      <div className="overflow-x-auto scrollbar-thin">
        <table className="w-full text-xs min-w-[400px]">
          <thead>
            <tr className="border-b border-zinc-700">
              {["Period", "Revenue Estimate", "EPS Estimate"].map(h => (
                <th key={h} className={`py-2 font-medium text-zinc-500 ${h === "Period" ? "text-left pr-4" : "text-right px-3"}`}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-b border-zinc-800/50 hover:bg-zinc-800/30 transition-colors">
                <td className="py-2 pr-4 text-zinc-300 font-mono">{r.fiscal_period}</td>
                <td className="py-2 px-3 text-right font-mono tabular-nums text-zinc-200">{fmtLarge(r.revenue)}</td>
                <td className="py-2 px-3 text-right font-mono tabular-nums text-emerald-400">
                  {r.earnings_per_share != null ? `$${r.earnings_per_share.toFixed(2)}` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div>
        <div className="text-xs font-semibold text-zinc-400 mb-3">Annual Estimates</div>
        {renderTable(annual)}
      </div>
      <div>
        <div className="text-xs font-semibold text-zinc-400 mb-3">Quarterly Estimates</div>
        {renderTable(quarterly)}
      </div>
    </div>
  );
}
