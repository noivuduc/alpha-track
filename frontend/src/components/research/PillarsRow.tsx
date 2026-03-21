"use client";
import { AnalysisPillar } from "@/lib/api";

const STATUS_COLORS: Record<string, { bg: string; text: string; dot: string }> = {
  // Positive
  Attractive:   { bg: "bg-emerald-950/60", text: "text-emerald-400", dot: "bg-emerald-400" },
  Strong:       { bg: "bg-emerald-950/60", text: "text-emerald-400", dot: "bg-emerald-400" },
  Exceptional:  { bg: "bg-emerald-950/60", text: "text-emerald-400", dot: "bg-emerald-400" },
  Fortress:     { bg: "bg-emerald-950/60", text: "text-emerald-400", dot: "bg-emerald-400" },
  Low:          { bg: "bg-emerald-950/60", text: "text-emerald-400", dot: "bg-emerald-400" },
  Positive:     { bg: "bg-emerald-950/60", text: "text-emerald-400", dot: "bg-emerald-400" },
  // Neutral
  Fair:         { bg: "bg-zinc-800/60", text: "text-zinc-300", dot: "bg-zinc-400" },
  Healthy:      { bg: "bg-zinc-800/60", text: "text-zinc-300", dot: "bg-zinc-400" },
  Moderate:     { bg: "bg-zinc-800/60", text: "text-zinc-300", dot: "bg-zinc-400" },
  Adequate:     { bg: "bg-zinc-800/60", text: "text-zinc-300", dot: "bg-zinc-400" },
  Neutral:      { bg: "bg-zinc-800/60", text: "text-zinc-300", dot: "bg-zinc-400" },
  // Warning
  Stretched:    { bg: "bg-amber-950/50", text: "text-amber-400", dot: "bg-amber-400" },
  Slowing:      { bg: "bg-amber-950/50", text: "text-amber-400", dot: "bg-amber-400" },
  Elevated:     { bg: "bg-amber-950/50", text: "text-amber-400", dot: "bg-amber-400" },
  Moderate_risk:{ bg: "bg-amber-950/50", text: "text-amber-400", dot: "bg-amber-400" },
  Weak:         { bg: "bg-amber-950/50", text: "text-amber-400", dot: "bg-amber-400" },
  // Negative
  Expensive:    { bg: "bg-red-950/50",   text: "text-red-400",   dot: "bg-red-400" },
  Declining:    { bg: "bg-red-950/50",   text: "text-red-400",   dot: "bg-red-400" },
  Leveraged:    { bg: "bg-red-950/50",   text: "text-red-400",   dot: "bg-red-400" },
  High:         { bg: "bg-red-950/50",   text: "text-red-400",   dot: "bg-red-400" },
  Bearish:      { bg: "bg-red-950/50",   text: "text-red-400",   dot: "bg-red-400" },
  Thin:         { bg: "bg-red-950/50",   text: "text-red-400",   dot: "bg-red-400" },
  // N/A
  "N/A":        { bg: "bg-zinc-900/40",  text: "text-zinc-600",  dot: "bg-zinc-700" },
};

const KEY_LABELS: Record<string, string> = {
  valuation:    "Valuation",
  growth:       "Growth",
  profitability:"Profitability",
  balance_sheet:"Balance Sheet",
  risk:         "Risk",
  momentum:     "Momentum",
};

function ScoreBar({ score }: { score: number | null }) {
  if (score === null) return null;
  const color =
    score >= 70 ? "bg-emerald-500" :
    score >= 45 ? "bg-zinc-400" :
    score >= 25 ? "bg-amber-500" :
                  "bg-red-500";
  return (
    <div className="w-full h-1 bg-zinc-800 rounded-full mt-2">
      <div className={`h-1 rounded-full transition-all ${color}`} style={{ width: `${score}%` }} />
    </div>
  );
}

function PillarCard({ pillar }: { pillar: AnalysisPillar }) {
  const colors = STATUS_COLORS[pillar.label] ?? STATUS_COLORS["N/A"];
  return (
    <div className={`rounded-xl border border-zinc-800/60 p-3.5 flex flex-col gap-1.5 ${colors.bg}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">
          {KEY_LABELS[pillar.key] ?? pillar.key}
        </span>
        <span className={`flex items-center gap-1 text-xs font-semibold ${colors.text}`}>
          <span className={`w-1.5 h-1.5 rounded-full ${colors.dot}`} />
          {pillar.label}
        </span>
      </div>

      {pillar.primary_metric && pillar.primary_value !== "—" && (
        <div className="flex items-baseline gap-1.5">
          <span className="text-base font-semibold text-zinc-100">{pillar.primary_value}</span>
          <span className="text-xs text-zinc-500">{pillar.primary_metric}</span>
        </div>
      )}

      {pillar.secondary_metric && pillar.secondary_value && pillar.secondary_value !== "—" && (
        <div className="text-xs text-zinc-500">
          {pillar.secondary_metric}: <span className="text-zinc-400">{pillar.secondary_value}</span>
        </div>
      )}

      <ScoreBar score={pillar.score} />

      <p className="text-xs text-zinc-500 leading-relaxed mt-0.5 line-clamp-2">
        {pillar.explanation}
      </p>

      <div className="text-[10px] text-zinc-700 mt-auto pt-1">{pillar.type}</div>
    </div>
  );
}

export default function PillarsRow({ pillars }: { pillars: AnalysisPillar[] }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-3">
      {pillars.map(p => <PillarCard key={p.key} pillar={p} />)}
    </div>
  );
}
