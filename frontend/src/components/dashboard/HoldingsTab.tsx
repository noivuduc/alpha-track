"use client";
import React, { useState, useEffect, useMemo, useCallback } from "react";
import {
  ChevronRight, ChevronDown, Plus, Trash2, X, Check,
  ArrowUp, ArrowDown, Pencil, TrendingUp, TrendingDown,
} from "lucide-react";
import { AreaChart, Area, ResponsiveContainer } from "recharts";
import SectorDonut, { SectorSlice } from "@/components/charts/SectorDonut";
import {
  Position, Transaction, PortfolioAnalytics, ContributionEntry, HistoryBar,
  positions as posApi, transactions as txnApi, market,
} from "@/lib/api";
import { fmt, fmtCurrency, fmtPct, gainClass } from "@/lib/portfolio-math";
import DatePicker from "@/components/ui/DatePicker";

// ── Module-level sector cache (survives re-renders) ────────────────────────────
const _sectorCache: Record<string, string | null> = {};

async function fetchSector(ticker: string): Promise<string | null> {
  if (ticker in _sectorCache) return _sectorCache[ticker];
  try {
    const p = await market.profile(ticker) as Record<string, unknown>;
    const s = (p?.sector ?? p?.Sector) as string | undefined ?? null;
    _sectorCache[ticker] = s;   // cache success (even null = "ticker has no sector")
    return s;
  } catch (e) {
    // Auth / transient errors: do NOT cache so the next render retries after login
    const status = (e as { status?: number })?.status;
    if (!status || status >= 400) return null;
    _sectorCache[ticker] = null;
    return null;
  }
}

// ── Types ──────────────────────────────────────────────────────────────────────
type SortKey = "ticker" | "shares" | "cost_basis" | "current_price" | "current_value" | "gain_loss" | "gain_loss_pct" | "weight_pct";
type Filter  = "all" | "winners" | "losers";

interface Props {
  portfolioId: string;
  data:        Position[];
  analytics?:  PortfolioAnalytics | null;
  onRefresh:   () => void;
}

interface TxnForm {
  ticker:    string;
  side:      "buy" | "sell";
  shares:    string;
  price:     string;
  traded_at: string;
}

interface EditForm {
  shares:    string;
  price:     string;
  traded_at: string;
}

// ── Constants ──────────────────────────────────────────────────────────────────
const COLS: { key: SortKey; label: string; align: "left" | "right"; title?: string }[] = [
  { key: "ticker",        label: "Ticker",    align: "left"  },
  { key: "shares",        label: "Shares",    align: "right" },
  { key: "cost_basis",    label: "Avg Cost",  align: "right" },
  { key: "current_price", label: "Price",     align: "right" },
  { key: "current_value", label: "Mkt Value", align: "right" },
  { key: "gain_loss",     label: "Unreal P&L", align: "right", title: "Unrealized dollar gain/loss vs average cost" },
  { key: "gain_loss_pct", label: "Simple Ret", align: "right", title: "Simple return on cost basis: (current − cost) / cost. Not time-weighted; differs from Annualized Return on Overview." },
  { key: "weight_pct",    label: "Weight",    align: "right" },
];

const todayStr = () => new Date().toISOString().slice(0, 10);

// ── Utilities ──────────────────────────────────────────────────────────────────

/** Compact dollar value: 143456 → "$143.5K" */
function fmtK(n: number | null | undefined): string {
  if (n == null) return "—";
  const abs  = Math.abs(n);
  const sign = n < 0 ? "-" : "";
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(1)}K`;
  return `${sign}$${abs.toFixed(0)}`;
}

/** FIFO realized P&L from transaction list for a single ticker. */
function computeRealizedPnl(txns: Transaction[]): number {
  const sorted = [...txns].sort((a, b) => a.traded_at.localeCompare(b.traded_at));
  const lots: { shares: number; price: number }[] = [];
  let realized = 0;
  for (const t of sorted) {
    if (t.side === "buy") {
      lots.push({ shares: Number(t.shares), price: Number(t.price) });
    } else {
      let remaining = Number(t.shares);
      while (remaining > 0.0001 && lots.length > 0) {
        const lot     = lots[0];
        const matched = Math.min(lot.shares, remaining);
        realized     += matched * (Number(t.price) - lot.price);
        lot.shares   -= matched;
        remaining    -= matched;
        if (lot.shares < 0.0001) lots.shift();
      }
    }
  }
  return realized;
}

/** Recompute position from full transaction list using FIFO. */
function reconcileFromTxns(txns: Transaction[]): { shares: number; costBasis: number } | null {
  const sorted = [...txns].sort((a, b) => a.traded_at.localeCompare(b.traded_at));
  const lots: { shares: number; price: number }[] = [];
  for (const t of sorted) {
    if (t.side === "buy") {
      lots.push({ shares: Number(t.shares), price: Number(t.price) });
    } else {
      let remaining = Number(t.shares);
      while (remaining > 0.0001 && lots.length > 0) {
        const lot     = lots[0];
        const matched = Math.min(lot.shares, remaining);
        lot.shares   -= matched;
        remaining    -= matched;
        if (lot.shares < 0.0001) lots.shift();
      }
    }
  }
  const totalShares = lots.reduce((s, l) => s + l.shares, 0);
  if (totalShares < 0.0001) return null;
  const totalCost   = lots.reduce((s, l) => s + l.shares * l.price, 0);
  return { shares: totalShares, costBasis: totalCost / totalShares };
}

// ── Ticker logo ────────────────────────────────────────────────────────────────
// Tries FMP → Parqet → colored-letter badge

function TickerLogo({ ticker }: { ticker: string }) {
  const [srcIdx, setSrcIdx] = useState(0);

  const color = useMemo(() => {
    const hue = ticker.split("").reduce((n, c) => n + c.charCodeAt(0), 0) % 360;
    return `hsl(${hue},55%,38%)`;
  }, [ticker]);

  const sources = useMemo(() => [
    `https://financialmodelingprep.com/image-stock/${ticker}.png`,
    `https://assets.parqet.com/logos/symbol/${ticker}?format=png`,
  ], [ticker]);

  if (srcIdx >= sources.length) {
    return (
      <div
        className="w-6 h-6 rounded-full flex items-center justify-center text-[9px] font-bold text-white shrink-0"
        style={{ backgroundColor: color }}
      >
        {ticker.slice(0, 2)}
      </div>
    );
  }
  return (
    <img
      src={sources[srcIdx]}
      alt={ticker}
      className="w-6 h-6 rounded-full object-contain bg-zinc-800 shrink-0"
      onError={() => setSrcIdx(i => i + 1)}
    />
  );
}

// ── Mini price chart ───────────────────────────────────────────────────────────

function MiniPriceChart({ ticker }: { ticker: string }) {
  const [bars,    setBars]    = useState<HistoryBar[] | null>(null);
  const [period,  setPeriod]  = useState<"3mo" | "6mo">("3mo");

  useEffect(() => {
    setBars(null);
    market.history(ticker, period)
      .then(r => setBars(r.data))
      .catch(() => setBars([]));
  }, [ticker, period]);

  const summary = useMemo(() => {
    if (!bars || bars.length < 2) return null;
    const first  = bars[0].close;
    const last   = bars[bars.length - 1].close;
    const retPct = ((last - first) / first) * 100;
    return { retPct, isUp: retPct >= 0 };
  }, [bars]);

  return (
    <div>
      <div className="flex items-center gap-3 mb-1.5">
        {/* Period toggle */}
        <div className="flex gap-1 bg-zinc-800/60 rounded-md p-0.5">
          {(["3mo", "6mo"] as const).map(p => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`px-2 py-0.5 text-[10px] rounded font-medium transition-colors ${
                period === p ? "bg-zinc-600 text-white" : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {p === "3mo" ? "3M" : "6M"}
            </button>
          ))}
        </div>
        {summary && (
          <span className={`text-xs font-mono font-semibold ${gainClass(summary.retPct)}`}>
            {summary.retPct >= 0 ? "+" : ""}{summary.retPct.toFixed(2)}%
          </span>
        )}
      </div>

      {bars === null ? (
        <div className="h-20 flex items-center justify-center">
          <div className="w-4 h-4 border border-zinc-700 border-t-zinc-400 rounded-full animate-spin" />
        </div>
      ) : bars.length === 0 ? (
        <div className="h-20 flex items-center justify-center text-xs text-zinc-700">No data</div>
      ) : (
        <div className="h-20">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={bars} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id={`mini-grad-${ticker}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor={summary?.isUp ? "#10b981" : "#ef4444"} stopOpacity={0.25} />
                  <stop offset="95%" stopColor={summary?.isUp ? "#10b981" : "#ef4444"} stopOpacity={0}    />
                </linearGradient>
              </defs>
              <Area
                type="monotone"
                dataKey="close"
                stroke={summary?.isUp ? "#10b981" : "#ef4444"}
                strokeWidth={1.5}
                fill={`url(#mini-grad-${ticker})`}
                dot={false}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

// ── Sector allocation panel ────────────────────────────────────────────────────

function SectorPanel({ positions, sectorMap }: { positions: Position[]; sectorMap: Record<string, string> }) {
  const totalValue = positions.reduce((s, p) => s + (p.current_value ?? 0), 0);

  const slices: SectorSlice[] = useMemo(() => {
    const groups: Record<string, number> = {};
    for (const p of positions) {
      const sector = sectorMap[p.ticker] || "Other";
      groups[sector] = (groups[sector] ?? 0) + (p.current_value ?? 0);
    }
    return Object.entries(groups)
      .map(([name, dollarVal]) => ({
        name,
        value:  totalValue > 0 ? (dollarVal / totalValue) * 100 : 0,
        dollar: dollarVal,
      }))
      .sort((a, b) => b.value - a.value);
  }, [positions, sectorMap, totalValue]);

  if (!slices.length) return null;

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
      <h3 className="text-[10px] font-semibold text-zinc-500 uppercase tracking-widest mb-1">
        Sector Allocation
      </h3>
      <SectorDonut data={slices} height={200} showLegend />
    </div>
  );
}

// ── Contribution to return panel ───────────────────────────────────────────────

function ContributionPanel({ contribution }: { contribution: ContributionEntry[] }) {
  const sorted = useMemo(
    () => [...contribution].sort((a, b) => b.contribution_pct - a.contribution_pct),
    [contribution],
  );
  const maxAbs = Math.max(...sorted.map(c => Math.abs(c.contribution_pct)), 0.01);

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
      <h3 className="text-[10px] font-semibold text-zinc-500 uppercase tracking-widest mb-3">
        Contribution to Return
      </h3>
      <div className="space-y-2">
        {sorted.map(c => {
          const barPct = (Math.abs(c.contribution_pct) / maxAbs) * 100;
          const isPos  = c.contribution_pct >= 0;
          return (
            <div key={c.ticker} className="flex items-center gap-2">
              <span className="text-xs font-mono text-zinc-500 w-14 shrink-0">{c.ticker}</span>
              {/* Centered diverging bar */}
              <div className="flex-1 flex h-4 items-center">
                {/* Left half (negative) */}
                <div className="w-1/2 flex justify-end pr-px">
                  {!isPos && (
                    <div
                      className="h-3 bg-red-500/70 rounded-l-sm"
                      style={{ width: `${barPct}%` }}
                    />
                  )}
                </div>
                {/* Center axis */}
                <div className="w-px h-4 bg-zinc-700 shrink-0" />
                {/* Right half (positive) */}
                <div className="w-1/2 pl-px">
                  {isPos && (
                    <div
                      className="h-3 bg-emerald-500/70 rounded-r-sm"
                      style={{ width: `${barPct}%` }}
                    />
                  )}
                </div>
              </div>
              <span className={`text-xs font-mono tabular-nums w-14 text-right shrink-0 ${gainClass(c.contribution_pct)}`}>
                {c.contribution_pct >= 0 ? "+" : ""}{c.contribution_pct.toFixed(2)}%
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Position summary panel ─────────────────────────────────────────────────────

interface SummaryProps {
  pos:         Position;
  realizedPnl: number;
}

function PositionSummaryPanel({ pos, realizedPnl }: SummaryProps) {
  const totalReturn = pos.current_value != null && pos.cost_basis > 0 && pos.shares > 0
    ? ((pos.current_value - pos.shares * pos.cost_basis + realizedPnl) / (pos.shares * pos.cost_basis)) * 100
    : null;

  const stats = [
    { label: "Shares Held",    value: fmt(pos.shares, pos.shares % 1 === 0 ? 0 : 4), color: "" },
    { label: "Market Value",   value: fmtCurrency(pos.current_value),                 color: "" },
    { label: "Avg Cost",       value: `$${fmt(pos.cost_basis)}`,                      color: "" },
    { label: "Unrealized P&L", value: pos.gain_loss != null ? `${pos.gain_loss >= 0 ? "+" : ""}${fmtCurrency(pos.gain_loss)}` : "—", color: gainClass(pos.gain_loss) },
    { label: "Current Price",  value: pos.current_price != null ? `$${fmt(pos.current_price)}` : "—", color: "" },
    { label: "Realized P&L",   value: realizedPnl !== 0 ? `${realizedPnl >= 0 ? "+" : ""}${fmtCurrency(realizedPnl)}` : "—", color: gainClass(realizedPnl || 0) },
    { label: "P&L %",          value: fmtPct(pos.gain_loss_pct), color: gainClass(pos.gain_loss_pct) },
    { label: "Total Return",   value: totalReturn != null ? fmtPct(totalReturn) : "—", color: gainClass(totalReturn) },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-3 py-3 px-1">
      {stats.map(s => (
        <div key={s.label}>
          <div className="text-[10px] text-zinc-600 uppercase tracking-wider">{s.label}</div>
          <div className={`text-sm font-mono font-semibold tabular-nums mt-0.5 ${s.color || "text-zinc-200"}`}>
            {s.value}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Transaction table ──────────────────────────────────────────────────────────

interface TxnTableProps {
  txns:        Transaction[];
  portfolioId: string;
  ticker:      string;
  positions:   Position[];
  onSaved:     (updatedTxns: Transaction[]) => void;
  onAddClick:  () => void;
}

function TransactionTable({ txns, portfolioId, ticker, positions, onSaved, onAddClick }: TxnTableProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm,  setEditForm]  = useState<EditForm>({ shares: "", price: "", traded_at: "" });
  const [saving,    setSaving]    = useState(false);
  const [deleting,  setDeleting]  = useState<string | null>(null);
  const [editError, setEditError] = useState("");

  const startEdit = (t: Transaction) => {
    setEditingId(t.id);
    setEditForm({
      shares:    String(t.shares),
      price:     String(t.price),
      traded_at: t.traded_at.slice(0, 10),
    });
    setEditError("");
  };

  const cancelEdit = () => { setEditingId(null); setEditError(""); };

  const saveEdit = async () => {
    const nShares = parseFloat(editForm.shares);
    const nPrice  = parseFloat(editForm.price);
    if (isNaN(nShares) || isNaN(nPrice) || nShares <= 0 || nPrice <= 0 || !editForm.traded_at) {
      setEditError("Shares and price must be positive"); return;
    }
    setSaving(true);
    try {
      await txnApi.update(portfolioId, editingId!, {
        shares:    nShares,
        price:     nPrice,
        traded_at: new Date(editForm.traded_at + "T12:00:00Z").toISOString(),
      });
      const fresh = await txnApi.list(portfolioId);
      await reconcilePosition(ticker, fresh, positions, portfolioId);
      setEditingId(null);
      onSaved(fresh);
    } catch (e: unknown) {
      setEditError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const deleteTxn = async (txnId: string) => {
    setDeleting(txnId);
    try {
      await txnApi.remove(portfolioId, txnId);
      const fresh = await txnApi.list(portfolioId);
      await reconcilePosition(ticker, fresh, positions, portfolioId);
      onSaved(fresh);
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setDeleting(null);
    }
  };

  if (!txns.length) {
    return (
      <div className="flex items-center justify-between py-2">
        <p className="text-xs text-zinc-700">No transactions recorded.</p>
        <button onClick={onAddClick} className="text-xs text-blue-500 hover:text-blue-400 flex items-center gap-1">
          <Plus size={11} /> Add
        </button>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-semibold text-zinc-600 uppercase tracking-widest">Transactions</span>
        <button onClick={onAddClick} className="text-xs text-blue-500 hover:text-blue-400 flex items-center gap-1 transition-colors">
          <Plus size={11} /> Add
        </button>
      </div>

      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-zinc-800">
            <th className="text-left text-zinc-600 font-semibold pb-1.5 pr-4">Date</th>
            <th className="text-left text-zinc-600 font-semibold pb-1.5 pr-4">Type</th>
            <th className="text-right text-zinc-600 font-semibold pb-1.5 pr-4">Shares</th>
            <th className="text-right text-zinc-600 font-semibold pb-1.5 pr-4">Price</th>
            <th className="text-right text-zinc-600 font-semibold pb-1.5 pr-4">Total</th>
            <th className="w-20 text-right text-zinc-600 font-semibold pb-1.5" />
          </tr>
        </thead>
        <tbody>
          {txns.map(t => {
            const isEditing = editingId === t.id;
            return (
              <tr
                key={t.id}
                className={`border-b border-zinc-900 last:border-0 group ${isEditing ? "bg-zinc-900/60" : ""}`}
              >
                {isEditing ? (
                  <>
                    <td className="py-1.5 pr-3">
                      <DatePicker
                        value={editForm.traded_at}
                        onChange={v => setEditForm(f => ({ ...f, traded_at: v }))}
                        max={todayStr()}
                        className="text-xs"
                      />
                    </td>
                    <td className="py-1.5 pr-3">
                      <span className={`font-semibold ${t.side === "buy" ? "text-emerald-500" : "text-red-500"}`}>
                        {t.side.toUpperCase()}
                      </span>
                    </td>
                    <td className="py-1.5 pr-3">
                      <input
                        type="number" min="0" step="any"
                        value={editForm.shares}
                        onChange={e => setEditForm(f => ({ ...f, shares: e.target.value }))}
                        className="w-20 bg-zinc-950 border border-zinc-700 rounded px-2 py-1 text-zinc-50 text-right focus:outline-none focus:border-blue-500"
                      />
                    </td>
                    <td className="py-1.5 pr-3">
                      <input
                        type="number" min="0" step="any"
                        value={editForm.price}
                        onChange={e => setEditForm(f => ({ ...f, price: e.target.value }))}
                        className="w-24 bg-zinc-950 border border-zinc-700 rounded px-2 py-1 text-zinc-50 text-right focus:outline-none focus:border-blue-500"
                      />
                    </td>
                    <td className="py-1.5 pr-3 text-right text-zinc-600">
                      {editForm.shares && editForm.price
                        ? fmtK(parseFloat(editForm.shares) * parseFloat(editForm.price))
                        : "—"}
                    </td>
                    <td className="py-1.5 text-right">
                      <div className="flex items-center justify-end gap-2">
                        {editError && <span className="text-red-400 text-[10px]">{editError}</span>}
                        <button onClick={saveEdit} disabled={saving} className="text-emerald-500 hover:text-emerald-400 disabled:opacity-50">
                          {saving
                            ? <span className="w-3 h-3 border border-emerald-500 border-t-transparent rounded-full animate-spin inline-block" />
                            : <Check size={13} />}
                        </button>
                        <button onClick={cancelEdit} className="text-zinc-500 hover:text-zinc-300">
                          <X size={13} />
                        </button>
                      </div>
                    </td>
                  </>
                ) : (
                  <>
                    <td className="font-mono text-zinc-500 py-1.5 pr-4">{t.traded_at.slice(0, 10)}</td>
                    <td className="py-1.5 pr-4">
                      <span className={`font-semibold ${t.side === "buy" ? "text-emerald-500" : "text-red-500"}`}>
                        {t.side.toUpperCase()}
                      </span>
                    </td>
                    <td className="font-mono tabular-nums text-zinc-400 text-right py-1.5 pr-4">
                      {fmt(Number(t.shares), Number(t.shares) % 1 === 0 ? 0 : 4)}
                    </td>
                    <td className="font-mono tabular-nums text-zinc-400 text-right py-1.5 pr-4">
                      ${fmt(Number(t.price))}
                    </td>
                    <td className="font-mono tabular-nums text-zinc-600 text-right py-1.5 pr-4">
                      {fmtK(Number(t.shares) * Number(t.price))}
                    </td>
                    <td className="py-1.5 text-right">
                      <div className="flex items-center justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button onClick={() => startEdit(t)} className="text-zinc-600 hover:text-zinc-300 transition-colors">
                          <Pencil size={12} />
                        </button>
                        <button
                          onClick={() => deleteTxn(t.id)}
                          disabled={deleting === t.id}
                          className="text-zinc-600 hover:text-red-400 transition-colors disabled:opacity-50"
                        >
                          {deleting === t.id
                            ? <span className="w-3 h-3 border border-red-400 border-t-transparent rounded-full animate-spin inline-block" />
                            : <Trash2 size={12} />}
                        </button>
                      </div>
                    </td>
                  </>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Reconcile helper ───────────────────────────────────────────────────────────

async function reconcilePosition(
  ticker:      string,
  allTxns:     Transaction[],
  positions:   Position[],
  portfolioId: string,
) {
  const tickerTxns = allTxns.filter(t => t.ticker === ticker);
  const rec        = reconcileFromTxns(tickerTxns);
  const existing   = positions.find(p => p.ticker === ticker);
  if (!existing) return;

  if (!rec) {
    await posApi.delete(portfolioId, existing.id);
  } else {
    await posApi.update(portfolioId, existing.id, {
      shares:     rec.shares,
      cost_basis: parseFloat(rec.costBasis.toFixed(6)),
    });
  }
}

// ── Expanded panel ─────────────────────────────────────────────────────────────

interface ExpandedPanelProps {
  pos:          Position;
  portfolioId:  string;
  allTxns:      Transaction[];
  positions:    Position[];
  contribution: number | null;
  onTxnsChange: (fresh: Transaction[]) => void;
  onQuickAction:(ticker: string, side: "buy" | "sell") => void;
  onRefresh:    () => void;
}

function ExpandedPanel({
  pos, portfolioId, allTxns, positions,
  contribution, onTxnsChange, onQuickAction, onRefresh,
}: ExpandedPanelProps) {
  const tickerTxns  = useMemo(
    () => allTxns.filter(t => t.ticker === pos.ticker)
                 .sort((a, b) => b.traded_at.localeCompare(a.traded_at)),
    [allTxns, pos.ticker],
  );
  const realizedPnl = useMemo(() => computeRealizedPnl(tickerTxns), [tickerTxns]);

  const handleSaved = useCallback((fresh: Transaction[]) => {
    onTxnsChange(fresh);
    onRefresh();
  }, [onTxnsChange, onRefresh]);

  return (
    <div className="bg-zinc-950/50 border-t border-zinc-800/60">
      <div className="pl-10 pr-6 py-4 space-y-5">

        {/* Quick actions */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => onQuickAction(pos.ticker, "buy")}
            className="flex items-center gap-1.5 text-xs font-semibold text-emerald-400 border border-emerald-800 hover:bg-emerald-900/30 px-3 py-1.5 rounded-lg transition-colors"
          >
            <TrendingUp size={12} /> Buy More
          </button>
          <button
            onClick={() => onQuickAction(pos.ticker, "sell")}
            className="flex items-center gap-1.5 text-xs font-semibold text-red-400 border border-red-900 hover:bg-red-900/20 px-3 py-1.5 rounded-lg transition-colors"
          >
            <TrendingDown size={12} /> Sell
          </button>
        </div>

        {/* Mini price chart */}
        <div>
          <p className="text-[10px] font-semibold text-zinc-600 uppercase tracking-widest mb-1.5">
            Price History
          </p>
          <MiniPriceChart ticker={pos.ticker} />
        </div>

        {/* Position summary */}
        <div>
          <p className="text-[10px] font-semibold text-zinc-600 uppercase tracking-widest mb-1">
            Position Summary
          </p>
          <div className="border border-zinc-800/60 rounded-lg px-4">
            <PositionSummaryPanel pos={pos} realizedPnl={realizedPnl} />
          </div>
        </div>

        {/* Contribution bar */}
        {contribution != null && (
          <div>
            <p className="text-[10px] font-semibold text-zinc-600 uppercase tracking-widest mb-1.5">
              Contribution to Return
            </p>
            <div className="flex items-center gap-3">
              <div className="flex-1 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${contribution >= 0 ? "bg-emerald-500" : "bg-red-500"}`}
                  style={{ width: `${Math.min(Math.abs(contribution) * 10, 100)}%` }}
                />
              </div>
              <span className={`text-xs font-mono font-semibold tabular-nums ${gainClass(contribution)}`}>
                {fmtPct(contribution)}
              </span>
            </div>
          </div>
        )}

        {/* Transaction table */}
        <div className="[&_tr:hover_td:last-child>div]:opacity-100">
          <TransactionTable
            txns={tickerTxns}
            portfolioId={portfolioId}
            ticker={pos.ticker}
            positions={positions}
            onSaved={handleSaved}
            onAddClick={() => onQuickAction(pos.ticker, "buy")}
          />
        </div>

      </div>
    </div>
  );
}

// ── Add Transaction form ───────────────────────────────────────────────────────

interface AddFormProps {
  form:     TxnForm;
  setForm:  React.Dispatch<React.SetStateAction<TxnForm>>;
  adding:   boolean;
  error:    string;
  onSubmit: () => void;
  onCancel: () => void;
}

function AddTransactionForm({ form, setForm, adding, error, onSubmit, onCancel }: AddFormProps) {
  return (
    <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold text-zinc-300">New Transaction</h4>
        <button onClick={onCancel} className="text-zinc-600 hover:text-zinc-400">
          <X size={14} />
        </button>
      </div>

      <div className="flex flex-wrap gap-3 items-end">
        {/* Ticker */}
        <div>
          <label className="block text-xs text-zinc-500 mb-1">Ticker</label>
          <input
            value={form.ticker}
            onChange={e => setForm(f => ({ ...f, ticker: e.target.value.toUpperCase() }))}
            placeholder="AAPL"
            className="w-24 bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-2 text-zinc-50 text-sm font-mono placeholder:normal-case placeholder:text-zinc-600 focus:outline-none focus:border-blue-500"
          />
        </div>

        {/* BUY / SELL toggle */}
        <div>
          <label className="block text-xs text-zinc-500 mb-1">Type</label>
          <div className="flex rounded-lg overflow-hidden border border-zinc-700">
            {(["buy", "sell"] as const).map(s => (
              <button
                key={s}
                onClick={() => setForm(f => ({ ...f, side: s }))}
                className={`px-4 py-2 text-sm font-semibold transition-colors ${
                  form.side === s
                    ? s === "buy" ? "bg-emerald-600 text-white" : "bg-red-600 text-white"
                    : "bg-zinc-950 text-zinc-500 hover:text-zinc-300"
                }`}
              >
                {s.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        {/* Shares */}
        <div>
          <label className="block text-xs text-zinc-500 mb-1">Shares</label>
          <input
            type="number" min="0" step="any"
            value={form.shares}
            onChange={e => setForm(f => ({ ...f, shares: e.target.value }))}
            placeholder="100"
            className="w-28 bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-2 text-zinc-50 text-sm placeholder:text-zinc-600 focus:outline-none focus:border-blue-500"
          />
        </div>

        {/* Price */}
        <div>
          <label className="block text-xs text-zinc-500 mb-1">Price ($)</label>
          <input
            type="number" min="0" step="any"
            value={form.price}
            onChange={e => setForm(f => ({ ...f, price: e.target.value }))}
            placeholder="150.00"
            className="w-32 bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-2 text-zinc-50 text-sm placeholder:text-zinc-600 focus:outline-none focus:border-blue-500"
          />
        </div>

        {/* Date */}
        <div>
          <label className="block text-xs text-zinc-500 mb-1">Date</label>
          <DatePicker
            value={form.traded_at}
            onChange={v => setForm(f => ({ ...f, traded_at: v }))}
            max={todayStr()}
          />
        </div>

        <button
          onClick={onSubmit}
          disabled={adding}
          className="flex items-center gap-1.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          {adding
            ? <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            : <Check size={14} />}
          Add
        </button>
      </div>

      {error && <p className="text-red-400 text-xs">{error}</p>}
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function HoldingsTab({ portfolioId, data, analytics, onRefresh }: Props) {
  // ── Sort & filter ──────────────────────────────────────────────────────────
  const [sortKey, setSortKey] = useState<SortKey>("current_value");
  const [sortDir, setSortDir] = useState<1 | -1>(-1);
  const [filter,  setFilter]  = useState<Filter>("all");

  // ── Row expansion ──────────────────────────────────────────────────────────
  const [expandedTicker, setExpandedTicker] = useState<string | null>(null);

  // ── Transactions ───────────────────────────────────────────────────────────
  const [allTxns,    setAllTxns]    = useState<Transaction[]>([]);
  const [txnsLoaded, setTxnsLoaded] = useState(false);

  const loadTxns = useCallback(() => {
    txnApi.list(portfolioId)
      .then(list => { setAllTxns(list); setTxnsLoaded(true); })
      .catch(() => setTxnsLoaded(true));
  }, [portfolioId]);

  useEffect(() => { loadTxns(); }, [loadTxns]);

  // ── Sector data ────────────────────────────────────────────────────────────
  const [sectorMap, setSectorMap] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!data.length) return;
    const tickers  = data.map(p => p.ticker);
    const toFetch  = tickers.filter(t => !(t in _sectorCache));

    const applyCache = () => {
      const m: Record<string, string> = {};
      for (const t of tickers) {
        if (_sectorCache[t]) m[t] = _sectorCache[t]!;
      }
      setSectorMap(m);
    };

    if (!toFetch.length) { applyCache(); return; }
    Promise.allSettled(toFetch.map(t => fetchSector(t))).then(applyCache);
  }, [data]);

  // ── Add transaction form ───────────────────────────────────────────────────
  const [showAdd, setShowAdd] = useState(false);
  const [addForm, setAddForm] = useState<TxnForm>({
    ticker: "", side: "buy", shares: "", price: "", traded_at: todayStr(),
  });
  const [adding, setAdding] = useState(false);
  const [error,  setError]  = useState("");

  // ── Position delete ────────────────────────────────────────────────────────
  const [deletingPos, setDeletingPos] = useState<string | null>(null);

  // ── Contribution lookup ────────────────────────────────────────────────────
  // Prefer analytics.contribution (compute_engine, TWR-consistent) when loaded.
  // Fall back to position.contribution_to_portfolio_pct (same formula, live prices).
  const contributionMap = useMemo(() => {
    const m: Record<string, number> = {};
    // Seed with position-level values as baseline
    for (const p of data) {
      if (p.contribution_to_portfolio_pct != null) m[p.ticker] = p.contribution_to_portfolio_pct;
    }
    // Override with analytics values (more accurate — price-history snapshot)
    for (const c of analytics?.contribution ?? []) m[c.ticker] = c.contribution_pct;
    return m;
  }, [analytics, data]);

  // ── Sort + filter ──────────────────────────────────────────────────────────
  const handleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir(d => (d === 1 ? -1 : 1));
    else { setSortKey(key); setSortDir(-1); }
  };

  const displayData = useMemo(() => {
    let arr = [...data];
    if (filter === "winners") arr = arr.filter(p => (p.gain_loss ?? 0) >= 0);
    if (filter === "losers")  arr = arr.filter(p => (p.gain_loss ?? 0) <  0);
    return arr.sort((a, b) => {
      const av = (a[sortKey] ?? 0) as number | string;
      const bv = (b[sortKey] ?? 0) as number | string;
      if (typeof av === "string") return sortDir * av.localeCompare(bv as string);
      return sortDir * ((av as number) - (bv as number));
    });
  }, [data, filter, sortKey, sortDir]);

  // ── Totals ─────────────────────────────────────────────────────────────────
  const totalValue  = data.reduce((s, p) => s + (p.current_value ?? 0), 0);
  const totalGL     = data.reduce((s, p) => s + (p.gain_loss     ?? 0), 0);
  const totalCost   = data.reduce((s, p) => s + p.shares * p.cost_basis, 0);
  const totalRetPct = totalCost > 0 ? (totalGL / totalCost) * 100 : null;

  // ── Add transaction handler ────────────────────────────────────────────────
  const handleAddTransaction = async () => {
    const { ticker, side, shares, price, traded_at } = addForm;
    if (!ticker || !shares || !price || !traded_at) { setError("All fields required"); return; }
    const sym     = ticker.toUpperCase().trim();
    const nShares = parseFloat(shares);
    const nPrice  = parseFloat(price);
    if (isNaN(nShares) || isNaN(nPrice) || nShares <= 0 || nPrice <= 0) {
      setError("Shares and price must be positive"); return;
    }
    setError(""); setAdding(true);
    try {
      await txnApi.add(portfolioId, {
        ticker: sym, side, shares: nShares, price: nPrice, fees: 0,
        traded_at: new Date(traded_at + "T12:00:00Z").toISOString(),
      });
      const existing = data.find(p => p.ticker === sym);
      if (side === "buy") {
        if (existing) {
          const totalShares = existing.shares + nShares;
          const avgCost     = (existing.shares * existing.cost_basis + nShares * nPrice) / totalShares;
          await posApi.update(portfolioId, existing.id, { shares: totalShares, cost_basis: parseFloat(avgCost.toFixed(6)) });
        } else {
          await posApi.add(portfolioId, { ticker: sym, shares: nShares, cost_basis: nPrice });
        }
      } else if (existing) {
        const remaining = existing.shares - nShares;
        if (remaining <= 0.000001) await posApi.delete(portfolioId, existing.id);
        else await posApi.update(portfolioId, existing.id, { shares: remaining });
      }
      const fresh = await txnApi.list(portfolioId);
      setAllTxns(fresh);
      setAddForm({ ticker: "", side: "buy", shares: "", price: "", traded_at: todayStr() });
      setShowAdd(false);
      onRefresh();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to add transaction");
    } finally {
      setAdding(false);
    }
  };

  const handleQuickAction = useCallback((ticker: string, side: "buy" | "sell") => {
    setAddForm(f => ({ ...f, ticker, side }));
    setShowAdd(true);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, []);

  const handleDeletePos = async (posId: string) => {
    setDeletingPos(posId);
    try { await posApi.delete(portfolioId, posId); onRefresh(); }
    catch (e: unknown) { alert(e instanceof Error ? e.message : "Delete failed"); }
    finally { setDeletingPos(null); }
  };

  const SortIcon = ({ col }: { col: SortKey }) => {
    if (sortKey !== col) return <span className="w-3 inline-block" />;
    return sortDir === -1
      ? <ArrowDown size={11} className="text-blue-400" />
      : <ArrowUp   size={11} className="text-blue-400" />;
  };

  const hasContribution = (analytics?.contribution?.length ?? 0) > 0;
  const hasSectors      = Object.keys(sectorMap).length > 0;

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="space-y-4">

      {/* ── Toolbar ──────────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <p className="text-sm text-zinc-500">
            {data.length} position{data.length !== 1 ? "s" : ""}
            {txnsLoaded && allTxns.length > 0 && (
              <span className="ml-2 text-zinc-700">· {allTxns.length} txn{allTxns.length !== 1 ? "s" : ""}</span>
            )}
          </p>

          {/* Filter pills */}
          <div className="flex gap-1 bg-zinc-800/60 rounded-lg p-0.5">
            {(["all", "winners", "losers"] as Filter[]).map(f => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-2.5 py-1 text-xs rounded-md font-medium capitalize transition-colors ${
                  filter === f
                    ? f === "winners" ? "bg-emerald-700 text-white"
                    : f === "losers"  ? "bg-red-800 text-white"
                    :                   "bg-zinc-600 text-white"
                    : "text-zinc-500 hover:text-zinc-300"
                }`}
              >
                {f === "winners" ? "▲ Winners" : f === "losers" ? "▼ Losers" : "All"}
              </button>
            ))}
          </div>
        </div>

        <button
          onClick={() => { setShowAdd(s => !s); setError(""); }}
          className="flex items-center gap-1.5 text-sm bg-blue-600 hover:bg-blue-500 text-white px-3 py-1.5 rounded-lg transition-colors"
        >
          {showAdd ? <X size={14} /> : <Plus size={14} />}
          {showAdd ? "Cancel" : "Add Transaction"}
        </button>
      </div>

      {/* ── Add Transaction form ──────────────────────────────────────────────── */}
      {showAdd && (
        <AddTransactionForm
          form={addForm} setForm={setAddForm}
          adding={adding} error={error}
          onSubmit={handleAddTransaction}
          onCancel={() => { setShowAdd(false); setError(""); }}
        />
      )}

      {/* ── Analytics panels (Sector + Contribution) ─────────────────────────── */}
      {(hasSectors || hasContribution) && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {hasSectors && (
            <SectorPanel positions={data} sectorMap={sectorMap} />
          )}
          {hasContribution && (
            <ContributionPanel contribution={analytics!.contribution!} />
          )}
        </div>
      )}

      {/* ── Holdings table ────────────────────────────────────────────────────── */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
        <div className="overflow-x-auto scrollbar-thin">
          <table className="w-full text-sm">

            <thead>
              <tr className="border-b border-zinc-800 sticky top-0 bg-zinc-900 z-10">
                <th className="w-8 px-2" />
                {COLS.map(col => (
                  <th
                    key={col.key}
                    onClick={() => handleSort(col.key)}
                    title={col.title}
                    className={`px-4 py-3 text-xs font-semibold text-zinc-500 cursor-pointer hover:text-zinc-300 select-none transition-colors ${
                      col.align === "right" ? "text-right" : "text-left"
                    } ${col.title ? "underline decoration-dotted decoration-zinc-600 underline-offset-2" : ""}`}
                  >
                    <span className="inline-flex items-center gap-1">
                      {col.align === "right" && <SortIcon col={col.key} />}
                      {col.label}
                      {col.align === "left"  && <SortIcon col={col.key} />}
                    </span>
                  </th>
                ))}
                <th className="w-10 px-4" />
              </tr>
            </thead>

            <tbody>
              {displayData.length === 0 ? (
                <tr>
                  <td colSpan={COLS.length + 2} className="px-4 py-12 text-center text-zinc-600">
                    {filter !== "all"
                      ? `No ${filter} in this portfolio.`
                      : "No positions yet. Add your first transaction above."}
                  </td>
                </tr>
              ) : displayData.map((pos, i) => {
                const isExpanded = expandedTicker === pos.ticker;
                const gl         = pos.gain_loss     ?? 0;
                const glPct      = pos.gain_loss_pct ?? 0;
                const isLast     = i === displayData.length - 1;

                return (
                  <React.Fragment key={pos.id}>
                    {/* ── Position row ──────────────────────────────────── */}
                    <tr
                      onClick={() => setExpandedTicker(isExpanded ? null : pos.ticker)}
                      className={`border-b border-zinc-800/50 hover:bg-zinc-800/30 transition-colors cursor-pointer select-none group ${
                        isExpanded ? "bg-zinc-800/20" : ""
                      } ${isLast && !isExpanded ? "border-0" : ""}`}
                    >
                      <td className="pl-3 pr-0 py-3 text-zinc-600">
                        {isExpanded
                          ? <ChevronDown  size={14} className="text-zinc-400" />
                          : <ChevronRight size={14} />}
                      </td>

                      {/* Ticker + logo */}
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <TickerLogo ticker={pos.ticker} />
                          <div>
                            <div className="font-mono font-semibold text-zinc-100 tracking-wide">{pos.ticker}</div>
                            {sectorMap[pos.ticker] && (
                              <div className="text-[10px] text-zinc-600 leading-none mt-0.5">{sectorMap[pos.ticker]}</div>
                            )}
                          </div>
                        </div>
                      </td>

                      <td className="px-4 py-3 text-right font-mono tabular-nums text-zinc-300">
                        {fmt(pos.shares, pos.shares % 1 === 0 ? 0 : 2)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono tabular-nums text-zinc-400">
                        ${fmt(pos.cost_basis)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono tabular-nums text-zinc-300">
                        {pos.current_price != null ? `$${fmt(pos.current_price)}` : "—"}
                      </td>
                      <td className="px-4 py-3 text-right font-mono tabular-nums text-zinc-200 font-medium">
                        {fmtK(pos.current_value)}
                      </td>
                      <td className={`px-4 py-3 text-right font-mono tabular-nums font-medium ${gainClass(gl)}`}>
                        {gl >= 0 ? "+" : ""}{fmtK(gl)}
                      </td>
                      <td className={`px-4 py-3 text-right font-mono tabular-nums font-medium ${gainClass(glPct)}`}>
                        {fmtPct(glPct)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono tabular-nums text-zinc-500">
                        {fmt(pos.weight_pct)}%
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={e => { e.stopPropagation(); handleDeletePos(pos.id); }}
                          disabled={deletingPos === pos.id}
                          className="text-zinc-700 hover:text-red-400 transition-colors disabled:opacity-50"
                          title="Delete position"
                        >
                          <Trash2 size={13} />
                        </button>
                      </td>
                    </tr>

                    {/* ── Expanded panel ────────────────────────────────── */}
                    {isExpanded && (
                      <tr className={isLast ? "border-0" : "border-b border-zinc-800/50"}>
                        <td colSpan={COLS.length + 2} className="p-0">
                          <ExpandedPanel
                            pos={pos}
                            portfolioId={portfolioId}
                            allTxns={allTxns}
                            positions={data}
                            contribution={contributionMap[pos.ticker] ?? null}
                            onTxnsChange={setAllTxns}
                            onQuickAction={handleQuickAction}
                            onRefresh={onRefresh}
                          />
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>

            {/* ── Totals footer ─────────────────────────────────────────── */}
            {data.length > 0 && (
              <tfoot>
                <tr className="border-t border-zinc-700 bg-zinc-900/60">
                  <td className="pl-3 pr-0" />
                  <td className="px-4 py-3">
                    <span className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">Portfolio</span>
                  </td>
                  <td colSpan={3} />
                  <td className="px-4 py-3 text-right">
                    <div className="font-mono font-bold text-zinc-100 text-sm">{fmtK(totalValue)}</div>
                    <div className="text-[10px] text-zinc-600">Mkt Value</div>
                  </td>
                  <td className={`px-4 py-3 text-right font-mono font-bold text-sm ${gainClass(totalGL)}`}>
                    <div>{totalGL >= 0 ? "+" : ""}{fmtK(totalGL)}</div>
                    <div
                      className={`text-[10px] font-normal ${gainClass(totalRetPct)}`}
                      title="Simple return on cost basis. For time-weighted return see Overview → Annualized Return."
                    >
                      {totalRetPct != null ? fmtPct(totalRetPct) : ""} simple ret
                    </div>
                  </td>
                  <td colSpan={3} />
                </tr>
              </tfoot>
            )}

          </table>
        </div>
      </div>
    </div>
  );
}
