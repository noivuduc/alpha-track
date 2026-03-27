/**
 * Portfolio analytics: risk metrics, return series, drawdown, heatmap.
 * All return values are in decimal form unless noted (e.g. 0.05 = 5%).
 */

export interface HistoryBar { ts: string; close: number; }

// ─── Return series ─────────────────────────────────────────────────────────────

/** Daily log returns from a close price series. */
export function dailyReturns(closes: number[]): number[] {
  const r: number[] = [];
  for (let i = 1; i < closes.length; i++) {
    r.push((closes[i] - closes[i - 1]) / closes[i - 1]);
  }
  return r;
}

/** Cumulative wealth index, normalised to `base` at t=0. */
export function cumulative(returns: number[], base = 100): number[] {
  let v = base;
  const out = [base];
  for (const r of returns) {
    v *= 1 + r;
    out.push(v);
  }
  return out;
}

// ─── Basic stats ───────────────────────────────────────────────────────────────

export function mean(arr: number[]): number {
  return arr.length === 0 ? 0 : arr.reduce((a, b) => a + b, 0) / arr.length;
}

export function stdDev(arr: number[]): number {
  if (arr.length < 2) return 0;
  const m = mean(arr);
  return Math.sqrt(arr.reduce((acc, v) => acc + (v - m) ** 2, 0) / (arr.length - 1));
}

// ─── Risk metrics ─────────────────────────────────────────────────────────────
// NOTE: sharpe, sortino, beta, alpha, calmar, winRate, annualisedVol, and VaR
// are computed exclusively on the backend. Frontend only renders values returned
// from the API — do NOT add client-side implementations of these metrics.

/** Max peak-to-trough drawdown as a percentage (e.g. -23.5). */
export function maxDrawdown(closes: number[]): number {
  let peak = -Infinity;
  let maxDD = 0;
  for (const v of closes) {
    if (v > peak) peak = v;
    const dd = (v - peak) / peak;
    if (dd < maxDD) maxDD = dd;
  }
  return maxDD * 100;
}

/** Drawdown series (% from running peak) for charting. */
export function drawdownSeries(closes: number[]): { i: number; dd: number }[] {
  let peak = -Infinity;
  return closes.map((v, i) => {
    if (v > peak) peak = v;
    return { i, dd: (v - peak) / peak * 100 };
  });
}

// ─── Shared type re-exports ───────────────────────────────────────────────────
// MonthlyReturn is the canonical type for backend monthly_returns_twr data.
// The function monthlyReturns() was removed — use the backend field directly.
export interface MonthlyReturn { year: number; month: number; label: string; value: number; }

// ─── Formatting helpers ───────────────────────────────────────────────────────

export const fmt = (n: number | null | undefined, d = 2): string =>
  n == null ? '—' : n.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });

export const fmtPct = (n: number | null | undefined, d = 2): string =>
  n == null ? '—' : `${n >= 0 ? '+' : ''}${fmt(n, d)}%`;

export const fmtCurrency = (n: number | null | undefined): string =>
  n == null ? '—' : `$${Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export const fmtLarge = (n: number | null | undefined): string => {
  if (n == null) return '—';
  if (Math.abs(n) >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  if (Math.abs(n) >= 1e3) return `$${(n / 1e3).toFixed(2)}K`;
  return fmtCurrency(n);
};

export const gainClass = (n: number | null | undefined): string =>
  n == null ? 'text-zinc-400' : n >= 0 ? 'text-emerald-400' : 'text-red-400';
