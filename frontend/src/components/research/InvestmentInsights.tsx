"use client";
import { TrendingUp, TrendingDown, Zap, AlertTriangle } from "lucide-react";
import { ResearchInsights, InsightItem } from "@/lib/api";

function InsightList({
  items,
  color,
}: {
  items: InsightItem[];
  color: "green" | "red" | "amber" | "blue";
}) {
  const dot = {
    green: "bg-emerald-500",
    red:   "bg-red-500",
    amber: "bg-amber-500",
    blue:  "bg-blue-500",
  }[color];
  const text = {
    green: "text-zinc-300",
    red:   "text-zinc-300",
    amber: "text-zinc-300",
    blue:  "text-zinc-300",
  }[color];

  if (!items.length) {
    return <p className="text-xs text-zinc-600 italic">Insufficient data</p>;
  }
  return (
    <ul className="space-y-2">
      {items.map((item, i) => (
        <li key={i} className="flex gap-2.5 items-start">
          <span className={`w-1.5 h-1.5 rounded-full mt-1.5 shrink-0 ${dot} ${item.strength === "weak" ? "opacity-50" : ""}`} />
          <span className={`text-xs leading-relaxed ${text} ${item.strength === "weak" ? "opacity-60" : ""}`}>
            {item.text}
          </span>
        </li>
      ))}
    </ul>
  );
}

const SECTIONS = [
  { key: "bull",      label: "Bull Case",     icon: TrendingUp,    color: "green" as const, bg: "bg-emerald-950/30 border-emerald-800/30" },
  { key: "bear",      label: "Bear Case",     icon: TrendingDown,  color: "red"   as const, bg: "bg-red-950/30 border-red-800/30"         },
  { key: "catalysts", label: "Key Catalysts", icon: Zap,           color: "amber" as const, bg: "bg-amber-950/30 border-amber-800/30"      },
  { key: "risks",     label: "Key Risks",     icon: AlertTriangle, color: "blue"  as const, bg: "bg-zinc-800/40 border-zinc-700/40"        },
] as const;

export default function InvestmentInsights({
  insights,
  sections = ["bull", "bear", "catalysts", "risks"],
}: {
  insights: ResearchInsights;
  sections?: ("bull" | "bear" | "catalysts" | "risks")[];
}) {
  const iconColor = {
    green: "text-emerald-400",
    red:   "text-red-400",
    amber: "text-amber-400",
    blue:  "text-blue-400",
  };

  const visibleSections = SECTIONS.filter((s) => sections.includes(s.key));
  const gridCols = visibleSections.length <= 2
    ? "grid-cols-1 md:grid-cols-2"
    : "grid-cols-1 md:grid-cols-2";

  return (
    <div className="space-y-4">
      <div className="text-xs text-zinc-500 bg-zinc-800/40 rounded-lg px-3 py-2 border border-zinc-700/40">
        ⚠ These insights are algorithmically generated from financial data and should not be considered investment advice.
      </div>
      <div className={`grid ${gridCols} gap-4`}>
        {visibleSections.map(({ key, label, icon: Icon, color, bg }) => (
          <div key={key} className={`rounded-xl border p-4 ${bg}`}>
            <div className={`flex items-center gap-2 mb-3 ${iconColor[color]}`}>
              <Icon size={15} />
              <span className="text-sm font-semibold">{label}</span>
            </div>
            <InsightList items={insights[key]} color={color} />
          </div>
        ))}
      </div>
    </div>
  );
}
