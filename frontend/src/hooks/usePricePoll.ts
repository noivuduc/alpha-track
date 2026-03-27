"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import { pricesApi, PriceUpdate } from "@/lib/api";

const REFRESH_INTERVAL_MS = 5 * 60 * 1000; // 5 minutes

interface UsePricePollOptions {
  tickers: string[];
  enabled?: boolean;
}

interface UsePricePollResult {
  prices: Record<string, PriceUpdate>;
  lastFetchedAt: Date | null;
  /** Seconds until next refresh, counts down to 0 */
  nextRefreshIn: number;
  refresh: () => void;
}

export function usePricePoll({
  tickers,
  enabled = true,
}: UsePricePollOptions): UsePricePollResult {
  const [prices, setPrices]           = useState<Record<string, PriceUpdate>>({});
  const [lastFetchedAt, setLastFetchedAt] = useState<Date | null>(null);
  const [nextRefreshIn, setNextRefreshIn] = useState(0);

  const tickerKey    = [...tickers].sort().join(",");
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const countdownRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const fetchedAt    = useRef<Date | null>(null);

  const startCountdown = useCallback(() => {
    clearInterval(countdownRef.current);
    const end = Date.now() + REFRESH_INTERVAL_MS;
    setNextRefreshIn(Math.round(REFRESH_INTERVAL_MS / 1000));
    countdownRef.current = setInterval(() => {
      const remaining = Math.max(0, Math.round((end - Date.now()) / 1000));
      setNextRefreshIn(remaining);
    }, 1_000);
  }, []);

  const fetchPrices = useCallback(async (tickerList: string[]) => {
    if (!tickerList.length) return;
    try {
      const raw = await pricesApi.bulk(tickerList);
      // Normalize: ensure each entry has a `ticker` field (backend uses it as key)
      const normalized: Record<string, PriceUpdate> = {};
      for (const [ticker, data] of Object.entries(raw)) {
        normalized[ticker] = { ...data, ticker } as PriceUpdate;
      }
      setPrices(normalized);
      const now = new Date();
      fetchedAt.current = now;
      setLastFetchedAt(now);
    } catch (err) {
      console.error("[PricePoll] fetch failed:", err);
    }
  }, []);

  const scheduleNext = useCallback(
    (tickerList: string[]) => {
      clearTimeout(refreshTimer.current);
      startCountdown();
      refreshTimer.current = setTimeout(() => {
        fetchPrices(tickerList).then(() => scheduleNext(tickerList));
      }, REFRESH_INTERVAL_MS);
    },
    [fetchPrices, startCountdown],
  );

  // Exposed manual refresh — resets the timer
  const refresh = useCallback(() => {
    clearTimeout(refreshTimer.current);
    clearInterval(countdownRef.current);
    const list = tickerKey.split(",").filter(Boolean);
    fetchPrices(list).then(() => scheduleNext(list));
  }, [tickerKey, fetchPrices, scheduleNext]);

  useEffect(() => {
    clearTimeout(refreshTimer.current);
    clearInterval(countdownRef.current);

    if (!enabled || !tickers.length) {
      setPrices({});
      setLastFetchedAt(null);
      setNextRefreshIn(0);
      return;
    }

    const list = tickerKey.split(",").filter(Boolean);
    fetchPrices(list).then(() => scheduleNext(list));

    return () => {
      clearTimeout(refreshTimer.current);
      clearInterval(countdownRef.current);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tickerKey, enabled]);

  return { prices, lastFetchedAt, nextRefreshIn, refresh };
}
