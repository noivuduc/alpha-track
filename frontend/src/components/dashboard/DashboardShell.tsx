"use client";
import dynamic from "next/dynamic";
import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  LayoutDashboard, BarChart2, ShieldAlert, FlaskConical,
  Plus, ChevronDown, LogOut, RefreshCw,
} from "lucide-react";
import { useAuth } from "@/components/AuthProvider";
import {
  portfolios as portApi, positions as posApi,
  Portfolio, Position, PortfolioAnalytics,
} from "@/lib/api";
import SearchAutocomplete from "@/components/research/SearchAutocomplete";

const OverviewTab   = dynamic(() => import("./OverviewTab"),   { ssr: false });
const HoldingsTab   = dynamic(() => import("./HoldingsTab"),   { ssr: false });
const RiskTab       = dynamic(() => import("./RiskTab"),       { ssr: false });
const SimulatorTab  = dynamic(() => import("./SimulatorTab"),  { ssr: false });

type Tab    = "overview" | "holdings" | "risk" | "simulator";
type Period = "1mo" | "3mo" | "6mo" | "ytd" | "1y" | "2y";

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: "overview",   label: "Overview",   icon: <LayoutDashboard size={16} /> },
  { id: "holdings",   label: "Holdings",   icon: <BarChart2 size={16} />       },
  { id: "risk",       label: "Risk",       icon: <ShieldAlert size={16} />     },
  { id: "simulator",  label: "Simulator",  icon: <FlaskConical size={16} />    },
];

const tierBadge: Record<string, string> = {
  free: "bg-zinc-700 text-zinc-300",
  pro:  "bg-blue-900 text-blue-300",
  fund: "bg-amber-900 text-amber-300",
};

export default function DashboardShell() {
  const { user, logout } = useAuth();
  const router = useRouter();

  const [tab,         setTab]         = useState<Tab>("overview");
  const period: Period = "1y";
  const [portfolios,  setPortfolios]  = useState<Portfolio[]>([]);
  const [selected,    setSelected]    = useState<Portfolio | null>(null);
  const [positions,   setPositions]   = useState<Position[]>([]);
  const [analytics,   setAnalytics]   = useState<PortfolioAnalytics | null>(null);
  const [portOpen,    setPortOpen]    = useState(false);
  const [newPortName, setNewPortName] = useState("");
  const [creating,    setCreating]    = useState(false);
  const [showCreate,  setShowCreate]  = useState(false);
  const [loadingData, setLoadingData] = useState(false);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);

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
    portApi.analytics(pid, p, force)
      .then(setAnalytics)
      .catch(e => { console.error(e); setAnalytics(null); })
      .finally(() => setAnalyticsLoading(false));
  }, []);

  useEffect(() => {
    if (!selected) return;
    loadPositions(selected.id);
    loadAnalytics(selected.id, period);
  }, [selected, period, loadPositions, loadAnalytics]);

  const handleRefresh = () => {
    if (!selected) return;
    loadPositions(selected.id);
    loadAnalytics(selected.id, period, true); // force = bypass cache
  };

  const handleLogout = async () => {
    await logout();
    router.push("/login");
  };

  const handleCreatePortfolio = async () => {
    if (!newPortName.trim()) return;
    setCreating(true);
    try {
      const p = await portApi.create({
        name: newPortName.trim(),
        is_default: portfolios.length === 0,
        currency: "USD",
      });
      setPortfolios(prev => [...prev, p]);
      setSelected(p);
      setNewPortName("");
      setShowCreate(false);
      setPortOpen(false);
    } catch (e: any) {
      alert(e.message || "Failed to create portfolio");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950 flex flex-col">
      {/* ── Top nav ──────────────────────────────────────── */}
      <header className="border-b border-zinc-800 bg-zinc-900/80 backdrop-blur-sm sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 flex items-center justify-between h-14">

          {/* Logo */}
          <div className="flex items-center gap-3">
            <div className="w-7 h-7 bg-blue-600 rounded-lg flex items-center justify-center shrink-0">
              <span className="text-white text-xs font-bold">A</span>
            </div>
            <span className="font-bold text-zinc-50 tracking-tight hidden sm:block">AlphaDesk</span>
          </div>

          {/* Portfolio selector */}
          <div className="relative">
            <button
              onClick={() => setPortOpen(o => !o)}
              className="flex items-center gap-2 text-sm text-zinc-200 hover:text-zinc-50 bg-zinc-800 hover:bg-zinc-700 px-3 py-1.5 rounded-lg transition-colors"
            >
              <span className="max-w-[160px] truncate">{selected?.name ?? "Select portfolio"}</span>
              <ChevronDown size={14} className={`transition-transform ${portOpen ? "rotate-180" : ""}`} />
            </button>

            {portOpen && (
              <div className="absolute left-1/2 -translate-x-1/2 top-10 w-64 bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl z-50 overflow-hidden">
                {portfolios.map(p => (
                  <button
                    key={p.id}
                    onClick={() => { setSelected(p); setPortOpen(false); }}
                    className={`w-full text-left px-4 py-3 text-sm transition-colors flex items-center justify-between ${
                      selected?.id === p.id
                        ? "bg-blue-900/50 text-blue-300"
                        : "hover:bg-zinc-800 text-zinc-300"
                    }`}
                  >
                    <span className="truncate">{p.name}</span>
                    {selected?.id === p.id && <span className="w-2 h-2 rounded-full bg-blue-400 shrink-0" />}
                  </button>
                ))}

                <div className="border-t border-zinc-800 p-3">
                  {showCreate ? (
                    <div className="space-y-2">
                      <input
                        value={newPortName}
                        onChange={e => setNewPortName(e.target.value)}
                        onKeyDown={e => e.key === "Enter" && handleCreatePortfolio()}
                        autoFocus
                        placeholder="Portfolio name"
                        className="w-full bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-50 placeholder:text-zinc-600 focus:outline-none focus:border-blue-500"
                      />
                      <div className="flex gap-2">
                        <button
                          onClick={handleCreatePortfolio}
                          disabled={creating}
                          className="flex-1 bg-blue-600 hover:bg-blue-500 text-white text-xs py-1.5 rounded-lg transition-colors disabled:opacity-50"
                        >
                          {creating ? "Creating…" : "Create"}
                        </button>
                        <button
                          onClick={() => { setShowCreate(false); setNewPortName(""); }}
                          className="flex-1 bg-zinc-700 hover:bg-zinc-600 text-zinc-300 text-xs py-1.5 rounded-lg transition-colors"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <button
                      onClick={() => setShowCreate(true)}
                      className="w-full flex items-center justify-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-200 py-1 transition-colors"
                    >
                      <Plus size={12} /> New portfolio
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Right: refresh + user + logout */}
          <div className="flex items-center gap-2">
            {/* Ticker research search */}
            <div className="hidden sm:block">
              <SearchAutocomplete placeholder="Research ticker…" />
            </div>

            <button
              onClick={handleRefresh}
              className="text-zinc-500 hover:text-zinc-300 transition-colors p-1.5 rounded-lg hover:bg-zinc-800"
              title="Refresh data"
            >
              <RefreshCw size={15} className={(loadingData || analyticsLoading) ? "animate-spin" : ""} />
            </button>

            <div className="hidden sm:flex items-center gap-2">
              <span className="text-zinc-400 text-sm truncate max-w-[140px]">{user?.email}</span>
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${tierBadge[user?.tier ?? "free"]}`}>
                {user?.tier?.toUpperCase()}
              </span>
            </div>

            <button
              onClick={handleLogout}
              className="text-zinc-500 hover:text-zinc-300 transition-colors p-1.5 rounded-lg hover:bg-zinc-800"
              title="Sign out"
            >
              <LogOut size={15} />
            </button>
          </div>
        </div>
      </header>

      {/* ── Tab bar ──────────────────────────────────────── */}
      <div className="border-b border-zinc-800 bg-zinc-900/40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 flex gap-1 overflow-x-auto scrollbar-thin">
          {TABS.map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-2 px-4 py-3 text-sm font-medium whitespace-nowrap border-b-2 transition-colors ${
                tab === t.id
                  ? "border-blue-500 text-blue-400"
                  : "border-transparent text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {t.icon}
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── Content ──────────────────────────────────────── */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-6">
        {!selected ? (
          <div className="flex flex-col items-center justify-center h-64">
            <p className="text-lg font-medium text-zinc-400 mb-1">No portfolio yet</p>
            <p className="text-sm text-zinc-500">Create one using the selector above</p>
          </div>
        ) : (
          <>
            {tab === "overview"     && (
              <OverviewTab
                analytics={analytics}
                positions={positions}
                loading={analyticsLoading}
                period={period}
              />
            )}
            {tab === "holdings"     && (
              <HoldingsTab
                portfolioId={selected.id}
                data={positions}
                analytics={analytics}
                onRefresh={() => {
                  loadPositions(selected.id);
                  loadAnalytics(selected.id, period, true);
                }}
              />
            )}
            {tab === "risk" && (
              <RiskTab
                analytics={analytics}
                loading={analyticsLoading}
                period={period}
              />
            )}
            {tab === "simulator" && (
              <SimulatorTab portfolioId={selected.id} />
            )}
          </>
        )}
      </main>

      {portOpen && (
        <div className="fixed inset-0 z-30" onClick={() => setPortOpen(false)} />
      )}
    </div>
  );
}
