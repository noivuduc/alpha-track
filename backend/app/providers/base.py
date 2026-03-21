"""
Abstract base class for market data providers.

All vendor-specific imports, field-name mappings, and API credentials live in
concrete subclasses.  DataService talks only to this interface.

Normalized schemas
------------------
PriceDict:
    ticker, price, change, change_pct, volume, market_cap, fetched_at

ProfileDict:
    ticker, name, sector, industry, description, website, employees,
    country, pe_ratio, fwd_pe, pb_ratio, dividend_yield, beta,
    52w_high, 52w_low, avg_volume

HistoryBar:
    ts (ISO str), open, high, low, close, volume

NewsItem:
    ticker, title, source, url, date (YYYY-MM-DD)

For datasets that are provider-specific (FD fundamentals, ownership, etc.)
the methods return the raw response dict — no normalization needed because
those datasets have no alternative source today.  When a second provider is
added for those data types a normalized schema will be introduced then.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, TypedDict


# ── Normalized TypedDicts ──────────────────────────────────────────────────────

class PriceDict(TypedDict, total=False):
    ticker: str
    price: float
    change: float
    change_pct: float
    volume: int
    market_cap: float
    fetched_at: str


class ProfileDict(TypedDict, total=False):
    ticker: str
    name: str
    sector: str
    industry: str
    description: str
    website: str
    employees: int | None
    country: str
    pe_ratio: float | None
    fwd_pe: float | None
    pb_ratio: float | None
    dividend_yield: float | None
    beta: float | None
    high_52w: float | None      # normalized: was "52w_high"
    low_52w: float | None       # normalized: was "52w_low"
    avg_volume: int | None


class HistoryBar(TypedDict):
    ts: str       # ISO datetime string
    open: float
    high: float
    low: float
    close: float
    volume: int


class NewsItem(TypedDict, total=False):
    ticker: str
    title: str
    source: str
    url: str
    date: str     # YYYY-MM-DD


# ── Abstract base ──────────────────────────────────────────────────────────────

class MarketDataProvider(ABC):
    """
    Pluggable market data source.

    Concrete providers implement only the methods they support; everything
    else raises NotImplementedError so DataService knows to fall back or fail.

    All public methods are async.  Sync vendor libraries (e.g. yfinance) must
    be wrapped with loop.run_in_executor() inside the concrete implementation.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier for logging / cache metadata (e.g. 'yfinance')."""
        ...

    # ── Prices ──────────────────────────────────────────────────────────────

    async def get_price(self, ticker: str) -> PriceDict:
        raise NotImplementedError(f"{self.name} does not support get_price")

    async def get_prices_bulk(self, tickers: list[str]) -> dict[str, PriceDict]:
        raise NotImplementedError(f"{self.name} does not support get_prices_bulk")

    # ── History ─────────────────────────────────────────────────────────────

    async def get_price_history(
        self, ticker: str, period: str = "1y", interval: str = "1d",
    ) -> list[HistoryBar]:
        raise NotImplementedError(f"{self.name} does not support get_price_history")

    # ── Company info ────────────────────────────────────────────────────────

    async def get_profile(self, ticker: str) -> ProfileDict:
        raise NotImplementedError(f"{self.name} does not support get_profile")

    async def get_news(self, ticker: str) -> list[NewsItem]:
        raise NotImplementedError(f"{self.name} does not support get_news")

    # ── Paid / fundamental datasets ─────────────────────────────────────────
    # These return provider-native dicts; a normalized schema will be added
    # when a second provider covers the same data type.

    async def get_price_snapshot(self, ticker: str) -> dict[str, Any]:
        raise NotImplementedError(f"{self.name} does not support get_price_snapshot")

    async def get_earnings(self, ticker: str) -> dict[str, Any]:
        raise NotImplementedError(f"{self.name} does not support get_earnings")

    async def get_fundamentals_ttm(self, ticker: str) -> dict[str, Any]:
        raise NotImplementedError(f"{self.name} does not support get_fundamentals_ttm")

    async def get_company_facts(self, ticker: str) -> dict[str, Any]:
        raise NotImplementedError(f"{self.name} does not support get_company_facts")

    async def get_metrics_snapshot(self, ticker: str) -> dict[str, Any]:
        raise NotImplementedError(f"{self.name} does not support get_metrics_snapshot")

    async def get_financials(
        self, ticker: str, period: str = "annual", limit: int = 10,
    ) -> dict[str, Any]:
        raise NotImplementedError(f"{self.name} does not support get_financials")

    async def get_metrics_history(
        self, ticker: str, period: str = "annual", limit: int = 10,
    ) -> dict[str, Any]:
        raise NotImplementedError(f"{self.name} does not support get_metrics_history")

    async def get_institutional_ownership(
        self, ticker: str, limit: int = 15,
    ) -> dict[str, Any]:
        raise NotImplementedError(
            f"{self.name} does not support get_institutional_ownership"
        )

    async def get_analyst_estimates(
        self, ticker: str, period: str = "annual",
    ) -> dict[str, Any]:
        raise NotImplementedError(f"{self.name} does not support get_analyst_estimates")

    async def get_insider_trades(
        self, ticker: str, limit: int = 30,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError(f"{self.name} does not support get_insider_trades")

    async def get_segmented_revenues(self, ticker: str) -> dict[str, Any]:
        raise NotImplementedError(f"{self.name} does not support get_segmented_revenues")
