"use client";
import { useEffect, useRef, useState } from "react";
import { connectPriceStream, PriceUpdate } from "@/lib/api";

interface UsePriceStreamOptions {
  tickers: string[];
  enabled?: boolean;
  onPrice?: (update: PriceUpdate) => void;
}

export function usePriceStream({ tickers, enabled = true, onPrice }: UsePriceStreamOptions) {
  const [connected, setConnected] = useState(false);
  const [lastUpdate, setLastUpdate] = useState<string | null>(null);
  const disconnectRef = useRef<(() => void) | null>(null);
  const onPriceRef = useRef(onPrice);
  onPriceRef.current = onPrice;

  const tickerKey = [...tickers].sort().join(",");

  useEffect(() => {
    if (!enabled || !tickers.length) {
      disconnectRef.current?.();
      disconnectRef.current = null;
      setConnected(false);
      return;
    }

    let retryTimer: ReturnType<typeof setTimeout>;
    let stopped = false;

    function connect() {
      const disconnect = connectPriceStream(tickers, {
        onPrice: (update) => {
          setLastUpdate(new Date().toLocaleTimeString());
          onPriceRef.current?.(update);
        },
        onMarketStatus: () => {
          setConnected(true);
        },
        onHeartbeat: () => {
          setConnected(true);
        },
        onError: () => {
          setConnected(false);
          if (!stopped) retryTimer = setTimeout(connect, 5_000);
        },
        onClose: () => {
          setConnected(false);
          if (!stopped) retryTimer = setTimeout(connect, 5_000);
        },
      });
      disconnectRef.current = disconnect;
    }

    connect();

    return () => {
      stopped = true;
      clearTimeout(retryTimer);
      disconnectRef.current?.();
      disconnectRef.current = null;
      setConnected(false);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tickerKey, enabled]);

  return { connected, lastUpdate };
}
