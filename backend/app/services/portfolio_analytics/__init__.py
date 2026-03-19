"""
portfolio_analytics — modular portfolio analytics engine.

Public API re-exported here for convenient importing:

    from app.services.portfolio_analytics import compute_engine
    from app.services.portfolio_analytics import align_series, build_price_lookup
    from app.services.portfolio_analytics import compute_position_summary
"""

# Core entry points used by the router
from .engine import (
    compute_engine,
    build_portfolio_returns,
)
from .portfolio_reconstruction import align_series, build_price_lookup
from .positions import compute_position_summary

# Constants (commonly referenced externally)
from .constants import RF_ANNUAL, RF_DAILY, TRADING_YR, MONTHS

__all__ = [
    # Engine
    "compute_engine",
    "build_portfolio_returns",
    # Reconstruction
    "align_series",
    "build_price_lookup",
    # Position summary (used directly by router)
    "compute_position_summary",
    # Constants
    "RF_ANNUAL",
    "RF_DAILY",
    "TRADING_YR",
    "MONTHS",
]
