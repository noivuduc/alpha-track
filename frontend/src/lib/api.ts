/**
 * AlphaTrack API Client — typed wrapper with auto token-refresh and error handling.
 * All API calls go through apiFetch() which handles auth headers and 401 retries.
 */

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

let _accessToken: string | null = null;
export const setAccessToken = (t: string | null) => { _accessToken = t; };
export const getAccessToken = () => _accessToken;

let _onSessionExpired: (() => void) | null = null;
export const onSessionExpired = (cb: (() => void) | null) => { _onSessionExpired = cb; };

// Shared in-flight refresh promise — prevents concurrent token rotations from
// racing each other (e.g. React Strict Mode double-invoking effects).
let _refreshPromise: Promise<boolean> | null = null;

export class ApiError extends Error {
  constructor(public status: number, message: string, public detail?: unknown) {
    super(message);
  }
}

async function apiFetch<T>(
  path: string,
  opts: RequestInit & { skipRefresh?: boolean } = {}
): Promise<T> {
  const { skipRefresh, ...init } = opts;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((init.headers as Record<string, string>) || {}),
  };
  if (_accessToken) headers["Authorization"] = `Bearer ${_accessToken}`;

  // credentials: "include" sends the httpOnly refresh_token cookie automatically
  const res = await fetch(`${BASE}${path}`, { ...init, headers, credentials: "include" });

  if (res.status === 401 && !skipRefresh) {
    const ok = await tryRefresh();
    if (ok) {
      headers["Authorization"] = `Bearer ${_accessToken}`;
      const retry = await fetch(`${BASE}${path}`, { ...init, headers, credentials: "include" });
      if (retry.ok) return retry.status === 204 ? (undefined as T) : retry.json();
    }
    _onSessionExpired?.();
    throw new ApiError(401, "Session expired. Please log in again.");
  }

  if (!res.ok) {
    const b = await res.json().catch(() => ({}));
    throw new ApiError(res.status, b.detail || res.statusText, b);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

async function tryRefresh(): Promise<boolean> {
  // If a refresh is already in flight, reuse it — never send two rotation requests.
  if (_refreshPromise) return _refreshPromise;

  _refreshPromise = (async (): Promise<boolean> => {
    try {
      // No body needed — the browser sends the httpOnly refresh_token cookie
      // automatically via credentials: "include" (set in apiFetch).
      const d = await apiFetch<{ access_token: string }>(
        "/auth/refresh",
        { method: "POST", skipRefresh: true }
      );
      setAccessToken(d.access_token);
      return true;
    } catch (e) {
      setAccessToken(null);
      return false;
    } finally {
      _refreshPromise = null;
    }
  })();

  return _refreshPromise;
}

// ─── Types ────────────────────────────────────────────────────────────────────
export interface User          { id: string; email: string; full_name: string|null; tier: "free"|"pro"|"fund"; is_admin: boolean; is_verified: boolean; created_at: string; }
export interface TokenResp     { access_token: string; refresh_token?: string | null; token_type: string; expires_in: number; }
export interface Portfolio     { id: string; name: string; description: string|null; currency: string; is_default: boolean; created_at: string; }
export interface Position      { id: string; ticker: string; shares: number; cost_basis: number; notes: string|null; opened_at: string; current_price?: number; current_value?: number; gain_loss?: number; gain_loss_pct?: number; weight_pct?: number; contribution_to_portfolio_pct?: number; }
export interface PortfolioMetrics { total_value: number; total_cost: number; total_gain: number; total_gain_pct: number; day_gain: number; day_gain_pct: number; cash_value: number; cash_pct: number; beta?: number; sharpe?: number; max_drawdown?: number; volatility?: number; }
export interface PriceData     { ticker: string; price: number; change: number; change_pct: number; volume?: number; fetched_at: string; source: string; }
export interface Fundamentals  { ticker: string; ni_margin?: number; ebit_margin?: number; ebitda_margin?: number; fcf_margin?: number; revenue?: number; net_income?: number; fetched_at?: string; source: string; }
export interface WatchlistItem { id: string; ticker: string; quant_rating?: number; sector?: string; announce_date?: string; notes?: string; alert_price?: number; created_at: string; current_price?: number; }
export interface Transaction   { id: string; ticker: string; side: "buy"|"sell"; shares: number; price: number; fees: number; traded_at: string; notes?: string; }
export interface HistoryBar    { ts: string; open: number; high: number; low: number; close: number; volume: number; }
export interface AdminStats    { total_users: number; users_by_tier: Record<string,number>; api_calls_today: number; cache_hit_rate: number; paid_calls_today: number; estimated_cost_usd: number; }

// ─── Analytics ────────────────────────────────────────────────────────────────
export interface RiskMetrics {
  sharpe?:                number;
  sortino?:               number;
  beta?:                  number;
  alpha_pct?:             number;
  max_drawdown_pct?:      number;
  volatility_pct?:        number;
  calmar?:                number;
  win_rate_pct?:          number;
  annualized_return_pct?: number;
  information_ratio?:     number;
  var_95_pct?:            number;
  trading_days?:          number;
  // Downside risk
  downside_deviation?: number;
  ulcer_index?:        number;
  tail_loss_95?:       number;
}
export interface PerformancePoint { date: string; portfolio?: number; spy?: number; qqq?: number; }
export interface DrawdownPoint    { date: string; drawdown: number; }
export interface MonthlyReturn    { year: number; month: number; label: string; value: number; }
export interface PerformanceSummary {
  "1d_pct":  number | null;
  "1w_pct":  number | null;
  "1m_pct":  number | null;
  ytd_pct:   number | null;
  "1y_pct":  number | null;
}
export interface BenchmarkComparison {
  portfolio_return_pct: number | null;
  spy_return_pct:       number | null;
  qqq_return_pct:       number | null;
  alpha_vs_spy_pct:     number | null;
  alpha_vs_qqq_pct:     number | null;
}
export interface DerivedMetrics {
  performance_summary:     PerformanceSummary;
  benchmark_comparison:    BenchmarkComparison;
  best_day_pct:            number | null;
  worst_day_pct:           number | null;
  avg_daily_return_pct:    number | null;
  median_daily_return_pct: number | null;
  current_drawdown_pct:    number | null;
  recovery_days_since_peak: number;
}
export interface PositionPerformer {
  ticker:       string;
  return_pct:   number;
  contribution: number;
}
export interface TickerReturn {
  ticker:        string;
  return_1w_pct: number | null;
  return_1m_pct: number | null;
  return_3m_pct: number | null;
  return_1y_pct: number | null;
}
export interface PositionSummary {
  best_performers:  PositionPerformer[];
  worst_performers: PositionPerformer[];
  ticker_returns:   TickerReturn[];
}
export interface PortfolioNewsItem {
  ticker:    string;
  title:     string;
  headline?: string;  // legacy alias — use title
  source:    string;
  url:       string;
  date:      string;
}
// ── New comprehensive analytics types ────────────────────────────
export interface PortfolioValuePoint {
  date:  string;
  value: number;
}
export interface RollingReturns {
  return_1w:   number | null;
  return_1m:   number | null;
  return_3m:   number | null;
  return_ytd:  number | null;
  return_1y:   number | null;
}
export interface ContributionEntry {
  ticker:           string;
  contribution_pct: number;
  pnl_contribution: number;
}
export interface PositionAnalyticsEntry {
  ticker:       string;
  return_pct:   number;
  pnl:          number;
  weight:       number;
  volatility:   number | null;
  daily_return: number | null;
}
export interface PerformanceMetrics {
  // Core performance
  cumulative_return:  number | null;
  annualized_return:  number | null;
  volatility:         number | null;
  sharpe_ratio:       number | null;
  max_drawdown:       number | null;
  beta:               number | null;
  alpha:              number | null;
  // Correlation
  correlation_spy:    number | null;
  correlation_qqq:    number | null;
  // Concentration
  largest_position_weight?: number | null;
  top3_weight?:             number | null;
  top5_weight?:             number | null;
  herfindahl_index?:        number | null;
  // Market capture
  upside_capture_ratio?:   number | null;
  downside_capture_ratio?: number | null;
  // Turnover
  estimated_turnover_pct?: number | null;
  // Distribution
  skewness?: number | null;
  kurtosis?: number | null;
}

export interface RollingMetricPoint {
  date:               string;
  rolling_sharpe:     number | null;
  rolling_volatility: number | null;
  rolling_beta:       number | null;
  rolling_sortino:    number | null;
}

export interface RollingCorrelationPoint {
  date:  string;
  value: number | null;
}

export interface VolatilityRegimePoint {
  date:       string;
  volatility: number;
  regime:     "low" | "normal" | "high";
}

export interface GrowthPoint {
  date:      string;
  portfolio: number;
  spy?:      number;
  qqq?:      number;
}

export interface DailyHeatmapPoint {
  date:       string;
  year:       number;
  month:      number;
  day:        number;
  weekday:    number;  // 0 = Monday … 6 = Sunday
  return_pct: number;
}

export interface WeeklyReturn {
  week:        string;  // "2026-W10"
  year:        number;
  week_number: number;
  return_pct:  number;
}

export interface PeriodExtremes {
  best_day_pct?:    number | null;
  worst_day_pct?:   number | null;
  best_week_pct?:   number | null;
  worst_week_pct?:  number | null;
  best_month_pct?:  number | null;
  worst_month_pct?: number | null;
}

export interface PortfolioAnalytics {
  portfolio_id:    string;
  period:          string;
  computed_at:     string;
  total_value:     number;
  total_cost:      number;
  total_gain:      number;
  total_gain_pct:  number;
  day_gain:        number;
  day_gain_pct:    number;
  risk_metrics:    RiskMetrics;
  performance:     PerformancePoint[];
  drawdown:        DrawdownPoint[];
  monthly_returns: MonthlyReturn[];
  derived_metrics?:       DerivedMetrics          | null;
  position_summary?:      PositionSummary         | null;
  portfolio_news?:        PortfolioNewsItem[]      | null;
  // ── Comprehensive analytics fields ────────────────────────────
  portfolio_value_series?: PortfolioValuePoint[]    | null;
  rolling_returns?:        RollingReturns           | null;
  contribution?:           ContributionEntry[]      | null;
  position_analytics?:     PositionAnalyticsEntry[] | null;
  performance_metrics?:    PerformanceMetrics       | null;
  // ── Advanced institutional analytics ───────────────────────
  rolling_metrics?:         Record<string, RollingMetricPoint[]> | null;  // "63d"|"126d"|"252d"
  rolling_correlation_spy?: RollingCorrelationPoint[]            | null;
  volatility_regime?:       VolatilityRegimePoint[]              | null;
  rolling_drawdown_6m?:     DrawdownPoint[]                      | null;
  growth_of_100?:           GrowthPoint[]                        | null;
  daily_heatmap?:           DailyHeatmapPoint[]                  | null;
  weekly_returns?:          WeeklyReturn[]                        | null;
  period_extremes?:         PeriodExtremes                        | null;
}

// ─── Portfolio Analysis ───────────────────────────────────────────────────────
export interface HealthBreakdown {
  diversification:      number;
  concentration:        number;
  risk_adjusted_return: number;
  drawdown:             number;
  correlation:          number;
}
export interface HealthScore {
  score:      number;
  grade:      string;
  breakdown:  HealthBreakdown;
  insights:   string[];
  top_issues?: string[];
}
export interface RebalancingSuggestion {
  action:        "reduce" | "increase" | "add";
  ticker?:       string | null;
  sector?:       string | null;
  reason:        string;
  impact:        string;
  priority:      "high" | "medium" | "low";
  metrics_delta?: Record<string, string> | null;
}
export interface CorrelationCluster {
  cluster_id:      number;
  assets:          string[];
  avg_correlation: number;
  label:           string;
  insight?:        string | null;
}
export interface PortfolioAnalysisResponse {
  portfolio_id: string;
  computed_at:  string;
  health:       HealthScore;
  suggestions:  RebalancingSuggestion[];
  clusters:     CorrelationCluster[];
}

// ─── Simulator prefill ────────────────────────────────────────────────────────
/** A single pre-populated row for the Scenario Builder, derived from a suggestion. */
export interface SimulatorPrefillRow {
  action: "buy" | "sell";
  ticker: string;
  mode:   "shares" | "amount" | "weight_pct" | "target_weight";
  value:  string;
}

// ─── Simulation ───────────────────────────────────────────────────────────────
export interface SimulateSnapshot {
  sharpe:                number;
  sortino:               number;
  beta:                  number;
  alpha_pct:             number;
  max_drawdown_pct:      number;
  volatility_pct:        number;
  annualized_return_pct: number;
  var_95_pct:            number;
}

export interface ScenarioTransaction {
  action: "buy" | "sell";
  ticker: string;
  mode:   "shares" | "amount" | "weight_pct" | "target_weight";
  value:  number;
}

export interface HoldingSnapshot {
  ticker:       string;
  shares:       number;
  weight_pct:   number;
  market_value: number;
  change:       "new" | "increased" | "reduced" | "exited" | null;
}

export interface ScenarioSummary {
  transaction_count: number;  // rows the user entered
  buy_count:         number;
  sell_count:        number;
  tickers_added:   string[];  // new positions (didn't exist before)
  tickers_removed: string[];  // fully exited positions
  tickers_changed: string[];  // reweighted (can be > transaction_count)
  net_cash_delta:  number;
}

export interface ScenarioResponse {
  before:           SimulateSnapshot;
  after:            SimulateSnapshot;
  delta:            SimulateSnapshot;
  exposure:         { sector_before: Record<string,number>; sector_after: Record<string,number> };
  insights:         string[];
  holdings_before:  HoldingSnapshot[];
  holdings_after:   HoldingSnapshot[];
  scenario_summary: ScenarioSummary;
  scenario_id:      string;
}

export interface ApplyScenarioResult {
  applied_transactions: number;
  positions_created:    number;
  positions_updated:    number;
  positions_closed:     number;
  message:              string;
}

// Legacy alias
export type SimulateResponse = ScenarioResponse;

// ─── Auth ────────────────────────────────────────────────────────────────────
export const auth = {
  register: (email: string, password: string, full_name?: string) =>
    apiFetch<User>("/auth/register", { method: "POST", body: JSON.stringify({ email, password, full_name }) }),

  login: async (email: string, password: string) => {
    const d = await apiFetch<TokenResp>("/auth/login", {
      method: "POST", body: JSON.stringify({ email, password }), skipRefresh: true,
    });
    setAccessToken(d.access_token);
    // Refresh token is now in an httpOnly cookie — no localStorage needed
    return d;
  },

  logout: async () => {
    await apiFetch("/auth/logout", { method: "POST" }).catch(() => {});
    setAccessToken(null);
    // Cookie is cleared server-side by the logout endpoint
  },

  me:             () => apiFetch<User>("/auth/me"),

  // Restores session on page load: refresh first (uses httpOnly cookie), then fetch user.
  // Avoids the guaranteed-to-fail initial /auth/me call when _accessToken is null.
  initSession: async (): Promise<User | null> => {
    if (!_accessToken) {
      const ok = await tryRefresh();
      if (!ok) return null;
    }
    return apiFetch<User>("/auth/me").catch(() => null);
  },
  generateApiKey: () => apiFetch<{ api_key: string; note: string }>("/auth/api-key", { method: "POST" }),
  revokeApiKey:   () => apiFetch("/auth/api-key", { method: "DELETE" }),
};

// ─── Generic polling helper for 202 responses ────────────────────────────────

const _POLL_MAX_GENERIC = 60;   // up to ~60s total

// Backoff schedule: fast initial retries, then slow down
function _pollDelay(attempt: number): number {
  if (attempt === 0) return 400;   // first retry: 400ms
  if (attempt  < 5) return 800;   // next 4: 800ms each
  return 2000;                     // then 2s
}

async function pollUntilReady<T>(
  path: string,
  opts: RequestInit = {},
  onPreparing?: () => void,
): Promise<T> {
  for (let i = 0; i < _POLL_MAX_GENERIC; i++) {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...((opts.headers as Record<string, string>) || {}),
    };
    const token = getAccessToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const res = await fetch(`${BASE}${path}`, { ...opts, headers, credentials: "include" });

    if (res.status === 200) {
      const body = await res.json();
      if (body.status === "preparing") {
        onPreparing?.();
        await new Promise(r => setTimeout(r, _pollDelay(i)));
        continue;
      }
      return body as T;
    }

    if (res.status === 202) {
      onPreparing?.();
      await new Promise(r => setTimeout(r, _pollDelay(i)));
      continue;
    }

    if (res.status === 401) {
      const ok = await tryRefresh();
      if (!ok) { _onSessionExpired?.(); throw new ApiError(401, "Session expired"); }
      continue;
    }

    const b = await res.json().catch(() => ({}));
    throw new ApiError(res.status, b.detail || res.statusText, b);
  }

  throw new ApiError(408, "Data loading timed out. Please try again.");
}

// ─── Portfolios ───────────────────────────────────────────────────────────────
export const portfolios = {
  list:    ()                                  => apiFetch<Portfolio[]>("/portfolio/"),
  create:  (b: Partial<Portfolio>)             => apiFetch<Portfolio>("/portfolio/", { method: "POST", body: JSON.stringify(b) }),
  get:     (id: string)                        => apiFetch<Portfolio>(`/portfolio/${id}`),
  update:  (id: string, b: Partial<Portfolio>) => apiFetch<Portfolio>(`/portfolio/${id}`, { method: "PATCH", body: JSON.stringify(b) }),
  delete:  (id: string)                        => apiFetch(`/portfolio/${id}`, { method: "DELETE" }),
  metrics:   (id: string)                               => apiFetch<PortfolioMetrics>(`/portfolio/${id}/metrics`),
  analytics: (id: string, period = "1y", force = false, onPreparing?: () => void) =>
               pollUntilReady<PortfolioAnalytics>(`/portfolio/${id}/analytics?period=${period}&force=${force}`, {}, onPreparing),
  simulate:  (id: string, transactions: ScenarioTransaction[]) =>
               apiFetch<ScenarioResponse>(`/portfolio/${id}/simulate`, {
                 method: "POST",
                 body: JSON.stringify({ transactions }),
               }),
  applyScenario: (id: string, scenarioId: string) =>
               apiFetch<ApplyScenarioResult>(`/portfolio/${id}/simulate/apply`, {
                 method: "POST",
                 body: JSON.stringify({ scenario_id: scenarioId }),
               }),
  analysis:  (id: string, force = false, onPreparing?: () => void) =>
               pollUntilReady<PortfolioAnalysisResponse>(`/portfolio/${id}/analysis?force=${force}`, {}, onPreparing),
};

// ─── Positions ────────────────────────────────────────────────────────────────
export const positions = {
  list:   (pid: string) => apiFetch<Position[]>(`/portfolio/${pid}/positions`),
  add:    (pid: string, b: { ticker: string; shares: number; cost_basis: number; notes?: string }) =>
            apiFetch<Position>(`/portfolio/${pid}/positions`, { method: "POST", body: JSON.stringify(b) }),
  update: (pid: string, id: string, b: Partial<Position>) =>
            apiFetch<Position>(`/portfolio/${pid}/positions/${id}`, { method: "PATCH", body: JSON.stringify(b) }),
  delete: (pid: string, id: string) => apiFetch(`/portfolio/${pid}/positions/${id}`, { method: "DELETE" }),
};

// ─── Transactions ─────────────────────────────────────────────────────────────
export const transactions = {
  list:   (pid: string) => apiFetch<Transaction[]>(`/portfolio/${pid}/transactions`),
  add:    (pid: string, b: Omit<Transaction,"id">) =>
            apiFetch<Transaction>(`/portfolio/${pid}/transactions`, { method: "POST", body: JSON.stringify(b) }),
  update: (pid: string, txnId: string, b: Partial<Pick<Transaction,"shares"|"price"|"fees"|"traded_at"|"notes">>) =>
            apiFetch<Transaction>(`/portfolio/${pid}/transactions/${txnId}`, { method: "PATCH", body: JSON.stringify(b) }),
  remove: (pid: string, txnId: string) =>
            apiFetch(`/portfolio/${pid}/transactions/${txnId}`, { method: "DELETE" }),
};

// ─── Watchlist ────────────────────────────────────────────────────────────────
export const watchlistApi = {
  list:   ()                          => apiFetch<WatchlistItem[]>("/portfolio/watchlist/"),
  add:    (b: Partial<WatchlistItem>) => apiFetch<WatchlistItem>("/portfolio/watchlist/", { method: "POST", body: JSON.stringify(b) }),
  remove: (id: string)                => apiFetch(`/portfolio/watchlist/${id}`, { method: "DELETE" }),
};

// ─── Market data ──────────────────────────────────────────────────────────────
export const market = {
  price:        (ticker: string)                => pollUntilReady<PriceData>(`/market/price/${ticker}`),
  prices:       (tickers: string[])             => apiFetch<Record<string,PriceData>>(`/market/prices?tickers=${tickers.join(",")}`),
  fundamentals: (ticker: string, force = false) => pollUntilReady<Fundamentals>(`/market/fundamentals/${ticker}?force_refresh=${force}`),
  history:      (ticker: string, period = "1y", interval = "1d") =>
                  pollUntilReady<{ ticker: string; data: HistoryBar[] }>(`/market/history/${ticker}?period=${period}&interval=${interval}`),
  /** Fire-and-forget: triggers cache seeding without polling. */
  prefetchHistory: (ticker: string, period = "1y", interval = "1d") => {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    const token = getAccessToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
    fetch(`${BASE}/market/history/${ticker}?period=${period}&interval=${interval}`, {
      headers, credentials: "include",
    }).catch(() => {});
  },
  profile:      (ticker: string) => pollUntilReady<Record<string,unknown>>(`/market/profile/${ticker}`),
  /** Batch profile fetch — single request for N tickers. */
  profiles:     (tickers: string[]) =>
                  apiFetch<{ data: Record<string, Record<string,unknown>>; missing: string[] }>(
                    `/market/profiles?tickers=${encodeURIComponent(tickers.map(t => t.toUpperCase()).join(","))}`,
                  ),
  insider:      (ticker: string) => apiFetch<{ trades: unknown[] }>(`/market/insider/${ticker}`),
  earnings:     (ticker: string) => pollUntilReady<Record<string,unknown>>(`/market/earnings/${ticker}`),
  invalidate:   (ticker: string) => apiFetch(`/market/cache/invalidate/${ticker}`, { method: "POST" }),
};

// ─── Research ─────────────────────────────────────────────────────────────────
export interface CompanyFacts {
  ticker: string; name: string; cik: string; industry: string; sector: string;
  category: string; exchange: string; is_active: boolean; location: string;
  sic_code: string; sic_industry: string; sic_sector: string;
}
export interface PriceSnapshot { ticker: string; price: number; day_change: number; day_change_percent: number; time: string; }
export interface FinancialMetrics {
  // Valuation
  enterprise_value?: number; price_to_earnings_ratio?: number; price_to_book_ratio?: number;
  price_to_sales_ratio?: number; enterprise_value_to_ebitda_ratio?: number;
  enterprise_value_to_revenue_ratio?: number; free_cash_flow_yield?: number; peg_ratio?: number;
  // Profitability
  gross_margin?: number; operating_margin?: number; net_margin?: number;
  return_on_equity?: number; return_on_assets?: number; return_on_invested_capital?: number;
  // Liquidity
  current_ratio?: number; quick_ratio?: number; cash_ratio?: number; operating_cash_flow_ratio?: number;
  // Leverage
  debt_to_equity?: number; debt_to_assets?: number; interest_coverage?: number;
  // Efficiency
  asset_turnover?: number; inventory_turnover?: number; receivables_turnover?: number;
  days_sales_outstanding?: number; operating_cycle?: number; working_capital_turnover?: number;
  // Growth
  revenue_growth?: number; earnings_growth?: number; earnings_per_share_growth?: number;
  free_cash_flow_growth?: number; ebitda_growth?: number;
  book_value_growth?: number; operating_income_growth?: number;
  // Per share
  earnings_per_share?: number; book_value_per_share?: number; free_cash_flow_per_share?: number;
  payout_ratio?: number;
}

/** One row from the financial-metrics historical API */
export interface MetricsHistory {
  ticker: string; report_period: string; fiscal_period?: string; period: string;
  // Profitability
  gross_margin?: number | null; operating_margin?: number | null; net_margin?: number | null;
  return_on_equity?: number | null; return_on_assets?: number | null; return_on_invested_capital?: number | null;
  // Growth
  revenue_growth?: number | null; earnings_per_share_growth?: number | null;
  free_cash_flow_growth?: number | null; earnings_growth?: number | null;
  ebitda_growth?: number | null; operating_income_growth?: number | null; book_value_growth?: number | null;
  // Efficiency
  asset_turnover?: number | null; inventory_turnover?: number | null;
  // Valuation
  price_to_earnings_ratio?: number | null; enterprise_value_to_ebitda_ratio?: number | null;
  price_to_sales_ratio?: number | null; free_cash_flow_yield?: number | null;
  // Liquidity / Leverage
  current_ratio?: number | null; debt_to_equity?: number | null; interest_coverage?: number | null;
}
export interface IncomeStatement {
  ticker: string; report_period: string; fiscal_period: string; period: string;
  revenue?: number; cost_of_revenue?: number; gross_profit?: number;
  operating_expense?: number; operating_income?: number; ebit?: number; ebitda?: number;
  net_income?: number; net_income_common_stock?: number;
  earnings_per_share?: number; earnings_per_share_diluted?: number;
  research_and_development?: number; selling_general_and_administrative_expenses?: number;
  interest_expense?: number; income_tax_expense?: number;
  weighted_average_shares?: number; weighted_average_shares_diluted?: number;
}
export interface BalanceSheet {
  ticker: string; report_period: string; fiscal_period: string; period: string;
  total_assets?: number; current_assets?: number; cash_and_equivalents?: number;
  inventory?: number; trade_and_non_trade_receivables?: number;
  non_current_assets?: number; property_plant_and_equipment?: number;
  goodwill_and_intangible_assets?: number; total_liabilities?: number;
  current_liabilities?: number; current_debt?: number;
  non_current_liabilities?: number; non_current_debt?: number; total_debt?: number;
  shareholders_equity?: number; retained_earnings?: number; outstanding_shares?: number;
}
export interface CashFlowStatement {
  ticker: string; report_period: string; fiscal_period: string; period: string;
  net_income?: number; depreciation_and_amortization?: number; share_based_compensation?: number;
  net_cash_flow_from_operations?: number; capital_expenditure?: number;
  net_cash_flow_from_investing?: number; issuance_or_repayment_of_debt_securities?: number;
  issuance_or_purchase_of_equity_shares?: number; dividends_and_other_cash_distributions?: number;
  net_cash_flow_from_financing?: number; free_cash_flow?: number; ending_cash_balance?: number;
}
export interface InstitutionalOwner { investor: string; report_period: string; shares: number; market_value: number; price?: number; }
export interface InsiderTrade {
  name: string; title: string; is_board_director: boolean;
  transaction_date: string; transaction_shares: number;
  transaction_price_per_share: number; transaction_value: number;
  shares_owned_after_transaction: number; security_title: string; filing_date: string;
}
export interface AnalystEstimate { fiscal_period: string; period: string; revenue?: number; revenue_low?: number; revenue_high?: number; earnings_per_share?: number; eps_low?: number; eps_high?: number; num_analysts?: number; }
export interface NewsItem { ticker: string; title: string; source: string; date: string; url: string; }
export interface SegmentedRevenueSegment { key: string; axis: string; label: string; type?: string; }
export interface SegmentedRevenueItem { name: string; amount: number; start_period: string; end_period: string; segments: SegmentedRevenueSegment[]; }
export interface SegmentedRevenuePeriod { ticker: string; period: string; report_period: string; items: SegmentedRevenueItem[]; }
export interface CompanyProfile {
  description?: string; website?: string; employees?: number; city?: string; state?: string; country?: string;
  market_cap?: number; enterprise_value?: number; pe_ratio?: number; forward_pe?: number;
  peg_ratio?: number; ev_ebitda?: number; ev_revenue?: number; price_to_book?: number;
  price_to_sales?: number; beta?: number; week52_high?: number; week52_low?: number;
  avg_volume?: number; avg_volume_10d?: number; dividend_yield?: number;
  roe?: number; roa?: number; gross_margins?: number; operating_margins?: number; profit_margins?: number;
  revenue_growth?: number; earnings_growth?: number; current_ratio?: number; quick_ratio?: number;
  debt_to_equity?: number; shares_outstanding?: number; float_shares?: number;
  held_pct_institutions?: number; held_pct_insiders?: number;
  short_ratio?: number; short_pct_float?: number;
  officers?: { name: string; title: string; age?: number; pay?: number }[];
  currency?: string; exchange?: string;
}
export interface PeerMetrics {
  symbol: string; name: string;
  market_cap?: number; price?: number; day_change_pct?: number;
  revenue_growth?: number; gross_margin?: number; operating_margin?: number; net_margin?: number;
  roic?: number; pe?: number; ev_ebitda?: number; ps?: number; fcf_yield?: number;
}
export interface EarningsRecord {
  date: string; eps_estimate?: number; eps_actual?: number; surprise_pct?: number;
}
export interface PeHistoryRecord {
  year: string; eps?: number; price?: number; pe?: number;
}
export interface InsightItem { text: string; strength?: "strong" | "moderate" | "weak"; }
export interface ResearchInsights {
  bull: InsightItem[]; bear: InsightItem[];
  catalysts: InsightItem[]; risks: InsightItem[];
}

export interface FinancialAnomaly {
  id: string;
  category: "revenue" | "margins" | "profitability" | "cashflow" | "debt" | "working_capital";
  title: string;
  description: string;
  severity: "low" | "medium" | "high";
  section_id: string;
  metric_before?: number | null;
  metric_after?: number | null;
  metric_unit?: string;
}

export interface TrendPoint {
  period: string; report_period: string;
  value: number; growth: number | null;
}
export interface MarginPoint {
  period: string; report_period: string;
  gross: number | null; operating: number | null; net: number | null;
}
export interface ReturnPoint {
  period: string; report_period: string;
  roe: number | null; roa: number | null; roic: number | null;
}
export interface ResearchTrends {
  revenue: TrendPoint[]; eps: TrendPoint[];
  free_cash_flow: TrendPoint[]; margins: MarginPoint[]; returns: ReturnPoint[];
}

// ── Analysis Layer (deterministic — Computed) ─────────────────────────────────
export interface AnalysisPillar {
  key:              string;
  label:            string;
  score:            number | null;
  primary_metric:   string;
  primary_value:    string;
  secondary_metric: string;
  secondary_value:  string;
  explanation:      string;
  type:             "Computed";
}
export interface RiskFlag {
  category:    string;
  label:       string;
  severity:    "high" | "medium" | "low";
  explanation: string;
  type:        "Computed";
}
export interface SentimentRegime {
  score:      number | null;
  label:      string;
  type:       "Computed";
  drivers:    string[];
  warnings:   string[];
  components: {
    momentum?:             number | null;
    volatility_stress?:    number | null;
    positioning?:          number | null;
    expectation_pressure?: number | null;
  };
  meta?: {
    version?:          string;
    inputs_available?: boolean;
    missing?:          string[];
  };
}
export interface DataCoverage {
  quote_available:        boolean;
  fundamentals_available: "full" | "partial" | "none";
  estimates_available:    "full" | "partial" | "none";
  fresh_context_available: boolean;
}
export interface AnalysisLayer {
  pillars:          AnalysisPillar[];
  risk_flags:       RiskFlag[];
  sentiment_regime: SentimentRegime;
  coverage:         DataCoverage;
}

// ── Overview Synthesis (AI — Estimated) ──────────────────────────────────────
export interface NewsEnrichmentItem {
  headline:       string;
  why_it_matters: string;
  tag:            string;
}
export interface OverviewSynthesis {
  available:               boolean;
  stance:                  "bullish" | "neutral" | "bearish" | "insufficient_data" | null;
  summary_bullets:         string[];
  what_changed:            string[];
  why_now:                 string[];
  thesis_breakers:         string[];
  news_enrichment:         NewsEnrichmentItem[];
  confidence_note:         string;
  type:                    "Estimated";
  generated_at:            string;
  model:                   string | null;
  provider:                string | null;
  prompt_version:          string;
  tavily_retrieved_at:     string | null;
  fresh_context_available: boolean;
  _source:                 "cache" | "generated" | "none";
}

export interface ResearchData {
  ticker: string; computed_at: string;

  overview: {
    company:  CompanyFacts;
    profile:  CompanyProfile;
    snapshot: PriceSnapshot;
  };

  financials: {
    income_annual:    IncomeStatement[];
    income_quarterly: IncomeStatement[];
    income_ttm:       IncomeStatement | null;
    balance_annual:    BalanceSheet[];
    balance_quarterly: BalanceSheet[];
    balance_ttm:       BalanceSheet | null;
    cashflow_annual:    CashFlowStatement[];
    cashflow_quarterly: CashFlowStatement[];
    cashflow_ttm:       CashFlowStatement | null;
  };

  metrics: {
    snapshot:          FinancialMetrics | null;
    history_annual:    MetricsHistory[];
    history_quarterly: MetricsHistory[];
  };

  trends: {
    annual:    ResearchTrends;
    quarterly: ResearchTrends;
  };

  research: {
    peers:         PeerMetrics[];
    ownership:     InstitutionalOwner[];
    insider_trades: InsiderTrade[];
  };

  estimates: {
    annual:    AnalystEstimate[];
    quarterly: AnalystEstimate[];
  };

  valuation: {
    pe_history: PeHistoryRecord[];
  };

  segments:         SegmentedRevenuePeriod[];
  earnings_history: EarningsRecord[];

  analysis: {
    insights:  ResearchInsights | null;
    anomalies: FinancialAnomaly[];
  };

  news: NewsItem[];

  /** Deterministic analysis layer — always present when research is ready */
  analysis_layer?: AnalysisLayer | null;
}
export interface ResearchPollStatus {
  status: "preparing" | "error";
  ticker: string;
  detail?: string;
}

const _POLL_INTERVAL = 3000;
const _POLL_MAX      = 40;   // 40 × 3s = 2 min timeout

async function _researchPoll(
  ticker: string,
  force: boolean,
  onPreparing?: () => void,
): Promise<ResearchData> {
  const base = `/research/${ticker.toUpperCase()}`;

  for (let i = 0; i < _POLL_MAX; i++) {
    // force=true only on the first request — subsequent polls must check the
    // cache normally, otherwise a completed pipeline task is never detected.
    const path = `${base}${force && i === 0 ? "?force=true" : ""}`;

    const headers: Record<string, string> = { "Content-Type": "application/json" };
    const token = getAccessToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const res = await fetch(`${BASE}${path}`, { headers, credentials: "include" });

    if (res.status === 200) {
      const body = await res.json();
      if (body.status === "error") throw new ApiError(500, body.detail || "Data fetch failed");
      if (body.status === "preparing") {
        onPreparing?.();
        await new Promise(r => setTimeout(r, _POLL_INTERVAL));
        continue;
      }
      return body as ResearchData;
    }

    if (res.status === 202) {
      onPreparing?.();
      await new Promise(r => setTimeout(r, _POLL_INTERVAL));
      continue;
    }

    if (res.status === 401) {
      const ok = await tryRefresh();
      if (!ok) { _onSessionExpired?.(); throw new ApiError(401, "Session expired"); }
      continue;
    }

    const b = await res.json().catch(() => ({}));
    throw new ApiError(res.status, b.detail || res.statusText, b);
  }

  throw new ApiError(408, "Research data fetch timed out. Please try again.");
}

export const researchApi = {
  get: (ticker: string, force = false, onPreparing?: () => void) =>
    _researchPoll(ticker, force, onPreparing),
  aiInsights: (ticker: string, force = false) =>
    apiFetch<AiInsights>(`/research/${ticker.toUpperCase()}/ai-insights${force ? "?force=true" : ""}`),
  overviewSynthesis: (ticker: string, force = false) =>
    apiFetch<OverviewSynthesis>(`/research/${ticker.toUpperCase()}/overview-synthesis${force ? "?force=true" : ""}`),
};

export interface AiInsights {
  summary:        string;
  strengths:      string[];
  weaknesses:     string[];
  drivers:        string[];
  risks:          string[];
  valuation_view: string;
  generated_at:   string;
  model:          string | null;
  provider:       string | null;
  available:      boolean;
  _source:        "cache" | "generated" | "none";
}

// ─── Search ───────────────────────────────────────────────────────────────────
export interface SearchResult {
  symbol: string; name: string; exchange: string; type: string; sector: string;
}

export const searchApi = {
  search: (q: string) => apiFetch<SearchResult[]>(`/search?q=${encodeURIComponent(q)}`),
};

// ─── Admin Types ──────────────────────────────────────────────────────────────
export interface AdminUserRow {
  id: string; email: string; full_name: string | null;
  tier: string; is_active: boolean; is_admin: boolean; is_verified: boolean;
  created_at: string; portfolio_count: number; last_active_at: string | null;
}
export interface AdminUserDetail extends AdminUserRow {
  stripe_customer_id: string | null; has_api_key: boolean;
}
export interface AdminUserUpdate {
  tier?: string; is_active?: boolean; is_admin?: boolean; full_name?: string;
}
export interface AdminUserListResponse {
  items: AdminUserRow[]; total: number; limit: number; offset: number;
}

export interface TierConfig {
  name: string; display_name: string;
  max_portfolios: number; max_positions: number;
  rpm: number; rpd: number; ai_per_day: number; price_usd: number;
}

export interface DataProviderConfig {
  name: string; display_name: string; enabled: boolean;
  priority: number; rate_limit_rpm: number;
  cost_per_call_usd: number; notes: string | null;
}

export interface AdminPortfolioRow {
  id: string; user_id: string; user_email: string;
  name: string; currency: string; position_count: number;
  created_at: string; updated_at: string;
}
export interface AdminPortfolioListResponse {
  items: AdminPortfolioRow[]; total: number; limit: number; offset: number;
}

export interface ProviderCostDay {
  date: string; provider: string; calls: number; estimated_cost_usd: number;
}
export interface CostSummary {
  period_days: number; total_calls: number; total_cost_usd: number;
  by_provider: Record<string, { calls: number; estimated_cost_usd: number }>;
  daily: ProviderCostDay[];
}

export interface SystemSummary {
  total_users: number; active_users_7d: number; active_users_30d: number;
  requests_today: number; requests_7d: number;
  error_rate_pct: number; cache_hit_rate_pct: number;
  paid_calls_today: number; estimated_cost_today: number; avg_latency_ms: number;
}

export interface AuditLogRow {
  id: string; admin_email: string | null; action: string;
  entity: string | null; entity_id: string | null;
  metadata: Record<string, unknown> | null; ip_address: string | null; ts: string;
}
export interface AuditLogListResponse {
  items: AuditLogRow[]; total: number; limit: number; offset: number;
}

// ─── Admin API ────────────────────────────────────────────────────────────────
function _qs(params: Record<string, unknown>): string {
  const p = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== "")
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
    .join("&");
  return p ? `?${p}` : "";
}

export const adminApi = {
  stats: () => apiFetch<AdminStats>("/admin/stats"),

  users: (p: { limit?: number; offset?: number; email?: string; tier?: string; is_active?: boolean }) =>
    apiFetch<AdminUserListResponse>(`/admin/users${_qs(p)}`),
  user:  (id: string) => apiFetch<AdminUserDetail>(`/admin/users/${id}`),
  updateUser: (id: string, body: AdminUserUpdate) =>
    apiFetch<AdminUserDetail>(`/admin/users/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  resetPassword: (id: string, new_password: string) =>
    apiFetch<void>(`/admin/users/${id}/reset-password`, { method: "POST", body: JSON.stringify({ new_password }) }),
  revokeApiKey: (id: string) =>
    apiFetch<void>(`/admin/users/${id}/revoke-api-key`, { method: "POST" }),

  tiers: () => apiFetch<TierConfig[]>("/admin/tiers"),
  updateTier: (name: string, body: Partial<Omit<TierConfig, "name">>) =>
    apiFetch<TierConfig>(`/admin/tiers/${name}`, { method: "PATCH", body: JSON.stringify(body) }),

  providers: () => apiFetch<DataProviderConfig[]>("/admin/providers"),
  updateProvider: (name: string, body: Partial<Omit<DataProviderConfig, "name" | "display_name">>) =>
    apiFetch<DataProviderConfig>(`/admin/providers/${name}`, { method: "PATCH", body: JSON.stringify(body) }),
  reorderProviders: (order: string[]) =>
    apiFetch<void>("/admin/providers/reorder", { method: "POST", body: JSON.stringify({ order }) }),

  portfolios: (p: { limit?: number; offset?: number; user_id?: string }) =>
    apiFetch<AdminPortfolioListResponse>(`/admin/portfolios${_qs(p)}`),
  deletePortfolio: (id: string) =>
    apiFetch<void>(`/admin/portfolios/${id}`, { method: "DELETE" }),

  costs: (days = 30) => apiFetch<CostSummary>(`/admin/costs?days=${days}`),
  systemSummary: () => apiFetch<SystemSummary>("/admin/system-summary"),
  auditLogs: (p: { limit?: number; offset?: number; action?: string }) =>
    apiFetch<AuditLogListResponse>(`/admin/audit-logs${_qs(p)}`),
};

// ─── Market Status ────────────────────────────────────────────────────────────
export interface MarketStatus {
  state:       "pre_market" | "open" | "after_hours" | "closed";
  label:       string;
  next_change: string;
  countdown:   string;
  is_trading:  boolean;
  timezone:    string;
}

export const marketStatus = {
  get: () => apiFetch<MarketStatus>("/market/status"),
};

// ─── Prices (REST bulk) ───────────────────────────────────────────────────────
export const pricesApi = {
  bulk: (tickers: string[]) =>
    apiFetch<Record<string, PriceUpdate>>(
      `/market/prices?tickers=${encodeURIComponent(tickers.map(t => t.toUpperCase()).join(","))}`,
    ),
};

// ─── SSE Price Stream ─────────────────────────────────────────────────────────
export interface PriceUpdate {
  ticker:     string;
  price:      number;
  change:     number;
  change_pct: number;
  fetched_at: string;
}

export type SSEEventHandler = {
  onPrice?:        (update: PriceUpdate) => void;
  onMarketStatus?: (status: MarketStatus) => void;
  onHeartbeat?:    () => void;
  onError?:        (err: Event) => void;
  onClose?:        (reason: string) => void;
};

/**
 * Connect to the SSE price stream using fetch() + ReadableStream.
 * This lets us send the Authorization header (EventSource cannot).
 * Returns a cleanup function that aborts the connection.
 */
export function connectPriceStream(
  tickers: string[],
  handlers: SSEEventHandler,
): () => void {
  if (!tickers.length) return () => {};

  const tickerParam = tickers.map(t => t.toUpperCase()).join(",");
  const url = `${BASE}/stream/prices?tickers=${encodeURIComponent(tickerParam)}`;
  const controller = new AbortController();

  (async () => {
    try {
      const headers: Record<string, string> = { "Accept": "text/event-stream" };
      if (_accessToken) headers["Authorization"] = `Bearer ${_accessToken}`;

      console.log("[SSE] connecting to", url);
      const res = await fetch(url, {
        headers,
        credentials: "include",
        signal: controller.signal,
      });

      if (!res.ok || !res.body) {
        console.warn("[SSE] fetch failed:", res.status, res.statusText);
        handlers.onError?.(new Event("fetch-error"));
        return;
      }

      console.log("[SSE] connected, reading stream...");
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) { console.log("[SSE] stream ended"); break; }

        buf += decoder.decode(value, { stream: true });
        const parts = buf.split("\n\n");
        buf = parts.pop() ?? "";

        for (const part of parts) {
          const lines = part.split("\n");
          let event = "";
          let data = "";
          for (const line of lines) {
            if (line.startsWith("event: ")) event = line.slice(7);
            else if (line.startsWith("data: ")) data = line.slice(6);
          }
          if (!event || !data) continue;

          try {
            const parsed = JSON.parse(data);
            console.log("[SSE]", event, event === "price" ? parsed.ticker : "");
            switch (event) {
              case "price":         handlers.onPrice?.(parsed); break;
              case "market_status": handlers.onMarketStatus?.(parsed); break;
              case "heartbeat":     handlers.onHeartbeat?.(); break;
              case "close":
                handlers.onClose?.(parsed.reason || "unknown");
                reader.cancel();
                return;
            }
          } catch { /* skip malformed events */ }
        }
      }
    } catch (err) {
      // Suppress errors that fired after an intentional abort —
      // covers AbortError, TypeError ("Failed to fetch"), and any race
      // where the error arrives after controller.abort() was called.
      if (controller.signal.aborted || (err as DOMException)?.name === "AbortError") {
        return;
      }
      console.warn("[SSE] stream error:", err);
      handlers.onError?.(new Event("stream-error"));
    }
  })();

  return () => controller.abort();
}
