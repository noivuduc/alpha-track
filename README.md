# AlphaTrack

**Self-hosted portfolio analytics with institutional-grade metrics, AI insights, and a background data pipeline.**

AlphaTrack is an open-source, full-stack portfolio tracker built for developers and quantitative-minded investors. It computes Sharpe ratio, drawdown, sector attribution, and scenario simulations on your own data — backed by a production-grade FastAPI + TimescaleDB backend and a real async data pipeline. No SaaS, no data sharing, your portfolio stays on your server.

![AlphaTrack dashboard — portfolio overview](imgs/screenshot-dashboard-overview.png)

*Portfolio overview: health score, benchmarks vs SPY/QQQ, return heatmap, positions, and news.*

---

## Why AlphaTrack

Most portfolio trackers are either too simple (pie chart + total return) or too expensive (Bloomberg, FactSet). AlphaTrack sits in the middle: institutional-grade analytics running on hardware you control, with open data sources and a codebase you can read and extend.

It is not a trading platform and does not connect to your broker. It is a **research and analysis layer** for portfolios you manage yourself.

---

## Key Features

- **Portfolio tracking** — positions, transactions, cost basis, unrealised P&L
- **Performance analytics** — time-weighted returns, rolling windows (1W/1M/3M/YTD/1Y), benchmark comparison vs SPY/QQQ
- **Risk metrics** — Sharpe, Sortino, Calmar, Beta, Alpha, Max Drawdown, Win Rate, volatility
- **Scenario simulator** — model rebalances and "what-if" allocations before executing them
- **Fundamentals** — revenue, margins, P/E, EV/EBITDA, debt ratios per ticker
- **AI insights** — Claude/GPT-powered portfolio analysis (optional, requires API key)
- **Watchlist** — track tickers outside your portfolio with alert prices
- **Background pipeline** — ARQ worker keeps prices, fundamentals, and news current automatically
- **Admin dashboard** — user management, tier configuration, data provider cost tracking
- **Multi-tier access control** — Free / Pro / Fund tiers with configurable rate limits and quotas

### Production-ready vs. experimental

| Feature | Status |
|---|---|
| Portfolio tracking, P&L, analytics | Production-ready |
| Risk metrics engine | Production-ready |
| Scenario simulator | Production-ready |
| Background data pipeline | Production-ready |
| Authentication (JWT + API keys) | Production-ready |
| Rate limiting and tier enforcement | Production-ready |
| AI insights (Claude / GPT) | Working, optional |
| WebSocket real-time prices | Experimental / incomplete |
| Stripe billing | Scaffolded, not implemented |
| Email verification | Scaffolded, not implemented |

---

## Screenshots

### Portfolio dashboard

| Overview | Holdings | Risk |
| :---: | :---: | :---: |
| ![Dashboard overview](imgs/screenshot-dashboard-overview.png) | ![Holdings](imgs/screenshot-dashboard-holdings.png) | ![Risk analytics](imgs/screenshot-dashboard-risk.png) |

### Scenario simulator

![Scenario simulator — before/after metrics and sector exposure](imgs/screenshot-dashboard-simulator.png)

### Equity research (example: MSFT)

| Overview | Financials | Valuation |
| :---: | :---: | :---: |
| ![MSFT overview](imgs/screenshot-research-msft-overview.png) | ![MSFT financials](imgs/screenshot-research-msft-financials.png) | ![MSFT valuation](imgs/screenshot-research-msft-valuation.png) |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 15, React 19, TypeScript, Tailwind CSS, Recharts |
| Backend | FastAPI, SQLAlchemy 2.0 (async), Pydantic v2 |
| Database | PostgreSQL 16 + TimescaleDB |
| Cache | Redis 7 |
| Task queue | ARQ (async Redis queue) |
| Free market data | yfinance |
| Paid market data | financialdatasets.ai (optional) |
| AI | Anthropic Claude API, OpenAI (optional) |
| Auth | JWT (HS256) + API keys, bcrypt |
| Migrations | Alembic |
| Deployment | Docker Compose |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  Next.js Frontend (:3000)                                       │
│  Auth → Portfolio → Analytics → Simulator → Research           │
└───────────────────────────┬─────────────────────────────────────┘
                            │ HTTP/REST
┌───────────────────────────▼─────────────────────────────────────┐
│  FastAPI Backend (:8000)                                        │
│  JWT auth · rate limiting · request logging · tier enforcement  │
│                                                                 │
│  Routers:  auth, portfolio, market, research, admin, search     │
│  Services: DataService, AnalyticsEngine, SimulationService      │
│                                                                 │
│  Cache strategy:                                                │
│  Redis L1 (15 min TTL) → Postgres L2 → yfinance / paid API     │
└──────┬──────────────────┬──────────────────┬────────────────────┘
       │                  │                  │
┌──────▼──────┐  ┌────────▼─────┐  ┌────────▼────────────────────┐
│ PostgreSQL  │  │    Redis     │  │  ARQ Pipeline Worker        │
│ TimescaleDB │  │  Cache +     │  │  Price · fundamentals ·     │
│ 17 tables   │  │  rate limit  │  │  earnings · news            │
└─────────────┘  └──────────────┘  └─────────────────────────────┘
```

All tables use the `alphatrack_` prefix. See [ARCHITECTURE.md](ARCHITECTURE.md) for design rationale.

---

## Prerequisites

- [Docker](https://www.docker.com/products/docker-desktop) and Docker Compose
- Python 3.11+
- Node.js 18+

> **TimescaleDB required.** The project uses TimescaleDB for the price history table. The Docker image includes it automatically. Standard PostgreSQL without the extension is not supported.

---

## Quick Start

### 1. Clone

```bash
git clone https://github.com/YOUR_USERNAME/alphatrack.git
cd alphatrack
```

### 2. Configure environment

```bash
# Root — Docker Compose DB credentials
cp .env.example .env

# Backend — API keys and app config
cp backend/.env.example backend/.env
# Edit backend/.env and set SECRET_KEY plus any optional API keys
```

### 3. Start databases

```bash
docker compose up -d postgres redis
```

### 4. Run migrations

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export DATABASE_URL="postgresql+asyncpg://alphatrack:changeme@localhost:5432/alphatrack"
alembic upgrade head
```

> **Docker path:** If you used `docker compose up -d postgres redis`, the `init.sql` bootstrap already ran. In that case, stamp instead of upgrade:
> ```bash
> alembic stamp head
> ```

### 5. Start the backend

```bash
export DATABASE_URL="postgresql+asyncpg://alphatrack:changeme@localhost:5432/alphatrack"
export REDIS_URL="redis://:changeme@localhost:6379/0"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 6. Seed demo data (optional)

```bash
cd ..
backend/.venv/bin/python seed.py
```

| Email | Password | Tier |
|---|---|---|
| admin@alphatrack.com | Admin123! | Fund (admin) |
| free@demo.com | Demo1234 | Free |
| pro@demo.com | Demo1234 | Pro |
| fund@demo.com | Demo1234 | Fund |

### 7. Start the frontend

```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL="http://localhost:8000/api/v1" npm run dev
```

### Or: start everything at once

```bash
./start.sh
```

---

## Full Docker Stack

```bash
docker compose up -d
```

| URL | Service |
|---|---|
| http://localhost:3000 | Frontend |
| http://localhost:8000 | Backend API |
| http://localhost:8000/docs | Swagger UI |
| http://localhost:9000 | Pipeline task dashboard |

---

## Environment Variables

### Root `.env` (Docker Compose)

```bash
POSTGRES_USER=alphatrack
POSTGRES_PASSWORD=changeme        # change in production
POSTGRES_DB=alphatrack
REDIS_PASSWORD=changeme           # change in production
```

### `backend/.env`

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | **Yes** | JWT signing key — generate with: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | **Yes** | `postgresql+asyncpg://alphatrack:changeme@localhost:5432/alphatrack` |
| `REDIS_URL` | **Yes** | `redis://:changeme@localhost:6379/0` |
| `ENVIRONMENT` | No | `development` (default) or `production` |
| `PAID_PROVIDER_API_KEY` | No | [financialdatasets.ai](https://financialdatasets.ai) key — fundamentals, SEC filings |
| `ANTHROPIC_API_KEY` | No | Claude API key — AI insights |
| `OPENAI_API_KEY` | No | OpenAI key — AI insights fallback |
| `TAVILY_API_KEY` | No | Tavily key — news search |

Most features work with only the required variables. Fundamentals and AI insights require the optional paid keys.

---

## Build and Test

```bash
# Backend tests
cd backend
source .venv/bin/activate
pytest tests/ -v

# Frontend build check
cd frontend
npm run build
npm run lint

# TypeScript check
npx tsc --noEmit
```

---

## Project Structure

```
alphatrack/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point, Alembic startup, middleware
│   │   ├── models.py            # SQLAlchemy ORM (17 tables, alphatrack_ prefix)
│   │   ├── schemas.py           # Pydantic request/response schemas
│   │   ├── config.py            # Settings (env-based, Pydantic Settings)
│   │   ├── database.py          # PostgreSQL + Redis connection setup
│   │   ├── middleware.py        # JWT auth, rate limiting
│   │   ├── routers/             # API endpoint handlers
│   │   │   ├── auth.py          # Register, login, token refresh, API keys
│   │   │   ├── portfolio.py     # Portfolios, positions, transactions
│   │   │   ├── market.py        # Prices, history, fundamentals
│   │   │   ├── research.py      # AI insights
│   │   │   ├── admin.py         # User management, tier config
│   │   │   └── search.py        # Ticker search
│   │   ├── services/            # Business logic
│   │   │   ├── data_service.py  # Cache-first data fetcher (Redis → Postgres → API)
│   │   │   ├── analytics.py     # Portfolio analytics engine
│   │   │   └── simulation_service.py
│   │   └── providers/           # Data source adapters
│   │       ├── yahoo_finance.py # Free: prices, history, profiles
│   │       └── financial_datasets.py  # Paid: fundamentals, SEC filings
│   ├── alembic/
│   │   └── versions/            # Migration history
│   ├── pipeline/                # ARQ background worker tasks
│   ├── sql/init.sql             # Docker bootstrap (extensions + TimescaleDB hypertable)
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── app/                 # Next.js App Router pages
│       ├── components/
│       │   └── dashboard/       # Overview, Holdings, Risk, Fundamentals tabs
│       └── lib/
│           ├── api.ts           # Typed API client with auto token-refresh
│           └── portfolio-math.ts
├── docker-compose.yml
├── seed.py                      # Demo data seeding
├── start.sh                     # Local dev launcher
└── ARCHITECTURE.md
```

---

## Data Sources

| Source | Cost | Data |
|---|---|---|
| yfinance | Free | Prices, OHLC history, company profiles |
| financialdatasets.ai | Paid (free tier available) | Fundamentals, SEC filings, insider trades, earnings |
| Anthropic Claude | Paid | AI insights (optional) |
| OpenAI | Paid | AI insights fallback (optional) |
| Tavily | Paid (free tier available) | News search (optional) |

---

## Limitations

- **No broker integration.** Positions must be entered manually.
- **No real-time prices.** Prices refresh on a background schedule, not live.
- **TimescaleDB required.** The price history table uses TimescaleDB hypertables; standard PostgreSQL is not supported.
- **Alembic manages schema.** Do not run `create_all` in production — migrations are the source of truth.
- **Stripe billing scaffolded only.** Tier upgrades require manual admin changes until billing is implemented.
- **Email verification scaffolded only.** The `is_verified` flag exists but no email is sent on registration.

---

## Roadmap

- [ ] WebSocket real-time price updates
- [ ] Stripe billing for Pro/Fund tier upgrades
- [ ] Email verification on registration
- [ ] CSV / broker import
- [ ] Expanded AI portfolio analysis
- [ ] Watchlist tab UI (API already built)
- [ ] Earnings calendar view
- [ ] Insider transaction tracker (endpoint exists)
- [ ] Mobile-responsive improvements

---

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) first.

```bash
# Fork, then:
git checkout -b feature/your-feature
# make changes, add tests
git push origin feature/your-feature
# open a pull request
```

Good first issues are labelled [`good first issue`](../../issues?q=label%3A%22good+first+issue%22).

---

## License

[MIT](LICENSE)

---

## Acknowledgements

- [yfinance](https://github.com/ranaroussi/yfinance) — free market data
- [financialdatasets.ai](https://financialdatasets.ai) — fundamentals data
- [TimescaleDB](https://www.timescale.com) — time-series PostgreSQL extension
- [FastAPI](https://fastapi.tiangolo.com) — Python web framework
- [Recharts](https://recharts.org) — React charting library
