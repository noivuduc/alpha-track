"use client";
import { useEffect, useState } from "react";
import { AnalysisLayer as AnalysisLayerType, OverviewSynthesis, researchApi } from "@/lib/api";

import SectionPanel      from "./SectionPanel";
import ExecutiveSummaryCard from "./ExecutiveSummaryCard";
import PillarsRow        from "./PillarsRow";
import RiskStrip         from "./RiskStrip";
import WhyNowCard        from "./WhyNowCard";
import SentimentRegimeCard from "./SentimentRegimeCard";
import TransparencyDrawer from "./TransparencyDrawer";

interface Props {
  ticker:        string;
  analysisLayer: AnalysisLayerType;
  computedAt:    string;
}

type SynthStatus = "idle" | "loading" | "ready" | "error";

export default function AnalysisLayer({ ticker, analysisLayer, computedAt }: Props) {
  const [synthesis,   setSynthesis]   = useState<OverviewSynthesis | null>(null);
  const [synthStatus, setSynthStatus] = useState<SynthStatus>("idle");
  const [refreshing,  setRefreshing]  = useState(false);

  const loadSynthesis = async (force = false) => {
    setSynthStatus("loading");
    try {
      const result = await researchApi.overviewSynthesis(ticker, force);
      setSynthesis(result);
      setSynthStatus("ready");
    } catch {
      setSynthStatus("error");
    }
  };

  useEffect(() => {
    loadSynthesis(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticker]);

  const handleRefresh = async () => {
    setRefreshing(true);
    await loadSynthesis(true);
    setRefreshing(false);
  };

  // Merge coverage: deterministic base + AI fresh_context flag
  const coverage = {
    ...analysisLayer.coverage,
    fresh_context_available: synthesis?.fresh_context_available ?? false,
  };

  const hasRiskFlags = analysisLayer.risk_flags.length > 0;

  return (
    <div className="space-y-4">
      {/* Executive Summary — AI narrative, loads async */}
      {synthStatus === "loading" && (
        <div className="bg-zinc-900/60 border border-zinc-800/60 rounded-xl p-4 flex items-center gap-3">
          <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin shrink-0" />
          <span className="text-sm text-zinc-500">Generating AI summary…</span>
        </div>
      )}

      {synthStatus === "ready" && synthesis && (
        <ExecutiveSummaryCard
          synthesis={synthesis}
          coverage={coverage}
          onRefresh={handleRefresh}
          refreshing={refreshing}
        />
      )}

      {synthStatus === "error" && (
        <div className="bg-zinc-900/60 border border-zinc-800/60 rounded-xl px-4 py-3 flex items-center justify-between gap-3">
          <span className="text-sm text-zinc-500">AI summary unavailable right now.</span>
          <button
            onClick={() => loadSynthesis(false)}
            className="text-xs text-blue-400 hover:text-blue-300 transition-colors shrink-0"
          >
            Retry
          </button>
        </div>
      )}

      {/* Pillars — always deterministic */}
      <SectionPanel title="Investment Pillars" id="sec-pillars">
        <PillarsRow pillars={analysisLayer.pillars} />
      </SectionPanel>

      {/* Risk strip — only if there are flags */}
      {hasRiskFlags && (
        <SectionPanel title="Risk Flags" id="sec-risk-flags">
          <RiskStrip flags={analysisLayer.risk_flags} />
        </SectionPanel>
      )}

      {/* Why Now / What Breaks — only if AI synthesis ready */}
      {synthStatus === "ready" && synthesis?.available && (
        <WhyNowCard synthesis={synthesis} />
      )}

      {/* Sentiment Regime — always rendered; shows fallback when score is null */}
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
