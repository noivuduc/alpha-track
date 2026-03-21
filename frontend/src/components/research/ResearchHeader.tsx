"use client";
import { ExternalLink, RefreshCw } from "lucide-react";
import { ResearchData, PriceUpdate } from "@/lib/api";
import TickerLogo from "@/components/ui/TickerLogo";

function fmt(n: number | undefined | null, decimals = 2): string {
  if (n == null) return "—";
  return n.toFixed(decimals);
}

function fmtLargeNum(n: number | undefined | null): string {
  if (n == null) return "—";
  if (Math.abs(n) >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (Math.abs(n) >= 1e9)  return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6)  return `$${(n / 1e6).toFixed(2)}M`;
  return `$${n.toLocaleString()}`;
}

interface Props { data: ResearchData; livePrice?: PriceUpdate | null; onRefresh: () => void; refreshing: boolean; }

export default function ResearchHeader({ data, livePrice, onRefresh, refreshing }: Props) {
  const snap     = data.overview.snapshot;
  const company  = data.overview.company;
  const profile  = data.overview.profile;

  const isLive    = !!(livePrice && livePrice.price > 0);
  const price     = isLive ? livePrice.price       : snap.price;
  const change    = isLive ? livePrice.change       : snap.day_change;
  const changePct = isLive ? livePrice.change_pct   : snap.day_change_percent;
  const positive  = (change ?? 0) >= 0;

  return (
    <div className="bg-zinc-900 border-b border-zinc-800">
      <div className="px-4 sm:px-6 py-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          {/* Left: company identity */}
          <div>
            <div className="flex items-center gap-3 mb-1">
              <TickerLogo ticker={data.ticker} size={36} rounded="lg" />
              <div>
                <div className="flex items-center gap-2">
                  <h1 className="text-xl font-bold text-zinc-50">
                    {company.name || profile.description?.slice(0, 40) || data.ticker}
                  </h1>
                  {profile.website && (
                    <a href={profile.website} target="_blank" rel="noopener noreferrer"
                       className="text-zinc-600 hover:text-blue-400 transition-colors">
                      <ExternalLink size={14} />
                    </a>
                  )}
                </div>
                <div className="flex flex-wrap items-center gap-2 mt-0.5">
                  <span className="font-mono text-blue-400 font-semibold text-sm">{data.ticker}</span>
                  {company.exchange && (
                    <span className="text-xs text-zinc-500 bg-zinc-800 px-2 py-0.5 rounded">{company.exchange}</span>
                  )}
                  {company.sector && (
                    <span className="text-xs text-zinc-500">{company.sector}</span>
                  )}
                  {company.industry && (
                    <span className="text-xs text-zinc-600">· {company.industry}</span>
                  )}
                </div>
              </div>
            </div>
            <div className="flex flex-wrap gap-4 text-xs text-zinc-500 mt-2 ml-12">
              {company.location && <span>📍 {company.location}</span>}
              {profile.employees && <span>👥 {profile.employees.toLocaleString()} employees</span>}
              {profile.country && !company.location && (
                <span>📍 {profile.city ? `${profile.city}, ` : ""}{profile.country}</span>
              )}
            </div>
          </div>

          {/* Right: price + quick stats + refresh */}
          <div className="flex flex-wrap gap-6 items-start">
            {/* Price block */}
            <div className="text-right">
              <div className="flex items-baseline gap-2 justify-end">
                <div className="text-3xl font-bold font-mono text-zinc-50">
                  ${fmt(price, 2)}
                </div>
                {isLive && (
                  <span className="flex items-center gap-1 text-[10px] text-emerald-500 font-medium">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_6px_theme(colors.emerald.400)] animate-pulse" />
                    LIVE
                  </span>
                )}
              </div>
              {change != null && (
                <div className={`text-sm font-mono mt-0.5 ${positive ? "text-emerald-400" : "text-red-400"}`}>
                  {positive ? "+" : ""}{fmt(change, 2)} ({positive ? "+" : ""}{fmt(changePct, 2)}%)
                </div>
              )}
              <div className="text-xs text-zinc-600 mt-1">
                {isLive
                  ? `Live · ${new Date(livePrice.fetched_at).toLocaleTimeString()}`
                  : snap.time ? new Date(snap.time).toLocaleString() : ""}
              </div>
            </div>

            {/* Quick stats */}
            <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs">
              {[
                ["Mkt Cap",    fmtLargeNum(profile.market_cap)],
                ["Ent. Value", fmtLargeNum(profile.enterprise_value)],
                ["52W High",   profile.week52_high  ? `$${fmt(profile.week52_high)}`  : "—"],
                ["52W Low",    profile.week52_low   ? `$${fmt(profile.week52_low)}`   : "—"],
                ["P/E",        fmt(profile.pe_ratio, 1)],
                ["Fwd P/E",    fmt(profile.forward_pe, 1)],
                ["Beta",       fmt(profile.beta, 2)],
                ["Avg Vol",    profile.avg_volume ? (profile.avg_volume / 1e6).toFixed(1) + "M" : "—"],
              ].map(([label, val]) => (
                <div key={label} className="flex items-center gap-2">
                  <span className="text-zinc-500 w-20 shrink-0">{label}</span>
                  <span className="text-zinc-200 font-mono tabular-nums">{val}</span>
                </div>
              ))}
            </div>

            {/* Refresh */}
            <button
              onClick={onRefresh}
              className="text-zinc-500 hover:text-zinc-300 p-1.5 rounded-lg hover:bg-zinc-800 transition-colors self-start"
              title="Force refresh data"
            >
              <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
