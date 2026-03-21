"use client";
import { useState, useRef, useEffect } from "react";
import { ExternalLink, RefreshCw, ChevronDown } from "lucide-react";
import { ResearchData, PriceUpdate } from "@/lib/api";
import TickerLogo from "@/components/ui/TickerLogo";

function fmt(n: number | undefined | null, decimals = 2): string {
  if (n == null) return "—";
  return n.toFixed(decimals);
}

interface TabItem { key: string; label: string; }

interface Props {
  data:        ResearchData;
  livePrice?:  PriceUpdate | null;
  onRefresh:   () => void;
  refreshing:  boolean;
  tabs:        TabItem[];
  moreTabs:    TabItem[];
  activeTab:   string;
  onTabChange: (key: string) => void;
}

export default function ResearchHeader({
  data, livePrice, onRefresh, refreshing,
  tabs, moreTabs, activeTab, onTabChange,
}: Props) {
  const snap    = data.overview.snapshot;
  const company = data.overview.company;
  const profile = data.overview.profile;

  const [moreOpen, setMoreOpen] = useState(false);
  const moreRef = useRef<HTMLDivElement>(null);

  const isLive    = !!(livePrice && livePrice.price > 0);
  const price     = isLive ? livePrice.price     : snap.price;
  const change    = isLive ? livePrice.change     : snap.day_change;
  const changePct = isLive ? livePrice.change_pct : snap.day_change_percent;
  const positive  = (change ?? 0) >= 0;
  const moreActive = moreTabs.some(t => t.key === activeTab);

  // Close More dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (moreRef.current && !moreRef.current.contains(e.target as Node)) {
        setMoreOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div className="bg-zinc-900 border-b border-zinc-800">

      {/* ── ROW 1: Company identity + Price ────────────────────────── */}
      <div className="max-w-[1400px] mx-auto px-4 sm:px-6 py-3 flex items-center justify-between gap-6">

        {/* LEFT: Identity */}
        <div className="flex items-center gap-3 min-w-0">
          <TickerLogo ticker={data.ticker} size={36} rounded="lg" />
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-bold text-zinc-50 text-base leading-tight truncate">
                {company.name || data.ticker}
              </span>
              <span className="font-mono text-blue-400 font-semibold text-sm shrink-0">{data.ticker}</span>
              {profile.website && (
                <a href={profile.website} target="_blank" rel="noopener noreferrer"
                   className="text-zinc-600 hover:text-blue-400 transition-colors shrink-0">
                  <ExternalLink size={13} />
                </a>
              )}
            </div>
            <div className="flex items-center gap-1.5 mt-0.5 text-xs text-zinc-500">
              {company.exchange && <span>{company.exchange}</span>}
              {company.sector   && <><span className="text-zinc-700">·</span><span>{company.sector}</span></>}
              {company.industry && <><span className="text-zinc-700">·</span><span className="hidden sm:inline">{company.industry}</span></>}
              {(company.location || profile.country) && (
                <><span className="text-zinc-700">·</span>
                <span className="hidden md:inline">{company.location || profile.country}</span></>
              )}
              {profile.employees && (
                <><span className="text-zinc-700">·</span>
                <span className="hidden lg:inline">{profile.employees.toLocaleString()} emp.</span></>
              )}
            </div>
          </div>
        </div>

        {/* RIGHT: Price + refresh */}
        <div className="flex items-center gap-3 shrink-0">
          <div className="text-right">
            <div className="flex items-baseline gap-1.5 justify-end">
              <span className="text-2xl font-bold font-mono text-zinc-50 tabular-nums">
                ${fmt(price, 2)}
              </span>
              {isLive && (
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_6px_theme(colors.emerald.400)] animate-pulse" />
              )}
            </div>
            {change != null && (
              <div className={`text-sm font-mono tabular-nums leading-tight ${positive ? "text-emerald-400" : "text-red-400"}`}>
                {positive ? "+" : ""}{fmt(change, 2)} ({positive ? "+" : ""}{fmt(changePct, 2)}%)
              </div>
            )}
          </div>
          <button
            onClick={onRefresh}
            className="text-zinc-500 hover:text-zinc-300 p-1.5 rounded-lg hover:bg-zinc-800 transition-colors"
            title="Force refresh data"
          >
            <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {/* ── ROW 2: Tab navigation ───────────────────────────────────── */}
      <div className="border-t border-zinc-800/60 hidden lg:block">
        <div className="max-w-[1400px] mx-auto px-4 sm:px-6 flex items-center">

          {/* Primary tabs */}
          {tabs.map(tab => (
            <button
              key={tab.key}
              onClick={() => onTabChange(tab.key)}
              className={`px-4 py-3 text-sm font-medium whitespace-nowrap border-b-2 transition-colors ${
                activeTab === tab.key
                  ? "border-blue-500 text-blue-400"
                  : "border-transparent text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {tab.label}
            </button>
          ))}

          {/* More dropdown */}
          {moreTabs.length > 0 && (
            <div ref={moreRef} className="relative">
              <button
                onClick={() => setMoreOpen(o => !o)}
                className={`flex items-center gap-1 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                  moreActive
                    ? "border-blue-500 text-blue-400"
                    : "border-transparent text-zinc-500 hover:text-zinc-300"
                }`}
              >
                More
                <ChevronDown size={13} className={`transition-transform ${moreOpen ? "rotate-180" : ""}`} />
              </button>

              {moreOpen && (
                <div className="absolute top-full left-0 w-44 bg-zinc-900 border border-zinc-700 rounded-xl shadow-xl z-50 py-1 mt-px">
                  {moreTabs.map(tab => (
                    <button
                      key={tab.key}
                      onClick={() => { onTabChange(tab.key); setMoreOpen(false); }}
                      className={`w-full text-left px-4 py-2.5 text-sm transition-colors ${
                        activeTab === tab.key
                          ? "bg-blue-600/10 text-blue-400"
                          : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800"
                      }`}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

        </div>
      </div>

    </div>
  );
}
