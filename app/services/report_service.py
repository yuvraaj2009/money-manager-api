"""
Report service. Monthly reports, category breakdowns, trends, CSV export.
Only counts confirmed + non-deleted transactions.
"""

import calendar
import csv
import io
import uuid
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.category import Category
from app.models.transaction import Transaction

# Base filter: confirmed and not deleted
_ACTIVE = and_(
    Transaction.is_confirmed == True,  # noqa: E712
    Transaction.deleted_at.is_(None),
)


def _user_active(user_id: uuid.UUID) -> list:
    return [Transaction.user_id == user_id, _ACTIVE]


async def get_monthly_report(
    db: AsyncSession, user_id: uuid.UUID, year: int, month: int
) -> dict:
    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])
    days_in_month = (last_day - first_day).days + 1

    date_range = and_(
        Transaction.transaction_date >= first_day,
        Transaction.transaction_date <= last_day,
    )
    base = and_(*_user_active(user_id), date_range)

    # Totals
    totals = await db.execute(
        select(
            func.coalesce(
                func.sum(case((Transaction.type == "income", Transaction.amount), else_=0)), 0
            ).label("income"),
            func.coalesce(
                func.sum(case((Transaction.type == "expense", Transaction.amount), else_=0)), 0
            ).label("expense"),
        ).where(base)
    )
    row = totals.one()
    total_income = row.income
    total_expense = row.expense
    net = total_income - total_expense

    # Category breakdown (expenses only)
    cat_rows = await db.execute(
        select(
            Category.name,
            Category.icon,
            Category.color,
            func.sum(Transaction.amount).label("total"),
        )
        .join(Category, Transaction.category_id == Category.id)
        .where(and_(base, Transaction.type == "expense"))
        .group_by(Category.name, Category.icon, Category.color)
        .order_by(func.sum(Transaction.amount).desc())
    )
    category_breakdown = []
    for r in cat_rows.all():
        pct = (r.total / total_expense * 100) if total_expense > 0 else Decimal(0)
        category_breakdown.append({
            "category_name": r.name,
            "icon": r.icon,
            "color": r.color,
            "amount": float(r.total),
            "percentage": round(float(pct), 1),
        })

    # Daily breakdown
    daily_rows = await db.execute(
        select(
            Transaction.transaction_date,
            func.coalesce(
                func.sum(case((Transaction.type == "income", Transaction.amount), else_=0)), 0
            ).label("income"),
            func.coalesce(
                func.sum(case((Transaction.type == "expense", Transaction.amount), else_=0)), 0
            ).label("expense"),
        )
        .where(base)
        .group_by(Transaction.transaction_date)
        .order_by(Transaction.transaction_date)
    )
    daily_breakdown = [
        {"date": str(r.transaction_date), "income": float(r.income), "expense": float(r.expense)}
        for r in daily_rows.all()
    ]

    # Top 5 expenses
    top5_rows = await db.execute(
        select(
            Transaction.id,
            Transaction.amount,
            Transaction.description,
            Transaction.transaction_date,
            Category.name.label("category_name"),
        )
        .join(Category, Transaction.category_id == Category.id)
        .where(and_(base, Transaction.type == "expense"))
        .order_by(Transaction.amount.desc())
        .limit(5)
    )
    top_5_expenses = [
        {
            "id": str(r.id),
            "amount": float(r.amount),
            "description": r.description,
            "date": str(r.transaction_date),
            "category": r.category_name,
        }
        for r in top5_rows.all()
    ]

    # Comparison vs last month
    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1

    prev_first = date(prev_year, prev_month, 1)
    prev_last = date(prev_year, prev_month, calendar.monthrange(prev_year, prev_month)[1])

    prev_totals = await db.execute(
        select(
            func.coalesce(
                func.sum(case((Transaction.type == "expense", Transaction.amount), else_=0)), 0
            ).label("expense"),
        ).where(
            and_(
                *_user_active(user_id),
                Transaction.transaction_date >= prev_first,
                Transaction.transaction_date <= prev_last,
            )
        )
    )
    prev_expense = prev_totals.scalar()

    comparison = None
    if prev_expense and prev_expense > 0:
        diff = float(total_expense) - float(prev_expense)
        diff_pct = round(diff / float(prev_expense) * 100, 1)
        comparison = {
            "previous_month_expense": float(prev_expense),
            "current_month_expense": float(total_expense),
            "diff_amount": round(diff, 2),
            "diff_percentage": diff_pct,
        }

    return {
        "year": year,
        "month": month,
        "total_income": float(total_income),
        "total_expense": float(total_expense),
        "net": float(net),
        "daily_average_expense": round(float(total_expense) / days_in_month, 2),
        "transaction_count": len(daily_breakdown),
        "category_breakdown": category_breakdown,
        "daily_breakdown": daily_breakdown,
        "top_5_expenses": top_5_expenses,
        "comparison_vs_last_month": comparison,
    }


async def get_category_breakdown(
    db: AsyncSession,
    user_id: uuid.UUID,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> dict:
    conditions = list(_user_active(user_id))
    conditions.append(Transaction.type == "expense")
    if date_from:
        conditions.append(Transaction.transaction_date >= date_from)
    if date_to:
        conditions.append(Transaction.transaction_date <= date_to)

    where = and_(*conditions)

    # Total expenses for percentage calc
    total_result = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(where)
    )
    total_expense = total_result.scalar()

    # Per-category
    rows = await db.execute(
        select(
            Category.name,
            Category.icon,
            Category.color,
            func.sum(Transaction.amount).label("total"),
            func.count(Transaction.id).label("count"),
        )
        .join(Category, Transaction.category_id == Category.id)
        .where(where)
        .group_by(Category.name, Category.icon, Category.color)
        .order_by(func.sum(Transaction.amount).desc())
    )

    categories = []
    for r in rows.all():
        pct = (r.total / total_expense * 100) if total_expense > 0 else Decimal(0)
        categories.append({
            "category_name": r.name,
            "icon": r.icon,
            "color": r.color,
            "amount": float(r.total),
            "percentage": round(float(pct), 1),
            "transaction_count": r.count,
        })

    return {
        "date_from": str(date_from) if date_from else None,
        "date_to": str(date_to) if date_to else None,
        "total_expense": float(total_expense),
        "categories": categories,
    }


async def get_trends(
    db: AsyncSession, user_id: uuid.UUID, months: int = 6
) -> list[dict]:
    """Month-over-month for last N months."""
    today = date.today()
    results = []

    for i in range(months - 1, -1, -1):
        # Calculate month offset
        m = today.month - i
        y = today.year
        while m <= 0:
            m += 12
            y -= 1

        first_day = date(y, m, 1)
        last_day = date(y, m, calendar.monthrange(y, m)[1])

        totals = await db.execute(
            select(
                func.coalesce(
                    func.sum(case((Transaction.type == "income", Transaction.amount), else_=0)), 0
                ).label("income"),
                func.coalesce(
                    func.sum(case((Transaction.type == "expense", Transaction.amount), else_=0)), 0
                ).label("expense"),
            ).where(
                and_(
                    *_user_active(user_id),
                    Transaction.transaction_date >= first_day,
                    Transaction.transaction_date <= last_day,
                )
            )
        )
        row = totals.one()
        results.append({
            "year": y,
            "month": m,
            "month_name": calendar.month_abbr[m],
            "income": float(row.income),
            "expense": float(row.expense),
            "net": float(row.income - row.expense),
        })

    return results


async def export_csv(
    db: AsyncSession,
    user_id: uuid.UUID,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> str:
    """Generate CSV string of transactions."""
    conditions = list(_user_active(user_id))
    if date_from:
        conditions.append(Transaction.transaction_date >= date_from)
    if date_to:
        conditions.append(Transaction.transaction_date <= date_to)

    rows = await db.execute(
        select(
            Transaction.transaction_date,
            Transaction.type,
            Transaction.amount,
            Category.name.label("category"),
            Account.name.label("account"),
            Transaction.description,
            Transaction.source,
        )
        .join(Category, Transaction.category_id == Category.id)
        .join(Account, Transaction.account_id == Account.id)
        .where(and_(*conditions))
        .order_by(Transaction.transaction_date.desc())
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["date", "type", "amount", "category", "account", "description", "source"])

    for r in rows.all():
        writer.writerow([
            str(r.transaction_date),
            r.type,
            float(r.amount),
            r.category,
            r.account,
            r.description or "",
            r.source,
        ])

    return output.getvalue()
