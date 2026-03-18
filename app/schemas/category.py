"""Pydantic schemas for categories."""

import uuid
from typing import Optional

from pydantic import BaseModel, field_validator


class CategoryCreate(BaseModel):
    name: str
    icon: str
    color: str
    type: str  # income / expense

    @field_validator("type")
    @classmethod
    def valid_type(cls, v: str) -> str:
        if v not in ("income", "expense"):
            raise ValueError("Type must be income or expense.")
        return v

    @field_validator("color")
    @classmethod
    def valid_color(cls, v: str) -> str:
        if not v.startswith("#") or len(v) != 7:
            raise ValueError("Color must be hex format: #RRGGBB")
        return v


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    type: Optional[str] = None

    @field_validator("type")
    @classmethod
    def valid_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("income", "expense"):
            raise ValueError("Type must be income or expense.")
        return v


class CategoryResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    icon: str
    color: str
    type: str
    is_default: bool

    model_config = {"from_attributes": True}
