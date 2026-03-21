"""
Budget CRUD routes. JWT required, scoped to current user.
Monthly budgets — optionally per-category.
"""

import uuid
from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.budget import Budget
from app.models.user import User


class BudgetCreate(BaseModel):
    amount: float = Field(gt=0)
    month: str = Field(description="YYYY-MM-DD (first of month)")
    category_id: str | None = None


class BudgetUpdate(BaseModel):
    amount: float | None = Field(default=None, gt=0)


class BudgetResponse(BaseModel):
    id: str
    amount: float
    month: str
    category_id: str | None

    model_config = {"from_attributes": True}


router = APIRouter(prefix="/budgets", tags=["budgets"])


@router.get("")
async def list_budgets(
    month: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    query = select(Budget).where(Budget.user_id == current_user.id)
    if month:
        try:
            month_date = date_type.fromisoformat(month)
            query = query.where(Budget.month == month_date)
        except ValueError:
            pass
    query = query.order_by(Budget.month.desc())
    result = await db.execute(query)
    budgets = list(result.scalars().all())
    return {
        "success": True,
        "data": {
            "budgets": [
                {
                    "id": str(b.id),
                    "amount": float(b.amount),
                    "month": str(b.month),
                    "category_id": str(b.category_id) if b.category_id else None,
                }
                for b in budgets
            ],
        },
    }


@router.post("")
async def create_budget(
    data: BudgetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    month_date = date_type.fromisoformat(data.month)

    # Check for duplicate (same month + category)
    dup_query = select(Budget).where(
        and_(
            Budget.user_id == current_user.id,
            Budget.month == month_date,
        )
    )
    if data.category_id:
        dup_query = dup_query.where(Budget.category_id == uuid.UUID(data.category_id))
    else:
        dup_query = dup_query.where(Budget.category_id.is_(None))

    existing = await db.execute(dup_query)
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Budget already exists for this month/category.")

    budget = Budget(
        user_id=current_user.id,
        amount=data.amount,
        month=month_date,
        category_id=uuid.UUID(data.category_id) if data.category_id else None,
    )
    db.add(budget)
    await db.commit()
    await db.refresh(budget)

    return {
        "success": True,
        "data": {
            "id": str(budget.id),
            "amount": float(budget.amount),
            "month": str(budget.month),
            "category_id": str(budget.category_id) if budget.category_id else None,
        },
    }


@router.put("/{budget_id}")
async def update_budget(
    budget_id: uuid.UUID,
    data: BudgetUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    result = await db.execute(
        select(Budget).where(
            and_(Budget.id == budget_id, Budget.user_id == current_user.id)
        )
    )
    budget = result.scalar_one_or_none()
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found.")

    if data.amount is not None:
        budget.amount = data.amount

    await db.commit()
    await db.refresh(budget)

    return {
        "success": True,
        "data": {
            "id": str(budget.id),
            "amount": float(budget.amount),
            "month": str(budget.month),
            "category_id": str(budget.category_id) if budget.category_id else None,
        },
    }


@router.delete("/{budget_id}")
async def delete_budget(
    budget_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    result = await db.execute(
        select(Budget).where(
            and_(Budget.id == budget_id, Budget.user_id == current_user.id)
        )
    )
    budget = result.scalar_one_or_none()
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found.")

    await db.delete(budget)
    await db.commit()

    return {"success": True, "data": {"id": str(budget_id), "deleted": True}}
