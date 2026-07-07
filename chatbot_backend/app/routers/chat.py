"""Rotas relacionadas ao chatbot."""

from __future__ import annotations

import asyncio
import json
import logging
from time import perf_counter
from typing import AsyncIterator, Dict, Optional
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import SQLAlchemyError

from ..core.config import get_settings
from ..core.database import get_session
from ..schemas import ChatQuotaResponse, ChatRequest, ChatResponse
from ..security import verify_token_header
from ..services.chat_service import ChatbotService
from ..services.quota import (
    ChatQuotaConfigError,
    disabled_quota_response,
    get_chat_quota,
    mark_chat_usage,
    start_chat_usage,
)

router = APIRouter(prefix="/chatbot", tags=["chatbot"])

service = ChatbotService()
logger = logging.getLogger(__name__)


def _sse_event_stream(payload: Dict[str, object]) -> str:
    """Formatador padrão de eventos Server-Sent Events."""

    data = json.dumps(payload, ensure_ascii=False)
    return f"data: {data}\n\n"


def _quota_enabled() -> bool:
    return bool(get_settings().chatbot_quota_enabled)


def _token_email_from_header(authorization: Optional[str]) -> str:
    payload = verify_token_header(authorization)
    token_email = payload.get("sub")
    if not isinstance(token_email, str) or not token_email.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token sem e-mail (sub) para identificar o projeto.",
        )
    return token_email.strip()


def _start_usage_or_raise(
    authorization: Optional[str],
    *,
    request_id: str,
    question: str,
) -> int | None:
    token_email = _token_email_from_header(authorization)
    if not _quota_enabled():
        return None

    settings = get_settings()
    try:
        with get_session() as session:
            usage = start_chat_usage(
                session,
                token_email,
                request_id=request_id,
                question_chars=len(question or ""),
                model=settings.openai_model,
            )
            return usage.usage_id
    except (ChatQuotaConfigError, SQLAlchemyError) as exc:
        if settings.chatbot_quota_fail_open:
            logger.exception(
                "Chatbot quota check failed open | request_id=%s | reason=%s",
                request_id,
                exc,
            )
            return None
        logger.exception(
            "Chatbot quota check failed closed | request_id=%s | reason=%s",
            request_id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Falha ao verificar limite de consultas IA.",
        ) from exc


def _mark_usage(
    usage_id: int | None,
    *,
    status_value: str,
    answer_chars: int = 0,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
) -> None:
    if usage_id is None:
        return
    try:
        with get_session() as session:
            mark_chat_usage(
                session,
                usage_id,
                status_value=status_value,
                answer_chars=answer_chars,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
    except SQLAlchemyError as exc:  # pragma: no cover - only observability on cleanup
        logger.exception(
            "Failed to mark chatbot usage | usage_id=%s | status=%s | reason=%s",
            usage_id,
            status_value,
            exc,
        )


@router.get(
    "/quota",
    response_model=ChatQuotaResponse,
    status_code=status.HTTP_200_OK,
    summary="Consulta a cota mensal de uso do chatbot",
)
async def quota(authorization: Optional[str] = Header(default=None)) -> ChatQuotaResponse:
    """Return the authenticated user's chatbot quota when quota enforcement is enabled."""

    if not _quota_enabled():
        with get_session() as session:
            return get_chat_quota(session, email="")

    token_email = _token_email_from_header(authorization)
    settings = get_settings()
    try:
        with get_session() as session:
            return get_chat_quota(session, token_email)
    except (ChatQuotaConfigError, SQLAlchemyError) as exc:
        if settings.chatbot_quota_fail_open:
            logger.exception("Chatbot quota endpoint failed open | reason=%s", exc)
            return disabled_quota_response()
        logger.exception("Chatbot quota endpoint failed closed | reason=%s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Falha ao verificar limite de consultas IA.",
        ) from exc


@router.post(
    "/stream",
    status_code=status.HTTP_200_OK,
    response_class=StreamingResponse,
    summary="Obtém resposta do chatbot em modo streaming",
)
async def stream_chat(
    request: ChatRequest,
    authorization: Optional[str] = Header(default=None),
) -> StreamingResponse:
    """Expõe o fluxo de tokens gerados pelo LLM."""

    request_id = str(uuid4())
    usage_id = _start_usage_or_raise(
        authorization,
        request_id=request_id,
        question=request.question,
    )

    async def event_generator() -> AsyncIterator[str]:
        started_at = perf_counter()
        answer_chars = 0
        filters = request.filters.model_dump(exclude_none=True) if request.filters else None
        inputs = {"question": request.question, "history": [msg.model_dump() for msg in request.history]}
        if filters:
            inputs["filters"] = filters
        logger.info(
            "📨 Stream request received | request_id=%s | question_chars=%s | history_messages=%s | has_filters=%s",
            request_id,
            len(request.question or ""),
            len(request.history),
            bool(filters),
        )
        prompt_tokens: int | None = None
        completion_tokens: int | None = None
        # A resposta é considerada concluída quando o pipeline emite o chunk "end"
        # (depois de todos os tokens e do "usage"). Marcamos ANTES de repassar o
        # "end" ao cliente porque, se ele já desconectou, o `yield` dispara
        # CancelledError — mas a consulta FOI respondida e precisa contar.
        pipeline_finished = False
        final_status = "cancelled"
        try:
            async for chunk in service.stream_response(inputs, request_id=request_id):
                chunk_type = chunk.get("type")
                if chunk_type == "usage":
                    # Evento interno: guarda os tokens e NÃO repassa ao cliente.
                    prompt_tokens = chunk.get("prompt_tokens")
                    completion_tokens = chunk.get("completion_tokens")
                    continue
                if chunk_type == "end":
                    pipeline_finished = True
                value = chunk.get("value")
                if chunk_type == "token" and isinstance(value, str):
                    answer_chars += len(value)
                yield _sse_event_stream(chunk)
            pipeline_finished = True
            final_status = "completed"
            elapsed = perf_counter() - started_at
            logger.info(
                "✅ Stream request completed | request_id=%s | elapsed_ms=%.2f",
                request_id,
                elapsed * 1000,
            )
        except asyncio.CancelledError:
            # Cliente desconectou. Se a resposta já foi totalmente gerada
            # (pipeline_finished), conta como completed — foi respondida e o uso
            # deve ser registrado com os tokens capturados. Senão, cancelamento real.
            final_status = "completed" if pipeline_finished else "cancelled"
            elapsed = perf_counter() - started_at
            logger.warning(
                "⚠️ Stream request %s (cliente desconectou) | request_id=%s | elapsed_ms=%.2f",
                final_status,
                request_id,
                elapsed * 1000,
            )
            raise
        except Exception as exc:  # pragma: no cover - logado externamente
            final_status = "failed"
            elapsed = perf_counter() - started_at
            logger.exception(
                "❌ Stream request failed | request_id=%s | elapsed_ms=%.2f | error=%s",
                request_id,
                elapsed * 1000,
                exc,
            )
            yield _sse_event_stream({"type": "error", "message": str(exc)})
        finally:
            # Registro ÚNICO do uso, com o status real e os tokens capturados —
            # roda mesmo quando o cliente desconecta no fim do stream.
            _mark_usage(
                usage_id,
                status_value=final_status,
                answer_chars=answer_chars,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.post(
    "/query",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Obtém resposta completa do chatbot (sem streaming)",
)
async def query_chat(
    request: ChatRequest,
    authorization: Optional[str] = Header(default=None),
) -> ChatResponse:
    """Executa o fluxo normal sem streaming."""

    request_id = str(uuid4())
    usage_id = _start_usage_or_raise(
        authorization,
        request_id=request_id,
        question=request.question,
    )
    started_at = perf_counter()
    payload = {
        "question": request.question,
        "history": [msg.model_dump() for msg in request.history],
    }
    if request.filters:
        payload["filters"] = request.filters.model_dump(exclude_none=True)
    logger.info(
        "📨 Query request received | request_id=%s | question_chars=%s | history_messages=%s | has_filters=%s",
        request_id,
        len(request.question or ""),
        len(request.history),
        bool(request.filters),
    )

    try:
        answer = await service.invoke(payload, request_id=request_id)
    except Exception as exc:
        _mark_usage(usage_id, status_value="failed")
        elapsed = perf_counter() - started_at
        logger.exception(
            "❌ Query request failed | request_id=%s | elapsed_ms=%.2f | error=%s",
            request_id,
            elapsed * 1000,
            exc,
        )
        raise
    _mark_usage(usage_id, status_value="completed", answer_chars=len(answer))
    elapsed = perf_counter() - started_at
    logger.info(
        "✅ Query request completed | request_id=%s | elapsed_ms=%.2f | answer_chars=%s",
        request_id,
        elapsed * 1000,
        len(answer),
    )
    return ChatResponse(answer=answer)
