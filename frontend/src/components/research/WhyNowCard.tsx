"use client";
import { OverviewSynthesis, NewsEnrichmentItem } from "@/lib/api";

const TAG_COLORS: Record<string, string> = {
  Earnings:   "text-blue-400 bg-blue-950/50 border-blue-900/60",
  Product:    "text-purple-400 bg-purple-950/50 border-purple-900/60",
  Regulation: "text-amber-400 bg-amber-950/50 border-amber-900/60",
  "M&A":      "text-pink-400 bg-pink-950/50 border-pink-900/60",
  Macro:      "text-zinc-400 bg-zinc-800/50 border-zinc-700/60",
  Guidance:   "text-cyan-400 bg-cyan-950/50 border-cyan-900/60",
};

function EnrichmentItem({ item }: { item: NewsEnrichmentItem }) {
  const tagStyle = TAG_COLORS[item.tag] ?? "text-zinc-400 bg-zinc-800/50 border-zinc-700/60";
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-start gap-2">
        <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded border shrink-0 mt-0.5 ${tagStyle}`}>
          {item.tag}
        </span>
        <span className="text-xs text-zinc-300 leading-snug">{item.headline}</span>
      </div>
      <p className="text-xs text-zinc-500 leading-relaxed ml-12">{item.why_it_matters}</p>
    </div>
  );
}

interface Props {
  synthesis: OverviewSynthesis;
}

export default function WhyNowCard({ synthesis }: Props) {
  const hasWhyNow        = synthesis.why_now.length > 0;
  const hasThesisBreakers = synthesis.thesis_breakers.length > 0;
  const hasWhatChanged   = synthesis.what_changed.length > 0;
  const hasEnrichment    = synthesis.news_enrichment.length > 0;

  if (!hasWhyNow && !hasThesisBreakers && !hasWhatChanged && !hasEnrichment) return null;

  return (
    <div className="space-y-4">
      {/* Why Now + Thesis Breakers */}
      {(hasWhyNow || hasThesisBreakers) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {hasWhyNow && (
            <div className="bg-zinc-900/60 border border-zinc-800/60 rounded-xl p-4 space-y-2">
              <div className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">Why Now</div>
              <ul className="space-y-1.5">
                {synthesis.why_now.map((item, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-zinc-300 leading-relaxed">
                    <span className="text-blue-500 shrink-0 mt-1">→</span>
                    {item}
                  </li>
                ))}
              </ul>
              <div className="text-[10px] text-zinc-700">Estimated</div>
            </div>
          )}

          {hasThesisBreakers && (
            <div className="bg-zinc-900/60 border border-zinc-800/60 rounded-xl p-4 space-y-2">
              <div className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">What Breaks the Thesis</div>
              <ul className="space-y-1.5">
                {synthesis.thesis_breakers.map((item, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-zinc-300 leading-relaxed">
                    <span className="text-red-500 shrink-0 mt-1">⚠</span>
                    {item}
                  </li>
                ))}
              </ul>
              <div className="text-[10px] text-zinc-700">Estimated</div>
            </div>
          )}
        </div>
      )}

      {/* What Changed */}
      {hasWhatChanged && (
        <div className="bg-zinc-900/60 border border-zinc-800/60 rounded-xl p-4 space-y-2">
          <div className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">What Changed</div>
          <ul className="space-y-1.5">
            {synthesis.what_changed.map((item, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-zinc-300 leading-relaxed">
                <span className="text-amber-500 shrink-0 mt-1">△</span>
                {item}
              </li>
            ))}
          </ul>
          <div className="text-[10px] text-zinc-700">Estimated</div>
        </div>
      )}

      {/* News enrichment */}
      {hasEnrichment && (
        <div className="bg-zinc-900/60 border border-zinc-800/60 rounded-xl p-4 space-y-3">
          <div className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">
            News Relevance
          </div>
          <div className="space-y-3 divide-y divide-zinc-800/40">
            {synthesis.news_enrichment.map((item, i) => (
              <div key={i} className={i > 0 ? "pt-3" : ""}>
                <EnrichmentItem item={item} />
              </div>
            ))}
          </div>
          <div className="text-[10px] text-zinc-700">Estimated — AI-generated context. Verify independently.</div>
        </div>
      )}
    </div>
  );
}
