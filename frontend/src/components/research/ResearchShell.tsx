"use client";
import dynamic from "next/dynamic";
import { useState, useEffect, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { Menu, X } from "lucide-react";
import { useAuth } from "@/components/AuthProvider";
import { researchApi, ResearchData } from "@/lib/api";

import GlobalHeader        from "@/components/GlobalHeader";
import SectionPanel        from "./SectionPanel";
import ResearchHeader      from "./ResearchHeader";
import CompanySummaryBar   from "./CompanySummaryBar";
import KeyMetricsGrid      from "./KeyMetricsGrid";
import ValuationSection    from "./ValuationSection";
import OwnershipSection    from "./OwnershipSection";
import EstimatesSection    from "./EstimatesSection";
import NewsSection         from "./NewsSection";
import RevenueSegmentation from "./RevenueSegmentation";
import GrowthProfitabilityScatter from "./GrowthProfitabilityScatter";
import ResearchNav, { NavSection } from "./ResearchNav";
import PeerComparison      from "./PeerComparison";
import HistoricalValuation from "./HistoricalValuation";
import EarningsReaction    from "./EarningsReaction";
import InvestmentInsights  from "./InvestmentInsights";
import FinancialSignals    from "./FinancialSignals";
import { PeerMetrics }     from "@/lib/api";

const FinancialCharts     = dynamic(() => import("./FinancialCharts"),     { ssr: false });
const FinancialTrends     = dynamic(() => import("./FinancialTrends"),     { ssr: false });
const FinancialStatements = dynamic(() => import("./FinancialStatements"), { ssr: false });
const StockPriceChart     = dynamic(() => import("./StockPriceChart"),     { ssr: false });

function fmtLarge(n: number | undefined | null): string {
  if (n == null) return "—";
  if (Math.abs(n) >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (Math.abs(n) >= 1e9)  return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6)  return `$${(n / 1e6).toFixed(1)}M`;
  return `$${n.toLocaleString()}`;
}

const ALL_NAV: NavSection[] = [
  { id: "sec-overview",   label: "Overview"           },
  { id: "sec-insights",   label: "Investment Insights" },
  { id: "sec-price",      label: "Price Chart"         },
  { id: "sec-metrics",    label: "Key Metrics"         },
  { id: "sec-trends",     label: "Financial Trends"    },
  { id: "sec-signals",    label: "Financial Signals"   },
  { id: "sec-segments",   label: "Revenue Drivers"         },
  { id: "sec-growth",     label: "Growth vs Profitability" },
  { id: "sec-statements", label: "Statements"              },
  { id: "sec-val-history",label: "Historical Valuation"},
  { id: "sec-peers",      label: "Peer Comparison"     },
  { id: "sec-estimates",  label: "Estimates"           },
  { id: "sec-earnings",   label: "Earnings Reaction"   },
  { id: "sec-ownership",  label: "Ownership"           },
  { id: "sec-risks",      label: "Key Risks"           },
  { id: "sec-news",       label: "News"                },
];

export default function ResearchShell({ ticker }: { ticker: string }) {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();

  const [data,       setData]       = useState<ResearchData | null>(null);
  const [loading,    setLoading]    = useState(true);
  const [error,      setError]      = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [finPeriod,  setFinPeriod]  = useState<"annual" | "quarterly">("annual");
  const [navOpen,    setNavOpen]    = useState(false);

  // Sentinel ref: when the company header scrolls out of view, the summary bar appears
  const headerSentinelRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async (force = false) => {
    try {
      const d = await researchApi.get(ticker, force);
      setData(d);
      setError("");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load research data");
    }
  }, [ticker]);

  useEffect(() => {
    if (authLoading) return;
    if (!user) { router.push("/login"); return; }
    setLoading(true);
    load(false).finally(() => setLoading(false));
  }, [authLoading, user, router, load]);

  // Close mobile nav on resize to xl
  useEffect(() => {
    const handler = () => { if (window.innerWidth >= 1280) setNavOpen(false); };
    window.addEventListener("resize", handler);
    return () => window.removeEventListener("resize", handler);
  }, []);

  if (authLoading || loading) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <GlobalHeader showBack />
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          <div className="text-sm text-zinc-500">Loading {ticker} research…</div>
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

  const { ticker: sym, overview, financials, metrics, trends, research, estimates, valuation, segments, earnings_history, analysis, news } = data;
  const { company, profile, snapshot } = overview;

  const hasFinancials = financials.income_annual.length > 0;
  const hasSegments   = segments?.length > 0;
  const hasPeers      = research.peers.length > 0;
  const hasEarnings   = earnings_history?.length > 0;
  const hasPeHistory  = valuation.pe_history.length > 0;

  const navSections = ALL_NAV.filter(s => {
    if (s.id === "sec-overview"    && !profile.description && !company.sector) return false;
    if (s.id === "sec-trends"      && !hasFinancials) return false;
    if (s.id === "sec-statements"  && !hasFinancials) return false;
    if (s.id === "sec-segments"    && !hasSegments)   return false;
    if (s.id === "sec-growth"      && !hasFinancials) return false;
    if (s.id === "sec-estimates"   && !estimates.annual.length && !estimates.quarterly.length) return false;
    if (s.id === "sec-news"        && !news.length)   return false;
    if (s.id === "sec-peers"       && !hasPeers)      return false;
    if (s.id === "sec-earnings"    && !hasEarnings)   return false;
    if (s.id === "sec-val-history" && !hasPeHistory)  return false;
    return true;
  });

  const snap = overview.snapshot;
  const selfMetrics: PeerMetrics = {
    symbol:           sym,
    name:             company.name,
    market_cap:       profile.market_cap,
    price:            snap.price,
    day_change_pct:   snap.day_change_percent,
    revenue_growth:   metrics.snapshot?.revenue_growth ?? profile.revenue_growth,
    gross_margin:     metrics.snapshot?.gross_margin    ?? profile.gross_margins,
    operating_margin: metrics.snapshot?.operating_margin ?? profile.operating_margins,
    net_margin:       metrics.snapshot?.net_margin       ?? profile.profit_margins,
    roic:             metrics.snapshot?.return_on_invested_capital,
    pe:               profile.pe_ratio ?? metrics.snapshot?.price_to_earnings_ratio,
    ev_ebitda:        profile.ev_ebitda ?? metrics.snapshot?.enterprise_value_to_ebitda_ratio,
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

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-50">
      {/* Fixed global header */}
      <GlobalHeader showBack />

      {/* Sticky summary bar (appears when company header scrolls out of view) */}
      <CompanySummaryBar data={data} sentinelRef={headerSentinelRef} />

      {/* Mobile nav drawer overlay */}
      {navOpen && (
        <div className="xl:hidden fixed inset-0 z-50 flex">
          <div className="absolute inset-0 bg-black/60" onClick={() => setNavOpen(false)} />
          <aside className="relative w-64 bg-zinc-900 border-r border-zinc-800 h-full overflow-y-auto py-4 px-3 flex flex-col gap-2">
            <div className="flex items-center justify-between mb-2 px-1">
              <span className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">Navigation</span>
              <button onClick={() => setNavOpen(false)} className="text-zinc-500 hover:text-zinc-200 transition-colors">
                <X size={16} />
              </button>
            </div>
            <ResearchNav sections={navSections} />
          </aside>
        </div>
      )}

      {/* Everything below the 48px fixed header */}
      <div className="pt-12">
        {/* Company info header — scrolls with page; sentinel marks its bottom edge */}
        <ResearchHeader
          data={data}
          onRefresh={async () => { setRefreshing(true); await load(true); setRefreshing(false); }}
          refreshing={refreshing}
        />
        {/* Sentinel: placed at the bottom of the header so the summary bar triggers correctly */}
        <div ref={headerSentinelRef} className="h-0" />

        {/* ── Two-column layout ── */}
        <div className="max-w-[1800px] mx-auto w-full px-4 sm:px-6 flex gap-6 items-start">

          {/* Desktop left nav — sticky, dedicated 240px column */}
          <aside className="hidden xl:flex flex-col w-60 shrink-0 sticky top-12 h-[calc(100vh-3rem)] overflow-y-auto pt-6 pb-6">
            <ResearchNav sections={navSections} />
          </aside>

          {/* Main content — fills all remaining space */}
          <main className="flex-1 min-w-0 py-6 space-y-5">

            {/* Mobile nav toggle button */}
            <div className="xl:hidden flex justify-start">
              <button
                onClick={() => setNavOpen(true)}
                className="flex items-center gap-2 text-xs text-zinc-400 hover:text-zinc-200 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-lg px-3 py-1.5 transition-colors"
              >
                <Menu size={14} />
                Jump to section
              </button>
            </div>

            {/* 1. Company Overview */}
            {(profile.description || company.sector) && (
              <SectionPanel title="Company Overview" id="sec-overview">
                <div className="space-y-4">
                  {profile.description && (
                    <p className="text-sm text-zinc-400 leading-relaxed">{profile.description}</p>
                  )}
                  <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
                    {company.sector           && <Info label="Sector"       value={company.sector} />}
                    {company.industry         && <Info label="Industry"     value={company.industry} />}
                    {company.exchange         && <Info label="Exchange"     value={company.exchange} />}
                    {company.location         && <Info label="Location"     value={company.location} />}
                    {profile.employees        && <Info label="Employees"    value={profile.employees.toLocaleString()} />}
                    {profile.market_cap       && <Info label="Market Cap"   value={fmtLarge(profile.market_cap)} />}
                    {profile.enterprise_value && <Info label="Ent. Value"   value={fmtLarge(profile.enterprise_value)} />}
                    {profile.website && (
                      <div className="bg-zinc-800/40 rounded-lg p-3">
                        <div className="text-xs text-zinc-500 mb-1">Website</div>
                        <a href={profile.website} target="_blank" rel="noopener noreferrer"
                           className="text-xs text-blue-400 hover:underline break-all">
                          {profile.website.replace(/^https?:\/\//, "")}
                        </a>
                      </div>
                    )}
                    {profile.currency && <Info label="Currency" value={profile.currency} />}
                    {company.cik      && <Info label="CIK"      value={company.cik} />}
                  </div>
                  {profile.officers && profile.officers.length > 0 && (
                    <div>
                      <div className="text-xs font-semibold text-zinc-400 mb-2">Key Executives</div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-2">
                        {profile.officers.map((o, i) => (
                          <div key={i} className="bg-zinc-800/40 rounded-lg px-3 py-2">
                            <div className="text-sm text-zinc-200 font-medium">{o.name}</div>
                            <div className="text-xs text-zinc-500">{o.title}</div>
                            {o.pay && <div className="text-xs text-zinc-600 mt-0.5">Comp: ${(o.pay / 1e6).toFixed(1)}M</div>}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </SectionPanel>
            )}

            {/* 2. Investment Insights — bull case + catalysts */}
            {analysis.insights && (
              <SectionPanel title="Investment Insights" id="sec-insights">
                <InvestmentInsights insights={analysis.insights} sections={["bull", "catalysts"]} />
              </SectionPanel>
            )}

            {/* 3. Price Chart */}
            <SectionPanel title="Stock Price" id="sec-price">
              <StockPriceChart ticker={ticker} />
            </SectionPanel>

            {/* 4. Key Metrics */}
            <SectionPanel title="Key Metrics" id="sec-metrics">
              <KeyMetricsGrid data={data} />
            </SectionPanel>

            {/* 5. Financial Trends */}
            {hasFinancials && (
              <SectionPanel title="Financial Trends" action={periodToggle} id="sec-trends">
                <FinancialTrends
                  annual={trends.annual}
                  quarterly={trends.quarterly}
                  period={finPeriod}
                />
              </SectionPanel>
            )}

            {/* 5b. Financial Signals */}
            {analysis.anomalies.length > 0 && (
              <SectionPanel title="Financial Signals" id="sec-signals">
                <FinancialSignals anomalies={analysis.anomalies} />
              </SectionPanel>
            )}

            {/* 6. Revenue Drivers */}
            {hasSegments && (
              <SectionPanel title="Revenue Drivers" id="sec-segments">
                <RevenueSegmentation segments={segments} />
              </SectionPanel>
            )}

            {/* 6b. Growth vs Profitability */}
            {hasFinancials && (
              <SectionPanel title="Growth vs Profitability" id="sec-growth">
                <GrowthProfitabilityScatter
                  ticker={sym}
                  incomeAnnual={financials.income_annual}
                  selfMetrics={selfMetrics}
                  peers={research.peers}
                />
              </SectionPanel>
            )}

            {/* 7. Financial Statements */}
            {hasFinancials && (
              <SectionPanel title="Financial Statements" id="sec-statements">
                <FinancialStatements
                  income={financials.income_annual} balance={financials.balance_annual} cashflow={financials.cashflow_annual}
                  incomeQ={financials.income_quarterly} balanceQ={financials.balance_quarterly} cashflowQ={financials.cashflow_quarterly}
                  period={finPeriod} onPeriodChange={setFinPeriod}
                />
              </SectionPanel>
            )}

            {/* 8. Historical Valuation */}
            {hasPeHistory && (
              <SectionPanel title="Historical Valuation" id="sec-val-history">
                <HistoricalValuation peHistory={valuation.pe_history} currentPe={profile.pe_ratio ?? metrics.snapshot?.price_to_earnings_ratio} />
              </SectionPanel>
            )}

            {/* 9. Peer Comparison */}
            {hasPeers && (
              <SectionPanel title="Peer Comparison" id="sec-peers">
                <PeerComparison ticker={sym} selfMetrics={selfMetrics} peers={research.peers} />
              </SectionPanel>
            )}

            {/* 10. Analyst Estimates */}
            {(estimates.annual.length > 0 || estimates.quarterly.length > 0) && (
              <SectionPanel title="Analyst Estimates" id="sec-estimates">
                <EstimatesSection annual={estimates.annual} quarterly={estimates.quarterly} />
              </SectionPanel>
            )}

            {/* 11. Earnings Reaction */}
            {hasEarnings && (
              <SectionPanel title="Earnings Reaction" id="sec-earnings">
                <EarningsReaction earnings={earnings_history} />
              </SectionPanel>
            )}

            {/* 12. Ownership */}
            <SectionPanel title="Ownership & Insider Transactions" id="sec-ownership">
              <OwnershipSection ownership={research.ownership} insider_trades={research.insider_trades} profile={profile} />
            </SectionPanel>

            {/* 13. Key Risks — bear case + risks from insights */}
            {analysis.insights && (
              <SectionPanel title="Key Risks" defaultOpen={false} id="sec-risks">
                <InvestmentInsights insights={analysis.insights} sections={["bear", "risks"]} />
              </SectionPanel>
            )}

            {/* 14. News */}
            {news.length > 0 && (
              <SectionPanel title="Latest News" defaultOpen={false} id="sec-news">
                <NewsSection news={news} />
              </SectionPanel>
            )}

            <div className="text-xs text-zinc-700 text-center py-4">
              Data from financialdatasets.ai &amp; yfinance · Cached 1h · Last computed {new Date(data.computed_at).toLocaleString()}
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-zinc-800/40 rounded-lg p-3">
      <div className="text-xs text-zinc-500 mb-1">{label}</div>
      <div className="text-sm text-zinc-200 font-medium">{value}</div>
    </div>
  );
}
