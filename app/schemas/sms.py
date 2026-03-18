"""Pydantic schemas for SMS parsing."""

from typing import Optional

from pydantic import BaseModel


class SMSParseRequest(BaseModel):
    sms_body: str
    timestamp: str  # ISO format or any string
    sender: Optional[str] = None


class SMSBatchRequest(BaseModel):
    messages: list[SMSParseRequest]
