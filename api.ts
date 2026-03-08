/**
 * AlphaDesk API Client — typed wrapper with auto token-refresh and error handling.
 * All API calls go through apiFetch() which handles auth headers and 401 retries.
 */

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

let _accessToken: string | null = null;
export const setAccessToken = (t: string | null) => { _accessToken = t; };
export const getAccessToken = () => _accessToken;

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

  const res = await fetch(`${BASE}${path}`, { ...init, headers });

  if (res.status === 401 && !skipRefresh) {
    const ok = await tryRefresh();
    if (ok) {
      headers["Authorization"] = `Bearer ${_accessToken}`;
      const retry = await fetch(`${BASE}${path}`, { ...init, headers });
      if (retry.ok) return retry.status === 204 ? (undefined as T) : retry.json();
    }
    throw new ApiError(401, "Session expired. Please log in again.");
  }

  if (!res.ok) {
    const b = await res.json().catch(() => ({}));
    throw new ApiError(res.status, b.detail || res.statusText, b);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

async function tryRefresh(): Promise<boolean> {
  const rt = typeof window !== "undefined" ? localStorage.getItem("refresh_token") : null;
  if (!rt) return false;
  try {
    const d = await apiFetch<{ access_token: string; refresh_token: string }>(
      "/auth/refresh",
      { method: "POST", body: JSON.stringify({ refresh_token: rt }), skipRefresh: true }
    );
    setAccessToken(d.access_token);
    if (typeof window !== "undefined") localStorage.setItem("refresh_token", d.refresh_token);
    return true;
  } catch {
    setAccessToken(null);
    if (typeof window !== "undefined") localStorage.removeItem("refresh_token");
    return false;
  }
}

// ─── Types ────────────────────────────────────────────────────────────────────
export interface User          { id: string; email: string; full_name: string|null; tier: "free"|"pro"|"fund"; is_verified: boolean; created_at: string; }
export interface TokenResp     { access_token: string; refresh_token: string; token_type: string; expires_in: number; }
export interface Portfolio     { id: string; name: string; description: string|null; currency: string; is_default: boolean; created_at: string; }
export interface Position      { id: string; ticker: string; shares: number; cost_basis: number; notes: string|null; opened_at: string; current_price?: number; current_value?: number; gain_loss?: number; gain_loss_pct?: number; weight_pct?: number; }
export interface PortfolioMetrics { total_value: number; total_cost: number; total_gain: number; total_gain_pct: number; day_gain: number; day_gain_pct: number; cash_value: number; cash_pct: number; beta?: number; sharpe?: number; max_drawdown?: number; volatility?: number; }
export interface PriceData     { ticker: string; price: number; change: number; change_pct: number; volume?: number; fetched_at: string; source: string; }
export interface Fundamentals  { ticker: string; ni_margin?: number; ebit_margin?: number; ebitda_margin?: number; fcf_margin?: number; revenue?: number; net_income?: number; fetched_at?: string; source: string; }
export interface WatchlistItem { id: string; ticker: string; quant_rating?: number; sector?: string; announce_date?: string; notes?: string; alert_price?: number; created_at: string; current_price?: number; }
export interface Transaction   { id: string; ticker: string; side: "buy"|"sell"; shares: number; price: number; fees: number; traded_at: string; notes?: string; }
export interface HistoryBar    { ts: string; open: number; high: number; low: number; close: number; volume: number; }
export interface AdminStats    { total_users: number; users_by_tier: Record<string,number>; api_calls_today: number; cache_hit_rate: number; paid_calls_today: number; estimated_cost_usd: number; }

// ─── Auth ────────────────────────────────────────────────────────────────────
export const auth = {
  register: (email: string, password: string, full_name?: string) =>
    apiFetch<User>("/auth/register", { method: "POST", body: JSON.stringify({ email, password, full_name }) }),

  login: async (email: string, password: string) => {
    const d = await apiFetch<TokenResp>("/auth/login", {
      method: "POST", body: JSON.stringify({ email, password }), skipRefresh: true,
    });
    setAccessToken(d.access_token);
    if (typeof window !== "undefined") localStorage.setItem("refresh_token", d.refresh_token);
    return d;
  },

  logout: async () => {
    await apiFetch("/auth/logout", { method: "POST" }).catch(() => {});
    setAccessToken(null);
    if (typeof window !== "undefined") localStorage.removeItem("refresh_token");
  },

  me:             () => apiFetch<User>("/auth/me"),
  generateApiKey: () => apiFetch<{ api_key: string; note: string }>("/auth/api-key", { method: "POST" }),
  revokeApiKey:   () => apiFetch("/auth/api-key", { method: "DELETE" }),
};

// ─── Portfolios ───────────────────────────────────────────────────────────────
export const portfolios = {
  list:    ()                                  => apiFetch<Portfolio[]>("/portfolio/"),
  create:  (b: Partial<Portfolio>)             => apiFetch<Portfolio>("/portfolio/", { method: "POST", body: JSON.stringify(b) }),
  get:     (id: string)                        => apiFetch<Portfolio>(`/portfolio/${id}`),
  update:  (id: string, b: Partial<Portfolio>) => apiFetch<Portfolio>(`/portfolio/${id}`, { method: "PATCH", body: JSON.stringify(b) }),
  delete:  (id: string)                        => apiFetch(`/portfolio/${id}`, { method: "DELETE" }),
  metrics: (id: string)                        => apiFetch<PortfolioMetrics>(`/portfolio/${id}/metrics`),
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
  list: (pid: string) => apiFetch<Transaction[]>(`/portfolio/${pid}/transactions`),
  add:  (pid: string, b: Omit<Transaction,"id">) =>
          apiFetch<Transaction>(`/portfolio/${pid}/transactions`, { method: "POST", body: JSON.stringify(b) }),
};

// ─── Watchlist ────────────────────────────────────────────────────────────────
export const watchlistApi = {
  list:   ()                          => apiFetch<WatchlistItem[]>("/portfolio/watchlist/"),
  add:    (b: Partial<WatchlistItem>) => apiFetch<WatchlistItem>("/portfolio/watchlist/", { method: "POST", body: JSON.stringify(b) }),
  remove: (id: string)                => apiFetch(`/portfolio/watchlist/${id}`, { method: "DELETE" }),
};

// ─── Market data ──────────────────────────────────────────────────────────────
export const market = {
  price:        (ticker: string)                => apiFetch<PriceData>(`/market/price/${ticker}`),
  prices:       (tickers: string[])             => apiFetch<Record<string,PriceData>>(`/market/prices?tickers=${tickers.join(",")}`),
  fundamentals: (ticker: string, force = false) => apiFetch<Fundamentals>(`/market/fundamentals/${ticker}?force_refresh=${force}`),
  history:      (ticker: string, period = "1y", interval = "1d") =>
                  apiFetch<{ ticker: string; data: HistoryBar[] }>(`/market/history/${ticker}?period=${period}&interval=${interval}`),
  profile:      (ticker: string) => apiFetch<Record<string,unknown>>(`/market/profile/${ticker}`),
  insider:      (ticker: string) => apiFetch<{ trades: unknown[] }>(`/market/insider/${ticker}`),
  earnings:     (ticker: string) => apiFetch<Record<string,unknown>>(`/market/earnings/${ticker}`),
  invalidate:   (ticker: string) => apiFetch(`/market/cache/invalidate/${ticker}`, { method: "POST" }),
};

// ─── Admin ────────────────────────────────────────────────────────────────────
export const adminApi = {
  stats: () => apiFetch<AdminStats>("/admin/stats"),
};
