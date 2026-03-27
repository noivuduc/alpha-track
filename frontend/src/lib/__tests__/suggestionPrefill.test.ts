/**
 * Tests for suggestionToPrefill — the mapping from a RebalancingSuggestion
 * to explicit SimulatorPrefillRow[].
 *
 * Run with: npx vitest  (add vitest to devDependencies to use)
 * Or run as plain Node assertions: npx tsx src/lib/__tests__/suggestionPrefill.test.ts
 */

import { suggestionToPrefill } from "../suggestionPrefill";
import { RebalancingSuggestion, SimulatorPrefillRow } from "../api";

// Minimal test harness (no framework dependency)
let _pass = 0, _fail = 0;
function test(name: string, fn: () => void) {
  try { fn(); _pass++; console.log(`  ✓ ${name}`); }
  catch (e: any) { _fail++; console.error(`  ✗ ${name}\n    ${e.message}`); }
}
function expect(actual: unknown) {
  return {
    toBe(expected: unknown) {
      if (actual !== expected)
        throw new Error(`expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
    },
    toEqual(expected: unknown) {
      const a = JSON.stringify(actual), b = JSON.stringify(expected);
      if (a !== b) throw new Error(`expected\n    ${b}\n  got\n    ${a}`);
    },
    toHaveLength(n: number) {
      const arr = actual as unknown[];
      if (arr.length !== n)
        throw new Error(`expected length ${n}, got ${arr.length}`);
    },
  };
}

// ── Test data helpers ─────────────────────────────────────────────────────────

function suggestion(
  action: RebalancingSuggestion["action"],
  ticker?: string,
): RebalancingSuggestion {
  return {
    action,
    ticker: ticker ?? "AAPL",
    reason: "test reason",
    impact: "test impact",
    priority: "medium",
  };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

console.log("\nsuggestionToPrefill");

// 1. Reduce suggestion → SELL prefill
test("reduce suggestion produces a SELL row", () => {
  const rows = suggestionToPrefill(suggestion("reduce", "MSFT"));
  expect(rows).toHaveLength(1);
  const row = rows[0] as SimulatorPrefillRow;
  expect(row.action).toBe("sell");
  expect(row.ticker).toBe("MSFT");
});

// 2. Add suggestion → BUY prefill
test("add suggestion produces a BUY row", () => {
  const rows = suggestionToPrefill(suggestion("add", "NVDA"));
  expect(rows).toHaveLength(1);
  const row = rows[0] as SimulatorPrefillRow;
  expect(row.action).toBe("buy");
  expect(row.ticker).toBe("NVDA");
});

// 3. Increase suggestion → BUY prefill
test("increase suggestion produces a BUY row", () => {
  const rows = suggestionToPrefill(suggestion("increase", "TSLA"));
  expect(rows).toHaveLength(1);
  const row = rows[0] as SimulatorPrefillRow;
  expect(row.action).toBe("buy");
  expect(row.ticker).toBe("TSLA");
});

// 4. Exit (reduce to zero) — represented by reduce action; simulator user sets value
test("reduce suggestion uses weight_pct mode so user can adjust to full exit", () => {
  const rows = suggestionToPrefill(suggestion("reduce", "MSFT"));
  const row = rows[0] as SimulatorPrefillRow;
  expect(row.mode).toBe("weight_pct");
  expect(row.action).toBe("sell");
});

// 5. Ticker is uppercased
test("ticker is normalized to uppercase", () => {
  // The RebalancingSuggestion ticker field is already a string; suggestionToPrefill uppercases it
  const s: RebalancingSuggestion = {
    action: "reduce",
    ticker: "msft",
    reason: "r", impact: "i", priority: "low",
  };
  const rows = suggestionToPrefill(s);
  expect(rows[0].ticker).toBe("MSFT");
});

// 6. Sector-level suggestion (no ticker) → empty prefill
test("sector-level suggestion with no ticker returns empty array", () => {
  const s: RebalancingSuggestion = {
    action: "reduce",
    ticker: null,
    sector: "Technology",
    reason: "r", impact: "i", priority: "low",
  };
  const rows = suggestionToPrefill(s);
  expect(rows).toHaveLength(0);
});

// 7. Prefill action is never the default "buy" when suggestion action is "reduce"
test("reduce suggestion never produces a BUY row", () => {
  const rows = suggestionToPrefill(suggestion("reduce", "AAPL"));
  expect(rows[0].action).toBe("sell");
  if (rows[0].action === "buy")
    throw new Error("BUG: reduce suggestion produced a buy row");
});

// 8. Rows have a value string that can be parsed as a positive number
test("all produced rows have a positive numeric value", () => {
  for (const action of ["reduce", "add", "increase"] as const) {
    const rows = suggestionToPrefill(suggestion(action, "GOOG"));
    for (const row of rows) {
      const v = Number(row.value);
      if (!(v > 0)) throw new Error(`value '${row.value}' is not positive for action='${action}'`);
    }
  }
});

// ── Summary ───────────────────────────────────────────────────────────────────
console.log(`\n${_pass} passed, ${_fail} failed\n`);
if (_fail > 0) process.exit(1);
