"use client";
import dynamic from "next/dynamic";
import { useState, useEffect, useCallback, useMemo } from "react";
import { LayoutDashboard, BarChart2, ShieldAlert, FlaskConical } from "lucide-react";
import {
  portfolios as portApi, positions as posApi,
  Portfolio, Position, PortfolioAnalytics, PortfolioAnalysisResponse, PriceUpdate,
} from "@/lib/api";
import { useMarketStatus } from "@/hooks/useMarketStatus";
import { usePriceStream } from "@/hooks/usePriceStream";
import { usePricePoll } from "@/hooks/usePricePoll";
import GlobalHeader from "@/components/GlobalHeader";
import PageHeader   from "@/components/PageHeader";

const OverviewTab  = dynamic(() => import("./OverviewTab"),  { ssr: false });
const HoldingsTab  = dynamic(() => import("./HoldingsTab"),  { ssr: false });
const RiskTab      = dynamic(() => import("./RiskTab"),      { ssr: false });
const SimulatorTab = dynamic(() => import("./SimulatorTab"), { ssr: false });

type Tab    = "overview" | "holdings" | "risk" | "simulator";
type Period = "1mo" | "3mo" | "6mo" | "ytd" | "1y" | "2y";

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: "overview",  label: "Overview",  icon: <LayoutDashboard size={16} /> },
  { id: "holdings",  label: "Holdings",  icon: <BarChart2 size={16} />       },
  { id: "risk",      label: "Risk",      icon: <ShieldAlert size={16} />     },
  { id: "simulator", label: "Simulator", icon: <FlaskConical size={16} />    },
];

export default function DashboardShell() {
  const [tab,        setTab]        = useState<Tab>("overview");
  const [simPrefill, setSimPrefill] = useState<string | undefined>(undefined);
  const period: Period = "1y";

  const [portfolios,       setPortfolios]       = useState<Portfolio[]>([]);
  const [selected,         setSelected]         = useState<Portfolio | null>(null);
  const [positions,        setPositions]        = useState<Position[]>([]);
  const [analytics,        setAnalytics]        = useState<PortfolioAnalytics | null>(null);
  const [loadingData,      setLoadingData]      = useState(false);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [analysis,         setAnalysis]         = useState<PortfolioAnalysisResponse | null>(null);
  const [livePrices,       setLivePrices]       = useState<Record<string, PriceUpdate>>({});

  const mktStatus = useMarketStatus();

  const tickers = useMemo(
    () => positions.map(p => p.ticker),
    [positions],
  );

  // Wait until market status is known before enabling either stream.
  // Without this, mktStatus null→value flip toggles `enabled` on mount,
  // causing an immediate abort+reconnect race that surfaces as an SSE error.
  const mktKnown  = mktStatus !== null;
  const isTrading = mktStatus?.is_trading === true;

  // Market open → real-time SSE stream
  const handlePriceUpdate = useCallback((update: PriceUpdate) => {
    setLivePrices(prev => ({ ...prev, [update.ticker]: update }));
  }, []);

  usePriceStream({
    tickers,
    enabled: tickers.length > 0 && mktKnown && isTrading,
    onPrice: handlePriceUpdate,
  });

  // Market closed → single fetch + poll every 5 min, with countdown
  const { prices: polledPrices, nextRefreshIn, lastFetchedAt } = usePricePoll({
    tickers,
    enabled: tickers.length > 0 && mktKnown && !isTrading,
  });

  // Merge polled prices into livePrices when market is closed
  useEffect(() => {
    if (!isTrading && Object.keys(polledPrices).length > 0) {
      setLivePrices(polledPrices);
    }
  }, [isTrading, polledPrices]);

  // ── Load portfolios on mount ─────────────────────────────
  useEffect(() => {
    portApi.list()
      .then(list => {
        setPortfolios(list);
        setSelected(list.find(p => p.is_default) ?? list[0] ?? null);
      })
      .catch(console.error);
  }, []);

  // ── Load positions when portfolio changes ────────────────
  const loadPositions = useCallback((pid: string) => {
    setLoadingData(true);
    posApi.list(pid)
      .then(setPositions)
      .catch(console.error)
      .finally(() => setLoadingData(false));
  }, []);

  // ── Load analytics when portfolio or period changes ──────
  const loadAnalytics = useCallback((pid: string, p: Period, force = false) => {
    setAnalyticsLoading(true);
    portApi.analytics(pid, p, force, () => {
      // Called when backend returns 202 (data preparing) — keep loading state
    })
      .then(setAnalytics)
      .catch(e => { console.error(e); setAnalytics(null); })
      .finally(() => setAnalyticsLoading(false));
  }, []);

  // ── Load portfolio analysis (health/suggestions/clusters) ─
  const loadAnalysis = useCallback((pid: string, force = false) => {
    portApi.analysis(pid, force)
      .then(setAnalysis)
      .catch(e => { console.error(e); setAnalysis(null); });
  }, []);

  useEffect(() => {
    if (!selected) return;
    loadPositions(selected.id);
    loadAnalytics(selected.id, period);
    loadAnalysis(selected.id);
  }, [selected, period, loadPositions, loadAnalytics, loadAnalysis]);

  // Auto-force-refresh when cached analytics is stale (>10 min old).
  // Only during trading hours — when market is closed prices don't change
  // meaningfully and the re-fetch introduces gain value noise.
  useEffect(() => {
    if (!analytics?.computed_at || !selected || !isTrading) return;
    const ageMs = Date.now() - new Date(analytics.computed_at).getTime();
    if (ageMs > 10 * 60 * 1000) {
      loadAnalytics(selected.id, period, true);
    }
  }, [analytics?.computed_at, selected, period, loadAnalytics, isTrading]);

  const handleRefresh = () => {
    if (!selected) return;
    loadPositions(selected.id);
    loadAnalytics(selected.id, period, true);
    loadAnalysis(selected.id, true);
  };

  const handleCreatePortfolio = useCallback(async (name: string) => {
    const p = await portApi.create({
      name,
      is_default: portfolios.length === 0,
      currency: "USD",
    });
    setPortfolios(prev => [...prev, p]);
    setSelected(p);
  }, [portfolios.length]);

  return (
    <div className="min-h-screen bg-zinc-950 flex flex-col pt-16">

      {/* ── Global header (fixed 64px) ───────────────────────── */}
      <GlobalHeader
        portfolios={portfolios}
        selectedPortfolio={selected}
        onSelectPortfolio={setSelected}
        onCreatePortfolio={handleCreatePortfolio}
        onRefresh={handleRefresh}
        refreshing={loadingData || analyticsLoading}
        onAddPosition={() => setTab("holdings")}
        onSimulatorOpen={() => { setSimPrefill(undefined); setTab("simulator"); }}
        marketStatus={mktStatus}
      />

      {/* ── Page-level tab bar (sticky below GlobalHeader) ───── */}
      <PageHeader
        tabs={TABS}
        activeTab={tab}
        onTabChange={id => setTab(id as Tab)}
      />

      {/* ── Content ──────────────────────────────────────────── */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-6">
        {!selected ? (
          <div className="flex flex-col items-center justify-center h-64">
            <p className="text-lg font-medium text-zinc-400 mb-1">No portfolio yet</p>
            <p className="text-sm text-zinc-500">Create one using the selector above</p>
          </div>
        ) : (
          <>
            {tab === "overview"  && (
              <OverviewTab
                analytics={analytics}
                positions={positions}
                loading={analyticsLoading}
                period={period}
                analysis={analysis}
                livePrices={livePrices}
                isStreaming={isTrading}
                nextRefreshIn={isTrading ? null : nextRefreshIn}
                lastFetchedAt={isTrading ? null : lastFetchedAt}
                onOpenSimulator={ticker => { setSimPrefill(ticker); setTab("simulator"); }}
              />
            )}
            {tab === "holdings"  && (
              <HoldingsTab
                portfolioId={selected.id}
                data={positions}
                analytics={analytics}
                livePrices={livePrices}
                onRefresh={() => {
                  loadPositions(selected.id);
                  loadAnalytics(selected.id, period, true);
                }}
              />
            )}
            {tab === "risk"      && (
              <RiskTab
                analytics={analytics}
                loading={analyticsLoading}
                period={period}
                analysis={analysis}
              />
            )}
            {tab === "simulator" && (
              <SimulatorTab portfolioId={selected.id} prefillTicker={simPrefill} />
            )}
          </>
        )}
      </main>
    </div>
  );
}
