"use client";
import { SentimentRegime } from "@/lib/api";

// ─── Color tokens per regime ──────────────────────────────────────────────────

const REGIME_STYLE: Record<string, {
  badge: string;
  scoreText: string;
  fill: string;
}> = {
  "Extreme Fear":      { badge: "bg-red-950/70 text-red-400 border-red-900",            scoreText: "text-red-400",     fill: "bg-red-600/70"      },
  "Fear":              { badge: "bg-orange-950/60 text-orange-400 border-orange-900",   scoreText: "text-orange-400",  fill: "bg-orange-500/70"   },
  "Neutral":           { badge: "bg-zinc-800/70 text-zinc-300 border-zinc-700",         scoreText: "text-zinc-300",    fill: "bg-zinc-500/70"     },
  "Greed":             { badge: "bg-emerald-950/70 text-emerald-400 border-emerald-900",scoreText: "text-emerald-400", fill: "bg-emerald-500/70"  },
  "Extreme Greed":     { badge: "bg-emerald-950/80 text-emerald-300 border-emerald-700",scoreText: "text-emerald-300", fill: "bg-emerald-400/70"  },
  "Insufficient data": { badge: "bg-zinc-900/50 text-zinc-600 border-zinc-800",         scoreText: "text-zinc-600",    fill: "bg-zinc-700/50"     },
};

// ─── Main score bar with position marker ─────────────────────────────────────

function MainScoreBar({ score, label }: { score: number; label: string }) {
  const style = REGIME_STYLE[label] ?? REGIME_STYLE["Neutral"];
  const pct   = Math.max(0, Math.min(100, score));

  return (
    <div className="space-y-1.5">
      {/* Track */}
      <div className="relative h-2.5 bg-zinc-800 rounded-full">
        {/* Zone boundary ticks at 40 and 60 */}
        <div className="absolute inset-y-0 left-[40%] w-px bg-zinc-700/60" />
        <div className="absolute inset-y-0 left-[60%] w-px bg-zinc-700/60" />
        {/* Fill */}
        <div
          className={`absolute inset-y-0 left-0 rounded-l-full ${style.fill}`}
          style={{ width: `${pct}%` }}
        />
        {/* Position marker: white ring */}
        <div
          className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-zinc-950 border-2 border-zinc-200 shadow-sm"
          style={{ left: `calc(${pct}% - 6px)` }}
        />
      </div>
      {/* Zone labels */}
      <div className="flex justify-between text-[10px] text-zinc-700 px-0.5 select-none">
        <span>Fear</span>
        <span>Neutral</span>
        <span>Greed</span>
      </div>
    </div>
  );
}

// ─── Per-component bar row ────────────────────────────────────────────────────

function ComponentBar({ label, value }: { label: string; value: number | null | undefined }) {
  if (value === null || value === undefined) return null;

  const pct   = Math.max(0, Math.min(100, value));
  const fill  = pct >= 65 ? "bg-emerald-500/70" : pct >= 40 ? "bg-zinc-500/60" : "bg-red-500/70";
  const digit = pct >= 65 ? "text-emerald-400"  : pct >= 40 ? "text-zinc-400"  : "text-red-400";

  return (
    <div className="grid grid-cols-[7.5rem_1fr_2rem] items-center gap-2">
      <span className="text-[11px] text-zinc-500 leading-none truncate">{label}</span>
      <div className="h-1.5 bg-zinc-800/80 rounded-full overflow-hidden">
        <div className={`h-1.5 rounded-full ${fill}`} style={{ width: `${pct}%` }} />
      </div>
      <span className={`text-[11px] ${digit} text-right tabular-nums leading-none`}>{value}</span>
    </div>
  );
}

// ─── Card ─────────────────────────────────────────────────────────────────────

export default function SentimentRegimeCard({ regime }: { regime: SentimentRegime }) {
  const style   = REGIME_STYLE[regime.label] ?? REGIME_STYLE["Neutral"];
  const hasData = regime.score !== null && regime.meta?.inputs_available !== false;
  const version = regime.meta?.version;

  const comps = regime.components ?? {};
  const hasComponents = Object.values(comps).some(v => v !== null && v !== undefined);

  return (
    <div className="bg-zinc-900/60 border border-zinc-800/60 rounded-xl p-4 space-y-3.5">

      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">
            Sentiment Regime
          </span>
          <span className="text-[10px] text-zinc-500 border border-zinc-700/60 bg-zinc-800/40 px-1.5 py-0.5 rounded leading-none">
            Computed
          </span>
          <span className="text-[10px] text-zinc-700 border border-zinc-800 bg-zinc-900/40 px-1.5 py-0.5 rounded leading-none">
            Experimental
          </span>
        </div>
        <span className="text-[10px] text-zinc-600 shrink-0 mt-0.5 leading-none">
          Secondary signal
        </span>
      </div>

      {/* ── Fallback ────────────────────────────────────────────────────── */}
      {!hasData ? (
        <p className="text-sm text-zinc-500 py-1">
          Insufficient data to compute sentiment regime.
        </p>
      ) : (
        <>
          {/* ── Score row ─────────────────────────────────────────────── */}
          <div className="flex items-center gap-3">
            <span className={`text-2xl font-bold tabular-nums leading-none ${style.scoreText}`}>
              {regime.score}
            </span>
            <span className={`inline-flex items-center text-xs font-semibold px-2 py-1 rounded-lg border ${style.badge}`}>
              {regime.label}
            </span>
          </div>

          {/* ── Score bar ─────────────────────────────────────────────── */}
          <MainScoreBar score={regime.score!} label={regime.label} />

          {/* ── Component breakdown ───────────────────────────────────── */}
          {hasComponents && (
            <div className="space-y-2 pt-0.5">
              <ComponentBar label="Momentum"            value={comps.momentum} />
              <ComponentBar label="Volatility / Stress" value={comps.volatility_stress} />
              <ComponentBar label="Positioning"         value={comps.positioning} />
              <ComponentBar label="Expect. Pressure"    value={comps.expectation_pressure} />
            </div>
          )}

          {/* ── Drivers + Warnings ────────────────────────────────────── */}
          {(regime.drivers.length > 0 || regime.warnings.length > 0) && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 border-t border-zinc-800/50">
              {regime.drivers.length > 0 && (
                <div>
                  <div className="text-[10px] font-semibold text-zinc-600 uppercase tracking-wider mb-1.5">
                    Drivers
                  </div>
                  <ul className="space-y-1.5">
                    {regime.drivers.map((d, i) => (
                      <li key={i} className="text-xs text-zinc-400 flex gap-1.5 items-start leading-relaxed">
                        <span className="text-emerald-500/80 shrink-0 mt-px leading-none">↑</span>
                        {d}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {regime.warnings.length > 0 && (
                <div>
                  <div className="text-[10px] font-semibold text-zinc-600 uppercase tracking-wider mb-1.5">
                    Cautions
                  </div>
                  <ul className="space-y-1.5">
                    {regime.warnings.map((w, i) => (
                      <li key={i} className="text-xs text-zinc-400 flex gap-1.5 items-start leading-relaxed">
                        <span className="text-amber-500/80 shrink-0 mt-px leading-none">⚠</span>
                        {w}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </>
      )}

      {/* ── Footer ──────────────────────────────────────────────────────── */}
      <div className="text-[10px] text-zinc-700 pt-1 border-t border-zinc-800/40 leading-relaxed">
        {regime.type} · Weighted average of 4 components (0–100). Not investment advice.
        {version && <span className="ml-1">· {version}</span>}
      </div>
    </div>
  );
}
