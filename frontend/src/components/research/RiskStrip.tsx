"use client";
import { RiskFlag } from "@/lib/api";

const SEV: Record<string, { dot: string; bg: string; text: string }> = {
  high:   { dot: "bg-red-500",    bg: "bg-red-950/40 border-red-900/60",    text: "text-red-400" },
  medium: { dot: "bg-amber-500",  bg: "bg-amber-950/40 border-amber-900/60", text: "text-amber-400" },
  low:    { dot: "bg-zinc-500",   bg: "bg-zinc-800/40 border-zinc-700/60",   text: "text-zinc-400" },
};

const CAT_LABELS: Record<string, string> = {
  valuation:     "Valuation",
  estimate:      "Estimates",
  macro:         "Macro / Leverage",
  earnings:      "Earnings",
  concentration: "Anomalies",
};

export default function RiskStrip({ flags }: { flags: RiskFlag[] }) {
  if (!flags.length) {
    return (
      <div className="text-xs text-zinc-600 py-2">
        No material risk flags computed from available data.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {flags.map((f, i) => {
        const sev = SEV[f.severity] ?? SEV.low;
        return (
          <div
            key={i}
            className={`flex items-start gap-3 rounded-lg border px-3 py-2.5 ${sev.bg}`}
          >
            <span className={`mt-1.5 w-2 h-2 rounded-full shrink-0 ${sev.dot}`} />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                <span className={`text-xs font-semibold ${sev.text}`}>{f.label}</span>
                <span className="text-[10px] text-zinc-600 uppercase tracking-wide">
                  {CAT_LABELS[f.category] ?? f.category}
                </span>
                <span className="text-[10px] text-zinc-700 ml-auto">{f.type}</span>
              </div>
              <p className="text-xs text-zinc-400 mt-0.5 leading-relaxed">{f.explanation}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
