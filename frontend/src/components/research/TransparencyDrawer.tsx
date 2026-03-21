"use client";
import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { OverviewSynthesis, DataCoverage } from "@/lib/api";

interface Props {
  synthesis?:    OverviewSynthesis | null;
  coverage?:     DataCoverage | null;
  computedAt?:   string;
}

function Row({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className="flex items-start justify-between gap-4 py-1.5 border-b border-zinc-800/40 last:border-0">
      <span className="text-xs text-zinc-500 shrink-0 w-40">{label}</span>
      <span className="text-xs text-zinc-400 text-right">{value ?? "—"}</span>
    </div>
  );
}

function fmt(iso: string | null | undefined): string {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}

export default function TransparencyDrawer({ synthesis, coverage, computedAt }: Props) {
  const [open, setOpen] = useState(false);

  return (
    <div className="border border-zinc-800/60 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between px-4 py-3 text-xs text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/30 transition-colors"
      >
        <span className="font-medium">Data Transparency</span>
        {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-4">
          {/* Source labeling */}
          <div>
            <div className="text-[10px] font-semibold text-zinc-600 uppercase tracking-wider mb-2">Source Types</div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-[11px]">
              <div className="bg-zinc-800/40 rounded-lg px-2.5 py-2">
                <div className="font-semibold text-zinc-300 mb-0.5">Measured</div>
                <div className="text-zinc-500">Live prices, raw financials, API data</div>
              </div>
              <div className="bg-zinc-800/40 rounded-lg px-2.5 py-2">
                <div className="font-semibold text-zinc-300 mb-0.5">Computed</div>
                <div className="text-zinc-500">Pillars, risk flags, sentiment regime — deterministic rules</div>
              </div>
              <div className="bg-zinc-800/40 rounded-lg px-2.5 py-2">
                <div className="font-semibold text-zinc-300 mb-0.5">Estimated</div>
                <div className="text-zinc-500">AI narrative — synthesised from above, not independently verified</div>
              </div>
            </div>
          </div>

          {/* Data timestamps */}
          <div>
            <div className="text-[10px] font-semibold text-zinc-600 uppercase tracking-wider mb-1">Timestamps</div>
            <Row label="Research assembled"   value={fmt(computedAt)} />
            <Row label="AI synthesis"         value={fmt(synthesis?.generated_at)} />
            <Row label="Web retrieval (Tavily)" value={fmt(synthesis?.tavily_retrieved_at)} />
          </div>

          {/* Data coverage */}
          {coverage && (
            <div>
              <div className="text-[10px] font-semibold text-zinc-600 uppercase tracking-wider mb-1">Data Coverage</div>
              <Row label="Quote"           value={coverage.quote_available ? "Available" : "Unavailable"} />
              <Row label="Fundamentals"    value={coverage.fundamentals_available} />
              <Row label="Estimates"       value={coverage.estimates_available} />
              <Row label="Fresh web context" value={coverage.fresh_context_available ? "Available" : "Unavailable"} />
            </div>
          )}

          {/* AI metadata */}
          {synthesis && (
            <div>
              <div className="text-[10px] font-semibold text-zinc-600 uppercase tracking-wider mb-1">AI Metadata</div>
              <Row label="Provider"      value={synthesis.provider} />
              <Row label="Model"         value={synthesis.model} />
              <Row label="Prompt version" value={synthesis.prompt_version} />
              <Row label="Source"        value={synthesis._source} />
            </div>
          )}

          {/* Data providers */}
          <div>
            <div className="text-[10px] font-semibold text-zinc-600 uppercase tracking-wider mb-1">Data Providers</div>
            <Row label="Market data"     value="yfinance (free tier)" />
            <Row label="Fundamentals"    value="financialdatasets.ai" />
            <Row label="Web retrieval"   value="Tavily" />
            <Row label="AI synthesis"    value="OpenAI" />
          </div>

          <p className="text-[10px] text-zinc-700 leading-relaxed">
            AlphaDesk is an analytical tool, not a financial advisor.
            Core metrics are backend-deterministic. AI narrative is illustrative and should not be the sole basis for investment decisions.
          </p>
        </div>
      )}
    </div>
  );
}
