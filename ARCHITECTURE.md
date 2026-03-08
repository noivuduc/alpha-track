# AlphaDesk — Full-Stack Architecture

## Database Selection Rationale

| Store | Why Chosen | Used For |
|-------|-----------|----------|
| **PostgreSQL 16** | ACID, rich queries, JSON support, battle-tested | Users, portfolios, positions, transactions, watchlist, subscriptions |
| **TimescaleDB** (PG extension) | Time-series partitioning, auto-compression, fast range queries | Price history, API usage logs, audit logs |
| **Redis 7** | Sub-ms in-memory, TTL-native, atomic ops for rate limiting | L1 cache, rate limit counters, JWT blacklist, session data |

### Why NOT other databases?
- **MongoDB** — Rejected. Schema-less doesn't help here; we want enforced types for financial data.
- **InfluxDB** — TimescaleDB gives us the same time-series performance but on Postgres, one less system.
- **DynamoDB** — Rejected. Complex querying patterns for portfolio analytics need SQL joins.
- **SQLite** — Rejected. Not suitable for concurrent multi-user access.

---

## Data Fetch Strategy (Cost Optimisation)

```
Request for market data
         │
         ▼
  ┌─────────────┐
  │ Redis (L1)  │  Hit → return immediately (sub-ms, FREE)
  │  TTL-based  │
  └──────┬──────┘
         │ Miss
         ▼
  ┌─────────────┐
  │ Postgres    │  Hit → repopulate Redis, return (~2ms, FREE)
  │ (L2 cache)  │
  └──────┬──────┘
         │ Miss
         ▼
  ┌──────────────────────────────────────┐
  │         Data Source Router           │
  │                                      │
  │  Prices / History / Profile          │
  │  ──────────────────────────          │
  │  yfinance (FREE, ~200ms)             │
  │                                      │
  │  Fundamentals / SEC / Insider /      │
  │  Earnings Estimates                  │
  │  ─────────────────────────────────── │
  │  financialdatasets.ai (PAID, ~300ms) │
  └──────────────────────────────────────┘
         │
         ▼
  Store in Redis + Postgres
  Return to client
```

### Cache TTLs
| Data Type | Redis TTL | Postgres TTL | Source |
|-----------|-----------|-------------|--------|
| Stock prices | 15 min | — | yfinance (free) |
| Price history (daily) | 1 hour | TimescaleDB permanent | yfinance (free) |
| Fundamentals / TTM | 24 hours | 24 hours | financialdatasets (paid) |
| Company profile | 7 days | — | yfinance (free) |
| Earnings data | 1 hour | — | financialdatasets (paid) |
| Insider trades | 4 hours | — | financialdatasets (paid) |
| SEC filings | 7 days | — | financialdatasets (paid) |

---

## API Architecture

### Authentication
- **JWT (HS256)** — short-lived access tokens (60 min) + long-lived refresh tokens (30 days)
- **API Key** — programmatic access via `X-API-Key` header (personal key per user)
- **Token blacklist** — logout/rotation stored in Redis with TTL matching token expiry
- **bcrypt** — password hashing (cost factor 12)

### Rate Limiting (Redis sliding window)
| Tier | Req/min | Req/day | Portfolios | Positions | AI calls/day |
|------|---------|---------|------------|-----------|-------------|
| Free | 20 | 500 | 1 | 5 | 0 |
| Pro ($29/mo) | 100 | 5,000 | 10 | 100 | 50 |
| Fund ($99/mo) | 500 | 50,000 | Unlimited | Unlimited | Unlimited |

### Validation
- All request bodies validated with **Pydantic v2** (strict mode)
- Password strength enforcement (uppercase + digit required)
- Ticker symbols uppercased and stripped automatically
- Decimal precision enforced for financial values (6 decimal places)
- Check constraints in database as second layer

---

## Project Structure

```
alphadesk/
├── docker-compose.yml          # PostgreSQL + TimescaleDB + Redis + API + Frontend
├── backend/
│   ├── main.py                 # FastAPI app, middleware, lifespan
│   ├── config.py               # Pydantic Settings (env-based)
│   ├── database.py             # PG engine + Redis pool + Cache helper
│   ├── models.py               # SQLAlchemy ORM (all tables)
│   ├── schemas.py              # Pydantic request/response schemas
│   ├── middleware.py           # JWT auth, rate limiting, quota checks
│   ├── sql/init.sql            # DB schema + TimescaleDB hypertables
│   ├── services/
│   │   └── data_service.py     # Smart data fetcher (cache → yfinance → paid API)
│   ├── routers/
│   │   ├── auth.py             # Register, login, refresh, logout, API keys
│   │   ├── portfolio.py        # Portfolios, positions, transactions, watchlist
│   │   ├── market.py           # Prices, fundamentals, history, insider, earnings
│   │   └── admin.py            # Usage stats, cost monitoring
│   └── requirements.txt
└── frontend/
    └── src/
        └── lib/
            └── api.ts          # Typed API client with auto token-refresh
```

---

## Key Design Decisions

1. **One DataService class** — all external data goes through `data_service.py`. Routers never call yfinance or financialdatasets directly. Makes it easy to swap providers.

2. **Two-level cache** — Redis for speed, Postgres for durability. Redis restart doesn't blow away our cached fundamentals.

3. **TimescaleDB for time-series** — price history partitioned by week, auto-compressed after 30 days. Same connection string as main Postgres.

4. **Pydantic + DB constraints** — validation at both app layer and DB layer. Financial data must not corrupt silently.

5. **Audit log as hypertable** — every action timestamped in a partitioned table. Fund managers need this for compliance.

6. **Cost tracking built-in** — every `source` field in ApiUsage tells us if we hit cache or paid API. Admin can see estimated cost in real-time.

---

## Next Steps

- [ ] Alembic migrations (replace create_all)
- [ ] Stripe integration (Pro/Fund subscription billing)
- [ ] Claude API integration (AI Portfolio Doctor, Thesis Builder)
- [ ] WebSocket endpoint for real-time price streaming
- [ ] Email verification flow
- [ ] Background job (APScheduler) to refresh cache for active users' holdings
- [ ] Export to PDF/CSV (Pro+ feature)
