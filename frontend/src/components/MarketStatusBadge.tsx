"use client";
import { useMarketStatus } from "@/hooks/useMarketStatus";

const stateConfig: Record<string, { dot: string; bg: string; text: string }> = {
  open:         { dot: "bg-green-400 shadow-[0_0_6px_theme(colors.green.400)]", bg: "bg-green-950/50 border-green-800/50", text: "text-green-300" },
  pre_market:   { dot: "bg-yellow-400 shadow-[0_0_6px_theme(colors.yellow.400)]", bg: "bg-yellow-950/50 border-yellow-800/50", text: "text-yellow-300" },
  after_hours:  { dot: "bg-yellow-400 shadow-[0_0_6px_theme(colors.yellow.400)]", bg: "bg-yellow-950/50 border-yellow-800/50", text: "text-yellow-300" },
  closed:       { dot: "bg-red-400", bg: "bg-zinc-800/50 border-zinc-700/50", text: "text-zinc-400" },
};

export default function MarketStatusBadge() {
  const status = useMarketStatus();

  if (!status) {
    return (
      <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-zinc-800/50 border border-zinc-700/50 text-xs text-zinc-500">
        <span className="w-1.5 h-1.5 rounded-full bg-zinc-600" />
        Loading...
      </div>
    );
  }

  const cfg = stateConfig[status.state] || stateConfig.closed;

  return (
    <div
      className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium ${cfg.bg} ${cfg.text}`}
      title={`${status.label} · ${status.countdown} · ${status.timezone}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${cfg.dot}`} />
      <span className="hidden sm:inline">{status.label}</span>
      <span className="text-[10px] opacity-70">{status.countdown}</span>
    </div>
  );
}
