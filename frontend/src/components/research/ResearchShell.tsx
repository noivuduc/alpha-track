"use client";
import dynamic from "next/dynamic";
import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import { researchApi, ResearchData } from "@/lib/api";

import SectionPanel      from "./SectionPanel";
import ResearchHeader    from "./ResearchHeader";
import KeyMetricsGrid    from "./KeyMetricsGrid";
import ValuationSection  from "./ValuationSection";
import OwnershipSection  from "./OwnershipSection";
import EstimatesSection  from "./EstimatesSection";
import NewsSection       from "./NewsSection";
import RevenueSegmentation from "./RevenueSegmentation";

const FinancialCharts     = dynamic(() => import("./FinancialCharts"),     { ssr: false });
const FinancialStatements = dynamic(() => import("./FinancialStatements"), { ssr: false });
const StockPriceChart     = dynamic(() => import("./StockPriceChart"),     { ssr: false });

export default function ResearchShell({ ticker }: { ticker: string }) {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();

  const [data,       setData]       = useState<ResearchData | null>(null);
  const [loading,    setLoading]    = useState(true);
  const [error,      setError]      = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [finPeriod,  setFinPeriod]  = useState<"annual" | "quarterly">("annual");

  const load = useCallback(async (force = false) => {
    try {
      const d = await researchApi.get(ticker, force);
      setData(d);
      setError("");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to load research data";
      setError(msg);
    }
  }, [ticker]);

  useEffect(() => {
    if (authLoading) return;
    if (!user) { router.push("/login"); return; }
    setLoading(true);
    load(false).finally(() => setLoading(false));
  }, [authLoading, user, router, load]);

  const handleRefresh = async () => {
    setRefreshing(true);
    await load(true);
    setRefreshing(false);
  };

  if (authLoading || loading) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
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
    company, profile, income, income_ttm, balance, balance_ttm, cashflow, cashflow_ttm,
    income_quarterly, balance_quarterly, cashflow_quarterly,
    metrics, ownership, insider_trades, estimates_annual, estimates_quarterly,
    news, segments,
  } = data;

  const hasFinancials = income.length > 0;
  const hasSegments   = segments?.length > 0;

  // Period toggle shared across charts + statements
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
      <ResearchHeader data={data} onRefresh={handleRefresh} refreshing={refreshing} />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-4">

        {/* Stock Price Chart */}
        <SectionPanel title="Stock Price History">
          <StockPriceChart ticker={ticker} />
        </SectionPanel>

        {/* Company Profile */}
        {(profile.description || company.sector) && (
          <SectionPanel title="Company Profile" defaultOpen={false}>
            <div className="space-y-3">
              {profile.description && (
                <p className="text-sm text-zinc-400 leading-relaxed max-w-4xl">
                  {profile.description}
                </p>
              )}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4">
                {company.sector   && <Info label="Sector"    value={company.sector} />}
                {company.industry && <Info label="Industry"  value={company.industry} />}
                {company.exchange && <Info label="Exchange"  value={company.exchange} />}
                {company.location && <Info label="Location"  value={company.location} />}
                {profile.employees && <Info label="Employees" value={profile.employees.toLocaleString()} />}
                {profile.website  && (
                  <div className="bg-zinc-800/40 rounded-lg p-3">
                    <div className="text-xs text-zinc-500 mb-1">Website</div>
                    <a href={profile.website} target="_blank" rel="noopener noreferrer"
                       className="text-xs text-blue-400 hover:underline break-all">
                      {profile.website.replace(/^https?:\/\//, "")}
                    </a>
                  </div>
                )}
                {profile.currency && <Info label="Currency"  value={profile.currency} />}
                {company.cik      && <Info label="CIK"       value={company.cik} />}
              </div>

              {profile.officers && profile.officers.length > 0 && (
                <div className="mt-4">
                  <div className="text-xs font-semibold text-zinc-400 mb-2">Key Executives</div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
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

        {/* Key Metrics */}
        <SectionPanel title="Key Metrics">
          <KeyMetricsGrid data={data} />
        </SectionPanel>

        {/* Financial Charts */}
        {hasFinancials && (
          <SectionPanel title="Financial Performance" action={periodToggle}>
            <FinancialCharts
              income={income}    cashflow={cashflow}
              incomeQ={income_quarterly} cashflowQ={cashflow_quarterly}
              period={finPeriod}
            />
          </SectionPanel>
        )}

        {/* Financial Statements */}
        {hasFinancials && (
          <SectionPanel title="Financial Statements">
            <FinancialStatements
              income={income}   balance={balance}   cashflow={cashflow}
              incomeQ={income_quarterly} balanceQ={balance_quarterly} cashflowQ={cashflow_quarterly}
              period={finPeriod} onPeriodChange={setFinPeriod}
            />
          </SectionPanel>
        )}

        {/* Revenue Segmentation */}
        {hasSegments && (
          <SectionPanel title="Revenue Segmentation">
            <RevenueSegmentation segments={segments} />
          </SectionPanel>
        )}

        {/* Valuation */}
        <SectionPanel title="Valuation Metrics">
          <ValuationSection metrics={metrics} profile={profile} />
        </SectionPanel>

        {/* Ownership & Insiders */}
        <SectionPanel title="Ownership & Insider Transactions">
          <OwnershipSection ownership={ownership} insider_trades={insider_trades} profile={profile} />
        </SectionPanel>

        {/* Analyst Estimates */}
        {(estimates_annual.length > 0 || estimates_quarterly.length > 0) && (
          <SectionPanel title="Analyst Estimates">
            <EstimatesSection annual={estimates_annual} quarterly={estimates_quarterly} />
          </SectionPanel>
        )}

        {/* News */}
        {news.length > 0 && (
          <SectionPanel title="Latest News" defaultOpen={false}>
            <NewsSection news={news} />
          </SectionPanel>
        )}

        <div className="text-xs text-zinc-700 text-center py-4">
          Data from financialdatasets.ai &amp; yfinance · Cached 1h · Last computed {new Date(data.computed_at).toLocaleString()}
        </div>
      </main>
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
