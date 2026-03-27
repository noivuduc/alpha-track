-- ═══════════════════════════════════════════════════════════════════
-- AlphaTrack Database Schema
-- PostgreSQL 16 + TimescaleDB
--
-- This file is the Docker bootstrap script (docker-entrypoint-initdb.d).
-- It runs ONCE on a fresh volume to create extensions, ENUMs, the
-- TimescaleDB-specific alphatrack_price_history hypertable, and triggers.
--
-- All regular ORM-managed tables are created by Alembic migrations.
-- After this script runs, execute: alembic stamp head
-- ═══════════════════════════════════════════════════════════════════

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "timescaledb";
CREATE EXTENSION IF NOT EXISTS "pg_trgm"; -- for ticker search

-- ── Subscription tiers ───────────────────────────────────────────
-- Enum name matches SQLAlchemy autogenerate: subscriptiontier (no underscore)
CREATE TYPE subscriptiontier AS ENUM ('free', 'pro', 'fund');
CREATE TYPE order_side AS ENUM ('buy', 'sell');

-- ── Price history (TimescaleDB hypertable — not managed by ORM) ──
-- Partitioned by time for fast range queries across years of OHLC data.
CREATE TABLE alphatrack_price_history (
    ticker      VARCHAR(20)   NOT NULL,
    ts          TIMESTAMPTZ   NOT NULL,
    open        NUMERIC(18,6),
    high        NUMERIC(18,6),
    low         NUMERIC(18,6),
    close       NUMERIC(18,6) NOT NULL,
    volume      BIGINT,
    interval    VARCHAR(10)   NOT NULL DEFAULT '1d',  -- '1d', '1h', '5m'
    PRIMARY KEY (ticker, ts, interval)
);

-- Convert to TimescaleDB hypertable (auto partitions by time)
SELECT create_hypertable('alphatrack_price_history', 'ts', chunk_time_interval => INTERVAL '7 days');

-- Compress chunks older than 30 days (~90% storage saving)
ALTER TABLE alphatrack_price_history SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'ticker,interval'
);
SELECT add_compression_policy('alphatrack_price_history', INTERVAL '30 days');

CREATE INDEX idx_alphatrack_price_history_ticker ON alphatrack_price_history(ticker, ts DESC);

-- ── Auto-update updated_at timestamps ────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;
