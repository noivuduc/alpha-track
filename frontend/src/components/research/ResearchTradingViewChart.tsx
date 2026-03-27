"use client";
import { useEffect, useRef, useState, useId } from "react";
import { mapToTvSymbol, buildTvConfig } from "@/lib/research/tradingview";

// Singleton script loader — inject tv.js only once per page
let _scriptPromise: Promise<void> | null = null;

function loadTvScript(): Promise<void> {
  if (_scriptPromise) return _scriptPromise;
  _scriptPromise = new Promise((resolve, reject) => {
    if (document.querySelector('script[src*="tv.js"]')) {
      resolve();
      return;
    }
    const script = document.createElement("script");
    script.src = "https://s3.tradingview.com/tv.js";
    script.async = true;
    script.onload  = () => resolve();
    script.onerror = () => {
      _scriptPromise = null;  // allow retry
      reject(new Error("Failed to load TradingView script"));
    };
    document.head.appendChild(script);
  });
  return _scriptPromise;
}

interface Props {
  ticker: string;
  exchange?: string | null;
}

type Status = "loading" | "ready" | "error";

export default function ResearchTradingViewChart({ ticker, exchange }: Props) {
  const uid         = useId();
  const containerId = `tv-chart-${uid.replace(/:/g, "")}`;
  const containerRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<Status>("loading");
  const [errMsg, setErrMsg] = useState("");

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    setErrMsg("");

    // Clear any previous widget
    if (containerRef.current) containerRef.current.innerHTML = "";

    const symbol = mapToTvSymbol(ticker, exchange);

    loadTvScript()
      .then(() => {
        if (cancelled) return;
        const TradingView = (window as any).TradingView;
        if (!TradingView?.widget) {
          throw new Error("TradingView library unavailable");
        }
        new TradingView.widget(buildTvConfig(symbol, containerId));
        setStatus("ready");
      })
      .catch((e: Error) => {
        if (cancelled) return;
        setStatus("error");
        setErrMsg(e.message || "Chart unavailable");
      });

    return () => {
      cancelled = true;
      // Clean up iframe/widget content on unmount or symbol change
      if (containerRef.current) containerRef.current.innerHTML = "";
    };
  // Re-run when ticker or exchange changes
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticker, exchange]);

  return (
    <div className="flex flex-col gap-2">
      {/* Loading overlay */}
      {status === "loading" && (
        <div className="flex items-center justify-center h-[500px] sm:h-[640px] bg-zinc-900/60 rounded-xl border border-zinc-800">
          <div className="flex flex-col items-center gap-3">
            <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
            <span className="text-xs text-zinc-500">Loading chart…</span>
          </div>
        </div>
      )}

      {/* Error state */}
      {status === "error" && (
        <div className="flex flex-col items-center justify-center h-[500px] sm:h-[640px] bg-zinc-900/60 rounded-xl border border-zinc-800 gap-3">
          <div className="text-sm text-zinc-400">{errMsg || "Chart unavailable"}</div>
          <div className="text-xs text-zinc-600">TradingView could not be loaded. Try refreshing the page.</div>
        </div>
      )}

      {/* Chart container — always rendered so TradingView can mount into it */}
      <div
        id={containerId}
        ref={containerRef}
        className={`w-full rounded-xl overflow-hidden border border-zinc-800 ${status === "error" ? "hidden" : ""}`}
        style={{ height: "640px" }}
      />

      {/* Disclaimer */}
      <p className="text-[11px] text-zinc-600 text-right leading-relaxed">
        Chart provided by{" "}
        <a
          href="https://www.tradingview.com"
          target="_blank"
          rel="noopener noreferrer"
          className="text-zinc-500 hover:text-zinc-400 underline underline-offset-2"
        >
          TradingView
        </a>
        {" "}· Prices shown elsewhere in AlphaTrack use a different data source.
      </p>
    </div>
  );
}
