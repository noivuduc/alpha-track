"""
Real-time streaming endpoints — SSE for price updates + market status.

Architecture:
  - Pipeline worker publishes price updates to Redis Pub/Sub channel "prices:live"
  - This router subscribes and fans out to connected SSE clients
  - Each client only receives updates for tickers they subscribe to
  - Market status endpoint lets frontend decide whether to open SSE connection
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.database import get_redis
from app.middleware import check_rate_limit
from app.models import User
from app.services.market_calendar import get_market_status

log = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(tags=["stream"])

PUBSUB_CHANNEL = "prices:live"


# ── Market Status (REST — no auth required) ──────────────────────────────────

@router.get("/market/status")
async def market_status() -> dict:
    """Current market state, next transition, and countdown."""
    return get_market_status()


# ── SSE Price Stream ──────────────────────────────────────────────────────────
# Auth uses the standard Bearer header via check_rate_limit.
# The frontend connects with fetch() + ReadableStream (not EventSource)
# so it can set Authorization headers normally.

@router.get("/stream/prices")
async def stream_prices(
    request: Request,
    tickers: str = Query(..., description="Comma-separated tickers to subscribe to"),
    user: User = Depends(check_rate_limit),
):
    """
    Server-Sent Events stream for real-time price updates.

    The client receives:
      - `event: price`          — price update for a subscribed ticker
      - `event: market_status`  — market state changes
      - `event: heartbeat`      — keepalive every 15s

    Connect only when market is_trading=true.
    """
    ticker_set = {t.strip().upper() for t in tickers.split(",") if t.strip()}
    if not ticker_set:
        return {"error": "No tickers provided"}

    return StreamingResponse(
        _sse_generator(request, ticker_set),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Encoding": "identity",
        },
    )


async def _sse_generator(
    request: Request,
    tickers: set[str],
) -> AsyncGenerator[bytes, None]:
    """
    Core SSE loop — subscribes to Redis Pub/Sub and yields filtered events.

    Yields bytes to ensure StreamingResponse flushes each chunk immediately.
    """
    log.info("SSE stream opened for tickers: %s", tickers)

    r = get_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe(PUBSUB_CHANNEL)

    heartbeat_interval = settings.SSE_HEARTBEAT_SECONDS
    last_heartbeat = asyncio.get_event_loop().time()

    # Send initial market status immediately so the client knows we're alive
    status = get_market_status()
    yield _sse_event("market_status", status)
    log.info("SSE sent initial market_status: %s", status["state"])

    try:
        while True:
            if await request.is_disconnected():
                log.info("SSE client disconnected")
                break

            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)

            if msg and msg["type"] == "message":
                try:
                    data = json.loads(msg["data"])
                    matched = 0

                    if isinstance(data, list):
                        for update in data:
                            if update.get("ticker") in tickers:
                                yield _sse_event("price", update)
                                matched += 1
                    elif isinstance(data, dict):
                        if data.get("type") == "market_status":
                            yield _sse_event("market_status", data)
                            matched += 1
                        elif data.get("ticker") in tickers:
                            yield _sse_event("price", data)
                            matched += 1

                    if matched:
                        log.debug("SSE forwarded %d events", matched)
                except (json.JSONDecodeError, TypeError) as e:
                    log.warning("SSE message parse error: %s", e)

            now = asyncio.get_event_loop().time()
            if now - last_heartbeat >= heartbeat_interval:
                last_heartbeat = now
                mkt = get_market_status()
                yield _sse_event("heartbeat", {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "market": mkt["state"],
                })
                yield _sse_event("market_status", mkt)

    except asyncio.CancelledError:
        log.info("SSE stream cancelled")
    finally:
        await pubsub.unsubscribe(PUBSUB_CHANNEL)
        await pubsub.aclose()
        log.info("SSE stream closed for tickers: %s", tickers)


def _sse_event(event: str, data: dict) -> bytes:
    """Format an SSE event and encode to bytes for reliable flushing."""
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n".encode()
