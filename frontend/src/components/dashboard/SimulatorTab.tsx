"use client";
import { useState, useMemo, useCallback, memo, useEffect } from "react";
import {
  TrendingUp, Loader2, FlaskConical, Plus, Trash2,
  CheckCircle2, AlertTriangle, X, RotateCcw, ChevronRight,
  ArrowUpRight, ArrowDownRight,
} from "lucide-react";
import {
  portfolios as portApi,
  ScenarioResponse,
  ScenarioTransaction,
  HoldingSnapshot,
  ApplyScenarioResult,
  SimulatorPrefillRow,
} from "@/lib/api";

// ─── Types ────────────────────────────────────────────────────────────────────

interface TxRow {
  id:     string;
  action: "buy" | "sell";
  ticker: string;
  mode:   "shares" | "amount" | "weight_pct" | "target_weight";
  value:  string;
}

let _nextId = 1;
const newRow = (patch?: Partial<TxRow>): TxRow => ({
  id: String(_nextId++), action: "buy", ticker: "", mode: "weight_pct", value: "5",
  ...patch,
});

// ─── Shared helpers ───────────────────────────────────────────────────────────

function fmt(v: number, d = 2) { return v.toFixed(d); }

function DeltaCell({
  v, suffix = "", invert = false,
}: { v: number; suffix?: string; invert?: boolean }) {
  const good = invert ? v < 0 : v > 0;
  const bad  = invert ? v > 0 : v < 0;
  const Icon = good ? ArrowUpRight : bad ? ArrowDownRight : null;
  const cls  = good ? "text-emerald-400" : bad ? "text-red-400" : "text-zinc-500";
  if (Math.abs(v) < 0.0001) return <span className="text-zinc-700">—</span>;
  return (
    <span className={`inline-flex items-center gap-0.5 font-medium tabular-nums ${cls}`}>
      {Icon && <Icon size={11} />}
      {v > 0 ? "+" : ""}{fmt(v)}{suffix}
    </span>
  );
}

// ─── Transaction row ──────────────────────────────────────────────────────────

function TransactionRow({
  row, index, onChange, onRemove, canRemove,
}: {
  row:      TxRow;
  index:    number;
  onChange: (id: string, patch: Partial<TxRow>) => void;
  onRemove: (id: string) => void;
  canRemove: boolean;
}) {
  const inp =
    "bg-zinc-950/70 border border-zinc-700/50 rounded-lg px-3 py-2 text-sm " +
    "text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-blue-500 " +
    "focus:bg-zinc-900/80 transition-colors w-full";

  return (
    <div className="grid grid-cols-[100px_1fr_170px_160px_40px] gap-2 items-center group">

      {/* Action toggle */}
      <div className="flex rounded-lg overflow-hidden border border-zinc-700/50 h-[38px]">
        {(["buy", "sell"] as const).map(a => (
          <button
            key={a}
            onClick={() => onChange(row.id, { action: a })}
            className={`flex-1 text-xs font-semibold capitalize transition-colors ${
              row.action === a
                ? a === "buy"
                  ? "bg-blue-600 text-white"
                  : "bg-rose-700 text-white"
                : "bg-zinc-900 text-zinc-500 hover:text-zinc-300"
            }`}
          >
            {a}
          </button>
        ))}
      </div>

      {/* Ticker */}
      <div className="relative">
        <input
          value={row.ticker}
          onChange={e => onChange(row.id, { ticker: e.target.value.toUpperCase() })}
          placeholder="TICKER"
          maxLength={10}
          className={`${inp} font-mono tracking-widest uppercase`}
        />
        {/* Inline badge for valid ticker */}
        {row.ticker.trim() && (
          <span className={`absolute right-2.5 top-1/2 -translate-y-1/2 text-[9px] font-semibold px-1.5 py-0.5 rounded ${
            row.action === "buy"
              ? "bg-blue-900/60 text-blue-400"
              : "bg-rose-900/60 text-rose-400"
          }`}>
            {row.action === "buy" ? "BUY" : "SELL"}
          </span>
        )}
      </div>

      {/* Mode */}
      <select
        value={row.mode}
        onChange={e => onChange(row.id, { mode: e.target.value as TxRow["mode"] })}
        className={inp}
      >
        <option value="weight_pct">% of portfolio (add/remove)</option>
        <option value="target_weight">Target final weight %</option>
        <option value="amount">$ amount</option>
        <option value="shares">Shares</option>
      </select>

      {/* Value */}
      <div className="relative">
        {row.mode === "amount" && (
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500 text-sm pointer-events-none select-none">$</span>
        )}
        <input
          type="number"
          min={0}
          step={row.mode === "shares" ? 1 : row.mode === "amount" ? 100 : 0.5}
          value={row.value}
          onChange={e => onChange(row.id, { value: e.target.value })}
          placeholder={
            row.mode === "shares" ? "100" :
            row.mode === "amount" ? "5000" :
            row.mode === "target_weight" ? "15.0" :
            "5.0"
          }
          className={`${inp} tabular-nums ${row.mode === "amount" ? "pl-6" : ""} ${row.mode === "weight_pct" || row.mode === "target_weight" ? "pr-6" : ""}`}
        />
        {(row.mode === "weight_pct" || row.mode === "target_weight") && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-500 text-sm pointer-events-none select-none">%</span>
        )}
      </div>

      {/* Remove */}
      <button
        onClick={() => onRemove(row.id)}
        disabled={!canRemove}
        className="flex items-center justify-center w-9 h-9 rounded-lg text-zinc-700 hover:text-red-400 hover:bg-red-950/30 disabled:opacity-20 disabled:cursor-not-allowed transition-colors opacity-0 group-hover:opacity-100 focus:opacity-100"
        tabIndex={canRemove ? 0 : -1}
      >
        <Trash2 size={14} />
      </button>
    </div>
  );
}

// ─── Scenario summary strip ───────────────────────────────────────────────────

function ScenarioStrip({ rows }: { rows: TxRow[] }) {
  const valid  = rows.filter(r => r.ticker.trim() && Number(r.value) > 0);
  const buys   = valid.filter(r => r.action === "buy").length;
  const sells  = valid.filter(r => r.action === "sell").length;
  const tickers = new Set(valid.map(r => r.ticker.trim())).size;

  let cashEst = 0, hasCashEst = false;
  for (const r of valid) {
    if (r.mode === "amount") {
      hasCashEst = true;
      cashEst += (r.action === "buy" ? 1 : -1) * Number(r.value);
    }
  }

  if (!valid.length) {
    return <span className="text-xs text-zinc-600 italic">Add at least one transaction to run</span>;
  }

  return (
    <div className="flex items-center gap-0 flex-wrap text-xs text-zinc-500">
      <span className="font-medium text-zinc-400">{valid.length} transaction{valid.length > 1 ? "s" : ""}</span>
      {buys  > 0 && <><span className="mx-2 text-zinc-700">·</span><span className="text-blue-500">{buys} buy{buys > 1 ? "s" : ""}</span></>}
      {sells > 0 && <><span className="mx-2 text-zinc-700">·</span><span className="text-rose-500">{sells} sell{sells > 1 ? "s" : ""}</span></>}
      {tickers > 0 && <><span className="mx-2 text-zinc-700">·</span><span>{tickers} ticker{tickers > 1 ? "s" : ""}</span></>}
      {hasCashEst && (
        <>
          <span className="mx-2 text-zinc-700">·</span>
          <span className={cashEst > 0 ? "text-amber-500" : "text-emerald-500"}>
            ~${Math.abs(cashEst).toLocaleString(undefined, { maximumFractionDigits: 0 })} {cashEst > 0 ? "needed" : "freed"}
          </span>
        </>
      )}
    </div>
  );
}

// ─── Before / After metrics table ────────────────────────────────────────────

const METRIC_GROUPS = [
  {
    label: "Returns",
    rows: [
      { label: "Ann. Return",  key: "annualized_return_pct", suffix: "%",  invert: false },
      { label: "Alpha",        key: "alpha_pct",             suffix: "%",  invert: false },
      { label: "VaR (95%)",    key: "var_95_pct",            suffix: "%",  invert: true  },
    ],
  },
  {
    label: "Risk",
    rows: [
      { label: "Volatility",   key: "volatility_pct",        suffix: "%",  invert: true  },
      { label: "Max Drawdown", key: "max_drawdown_pct",       suffix: "%",  invert: false },
      { label: "Beta",         key: "beta",                   suffix: "",   invert: true  },
    ],
  },
  {
    label: "Risk-Adjusted",
    rows: [
      { label: "Sharpe",       key: "sharpe",                suffix: "",   invert: false },
      { label: "Sortino",      key: "sortino",               suffix: "",   invert: false },
    ],
  },
] as const;

type SnapKey = keyof Pick<ScenarioResponse["before"],
  "annualized_return_pct"|"alpha_pct"|"var_95_pct"|"volatility_pct"|"max_drawdown_pct"|"beta"|"sharpe"|"sortino"
>;

function MetricsComparison({ before, after }: { before: ScenarioResponse["before"]; after: ScenarioResponse["after"] }) {
  return (
    <div className="space-y-4">
      {/* Column headers */}
      <div className="grid grid-cols-[1fr_76px_76px_96px] gap-3 text-[10px] text-zinc-600 uppercase tracking-wider px-2">
        <span>Metric</span>
        <span className="text-right">Before</span>
        <span className="text-right">After</span>
        <span className="text-right">Change</span>
      </div>

      {METRIC_GROUPS.map(group => (
        <div key={group.label}>
          <div className="text-[10px] font-semibold text-zinc-700 uppercase tracking-wider mb-1 px-2">
            {group.label}
          </div>
          <div className="rounded-lg overflow-hidden border border-zinc-800/40">
            {group.rows.map((m, i) => {
              const b = before[m.key as SnapKey] as number;
              const a = after[m.key as SnapKey] as number;
              return (
                <div
                  key={m.label}
                  className={`grid grid-cols-[1fr_76px_76px_96px] gap-3 items-center px-3 py-2 text-xs transition-colors hover:bg-zinc-800/30 ${
                    i > 0 ? "border-t border-zinc-800/40" : ""
                  }`}
                >
                  <span className="text-zinc-400">{m.label}</span>
                  <span className="text-right text-zinc-500 tabular-nums">{fmt(b)}{m.suffix}</span>
                  <span className="text-right text-zinc-200 font-medium tabular-nums">{fmt(a)}{m.suffix}</span>
                  <div className="text-right">
                    <DeltaCell v={a - b} suffix={m.suffix} invert={m.invert} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Holdings change table ─────────────────────────────────────────────────────

const CHANGE_STYLE = {
  new:       { dot: "bg-blue-400",    badge: "bg-blue-950/50 text-blue-400 border-blue-800/40",    label: "New"    },
  increased: { dot: "bg-emerald-400", badge: "bg-emerald-950/40 text-emerald-400 border-emerald-800/30", label: "Buy"  },
  reduced:   { dot: "bg-amber-400",   badge: "bg-amber-950/40 text-amber-400 border-amber-800/30",  label: "Trim"   },
  exited:    { dot: "bg-rose-400",    badge: "bg-rose-950/40 text-rose-400 border-rose-800/30",     label: "Exit"   },
};

const HoldingsChangeTable = memo(function HoldingsChangeTable({
  before, after,
}: { before: HoldingSnapshot[]; after: HoldingSnapshot[] }) {
  const beforeMap = useMemo(() => Object.fromEntries(before.map(h => [h.ticker, h])), [before]);
  const afterMap  = useMemo(() => Object.fromEntries(after.map(h => [h.ticker, h])),  [after]);

  const rows = useMemo(() => {
    const afterSet = new Set(after.map(h => h.ticker));
    const exited   = before.filter(h => !afterSet.has(h.ticker));
    return [...after, ...exited];
  }, [before, after]);

  const fmtMv = (n: number) =>
    n >= 1e6 ? `$${(n/1e6).toFixed(1)}M` : n >= 1e3 ? `$${(n/1e3).toFixed(1)}K` : `$${n.toFixed(0)}`;

  return (
    <div>
      {/* Header */}
      <div className="grid grid-cols-[1fr_70px_70px_60px_60px] gap-3 text-[10px] text-zinc-600 uppercase tracking-wider px-3 pb-1.5 border-b border-zinc-800/40">
        <span>Position</span>
        <span className="text-right">Before</span>
        <span className="text-right">After</span>
        <span className="text-right" title="All weights are recomputed after simulation. Untouched positions may shift due to portfolio rebalancing.">Δ Wt ⓘ</span>
        <span className="text-right">Status</span>
      </div>

      <div className="mt-1 space-y-0.5">
        {rows.map(h => {
          const b       = beforeMap[h.ticker];
          const a       = afterMap[h.ticker];
          const change  = a?.change ?? (b && !a ? "exited" : null);
          const style   = change ? CHANGE_STYLE[change as keyof typeof CHANGE_STYLE] : null;
          const wDelta  = (a?.weight_pct ?? 0) - (b?.weight_pct ?? 0);

          return (
            <div
              key={h.ticker}
              className={`grid grid-cols-[1fr_70px_70px_60px_60px] gap-3 items-center px-3 py-2 rounded-lg text-xs ${
                !a ? "opacity-60" : ""
              }`}
            >
              {/* Ticker */}
              <div className="flex items-center gap-2 min-w-0">
                {style && <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${style.dot}`} />}
                <span className="font-mono font-medium text-zinc-200 truncate">{h.ticker}</span>
              </div>

              {/* Before weight */}
              <div className="text-right tabular-nums text-zinc-500">
                {b ? `${b.weight_pct.toFixed(1)}%` : "—"}
              </div>

              {/* After weight */}
              <div className={`text-right tabular-nums font-medium ${
                !b                         ? "text-blue-300"    :
                a && a.weight_pct > b.weight_pct ? "text-emerald-400" :
                a && a.weight_pct < b.weight_pct ? "text-amber-400"   :
                "text-zinc-300"
              }`}>
                {a ? `${a.weight_pct.toFixed(1)}%` : <span className="text-rose-500 font-normal">—</span>}
              </div>

              {/* Weight delta */}
              <div className="text-right tabular-nums">
                {Math.abs(wDelta) > 0.05 ? (
                  <span className={wDelta > 0 ? "text-emerald-400" : "text-amber-400"}>
                    {wDelta > 0 ? "+" : ""}{wDelta.toFixed(1)}%
                  </span>
                ) : <span className="text-zinc-700">—</span>}
              </div>

              {/* Badge */}
              <div className="text-right">
                {style && (
                  <span className={`inline-block text-[9px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded border ${style.badge}`}>
                    {style.label}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
});

// ─── Sector exposure ──────────────────────────────────────────────────────────

const SectorExposure = memo(function SectorExposure({
  before, after,
}: { before: Record<string,number>; after: Record<string,number> }) {
  const sectors = useMemo(() => {
    const all = new Set([...Object.keys(before), ...Object.keys(after)]);
    return [...all].sort((a, b) => (after[b] ?? 0) - (after[a] ?? 0));
  }, [before, after]);

  return (
    <div className="space-y-3">
      {sectors.map(sec => {
        const bv    = before[sec] ?? 0;
        const av    = after[sec]  ?? 0;
        const delta = av - bv;
        const isNew = bv === 0 && av > 0;
        return (
          <div key={sec}>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs text-zinc-400 flex items-center gap-1.5">
                {sec}
                {isNew && (
                  <span className="text-[9px] bg-blue-950/50 text-blue-400 px-1.5 py-px rounded border border-blue-800/40">
                    new
                  </span>
                )}
              </span>
              <span className={`text-xs font-medium tabular-nums ${
                Math.abs(delta) < 0.5 ? "text-zinc-600" :
                delta > 0 ? "text-amber-400" : "text-emerald-400"
              }`}>
                {delta > 0 ? "+" : ""}{delta.toFixed(1)}%
              </span>
            </div>
            <div className="space-y-0.5">
              {[{ label: "Before", val: bv, color: "bg-zinc-600" },
                { label: "After",  val: av, color: av > bv ? "bg-blue-500" : "bg-zinc-500" }].map(({ label, val, color }) => (
                <div key={label} className="flex items-center gap-2">
                  <span className="text-[10px] text-zinc-700 w-9 text-right shrink-0">{label}</span>
                  <div className="flex-1 h-1.5 bg-zinc-800/80 rounded-full overflow-hidden">
                    <div className={`h-full rounded-full ${color} transition-all`} style={{ width: `${Math.min(val, 100)}%` }} />
                  </div>
                  <span className="text-[10px] text-zinc-500 w-8 text-right tabular-nums shrink-0">
                    {val > 0 ? `${val.toFixed(0)}%` : "—"}
                  </span>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
});

// ─── Scenario summary card ────────────────────────────────────────────────────

function ScenarioSummaryCard({ result }: { result: ScenarioResponse }) {
  const { scenario_summary: s, holdings_before, holdings_after } = result;

  const changes = [
    ...s.tickers_added.map(t => ({ ticker: t, kind: "new" as const })),
    ...s.tickers_removed.map(t => ({ ticker: t, kind: "exited" as const })),
    ...s.tickers_changed.map(t => ({ ticker: t, kind: "changed" as const })),
  ];

  const kindStyle = {
    new:     { dot: "bg-blue-400",    text: "text-blue-400",    label: "New position" },
    exited:  { dot: "bg-rose-400",    text: "text-rose-400",    label: "Exit"         },
    changed: { dot: "bg-amber-400",   text: "text-amber-400",   label: "Reweighted"   },
  };

  const stats = [
    { label: "Txns",      value: s.transaction_count      },
    { label: "Buys",      value: s.buy_count              },
    { label: "Sells",     value: s.sell_count             },
    { label: "New",       value: s.tickers_added.length   },
    { label: "Exits",     value: s.tickers_removed.length },
    { label: "Reweights", value: s.tickers_changed.length },
  ];

  return (
    <div className="space-y-4">
      {/* Stats grid */}
      <div className="grid grid-cols-3 gap-1.5">
        {stats.map(({ label, value }) => (
          <div key={label} className="bg-zinc-800/30 rounded-lg px-2 py-2 flex flex-col gap-0.5">
            <div className="text-[9px] text-zinc-600 uppercase tracking-wide leading-none truncate">{label}</div>
            <div className="text-lg font-semibold text-zinc-200 tabular-nums leading-tight">{value}</div>
          </div>
        ))}
      </div>

      {/* Changes list */}
      {changes.length > 0 && (
        <div className="space-y-1.5">
          {changes.map(({ ticker, kind }) => {
            const style = kindStyle[kind];
            const bef = holdings_before.find(h => h.ticker === ticker);
            const aft = holdings_after.find(h => h.ticker === ticker);
            return (
              <div key={ticker} className="flex items-center gap-2.5 px-2 py-1.5 rounded-lg hover:bg-zinc-800/30 transition-colors">
                <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${style.dot}`} />
                <span className="text-sm font-mono font-medium text-zinc-200">{ticker}</span>
                <span className={`text-xs ml-auto ${style.text}`}>
                  {kind === "changed"
                    ? `${bef?.weight_pct.toFixed(1) ?? "?"}% → ${aft?.weight_pct.toFixed(1) ?? "?"}%`
                    : style.label
                  }
                </span>
              </div>
            );
          })}
        </div>
      )}

      {/* Net cash */}
      {Math.abs(s.net_cash_delta) > 100 && (
        <div className={`flex items-center gap-2 rounded-lg px-3 py-2.5 text-xs border ${
          s.net_cash_delta > 0
            ? "bg-amber-950/30 border-amber-800/40 text-amber-300"
            : "bg-emerald-950/30 border-emerald-800/40 text-emerald-300"
        }`}>
          <span className="font-medium">
            {s.net_cash_delta > 0 ? "Requires" : "Frees"}{" "}
            ~${Math.abs(s.net_cash_delta).toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </span>
          <span className={s.net_cash_delta > 0 ? "text-amber-600" : "text-emerald-600"}>
            in capital
          </span>
        </div>
      )}
    </div>
  );
}

// ─── Confirmation modal ───────────────────────────────────────────────────────

function ConfirmApplyModal({
  result, portfolioName, applying, applyError, onConfirm, onCancel,
}: {
  result:        ScenarioResponse;
  portfolioName: string;
  applying:      boolean;
  applyError:    string | null;
  onConfirm:     () => void;
  onCancel:      () => void;
}) {
  const { scenario_summary: s, delta } = result;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/75 backdrop-blur-sm" onClick={onCancel} />
      <div className="relative bg-zinc-900 border border-zinc-800 rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] flex flex-col">

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800 shrink-0">
          <div>
            <div className="text-sm font-semibold text-zinc-100">Confirm apply</div>
            <div className="text-xs text-zinc-500 mt-0.5">{portfolioName}</div>
          </div>
          <button onClick={onCancel} className="text-zinc-500 hover:text-zinc-200 transition-colors p-1">
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div className="overflow-y-auto p-5 space-y-4 flex-1">
          {/* Warning */}
          <div className="flex items-start gap-3 bg-amber-950/30 border border-amber-800/40 rounded-xl p-3.5">
            <AlertTriangle size={15} className="text-amber-400 shrink-0 mt-px" />
            <p className="text-xs text-amber-200 leading-relaxed">
              This creates real portfolio transactions and permanently updates your positions.
              The simulation record will be cleared.
            </p>
          </div>

          {/* Transaction list */}
          <div>
            <div className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-2">Transactions</div>
            <div className="space-y-1 rounded-xl border border-zinc-800/60 overflow-hidden">
              {[
                ...s.tickers_added.map(t => ({ t, kind: "buy",  label: "New position",  c: "text-blue-400"  })),
                ...s.tickers_removed.map(t => ({ t, kind: "sell", label: "Exit",         c: "text-rose-400"  })),
                ...s.tickers_changed.map(t => {
                  const bef = result.holdings_before.find(h => h.ticker === t);
                  const aft = result.holdings_after.find(h => h.ticker === t);
                  const inc = aft && bef && aft.weight_pct > bef.weight_pct;
                  return { t, kind: inc ? "buy" : "sell", label: inc ? "Increase" : "Reduce", c: inc ? "text-emerald-400" : "text-amber-400" };
                }),
              ].map(({ t, kind, label, c }, i, arr) => (
                <div key={t} className={`flex items-center justify-between px-4 py-2.5 text-sm ${
                  i < arr.length - 1 ? "border-b border-zinc-800/60" : ""
                }`}>
                  <div className="flex items-center gap-2.5">
                    <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${
                      kind === "buy"
                        ? "bg-blue-900/60 text-blue-400"
                        : "bg-rose-900/60 text-rose-400"
                    }`}>{kind}</span>
                    <span className="font-mono font-medium text-zinc-200">{t}</span>
                  </div>
                  <span className={`text-xs ${c}`}>{label}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Key metric deltas */}
          <div>
            <div className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-2">Expected impact</div>
            <div className="grid grid-cols-2 gap-1.5">
              {[
                { label: "Ann. Return", v: delta.annualized_return_pct, s: "%",  inv: false },
                { label: "Volatility",  v: delta.volatility_pct,        s: "%",  inv: true  },
                { label: "Sharpe",      v: delta.sharpe,                 s: "",   inv: false },
                { label: "Max DD",      v: delta.max_drawdown_pct,       s: "%",  inv: false },
              ].map(({ label, v, s, inv }) => (
                <div key={label} className="bg-zinc-800/40 rounded-lg px-3 py-2 flex items-center justify-between">
                  <span className="text-xs text-zinc-500">{label}</span>
                  <DeltaCell v={v} suffix={s} invert={inv} />
                </div>
              ))}
            </div>
          </div>

          {applyError && (
            <div className="flex items-start gap-2.5 bg-red-950/40 border border-red-800/50 rounded-xl p-3 text-xs text-red-300">
              <AlertTriangle size={13} className="shrink-0 mt-0.5" />
              {applyError}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-5 py-4 border-t border-zinc-800 shrink-0">
          <button
            onClick={onCancel}
            disabled={applying}
            className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200 transition-colors rounded-lg hover:bg-zinc-800 disabled:opacity-40"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={applying}
            className="flex items-center gap-2 px-5 py-2 bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 text-white text-sm font-semibold rounded-lg transition-colors"
          >
            {applying ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />}
            {applying ? "Applying…" : "Confirm & Apply"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function SimulatorTab({
  portfolioId,
  portfolioName = "Portfolio",
  prefill,
  onApplied,
}: {
  portfolioId:    string;
  portfolioName?: string;
  prefill?:       SimulatorPrefillRow[];
  onApplied?:     () => void;
}) {
  const rowsFromPrefill = (p: SimulatorPrefillRow[] | undefined): TxRow[] =>
    p && p.length > 0
      ? p.map(r => newRow({ action: r.action, ticker: r.ticker, mode: r.mode as TxRow["mode"], value: r.value }))
      : [newRow()];

  const [rows,       setRows]       = useState<TxRow[]>(() => rowsFromPrefill(prefill));
  const [loading,    setLoading]    = useState(false);
  const [error,      setError]      = useState<string | null>(null);
  const [result,     setResult]     = useState<ScenarioResponse | null>(null);
  const [applyOpen,  setApplyOpen]  = useState(false);
  const [applying,   setApplying]   = useState(false);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [applied,    setApplied]    = useState<ApplyScenarioResult | null>(null);

  // When a new prefill arrives (user clicked another suggestion while already on
  // this tab), reset the builder with the new rows.
  useEffect(() => {
    if (prefill && prefill.length > 0) {
      setRows(rowsFromPrefill(prefill));
      setResult(null);
      setApplied(null);
      setError(null);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefill]);

  const updateRow = useCallback((id: string, patch: Partial<TxRow>) => {
    setRows(r => r.map(row => row.id === id ? { ...row, ...patch } : row));
  }, []);

  const removeRow = useCallback((id: string) => {
    setRows(r => r.filter(row => row.id !== id));
  }, []);

  const addRow = useCallback(() => setRows(r => [...r, newRow()]), []);

  const handleReset = useCallback(() => {
    setRows([newRow()]);
    setResult(null);
    setApplied(null);
    setError(null);
  }, []);

  const canRun = rows.some(r => r.ticker.trim() && Number(r.value) > 0);

  const run = useCallback(async () => {
    const valid = rows.filter(r => r.ticker.trim() && Number(r.value) > 0);
    if (!valid.length) return;
    const transactions: ScenarioTransaction[] = valid.map(r => ({
      action: r.action,
      ticker: r.ticker.trim().toUpperCase(),
      mode:   r.mode,
      value:  Number(r.value),
    }));
    setLoading(true);
    setError(null);
    setResult(null);
    setApplied(null);
    try {
      setResult(await portApi.simulate(portfolioId, transactions));
    } catch (e: any) {
      setError(e.message ?? "Simulation failed");
    } finally {
      setLoading(false);
    }
  }, [rows, portfolioId]);

  const handleApplyConfirm = useCallback(async () => {
    if (!result?.scenario_id) return;
    setApplying(true);
    setApplyError(null);
    try {
      const r = await portApi.applyScenario(portfolioId, result.scenario_id);
      setApplied(r);
      setApplyOpen(false);
      setResult(null);
      onApplied?.();
    } catch (e: any) {
      setApplyError(e.message ?? "Apply failed — please try again");
    } finally {
      setApplying(false);
    }
  }, [result, portfolioId, onApplied]);

  const validCount = rows.filter(r => r.ticker.trim() && Number(r.value) > 0).length;

  return (
    <div className="max-w-[1200px] space-y-6">

      {/* ── Page header ─────────────────────────────────────────────── */}
      <div>
        <h1 className="text-xl font-semibold text-zinc-100 flex items-center gap-2.5">
          <FlaskConical size={20} className="text-blue-400" />
          Portfolio Scenario Simulator
        </h1>
        <p className="text-sm text-zinc-500 mt-1">
          Model buy, sell, and rebalance scenarios before applying them to your real portfolio
        </p>
      </div>

      {/* ── Scenario builder ────────────────────────────────────────── */}
      <div className="bg-zinc-900/50 border border-zinc-800/60 rounded-2xl overflow-hidden">

        {/* Toolbar */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-zinc-800/60 bg-zinc-900/30">
          <div className="flex items-center gap-3">
            <span className="text-xs font-semibold text-zinc-300 uppercase tracking-wider">
              Scenario Builder
            </span>
            {validCount > 0 && (
              <span className="text-[10px] bg-zinc-800 text-zinc-500 px-2 py-0.5 rounded-full tabular-nums">
                {validCount} valid
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleReset}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-zinc-500 hover:text-zinc-300 rounded-lg hover:bg-zinc-800/60 transition-colors"
            >
              <RotateCcw size={12} />
              Reset
            </button>
            <button
              onClick={run}
              disabled={loading || !canRun}
              className="flex items-center gap-2 px-4 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-semibold rounded-lg transition-colors"
            >
              {loading
                ? <Loader2 size={13} className="animate-spin" />
                : <TrendingUp size={13} />
              }
              {loading ? "Running…" : "Run Scenario"}
            </button>
          </div>
        </div>

        {/* Column header labels */}
        <div className="grid grid-cols-[100px_1fr_170px_160px_40px] gap-2 px-5 pt-3.5 pb-1">
          {["Action", "Ticker", "Mode", "Value", ""].map((h, i) => (
            <div key={i} className="text-[10px] text-zinc-600 uppercase tracking-wider">{h}</div>
          ))}
        </div>

        {/* Transaction rows */}
        <div className="px-5 pt-1.5 pb-3 space-y-2">
          {rows.map((row, i) => (
            <TransactionRow
              key={row.id}
              row={row}
              index={i}
              onChange={updateRow}
              onRemove={removeRow}
              canRemove={rows.length > 1}
            />
          ))}

          {/* Empty state */}
          {rows.length === 0 && (
            <div className="py-8 text-center text-sm text-zinc-600">
              No transactions yet — add one to start building your scenario
            </div>
          )}
        </div>

        {/* Footer: add + summary strip */}
        <div className="px-5 py-3 border-t border-zinc-800/40 bg-zinc-900/20 flex items-center gap-4">
          <button
            onClick={addRow}
            className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-200 transition-colors group"
          >
            <span className="w-5 h-5 rounded flex items-center justify-center bg-zinc-800 group-hover:bg-zinc-700 transition-colors">
              <Plus size={12} />
            </span>
            Add transaction
          </button>
          <div className="w-px h-4 bg-zinc-800" />
          <ScenarioStrip rows={rows} />
        </div>
      </div>

      {/* ── Error ──────────────────────────────────────────────────── */}
      {error && (
        <div className="flex items-start gap-3 bg-red-950/40 border border-red-800/50 rounded-xl p-4">
          <AlertTriangle size={15} className="text-red-400 shrink-0 mt-0.5" />
          <p className="text-sm text-red-300">{error}</p>
        </div>
      )}

      {/* ── Apply success banner ─────────────────────────────────── */}
      {applied && (
        <div className="flex items-center gap-3 bg-emerald-950/40 border border-emerald-800/50 rounded-xl p-4">
          <CheckCircle2 size={16} className="text-emerald-400 shrink-0" />
          <div>
            <div className="text-sm font-medium text-emerald-300">{applied.message}</div>
            <div className="text-xs text-emerald-700 mt-0.5">
              {[
                applied.positions_created > 0 && `${applied.positions_created} created`,
                applied.positions_updated > 0 && `${applied.positions_updated} updated`,
                applied.positions_closed  > 0 && `${applied.positions_closed} closed`,
              ].filter(Boolean).join(" · ")}
            </div>
          </div>
        </div>
      )}

      {/* ── Results ──────────────────────────────────────────────── */}
      {result && (
        <div className="space-y-5">

          {/* Divider */}
          <div className="flex items-center gap-4">
            <div className="h-px flex-1 bg-zinc-800/60" />
            <span className="text-[10px] text-zinc-600 uppercase tracking-widest font-medium">
              Simulation Results
            </span>
            <div className="h-px flex-1 bg-zinc-800/60" />
          </div>

          {/* Row 1: Summary card + Metrics comparison */}
          <div className="grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-5">

            {/* Scenario summary */}
            <div className="bg-zinc-900/50 border border-zinc-800/60 rounded-xl p-5">
              <div className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-4">
                Scenario Summary
              </div>
              <ScenarioSummaryCard result={result} />
            </div>

            {/* Before vs After metrics */}
            <div className="bg-zinc-900/50 border border-zinc-800/60 rounded-xl p-5">
              <div className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-4">
                Before vs After
              </div>
              <MetricsComparison before={result.before} after={result.after} />
            </div>
          </div>

          {/* Row 2: Holdings changes + Sector exposure */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            <div className="bg-zinc-900/50 border border-zinc-800/60 rounded-xl p-5">
              <div className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-4">
                Holdings Changes
              </div>
              <HoldingsChangeTable
                before={result.holdings_before}
                after={result.holdings_after}
              />
            </div>

            <div className="bg-zinc-900/50 border border-zinc-800/60 rounded-xl p-5">
              <div className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-4">
                Sector Exposure
              </div>
              <SectorExposure
                before={result.exposure.sector_before}
                after={result.exposure.sector_after}
              />
            </div>
          </div>

          {/* Row 3: Insights */}
          {result.insights.length > 0 && (
            <div className="bg-zinc-900/50 border border-zinc-800/60 rounded-xl p-5">
              <div className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-3">
                Analysis
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {result.insights.map((msg, i) => (
                  <div key={i} className="flex items-start gap-2.5 bg-zinc-800/30 rounded-lg p-3 text-sm text-zinc-300">
                    <span className="text-blue-500 shrink-0 text-xs mt-0.5">•</span>
                    {msg}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Row 4: Apply CTA bar */}
          <div className="flex items-center justify-between py-3 px-5 bg-zinc-900/50 border border-zinc-800/60 rounded-xl">
            <div>
              <p className="text-sm text-zinc-300 font-medium">Ready to apply this scenario?</p>
              <p className="text-xs text-zinc-600 mt-0.5">
                Scenario expires in 15 min · This will create real portfolio transactions
              </p>
            </div>
            <div className="flex items-center gap-3 shrink-0 ml-4">
              <button
                onClick={() => { setResult(null); }}
                className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors px-3 py-2 rounded-lg hover:bg-zinc-800"
              >
                Discard
              </button>
              <button
                onClick={() => { setApplyOpen(true); setApplyError(null); }}
                className="flex items-center gap-2 px-5 py-2.5 bg-emerald-700 hover:bg-emerald-600 text-white text-sm font-semibold rounded-lg transition-colors"
              >
                <CheckCircle2 size={15} />
                Apply to Portfolio
                <ChevronRight size={14} />
              </button>
            </div>
          </div>

        </div>
      )}

      {/* ── Confirmation modal ──────────────────────────────────────── */}
      {applyOpen && result && (
        <ConfirmApplyModal
          result={result}
          portfolioName={portfolioName}
          applying={applying}
          applyError={applyError}
          onConfirm={handleApplyConfirm}
          onCancel={() => setApplyOpen(false)}
        />
      )}
    </div>
  );
}
