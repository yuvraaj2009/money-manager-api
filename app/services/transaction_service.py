"""
Transaction service. All business logic for transactions.
Handles balance updates on create/update/delete.
"""

import calendar
import uuid
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.category import Category
from app.models.transaction import Transaction
from app.schemas.transaction import TransactionCreate, TransactionUpdate


def _balance_delta(txn_type: str, amount: Decimal) -> Decimal:
    """Calculate balance change: income adds, expense/transfer subtracts."""
    if txn_type == "income":
        return amount
    return -amount


async def _get_account_for_user(
    db: AsyncSession, account_id: uuid.UUID, user_id: uuid.UUID
) -> Account:
    result = await db.execute(
        select(Account).where(
            and_(Account.id == account_id, Account.user_id == user_id)
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found.")
    return account


async def _validate_category(
    db: AsyncSession, category_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    result = await db.execute(
        select(Category.id).where(
            and_(Category.id == category_id, Category.user_id == user_id)
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Category not found.")


async def create_transaction(
    db: AsyncSession, user_id: uuid.UUID, data: TransactionCreate
) -> Transaction:
    await _validate_category(db, data.category_id, user_id)
    account = await _get_account_for_user(db, data.account_id, user_id)

    txn = Transaction(
        user_id=user_id,
        amount=data.amount,
        type=data.type,
        category_id=data.category_id,
        account_id=data.account_id,
        description=data.description,
        transaction_date=data.transaction_date,
        source=data.source,
        is_confirmed=data.source == "manual",
    )
    db.add(txn)

    # Update account balance
    account.balance += _balance_delta(data.type, data.amount)

    await db.commit()
    await db.refresh(txn)
    return txn


async def update_transaction(
    db: AsyncSession, user_id: uuid.UUID, txn_id: uuid.UUID, data: TransactionUpdate
) -> Transaction:
    result = await db.execute(
        select(Transaction).where(
            and_(
                Transaction.id == txn_id,
                Transaction.user_id == user_id,
                Transaction.deleted_at.is_(None),
            )
        )
    )
    txn = result.scalar_one_or_none()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found.")

    # Reverse old balance effect
    old_account = await _get_account_for_user(db, txn.account_id, user_id)
    old_account.balance -= _balance_delta(txn.type, txn.amount)

    # Apply updates
    if data.category_id is not None:
        await _validate_category(db, data.category_id, user_id)
        txn.category_id = data.category_id
    if data.account_id is not None:
        await _get_account_for_user(db, data.account_id, user_id)
        txn.account_id = data.account_id
    if data.amount is not None:
        txn.amount = data.amount
    if data.type is not None:
        txn.type = data.type
    if data.description is not None:
        txn.description = data.description
    if data.transaction_date is not None:
        txn.transaction_date = data.transaction_date

    # Apply new balance effect
    new_account = await _get_account_for_user(db, txn.account_id, user_id)
    new_account.balance += _balance_delta(txn.type, txn.amount)

    await db.commit()
    await db.refresh(txn)
    return txn


async def soft_delete_transaction(
    db: AsyncSession, user_id: uuid.UUID, txn_id: uuid.UUID
) -> Transaction:
    result = await db.execute(
        select(Transaction).where(
            and_(
                Transaction.id == txn_id,
                Transaction.user_id == user_id,
                Transaction.deleted_at.is_(None),
            )
        )
    )
    txn = result.scalar_one_or_none()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found.")

    # Reverse balance change
    account = await _get_account_for_user(db, txn.account_id, user_id)
    account.balance -= _balance_delta(txn.type, txn.amount)

    txn.deleted_at = func.now()

    await db.commit()
    await db.refresh(txn)
    return txn


async def list_transactions(
    db: AsyncSession,
    user_id: uuid.UUID,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    category_id: Optional[uuid.UUID] = None,
    account_id: Optional[uuid.UUID] = None,
    txn_type: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Transaction], int]:
    conditions = [
        Transaction.user_id == user_id,
        Transaction.deleted_at.is_(None),
    ]
    if date_from:
        conditions.append(Transaction.transaction_date >= date_from)
    if date_to:
        conditions.append(Transaction.transaction_date <= date_to)
    if category_id:
        conditions.append(Transaction.category_id == category_id)
    if account_id:
        conditions.append(Transaction.account_id == account_id)
    if txn_type:
        conditions.append(Transaction.type == txn_type)
    if source:
        conditions.append(Transaction.source == source)

    where = and_(*conditions)

    # Count
    count_result = await db.execute(select(func.count(Transaction.id)).where(where))
    total = count_result.scalar()

    # Fetch
    result = await db.execute(
        select(Transaction)
        .where(where)
        .order_by(Transaction.transaction_date.desc(), Transaction.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    transactions = list(result.scalars().all())

    return transactions, total


async def get_transaction_summary(
    db: AsyncSession, user_id: uuid.UUID, year: int, month: int
) -> dict:
    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])
    days_in_month = (last_day - first_day).days + 1

    conditions = and_(
        Transaction.user_id == user_id,
        Transaction.deleted_at.is_(None),
        Transaction.transaction_date >= first_day,
        Transaction.transaction_date <= last_day,
    )

    # Totals
    income_result = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            and_(conditions, Transaction.type == "income")
        )
    )
    total_income = income_result.scalar()

    expense_result = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            and_(conditions, Transaction.type == "expense")
        )
    )
    total_expense = expense_result.scalar()

    count_result = await db.execute(
        select(func.count(Transaction.id)).where(conditions)
    )
    txn_count = count_result.scalar()

    # Category breakdown
    cat_result = await db.execute(
        select(
            Category.id,
            Category.name,
            Category.icon,
            Category.color,
            func.sum(Transaction.amount).label("total"),
        )
        .join(Category, Transaction.category_id == Category.id)
        .where(and_(conditions, Transaction.type == "expense"))
        .group_by(Category.id, Category.name, Category.icon, Category.color)
        .order_by(func.sum(Transaction.amount).desc())
    )
    breakdown = []
    for row in cat_result.all():
        pct = (row.total / total_expense * 100) if total_expense > 0 else 0
        breakdown.append(
            {
                "category_id": str(row.id),
                "name": row.name,
                "icon": row.icon,
                "color": row.color,
                "amount": float(row.total),
                "percentage": round(float(pct), 1),
            }
        )

    net = total_income - total_expense
    daily_avg = total_expense / days_in_month if days_in_month > 0 else 0

    return {
        "year": year,
        "month": month,
        "total_income": float(total_income),
        "total_expense": float(total_expense),
        "net": float(net),
        "daily_average": round(float(daily_avg), 2),
        "transaction_count": txn_count,
        "category_breakdown": breakdown,
    }
