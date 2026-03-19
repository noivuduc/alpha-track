"use client";
import { useState, useEffect, useCallback } from "react";
import { Sparkles, TrendingUp, TrendingDown, Rocket, AlertTriangle, DollarSign, RefreshCw } from "lucide-react";
import { researchApi, AiInsights } from "@/lib/api";

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

function modelLabel(provider: string | null, model: string | null): string {
  if (!provider || !model) return "";
  const names: Record<string, string> = { anthropic: "Claude", openai: "GPT" };
  return `${names[provider] ?? provider} · ${model}`;
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
  const [data,    setData]    = useState<AiInsights | null>(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);

  const load = useCallback(async (force = false) => {
    setLoading(true);
    setError(null);
    try {
      const result = await researchApi.aiInsights(ticker, force);
      setData(result);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to load AI analysis";
      setError(msg.includes("404") || msg.includes("cached")
        ? "Analysis unavailable — please reload the research page first."
        : msg);
    } finally {
      setLoading(false);
    }
  }, [ticker]);

  useEffect(() => { load(); }, [load]);

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="space-y-4">

      {/* ── Controls bar ──────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Sparkles size={14} className="text-blue-400" />
          <span className="text-sm font-semibold text-zinc-200">AI Analysis</span>
          {data?.provider && data?.model && (
            <span className="text-[10px] px-1.5 py-0.5 rounded border bg-zinc-800 text-zinc-400 border-zinc-700 font-mono">
              {modelLabel(data.provider, data.model)}
            </span>
          )}
        </div>

        {data?.available && (
          <div className="flex items-center gap-3 text-[11px] text-zinc-600">
            {data.generated_at && <span>Generated {fmtDate(data.generated_at)}</span>}
            {data._source === "cache" && <span className="text-zinc-700">· cached</span>}
            <button
              onClick={() => load(true)}
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
            onClick={() => load()}
            className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1.5"
          >
            <RefreshCw size={12} /> Retry
          </button>
        </div>
      ) : data && !data.available ? (
        <div className="flex flex-col items-center gap-2 py-10 text-center">
          <Sparkles size={20} className="text-zinc-600" />
          <p className="text-sm text-zinc-500">AI analysis is not available</p>
          <p className="text-xs text-zinc-600">No AI provider API key is configured on the server.</p>
        </div>
      ) : data ? (
        <>
          {/* Executive summary */}
          {data.summary && (
            <div className="bg-zinc-800/40 border border-zinc-700/40 rounded-xl p-4">
              <div className="flex items-center gap-2 mb-2">
                <Sparkles size={13} className="text-blue-400" />
                <span className="text-xs font-semibold text-zinc-300">Executive Summary</span>
              </div>
              <p className="text-sm text-zinc-300 leading-relaxed">{data.summary}</p>
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
                <BulletList items={data[key] ?? []} color={color} />
              </div>
            ))}
          </div>

          {/* Valuation view */}
          {data.valuation_view && (
            <div className="bg-zinc-800/30 border border-zinc-700/30 rounded-xl p-4 flex gap-3 items-start">
              <DollarSign size={14} className="text-zinc-400 mt-0.5 shrink-0" />
              <div>
                <div className="text-xs font-semibold text-zinc-400 mb-1">Valuation View</div>
                <p className="text-xs text-zinc-300 leading-relaxed">{data.valuation_view}</p>
              </div>
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}
