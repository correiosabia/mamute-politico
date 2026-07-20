"""Esquemas Pydantic utilizados nos endpoints do chatbot."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


MAX_CHAT_QUESTION_CHARS = 2000
MAX_CHAT_HISTORY_MESSAGES = 20
MAX_CHAT_HISTORY_MESSAGE_CHARS = 2000
MAX_CHAT_REQUEST_CHARS = 8000


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=MAX_CHAT_HISTORY_MESSAGE_CHARS)


class ChatFilters(BaseModel):
    parliamentarian_ids: Optional[List[int]] = None
    parties: Optional[List[str]] = None
    states: Optional[List[str]] = None
    roles: Optional[List[str]] = None


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=MAX_CHAT_QUESTION_CHARS)
    history: List[ChatMessage] = Field(
        default_factory=list,
        max_length=MAX_CHAT_HISTORY_MESSAGES,
    )
    filters: Optional[ChatFilters] = None

    @model_validator(mode="after")
    def validate_total_context_size(self) -> "ChatRequest":
        total_chars = len(self.question or "") + sum(
            len(message.content or "") for message in self.history
        )
        if total_chars > MAX_CHAT_REQUEST_CHARS:
            raise ValueError(
                f"question plus history must have at most {MAX_CHAT_REQUEST_CHARS} characters"
            )
        return self


class ChatResponse(BaseModel):
    answer: str


class ChatQuotaWindow(BaseModel):
    """Uma janela de cota (semanal ou mensal)."""

    limit: int
    used: int
    remaining: int
    reset_at: datetime
    limit_reached: bool


class ChatQuotaResponse(BaseModel):
    # Campos de topo refletem a janela que "trava primeiro" (binding), mantidos
    # por compatibilidade. weekly/monthly trazem o detalhe de cada janela.
    enabled: bool
    limit: Optional[int] = None
    used: int = 0
    remaining: Optional[int] = None
    reset_at: datetime
    limit_reached: bool = False
    weekly: Optional[ChatQuotaWindow] = None
    monthly: Optional[ChatQuotaWindow] = None


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
