"""
Admin API — user management, tier config, provider management, cost tracking,
system metrics, audit log.

All endpoints require is_admin=True (enforced by require_admin dependency).
All mutations write to audit_log automatically.
Heavy list queries are cached in Redis for 30 seconds.
"""
from __future__ import annotations

import uuid
import json
import logging
from datetime import datetime, timezone, timedelta, date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, func, distinct, and_, or_, desc, text, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, get_cache, Cache
from app.middleware import require_admin, hash_password
from app.models import (
    User, Portfolio, Position, ApiUsage, AuditLog,
    SubscriptionTierConfig, DataProvider, SubscriptionTier,
)
from app.schemas import (
    AdminStats,
    AdminUserRow, AdminUserDetail, AdminUserUpdate, AdminUserListResponse,
    AdminResetPasswordRequest,
    TierConfigResponse, TierConfigUpdate,
    DataProviderResponse, DataProviderUpdate, ReorderProvidersRequest,
    AdminPortfolioRow, AdminPortfolioListResponse,
    CostSummaryResponse, ProviderCostDay,
    SystemSummaryResponse,
    AuditLogRow, AuditLogListResponse,
)

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])

# ── Cache TTLs ────────────────────────────────────────────────────────────────
_CACHE_STATS_TTL   = 30    # stats / system summary: 30 s
_CACHE_COSTS_TTL   = 300   # cost summary: 5 min
_CACHE_USERS_TTL   = 10    # user list: 10 s (near-realtime for admin)

# ── Cost per call estimates (used when provider table not seeded) ──────────────
_DEFAULT_COSTS: dict[str, float] = {
    "financialdatasets": 0.001,
    "yfinance":          0.0,
    "cache_redis":       0.0,
    "cache_pg":          0.0,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _audit(
    db: AsyncSession,
    admin: User,
    action: str,
    entity: str | None = None,
    entity_id: uuid.UUID | None = None,
    meta: dict | None = None,
    request: Request | None = None,
) -> None:
    ip = None
    if request:
        forwarded = request.headers.get("X-Forwarded-For")
        ip = (forwarded.split(",")[0].strip() if forwarded else None) or (
            request.client.host if request.client else None
        )
    db.add(AuditLog(
        user_id   = admin.id,
        action    = action,
        entity    = entity,
        entity_id = entity_id,
        meta      = meta,
        ip_address= ip,
    ))


async def _get_user_or_404(db: AsyncSession, user_id: str) -> User:
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid user ID")
    user = await db.get(User, uid)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return user


# ── Legacy stats endpoint (kept for backward compat) ─────────────────────────
@router.get("/stats", response_model=AdminStats)
async def get_stats(
    admin: User          = Depends(require_admin),
    db: AsyncSession     = Depends(get_db),
    cache: Cache         = Depends(get_cache),
):
    cached = await cache.get("admin:stats")
    if cached:
        return json.loads(cached)

    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    total_users    = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    tier_rows      = (await db.execute(select(User.tier, func.count()).group_by(User.tier))).all()
    users_by_tier  = {r[0].value: r[1] for r in tier_rows}
    api_calls_today= (await db.execute(select(func.count()).select_from(ApiUsage).where(ApiUsage.ts >= today))).scalar_one()
    paid_calls     = (await db.execute(select(func.count()).select_from(ApiUsage).where(ApiUsage.ts >= today, ApiUsage.source == "financialdatasets"))).scalar_one()
    cache_hits     = (await db.execute(select(func.count()).select_from(ApiUsage).where(ApiUsage.ts >= today, ApiUsage.source.like("cache_%")))).scalar_one()
    hit_rate       = cache_hits / api_calls_today * 100 if api_calls_today else 0.0

    result = AdminStats(
        total_users        = total_users,
        users_by_tier      = users_by_tier,
        api_calls_today    = api_calls_today,
        cache_hit_rate     = round(hit_rate, 1),
        paid_calls_today   = paid_calls,
        estimated_cost_usd = round(paid_calls * 0.001, 4),
    )
    await cache.set("admin:stats", result.model_dump_json(), _CACHE_STATS_TTL)
    return result


# ════════════════════════════════════════════════════════════════════════════════
# USER MANAGEMENT
# ════════════════════════════════════════════════════════════════════════════════

@router.get("/users", response_model=AdminUserListResponse)
async def list_users(
    limit:     int          = Query(20, ge=1, le=100),
    offset:    int          = Query(0, ge=0),
    email:     str | None   = Query(None, description="Partial email match"),
    tier:      str | None   = Query(None, description="free | pro | fund"),
    is_active: bool | None  = Query(None),
    admin: User              = Depends(require_admin),
    db: AsyncSession         = Depends(get_db),
):
    # Portfolio count subquery
    port_subq = (
        select(Portfolio.user_id, func.count(Portfolio.id).label("portfolio_count"))
        .group_by(Portfolio.user_id)
        .subquery()
    )

    # Last active from ApiUsage (last 90 days for performance)
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    active_subq = (
        select(ApiUsage.user_id, func.max(ApiUsage.ts).label("last_active_at"))
        .where(ApiUsage.ts >= cutoff)
        .group_by(ApiUsage.user_id)
        .subquery()
    )

    base = (
        select(
            User,
            func.coalesce(port_subq.c.portfolio_count, 0).label("portfolio_count"),
            active_subq.c.last_active_at,
        )
        .outerjoin(port_subq,   User.id == port_subq.c.user_id)
        .outerjoin(active_subq, User.id == active_subq.c.user_id)
    )

    if email:
        base = base.where(User.email.ilike(f"%{email}%"))
    if tier:
        try:
            base = base.where(User.tier == SubscriptionTier(tier))
        except ValueError:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Invalid tier: {tier}")
    if is_active is not None:
        base = base.where(User.is_active == is_active)

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

    rows = (
        await db.execute(base.order_by(User.created_at.desc()).limit(limit).offset(offset))
    ).all()

    items = [
        AdminUserRow(
            id              = r.User.id,
            email           = r.User.email,
            full_name       = r.User.full_name,
            tier            = r.User.tier.value,
            is_active       = r.User.is_active,
            is_admin        = r.User.is_admin,
            is_verified     = r.User.is_verified,
            created_at      = r.User.created_at,
            portfolio_count = r.portfolio_count,
            last_active_at  = r.last_active_at,
        )
        for r in rows
    ]
    return AdminUserListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/users/{user_id}", response_model=AdminUserDetail)
async def get_user(
    user_id: str,
    admin: User      = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    u = await _get_user_or_404(db, user_id)
    port_count = (
        await db.execute(select(func.count()).select_from(Portfolio).where(Portfolio.user_id == u.id))
    ).scalar_one()
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    last_active = (
        await db.execute(
            select(func.max(ApiUsage.ts)).where(ApiUsage.user_id == u.id, ApiUsage.ts >= cutoff)
        )
    ).scalar_one()

    return AdminUserDetail(
        id                 = u.id,
        email              = u.email,
        full_name          = u.full_name,
        tier               = u.tier.value,
        is_active          = u.is_active,
        is_admin           = u.is_admin,
        is_verified        = u.is_verified,
        created_at         = u.created_at,
        portfolio_count    = port_count,
        last_active_at     = last_active,
        stripe_customer_id = u.stripe_customer_id,
        has_api_key        = u.api_key_hash is not None,
    )


@router.patch("/users/{user_id}", response_model=AdminUserDetail)
async def update_user(
    user_id: str,
    body:    AdminUserUpdate,
    request: Request,
    admin:   User        = Depends(require_admin),
    db:      AsyncSession = Depends(get_db),
):
    u = await _get_user_or_404(db, user_id)

    changes: dict[str, Any] = {}
    if body.tier is not None:
        u.tier      = SubscriptionTier(body.tier)
        changes["tier"] = body.tier
    if body.is_active is not None:
        u.is_active = body.is_active
        changes["is_active"] = body.is_active
    if body.is_admin is not None:
        # Prevent admins from removing their own admin flag
        if str(u.id) == str(admin.id) and not body.is_admin:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot remove your own admin status")
        u.is_admin  = body.is_admin
        changes["is_admin"] = body.is_admin
    if body.full_name is not None:
        u.full_name = body.full_name
        changes["full_name"] = body.full_name

    await _audit(db, admin, "user.update", "user", u.id, changes, request)
    await db.commit()
    await db.refresh(u)

    port_count  = (await db.execute(select(func.count()).select_from(Portfolio).where(Portfolio.user_id == u.id))).scalar_one()
    cutoff      = datetime.now(timezone.utc) - timedelta(days=90)
    last_active = (await db.execute(select(func.max(ApiUsage.ts)).where(ApiUsage.user_id == u.id, ApiUsage.ts >= cutoff))).scalar_one()

    return AdminUserDetail(
        id=u.id, email=u.email, full_name=u.full_name, tier=u.tier.value,
        is_active=u.is_active, is_admin=u.is_admin, is_verified=u.is_verified,
        created_at=u.created_at, portfolio_count=port_count, last_active_at=last_active,
        stripe_customer_id=u.stripe_customer_id, has_api_key=u.api_key_hash is not None,
    )


@router.post("/users/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_user_password(
    user_id: str,
    body:    AdminResetPasswordRequest,
    request: Request,
    admin:   User        = Depends(require_admin),
    db:      AsyncSession = Depends(get_db),
):
    u = await _get_user_or_404(db, user_id)
    u.hashed_password = hash_password(body.new_password)
    await _audit(db, admin, "user.reset_password", "user", u.id, {}, request)
    await db.commit()


@router.post("/users/{user_id}/revoke-api-key", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    user_id: str,
    request: Request,
    admin:   User        = Depends(require_admin),
    db:      AsyncSession = Depends(get_db),
):
    u = await _get_user_or_404(db, user_id)
    if not u.api_key_hash:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User has no API key")
    u.api_key_hash = None
    await _audit(db, admin, "user.revoke_api_key", "user", u.id, {}, request)
    await db.commit()


# ════════════════════════════════════════════════════════════════════════════════
# SUBSCRIPTION TIER CONFIG
# ════════════════════════════════════════════════════════════════════════════════

@router.get("/tiers", response_model=list[TierConfigResponse])
async def list_tiers(
    admin: User      = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(select(SubscriptionTierConfig).order_by(SubscriptionTierConfig.price_usd))).scalars().all()
    return [TierConfigResponse.model_validate(r) for r in rows]


@router.patch("/tiers/{name}", response_model=TierConfigResponse)
async def update_tier(
    name:    str,
    body:    TierConfigUpdate,
    request: Request,
    admin:   User        = Depends(require_admin),
    db:      AsyncSession = Depends(get_db),
):
    tier = await db.get(SubscriptionTierConfig, name)
    if not tier:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Tier '{name}' not found")

    changes: dict[str, Any] = {}
    for field in ("display_name", "max_portfolios", "max_positions", "rpm", "rpd", "ai_per_day", "price_usd"):
        val = getattr(body, field, None)
        if val is not None:
            setattr(tier, field, val)
            changes[field] = str(val)

    await _audit(db, admin, "tier.update", "tier", None, {"tier": name, **changes}, request)
    await db.commit()
    await db.refresh(tier)
    return TierConfigResponse.model_validate(tier)


# ════════════════════════════════════════════════════════════════════════════════
# DATA PROVIDER MANAGEMENT
# ════════════════════════════════════════════════════════════════════════════════

@router.get("/providers", response_model=list[DataProviderResponse])
async def list_providers(
    admin: User      = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(select(DataProvider).order_by(DataProvider.priority))).scalars().all()
    return [DataProviderResponse.model_validate(r) for r in rows]


@router.patch("/providers/{name}", response_model=DataProviderResponse)
async def update_provider(
    name:    str,
    body:    DataProviderUpdate,
    request: Request,
    admin:   User        = Depends(require_admin),
    db:      AsyncSession = Depends(get_db),
):
    prov = await db.get(DataProvider, name)
    if not prov:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Provider '{name}' not found")

    changes: dict[str, Any] = {}
    for field in ("enabled", "priority", "rate_limit_rpm", "cost_per_call_usd", "notes"):
        val = getattr(body, field, None)
        if val is not None:
            setattr(prov, field, val)
            changes[field] = str(val)

    await _audit(db, admin, "provider.update", "provider", None, {"provider": name, **changes}, request)
    await db.commit()
    await db.refresh(prov)
    return DataProviderResponse.model_validate(prov)


@router.post("/providers/reorder", status_code=status.HTTP_204_NO_CONTENT)
async def reorder_providers(
    body:    ReorderProvidersRequest,
    request: Request,
    admin:   User        = Depends(require_admin),
    db:      AsyncSession = Depends(get_db),
):
    for idx, name in enumerate(body.order, start=1):
        prov = await db.get(DataProvider, name)
        if prov:
            prov.priority = idx
    await _audit(db, admin, "provider.reorder", "provider", None, {"order": body.order}, request)
    await db.commit()


# ════════════════════════════════════════════════════════════════════════════════
# PORTFOLIO OVERSIGHT
# ════════════════════════════════════════════════════════════════════════════════

@router.get("/portfolios", response_model=AdminPortfolioListResponse)
async def list_portfolios(
    limit:   int        = Query(20, ge=1, le=100),
    offset:  int        = Query(0, ge=0),
    user_id: str | None = Query(None),
    admin: User          = Depends(require_admin),
    db: AsyncSession     = Depends(get_db),
):
    pos_subq = (
        select(Position.portfolio_id, func.count(Position.id).label("position_count"))
        .where(Position.closed_at == None)
        .group_by(Position.portfolio_id)
        .subquery()
    )

    base = (
        select(
            Portfolio,
            User.email.label("user_email"),
            func.coalesce(pos_subq.c.position_count, 0).label("position_count"),
        )
        .join(User, Portfolio.user_id == User.id)
        .outerjoin(pos_subq, Portfolio.id == pos_subq.c.portfolio_id)
    )

    if user_id:
        try:
            uid = uuid.UUID(user_id)
            base = base.where(Portfolio.user_id == uid)
        except ValueError:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid user_id")

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows  = (await db.execute(base.order_by(Portfolio.updated_at.desc()).limit(limit).offset(offset))).all()

    items = [
        AdminPortfolioRow(
            id             = r.Portfolio.id,
            user_id        = r.Portfolio.user_id,
            user_email     = r.user_email,
            name           = r.Portfolio.name,
            currency       = r.Portfolio.currency,
            position_count = r.position_count,
            created_at     = r.Portfolio.created_at,
            updated_at     = r.Portfolio.updated_at,
        )
        for r in rows
    ]
    return AdminPortfolioListResponse(items=items, total=total, limit=limit, offset=offset)


@router.delete("/portfolios/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_portfolio(
    portfolio_id: str,
    request: Request,
    admin:   User        = Depends(require_admin),
    db:      AsyncSession = Depends(get_db),
):
    try:
        pid = uuid.UUID(portfolio_id)
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid portfolio ID")

    portfolio = await db.get(Portfolio, pid)
    if not portfolio:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Portfolio not found")

    await _audit(db, admin, "portfolio.delete", "portfolio", pid,
                 {"name": portfolio.name, "user_id": str(portfolio.user_id)}, request)
    await db.delete(portfolio)
    await db.commit()


# ════════════════════════════════════════════════════════════════════════════════
# COST TRACKING
# ════════════════════════════════════════════════════════════════════════════════

@router.get("/costs", response_model=CostSummaryResponse)
async def get_costs(
    days:    int          = Query(30, ge=1, le=90),
    admin: User           = Depends(require_admin),
    db: AsyncSession      = Depends(get_db),
    cache: Cache          = Depends(get_cache),
):
    cache_key = f"admin:costs:{days}"
    cached = await cache.get(cache_key)
    if cached:
        return json.loads(cached)

    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Aggregate from ApiUsage: group by date + source (=provider)
    rows = (await db.execute(
        select(
            func.date_trunc("day", ApiUsage.ts).label("day"),
            ApiUsage.source,
            func.count().label("calls"),
        )
        .where(ApiUsage.ts >= since, ApiUsage.source.isnot(None))
        .group_by(text("1"), ApiUsage.source)
        .order_by(text("1"), ApiUsage.source)
    )).all()

    # Fetch cost-per-call from provider table if available
    prov_costs: dict[str, float] = dict(_DEFAULT_COSTS)
    prov_rows = (await db.execute(select(DataProvider))).scalars().all()
    for p in prov_rows:
        prov_costs[p.name] = float(p.cost_per_call_usd)

    daily: list[ProviderCostDay] = []
    by_provider: dict[str, Any] = {}
    total_calls = 0
    total_cost  = 0.0

    for r in rows:
        cost_rate = prov_costs.get(r.source, 0.0)
        cost_usd  = r.calls * cost_rate
        total_calls += r.calls
        total_cost  += cost_usd

        if r.source not in by_provider:
            by_provider[r.source] = {"calls": 0, "estimated_cost_usd": 0.0}
        by_provider[r.source]["calls"] += r.calls
        by_provider[r.source]["estimated_cost_usd"] = round(
            by_provider[r.source]["estimated_cost_usd"] + cost_usd, 6
        )

        daily.append(ProviderCostDay(
            date               = r.day.strftime("%Y-%m-%d"),
            provider           = r.source,
            calls              = r.calls,
            estimated_cost_usd = round(cost_usd, 6),
        ))

    result = CostSummaryResponse(
        period_days    = days,
        total_calls    = total_calls,
        total_cost_usd = round(total_cost, 4),
        by_provider    = by_provider,
        daily          = daily,
    )
    await cache.set(cache_key, result.model_dump_json(), _CACHE_COSTS_TTL)
    return result


# ════════════════════════════════════════════════════════════════════════════════
# SYSTEM SUMMARY
# ════════════════════════════════════════════════════════════════════════════════

@router.get("/system-summary", response_model=SystemSummaryResponse)
async def get_system_summary(
    admin: User      = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    cache: Cache     = Depends(get_cache),
):
    cached = await cache.get("admin:system_summary")
    if cached:
        return json.loads(cached)

    now   = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    ago7d = now - timedelta(days=7)
    ago30d= now - timedelta(days=30)

    total_users = (await db.execute(select(func.count()).select_from(User))).scalar_one()

    active_7d = (await db.execute(
        select(func.count(distinct(ApiUsage.user_id)))
        .where(ApiUsage.ts >= ago7d, ApiUsage.user_id.isnot(None))
    )).scalar_one()

    active_30d = (await db.execute(
        select(func.count(distinct(ApiUsage.user_id)))
        .where(ApiUsage.ts >= ago30d, ApiUsage.user_id.isnot(None))
    )).scalar_one()

    reqs_today = (await db.execute(select(func.count()).select_from(ApiUsage).where(ApiUsage.ts >= today))).scalar_one()
    reqs_7d    = (await db.execute(select(func.count()).select_from(ApiUsage).where(ApiUsage.ts >= ago7d))).scalar_one()

    errors_today = (await db.execute(
        select(func.count()).select_from(ApiUsage)
        .where(ApiUsage.ts >= today, ApiUsage.status_code >= 500)
    )).scalar_one()
    error_rate = errors_today / reqs_today * 100 if reqs_today else 0.0

    cache_hits = (await db.execute(
        select(func.count()).select_from(ApiUsage)
        .where(ApiUsage.ts >= today, ApiUsage.source.like("cache_%"))
    )).scalar_one()
    cache_rate = cache_hits / reqs_today * 100 if reqs_today else 0.0

    paid_calls = (await db.execute(
        select(func.count()).select_from(ApiUsage)
        .where(ApiUsage.ts >= today, ApiUsage.source == "financialdatasets")
    )).scalar_one()

    avg_latency = (await db.execute(
        select(func.avg(ApiUsage.latency_ms))
        .where(ApiUsage.ts >= today, ApiUsage.latency_ms.isnot(None))
    )).scalar_one() or 0.0

    result = SystemSummaryResponse(
        total_users          = total_users,
        active_users_7d      = active_7d,
        active_users_30d     = active_30d,
        requests_today       = reqs_today,
        requests_7d          = reqs_7d,
        error_rate_pct       = round(error_rate, 2),
        cache_hit_rate_pct   = round(cache_rate, 1),
        paid_calls_today     = paid_calls,
        estimated_cost_today = round(paid_calls * 0.001, 4),
        avg_latency_ms       = round(float(avg_latency), 1),
    )
    await cache.set("admin:system_summary", result.model_dump_json(), _CACHE_STATS_TTL)
    return result


# ════════════════════════════════════════════════════════════════════════════════
# AUDIT LOG
# ════════════════════════════════════════════════════════════════════════════════

@router.get("/audit-logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    limit:  int        = Query(50, ge=1, le=200),
    offset: int        = Query(0, ge=0),
    action: str | None = Query(None),
    admin: User         = Depends(require_admin),
    db: AsyncSession    = Depends(get_db),
):
    # Join with User to get admin email
    base = (
        select(AuditLog, User.email.label("admin_email"))
        .outerjoin(User, AuditLog.user_id == User.id)
    )
    if action:
        base = base.where(AuditLog.action.ilike(f"%{action}%"))

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows  = (await db.execute(base.order_by(AuditLog.ts.desc()).limit(limit).offset(offset))).all()

    items = [
        AuditLogRow(
            id          = r.AuditLog.id,
            admin_email = r.admin_email,
            action      = r.AuditLog.action,
            entity      = r.AuditLog.entity,
            entity_id   = r.AuditLog.entity_id,
            metadata    = r.AuditLog.meta,
            ip_address  = r.AuditLog.ip_address,
            ts          = r.AuditLog.ts,
        )
        for r in rows
    ]
    return AuditLogListResponse(items=items, total=total, limit=limit, offset=offset)
