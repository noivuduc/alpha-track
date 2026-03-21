"use client";
import { ReactNode } from "react";

interface Props {
  title:   string;
  value:   string | number;
  sub?:    string;
  icon?:   ReactNode;
  color?:  "blue" | "green" | "amber" | "red" | "zinc";
  loading?: boolean;
}

const COLOR_MAP = {
  blue:  { bg: "bg-blue-500/10",  text: "text-blue-400",  border: "border-blue-500/20"  },
  green: { bg: "bg-emerald-500/10", text: "text-emerald-400", border: "border-emerald-500/20" },
  amber: { bg: "bg-amber-500/10", text: "text-amber-400", border: "border-amber-500/20" },
  red:   { bg: "bg-red-500/10",   text: "text-red-400",   border: "border-red-500/20"   },
  zinc:  { bg: "bg-zinc-800",     text: "text-zinc-400",  border: "border-zinc-700"     },
};

export default function StatCard({ title, value, sub, icon, color = "zinc", loading }: Props) {
  const c = COLOR_MAP[color];
  return (
    <div className={`rounded-xl border ${c.border} ${c.bg} p-4 flex flex-col gap-2`}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-zinc-500 uppercase tracking-wider">{title}</span>
        {icon && <span className={`${c.text} opacity-70`}>{icon}</span>}
      </div>
      {loading ? (
        <div className="h-7 w-24 bg-zinc-700 rounded animate-pulse" />
      ) : (
        <span className="text-2xl font-bold text-zinc-50 tabular-nums">{value}</span>
      )}
      {sub && <span className="text-xs text-zinc-500">{sub}</span>}
    </div>
  );
}
