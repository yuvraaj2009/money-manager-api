"""
SMS parsing routes. JWT required, scoped to current user.
Parsed transactions saved as source='sms_auto', is_confirmed=false.
Dedup via sms_hash.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.account import Account
from app.models.category import Category
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.sms import SMSBatchRequest, SMSParseRequest
from app.schemas.transaction import TransactionResponse
from app.services.sms_parser import ParsedSMS, parse_sms
from datetime import date as date_type

router = APIRouter(prefix="/sms", tags=["sms"])


async def _find_account_by_bank(
    db: AsyncSession, user_id: uuid.UUID, bank_identifier: str | None
) -> uuid.UUID | None:
    """Try to match bank_identifier to a user's account."""
    if not bank_identifier:
        return None
    result = await db.execute(
        select(Account.id).where(
            and_(
                Account.user_id == user_id,
                Account.bank_identifier.ilike(f"%{bank_identifier}%"),
            )
        )
    )
    account_id = result.scalar_one_or_none()
    return account_id


async def _find_default_account(db: AsyncSession, user_id: uuid.UUID) -> uuid.UUID:
    """Get the first account for the user as fallback."""
    result = await db.execute(
        select(Account.id)
        .where(Account.user_id == user_id)
        .order_by(Account.is_default.desc())
        .limit(1)
    )
    account_id = result.scalar_one_or_none()
    if not account_id:
        raise HTTPException(status_code=400, detail="No accounts found. Cannot save transaction.")
    return account_id


async def _find_category_by_name(
    db: AsyncSession, user_id: uuid.UUID, category_name: str | None, txn_type: str
) -> uuid.UUID:
    """Match category by name, or fall back to Other Expense/Other Income."""
    if category_name:
        result = await db.execute(
            select(Category.id).where(
                and_(
                    Category.user_id == user_id,
                    Category.name == category_name,
                )
            )
        )
        cat_id = result.scalar_one_or_none()
        if cat_id:
            return cat_id

    # Fallback
    fallback_name = "Other Income" if txn_type == "income" else "Other Expense"
    result = await db.execute(
        select(Category.id).where(
            and_(
                Category.user_id == user_id,
                Category.name == fallback_name,
            )
        )
    )
    cat_id = result.scalar_one_or_none()
    if not cat_id:
        # Last resort: any category
        result = await db.execute(
            select(Category.id).where(Category.user_id == user_id).limit(1)
        )
        cat_id = result.scalar_one()
    return cat_id


async def _check_duplicate(db: AsyncSession, user_id: uuid.UUID, sms_hash: str) -> bool:
    """Check if this SMS was already parsed (dedup)."""
    result = await db.execute(
        select(Transaction.id).where(
            and_(
                Transaction.user_id == user_id,
                Transaction.sms_hash == sms_hash,
            )
        )
    )
    return result.scalar_one_or_none() is not None


async def _save_parsed_sms(
    db: AsyncSession,
    user_id: uuid.UUID,
    parsed: ParsedSMS,
    transaction_date: str,
) -> Transaction:
    """Save a parsed SMS as an unconfirmed transaction."""
    account_id = await _find_account_by_bank(db, user_id, parsed.bank_identifier)
    if not account_id:
        account_id = await _find_default_account(db, user_id)

    category_id = await _find_category_by_name(db, user_id, parsed.category_keyword, parsed.type)

    # Use date from SMS parsing if available, otherwise from timestamp param
    if parsed.transaction_date:
        txn_date = parsed.transaction_date.date()
    else:
        try:
            txn_date = date_type.fromisoformat(transaction_date[:10])
        except (ValueError, IndexError):
            txn_date = date_type.today()

    txn = Transaction(
        user_id=user_id,
        amount=parsed.amount,
        type=parsed.type,
        category_id=category_id,
        account_id=account_id,
        description=parsed.description,
        transaction_date=txn_date,
        source="sms_auto",
        sms_hash=parsed.sms_hash,
        is_confirmed=False,
    )
    db.add(txn)
    # NOTE: balance NOT updated until user confirms
    await db.commit()
    await db.refresh(txn)
    return txn


def _parsed_to_dict(parsed: ParsedSMS) -> dict:
    return {
        "amount": float(parsed.amount),
        "type": parsed.type,
        "bank": parsed.bank_identifier,
        "merchant": parsed.merchant,
        "description": parsed.description,
        "confidence": parsed.confidence,
        "suggested_category": parsed.category_keyword,
        "sms_hash": parsed.sms_hash,
        "transaction_date": parsed.transaction_date.isoformat() if parsed.transaction_date else None,
    }


@router.post("/parse")
async def parse_single_sms(
    data: SMSParseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    parsed = parse_sms(data.sms_body, data.timestamp, data.sender)
    if not parsed:
        return {
            "success": True,
            "data": {"parsed": False, "reason": "Could not parse transaction from SMS."},
        }

    # Check duplicate
    is_dup = await _check_duplicate(db, current_user.id, parsed.sms_hash)
    if is_dup:
        return {
            "success": True,
            "data": {"parsed": True, "duplicate": True, "sms_hash": parsed.sms_hash},
        }

    # Save as pending transaction
    txn = await _save_parsed_sms(db, current_user.id, parsed, data.timestamp)

    return {
        "success": True,
        "data": {
            "parsed": True,
            "duplicate": False,
            "transaction": TransactionResponse.model_validate(txn).model_dump(),
            "parse_details": _parsed_to_dict(parsed),
        },
    }


@router.post("/batch")
async def parse_batch_sms(
    data: SMSBatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    results = []
    for msg in data.messages:
        parsed = parse_sms(msg.sms_body, msg.timestamp, msg.sender)
        if not parsed:
            results.append({"sms_body": msg.sms_body[:50], "parsed": False})
            continue

        is_dup = await _check_duplicate(db, current_user.id, parsed.sms_hash)
        if is_dup:
            results.append({
                "sms_body": msg.sms_body[:50],
                "parsed": True,
                "duplicate": True,
            })
            continue

        txn = await _save_parsed_sms(db, current_user.id, parsed, msg.timestamp)
        results.append({
            "sms_body": msg.sms_body[:50],
            "parsed": True,
            "duplicate": False,
            "transaction_id": str(txn.id),
            "amount": float(parsed.amount),
            "type": parsed.type,
            "confidence": parsed.confidence,
        })

    parsed_count = sum(1 for r in results if r.get("parsed") and not r.get("duplicate"))
    return {
        "success": True,
        "data": {
            "total": len(data.messages),
            "parsed": parsed_count,
            "duplicates": sum(1 for r in results if r.get("duplicate")),
            "failed": sum(1 for r in results if not r.get("parsed")),
            "results": results,
        },
    }


@router.get("/pending")
async def get_pending(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    result = await db.execute(
        select(Transaction)
        .where(
            and_(
                Transaction.user_id == current_user.id,
                Transaction.is_confirmed == False,  # noqa: E712
                Transaction.deleted_at.is_(None),
            )
        )
        .order_by(Transaction.created_at.desc())
    )
    transactions = list(result.scalars().all())
    return {
        "success": True,
        "data": {
            "pending_count": len(transactions),
            "transactions": [
                TransactionResponse.model_validate(t).model_dump() for t in transactions
            ],
        },
    }


@router.post("/confirm/{txn_id}")
async def confirm_transaction(
    txn_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    result = await db.execute(
        select(Transaction).where(
            and_(
                Transaction.id == txn_id,
                Transaction.user_id == current_user.id,
                Transaction.deleted_at.is_(None),
            )
        )
    )
    txn = result.scalar_one_or_none()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found.")

    if txn.is_confirmed:
        raise HTTPException(status_code=400, detail="Transaction already confirmed.")

    # Confirm: update source and flag
    txn.source = "sms_confirmed"
    txn.is_confirmed = True

    # NOW update account balance (deferred until confirmation)
    account_result = await db.execute(
        select(Account).where(
            and_(Account.id == txn.account_id, Account.user_id == current_user.id)
        )
    )
    account = account_result.scalar_one_or_none()
    if account:
        if txn.type == "income":
            account.balance += txn.amount
        else:
            account.balance -= txn.amount

    await db.commit()
    await db.refresh(txn)
    return {
        "success": True,
        "data": TransactionResponse.model_validate(txn).model_dump(),
    }


@router.put("/reject/{txn_id}")
async def reject_transaction(
    txn_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    from sqlalchemy import func as sa_func

    result = await db.execute(
        select(Transaction).where(
            and_(
                Transaction.id == txn_id,
                Transaction.user_id == current_user.id,
                Transaction.deleted_at.is_(None),
            )
        )
    )
    txn = result.scalar_one_or_none()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found.")

    # Soft delete — no balance reversal needed since unconfirmed txns don't affect balance
    txn.deleted_at = sa_func.now()

    await db.commit()
    await db.refresh(txn)
    return {
        "success": True,
        "data": {"id": str(txn.id), "rejected": True, "deleted_at": str(txn.deleted_at)},
    }
