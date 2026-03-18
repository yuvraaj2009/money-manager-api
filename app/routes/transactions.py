"""Transaction routes. JWT required, scoped to current user."""

import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.transaction import TransactionCreate, TransactionResponse, TransactionUpdate
from app.services.transaction_service import (
    create_transaction,
    get_transaction_summary,
    list_transactions,
    soft_delete_transaction,
    update_transaction,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("")
async def get_transactions(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    category_id: Optional[uuid.UUID] = Query(None),
    account_id: Optional[uuid.UUID] = Query(None),
    type: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    transactions, total = await list_transactions(
        db, current_user.id, date_from, date_to,
        category_id, account_id, type, source, limit, offset,
    )
    return {
        "success": True,
        "data": {
            "transactions": [
                TransactionResponse.model_validate(t).model_dump() for t in transactions
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        },
    }


@router.post("")
async def create(
    data: TransactionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    txn = await create_transaction(db, current_user.id, data)
    return {
        "success": True,
        "data": TransactionResponse.model_validate(txn).model_dump(),
    }


@router.put("/{txn_id}")
async def update(
    txn_id: uuid.UUID,
    data: TransactionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    txn = await update_transaction(db, current_user.id, txn_id, data)
    return {
        "success": True,
        "data": TransactionResponse.model_validate(txn).model_dump(),
    }


@router.delete("/{txn_id}")
async def delete(
    txn_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    txn = await soft_delete_transaction(db, current_user.id, txn_id)
    return {
        "success": True,
        "data": {"id": str(txn.id), "deleted_at": str(txn.deleted_at)},
    }


@router.get("/summary")
async def summary(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    data = await get_transaction_summary(db, current_user.id, year, month)
    return {"success": True, "data": data}
