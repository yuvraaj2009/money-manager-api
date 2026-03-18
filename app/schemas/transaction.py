"""Pydantic schemas for transactions."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, field_validator


class TransactionCreate(BaseModel):
    amount: Decimal
    type: str  # income / expense / transfer
    category_id: uuid.UUID
    account_id: uuid.UUID
    description: Optional[str] = None
    transaction_date: date
    source: str = "manual"

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Amount must be positive.")
        return v

    @field_validator("type")
    @classmethod
    def valid_type(cls, v: str) -> str:
        if v not in ("income", "expense", "transfer"):
            raise ValueError("Type must be income, expense, or transfer.")
        return v

    @field_validator("source")
    @classmethod
    def valid_source(cls, v: str) -> str:
        if v not in ("manual", "sms_auto", "sms_confirmed"):
            raise ValueError("Source must be manual, sms_auto, or sms_confirmed.")
        return v


class TransactionUpdate(BaseModel):
    amount: Optional[Decimal] = None
    type: Optional[str] = None
    category_id: Optional[uuid.UUID] = None
    account_id: Optional[uuid.UUID] = None
    description: Optional[str] = None
    transaction_date: Optional[date] = None

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v <= 0:
            raise ValueError("Amount must be positive.")
        return v

    @field_validator("type")
    @classmethod
    def valid_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("income", "expense", "transfer"):
            raise ValueError("Type must be income, expense, or transfer.")
        return v


class TransactionResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    amount: Decimal
    type: str
    category_id: uuid.UUID
    account_id: uuid.UUID
    description: Optional[str]
    transaction_date: date
    source: str
    sms_hash: Optional[str]
    is_confirmed: bool
    deleted_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class TransactionSummary(BaseModel):
    total_income: Decimal
    total_expense: Decimal
    net: Decimal
    daily_average: Decimal
    transaction_count: int
    category_breakdown: list[dict]
