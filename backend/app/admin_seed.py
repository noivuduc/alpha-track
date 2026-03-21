"""
Idempotent seed for admin defaults.
Called from lifespan on every startup — safe to re-run (uses INSERT ... ON CONFLICT DO NOTHING).
"""
from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import AsyncSessionLocal
from app.models import SubscriptionTierConfig, DataProvider

log = logging.getLogger(__name__)

_DEFAULT_TIERS = [
    {
        "name":           "free",
        "display_name":   "Free",
        "max_portfolios": 1,
        "max_positions":  5,
        "rpm":            20,
        "rpd":            500,
        "ai_per_day":     0,
        "price_usd":      Decimal("0.00"),
    },
    {
        "name":           "pro",
        "display_name":   "Pro",
        "max_portfolios": 10,
        "max_positions":  100,
        "rpm":            100,
        "rpd":            5000,
        "ai_per_day":     50,
        "price_usd":      Decimal("29.00"),
    },
    {
        "name":           "fund",
        "display_name":   "Fund",
        "max_portfolios": 999,
        "max_positions":  999,
        "rpm":            500,
        "rpd":            50000,
        "ai_per_day":     999,
        "price_usd":      Decimal("99.00"),
    },
]

_DEFAULT_PROVIDERS = [
    {
        "name":              "yfinance",
        "display_name":      "Yahoo Finance (yfinance)",
        "enabled":           True,
        "priority":          1,
        "rate_limit_rpm":    60,
        "cost_per_call_usd": Decimal("0.000000"),
        "notes":             "Free provider. Prices, history, profiles, news.",
    },
    {
        "name":              "financialdatasets",
        "display_name":      "FinancialDatasets.ai",
        "enabled":           True,
        "priority":          2,
        "rate_limit_rpm":    100,
        "cost_per_call_usd": Decimal("0.001000"),
        "notes":             "Paid provider. Fundamentals, metrics, insider trades, estimates.",
    },
    {
        "name":              "polygon",
        "display_name":      "Polygon.io",
        "enabled":           False,
        "priority":          3,
        "rate_limit_rpm":    1000,
        "cost_per_call_usd": Decimal("0.000100"),
        "notes":             "Not yet integrated. Placeholder for future use.",
    },
]


async def seed_admin_defaults() -> None:
    """Insert default tier configs + providers if they don't exist. Idempotent."""
    async with AsyncSessionLocal() as db:
        async with db.begin():
            # Tiers
            for tier in _DEFAULT_TIERS:
                stmt = (
                    pg_insert(SubscriptionTierConfig)
                    .values(**tier)
                    .on_conflict_do_nothing(index_elements=["name"])
                )
                await db.execute(stmt)

            # Providers — fix walrus assign issue
            for prov in _DEFAULT_PROVIDERS:
                stmt = (
                    pg_insert(DataProvider)
                    .values(**prov)
                    .on_conflict_do_nothing(index_elements=["name"])
                )
                await db.execute(stmt)

    log.info("admin_seed: tier configs + providers seeded")
