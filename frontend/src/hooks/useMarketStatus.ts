"use client";
import { useState, useEffect, useRef } from "react";
import { computeMarketStatus, MarketStatus } from "@/lib/marketCalendar";

export type { MarketStatus };

/**
 * Returns current market status, recomputed locally at every state transition.
 *
 * No API calls. A single setTimeout fires exactly when the market state
 * changes (e.g. open → after_hours), then reschedules for the next one.
 *
 * State transitions (ET):
 *   04:00 closed → pre_market
 *   09:30 pre_market → open
 *   16:00 open → after_hours
 *   20:00 after_hours → closed
 */
export function useMarketStatus(): MarketStatus | null {
  const [status, setStatus] = useState<MarketStatus | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    function tick() {
      const result = computeMarketStatus();
      setStatus(result);

      // Fire again exactly when the next state transition happens.
      // Add 1s buffer so the clock reads past the boundary cleanly.
      const delay = result.msUntilNextChange + 1_000;
      timerRef.current = setTimeout(tick, delay);
    }

    tick();
    return () => clearTimeout(timerRef.current);
  }, []);

  return status;
}
