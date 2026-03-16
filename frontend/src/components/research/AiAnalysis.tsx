"use client";
import { useState, useEffect, useCallback } from "react";
import { Sparkles, TrendingUp, TrendingDown, Rocket, AlertTriangle, DollarSign, RefreshCw } from "lucide-react";
import { researchApi, AiInsights, AiProvider } from "@/lib/api";

// ── Provider config ────────────────────────────────────────────────────────────
const PROVIDERS: { id: AiProvider; label: string; model: string; badge: string }[] = [
  { id: "anthropic", label: "Claude",  model: "claude-haiku-4-5",  badge: "bg-violet-500/20 text-violet-300 border-violet-500/30" },
  { id: "openai",    label: "GPT-4.1", model: "gpt-4.1-mini",      badge: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30" },
];

// ── Section config ─────────────────────────────────────────────────────────────
const SECTIONS = [
  { key: "strengths"  as const, label: "Strengths",      icon: TrendingUp,    color: "text-emerald-400", bg: "bg-emerald-950/30 border-emerald-800/30" },
  { key: "weaknesses" as const, label: "Weaknesses",     icon: TrendingDown,  color: "text-red-400",     bg: "bg-red-950/30 border-red-800/30"         },
  { key: "drivers"    as const, label: "Growth Drivers", icon: Rocket,        color: "text-blue-400",    bg: "bg-blue-950/30 border-blue-800/30"        },
  { key: "risks"      as const, label: "Key Risks",      icon: AlertTriangle, color: "text-amber-400",   bg: "bg-amber-950/30 border-amber-800/30"      },
] as const;

// ── Helpers ────────────────────────────────────────────────────────────────────
function fmtDate(iso: string): string {
  try { return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }); }
  catch { return iso; }
}

// ── Sub-components ─────────────────────────────────────────────────────────────
function BulletList({ items, color }: { items: string[]; color: string }) {
  if (!items.length) return <p className="text-xs text-zinc-600 italic">No data</p>;
  return (
    <ul className="space-y-2">
      {items.map((text, i) => (
        <li key={i} className="flex gap-2.5 items-start">
          <span className={`w-1.5 h-1.5 rounded-full mt-1.5 shrink-0 ${color.replace("text-", "bg-")}`} />
          <span className="text-xs text-zinc-300 leading-relaxed">{text}</span>
        </li>
      ))}
    </ul>
  );
}

function Skeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      <div className="h-4 bg-zinc-800 rounded w-3/4" />
      <div className="h-4 bg-zinc-800 rounded w-full" />
      <div className="h-4 bg-zinc-800 rounded w-5/6" />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="bg-zinc-800/50 rounded-xl p-4 space-y-2">
            <div className="h-3 bg-zinc-700 rounded w-1/3" />
            <div className="h-3 bg-zinc-700 rounded w-full" />
            <div className="h-3 bg-zinc-700 rounded w-4/5" />
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────
export default function AiAnalysis({ ticker }: { ticker: string }) {
  const [provider, setProvider] = useState<AiProvider>("anthropic");
  const [data,     setData]     = useState<Partial<Record<AiProvider, AiInsights>>>({});
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState<string | null>(null);

  const load = useCallback(async (p: AiProvider, force = false) => {
    setLoading(true);
    setError(null);
    try {
      const result = await researchApi.aiInsights(ticker, p, force);
      setData(prev => ({ ...prev, [p]: result }));
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to load AI analysis";
      setError(msg.includes("404") || msg.includes("cached")
        ? "Analysis unavailable — please reload the research page first."
        : msg);
    } finally {
      setLoading(false);
    }
  }, [ticker]);

  // Load current provider on mount and whenever provider switches
  useEffect(() => {
    if (!data[provider]) load(provider);
    else setLoading(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provider]);

  // Initial load
  useEffect(() => { load("anthropic"); }, [load]);

  const current = data[provider];

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="space-y-4">

      {/* ── Controls bar ──────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-3">

        {/* Provider toggle */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-zinc-500">Model</span>
          <div className="flex gap-0.5 bg-zinc-800 rounded-lg p-0.5">
            {PROVIDERS.map(pv => (
              <button
                key={pv.id}
                onClick={() => setProvider(pv.id)}
                className={`flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                  provider === pv.id
                    ? "bg-zinc-600 text-zinc-100"
                    : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                {pv.label}
                <span className={`hidden sm:inline text-[10px] px-1.5 py-0.5 rounded border font-mono ${pv.badge}`}>
                  {pv.model}
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* Metadata + refresh */}
        {current && (
          <div className="flex items-center gap-3 text-[11px] text-zinc-600">
            {current.generated_at && <span>Generated {fmtDate(current.generated_at)}</span>}
            {current._source === "cache" && <span className="text-zinc-700">· cached</span>}
            <button
              onClick={() => load(provider, true)}
              title="Force regenerate"
              className="flex items-center gap-1 text-zinc-600 hover:text-zinc-400 transition-colors"
            >
              <RefreshCw size={11} /> Refresh
            </button>
          </div>
        )}
      </div>

      {/* ── Disclaimer ─────────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 text-xs text-zinc-500 bg-zinc-800/40 rounded-lg px-3 py-2 border border-zinc-700/40">
        <Sparkles size={12} className="text-blue-400 shrink-0" />
        AI-generated analysis — not investment advice. Verify independently.
      </div>

      {/* ── Content ────────────────────────────────────────────────────────────── */}
      {loading ? (
        <Skeleton />
      ) : error ? (
        <div className="flex flex-col items-center gap-3 py-8 text-center">
          <p className="text-sm text-zinc-500">{error}</p>
          <button
            onClick={() => load(provider)}
            className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1.5"
          >
            <RefreshCw size={12} /> Retry
          </button>
        </div>
      ) : current ? (
        <>
          {/* Executive summary */}
          {current.summary && (
            <div className="bg-zinc-800/40 border border-zinc-700/40 rounded-xl p-4">
              <div className="flex items-center gap-2 mb-2">
                <Sparkles size={13} className="text-blue-400" />
                <span className="text-xs font-semibold text-zinc-300">Executive Summary</span>
              </div>
              <p className="text-sm text-zinc-300 leading-relaxed">{current.summary}</p>
            </div>
          )}

          {/* Four-quadrant grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {SECTIONS.map(({ key, label, icon: Icon, color, bg }) => (
              <div key={key} className={`rounded-xl border p-4 ${bg}`}>
                <div className={`flex items-center gap-2 mb-3 ${color}`}>
                  <Icon size={14} />
                  <span className="text-sm font-semibold text-zinc-200">{label}</span>
                </div>
                <BulletList items={current[key] ?? []} color={color} />
              </div>
            ))}
          </div>

          {/* Valuation view */}
          {current.valuation_view && (
            <div className="bg-zinc-800/30 border border-zinc-700/30 rounded-xl p-4 flex gap-3 items-start">
              <DollarSign size={14} className="text-zinc-400 mt-0.5 shrink-0" />
              <div>
                <div className="text-xs font-semibold text-zinc-400 mb-1">Valuation View</div>
                <p className="text-xs text-zinc-300 leading-relaxed">{current.valuation_view}</p>
              </div>
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}
