"use client";
import { useEffect, useState } from "react";
import { MarketStatus } from "@/lib/marketCalendar";

const stateConfig: Record<string, { dot: string; bg: string; text: string }> = {
  open:        { dot: "bg-green-400 shadow-[0_0_6px_theme(colors.green.400)]", bg: "bg-green-950/50 border-green-800/50", text: "text-green-300" },
  pre_market:  { dot: "bg-yellow-400 shadow-[0_0_6px_theme(colors.yellow.400)]", bg: "bg-yellow-950/50 border-yellow-800/50", text: "text-yellow-300" },
  after_hours: { dot: "bg-yellow-400 shadow-[0_0_6px_theme(colors.yellow.400)]", bg: "bg-yellow-950/50 border-yellow-800/50", text: "text-yellow-300" },
  closed:      { dot: "bg-red-400", bg: "bg-zinc-800/50 border-zinc-700/50", text: "text-zinc-400" },
};

function fmtCountdown(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s < 60)  return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60)  return `${m}m`;
  const h = Math.floor(m / 60);
  const rm = m % 60;
  if (h < 24)  return rm ? `${h}h ${rm}m` : `${h}h`;
  const d  = Math.floor(h / 24);
  const rh = h % 24;
  return rh ? `${d}d ${rh}h` : `${d}d`;
}

function useCountdown(nextChangeIso: string | undefined): string {
  const [text, setText] = useState("");

  useEffect(() => {
    if (!nextChangeIso) return;

    function update() {
      const ms = new Date(nextChangeIso!).getTime() - Date.now();
      setText(fmtCountdown(ms));
    }

    update();
    const id = setInterval(update, 30_000);
    return () => clearInterval(id);
  }, [nextChangeIso]);

  return text;
}

export default function MarketStatusBadge({ status }: { status: MarketStatus | null }) {
  const action    = status && (status.state === "closed" || status.state === "pre_market")
    ? "Opens in" : "Closes in";
  const countdown = useCountdown(status?.next_change);

  if (!status) {
    return (
      <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-zinc-800/50 border border-zinc-700/50 text-xs text-zinc-500">
        <span className="w-1.5 h-1.5 rounded-full bg-zinc-600" />
        <span>Market</span>
      </div>
    );
  }

  const cfg = stateConfig[status.state] ?? stateConfig.closed;

  return (
    <div
      className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium ${cfg.bg} ${cfg.text}`}
      title={`${status.label} · ${action} ${countdown} · ${status.timezone}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${cfg.dot}`} />
      <span className="hidden sm:inline">{status.label}</span>
      <span className="text-[10px] opacity-70">{action} {countdown}</span>
    </div>
  );
}
