"use client";
import dynamic from "next/dynamic";
import { useState, useEffect, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { Menu, X, RefreshCw } from "lucide-react";
import { useAuth } from "@/components/AuthProvider";
import {
  researchApi, ResearchData, PriceUpdate, market,
  OverviewSynthesis,
} from "@/lib/api";
import { usePriceStream } from "@/hooks/usePriceStream";

import GlobalHeader          from "@/components/GlobalHeader";
import SectionPanel          from "./SectionPanel";
import ResearchHeader        from "./ResearchHeader";
import CompanySummaryBar     from "./CompanySummaryBar";
import CompanyOverviewCard   from "./CompanyOverviewCard";
import ExecutiveSummaryCard  from "./ExecutiveSummaryCard";
import KeyMetricsGrid        from "./KeyMetricsGrid";
import OwnershipSection      from "./OwnershipSection";
import EstimatesSection      from "./EstimatesSection";
import NewsSection           from "./NewsSection";
import RevenueSegmentation   from "./RevenueSegmentation";
import GrowthProfitabilityScatter from "./GrowthProfitabilityScatter";
import PeerComparison        from "./PeerComparison";
import HistoricalValuation   from "./HistoricalValuation";
import EarningsReaction      from "./EarningsReaction";
import InvestmentInsights    from "./InvestmentInsights";
import FinancialSignals      from "./FinancialSignals";
import AiAnalysis            from "./AiAnalysis";
import AnalysisLayerBlock    from "./AnalysisLayer";
import { type SynthStatus }  from "./AnalysisLayer";
import { PeerMetrics }       from "@/lib/api";

const FinancialTrends          = dynamic(() => import("./FinancialTrends"),          { ssr: false });
const FinancialStatements      = dynamic(() => import("./FinancialStatements"),      { ssr: false });
const StockPriceChart          = dynamic(() => import("./StockPriceChart"),          { ssr: false });
const ResearchTradingViewChart = dynamic(() => import("./ResearchTradingViewChart"), { ssr: false });

function fmtLarge(n: number | undefined | null): string {
  if (n == null) return "—";
  if (Math.abs(n) >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (Math.abs(n) >= 1e9)  return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6)  return `$${(n / 1e6).toFixed(1)}M`;
  return `$${n.toLocaleString()}`;
}

// ── Tab registry ───────────────────────────────────────────────────────────────
const PRIMARY_TABS = [
  { key: "overview",   label: "Overview"   },
  { key: "financials", label: "Financials" },
  { key: "valuation",  label: "Valuation"  },
  { key: "charts",     label: "Charts"     },
  { key: "ai",         label: "AI"         },
] as const;

const MORE_TABS = [
  { key: "ownership",  label: "Ownership"  },
  { key: "news",       label: "News"       },
] as const;

const ALL_TABS  = [...PRIMARY_TABS, ...MORE_TABS];
type  TabKey    = (typeof ALL_TABS)[number]["key"];
const VALID_KEYS = ALL_TABS.map(t => t.key) as string[];

// ── Component ──────────────────────────────────────────────────────────────────
export default function ResearchShell({ ticker }: { ticker: string }) {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();

  const [data,       setData]       = useState<ResearchData | null>(null);
  const [loading,    setLoading]    = useState(true);
  const [preparing,  setPreparing]  = useState(false);
  const [error,      setError]      = useState("");
  const [finPeriod,  setFinPeriod]  = useState<"annual" | "quarterly">("annual");
  const [navOpen,    setNavOpen]    = useState(false);
  const [livePrice,  setLivePrice]  = useState<PriceUpdate | null>(null);
  const [activeTab,  setActiveTab]  = useState<TabKey>("overview");

  // ── Synthesis state (lifted from AnalysisLayer so exec summary
  //    can live in the 2-column top split) ──────────────────────
  const [synthesis,   setSynthesis]   = useState<OverviewSynthesis | null>(null);
  const [synthStatus, setSynthStatus] = useState<SynthStatus>("idle");
  const [refreshing,  setRefreshing]  = useState(false);

  const loadSynthesis = useCallback(async (force = false) => {
    setSynthStatus("loading");
    try {
      const result = await researchApi.overviewSynthesis(ticker, force);
      setSynthesis(result);
      setSynthStatus("ready");
    } catch {
      setSynthStatus("error");
    }
  }, [ticker]);

  const handleSynthRefresh = async () => {
    setRefreshing(true);
    await loadSynthesis(true);
    setRefreshing(false);
  };

  const headerSentinelRef = useRef<HTMLDivElement>(null);

  // Sync active tab from URL on mount
  useEffect(() => {
    const t = new URLSearchParams(window.location.search).get("tab");
    if (t && VALID_KEYS.includes(t)) setActiveTab(t as TabKey);
  }, []);

  const handleTabChange = useCallback((key: string) => {
    setActiveTab(key as TabKey);
    router.replace(`/research/${ticker}?tab=${key}`, { scroll: false });
  }, [router, ticker]);

  const handleLivePrice = useCallback((update: PriceUpdate) => {
    if (update.ticker === ticker.toUpperCase()) setLivePrice(update);
  }, [ticker]);

  usePriceStream({ tickers: [ticker.toUpperCase()], enabled: !!data, onPrice: handleLivePrice });

  const load = useCallback(async (force = false) => {
    try {
      const d = await researchApi.get(ticker, force, () => setPreparing(true));
      setPreparing(false);
      setData(d);
      setError("");
    } catch (e: unknown) {
      setPreparing(false);
      setError(e instanceof Error ? e.message : "Failed to load research data");
    }
  }, [ticker]);

  useEffect(() => {
    if (authLoading) return;
    if (!user) { router.push("/login"); return; }
    market.prefetchHistory(ticker, "1y", "1d");
    setLoading(true);
    load(false).finally(() => setLoading(false));
  }, [authLoading, user, router, load, ticker]);

  // Load synthesis once data is available
  useEffect(() => {
    if (!data) return;
    loadSynthesis(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data?.computed_at, ticker]);

  // Close mobile drawer on lg+
  useEffect(() => {
    const handler = () => { if (window.innerWidth >= 1024) setNavOpen(false); };
    window.addEventListener("resize", handler);
    return () => window.removeEventListener("resize", handler);
  }, []);

  // ── Loading / error states ──────────────────────────────────────────────────
  if (authLoading || loading) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <GlobalHeader showBack />
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          {preparing ? (
            <>
              <div className="text-sm text-zinc-300 font-medium mb-1">Fetching data for {ticker}…</div>
              <div className="text-xs text-zinc-600">First-time lookup — this may take a few seconds</div>
            </>
          ) : (
            <div className="text-sm text-zinc-500">Loading {ticker} research…</div>
          )}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <GlobalHeader showBack />
        <div className="text-center">
          <div className="text-red-400 font-semibold mb-2">Failed to load {ticker}</div>
          <div className="text-sm text-zinc-500 mb-4">{error}</div>
          <button onClick={() => load(true)} className="text-blue-400 hover:text-blue-300 text-sm">Retry</button>
        </div>
      </div>
    );
  }

  if (!data) return null;

  const {
    ticker: sym, overview, financials, metrics, trends, research,
    estimates, valuation, segments, earnings_history, analysis, news,
  } = data;
  const { company, profile, snapshot } = overview;

  const hasFinancials = financials.income_annual.length > 0;
  const hasSegments   = segments?.length > 0;
  const hasPeers      = research.peers.length > 0;
  const hasEarnings   = earnings_history?.length > 0;
  const hasPeHistory  = valuation.pe_history.length > 0;

  // Merge coverage for exec summary card
  const coverage = {
    ...(data.analysis_layer?.coverage ?? {
      quote_available:         !!snapshot.price,
      fundamentals_available:  "none" as const,
      estimates_available:     "none" as const,
      fresh_context_available: false,
    }),
    fresh_context_available: synthesis?.fresh_context_available ?? false,
  };

  const selfMetrics: PeerMetrics = {
    symbol:           sym,
    name:             company.name,
    market_cap:       profile.market_cap,
    price:            snapshot.price,
    day_change_pct:   snapshot.day_change_percent,
    revenue_growth:   metrics.snapshot?.revenue_growth   ?? profile.revenue_growth,
    gross_margin:     metrics.snapshot?.gross_margin      ?? profile.gross_margins,
    operating_margin: metrics.snapshot?.operating_margin  ?? profile.operating_margins,
    net_margin:       metrics.snapshot?.net_margin        ?? profile.profit_margins,
    roic:             metrics.snapshot?.return_on_invested_capital ?? profile.roe,
    pe:               profile.pe_ratio   ?? metrics.snapshot?.price_to_earnings_ratio,
    ev_ebitda:        profile.ev_ebitda  ?? metrics.snapshot?.enterprise_value_to_ebitda_ratio,
    ps:               profile.price_to_sales ?? metrics.snapshot?.price_to_sales_ratio,
    fcf_yield:        metrics.snapshot?.free_cash_flow_yield,
  };

  const periodToggle = (
    <div className="flex gap-0.5 bg-zinc-800 rounded-lg p-0.5">
      {(["annual", "quarterly"] as const).map(p => (
        <button key={p} onClick={() => setFinPeriod(p)}
          className={`px-3 py-1 text-xs rounded-md font-medium transition-colors ${
            finPeriod === p ? "bg-blue-600 text-white" : "text-zinc-400 hover:text-zinc-200"
          }`}>
          {p === "annual" ? "Annual" : "Quarterly"}
        </button>
      ))}
    </div>
  );

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-50">
      <GlobalHeader showBack />

      <CompanySummaryBar data={data} livePrice={livePrice} sentinelRef={headerSentinelRef} />

      {/* Mobile nav drawer */}
      {navOpen && (
        <div className="lg:hidden fixed inset-0 z-50 flex">
          <div className="absolute inset-0 bg-black/60" onClick={() => setNavOpen(false)} />
          <aside className="relative w-64 bg-zinc-900 border-r border-zinc-800 h-full overflow-y-auto py-4 px-3">
            <div className="flex items-center justify-between mb-3 px-1">
              <span className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">Navigation</span>
              <button onClick={() => setNavOpen(false)} className="text-zinc-500 hover:text-zinc-200 transition-colors">
                <X size={16} />
              </button>
            </div>
            <nav className="flex flex-col gap-1">
              {ALL_TABS.map(tab => (
                <button
                  key={tab.key}
                  onClick={() => { handleTabChange(tab.key); setNavOpen(false); }}
                  className={`w-full text-left px-3 py-2.5 rounded-lg text-sm transition-colors ${
                    activeTab === tab.key
                      ? "bg-blue-600/20 text-blue-400 font-medium"
                      : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </nav>
          </aside>
        </div>
      )}

      <div className="pt-16">
        <ResearchHeader
          data={data}
          livePrice={livePrice}
          tabs={[...PRIMARY_TABS]}
          moreTabs={[...MORE_TABS]}
          activeTab={activeTab}
          onTabChange={handleTabChange}
        />
        <div ref={headerSentinelRef} className="h-0" />

        <div className="max-w-[1400px] mx-auto px-4 sm:px-6">
          <div className="py-6 space-y-5">

            {/* Mobile: show active tab label + nav toggle */}
            <div className="lg:hidden flex items-center gap-2">
              <button
                onClick={() => setNavOpen(true)}
                className="flex items-center gap-2 text-xs text-zinc-400 hover:text-zinc-200 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-lg px-3 py-1.5 transition-colors"
              >
                <Menu size={14} />
                {ALL_TABS.find(t => t.key === activeTab)?.label ?? "Navigate"}
              </button>
            </div>

            {/* ── OVERVIEW ──────────────────────────────────────────── */}
            {activeTab === "overview" && (
              <>
                {/* ── TOP: 2-column split ───────────────────────────── */}
                {/* LEFT  → Executive Summary  (interpretation layer)   */}
                {/* RIGHT → Company Overview   (contextual facts)       */}
                {data.analysis_layer && (
                  <div className="grid grid-cols-1 lg:grid-cols-[1.6fr_1fr] gap-6 items-stretch">

                    {/* LEFT: Executive Summary */}
                    <div className="flex flex-col">
                      {synthStatus === "loading" && (
                        <div className="flex-1 bg-zinc-900/60 border border-zinc-800/60 rounded-xl p-4 flex items-center gap-3">
                          <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin shrink-0" />
                          <span className="text-sm text-zinc-500">Generating AI summary…</span>
                        </div>
                      )}

                      {synthStatus === "ready" && synthesis && (
                        <ExecutiveSummaryCard
                          synthesis={synthesis}
                          coverage={coverage}
                          onRefresh={handleSynthRefresh}
                          refreshing={refreshing}
                        />
                      )}

                      {synthStatus === "error" && (
                        <div className="flex-1 bg-zinc-900/60 border border-zinc-800/60 rounded-xl px-4 py-3 flex items-center justify-between gap-3">
                          <span className="text-sm text-zinc-500">AI summary unavailable right now.</span>
                          <button
                            onClick={() => loadSynthesis(false)}
                            className="flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300 transition-colors shrink-0"
                          >
                            <RefreshCw size={11} />
                            Retry
                          </button>
                        </div>
                      )}

                      {/* Fallback while synthesis not yet triggered */}
                      {synthStatus === "idle" && (
                        <div className="flex-1 bg-zinc-900/60 border border-zinc-800/60 rounded-xl p-4" />
                      )}
                    </div>

                    {/* RIGHT: Compact Company Overview */}
                    <CompanyOverviewCard company={company} profile={profile} />
                  </div>
                )}

                {/* ── ANALYSIS LAYER: pillars → bottom ─────────────── */}
                {/* Executive Summary was removed from AnalysisLayer.   */}
                {/* This block renders: Pillars, Risk Flags, Why Now,   */}
                {/* Sentiment Regime, Transparency Drawer.              */}
                {data.analysis_layer && (
                  <AnalysisLayerBlock
                    ticker={sym}
                    analysisLayer={data.analysis_layer}
                    computedAt={data.computed_at}
                    synthesis={synthesis}
                    synthStatus={synthStatus}
                    refreshing={refreshing}
                  />
                )}

                {/* ── FINANCIAL SNAPSHOT (evidence layer) ─────────── */}
                <SectionPanel title="Financial Snapshot" id="sec-metrics">
                  <KeyMetricsGrid data={data} />
                </SectionPanel>

                {/* ── INVESTMENT INSIGHTS (collapsed, supplemental) ── */}
                {/* Kept for deeper bull case / catalyst detail but     */}
                {/* collapsed to avoid repeating the exec summary.      */}
                {analysis.insights && (
                  <SectionPanel title="Investment Insights" defaultOpen={false} id="sec-insights">
                    <InvestmentInsights insights={analysis.insights} sections={["bull", "catalysts"]} />
                  </SectionPanel>
                )}

                {/* ── KEY RISKS (collapsed, supplemental) ────────────── */}
                {/* Broader structural risks distinct from current flags. */}
                {analysis.insights && (
                  <SectionPanel title="Key Risks" defaultOpen={false} id="sec-risks">
                    <InvestmentInsights insights={analysis.insights} sections={["bear", "risks"]} />
                  </SectionPanel>
                )}
              </>
            )}

            {/* ── FINANCIALS ─────────────────────────────────────────── */}
            {activeTab === "financials" && (
              <>
                {hasFinancials ? (
                  <>
                    <SectionPanel title="Financial Trends" action={periodToggle} id="sec-trends">
                      <FinancialTrends annual={trends.annual} quarterly={trends.quarterly} period={finPeriod} />
                    </SectionPanel>

                    {analysis.anomalies.length > 0 && (
                      <SectionPanel title="Financial Signals" id="sec-signals">
                        <FinancialSignals anomalies={analysis.anomalies} />
                      </SectionPanel>
                    )}

                    {hasSegments && (
                      <SectionPanel title="Revenue Drivers" id="sec-segments">
                        <RevenueSegmentation segments={segments} />
                      </SectionPanel>
                    )}

                    <SectionPanel title="Growth vs Profitability" id="sec-growth">
                      <GrowthProfitabilityScatter
                        ticker={sym}
                        incomeAnnual={financials.income_annual}
                        selfMetrics={selfMetrics}
                        peers={research.peers}
                        selfPeg={profile.peg_ratio}
                        selfEvSales={profile.ev_revenue}
                      />
                    </SectionPanel>

                    <SectionPanel title="Financial Statements" id="sec-statements">
                      <FinancialStatements
                        income={financials.income_annual}    balance={financials.balance_annual}    cashflow={financials.cashflow_annual}
                        incomeQ={financials.income_quarterly} balanceQ={financials.balance_quarterly} cashflowQ={financials.cashflow_quarterly}
                        period={finPeriod} onPeriodChange={setFinPeriod}
                      />
                    </SectionPanel>
                  </>
                ) : (
                  <p className="text-sm text-zinc-500 text-center py-16">No financial data available for {sym}.</p>
                )}
              </>
            )}

            {/* ── VALUATION ──────────────────────────────────────────── */}
            {activeTab === "valuation" && (
              <>
                {hasPeHistory && (
                  <SectionPanel title="Historical Valuation" id="sec-val-history">
                    <HistoricalValuation
                      peHistory={valuation.pe_history}
                      currentPe={profile.pe_ratio ?? metrics.snapshot?.price_to_earnings_ratio}
                    />
                  </SectionPanel>
                )}

                {hasPeers && (
                  <SectionPanel title="Peer Comparison" id="sec-peers">
                    <PeerComparison ticker={sym} selfMetrics={selfMetrics} peers={research.peers} />
                  </SectionPanel>
                )}

                {(estimates.annual.length > 0 || estimates.quarterly.length > 0) && (
                  <SectionPanel title="Analyst Estimates" id="sec-estimates">
                    <EstimatesSection annual={estimates.annual} quarterly={estimates.quarterly} />
                  </SectionPanel>
                )}

                {!hasPeHistory && !hasPeers && !estimates.annual.length && !estimates.quarterly.length && (
                  <p className="text-sm text-zinc-500 text-center py-16">No valuation data available for {sym}.</p>
                )}
              </>
            )}

            {/* ── CHARTS ─────────────────────────────────────────────── */}
            {activeTab === "charts" && (
              <SectionPanel title="Interactive Chart" id="sec-tv-chart">
                <ResearchTradingViewChart ticker={sym} exchange={company.exchange} />
              </SectionPanel>
            )}

            {/* StockPriceChart + EarningsReaction: always mounted (hidden) */}
            <div className={activeTab === "charts" ? "flex flex-col gap-5" : "hidden"}>
              <SectionPanel title="Price History" id="sec-price">
                <StockPriceChart ticker={ticker} />
              </SectionPanel>

              {hasEarnings && (
                <SectionPanel title="Earnings Reaction" id="sec-earnings">
                  <EarningsReaction earnings={earnings_history} />
                </SectionPanel>
              )}
            </div>

            {/* ── AI ─────────────────────────────────────────────────── */}
            {activeTab === "ai" && (
              <SectionPanel title="AI Analysis" id="sec-ai">
                <AiAnalysis ticker={sym} />
              </SectionPanel>
            )}

            {/* ── OWNERSHIP ──────────────────────────────────────────── */}
            {activeTab === "ownership" && (
              <SectionPanel title="Ownership & Insider Transactions" id="sec-ownership">
                <OwnershipSection
                  ownership={research.ownership}
                  insider_trades={research.insider_trades}
                  profile={profile}
                />
              </SectionPanel>
            )}

            {/* ── NEWS ───────────────────────────────────────────────── */}
            {activeTab === "news" && (
              news.length > 0 ? (
                <SectionPanel title="Latest News" id="sec-news">
                  <NewsSection news={news} />
                </SectionPanel>
              ) : (
                <p className="text-sm text-zinc-500 text-center py-16">No recent news available for {sym}.</p>
              )
            )}

          </div>

          <div className="text-xs text-zinc-700 text-center py-4 border-t border-zinc-800/40">
            Data from financialdatasets.ai &amp; yfinance · Cached 1h · Last computed {new Date(data.computed_at).toLocaleString()}
          </div>
        </div>
      </div>
    </div>
  );
}
