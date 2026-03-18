"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useRef, useEffect } from "react";
import {
  BarChart2, ArrowLeft, Plus, ChevronDown,
  RefreshCw, Bell, LogOut, FlaskConical,
  Briefcase, ArrowRightLeft,
} from "lucide-react";
import { useAuth } from "@/components/AuthProvider";
import SearchAutocomplete from "@/components/research/SearchAutocomplete";
import { Portfolio } from "@/lib/api";

const tierBadge: Record<string, string> = {
  free: "bg-zinc-700 text-zinc-300",
  pro:  "bg-blue-900 text-blue-300",
  fund: "bg-amber-900 text-amber-300",
};

interface Props {
  // Left side
  showBack?: boolean;
  // Portfolio selector (dashboard only)
  portfolios?: Portfolio[];
  selectedPortfolio?: Portfolio | null;
  onSelectPortfolio?: (p: Portfolio) => void;
  onCreatePortfolio?: (name: string) => Promise<void>;
  // Right side actions
  onRefresh?: () => void;
  refreshing?: boolean;
  onAddPosition?: () => void;
  onSimulatorOpen?: () => void;
}

export default function GlobalHeader({
  showBack = false,
  portfolios,
  selectedPortfolio,
  onSelectPortfolio,
  onCreatePortfolio,
  onRefresh,
  refreshing = false,
  onAddPosition,
  onSimulatorOpen,
}: Props) {
  const { user, logout } = useAuth();
  const router = useRouter();

  const [portOpen,    setPortOpen]    = useState(false);
  const [addOpen,     setAddOpen]     = useState(false);
  const [userOpen,    setUserOpen]    = useState(false);
  const [newPortName, setNewPortName] = useState("");
  const [showCreate,  setShowCreate]  = useState(false);
  const [creating,    setCreating]    = useState(false);

  const addRef  = useRef<HTMLDivElement>(null);
  const userRef = useRef<HTMLDivElement>(null);

  // Close dropdowns on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (addRef.current  && !addRef.current.contains(e.target as Node))  setAddOpen(false);
      if (userRef.current && !userRef.current.contains(e.target as Node)) setUserOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleCreatePortfolio = async () => {
    if (!newPortName.trim() || !onCreatePortfolio) return;
    setCreating(true);
    try {
      await onCreatePortfolio(newPortName.trim());
      setNewPortName("");
      setShowCreate(false);
      setPortOpen(false);
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Failed to create portfolio");
    } finally {
      setCreating(false);
    }
  };

  const handleLogout = async () => {
    await logout();
    router.push("/login");
  };

  const showPortfolioSelector = !!(portfolios && onSelectPortfolio);
  const showAddMenu = !!(onAddPosition || onSimulatorOpen);

  return (
    <>
      <header className="fixed top-0 left-0 right-0 h-16 bg-zinc-950/95 backdrop-blur-sm border-b border-zinc-800 z-50 flex items-center px-4 sm:px-6 gap-3">

        {/* ── LEFT: Logo or Back ─────────────────────────────────── */}
        <div className="flex items-center gap-2 shrink-0">
          {showBack ? (
            <button
              onClick={() => router.push("/dashboard")}
              className="flex items-center gap-1.5 text-zinc-400 hover:text-zinc-200 transition-colors text-sm"
            >
              <ArrowLeft size={15} />
              <span className="hidden sm:inline">Dashboard</span>
            </button>
          ) : (
            <Link href="/dashboard" className="flex items-center gap-2 text-zinc-200 hover:text-white transition-colors">
              <div className="w-7 h-7 bg-blue-600 rounded-lg flex items-center justify-center shrink-0">
                <span className="text-white text-xs font-bold">A</span>
              </div>
              <span className="font-bold text-zinc-50 tracking-tight hidden sm:inline">AlphaDesk</span>
            </Link>
          )}
        </div>

        {/* ── Portfolio selector (dashboard only) ─────────────────── */}
        {showPortfolioSelector && (
          <>
            <div className="w-px h-5 bg-zinc-800 shrink-0" />
            <div className="relative shrink-0">
              <button
                onClick={() => setPortOpen(o => !o)}
                className="flex items-center gap-2 text-sm text-zinc-200 hover:text-zinc-50 bg-zinc-800/60 hover:bg-zinc-800 px-3 py-1.5 rounded-lg transition-colors border border-zinc-700/50"
              >
                <Briefcase size={13} className="text-zinc-400 shrink-0" />
                <span className="max-w-[140px] truncate hidden sm:inline">
                  {selectedPortfolio?.name ?? "Select portfolio"}
                </span>
                <ChevronDown size={13} className={`transition-transform text-zinc-400 ${portOpen ? "rotate-180" : ""}`} />
              </button>

              {portOpen && (
                <div className="absolute left-0 top-10 w-64 bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl z-50 overflow-hidden">
                  {portfolios!.map(p => (
                    <button
                      key={p.id}
                      onClick={() => { onSelectPortfolio!(p); setPortOpen(false); }}
                      className={`w-full text-left px-4 py-3 text-sm transition-colors flex items-center justify-between ${
                        selectedPortfolio?.id === p.id
                          ? "bg-blue-900/50 text-blue-300"
                          : "hover:bg-zinc-800 text-zinc-300"
                      }`}
                    >
                      <span className="truncate">{p.name}</span>
                      {selectedPortfolio?.id === p.id && (
                        <span className="w-2 h-2 rounded-full bg-blue-400 shrink-0" />
                      )}
                    </button>
                  ))}

                  {onCreatePortfolio && (
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
                  )}
                </div>
              )}
            </div>
          </>
        )}

        {/* ── CENTER spacer ──────────────────────────────────────── */}
        <div className="flex-1" />

        {/* ── RIGHT: Search + Actions + User ────────────────────── */}
        <div className="flex items-center gap-2">

          {/* Global search */}
          <div className="hidden sm:block w-52">
            <SearchAutocomplete placeholder="Search ⌘K" />
          </div>

          {/* + Add ▼ quick action menu */}
          {showAddMenu && (
            <div ref={addRef} className="relative">
              <button
                onClick={() => setAddOpen(o => !o)}
                className="flex items-center gap-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium px-3 py-1.5 rounded-lg transition-colors"
              >
                <Plus size={14} />
                <span className="hidden sm:inline">Add</span>
                <ChevronDown size={13} className={`transition-transform ${addOpen ? "rotate-180" : ""}`} />
              </button>

              {addOpen && (
                <div className="absolute right-0 top-10 w-48 bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl z-50 overflow-hidden py-1">
                  <button
                    onClick={() => setAddOpen(false)}
                    className="w-full flex items-center gap-2.5 px-3 py-2.5 text-sm text-zinc-500 cursor-not-allowed"
                    disabled
                    title="Coming soon"
                  >
                    <ArrowRightLeft size={14} className="text-zinc-600" />
                    Add Transaction
                  </button>
                  {onAddPosition && (
                    <button
                      onClick={() => { setAddOpen(false); onAddPosition(); }}
                      className="w-full flex items-center gap-2.5 px-3 py-2.5 text-sm text-zinc-300 hover:bg-zinc-800 transition-colors"
                    >
                      <Briefcase size={14} className="text-zinc-500" />
                      Add Position
                    </button>
                  )}
                  {onSimulatorOpen && (
                    <button
                      onClick={() => { setAddOpen(false); onSimulatorOpen(); }}
                      className="w-full flex items-center gap-2.5 px-3 py-2.5 text-sm text-zinc-300 hover:bg-zinc-800 transition-colors"
                    >
                      <FlaskConical size={14} className="text-zinc-500" />
                      Run Simulation
                    </button>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Refresh */}
          {onRefresh && (
            <button
              onClick={onRefresh}
              className="text-zinc-500 hover:text-zinc-300 transition-colors p-1.5 rounded-lg hover:bg-zinc-800"
              title="Refresh data"
            >
              <RefreshCw size={15} className={refreshing ? "animate-spin" : ""} />
            </button>
          )}

          {/* Notifications (placeholder) */}
          <button
            className="hidden sm:flex text-zinc-500 hover:text-zinc-300 transition-colors p-1.5 rounded-lg hover:bg-zinc-800"
            title="Notifications"
          >
            <Bell size={15} />
          </button>

          {/* User avatar + menu */}
          {user && (
            <div ref={userRef} className="relative">
              <button
                onClick={() => setUserOpen(o => !o)}
                className="w-8 h-8 rounded-full bg-zinc-700 hover:bg-zinc-600 transition-colors flex items-center justify-center text-zinc-200 text-sm font-semibold shrink-0"
                title={user.email}
              >
                {user.email?.[0]?.toUpperCase() ?? "U"}
              </button>

              {userOpen && (
                <div className="absolute right-0 top-10 w-56 bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl z-50 overflow-hidden">
                  <div className="px-4 py-3 border-b border-zinc-800">
                    <div className="text-sm text-zinc-200 font-medium truncate">{user.email}</div>
                    <span className={`inline-block mt-1 text-xs px-2 py-0.5 rounded-full font-medium ${tierBadge[user.tier ?? "free"]}`}>
                      {user.tier?.toUpperCase()}
                    </span>
                  </div>
                  <button
                    onClick={handleLogout}
                    className="w-full flex items-center gap-2.5 px-4 py-3 text-sm text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
                  >
                    <LogOut size={14} />
                    Sign out
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </header>

      {/* Backdrop to close portfolio dropdown */}
      {portOpen && (
        <div className="fixed inset-0 z-40" onClick={() => setPortOpen(false)} />
      )}
    </>
  );
}
