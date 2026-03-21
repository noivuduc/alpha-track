"""
Market data provider abstraction layer.

Importing from here gives you everything needed to register and use providers.
"""
from .base import MarketDataProvider, PriceDict, ProfileDict, HistoryBar, NewsItem
from .yahoo_finance import YahooFinanceProvider
from .financial_datasets import FinancialDatasetsProvider

__all__ = [
    "MarketDataProvider",
    "PriceDict",
    "ProfileDict",
    "HistoryBar",
    "NewsItem",
    "YahooFinanceProvider",
    "FinancialDatasetsProvider",
]
