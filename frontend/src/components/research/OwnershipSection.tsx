"use client";
import { InstitutionalOwner, InsiderTrade, CompanyProfile } from "@/lib/api";

function fmtLarge(n: number | undefined | null): string {
  if (n == null) return "—";
  if (Math.abs(n) >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  return `$${n.toLocaleString()}`;
}

function fmtShares(n: number | undefined | null): string {
  if (n == null) return "—";
  if (Math.abs(n) >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  if (Math.abs(n) >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
  return n.toLocaleString();
}

export default function OwnershipSection({
  ownership, insider_trades, profile,
}: { ownership: InstitutionalOwner[]; insider_trades: InsiderTrade[]; profile: CompanyProfile }) {

  const instPct    = profile.held_pct_institutions != null ? (profile.held_pct_institutions * 100).toFixed(1) + "%" : "—";
  const insiderPct = profile.held_pct_insiders     != null ? (profile.held_pct_insiders     * 100).toFixed(1) + "%" : "—";

  return (
    <div className="space-y-6">
      {/* Summary stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          ["Institutional Ownership", instPct],
          ["Insider Ownership",       insiderPct],
          ["Shares Outstanding",      fmtShares(profile.shares_outstanding)],
          ["Float",                   fmtShares(profile.float_shares)],
        ].map(([label, val]) => (
          <div key={label} className="bg-zinc-800/50 border border-zinc-700/40 rounded-xl p-4">
            <div className="text-xs text-zinc-500 mb-1">{label}</div>
            <div className="text-lg font-bold font-mono text-zinc-100">{val}</div>
          </div>
        ))}
      </div>

      {/* Institutional holders */}
      {ownership.length > 0 && (
        <div>
          <div className="text-xs font-semibold text-zinc-400 mb-2">Top Institutional Holders</div>
          <div className="overflow-x-auto scrollbar-thin">
            <table className="w-full text-xs min-w-[500px]">
              <thead>
                <tr className="border-b border-zinc-700">
                  {["Investor", "Shares", "Market Value", "Filed"].map(h => (
                    <th key={h} className={`py-2 font-medium text-zinc-500 ${h === "Investor" ? "text-left pr-4" : "text-right px-3"}`}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ownership.map((o, i) => (
                  <tr key={i} className="border-b border-zinc-800/50 hover:bg-zinc-800/30 transition-colors">
                    <td className="py-2 pr-4 text-zinc-200 font-medium">{o.investor}</td>
                    <td className="py-2 px-3 text-right font-mono tabular-nums text-zinc-400">{fmtShares(o.shares)}</td>
                    <td className="py-2 px-3 text-right font-mono tabular-nums text-zinc-300">{fmtLarge(o.market_value)}</td>
                    <td className="py-2 px-3 text-right text-zinc-500">{o.report_period?.slice(0, 10)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Insider transactions */}
      {insider_trades.length > 0 && (
        <div>
          <div className="text-xs font-semibold text-zinc-400 mb-2">Recent Insider Transactions</div>
          <div className="overflow-x-auto scrollbar-thin">
            <table className="w-full text-xs min-w-[640px]">
              <thead>
                <tr className="border-b border-zinc-700">
                  {["Name / Title", "Type", "Date", "Shares", "Price", "Value", "Owned After"].map(h => (
                    <th key={h} className={`py-2 font-medium text-zinc-500 ${h === "Name / Title" ? "text-left pr-4" : "text-right px-3"}`}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {insider_trades.slice(0, 20).map((t, i) => {
                  const isBuy = (t.transaction_shares ?? 0) > 0;
                  return (
                    <tr key={i} className="border-b border-zinc-800/50 hover:bg-zinc-800/30 transition-colors">
                      <td className="py-2 pr-4">
                        <div className="text-zinc-200 font-medium">{t.name}</div>
                        <div className="text-zinc-600">{t.title}</div>
                      </td>
                      <td className="py-2 px-3 text-right">
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${isBuy ? "bg-emerald-950 text-emerald-400" : "bg-red-950 text-red-400"}`}>
                          {isBuy ? "BUY" : "SELL"}
                        </span>
                      </td>
                      <td className="py-2 px-3 text-right text-zinc-500">{t.transaction_date?.slice(0, 10)}</td>
                      <td className={`py-2 px-3 text-right font-mono tabular-nums ${isBuy ? "text-emerald-400" : "text-red-400"}`}>
                        {isBuy ? "+" : ""}{fmtShares(t.transaction_shares)}
                      </td>
                      <td className="py-2 px-3 text-right font-mono tabular-nums text-zinc-400">
                        {t.transaction_price_per_share != null ? `$${t.transaction_price_per_share.toFixed(2)}` : "—"}
                      </td>
                      <td className="py-2 px-3 text-right font-mono tabular-nums text-zinc-300">{fmtLarge(Math.abs(t.transaction_value))}</td>
                      <td className="py-2 px-3 text-right font-mono tabular-nums text-zinc-500">{fmtShares(t.shares_owned_after_transaction)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
