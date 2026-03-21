"""Peer company lookup — delegates to YahooFinanceProvider."""
import logging
from app.providers import YahooFinanceProvider

log = logging.getLogger(__name__)

# Module-level provider instance (stateless, reusable)
_provider = YahooFinanceProvider()


async def get_peer_symbols(sym: str) -> list[str]:
    """Get peer tickers from Yahoo Finance recommendations API."""
    return await _provider.get_peer_symbols(sym)


async def fetch_peer_metrics(peer_syms: list[str]) -> list[dict]:
    """Fetch metrics for all peers concurrently."""
    return await _provider.get_peer_metrics(peer_syms)
