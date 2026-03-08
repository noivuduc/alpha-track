"use client";
import { useState } from "react";
import { ChevronUp, ChevronDown, Plus, Trash2, X, Check } from "lucide-react";
import { Position, positions as posApi, transactions as txnApi } from "@/lib/api";
import { fmt, fmtCurrency, fmtPct, gainClass } from "@/lib/portfolio-math";

type SortKey = "ticker" | "shares" | "cost_basis" | "current_price" | "current_value" | "gain_loss" | "gain_loss_pct" | "weight_pct";

interface Props {
  portfolioId: string;
  data: Position[];
  onRefresh: () => void;
}

interface AddForm { ticker: string; shares: string; cost_basis: string; }

const COLS: { key: SortKey; label: string; align: "left" | "right" }[] = [
  { key: "ticker",        label: "Ticker",     align: "left"  },
  { key: "shares",        label: "Shares",     align: "right" },
  { key: "cost_basis",    label: "Avg Cost",   align: "right" },
  { key: "current_price", label: "Price",      align: "right" },
  { key: "current_value", label: "Mkt Value",  align: "right" },
  { key: "gain_loss",     label: "Unr. P&L",  align: "right" },
  { key: "gain_loss_pct", label: "P&L %",      align: "right" },
  { key: "weight_pct",    label: "Weight",     align: "right" },
];

export default function HoldingsTab({ portfolioId, data, onRefresh }: Props) {
  const [sortKey,  setSortKey]  = useState<SortKey>("current_value");
  const [sortDir,  setSortDir]  = useState<1 | -1>(-1);
  const [showAdd,  setShowAdd]  = useState(false);
  const [form,     setForm]     = useState<AddForm>({ ticker: "", shares: "", cost_basis: "" });
  const [adding,   setAdding]   = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [error,    setError]    = useState("");

  const handleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir(d => (d === 1 ? -1 : 1));
    else { setSortKey(key); setSortDir(-1); }
  };

  const sorted = [...data].sort((a, b) => {
    const av = (a[sortKey] ?? 0) as number | string;
    const bv = (b[sortKey] ?? 0) as number | string;
    if (typeof av === "string") return sortDir * av.localeCompare(bv as string);
    return sortDir * ((av as number) - (bv as number));
  });

  const handleAdd = async () => {
    const { ticker, shares, cost_basis } = form;
    if (!ticker || !shares || !cost_basis) { setError("All fields required"); return; }
    const sym       = ticker.toUpperCase().trim();
    const newShares = parseFloat(shares);
    const newCost   = parseFloat(cost_basis);
    if (isNaN(newShares) || isNaN(newCost) || newShares <= 0 || newCost <= 0) {
      setError("Shares and cost must be positive numbers"); return;
    }
    setError("");
    setAdding(true);
    try {
      const existing = data.find(p => p.ticker === sym);
      if (existing) {
        // Merge: weighted-average cost basis + add shares
        const totalShares  = existing.shares + newShares;
        const avgCost      = (existing.shares * existing.cost_basis + newShares * newCost) / totalShares;
        await Promise.all([
          posApi.update(portfolioId, existing.id, {
            shares:     totalShares,
            cost_basis: parseFloat(avgCost.toFixed(6)),
          }),
          txnApi.add(portfolioId, {
            ticker:    sym,
            side:      "buy",
            shares:    newShares,
            price:     newCost,
            fees:      0,
            traded_at: new Date().toISOString(),
          }),
        ]);
      } else {
        await posApi.add(portfolioId, { ticker: sym, shares: newShares, cost_basis: newCost });
      }
      setForm({ ticker: "", shares: "", cost_basis: "" });
      setShowAdd(false);
      onRefresh();
    } catch (e: any) {
      setError(e.message || "Failed to add position");
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

  const SortIcon = ({ col }: { col: SortKey }) => {
    if (sortKey !== col) return <ChevronUp size={12} className="opacity-20" />;
    return sortDir === -1 ? <ChevronDown size={12} className="text-blue-400" /> : <ChevronUp size={12} className="text-blue-400" />;
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="text-sm text-zinc-500">{data.length} positions</div>
        <button
          onClick={() => setShowAdd(s => !s)}
          className="flex items-center gap-1.5 text-sm bg-blue-600 hover:bg-blue-500 text-white px-3 py-1.5 rounded-lg transition-colors"
        >
          {showAdd ? <X size={14} /> : <Plus size={14} />}
          {showAdd ? "Cancel" : "Add Position"}
        </button>
      </div>

      {/* Add position form */}
      {showAdd && (
        <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-4">
          <h4 className="text-sm font-semibold text-zinc-300 mb-3">
            {form.ticker && data.some(p => p.ticker === form.ticker.toUpperCase().trim())
              ? `Add lot to ${form.ticker.toUpperCase().trim()} — will average cost basis`
              : "New Position"}
          </h4>
          <div className="flex flex-wrap gap-3 items-end">
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Ticker</label>
              <input
                value={form.ticker}
                onChange={e => setForm(f => ({ ...f, ticker: e.target.value }))}
                placeholder="AAPL"
                className="w-24 bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-2 text-zinc-50 text-sm uppercase placeholder:normal-case placeholder:text-zinc-600 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Shares</label>
              <input
                type="number"
                value={form.shares}
                onChange={e => setForm(f => ({ ...f, shares: e.target.value }))}
                placeholder="100"
                className="w-28 bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-2 text-zinc-50 text-sm placeholder:text-zinc-600 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Avg Cost ($)</label>
              <input
                type="number"
                value={form.cost_basis}
                onChange={e => setForm(f => ({ ...f, cost_basis: e.target.value }))}
                placeholder="150.00"
                className="w-32 bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-2 text-zinc-50 text-sm placeholder:text-zinc-600 focus:outline-none focus:border-blue-500"
              />
            </div>
            <button
              onClick={handleAdd}
              disabled={adding}
              className="flex items-center gap-1.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            >
              {adding
                ? <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                : <Check size={14} />}
              Add
            </button>
          </div>
          {error && <p className="text-red-400 text-xs mt-2">{error}</p>}
        </div>
      )}

      {/* Holdings table */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
        <div className="overflow-x-auto scrollbar-thin">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-800">
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
                      {col.align === "left" && <SortIcon col={col.key} />}
                    </span>
                  </th>
                ))}
                <th className="px-4 py-3 w-10" />
              </tr>
            </thead>
            <tbody>
              {sorted.length === 0 ? (
                <tr>
                  <td colSpan={COLS.length + 1} className="px-4 py-12 text-center text-zinc-500">
                    No positions yet. Add your first position above.
                  </td>
                </tr>
              ) : (
                sorted.map((pos, i) => {
                  const gl    = pos.gain_loss ?? 0;
                  const glPct = pos.gain_loss_pct ?? 0;
                  return (
                    <tr
                      key={pos.id}
                      className={`border-b border-zinc-800/50 hover:bg-zinc-800/40 transition-colors ${i === sorted.length - 1 ? "border-0" : ""}`}
                    >
                      <td className="px-4 py-3 font-mono font-semibold text-zinc-100">{pos.ticker}</td>
                      <td className="px-4 py-3 text-right font-mono tabular-nums text-zinc-300">
                        {fmt(pos.shares, pos.shares % 1 === 0 ? 0 : 4)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono tabular-nums text-zinc-300">
                        ${fmt(pos.cost_basis)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono tabular-nums text-zinc-300">
                        ${fmt(pos.current_price)}
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
                          onClick={() => handleDelete(pos.id)}
                          disabled={deleting === pos.id}
                          className="text-zinc-600 hover:text-red-400 transition-colors disabled:opacity-50"
                        >
                          <Trash2 size={14} />
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>

            {sorted.length > 0 && (
              <tfoot>
                <tr className="border-t border-zinc-700">
                  <td className="px-4 py-3 text-xs font-semibold text-zinc-400">TOTAL</td>
                  <td colSpan={3} />
                  <td className="px-4 py-3 text-right font-mono tabular-nums font-bold text-zinc-100 text-sm">
                    {fmtCurrency(data.reduce((s, p) => s + (p.current_value ?? 0), 0))}
                  </td>
                  <td className={`px-4 py-3 text-right font-mono tabular-nums font-bold text-sm ${gainClass(data.reduce((s, p) => s + (p.gain_loss ?? 0), 0))}`}>
                    {(() => {
                      const total = data.reduce((s, p) => s + (p.gain_loss ?? 0), 0);
                      return `${total >= 0 ? "+" : ""}${fmtCurrency(total)}`;
                    })()}
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
