"use client";
import { useState, useMemo, useCallback, memo } from "react";
import { TrendingUp, Loader2, FlaskConical } from "lucide-react";
import { portfolios as portApi, SimulateResponse } from "@/lib/api";

// ─────────────────────────────────────────────────────────────────────────────
// PART 1 — Risk vs Return scatter (pure SVG, ~0ms render)
// ─────────────────────────────────────────────────────────────────────────────

interface ScatterPoint { x: number; y: number; label: string; color: string; }

interface RiskReturnChartProps {
  before: { vol: number; ret: number };
  after:  { vol: number; ret: number };
}

const RiskReturnChart = memo(function RiskReturnChart({ before, after }: RiskReturnChartProps) {
  const [hovered, setHovered] = useState<"before" | "after" | null>(null);

  const W = 320, H = 200;
  const PAD = { top: 24, right: 56, bottom: 36, left: 52 };
  const CW  = W - PAD.left - PAD.right;
  const CH  = H - PAD.top  - PAD.bottom;

  // Scale with 25% padding around data range
  const xs = [before.vol, after.vol];
  const ys = [before.ret, after.ret];
  const xMin = Math.min(...xs), xMax = Math.max(...xs);
  const yMin = Math.min(...ys), yMax = Math.max(...ys);
  const xPad = Math.max((xMax - xMin) * 0.6, 1.5);
  const yPad = Math.max((yMax - yMin) * 0.6, 3);
  const xL = xMin - xPad, xR = xMax + xPad;
  const yB = yMin - yPad, yT = yMax + yPad;

  const tx = (v: number) => PAD.left + ((v - xL) / (xR - xL)) * CW;
  const ty = (v: number) => PAD.top  + ((yT - v) / (yT - yB)) * CH;

  const bx = tx(before.vol), by = ty(before.ret);
  const ax = tx(after.vol),  ay = ty(after.ret);

  // Arrow direction
  const dx = ax - bx, dy = ay - by;
  const len = Math.sqrt(dx * dx + dy * dy) || 1;
  const ux = dx / len, uy = dy / len;
  const R = 9;  // point radius
  const arrowStart = { x: bx + ux * (R + 2), y: by + uy * (R + 2) };
  const arrowEnd   = { x: ax - ux * (R + 2), y: ay - uy * (R + 2) };
  const hasArrow   = len > R * 3;

  // Tick helpers
  const xTick = (v: number) => `${v.toFixed(1)}%`;
  const yTick = (v: number) => `${v.toFixed(0)}%`;

  // Whether "after" is strictly better (higher return, lower or equal vol)
  const improved = after.ret > before.ret && after.vol <= before.vol + 0.1;
  const afterColor = improved ? "#34d399" : "#60a5fa";  // emerald or blue

  const tooltipData = {
    before: { label: "Before", vol: before.vol, ret: before.ret },
    after:  { label: "After",  vol: after.vol,  ret: after.ret  },
  };

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 200 }}>
        <defs>
          <marker id="arrowhead" markerWidth="6" markerHeight="6"
            refX="3" refY="3" orient="auto">
            <path d="M0,0 L0,6 L6,3 z" fill="#71717a" />
          </marker>
          {/* subtle grid */}
          <pattern id="sim-grid" width={(CW/4).toFixed(0)} height={(CH/4).toFixed(0)} patternUnits="userSpaceOnUse"
            x={PAD.left} y={PAD.top}>
            <path d={`M ${(CW/4).toFixed(0)} 0 L 0 0 0 ${(CH/4).toFixed(0)}`}
              fill="none" stroke="#27272a" strokeWidth="0.5" />
          </pattern>
        </defs>

        {/* Grid */}
        <rect x={PAD.left} y={PAD.top} width={CW} height={CH} fill="url(#sim-grid)" />
        <rect x={PAD.left} y={PAD.top} width={CW} height={CH} fill="none" stroke="#3f3f46" strokeWidth="0.5" />

        {/* X axis label */}
        <text x={PAD.left + CW / 2} y={H - 4} textAnchor="middle"
          className="text-xs" fill="#71717a" fontSize="10">
          Volatility (%)
        </text>

        {/* Y axis label */}
        <text x={10} y={PAD.top + CH / 2} textAnchor="middle"
          fill="#71717a" fontSize="10"
          transform={`rotate(-90, 10, ${PAD.top + CH / 2})`}>
          Return (%)
        </text>

        {/* X ticks */}
        {[0.25, 0.5, 0.75].map(f => {
          const v = xL + f * (xR - xL);
          const x = tx(v);
          return (
            <g key={f}>
              <line x1={x} y1={PAD.top} x2={x} y2={PAD.top + CH} stroke="#27272a" strokeWidth="0.5" />
              <text x={x} y={PAD.top + CH + 12} textAnchor="middle" fill="#52525b" fontSize="9">
                {xTick(v)}
              </text>
            </g>
          );
        })}

        {/* Y ticks */}
        {[0.25, 0.5, 0.75].map(f => {
          const v = yB + f * (yT - yB);
          const y = ty(v);
          return (
            <g key={f}>
              <line x1={PAD.left} y1={y} x2={PAD.left + CW} y2={y} stroke="#27272a" strokeWidth="0.5" />
              <text x={PAD.left - 5} y={y + 3} textAnchor="end" fill="#52525b" fontSize="9">
                {yTick(v)}
              </text>
            </g>
          );
        })}

        {/* Arrow: before → after */}
        {hasArrow && (
          <line
            x1={arrowStart.x} y1={arrowStart.y}
            x2={arrowEnd.x}   y2={arrowEnd.y}
            stroke="#52525b" strokeWidth="1.5" strokeDasharray="3 2"
            markerEnd="url(#arrowhead)"
          />
        )}

        {/* Before point */}
        <circle cx={bx} cy={by} r={R} fill="#71717a" stroke="#a1a1aa" strokeWidth="1.5"
          className="cursor-pointer"
          onMouseEnter={() => setHovered("before")} onMouseLeave={() => setHovered(null)} />
        <text x={bx} y={by - R - 4} textAnchor="middle" fill="#a1a1aa" fontSize="9" fontWeight="600">
          Before
        </text>

        {/* After point */}
        <circle cx={ax} cy={ay} r={R} fill={afterColor} stroke="white" strokeWidth="1.5"
          className="cursor-pointer"
          onMouseEnter={() => setHovered("after")} onMouseLeave={() => setHovered(null)} />
        <text x={ax} y={ay - R - 4} textAnchor="middle" fill={afterColor} fontSize="9" fontWeight="600">
          After
        </text>

        {/* Tooltip */}
        {hovered && (() => {
          const d = tooltipData[hovered];
          const cx = hovered === "before" ? bx : ax;
          const cy = hovered === "before" ? by : ay;
          const tx2 = cx > W * 0.6 ? cx - 84 : cx + 12;
          const ty2 = cy > H * 0.6 ? cy - 42 : cy + 8;
          return (
            <g>
              <rect x={tx2} y={ty2} width={80} height={34} rx="4"
                fill="#18181b" stroke="#3f3f46" strokeWidth="0.8" />
              <text x={tx2 + 8} y={ty2 + 13} fill="#e4e4e7" fontSize="9" fontWeight="600">
                {d.label}
              </text>
              <text x={tx2 + 8} y={ty2 + 24} fill="#a1a1aa" fontSize="8">
                R: {d.ret.toFixed(1)}%  Vol: {d.vol.toFixed(1)}%
              </text>
            </g>
          );
        })()}
      </svg>

      {/* Efficiency callout */}
      <p className="text-center text-xs mt-1">
        {improved
          ? <span className="text-emerald-400">Higher return, controlled risk ↗</span>
          : after.ret > before.ret
          ? <span className="text-amber-400">Higher return, higher risk ↗</span>
          : after.vol < before.vol
          ? <span className="text-blue-400">Lower risk, lower return ↙</span>
          : <span className="text-zinc-500">Minimal efficiency change</span>
        }
      </p>
    </div>
  );
});

// ─────────────────────────────────────────────────────────────────────────────
// PART 2 — Delta bar chart (zero-centered, CSS only)
// ─────────────────────────────────────────────────────────────────────────────

interface DeltaBarItem {
  label:  string;
  value:  number;   // raw delta
  suffix: string;
  invert: boolean;  // true = lower is better (volatility, drawdown)
}

interface DeltaBarChartProps { items: DeltaBarItem[]; }

const DeltaBarChart = memo(function DeltaBarChart({ items }: DeltaBarChartProps) {
  const maxAbs = useMemo(
    () => Math.max(...items.map(i => Math.abs(i.value)), 0.001),
    [items],
  );

  return (
    <div className="space-y-2.5">
      {items.map(({ label, value, suffix, invert }) => {
        const isGood    = invert ? value < 0 : value > 0;
        const isBad     = invert ? value > 0 : value < 0;
        const barColor  = isGood ? "bg-emerald-500" : isBad ? "bg-red-500" : "bg-zinc-600";
        const pct       = Math.min(Math.abs(value) / maxAbs * 50, 50);  // max 50% of half-width
        const isNeg     = value < 0;
        const valStr    = `${value > 0 ? "+" : ""}${value.toFixed(2)}${suffix}`;

        return (
          <div key={label} className="flex items-center gap-2">
            {/* Label */}
            <div className="w-20 text-xs text-zinc-400 shrink-0 text-right">{label}</div>

            {/* Zero-centered bar container */}
            <div className="flex-1 flex items-center">
              <div className="w-1/2 flex justify-end">
                {isNeg && (
                  <div className={`h-4 rounded-l ${barColor} transition-all`}
                    style={{ width: `${pct * 2}%` }} />
                )}
              </div>
              <div className="w-px h-4 bg-zinc-600 shrink-0" />
              <div className="w-1/2">
                {!isNeg && Math.abs(value) > 0.0001 && (
                  <div className={`h-4 rounded-r ${barColor} transition-all`}
                    style={{ width: `${pct * 2}%` }} />
                )}
              </div>
            </div>

            {/* Value */}
            <div className={`w-16 text-xs text-right shrink-0 font-medium
              ${isGood ? "text-emerald-400" : isBad ? "text-red-400" : "text-zinc-500"}`}>
              {Math.abs(value) < 0.0001 ? "—" : valStr}
            </div>
          </div>
        );
      })}

      {/* Legend */}
      <div className="flex items-center gap-4 pt-1 text-xs text-zinc-600">
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-emerald-500 inline-block" /> improvement</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-red-500 inline-block" /> deterioration</span>
      </div>
    </div>
  );
});

// ─────────────────────────────────────────────────────────────────────────────
// PART 3 — Sector exposure side-by-side comparison (CSS only)
// ─────────────────────────────────────────────────────────────────────────────

interface ExposureComparisonProps {
  before:    Record<string, number>;
  after:     Record<string, number>;
  newTicker: string;
}

const ExposureComparison = memo(function ExposureComparison({
  before, after, newTicker,
}: ExposureComparisonProps) {
  const sectors = useMemo(() => {
    const all = new Set([...Object.keys(before), ...Object.keys(after)]);
    return [...all].sort((a, b) => (after[b] ?? 0) - (after[a] ?? 0));
  }, [before, after]);

  const topSector = sectors[0];
  const shift = topSector ? (after[topSector] ?? 0) - (before[topSector] ?? 0) : 0;

  return (
    <div>
      <div className="space-y-3">
        {sectors.map(sec => {
          const bv = before[sec] ?? 0;
          const av = after[sec]  ?? 0;
          const delta = av - bv;
          const isNew = bv === 0 && av > 0;

          return (
            <div key={sec}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-zinc-400 flex items-center gap-1.5">
                  {sec}
                  {isNew && (
                    <span className="text-[10px] bg-blue-900/50 text-blue-400 px-1.5 py-0.5 rounded-full">
                      new
                    </span>
                  )}
                </span>
                <span className={`text-xs font-medium ${
                  delta > 0.5 ? "text-amber-400" : delta < -0.5 ? "text-emerald-400" : "text-zinc-500"
                }`}>
                  {delta > 0 ? "+" : ""}{delta.toFixed(1)}%
                </span>
              </div>
              {/* Two bars stacked */}
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-zinc-600 w-10 shrink-0">Before</span>
                  <div className="flex-1 h-2 bg-zinc-800 rounded-full overflow-hidden">
                    <div className="h-full bg-zinc-600 rounded-full transition-all"
                      style={{ width: `${Math.min(bv, 100)}%` }} />
                  </div>
                  <span className="text-[10px] text-zinc-500 w-8 text-right">{bv > 0 ? bv.toFixed(0) + "%" : "—"}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-zinc-600 w-10 shrink-0">After</span>
                  <div className="flex-1 h-2 bg-zinc-800 rounded-full overflow-hidden">
                    <div className={`h-full rounded-full transition-all ${av > bv ? "bg-blue-500" : "bg-zinc-500"}`}
                      style={{ width: `${Math.min(av, 100)}%` }} />
                  </div>
                  <span className="text-[10px] text-zinc-500 w-8 text-right">{av > 0 ? av.toFixed(0) + "%" : "—"}</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {topSector && Math.abs(shift) > 1 && (
        <p className="mt-3 text-xs text-zinc-500">
          {shift > 0
            ? <span>Largest shift: <span className="text-amber-400">{topSector}</span> increases by {shift.toFixed(1)}%</span>
            : <span>Largest shift: <span className="text-emerald-400">{topSector}</span> decreases by {Math.abs(shift).toFixed(1)}%</span>
          }
        </p>
      )}
    </div>
  );
});

// ─────────────────────────────────────────────────────────────────────────────
// PART 4 — Correlation bar
// ─────────────────────────────────────────────────────────────────────────────

function CorrelationBar({ corr, ticker }: { corr: number; ticker: string }) {
  const pct   = Math.min(Math.max(corr, 0), 1) * 100;
  const color = corr < 0.3 ? "bg-emerald-500" : corr < 0.7 ? "bg-amber-500" : "bg-red-500";
  const label = corr < 0.3 ? "low — strong diversification"
              : corr < 0.7 ? "moderate — partial diversification"
              : "high — limited diversification";

  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs text-zinc-400">Correlation with portfolio</span>
        <span className={`text-xs font-semibold ${
          corr < 0.3 ? "text-emerald-400" : corr < 0.7 ? "text-amber-400" : "text-red-400"
        }`}>{corr.toFixed(2)}</span>
      </div>
      <div className="relative h-3 bg-zinc-800 rounded-full overflow-hidden">
        {/* Threshold markers */}
        <div className="absolute top-0 bottom-0 w-px bg-zinc-600" style={{ left: "30%" }} />
        <div className="absolute top-0 bottom-0 w-px bg-zinc-600" style={{ left: "70%" }} />
        {/* Fill */}
        <div className={`h-full rounded-full transition-all ${color}`}
          style={{ width: `${pct}%` }} />
      </div>
      <div className="flex justify-between mt-0.5 text-[9px] text-zinc-600">
        <span>0.0</span><span>0.3</span><span>0.7</span><span>1.0</span>
      </div>
      <p className="text-xs text-zinc-500 mt-1.5">{ticker}: {label}</p>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Small metrics table (kept as reference, deprioritized)
// ─────────────────────────────────────────────────────────────────────────────

function fmt(v: number, d = 2) { return v.toFixed(d); }

function MetricRow({ label, before, after, suffix = "", invert = false }:
  { label: string; before: number; after: number; suffix?: string; invert?: boolean }) {
  const delta  = after - before;
  const isGood = invert ? delta < 0 : delta > 0;
  const isBad  = invert ? delta > 0 : delta < 0;
  return (
    <div className="grid grid-cols-4 gap-2 py-1.5 border-b border-zinc-800/50 text-xs items-center">
      <span className="text-zinc-500">{label}</span>
      <span className="text-zinc-400 text-right">{fmt(before)}{suffix}</span>
      <span className="text-zinc-200 text-right font-medium">{fmt(after)}{suffix}</span>
      <span className={`text-right font-medium text-xs ${isGood ? "text-emerald-400" : isBad ? "text-red-400" : "text-zinc-600"}`}>
        {Math.abs(delta) < 0.0001 ? "—" : `${delta > 0 ? "+" : ""}${fmt(delta)}`}
      </span>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main component
// ─────────────────────────────────────────────────────────────────────────────

export default function SimulatorTab({ portfolioId }: { portfolioId: string }) {
  const [ticker,    setTicker]    = useState("");
  const [weightPct, setWeightPct] = useState(10);
  const [loading,   setLoading]   = useState(false);
  const [error,     setError]     = useState<string | null>(null);
  const [result,    setResult]    = useState<SimulateResponse | null>(null);

  const run = useCallback(async () => {
    const t = ticker.trim().toUpperCase();
    if (!t) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await portApi.simulate(portfolioId, t, weightPct));
    } catch (e: any) {
      setError(e.message ?? "Simulation failed");
    } finally {
      setLoading(false);
    }
  }, [ticker, weightPct, portfolioId]);

  // Memoize delta items so DeltaBarChart doesn't recompute
  const deltaItems = useMemo<DeltaBarItem[]>(() => {
    if (!result) return [];
    return [
      { label: "Ann. Return", value: result.delta.annualized_return_pct, suffix: "%", invert: false },
      { label: "Volatility",  value: result.delta.volatility_pct,        suffix: "%", invert: true  },
      { label: "Sharpe",      value: result.delta.sharpe,                suffix: "",  invert: false },
      { label: "Beta",        value: result.delta.beta,                  suffix: "",  invert: true  },
      { label: "Max DD",      value: result.delta.max_drawdown_pct,      suffix: "%", invert: false },
    ];
  }, [result]);

  return (
    <div className="space-y-6 max-w-4xl">

      {/* ── Header ─────────────────────────────────────── */}
      <div>
        <h2 className="text-lg font-semibold text-zinc-100 flex items-center gap-2">
          <FlaskConical size={18} className="text-blue-400" />
          Portfolio Simulator
        </h2>
        <p className="text-sm text-zinc-500 mt-0.5">
          See how adding a new position affects your risk–return profile and sector exposure.
        </p>
      </div>

      {/* ── Input form ─────────────────────────────────── */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
        <div className="flex flex-col sm:flex-row gap-4 items-end">
          <div className="flex-1">
            <label className="block text-xs text-zinc-500 mb-1.5 font-medium">Ticker to add</label>
            <input
              value={ticker}
              onChange={e => setTicker(e.target.value.toUpperCase())}
              onKeyDown={e => e.key === "Enter" && run()}
              placeholder="e.g. NVDA"
              className="w-full bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-50 placeholder:text-zinc-600 focus:outline-none focus:border-blue-500"
            />
          </div>
          <div className="w-44">
            <label className="block text-xs text-zinc-500 mb-1.5 font-medium">
              Weight: <span className="text-zinc-200 font-semibold">{weightPct}%</span>
            </label>
            <input type="range" min={1} max={49} step={1}
              value={weightPct}
              onChange={e => setWeightPct(Number(e.target.value))}
              className="w-full accent-blue-500" />
            <div className="flex justify-between text-[9px] text-zinc-600 mt-0.5">
              <span>1%</span><span>25%</span><span>49%</span>
            </div>
          </div>
          <button
            onClick={run}
            disabled={loading || !ticker.trim()}
            className="flex items-center gap-2 px-5 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium rounded-lg transition-colors shrink-0"
          >
            {loading
              ? <Loader2 size={14} className="animate-spin" />
              : <TrendingUp size={14} />
            }
            {loading ? "Simulating…" : "Simulate"}
          </button>
        </div>
      </div>

      {/* ── Error ──────────────────────────────────────── */}
      {error && (
        <div className="bg-red-950/40 border border-red-800/50 rounded-xl p-4 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* ── Results ────────────────────────────────────── */}
      {result && (
        <div className="space-y-5">

          {/* ── ROW 1: Risk/Return scatter + Delta bars ── */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">

            {/* Risk–Return scatter */}
            <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
              <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wide mb-3">
                Risk vs Return
              </h3>
              <RiskReturnChart
                before={{ vol: result.before.volatility_pct, ret: result.before.annualized_return_pct }}
                after ={{ vol: result.after.volatility_pct,  ret: result.after.annualized_return_pct  }}
              />
            </div>

            {/* Delta bars + Correlation */}
            <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-5">
              <div>
                <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wide mb-3">
                  Impact of adding {ticker} at {result.new_ticker_weight_pct}%
                </h3>
                <DeltaBarChart items={deltaItems} />
              </div>

              {result.correlation_with_portfolio != null && (
                <div className="border-t border-zinc-800 pt-4">
                  <CorrelationBar
                    corr={result.correlation_with_portfolio}
                    ticker={ticker}
                  />
                </div>
              )}
            </div>
          </div>

          {/* ── ROW 2: Insights ─────────────────────────── */}
          {result.insights.length > 0 && (
            <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
              <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wide mb-3">
                Insights
              </h3>
              <ul className="space-y-2">
                {result.insights.map((msg, i) => (
                  <li key={i} className="flex gap-2 text-sm text-zinc-300">
                    <span className="text-blue-400 shrink-0 mt-0.5">•</span>
                    {msg}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* ── ROW 3: Sector exposure comparison ───────── */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
            <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wide mb-4">
              Sector Exposure Shift
            </h3>
            <ExposureComparison
              before={result.exposure.sector_before}
              after={result.exposure.sector_after}
              newTicker={ticker}
            />
          </div>

          {/* ── ROW 4: Full numbers (reference, secondary) ─ */}
          <details className="group">
            <summary className="cursor-pointer text-xs text-zinc-500 hover:text-zinc-300 transition-colors flex items-center gap-1.5 select-none">
              <span className="group-open:rotate-90 transition-transform inline-block">▶</span>
              Full metrics table
            </summary>
            <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 mt-3">
              <div className="grid grid-cols-4 gap-2 text-[10px] text-zinc-600 mb-1 font-medium uppercase">
                <span>Metric</span>
                <span className="text-right">Before</span>
                <span className="text-right">After</span>
                <span className="text-right">Δ</span>
              </div>
              <MetricRow label="Sharpe"      before={result.before.sharpe}                after={result.after.sharpe} />
              <MetricRow label="Sortino"     before={result.before.sortino}               after={result.after.sortino} />
              <MetricRow label="Volatility"  before={result.before.volatility_pct}        after={result.after.volatility_pct}        suffix="%" invert />
              <MetricRow label="Max DD"      before={result.before.max_drawdown_pct}      after={result.after.max_drawdown_pct}      suffix="%" />
              <MetricRow label="Beta"        before={result.before.beta}                  after={result.after.beta}                  invert />
              <MetricRow label="Alpha"       before={result.before.alpha_pct}             after={result.after.alpha_pct}             suffix="%" />
              <MetricRow label="Ann. Return" before={result.before.annualized_return_pct} after={result.after.annualized_return_pct} suffix="%" />
              <MetricRow label="VaR 95%"     before={result.before.var_95_pct}            after={result.after.var_95_pct}            suffix="%" invert />
            </div>
          </details>

        </div>
      )}
    </div>
  );
}
