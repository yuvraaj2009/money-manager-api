"""
Debug endpoints. Always deployed, no auth required. READ-ONLY.
/debug/health  - Alive + DB connection + response time
/debug/config  - Env vars loaded (secrets masked)
/debug/db-stats - Row counts, DB size, pool stats
/debug/user/{id} - Full user state: seeded?, counts
"""

import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_db

router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)) -> dict:
    start = time.perf_counter()

    # Test DB connection
    db_status = "connected"
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"error: {str(e)}"

    duration_ms = round((time.perf_counter() - start) * 1000, 2)

    return {
        "success": True,
        "data": {
            "status": "healthy" if db_status == "connected" else "degraded",
            "database": db_status,
            "response_time_ms": duration_ms,
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
        },
    }


@router.get("/config")
async def show_config() -> dict:
    return {
        "success": True,
        "data": {
            "ENVIRONMENT": settings.ENVIRONMENT,
            "APP_VERSION": settings.APP_VERSION,
            "DATABASE_URL": _mask_secret(settings.DATABASE_URL),
            "JWT_SECRET": "***masked***",
            "JWT_ALGORITHM": settings.JWT_ALGORITHM,
            "JWT_EXPIRY_MINUTES": settings.JWT_EXPIRY_MINUTES,
            "REFRESH_TOKEN_EXPIRY_DAYS": settings.REFRESH_TOKEN_EXPIRY_DAYS,
        },
    }


@router.get("/db-stats")
async def db_stats(db: AsyncSession = Depends(get_db)) -> dict:
    tables = ["users", "transactions", "categories", "accounts", "budgets"]
    counts = {}

    for table in tables:
        try:
            result = await db.execute(
                text(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
            )
            counts[table] = result.scalar()
        except Exception:
            counts[table] = "table not found"

    # Database size
    try:
        result = await db.execute(
            text("SELECT pg_size_pretty(pg_database_size(current_database()))")
        )
        db_size = result.scalar()
    except Exception:
        db_size = "unknown"

    return {
        "success": True,
        "data": {
            "row_counts": counts,
            "database_size": db_size,
        },
    }


@router.get("/user/{user_id}")
async def user_state(user_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    from app.models.user import User

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    # Count related records
    counts = {}
    for table, col in [("categories", "user_id"), ("accounts", "user_id"), ("transactions", "user_id")]:
        try:
            r = await db.execute(
                text(f"SELECT COUNT(*) FROM {table} WHERE {col} = :uid"),  # noqa: S608
                {"uid": user_id},
            )
            counts[table] = r.scalar()
        except Exception:
            counts[table] = "table not found"

    return {
        "success": True,
        "data": {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "is_seeded": user.is_seeded,
            "created_at": str(user.created_at),
            "counts": counts,
        },
    }


def _mask_secret(value: str) -> str:
    if len(value) <= 10:
        return "***masked***"
    return value[:5] + "***" + value[-3:]
