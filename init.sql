-- ═══════════════════════════════════════════════════════════════════
-- AlphaDesk Database Schema
-- PostgreSQL 16 + TimescaleDB
-- ═══════════════════════════════════════════════════════════════════

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "timescaledb";
CREATE EXTENSION IF NOT EXISTS "pg_trgm"; -- for ticker search

-- ── Subscription tiers ───────────────────────────────────────────
CREATE TYPE subscription_tier AS ENUM ('free', 'pro', 'fund');
CREATE TYPE order_side AS ENUM ('buy', 'sell');

-- ── Users ────────────────────────────────────────────────────────
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email           VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name       VARCHAR(255),
    tier            subscription_tier NOT NULL DEFAULT 'free',
    api_key         VARCHAR(64) UNIQUE,                -- personal API key for programmatic access
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    is_verified     BOOLEAN NOT NULL DEFAULT FALSE,
    stripe_customer_id VARCHAR(255),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_users_email   ON users(email);
CREATE INDEX idx_users_api_key ON users(api_key) WHERE api_key IS NOT NULL;

-- ── Portfolios (one user can have multiple) ──────────────────────
CREATE TABLE portfolios (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        VARCHAR(100) NOT NULL,
    description TEXT,
    currency    CHAR(3) NOT NULL DEFAULT 'USD',
    is_default  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_portfolios_user ON portfolios(user_id);

-- ── Positions ─────────────────────────────────────────────────────
CREATE TABLE positions (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    portfolio_id UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    ticker       VARCHAR(20) NOT NULL,
    shares       NUMERIC(18,6) NOT NULL,
    cost_basis   NUMERIC(18,6) NOT NULL,     -- average cost per share
    notes        TEXT,
    opened_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at    TIMESTAMPTZ,                 -- NULL = open position
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT positive_shares CHECK (shares > 0),
    CONSTRAINT positive_cost   CHECK (cost_basis > 0)
);
CREATE INDEX idx_positions_portfolio ON positions(portfolio_id);
CREATE INDEX idx_positions_ticker    ON positions(ticker);

-- ── Transaction ledger (audit trail of every trade) ──────────────
CREATE TABLE transactions (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    portfolio_id UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    ticker       VARCHAR(20) NOT NULL,
    side         order_side NOT NULL,
    shares       NUMERIC(18,6) NOT NULL,
    price        NUMERIC(18,6) NOT NULL,
    fees         NUMERIC(18,6) NOT NULL DEFAULT 0,
    traded_at    TIMESTAMPTZ NOT NULL,
    notes        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_txn_portfolio ON transactions(portfolio_id);
CREATE INDEX idx_txn_ticker    ON transactions(ticker);
CREATE INDEX idx_txn_date      ON transactions(traded_at DESC);

-- ── Watchlist ─────────────────────────────────────────────────────
CREATE TABLE watchlist (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ticker         VARCHAR(20) NOT NULL,
    quant_rating   NUMERIC(3,2),
    sector         VARCHAR(100),
    announce_date  DATE,
    notes          TEXT,
    alert_price    NUMERIC(18,6),            -- trigger alert when price hits this
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, ticker)
);
CREATE INDEX idx_watchlist_user ON watchlist(user_id);

-- ── Cache: Fundamentals (24h TTL enforced in app layer) ──────────
-- PostgreSQL as L2 cache — Redis is L1 (in-memory, faster)
CREATE TABLE cache_fundamentals (
    ticker         VARCHAR(20) PRIMARY KEY,
    source         VARCHAR(50) NOT NULL,     -- 'financialdatasets' | 'yfinance'
    data           JSONB NOT NULL,
    period         VARCHAR(20) NOT NULL DEFAULT 'ttm',
    fetched_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at     TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '24 hours'
);
CREATE INDEX idx_cache_fund_expires ON cache_fundamentals(expires_at);

-- ── Cache: Stock prices (15-min TTL in Redis, here for cold start) 
CREATE TABLE cache_prices (
    ticker      VARCHAR(20) PRIMARY KEY,
    price       NUMERIC(18,6) NOT NULL,
    change_pct  NUMERIC(8,4),
    volume      BIGINT,
    source      VARCHAR(50) NOT NULL,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Price history (TimescaleDB hypertable) ────────────────────────
-- Partitioned by time — critical for fast range queries
CREATE TABLE price_history (
    ticker      VARCHAR(20) NOT NULL,
    ts          TIMESTAMPTZ NOT NULL,
    open        NUMERIC(18,6),
    high        NUMERIC(18,6),
    low         NUMERIC(18,6),
    close       NUMERIC(18,6) NOT NULL,
    volume      BIGINT,
    interval    VARCHAR(10) NOT NULL DEFAULT '1d',  -- '1d', '1h', '5m'
    PRIMARY KEY (ticker, ts, interval)
);

-- Convert to TimescaleDB hypertable (auto partitions by time)
SELECT create_hypertable('price_history', 'ts', chunk_time_interval => INTERVAL '7 days');

-- Compress chunks older than 30 days (saves ~90% storage)
ALTER TABLE price_history SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'ticker,interval'
);
SELECT add_compression_policy('price_history', INTERVAL '30 days');

CREATE INDEX idx_price_hist_ticker ON price_history(ticker, ts DESC);

-- ── API usage tracking (for cost monitoring + quota enforcement) ──
CREATE TABLE api_usage (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id      UUID REFERENCES users(id) ON DELETE SET NULL,
    endpoint     VARCHAR(255) NOT NULL,
    method       VARCHAR(10) NOT NULL,
    status_code  INT NOT NULL,
    source       VARCHAR(50),                -- 'cache_redis' | 'cache_pg' | 'yfinance' | 'financialdatasets'
    latency_ms   INT,
    ts           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- TimescaleDB for api_usage too — high write volume
SELECT create_hypertable('api_usage', 'ts', chunk_time_interval => INTERVAL '1 day');
CREATE INDEX idx_api_usage_user ON api_usage(user_id, ts DESC);

-- ── Rate limit tiers (referenced in app) ──────────────────────────
CREATE TABLE rate_limit_tiers (
    tier             subscription_tier PRIMARY KEY,
    requests_per_min INT NOT NULL,
    requests_per_day INT NOT NULL,
    max_portfolios   INT NOT NULL,
    max_positions    INT NOT NULL,
    ai_calls_per_day INT NOT NULL,
    can_export       BOOLEAN NOT NULL DEFAULT FALSE
);

INSERT INTO rate_limit_tiers VALUES
  ('free',  20,   500,  1,   5,   0,   FALSE),
  ('pro',   100,  5000, 10,  100, 50,  TRUE),
  ('fund',  500,  50000,999, 999, 999, TRUE);

-- ── Audit log ─────────────────────────────────────────────────────
CREATE TABLE audit_log (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id    UUID REFERENCES users(id) ON DELETE SET NULL,
    action     VARCHAR(100) NOT NULL,
    entity     VARCHAR(50),
    entity_id  UUID,
    metadata   JSONB,
    ip_address INET,
    ts         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
SELECT create_hypertable('audit_log', 'ts', chunk_time_interval => INTERVAL '7 days');

-- ── Auto-update updated_at timestamps ────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users_updated_at      BEFORE UPDATE ON users      FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_portfolios_updated_at BEFORE UPDATE ON portfolios  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_positions_updated_at  BEFORE UPDATE ON positions   FOR EACH ROW EXECUTE FUNCTION update_updated_at();
