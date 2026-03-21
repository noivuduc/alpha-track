"use client";
import { AnalysisLayer as AnalysisLayerType, OverviewSynthesis } from "@/lib/api";

import SectionPanel        from "./SectionPanel";
import PillarsRow          from "./PillarsRow";
import RiskStrip           from "./RiskStrip";
import WhyNowCard          from "./WhyNowCard";
import SentimentRegimeCard from "./SentimentRegimeCard";
import TransparencyDrawer  from "./TransparencyDrawer";

export type SynthStatus = "idle" | "loading" | "ready" | "error";

interface Props {
  ticker:        string;
  analysisLayer: AnalysisLayerType;
  computedAt:    string;
  // Synthesis is fetched and managed by the parent (ResearchShell)
  // so it can be placed in the 2-column top layout.
  synthesis:     OverviewSynthesis | null;
  synthStatus:   SynthStatus;
  refreshing?:   boolean;
}

export default function AnalysisLayer({
  analysisLayer,
  computedAt,
  synthesis,
  synthStatus,
}: Props) {
  // Merge coverage: deterministic base + AI fresh_context flag
  const coverage = {
    ...analysisLayer.coverage,
    fresh_context_available: synthesis?.fresh_context_available ?? false,
  };

  const hasRiskFlags = analysisLayer.risk_flags.length > 0;

  return (
    <div className="space-y-4">
      {/* Investment Pillars — deterministic */}
      <SectionPanel title="Investment Pillars" id="sec-pillars">
        <PillarsRow pillars={analysisLayer.pillars} />
      </SectionPanel>

      {/* Risk Flags — only if present */}
      {hasRiskFlags && (
        <SectionPanel title="Risk Flags" id="sec-risk-flags">
          <RiskStrip flags={analysisLayer.risk_flags} />
        </SectionPanel>
      )}

      {/* Why Now / What Breaks / What Changed / News Relevance — only if AI synthesis ready */}
      {synthStatus === "ready" && synthesis?.available && (
        <WhyNowCard synthesis={synthesis} />
      )}

      {/* Sentiment Regime — always rendered; handles null score internally */}
      <SentimentRegimeCard regime={analysisLayer.sentiment_regime} />

      {/* Transparency Drawer */}
      <TransparencyDrawer
        synthesis={synthesis}
        coverage={coverage}
        computedAt={computedAt}
      />
    </div>
  );
}
