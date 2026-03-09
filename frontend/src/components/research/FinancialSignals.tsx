"use client";
import { FinancialAnomaly } from "@/lib/api";

function SignalCard({ anomaly: a }: { anomaly: FinancialAnomaly }) {
  // Severity styles
  const sev = {
    high:   { border: "border-red-800/50",    bg: "bg-red-950/30",    badge: "bg-red-500/20 text-red-400",    dot: "bg-red-500",    label: "High" },
    medium: { border: "border-amber-800/50",  bg: "bg-amber-950/20",  badge: "bg-amber-500/20 text-amber-400", dot: "bg-amber-500",  label: "Medium" },
    low:    { border: "border-zinc-700/50",   bg: "bg-zinc-800/40",   badge: "bg-zinc-700/60 text-zinc-400",  dot: "bg-zinc-400",   label: "Low" },
  }[a.severity];

  // Category icon label
  const catIcon: Record<string, string> = {
    revenue: "📈", margins: "📊", profitability: "💰", cashflow: "💵", debt: "🏦", working_capital: "⚙️",
  };

  return (
    <div className={`rounded-xl border p-4 ${sev.bg} ${sev.border}`}>
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full shrink-0 mt-0.5 ${sev.dot}`} />
          <span className="text-sm font-semibold text-zinc-200">{a.title}</span>
        </div>
        <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded shrink-0 ${sev.badge}`}>{sev.label}</span>
      </div>
      <p className="text-xs text-zinc-400 leading-relaxed ml-4">{a.description}</p>
      {a.metric_before != null && a.metric_after != null && (
        <div className="flex items-center gap-2 ml-4 mt-2">
          <span className="text-xs font-mono text-zinc-400">{a.metric_before}{a.metric_unit}</span>
          <span className="text-xs text-zinc-600">→</span>
          <span className={`text-xs font-mono font-semibold ${
            a.severity === "low" && a.metric_after > a.metric_before ? "text-emerald-400" :
            a.severity !== "low" && a.metric_after < a.metric_before ? "text-red-400" :
            a.metric_after < a.metric_before ? "text-red-400" : "text-emerald-400"
          }`}>{a.metric_after}{a.metric_unit}</span>
          <a href={`#${a.section_id}`}
             className="ml-auto text-[10px] text-blue-400 hover:text-blue-300 transition-colors">
            View →
          </a>
        </div>
      )}
    </div>
  );
}

export default function FinancialSignals({ anomalies }: { anomalies: FinancialAnomaly[] }) {
  if (!anomalies.length) {
    return (
      <div className="flex items-center gap-3 text-sm text-zinc-500 py-4">
        <span>✓</span>
        <span>No unusual financial signals detected in recent periods.</span>
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <div className="text-xs text-zinc-500 mb-4">
        Signals are auto-detected from year-over-year changes in financial statements. Always verify with primary data.
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {anomalies.map(a => <SignalCard key={a.id} anomaly={a} />)}
      </div>
    </div>
  );
}
