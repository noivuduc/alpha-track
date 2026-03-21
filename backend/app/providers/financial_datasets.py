"""
FinancialDatasets.ai provider — paid tier, uses httpx.

All FD API endpoint strings, the X-API-KEY header, and FD-specific field
names are contained here.  Nothing outside this file should reference
financialdatasets.ai URLs or response field names directly.

Supported methods:
    get_price_snapshot          — /prices/snapshot/
    get_earnings                — /earnings/
    get_fundamentals_ttm        — /financials/income-statements/ +
                                  /financials/cash-flow-statements/ +
                                  /financials/balance-sheets/
    get_company_facts           — /company/facts/
    get_metrics_snapshot        — /financial-metrics/snapshot/
    get_financials              — /financials/
    get_metrics_history         — /financial-metrics/
    get_institutional_ownership — /institutional-ownership/
    get_analyst_estimates       — /analyst-estimates/
    get_insider_trades          — /insider-trades/
    get_segmented_revenues      — /financials/segmented-revenues/
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from .base import MarketDataProvider

log = logging.getLogger(__name__)


class FinancialDatasetsProvider(MarketDataProvider):
    """
    Wraps the financialdatasets.ai REST API.

    Constructor
    -----------
    api_key  : str   — value of the X-API-KEY header
    base_url : str   — base URL (default https://api.financialdatasets.ai)
    timeout  : float — request timeout in seconds (default 15)
    """

    def __init__(
        self,
        api_key:  str,
        base_url: str = "https://api.financialdatasets.ai",
        timeout:  float = 15.0,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"X-API-KEY": api_key},
            timeout=timeout,
            follow_redirects=True,
        )

    @property
    def name(self) -> str:
        return "financialdatasets"

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.aclose()

    # ── Internal helper ──────────────────────────────────────────────────────

    async def _get(self, path: str, params: dict) -> dict[str, Any]:
        """Safe GET — never raises, returns {} on non-200 or exception."""
        t0 = time.perf_counter()
        try:
            r  = await self._client.get(path, params=params)
            ms = int((time.perf_counter() - t0) * 1000)
            if r.status_code == 200:
                log.debug("FD %s %s → 200 (%dms)", path, params, ms)
                return r.json()
            log.warning(
                "FD %s %s → HTTP %s (%dms): %s",
                path, params, r.status_code, ms, r.text[:120],
            )
            return {}
        except Exception as exc:
            log.error("FD fetch error %s %s: %s", path, params, exc)
            return {}

    # ── Price ────────────────────────────────────────────────────────────────

    async def get_price_snapshot(self, ticker: str) -> dict[str, Any]:
        return await self._get("/prices/snapshot/", {"ticker": ticker})

    # ── Earnings ─────────────────────────────────────────────────────────────

    async def get_earnings(self, ticker: str) -> dict[str, Any]:
        return await self._get("/earnings/", {"ticker": ticker, "limit": 8})

    # ── Fundamentals TTM (3 parallel calls, normalized to flat dict) ─────────

    async def get_fundamentals_ttm(self, ticker: str) -> dict[str, Any]:
        """
        Fetches income statement, cash-flow statement, and balance sheet in
        parallel and returns a normalized flat dict.  On error returns
        {"ticker": ticker, "error": reason}.
        """
        try:
            inc_r, cf_r, bal_r = await asyncio.gather(
                self._client.get("/financials/income-statements/",
                                 params={"ticker": ticker, "period": "ttm", "limit": 1}),
                self._client.get("/financials/cash-flow-statements/",
                                 params={"ticker": ticker, "period": "ttm", "limit": 1}),
                self._client.get("/financials/balance-sheets/",
                                 params={"ticker": ticker, "period": "ttm", "limit": 1}),
            )
            for label, r in [("income", inc_r), ("cashflow", cf_r), ("balance", bal_r)]:
                if r.status_code not in (200, 201):
                    raise ValueError(f"FD {label} HTTP {r.status_code}")

            income   = inc_r.json().get("income_statements",   [{}])[0]
            cashflow = cf_r.json().get("cash_flow_statements", [{}])[0]
            balance  = bal_r.json().get("balance_sheets",      [{}])[0]

            rev    = income.get("revenue", 1) or 1
            net_inc= income.get("net_income", 0) or 0
            ebit   = income.get("operating_income", 0) or 0
            ebitda = income.get("ebitda", 0) or 0
            fcf    = cashflow.get("free_cash_flow", 0) or 0

            return {
                "ticker":          ticker.upper(),
                "revenue":         rev,
                "net_income":      net_inc,
                "ebit":            ebit,
                "ebitda":          ebitda,
                "free_cash_flow":  fcf,
                "ni_margin":       round(net_inc / rev * 100, 2),
                "ebit_margin":     round(ebit    / rev * 100, 2),
                "ebitda_margin":   round(ebitda  / rev * 100, 2),
                "fcf_margin":      round(fcf     / rev * 100, 2),
                "total_assets":    balance.get("total_assets"),
                "total_debt":      balance.get("total_debt"),
                "cash":            balance.get("cash_and_equivalents"),
                "raw_income":      income,
                "raw_cashflow":    cashflow,
                "raw_balance":     balance,
            }
        except Exception as exc:
            log.error("FD fundamentals_ttm error for %s: %s", ticker, exc)
            return {"ticker": ticker, "error": str(exc)}

    # ── Company / market datasets (pass-through) ─────────────────────────────

    async def get_company_facts(self, ticker: str) -> dict[str, Any]:
        return await self._get("/company/facts/", {"ticker": ticker})

    async def get_metrics_snapshot(self, ticker: str) -> dict[str, Any]:
        return await self._get("/financial-metrics/snapshot/", {"ticker": ticker})

    async def get_financials(
        self, ticker: str, period: str = "annual", limit: int = 10,
    ) -> dict[str, Any]:
        return await self._get("/financials/", {"ticker": ticker, "period": period, "limit": limit})

    async def get_metrics_history(
        self, ticker: str, period: str = "annual", limit: int = 10,
    ) -> dict[str, Any]:
        return await self._get(
            "/financial-metrics/", {"ticker": ticker, "period": period, "limit": limit},
        )

    async def get_institutional_ownership(
        self, ticker: str, limit: int = 15,
    ) -> dict[str, Any]:
        return await self._get("/institutional-ownership/", {"ticker": ticker, "limit": limit})

    async def get_analyst_estimates(
        self, ticker: str, period: str = "annual",
    ) -> dict[str, Any]:
        return await self._get("/analyst-estimates/", {"ticker": ticker, "period": period})

    async def get_insider_trades(
        self, ticker: str, limit: int = 30,
    ) -> list[dict[str, Any]]:
        raw = await self._get("/insider-trades/", {"ticker": ticker, "limit": limit})
        return raw.get("insider_trades", [])

    async def get_segmented_revenues(self, ticker: str) -> dict[str, Any]:
        return await self._get(
            "/financials/segmented-revenues/",
            {"ticker": ticker, "period": "annual", "limit": 5},
        )
