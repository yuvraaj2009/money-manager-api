"""Account CRUD routes. JWT required, scoped to current user."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.account import Account
from app.models.user import User
from app.schemas.account import AccountCreate, AccountResponse, AccountUpdate

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("")
async def get_accounts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    result = await db.execute(
        select(Account)
        .where(Account.user_id == current_user.id)
        .order_by(Account.name)
    )
    accounts = list(result.scalars().all())
    return {
        "success": True,
        "data": [AccountResponse.model_validate(a).model_dump() for a in accounts],
    }


@router.post("")
async def create_account(
    data: AccountCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    account = Account(
        user_id=current_user.id,
        name=data.name,
        type=data.type,
        balance=data.balance,
        is_default=False,
        bank_identifier=data.bank_identifier,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return {
        "success": True,
        "data": AccountResponse.model_validate(account).model_dump(),
    }


@router.put("/{account_id}")
async def update_account(
    account_id: uuid.UUID,
    data: AccountUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    result = await db.execute(
        select(Account).where(
            and_(Account.id == account_id, Account.user_id == current_user.id)
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found.")

    if data.name is not None:
        account.name = data.name
    if data.type is not None:
        account.type = data.type
    if data.bank_identifier is not None:
        account.bank_identifier = data.bank_identifier

    await db.commit()
    await db.refresh(account)
    return {
        "success": True,
        "data": AccountResponse.model_validate(account).model_dump(),
    }


@router.delete("/{account_id}")
async def delete_account(
    account_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    result = await db.execute(
        select(Account).where(
            and_(Account.id == account_id, Account.user_id == current_user.id)
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found.")

    await db.delete(account)
    await db.commit()
    return {
        "success": True,
        "data": {"id": str(account_id), "deleted": True},
    }
