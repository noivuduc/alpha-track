#!/usr/bin/env bash
# AlphaTrack — local dev launcher
# Usage: ./start.sh [--no-frontend]
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[alphatrack]${NC} $*"; }
warn()  { echo -e "${YELLOW}[alphatrack]${NC} $*"; }
error() { echo -e "${RED}[alphatrack]${NC} $*"; exit 1; }

# ── Preflight checks ──────────────────────────────────────────────────────────
command -v docker  >/dev/null 2>&1 || error "Docker not found. Install from https://www.docker.com/products/docker-desktop"
command -v node    >/dev/null 2>&1 || warn  "Node.js not found — frontend won't start. Install from https://nodejs.org"

# ── Start Docker services (Postgres + Redis only) ────────────────────────────
info "Starting Postgres (TimescaleDB) + Redis..."
docker compose up -d postgres redis

info "Waiting for Postgres to be healthy..."
for i in $(seq 1 30); do
  if docker compose exec -T postgres pg_isready -U alphatrack >/dev/null 2>&1; then
    info "Postgres is ready ✓"
    break
  fi
  [ $i -eq 30 ] && error "Postgres never became ready after 30s"
  sleep 1
done

info "Waiting for Redis to be healthy..."
for i in $(seq 1 15); do
  if docker compose exec -T redis redis-cli -a changeme ping >/dev/null 2>&1; then
    info "Redis is ready ✓"
    break
  fi
  [ $i -eq 15 ] && error "Redis never became ready"
  sleep 1
done

# ── Backend (FastAPI) ─────────────────────────────────────────────────────────
info "Installing Python dependencies..."
cd backend
python3 -m venv .venv 2>/dev/null || true
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt
pip install -q -r "$SCRIPT_DIR/pipeline/requirements.txt"
info "Python deps installed ✓"

info "Starting FastAPI backend on http://localhost:8000 ..."
DATABASE_URL="postgresql+asyncpg://alphatrack:changeme@localhost:5432/alphatrack" \
REDIS_URL="redis://:changeme@localhost:6379/0" \
  # Limit --reload to app/ only (avoids watching .venv, __pycache__, etc. → fewer FDs / watches)
  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir app &
BACKEND_PID=$!

cd "$SCRIPT_DIR"

# ── Pipeline Worker (ARQ) — standalone service ────────────────────────────────
info "Starting ARQ pipeline worker..."
PYTHONPATH="$SCRIPT_DIR/backend:$SCRIPT_DIR/pipeline" \
DATABASE_URL="postgresql+asyncpg://alphatrack:changeme@localhost:5432/alphatrack" \
REDIS_URL="redis://:changeme@localhost:6379/0" \
  arq pipeline_worker.worker.WorkerSettings &
WORKER_PID=$!
info "Pipeline worker started (PID $WORKER_PID) ✓"

# ── Pipeline Dashboard ────────────────────────────────────────────────────────
info "Starting pipeline dashboard on http://localhost:9000 ..."
PYTHONPATH="$SCRIPT_DIR/backend:$SCRIPT_DIR/pipeline" \
DATABASE_URL="postgresql+asyncpg://alphatrack:changeme@localhost:5432/alphatrack" \
REDIS_URL="redis://:changeme@localhost:6379/0" \
  uvicorn pipeline_worker.dashboard.app:app --host 0.0.0.0 --port 9000 &
DASHBOARD_PID=$!
info "Dashboard started (PID $DASHBOARD_PID) ✓"

# ── Frontend (Next.js) ────────────────────────────────────────────────────────
if [[ "$1" != "--no-frontend" ]] && command -v node >/dev/null 2>&1; then
  info "Installing Node dependencies..."
  cd frontend
  npm install --silent
  info "Starting Next.js frontend on http://localhost:3000 ..."
  NEXT_PUBLIC_API_URL="http://localhost:8000/api/v1" npm run dev &
  FRONTEND_PID=$!
  cd "$SCRIPT_DIR"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
info "╔═══════════════════════════════════════════╗"
info "║         AlphaTrack is running!           ║"
info "╠═══════════════════════════════════════════╣"
info "║  Frontend   →  http://localhost:3000     ║"
info "║  API docs   →  http://localhost:8000/docs║"
info "║  Dashboard  →  http://localhost:9000     ║"
info "║  Health     →  http://localhost:8000/health ║"
info "║  Pipeline   →  ARQ worker (background)   ║"
info "╚═══════════════════════════════════════════╝"
echo ""
info "Press Ctrl+C to stop all services."

# Cleanup on exit
trap 'info "Shutting down..."; kill $BACKEND_PID 2>/dev/null; kill $WORKER_PID 2>/dev/null; kill $DASHBOARD_PID 2>/dev/null; kill $FRONTEND_PID 2>/dev/null; docker compose stop postgres redis; info "Done."' INT TERM

wait $BACKEND_PID
