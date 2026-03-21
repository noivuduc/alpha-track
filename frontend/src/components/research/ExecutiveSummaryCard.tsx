"use client";
import { OverviewSynthesis, DataCoverage } from "@/lib/api";
import { TrendingUp, TrendingDown, Minus, RefreshCw, HelpCircle } from "lucide-react";

const STANCE_STYLE: Record<string, { badge: string; icon: React.ElementType }> = {
  bullish:           { badge: "bg-emerald-950/80 text-emerald-300 border-emerald-800", icon: TrendingUp },
  neutral:           { badge: "bg-zinc-800/80 text-zinc-300 border-zinc-700",          icon: Minus },
  bearish:           { badge: "bg-red-950/80 text-red-300 border-red-900",             icon: TrendingDown },
  insufficient_data: { badge: "bg-zinc-900/60 text-zinc-500 border-zinc-800",          icon: Minus },
};

const STANCE_LABELS: Record<string, string> = {
  bullish:           "Constructive",
  neutral:           "Neutral",
  bearish:           "Cautious",
  insufficient_data: "Insufficient Data",
};

function CoverageChip({ available, label }: { available: boolean | string; label: string }) {
  const ok = available === true || available === "full";
  const partial = available === "partial";
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded border ${
      ok      ? "border-emerald-900/60 text-emerald-600 bg-emerald-950/30" :
      partial ? "border-amber-900/60 text-amber-600 bg-amber-950/30" :
                "border-zinc-800 text-zinc-600 bg-zinc-900/40"
    }`}>
      <span className={`w-1.5 h-1.5 rounded-full ${ok ? "bg-emerald-500" : partial ? "bg-amber-500" : "bg-zinc-700"}`} />
      {label}
    </span>
  );
}

interface Props {
  synthesis:   OverviewSynthesis;
  coverage:    DataCoverage;
  onRefresh?:  () => void;
  refreshing?: boolean;
}

export default function ExecutiveSummaryCard({ synthesis, coverage, onRefresh, refreshing }: Props) {
  const stance = synthesis.stance ?? "insufficient_data";
  const style  = STANCE_STYLE[stance] ?? STANCE_STYLE.insufficient_data;
  const Icon   = style.icon;

  return (
    <div className="bg-zinc-900/60 border border-zinc-800/60 rounded-xl p-4 space-y-3">
      {/* Header row */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2.5 flex-wrap">
          <span className={`inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-lg border ${style.badge}`}>
            <Icon size={12} />
            {STANCE_LABELS[stance]}
            {stance === "insufficient_data" && (
              <span
                className="relative group inline-flex items-center"
                title=""
              >
                <HelpCircle size={11} className="text-zinc-600 cursor-help" />
                <span className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 rounded-lg bg-zinc-800 border border-zinc-700 px-3 py-2 text-xs text-zinc-300 font-normal leading-relaxed shadow-xl opacity-0 group-hover:opacity-100 transition-opacity z-50">
                  The AI model received too little structured data to form a directional view.
                  This usually means fundamental data hasn&apos;t loaded yet — try refreshing, or check that the ticker has available financials.
                  <span className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-zinc-700" />
                </span>
              </span>
            )}
          </span>
          <span className="text-[10px] text-zinc-600">AI Summary · Estimated</span>
        </div>

        <div className="flex items-center gap-1.5 flex-wrap">
          <CoverageChip available={coverage.quote_available}        label="Quote" />
          <CoverageChip available={coverage.fundamentals_available} label="Fundamentals" />
          <CoverageChip available={coverage.estimates_available}    label="Estimates" />
          <CoverageChip available={coverage.fresh_context_available} label="Web context" />
        </div>
      </div>

      {/* Summary bullets */}
      {synthesis.summary_bullets.length > 0 ? (
        <ul className="space-y-1.5">
          {synthesis.summary_bullets.map((b, i) => (
            <li key={i} className="flex items-start gap-2 text-sm text-zinc-300 leading-relaxed">
              <span className="text-zinc-600 shrink-0 mt-1">·</span>
              {b}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-zinc-500 italic">AI summary unavailable right now.</p>
      )}

      {/* Confidence note + refresh */}
      <div className="flex items-center justify-between gap-2 pt-1 border-t border-zinc-800/60">
        {synthesis.confidence_note && (
          <p className="text-[11px] text-zinc-600 leading-relaxed">{synthesis.confidence_note}</p>
        )}
        {onRefresh && (
          <button
            onClick={onRefresh}
            disabled={refreshing}
            className="flex items-center gap-1.5 text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors shrink-0 disabled:opacity-40"
          >
            <RefreshCw size={11} className={refreshing ? "animate-spin" : ""} />
            Refresh
          </button>
        )}
      </div>
    </div>
  );
}
