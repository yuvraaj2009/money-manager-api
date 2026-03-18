"""
Report routes. JWT required, scoped to current user.
Only confirmed + non-deleted transactions counted.
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.services.report_service import (
    export_csv,
    get_category_breakdown,
    get_monthly_report,
    get_trends,
)

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/monthly/{year}/{month}")
async def monthly_report(
    year: int,
    month: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    data = await get_monthly_report(db, current_user.id, year, month)
    return {"success": True, "data": data}


@router.get("/category-breakdown")
async def category_breakdown(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    data = await get_category_breakdown(db, current_user.id, date_from, date_to)
    return {"success": True, "data": data}


@router.get("/trends")
async def trends(
    months: int = Query(6, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    data = await get_trends(db, current_user.id, months)
    return {"success": True, "data": data}


@router.get("/export/csv")
async def export_csv_report(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    csv_content = await export_csv(db, current_user.id, date_from, date_to)

    filename = "transactions"
    if date_from:
        filename += f"_from_{date_from}"
    if date_to:
        filename += f"_to_{date_to}"
    filename += ".csv"

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
