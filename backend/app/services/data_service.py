"""
Smart Data Service — The heart of AlphaDesk's cost-saving strategy.

Fetch strategy (cheapest to most expensive):
  1. Redis L1 cache     → sub-ms, free
  2. Postgres L2 cache  → ~2ms, free
  3. yfinance           → ~200ms, free (rate limited by Yahoo)
  4. financialdatasets  → ~300ms, PAID — only when needed

Data source mapping:
  Prices (real-time)    → yfinance (free) with Redis TTL 15min
  Price history         → yfinance (free) → stored in TimescaleDB
  Fundamentals/TTM      → financialdatasets (paid) cached 24h in Redis + PG
  SEC Filings           → financialdatasets (paid) cached 7 days
  Insider trades        → financialdatasets (paid) cached 4h
  Earnings estimates    → financialdatasets (paid) cached 1h
  Company profile       → yfinance (free) cached 7 days
"""
import asyncio, json, logging, time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import yfinance as yf
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.config import get_settings
from app.database import Cache
from app.models import CacheFundamentals, CachePrice

log      = logging.getLogger(__name__)
settings = get_settings()

# ── Cache key helpers ────────────────────────────────────────────────────────
def _price_key(ticker: str)        -> str: return f"price:{ticker.upper()}"
def _fund_key(ticker: str)         -> str: return f"fundamentals:{ticker.upper()}"
def _profile_key(ticker: str)      -> str: return f"profile:{ticker.upper()}"
def _history_key(t, period, iv)    -> str: return f"history:{t.upper()}:{period}:{iv}"
def _insider_key(ticker: str)      -> str: return f"insider:{ticker.upper()}"
def _earnings_key(ticker: str)     -> str: return f"earnings:{ticker.upper()}"


class DataService:
    """
    All external data access goes through this class.
    Never call yfinance or financialdatasets directly from routers.
    """

    def __init__(self, cache: Cache, db: AsyncSession):
        self.cache = cache
        self.db    = db
        self._fd_client = httpx.AsyncClient(
            base_url=settings.FINANCIALDATASETS_BASE_URL,
            headers={"X-API-KEY": settings.FINANCIALDATASETS_API_KEY},
            timeout=15.0,
            follow_redirects=True,
        )

    async def aclose(self):
        await self._fd_client.aclose()

    # ════════════════════════════════════════════════════════════════
    # PRICES  (yfinance free, Redis TTL 15min)
    # ════════════════════════════════════════════════════════════════
    async def get_price(self, ticker: str) -> dict[str, Any]:
        key = _price_key(ticker)

        # L1: Redis
        cached = await self.cache.get(key)
        if cached:
            data = json.loads(cached)
            data["_source"] = "cache_redis"
            return data

        # Fetch from yfinance (free)
        data = await self._fetch_price_yfinance(ticker)
        data["_source"] = "yfinance"

        # Store in L1 (Redis)
        await self.cache.set(key, json.dumps(data), settings.CACHE_PRICE_TTL)
        return data

    async def get_prices_bulk(self, tickers: list[str]) -> dict[str, dict]:
        """Batch price fetch — minimises yfinance calls."""
        results = {}
        missing = []

        for t in tickers:
            cached = await self.cache.get(_price_key(t))
            if cached:
                results[t] = json.loads(cached)
                results[t]["_source"] = "cache_redis"
            else:
                missing.append(t)

        if missing:
            fetched = await self._fetch_prices_bulk_yfinance(missing)
            for ticker, data in fetched.items():
                data["_source"] = "yfinance"
                results[ticker] = data
                await self.cache.set(_price_key(ticker), json.dumps(data), settings.CACHE_PRICE_TTL)

        return results

    async def _fetch_price_yfinance(self, ticker: str) -> dict:
        loop = asyncio.get_event_loop()
        def _sync():
            t = yf.Ticker(ticker)
            info = t.fast_info
            return {
                "ticker":     ticker.upper(),
                "price":      float(info.last_price or 0),
                "change":     float(info.last_price - info.previous_close) if info.previous_close else 0,
                "change_pct": float((info.last_price - info.previous_close) / info.previous_close * 100) if info.previous_close else 0,
                "volume":     int(info.three_month_average_volume or 0),
                "market_cap": float(info.market_cap or 0),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
        return await loop.run_in_executor(None, _sync)

    async def _fetch_prices_bulk_yfinance(self, tickers: list[str]) -> dict[str, dict]:
        loop = asyncio.get_event_loop()
        def _sync():
            import pandas as pd
            symbols = " ".join(tickers)
            data = yf.download(symbols, period="2d", auto_adjust=True, progress=False)
            results = {}
            now = datetime.now(timezone.utc).isoformat()
            for t in tickers:
                try:
                    close_col = ("Close", t) if isinstance(data.columns, pd.MultiIndex) else "Close"
                    prices = data[close_col].dropna()
                    if len(prices) >= 2:
                        curr, prev = float(prices.iloc[-1]), float(prices.iloc[-2])
                        results[t] = {
                            "ticker": t, "price": curr,
                            "change": curr - prev,
                            "change_pct": (curr - prev) / prev * 100,
                            "fetched_at": now,
                        }
                    else:
                        results[t] = {"ticker": t, "price": 0, "change": 0, "change_pct": 0, "fetched_at": now}
                except Exception as e:
                    log.warning(f"yfinance bulk price error for {t}: {e}")
                    results[t] = {"ticker": t, "price": 0, "error": str(e), "fetched_at": now}
            return results
        return await loop.run_in_executor(None, _sync)

    # ════════════════════════════════════════════════════════════════
    # FUNDAMENTALS  (financialdatasets PAID — aggressive caching)
    # ════════════════════════════════════════════════════════════════
    async def get_fundamentals(self, ticker: str, force_refresh: bool = False) -> dict[str, Any]:
        key = _fund_key(ticker)

        if not force_refresh:
            # L1: Redis
            cached = await self.cache.get(key)
            if cached:
                data = json.loads(cached)
                data["_source"] = "cache_redis"
                return data

            # L2: Postgres (survives Redis restarts)
            pg_cached = await self._get_pg_fundamentals(ticker)
            if pg_cached:
                # Repopulate Redis from PG
                await self.cache.set(key, json.dumps(pg_cached), settings.CACHE_FUNDAMENTALS_TTL)
                pg_cached["_source"] = "cache_pg"
                return pg_cached

        # L3: financialdatasets.ai (PAID — billed per call)
        log.info(f"PAID API CALL: financialdatasets fundamentals for {ticker}")
        data = await self._fetch_fundamentals_fd(ticker)

        if "error" not in data:
            # Enrich with yfinance free data (ratios, margins)
            yf_data = await self._fetch_profile_yfinance(ticker)
            data["yf_enrichment"] = yf_data

            now = datetime.now(timezone.utc)
            data["fetched_at"] = now.isoformat()

            # Store in both caches
            await self.cache.set(key, json.dumps(data), settings.CACHE_FUNDAMENTALS_TTL)
            await self._upsert_pg_fundamentals(ticker, data)

        data["_source"] = "financialdatasets"
        return data

    async def _fetch_fundamentals_fd(self, ticker: str) -> dict:
        """Call financialdatasets.ai for income statement + cash flow."""
        try:
            # Fetch both in parallel to minimise latency
            income_task = self._fd_client.get(
                "/financials/income-statements",
                params={"ticker": ticker, "period": "ttm", "limit": 1}
            )
            cashflow_task = self._fd_client.get(
                "/financials/cash-flow-statements",
                params={"ticker": ticker, "period": "ttm", "limit": 1}
            )
            balance_task = self._fd_client.get(
                "/financials/balance-sheets",
                params={"ticker": ticker, "period": "ttm", "limit": 1}
            )
            income_r, cashflow_r, balance_r = await asyncio.gather(
                income_task, cashflow_task, balance_task
            )

            for label, r in [("income", income_r), ("cashflow", cashflow_r), ("balance", balance_r)]:
                if r.status_code not in (200, 201):
                    log.error("financialdatasets %s HTTP %s: %s", label, r.status_code, r.text[:200])
                    raise ValueError(f"financialdatasets {label} returned HTTP {r.status_code}: {r.text[:200]}")

            income   = income_r.json().get("income_statements", [{}])[0]
            cashflow = cashflow_r.json().get("cash_flow_statements", [{}])[0]
            balance  = balance_r.json().get("balance_sheets", [{}])[0]

            revenue  = income.get("revenue", 1) or 1
            net_inc  = income.get("net_income", 0) or 0
            ebit     = income.get("operating_income", 0) or 0
            ebitda   = income.get("ebitda", 0) or 0
            fcf      = cashflow.get("free_cash_flow", 0) or 0

            return {
                "ticker":          ticker.upper(),
                "revenue":         revenue,
                "net_income":      net_inc,
                "ebit":            ebit,
                "ebitda":          ebitda,
                "free_cash_flow":  fcf,
                "ni_margin":       round(net_inc / revenue * 100, 2),
                "ebit_margin":     round(ebit    / revenue * 100, 2),
                "ebitda_margin":   round(ebitda  / revenue * 100, 2),
                "fcf_margin":      round(fcf     / revenue * 100, 2),
                "total_assets":    balance.get("total_assets"),
                "total_debt":      balance.get("total_debt"),
                "cash":            balance.get("cash_and_equivalents"),
                "raw_income":      income,
                "raw_cashflow":    cashflow,
                "raw_balance":     balance,
            }
        except Exception as e:
            log.error(f"financialdatasets API error for {ticker}: {e}")
            return {"ticker": ticker, "error": str(e)}

    async def _get_pg_fundamentals(self, ticker: str) -> dict | None:
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(CacheFundamentals).where(
                CacheFundamentals.ticker == ticker.upper(),
                CacheFundamentals.expires_at > now
            )
        )
        row = result.scalar_one_or_none()
        return row.data if row else None

    async def _upsert_pg_fundamentals(self, ticker: str, data: dict):
        now     = datetime.now(timezone.utc)
        expires = now + timedelta(hours=settings.PG_CACHE_FUNDAMENTALS_HOURS)
        existing = await self.db.get(CacheFundamentals, ticker.upper())
        if existing:
            existing.data       = data
            existing.source     = "financialdatasets"
            existing.fetched_at = now
            existing.expires_at = expires
        else:
            self.db.add(CacheFundamentals(
                ticker=ticker.upper(), source="financialdatasets",
                data=data, fetched_at=now, expires_at=expires
            ))
        await self.db.flush()

    # ════════════════════════════════════════════════════════════════
    # PRICE HISTORY  (yfinance free → stored in TimescaleDB)
    # ════════════════════════════════════════════════════════════════
    async def get_price_history(self, ticker: str, period: str = "1y", interval: str = "1d") -> list[dict]:
        key = _history_key(ticker, period, interval)
        cached = await self.cache.get(key)
        if cached:
            return json.loads(cached)

        loop = asyncio.get_event_loop()
        def _sync():
            t = yf.Ticker(ticker)
            hist = t.history(period=period, interval=interval, auto_adjust=True)
            records = []
            for ts, row in hist.iterrows():
                records.append({
                    "ts":     ts.isoformat(),
                    "open":   round(float(row["Open"]),  4),
                    "high":   round(float(row["High"]),  4),
                    "low":    round(float(row["Low"]),   4),
                    "close":  round(float(row["Close"]), 4),
                    "volume": int(row["Volume"]),
                })
            return records

        records = await loop.run_in_executor(None, _sync)
        # Cache for 1h for daily, 15min for intraday
        ttl = 900 if interval in ("1m","5m","15m","1h") else 3600
        await self.cache.set(key, json.dumps(records), ttl)
        return records

    # ════════════════════════════════════════════════════════════════
    # COMPANY PROFILE  (yfinance free, 7-day cache)
    # ════════════════════════════════════════════════════════════════
    async def get_profile(self, ticker: str) -> dict:
        key = _profile_key(ticker)
        cached = await self.cache.get(key)
        if cached:
            data = json.loads(cached)
            data["_source"] = "cache_redis"
            return data

        data = await self._fetch_profile_yfinance(ticker)
        await self.cache.set(key, json.dumps(data), settings.CACHE_PROFILE_TTL)
        data["_source"] = "yfinance"
        return data

    async def _fetch_profile_yfinance(self, ticker: str) -> dict:
        loop = asyncio.get_event_loop()
        def _sync():
            t = yf.Ticker(ticker)
            i = t.info
            return {
                "ticker":      ticker.upper(),
                "name":        i.get("longName", ""),
                "sector":      i.get("sector", ""),
                "industry":    i.get("industry", ""),
                "description": i.get("longBusinessSummary", ""),
                "website":     i.get("website", ""),
                "employees":   i.get("fullTimeEmployees"),
                "country":     i.get("country", ""),
                "pe_ratio":    i.get("trailingPE"),
                "fwd_pe":      i.get("forwardPE"),
                "pb_ratio":    i.get("priceToBook"),
                "dividend_yield": i.get("dividendYield"),
                "beta":        i.get("beta"),
                "52w_high":    i.get("fiftyTwoWeekHigh"),
                "52w_low":     i.get("fiftyTwoWeekLow"),
                "avg_volume":  i.get("averageVolume"),
            }
        return await loop.run_in_executor(None, _sync)

    # ════════════════════════════════════════════════════════════════
    # INSIDER TRADES  (financialdatasets PAID, 4h cache)
    # ════════════════════════════════════════════════════════════════
    async def get_insider_trades(self, ticker: str) -> list[dict]:
        key = _insider_key(ticker)
        cached = await self.cache.get(key)
        if cached:
            return json.loads(cached)

        log.info(f"PAID API CALL: financialdatasets insider trades for {ticker}")
        try:
            r = await self._fd_client.get(
                "/insider-trades",
                params={"ticker": ticker, "limit": 20}
            )
            trades = r.json().get("insider_trades", [])
        except Exception as e:
            log.error(f"Insider trades error {ticker}: {e}")
            trades = []

        await self.cache.set(key, json.dumps(trades), settings.CACHE_INSIDER_TTL)
        return trades

    # ════════════════════════════════════════════════════════════════
    # EARNINGS  (financialdatasets PAID, 1h cache)
    # ════════════════════════════════════════════════════════════════
    async def get_earnings(self, ticker: str) -> dict:
        key = _earnings_key(ticker)
        cached = await self.cache.get(key)
        if cached:
            return json.loads(cached)

        log.info(f"PAID API CALL: financialdatasets earnings for {ticker}")
        try:
            r = await self._fd_client.get(
                "/earnings",
                params={"ticker": ticker, "limit": 8}
            )
            data = r.json()
        except Exception as e:
            log.error(f"Earnings error {ticker}: {e}")
            data = {"error": str(e)}

        await self.cache.set(key, json.dumps(data), settings.CACHE_EARNINGS_TTL)
        return data

    # ════════════════════════════════════════════════════════════════
    # NEWS  (yfinance free, 15-minute cache per ticker)
    # ════════════════════════════════════════════════════════════════
    async def get_news(self, ticker: str) -> list[dict]:
        """Fetch recent news for a ticker via yfinance. Cached 15 minutes."""
        key = f"news:{ticker.upper()}"
        cached = await self.cache.get(key)
        if cached:
            return json.loads(cached)

        loop = asyncio.get_event_loop()
        def _sync():
            t        = yf.Ticker(ticker)
            raw_news = t.news or []
            result   = []
            for item in raw_news[:15]:
                content = item.get("content") or {}
                if content:
                    # yfinance ≥1.2 nested format
                    title    = content.get("title", "")
                    provider = (content.get("provider") or {}).get("displayName", "")
                    url_obj  = content.get("canonicalUrl") or content.get("clickThroughUrl") or {}
                    url      = url_obj.get("url", "")
                    pub_date = (content.get("pubDate") or "")[:10]
                else:
                    # Legacy flat format
                    title    = item.get("title", "")
                    provider = item.get("publisher", "")
                    url      = item.get("link", "")
                    ts       = item.get("providerPublishTime", 0)
                    pub_date = (
                        datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
                        if ts else ""
                    )
                if title:
                    result.append({
                        "ticker":   ticker.upper(),
                        "headline": title,
                        "source":   provider,
                        "url":      url,
                        "date":     pub_date,
                    })
            return result

        news = await loop.run_in_executor(None, _sync)
        await self.cache.set(key, json.dumps(news), 900)   # 15 min
        return news

    # ════════════════════════════════════════════════════════════════
    # CACHE MANAGEMENT
    # ════════════════════════════════════════════════════════════════
    async def invalidate(self, ticker: str):
        """Force-expire all cached data for a ticker."""
        for key in [_price_key(ticker), _fund_key(ticker), _profile_key(ticker),
                    _insider_key(ticker), _earnings_key(ticker)]:
            await self.cache.delete(key)
        await self.db.execute(
            delete(CacheFundamentals).where(CacheFundamentals.ticker == ticker.upper())
        )
        log.info(f"Cache invalidated for {ticker}")
