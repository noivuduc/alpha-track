"use client";
import { useState, useEffect, useRef, useCallback } from "react";
import { marketStatus, MarketStatus } from "@/lib/api";

const POLL_INTERVAL_TRADING = 30_000;
const POLL_INTERVAL_CLOSED  = 60_000;

export function useMarketStatus() {
  const [status, setStatus] = useState<MarketStatus | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout>>();

  const refresh = useCallback(async () => {
    try {
      const s = await marketStatus.get();
      setStatus(s);
    } catch {
      /* network error — keep last known status */
    }
  }, []);

  useEffect(() => {
    refresh();

    const tick = () => {
      const interval = status?.is_trading ? POLL_INTERVAL_TRADING : POLL_INTERVAL_CLOSED;
      timerRef.current = setTimeout(async () => {
        await refresh();
        tick();
      }, interval);
    };
    tick();

    return () => clearTimeout(timerRef.current);
  }, [refresh, status?.is_trading]);

  return status;
}
