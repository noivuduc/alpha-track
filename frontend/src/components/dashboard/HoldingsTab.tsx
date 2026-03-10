"use client";
import React, { useState, useEffect, useMemo } from "react";
import { ChevronRight, ChevronDown, Plus, Trash2, X, Check, ArrowUp, ArrowDown } from "lucide-react";
import {
  Position, Transaction,
  positions as posApi, transactions as txnApi,
} from "@/lib/api";
import { fmt, fmtCurrency, fmtPct, gainClass } from "@/lib/portfolio-math";

// ── Types ──────────────────────────────────────────────────────────────────────

type SortKey = "ticker" | "shares" | "cost_basis" | "current_price" | "current_value" | "gain_loss" | "gain_loss_pct" | "weight_pct";

interface Props {
  portfolioId: string;
  data:        Position[];
  onRefresh:   () => void;
}

interface TxnForm {
  ticker:    string;
  side:      "buy" | "sell";
  shares:    string;
  price:     string;
  traded_at: string;   // YYYY-MM-DD
}

// ── Constants ──────────────────────────────────────────────────────────────────

const COLS: { key: SortKey; label: string; align: "left" | "right" }[] = [
  { key: "ticker",        label: "Ticker",    align: "left"  },
  { key: "shares",        label: "Shares",    align: "right" },
  { key: "cost_basis",    label: "Avg Cost",  align: "right" },
  { key: "current_price", label: "Price",     align: "right" },
  { key: "current_value", label: "Mkt Value", align: "right" },
  { key: "gain_loss",     label: "P&L",       align: "right" },
  { key: "gain_loss_pct", label: "P&L %",     align: "right" },
  { key: "weight_pct",    label: "Weight",    align: "right" },
];

const todayStr = () => new Date().toISOString().slice(0, 10);

// ── Component ──────────────────────────────────────────────────────────────────

export default function HoldingsTab({ portfolioId, data, onRefresh }: Props) {
  // ── Sorting ────────────────────────────────────────────────────────────────
  const [sortKey, setSortKey] = useState<SortKey>("current_value");
  const [sortDir, setSortDir] = useState<1 | -1>(-1);

  // ── Row expansion ──────────────────────────────────────────────────────────
  const [expandedTicker, setExpandedTicker] = useState<string | null>(null);

  // ── Transactions (loaded once on mount) ────────────────────────────────────
  const [allTxns,    setAllTxns]    = useState<Transaction[]>([]);
  const [txnsLoaded, setTxnsLoaded] = useState(false);

  useEffect(() => {
    txnApi.list(portfolioId)
      .then(list => { setAllTxns(list); setTxnsLoaded(true); })
      .catch(() => setTxnsLoaded(true));
  }, [portfolioId]);

  // Group transactions by ticker, sorted newest-first
  const txnsByTicker = useMemo<Record<string, Transaction[]>>(() => {
    const map: Record<string, Transaction[]> = {};
    for (const t of allTxns) {
      (map[t.ticker] ??= []).push(t);
    }
    for (const key in map) {
      map[key].sort((a, b) => b.traded_at.localeCompare(a.traded_at));
    }
    return map;
  }, [allTxns]);

  // ── Add Transaction form ───────────────────────────────────────────────────
  const [showAdd, setShowAdd] = useState(false);
  const [form,    setForm]    = useState<TxnForm>({
    ticker: "", side: "buy", shares: "", price: "", traded_at: todayStr(),
  });
  const [adding,   setAdding]   = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [error,    setError]    = useState("");

  const handleAddTransaction = async () => {
    const { ticker, side, shares, price, traded_at } = form;
    if (!ticker || !shares || !price || !traded_at) {
      setError("All fields are required"); return;
    }
    const sym     = ticker.toUpperCase().trim();
    const nShares = parseFloat(shares);
    const nPrice  = parseFloat(price);
    if (isNaN(nShares) || isNaN(nPrice) || nShares <= 0 || nPrice <= 0) {
      setError("Shares and price must be positive numbers"); return;
    }
    setError("");
    setAdding(true);
    try {
      // 1. Record the transaction
      await txnApi.add(portfolioId, {
        ticker:    sym,
        side,
        shares:    nShares,
        price:     nPrice,
        fees:      0,
        traded_at: new Date(traded_at + "T12:00:00Z").toISOString(),
      });

      // 2. Reconcile the position aggregate
      const existing = data.find(p => p.ticker === sym);
      if (side === "buy") {
        if (existing) {
          const totalShares = existing.shares + nShares;
          const avgCost     = (existing.shares * existing.cost_basis + nShares * nPrice) / totalShares;
          await posApi.update(portfolioId, existing.id, {
            shares:     totalShares,
            cost_basis: parseFloat(avgCost.toFixed(6)),
          });
        } else {
          await posApi.add(portfolioId, { ticker: sym, shares: nShares, cost_basis: nPrice });
        }
      } else {
        // sell — reduce or close the position
        if (existing) {
          const remaining = existing.shares - nShares;
          if (remaining <= 0.000001) {
            await posApi.delete(portfolioId, existing.id);
          } else {
            await posApi.update(portfolioId, existing.id, { shares: remaining });
          }
        }
      }

      // 3. Refresh transaction list + positions
      const freshTxns = await txnApi.list(portfolioId);
      setAllTxns(freshTxns);
      setForm({ ticker: "", side: "buy", shares: "", price: "", traded_at: todayStr() });
      setShowAdd(false);
      onRefresh();
    } catch (e: any) {
      setError(e.message || "Failed to add transaction");
    } finally {
      setAdding(false);
    }
  };

  const handleDelete = async (posId: string) => {
    setDeleting(posId);
    try {
      await posApi.delete(portfolioId, posId);
      onRefresh();
    } catch (e: any) {
      alert(e.message || "Delete failed");
    } finally {
      setDeleting(null);
    }
  };

  // ── Sort ───────────────────────────────────────────────────────────────────
  const handleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir(d => (d === 1 ? -1 : 1));
    else { setSortKey(key); setSortDir(-1); }
  };

  const sorted = useMemo(() => {
    return [...data].sort((a, b) => {
      const av = (a[sortKey] ?? 0) as number | string;
      const bv = (b[sortKey] ?? 0) as number | string;
      if (typeof av === "string") return sortDir * av.localeCompare(bv as string);
      return sortDir * ((av as number) - (bv as number));
    });
  }, [data, sortKey, sortDir]);

  // ── Totals ─────────────────────────────────────────────────────────────────
  const totalValue = data.reduce((s, p) => s + (p.current_value ?? 0), 0);
  const totalGL    = data.reduce((s, p) => s + (p.gain_loss     ?? 0), 0);

  // ── Helpers ────────────────────────────────────────────────────────────────
  const SortIcon = ({ col }: { col: SortKey }) => {
    if (sortKey !== col) return <span className="w-3 inline-block" />;
    return sortDir === -1
      ? <ArrowDown size={11} className="text-blue-400" />
      : <ArrowUp   size={11} className="text-blue-400" />;
  };

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="space-y-4">

      {/* ── Toolbar ─────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-zinc-500">
          {data.length} position{data.length !== 1 ? "s" : ""}
          {txnsLoaded && allTxns.length > 0 && (
            <span className="ml-2 text-zinc-700">· {allTxns.length} transaction{allTxns.length !== 1 ? "s" : ""}</span>
          )}
        </p>
        <button
          onClick={() => { setShowAdd(s => !s); setError(""); }}
          className="flex items-center gap-1.5 text-sm bg-blue-600 hover:bg-blue-500 text-white px-3 py-1.5 rounded-lg transition-colors"
        >
          {showAdd ? <X size={14} /> : <Plus size={14} />}
          {showAdd ? "Cancel" : "Add Transaction"}
        </button>
      </div>

      {/* ── Add Transaction form ─────────────────────────────────────────── */}
      {showAdd && (
        <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-4 space-y-3">
          <h4 className="text-sm font-semibold text-zinc-300">New Transaction</h4>

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
              <input
                type="date"
                value={form.traded_at}
                onChange={e => setForm(f => ({ ...f, traded_at: e.target.value }))}
                className="bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-2 text-zinc-50 text-sm focus:outline-none focus:border-blue-500"
              />
            </div>

            <button
              onClick={handleAddTransaction}
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
      )}

      {/* ── Holdings table ───────────────────────────────────────────────── */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
        <div className="overflow-x-auto scrollbar-thin">
          <table className="w-full text-sm">

            {/* Column headers */}
            <thead>
              <tr className="border-b border-zinc-800">
                <th className="w-8 px-2" />   {/* expand chevron */}
                {COLS.map(col => (
                  <th
                    key={col.key}
                    onClick={() => handleSort(col.key)}
                    className={`px-4 py-3 text-xs font-semibold text-zinc-500 cursor-pointer hover:text-zinc-300 select-none transition-colors ${
                      col.align === "right" ? "text-right" : "text-left"
                    }`}
                  >
                    <span className="inline-flex items-center gap-1">
                      {col.align === "right" && <SortIcon col={col.key} />}
                      {col.label}
                      {col.align === "left"  && <SortIcon col={col.key} />}
                    </span>
                  </th>
                ))}
                <th className="w-10 px-4" />   {/* delete button */}
              </tr>
            </thead>

            <tbody>
              {sorted.length === 0 ? (
                <tr>
                  <td colSpan={COLS.length + 2} className="px-4 py-12 text-center text-zinc-500">
                    No positions yet. Add your first transaction above.
                  </td>
                </tr>
              ) : sorted.map((pos, i) => {
                const isExpanded = expandedTicker === pos.ticker;
                const gl         = pos.gain_loss     ?? 0;
                const glPct      = pos.gain_loss_pct ?? 0;
                const isLast     = i === sorted.length - 1;
                const txns       = txnsByTicker[pos.ticker] ?? [];

                return (
                  <React.Fragment key={pos.id}>
                    {/* ── Position row ───────────────────────────────────── */}
                    <tr
                      onClick={() => setExpandedTicker(isExpanded ? null : pos.ticker)}
                      className={`border-b border-zinc-800/50 hover:bg-zinc-800/40 transition-colors cursor-pointer select-none ${
                        isExpanded ? "bg-zinc-800/30" : ""
                      } ${isLast && !isExpanded ? "border-0" : ""}`}
                    >
                      <td className="pl-3 pr-0 py-3">
                        {isExpanded
                          ? <ChevronDown  size={14} className="text-zinc-400" />
                          : <ChevronRight size={14} className="text-zinc-600" />}
                      </td>

                      <td className="px-4 py-3 font-mono font-semibold text-zinc-100 tracking-wide">
                        {pos.ticker}
                      </td>
                      <td className="px-4 py-3 text-right font-mono tabular-nums text-zinc-300">
                        {fmt(pos.shares, pos.shares % 1 === 0 ? 0 : 4)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono tabular-nums text-zinc-300">
                        ${fmt(pos.cost_basis)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono tabular-nums text-zinc-300">
                        {pos.current_price != null ? `$${fmt(pos.current_price)}` : "—"}
                      </td>
                      <td className="px-4 py-3 text-right font-mono tabular-nums text-zinc-200 font-medium">
                        {fmtCurrency(pos.current_value)}
                      </td>
                      <td className={`px-4 py-3 text-right font-mono tabular-nums font-medium ${gainClass(gl)}`}>
                        {gl >= 0 ? "+" : ""}{fmtCurrency(gl)}
                      </td>
                      <td className={`px-4 py-3 text-right font-mono tabular-nums font-medium ${gainClass(glPct)}`}>
                        {fmtPct(glPct)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono tabular-nums text-zinc-400">
                        {fmt(pos.weight_pct)}%
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={e => { e.stopPropagation(); handleDelete(pos.id); }}
                          disabled={deleting === pos.id}
                          className="text-zinc-700 hover:text-red-400 transition-colors disabled:opacity-50"
                          title="Delete position"
                        >
                          <Trash2 size={13} />
                        </button>
                      </td>
                    </tr>

                    {/* ── Transaction drawer (expanded) ──────────────────── */}
                    {isExpanded && (
                      <tr className={isLast ? "border-0" : "border-b border-zinc-800/50"}>
                        <td colSpan={COLS.length + 2} className="bg-zinc-950/50 p-0">
                          <div className="pl-10 pr-6 py-3">
                            <p className="text-[11px] font-semibold text-zinc-600 uppercase tracking-widest mb-2.5">
                              Transactions · {pos.ticker}
                            </p>

                            {txns.length === 0 ? (
                              <p className="text-xs text-zinc-700 py-1">
                                No transactions recorded for {pos.ticker}.
                              </p>
                            ) : (
                              <table className="w-full text-xs">
                                <thead>
                                  <tr className="border-b border-zinc-800/80">
                                    <th className="text-left text-zinc-600 font-semibold pb-2 pr-8">Date</th>
                                    <th className="text-left text-zinc-600 font-semibold pb-2 pr-8">Type</th>
                                    <th className="text-right text-zinc-600 font-semibold pb-2 pr-8">Shares</th>
                                    <th className="text-right text-zinc-600 font-semibold pb-2 pr-8">Price</th>
                                    <th className="text-right text-zinc-600 font-semibold pb-2">Total</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {txns.map(txn => (
                                    <tr key={txn.id} className="border-b border-zinc-900 last:border-0">
                                      <td className="font-mono text-zinc-500 py-1.5 pr-8">
                                        {txn.traded_at.slice(0, 10)}
                                      </td>
                                      <td className="py-1.5 pr-8">
                                        <span className={`font-semibold ${txn.side === "buy" ? "text-emerald-500" : "text-red-500"}`}>
                                          {txn.side.toUpperCase()}
                                        </span>
                                      </td>
                                      <td className="font-mono tabular-nums text-zinc-400 text-right py-1.5 pr-8">
                                        {fmt(txn.shares, txn.shares % 1 === 0 ? 0 : 4)}
                                      </td>
                                      <td className="font-mono tabular-nums text-zinc-400 text-right py-1.5 pr-8">
                                        ${fmt(txn.price)}
                                      </td>
                                      <td className="font-mono tabular-nums text-zinc-500 text-right py-1.5">
                                        {fmtCurrency(txn.shares * txn.price)}
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>

            {/* Footer totals */}
            {sorted.length > 0 && (
              <tfoot>
                <tr className="border-t border-zinc-700">
                  <td className="pl-3 pr-0" />
                  <td className="px-4 py-3 text-xs font-semibold text-zinc-500 uppercase tracking-wider">Total</td>
                  <td colSpan={3} />
                  <td className="px-4 py-3 text-right font-mono tabular-nums font-bold text-zinc-100 text-sm">
                    {fmtCurrency(totalValue)}
                  </td>
                  <td className={`px-4 py-3 text-right font-mono tabular-nums font-bold text-sm ${gainClass(totalGL)}`}>
                    {totalGL >= 0 ? "+" : ""}{fmtCurrency(totalGL)}
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
