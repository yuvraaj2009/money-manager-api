"""Pydantic schemas for accounts."""

import uuid
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, field_validator


class AccountCreate(BaseModel):
    name: str
    type: str  # bank / cash / wallet / credit_card
    balance: Decimal = Decimal("0.00")
    bank_identifier: Optional[str] = None

    @field_validator("type")
    @classmethod
    def valid_type(cls, v: str) -> str:
        if v not in ("bank", "cash", "wallet", "credit_card"):
            raise ValueError("Type must be bank, cash, wallet, or credit_card.")
        return v


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    bank_identifier: Optional[str] = None

    @field_validator("type")
    @classmethod
    def valid_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("bank", "cash", "wallet", "credit_card"):
            raise ValueError("Type must be bank, cash, wallet, or credit_card.")
        return v


class AccountResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    type: str
    balance: Decimal
    is_default: bool
    bank_identifier: Optional[str]

    model_config = {"from_attributes": True}
