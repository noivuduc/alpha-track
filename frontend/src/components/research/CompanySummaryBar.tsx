"use client";
import { useEffect, useState, RefObject } from "react";
import { ResearchData, PriceUpdate } from "@/lib/api";
import TickerLogo from "@/components/ui/TickerLogo";

function fmt(n: number | undefined | null, d = 2): string {
  if (n == null) return "—";
  return n.toFixed(d);
}
function fmtLarge(n: number | undefined | null): string {
  if (n == null) return "—";
  if (Math.abs(n) >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (Math.abs(n) >= 1e9)  return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6)  return `$${(n / 1e6).toFixed(1)}M`;
  return `$${n.toLocaleString()}`;
}

interface Props {
  data: ResearchData;
  livePrice?: PriceUpdate | null;
  sentinelRef: RefObject<HTMLDivElement | null>;
}

export default function CompanySummaryBar({ data, livePrice, sentinelRef }: Props) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([entry]) => setVisible(!entry.isIntersecting),
      { rootMargin: "-64px 0px 0px 0px" }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [sentinelRef]);

  if (!visible) return null;

  const snap     = data.overview.snapshot;
  const isLive   = !!(livePrice && livePrice.price > 0);
  const price    = isLive ? livePrice.price     : snap.price;
  const change   = isLive ? livePrice.change    : snap.day_change;
  const changePct = isLive ? livePrice.change_pct : snap.day_change_percent;
  const positive = (change ?? 0) >= 0;
  const revenue  = data.financials.income_ttm?.revenue;

  return (
    <div className="fixed top-16 left-0 right-0 z-40 bg-zinc-900/97 backdrop-blur-sm border-b border-zinc-800 shadow-lg">
      <div className="max-w-[1800px] mx-auto px-4 sm:px-6 py-2 flex items-center gap-4 text-xs overflow-x-auto scrollbar-none">
        {/* Identity */}
        <div className="flex items-center gap-2 shrink-0">
          <TickerLogo ticker={data.ticker} size={24} rounded="md" />
          <span className="font-mono font-semibold text-blue-400">{data.ticker}</span>
          <span className="text-zinc-400 hidden sm:block truncate max-w-[180px]">
            {data.overview.company.name}
          </span>
        </div>

        <div className="w-px h-4 bg-zinc-700 shrink-0" />

        {/* Price */}
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-zinc-100 font-mono font-semibold tabular-nums">
            ${fmt(price)}
          </span>
          {change != null && (
            <span className={`font-mono tabular-nums ${positive ? "text-emerald-400" : "text-red-400"}`}>
              {positive ? "+" : ""}{fmt(change)} ({positive ? "+" : ""}{fmt(changePct)}%)
            </span>
          )}
          {isLive && (
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_4px_theme(colors.emerald.400)] animate-pulse" />
          )}
        </div>

        {/* Key stats — hidden on small screens */}
        <div className="hidden md:flex items-center gap-5 text-zinc-400 shrink-0">
          {data.overview.profile.market_cap != null && (
            <span>Mkt Cap <span className="text-zinc-200 font-mono">{fmtLarge(data.overview.profile.market_cap)}</span></span>
          )}
          {data.overview.profile.pe_ratio != null && (
            <span>P/E <span className="text-zinc-200 font-mono">{fmt(data.overview.profile.pe_ratio, 1)}</span></span>
          )}
          {revenue != null && (
            <span>Rev TTM <span className="text-zinc-200 font-mono">{fmtLarge(revenue)}</span></span>
          )}
          {data.overview.profile.week52_high != null && (
            <span>52W H <span className="text-zinc-200 font-mono">${fmt(data.overview.profile.week52_high)}</span></span>
          )}
          {data.overview.profile.week52_low != null && (
            <span>52W L <span className="text-zinc-200 font-mono">${fmt(data.overview.profile.week52_low)}</span></span>
          )}
        </div>
      </div>
    </div>
  );
}
