"""Esquemas Pydantic utilizados nos endpoints do chatbot."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatFilters(BaseModel):
    parliamentarian_ids: Optional[List[int]] = None
    parties: Optional[List[str]] = None
    states: Optional[List[str]] = None
    roles: Optional[List[str]] = None


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=3)
    history: List[ChatMessage] = Field(default_factory=list)
    filters: Optional[ChatFilters] = None


class ChatResponse(BaseModel):
    answer: str


class ChatQuotaResponse(BaseModel):
    enabled: bool
    limit: Optional[int] = None
    used: int = 0
    remaining: Optional[int] = None
    reset_at: datetime
    limit_reached: bool = False


class HealthcheckResponse(BaseModel):
    status: str = "ok"
    environment: Optional[str] = None
    databases: Optional[Dict[str, str]] = None


__all__ = [
    "ChatMessage",
    "ChatFilters",
    "ChatRequest",
    "ChatQuotaResponse",
    "ChatResponse",
    "HealthcheckResponse",
]
