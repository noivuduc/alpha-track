"use client";
import { useEffect, useState } from "react";
import { Position, market, Fundamentals } from "@/lib/api";
import { fmtLarge, fmtPct } from "@/lib/portfolio-math";

interface Props { positions: Position[]; }

type TrafficLight = "green" | "amber" | "red" | "gray";

function getLight(value: number | null | undefined, thresholds: [number, number]): TrafficLight {
  if (value == null) return "gray";
  if (value >= thresholds[0]) return "green";
  if (value >= thresholds[1]) return "amber";
  if (value >= 0) return "red";
  return "red";
}

const lightClass: Record<TrafficLight, string> = {
  green: "bg-emerald-500",
  amber: "bg-amber-500",
  red:   "bg-red-500",
  gray:  "bg-zinc-700",
};

function MarginBar({ label, value, thresholds }: { label: string; value: number | null | undefined; thresholds: [number, number] }) {
  const light = getLight(value, thresholds);
  const barW  = value == null ? 0 : Math.min(Math.max(value, 0), 100);
  return (
    <div className="flex items-center gap-3">
      <span className="text-zinc-500 text-xs w-24 shrink-0">{label}</span>
      <div className="flex-1 relative h-4 bg-zinc-800 rounded overflow-hidden">
        <div
          className={`h-full rounded ${
            light === "green" ? "bg-emerald-500/70" : light === "amber" ? "bg-amber-500/70" : value != null && value < 0 ? "bg-red-500/70" : "bg-zinc-700"
          }`}
          style={{ width: `${barW}%` }}
        />
      </div>
      <div className="flex items-center gap-1.5 w-20 justify-end">
        <span className={`w-2 h-2 rounded-full ${lightClass[light]}`} />
        <span className={`font-mono text-xs tabular-nums ${
          light === "green" ? "text-emerald-400" : light === "amber" ? "text-amber-400" : value != null && value < 0 ? "text-red-400" : "text-zinc-500"
        }`}>
          {value != null ? fmtPct(value, 1) : "N/A"}
        </span>
      </div>
    </div>
  );
}

interface FundRow { ticker: string; data: Fundamentals | null; error?: string; }

export default function FundamentalsTab({ positions }: Props) {
  const [rows,    setRows]    = useState<FundRow[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!positions.length) { setRows([]); return; }
    const tickers = [...new Set(positions.map(p => p.ticker))];
    setLoading(true);
    setRows(tickers.map(ticker => ({ ticker, data: null })));

    Promise.all(
      tickers.map(ticker =>
        market.fundamentals(ticker)
          .then(data => ({ ticker, data }))
          .catch(e  => ({ ticker, data: null, error: e.message }))
      )
    )
      .then(setRows)
      .finally(() => setLoading(false));
  }, [positions]);

  if (!positions.length) {
    return (
      <div className="text-center py-16 text-zinc-500">
        Add positions to view fundamental scorecards
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="hidden lg:grid grid-cols-[1fr_1fr_1fr_1fr_1fr_1fr] gap-4 px-5 text-xs text-zinc-500 font-medium">
        <span>Ticker</span>
        <span>NI Margin</span>
        <span>EBIT Margin</span>
        <span>EBITDA Margin</span>
        <span>FCF Margin</span>
        <span>Revenue</span>
      </div>

      {loading && rows.every(r => !r.data) ? (
        <div className="flex items-center justify-center py-16">
          <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : (
        rows.map(({ ticker, data, error }) => (
          <div key={ticker} className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
            <div className="flex items-center justify-between mb-4">
              <div>
                <span className="text-zinc-50 font-mono font-bold text-lg">{ticker}</span>
                {data?.source && (
                  <span className="ml-2 text-xs text-zinc-600 bg-zinc-800 px-2 py-0.5 rounded">
                    {data.source}
                  </span>
                )}
              </div>
              <div className="text-right">
                <div className="text-xs text-zinc-500">Revenue</div>
                <div className="font-mono text-sm text-zinc-300">{fmtLarge(data?.revenue)}</div>
              </div>
            </div>

            {error ? (
              <p className="text-red-400 text-sm">{error}</p>
            ) : !data ? (
              <div className="flex items-center gap-2 text-zinc-500 text-sm">
                <span className="w-4 h-4 border-2 border-zinc-600 border-t-zinc-400 rounded-full animate-spin" />
                Loading…
              </div>
            ) : (
              <div className="space-y-3">
                <MarginBar label="NI Margin"     value={data.ni_margin}     thresholds={[10, 0]}  />
                <MarginBar label="EBIT Margin"   value={data.ebit_margin}   thresholds={[15, 0]}  />
                <MarginBar label="EBITDA Margin" value={data.ebitda_margin} thresholds={[20, 0]}  />
                <MarginBar label="FCF Margin"    value={data.fcf_margin}    thresholds={[10, 0]}  />

                {/* Net income */}
                {data.net_income != null && (
                  <div className="pt-2 border-t border-zinc-800 flex gap-6 text-xs">
                    <div>
                      <span className="text-zinc-500">Net Income</span>
                      <span className="ml-2 font-mono text-zinc-300">{fmtLarge(data.net_income)}</span>
                    </div>
                    {data.fetched_at && (
                      <div>
                        <span className="text-zinc-500">Updated</span>
                        <span className="ml-2 text-zinc-600">
                          {new Date(data.fetched_at).toLocaleDateString()}
                        </span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        ))
      )}
    </div>
  );
}
