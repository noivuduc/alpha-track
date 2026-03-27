/**
 * Client-side market calendar — mirrors backend/app/services/market_calendar.py
 *
 * All state transitions are computed locally from the browser clock.
 * No API calls needed. A single setTimeout fires at the next transition.
 *
 * US market schedule (America/New_York):
 *   04:00 → Pre-Market   (is_trading: true)
 *   09:30 → Regular Open  (is_trading: true)
 *   16:00 → After Hours   (is_trading: true)
 *   20:00 → Closed        (is_trading: false)
 */

export type MarketState = "pre_market" | "open" | "after_hours" | "closed";

export interface MarketStatus {
  state:       MarketState;
  label:       string;
  /** ISO string of next state transition */
  next_change: string;
  countdown:   string;
  /** True when prices are actively updating (pre-market, regular, after-hours) */
  is_trading:  boolean;
  timezone:    string;
}

// ── NYSE holidays (observed dates) ───────────────────────────────────────────
// Source: https://www.nyse.com/markets/hours-calendars — keep updated annually.

const HOLIDAYS = new Set([
  // 2026
  "2026-01-01", // New Year's Day
  "2026-01-19", // MLK Jr. Day
  "2026-02-16", // Presidents' Day
  "2026-04-03", // Good Friday
  "2026-05-25", // Memorial Day
  "2026-07-03", // Independence Day (observed)
  "2026-09-07", // Labor Day
  "2026-11-26", // Thanksgiving
  "2026-12-25", // Christmas
  // 2027
  "2027-01-01",
  "2027-01-18",
  "2027-02-15",
  "2027-03-26",
  "2027-05-31",
  "2027-07-05",
  "2027-09-06",
  "2027-11-25",
  "2027-12-24",
]);

const TZ       = "America/New_York";
const PRE_OPEN = { h:  4, m:  0 };
const REG_OPEN = { h:  9, m: 30 };
const REG_CLOSE= { h: 16, m:  0 };
const AH_CLOSE = { h: 20, m:  0 };

// ── Helpers ───────────────────────────────────────────────────────────────────

function isoDate(d: Date): string {
  // YYYY-MM-DD in ET
  return d.toLocaleDateString("en-CA", { timeZone: TZ });
}

function etHM(d: Date): { h: number; m: number } {
  const parts = d
    .toLocaleTimeString("en-US", { timeZone: TZ, hour12: false, hour: "2-digit", minute: "2-digit" })
    .split(":");
  return { h: parseInt(parts[0], 10), m: parseInt(parts[1], 10) };
}

function toMinutes({ h, m }: { h: number; m: number }): number {
  return h * 60 + m;
}

function isTradingDay(d: Date): boolean {
  const dow = new Date(d.toLocaleDateString("en-CA", { timeZone: TZ }) + "T12:00:00").getDay();
  if (dow === 0 || dow === 6) return false;
  return !HOLIDAYS.has(isoDate(d));
}

/** Return the Date for a specific HH:MM ET on `d` (a Date in any tz). */
function etTimeOnDay(d: Date, hm: { h: number; m: number }): Date {
  const dateStr = isoDate(d);
  // Build a string and parse it as ET
  const candidate = new Date(`${dateStr}T${String(hm.h).padStart(2,"0")}:${String(hm.m).padStart(2,"0")}:00`);
  // The above is local time — we need to correct for ET offset.
  // Simpler: use Intl to get the epoch for that clock time in ET.
  const formatter = new Intl.DateTimeFormat("en-US", {
    timeZone: TZ,
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
    hour12: false,
  });
  // Build target as UTC by adding/subtracting the ET offset
  const etNow = new Date(d.toLocaleString("en-US", { timeZone: TZ }));
  const diff   = d.getTime() - etNow.getTime(); // UTC - ET_local = offset in ms
  return new Date(
    new Date(`${dateStr}T${String(hm.h).padStart(2,"0")}:${String(hm.m).padStart(2,"0")}:00`).getTime() + diff
  );
}

function nextTradingDayOpen(from: Date): Date {
  let d = new Date(from.getTime() + 86_400_000);
  while (!isTradingDay(d)) d = new Date(d.getTime() + 86_400_000);
  return etTimeOnDay(d, PRE_OPEN);
}

function countdown(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s < 60)  return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60)  return `${m}m`;
  const h = Math.floor(m / 60);
  const rm = m % 60;
  if (h < 24)  return rm ? `${h}h ${rm}m` : `${h}h`;
  const days = Math.floor(h / 24);
  const rh   = h % 24;
  return rh ? `${days}d ${rh}h` : `${days}d`;
}

// ── Core computation ──────────────────────────────────────────────────────────

export function computeMarketStatus(now = new Date()): MarketStatus & { msUntilNextChange: number } {
  const trading = isTradingDay(now);
  const { h, m } = etHM(now);
  const cur = toMinutes({ h, m });

  const pre   = toMinutes(PRE_OPEN);   //  240
  const open  = toMinutes(REG_OPEN);   //  570
  const close = toMinutes(REG_CLOSE);  //  960
  const ah    = toMinutes(AH_CLOSE);   // 1200

  let state:      MarketState;
  let label:      string;
  let isTrading:  boolean;
  let nextChange: Date;

  if (!trading || cur < pre) {
    state      = "closed";
    label      = "Market Closed";
    isTrading  = false;
    nextChange = trading
      ? etTimeOnDay(now, PRE_OPEN)           // later today
      : nextTradingDayOpen(now);             // next trading day
  } else if (cur < open) {
    state      = "pre_market";
    label      = "Pre-Market";
    isTrading  = true;
    nextChange = etTimeOnDay(now, REG_OPEN);
  } else if (cur < close) {
    state      = "open";
    label      = "Market Open";
    isTrading  = true;
    nextChange = etTimeOnDay(now, REG_CLOSE);
  } else if (cur < ah) {
    state      = "after_hours";
    label      = "After Hours";
    isTrading  = true;
    nextChange = etTimeOnDay(now, AH_CLOSE);
  } else {
    state      = "closed";
    label      = "Market Closed";
    isTrading  = false;
    nextChange = nextTradingDayOpen(now);
  }

  const msUntilNextChange = Math.max(0, nextChange.getTime() - now.getTime());
  const action = (state === "closed" || state === "pre_market") ? "Opens in" : "Closes in";

  return {
    state,
    label,
    next_change:       nextChange.toISOString(),
    countdown:         `${action} ${countdown(msUntilNextChange)}`,
    is_trading:        isTrading,
    timezone:          TZ,
    msUntilNextChange,
  };
}
