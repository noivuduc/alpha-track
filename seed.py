#!/usr/bin/env python3
"""
AlphaTrack — Database Seed Script
Creates demo accounts (free/pro/fund/admin) with realistic portfolio data.

Usage:
    cd /path/to/alphatrack
    backend/.venv/bin/python seed.py
"""
import asyncio
import random
from datetime import datetime, timedelta, timezone, date
from uuid import uuid4

import asyncpg
import bcrypt

random.seed(42)

DB_URL = "postgresql://alphatrack:changeme@localhost:5432/alphatrack"

# ─── Historical monthly closing prices ───────────────────────────────────────
# Realistic approximate monthly close prices (YYYY-MM → price).
# Sources: actual market data for each ticker.
PRICE_TABLE: dict[str, dict[str, float]] = {
    "NVDA": {
        "2023-01": 143.15, "2023-02": 192.12, "2023-03": 277.77, "2023-04": 280.00,
        "2023-05": 378.34, "2023-06": 423.02, "2023-07": 455.72, "2023-08": 493.55,
        "2023-09": 434.99, "2023-10": 461.43, "2023-11": 467.65, "2023-12": 495.22,
        "2024-01": 613.28, "2024-02": 788.17, "2024-03": 903.56, "2024-04": 762.00,
        "2024-05": 1064.69,"2024-06": 123.54, "2024-07": 117.93, "2024-08": 116.00,
        "2024-09": 116.78, "2024-10": 140.47, "2024-11": 135.57, "2024-12": 137.96,
        "2025-01": 124.92, "2025-02": 128.30, "2025-03": 109.02, "2025-04": 93.50,
        "2025-05": 112.44, "2025-06": 131.48, "2025-07": 143.21, "2025-08": 138.76,
        "2025-09": 126.30, "2025-10": 140.59, "2025-11": 151.20, "2025-12": 160.25,
        "2026-01": 148.73, "2026-02": 131.45, "2026-03": 108.22,
    },
    "MSFT": {
        "2023-01": 242.58, "2023-02": 252.75, "2023-03": 288.54, "2023-04": 307.26,
        "2023-05": 328.39, "2023-06": 340.54, "2023-07": 359.49, "2023-08": 328.39,
        "2023-09": 315.75, "2023-10": 340.43, "2023-11": 378.85, "2023-12": 374.51,
        "2024-01": 397.12, "2024-02": 415.03, "2024-03": 420.53, "2024-04": 391.22,
        "2024-05": 430.16, "2024-06": 446.36, "2024-07": 440.82, "2024-08": 431.23,
        "2024-09": 436.60, "2024-10": 430.53, "2024-11": 432.53, "2024-12": 441.45,
        "2025-01": 422.83, "2025-02": 385.40, "2025-03": 387.76, "2025-04": 371.58,
        "2025-05": 403.24, "2025-06": 421.45, "2025-07": 440.23, "2025-08": 451.88,
        "2025-09": 437.56, "2025-10": 455.23, "2025-11": 463.88, "2025-12": 459.72,
        "2026-01": 442.30, "2026-02": 418.55, "2026-03": 393.40,
    },
    "AAPL": {
        "2023-01": 144.29, "2023-02": 147.92, "2023-03": 160.77, "2023-04": 169.68,
        "2023-05": 177.25, "2023-06": 189.59, "2023-07": 192.58, "2023-08": 178.19,
        "2023-09": 171.21, "2023-10": 170.77, "2023-11": 189.95, "2023-12": 192.53,
        "2024-01": 184.40, "2024-02": 181.42, "2024-03": 170.73, "2024-04": 170.73,
        "2024-05": 192.35, "2024-06": 210.62, "2024-07": 218.54, "2024-08": 226.84,
        "2024-09": 233.00, "2024-10": 230.76, "2024-11": 237.33, "2024-12": 239.59,
        "2025-01": 229.00, "2025-02": 241.84, "2025-03": 220.73, "2025-04": 209.28,
        "2025-05": 213.49, "2025-06": 216.98, "2025-07": 224.38, "2025-08": 228.87,
        "2025-09": 220.45, "2025-10": 231.72, "2025-11": 238.65, "2025-12": 245.50,
        "2026-01": 235.40, "2026-02": 228.15, "2026-03": 220.89,
    },
    "TSLA": {
        "2023-01": 123.18, "2023-02": 202.77, "2023-03": 207.46, "2023-04": 160.19,
        "2023-05": 203.93, "2023-06": 261.77, "2023-07": 269.81, "2023-08": 245.01,
        "2023-09": 251.21, "2023-10": 200.84, "2023-11": 240.08, "2023-12": 248.48,
        "2024-01": 187.29, "2024-02": 201.88, "2024-03": 175.79, "2024-04": 147.05,
        "2024-05": 176.75, "2024-06": 197.88, "2024-07": 232.12, "2024-08": 214.14,
        "2024-09": 249.95, "2024-10": 261.63, "2024-11": 352.56, "2024-12": 403.84,
        "2025-01": 388.73, "2025-02": 288.14, "2025-03": 278.65, "2025-04": 253.10,
        "2025-05": 342.21, "2025-06": 355.48, "2025-07": 376.92, "2025-08": 362.40,
        "2025-09": 341.88, "2025-10": 380.55, "2025-11": 402.33, "2025-12": 415.20,
        "2026-01": 378.45, "2026-02": 318.22, "2026-03": 285.73,
    },
}


def price_on(ticker: str, dt: datetime) -> float:
    """Interpolate price for a given date from the monthly price table."""
    prices = PRICE_TABLE.get(ticker, {})
    if not prices:
        return 100.0

    key = dt.strftime("%Y-%m")

    # Exact month match
    if key in prices:
        return prices[key]

    # Find bracketing months and interpolate
    all_months = sorted(prices.keys())
    before = [m for m in all_months if m <= key]
    after  = [m for m in all_months if m >  key]

    if before and after:
        m0, m1 = before[-1], after[0]
        p0, p1 = prices[m0], prices[m1]
        # Linear interpolation by day fraction
        d0 = datetime.strptime(m0 + "-15", "%Y-%m-%d").replace(tzinfo=timezone.utc)
        d1 = datetime.strptime(m1 + "-15", "%Y-%m-%d").replace(tzinfo=timezone.utc)
        frac = (dt - d0).total_seconds() / (d1 - d0).total_seconds()
        return round(p0 + frac * (p1 - p0), 2)
    elif before:
        return prices[before[-1]]
    elif after:
        return prices[after[0]]
    return 100.0


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt(rounds=12)).decode()


# ─── Demo accounts ────────────────────────────────────────────────────────────
USERS = [
    {"email": "admin@alphatrack.com", "password": "Admin123!",  "full_name": "AlphaTrack Admin", "tier": "fund",  "is_verified": True, "is_admin": True},
    {"email": "free@demo.com",       "password": "Demo1234",   "full_name": "Alex Freeman",     "tier": "free",  "is_verified": True},
    {"email": "pro@demo.com",        "password": "Demo1234",   "full_name": "Jordan Pro",       "tier": "pro",   "is_verified": True},
    {"email": "fund@demo.com",       "password": "Demo1234",   "full_name": "Morgan Fund",      "tier": "fund",  "is_verified": True},
]

# Each position: how many shares and how long ago they were bought
POSITIONS_CONFIG = {
    "free": [
        {"ticker": "NVDA", "shares": 10,  "months_range": (8,  18)},
        {"ticker": "MSFT", "shares": 20,  "months_range": (4,  14)},
        {"ticker": "AAPL", "shares": 25,  "months_range": (6,  20)},
        {"ticker": "TSLA", "shares": 15,  "months_range": (3,  12)},
    ],
    "pro": [
        {"ticker": "NVDA", "shares": 55,  "months_range": (14, 26)},
        {"ticker": "MSFT", "shares": 85,  "months_range": (8,  20)},
        {"ticker": "AAPL", "shares": 120, "months_range": (5,  22)},
        {"ticker": "TSLA", "shares": 45,  "months_range": (6,  18)},
    ],
    "fund": [
        {"ticker": "NVDA", "shares": 260, "months_range": (20, 32)},
        {"ticker": "MSFT", "shares": 380, "months_range": (14, 30)},
        {"ticker": "AAPL", "shares": 550, "months_range": (8,  26)},
        {"ticker": "TSLA", "shares": 180, "months_range": (5,  18)},
    ],
}


def pick_buy_date(months_range: tuple) -> datetime:
    low, high = months_range
    days_ago = random.uniform(low * 30.44, high * 30.44)
    return datetime.now(timezone.utc) - timedelta(days=days_ago)


async def seed():
    print(f"\n{'='*58}")
    print("  AlphaTrack — Database Seed")
    print(f"{'='*58}\n")

    conn = await asyncpg.connect(DB_URL)

    try:
        for u in USERS:
            email = u["email"]
            tier  = u["tier"]

            existing = await conn.fetchrow("SELECT id FROM alphatrack_users WHERE email=$1", email)

            if existing:
                user_id = str(existing["id"])
                print(f"→ {email} exists — checking portfolio…")
                port = await conn.fetchrow(
                    "SELECT id FROM alphatrack_portfolios WHERE user_id=$1", user_id
                )
                if port:
                    cnt = await conn.fetchval(
                        "SELECT COUNT(*) FROM alphatrack_positions WHERE portfolio_id=$1", port["id"]
                    )
                    if cnt > 0:
                        print(f"  Already has {cnt} positions, skipping.\n")
                        continue
                    portfolio_id = str(port["id"])
                else:
                    portfolio_id = None
            else:
                user_id = str(uuid4())
                await conn.execute(
                    """
                    INSERT INTO alphatrack_users
                      (id, email, hashed_password, full_name, tier, is_active, is_verified, is_admin)
                    VALUES ($1, $2, $3, $4, $5::alphatrack_subscriptiontier, TRUE, $6, $7)
                    """,
                    user_id, email, hash_password(u["password"]),
                    u["full_name"], tier, u["is_verified"], u.get("is_admin", False),
                )
                print(f"✓ Created [{tier:4}]  {email}  ({u['full_name']})")
                portfolio_id = None

            # ── Portfolio ──────────────────────────────────────
            if portfolio_id is None:
                portfolio_id = str(uuid4())
                first = u["full_name"].split()[0]
                await conn.execute(
                    """
                    INSERT INTO alphatrack_portfolios
                      (id, user_id, name, description, currency, is_default)
                    VALUES ($1, $2, $3, $4, 'USD', TRUE)
                    """,
                    portfolio_id, user_id,
                    f"{first}'s AlphaPicks",
                    "Demo portfolio — NVDA · MSFT · AAPL · TSLA",
                )

            # ── Positions ──────────────────────────────────────
            pos_configs = POSITIONS_CONFIG.get(tier, POSITIONS_CONFIG["free"])

            for cfg in pos_configs:
                ticker   = cfg["ticker"]
                shares   = float(cfg["shares"])
                buy_date = pick_buy_date(cfg["months_range"])
                cost     = price_on(ticker, buy_date)

                pos_id = str(uuid4())
                txn_id = str(uuid4())

                await conn.execute(
                    """
                    INSERT INTO alphatrack_positions
                      (id, portfolio_id, ticker, shares, cost_basis, opened_at, notes)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    pos_id, portfolio_id, ticker, shares, cost, buy_date,
                    f"Demo: {shares:.0f} sh @ ${cost:.2f}",
                )
                await conn.execute(
                    """
                    INSERT INTO alphatrack_transactions
                      (id, portfolio_id, ticker, side, shares, price, fees, traded_at, notes)
                    VALUES ($1, $2, $3, 'buy'::alphatrack_order_side, $4, $5, 0, $6, 'Seeded position')
                    """,
                    txn_id, portfolio_id, ticker, shares, cost, buy_date,
                )

                print(f"    {ticker}  {shares:>5.0f} sh  @  ${cost:>8.2f}  "
                      f"({buy_date.strftime('%Y-%m-%d')})")

            print()

    finally:
        await conn.close()

    print(f"{'='*58}")
    print("✅  Seed complete!\n")
    print(f"  {'TIER':<6}  {'EMAIL':<32}  PASSWORD")
    print(f"  {'─'*54}")
    for u in USERS:
        print(f"  {u['tier']:<6}  {u['email']:<32}  {u['password']}")
    print()
    print("  Start stack:  ./start.sh")
    print("  Frontend:     http://localhost:3000")
    print("  API docs:     http://localhost:8000/docs\n")


if __name__ == "__main__":
    asyncio.run(seed())
