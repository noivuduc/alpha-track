import { RebalancingSuggestion, SimulatorPrefillRow } from "./api";

/**
 * Maps a portfolio rebalancing suggestion to one or more explicit simulator
 * transaction rows, ensuring the correct buy/sell direction is always set.
 *
 * Mapping rules:
 *   reduce   → SELL  5% of portfolio value
 *   increase → BUY   5% of portfolio value
 *   add      → BUY   5% of portfolio value
 */
export function suggestionToPrefill(s: RebalancingSuggestion): SimulatorPrefillRow[] {
  if (!s.ticker) return [];

  const ticker = s.ticker.toUpperCase();

  switch (s.action) {
    case "reduce":
      return [{ action: "sell", ticker, mode: "weight_pct", value: "5" }];
    case "increase":
      return [{ action: "buy", ticker, mode: "weight_pct", value: "5" }];
    case "add":
      return [{ action: "buy", ticker, mode: "weight_pct", value: "5" }];
    default:
      return [{ action: "buy", ticker, mode: "weight_pct", value: "5" }];
  }
}
