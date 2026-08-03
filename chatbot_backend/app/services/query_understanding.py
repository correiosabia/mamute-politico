"""Interpretação da intenção de busca da pergunta pelo próprio LLM.

A extração heurística de palavras-chave (regex + stoplist) olha PALAVRAS, não
contexto: em "o que parlamentares falaram sobre a APAE, no geral?" ela
promovia "geral" a termo de busca com o mesmo peso de "apae". Ajustar a
stoplist trata o sintoma — a próxima formulação inesperada quebra de novo.

Este passo pede ao LLM os temas centrais da pergunta (frases inteiras, sem
palavras de enquadramento), que viram as âncoras do SQL context. A heurística
continua existindo apenas como fallback quando esta chamada falha.
"""

from __future__ import annotations

import asyncio
import json
import logging
from time import perf_counter
from typing import Any, List, Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from ..core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "Você extrai a intenção de busca de perguntas sobre atividade "
                "parlamentar (discursos, proposições e votações do Congresso "
                "Nacional). Responda EXCLUSIVAMENTE com JSON no formato: "
                '{{"temas": ["..."], "panoramica": true|false}}.\n'
                "Regras:\n"
                "- 'temas': de 1 a 3 termos de busca centrais da pergunta, na "
                "ordem de importância. Mantenha expressões compostas inteiras "
                '("reforma tributária", "imposto de renda").\n'
                "- Inclua nomes próprios (parlamentares, entidades, programas) "
                "quando forem o assunto da pergunta.\n"
                "- NÃO inclua palavras de enquadramento ou conversa: geral, "
                "exemplo, resumo, hoje, opinião, o que, quais, falaram, "
                "parlamentares, discursos etc.\n"
                "- NUNCA invente temas que não estejam na pergunta.\n"
                "- 'panoramica': true se a pergunta pede visão geral de vários "
                "parlamentares; false se mira alguém/algo específico."
            ),
        ),
        ("human", "Pergunta do usuário:\n{question}"),
    ]
)

_TIMEOUT_S = 8.0
_MAX_TOPICS = 3


class QueryUnderstanding:
    """Interpreta a pergunta antes da busca. Fail-soft: erro → None."""

    def __init__(self) -> None:
        self.llm = ChatOpenAI(
            model=settings.openai_model,
            temperature=0.0,
            max_tokens=200,
            api_key=settings.openai_api_key.get_secret_value(),
            base_url=settings.openai_base_url or None,
        )

    async def ainterpret(
        self, question: str, request_id: str = "n/a"
    ) -> Optional[dict[str, Any]]:
        started_at = perf_counter()
        try:
            chain = _PROMPT | self.llm
            response = await asyncio.wait_for(
                chain.ainvoke({"question": question}), timeout=_TIMEOUT_S
            )
            parsed = _parse_intent(getattr(response, "content", None) or "")
        except Exception as exc:  # noqa: BLE001 — interpretação nunca derruba a consulta
            logger.warning(
                "⚠️ Question interpretation failed (fallback heurístico) | "
                "request_id=%s | error=%s",
                request_id,
                exc,
            )
            return None

        if parsed is None:
            logger.warning(
                "⚠️ Question interpretation unparseable (fallback heurístico) | request_id=%s",
                request_id,
            )
            return None

        logger.info(
            "🧭 Question interpreted | request_id=%s | temas=%s | panoramica=%s | elapsed_ms=%.2f",
            request_id,
            parsed["temas"],
            parsed["panoramica"],
            (perf_counter() - started_at) * 1000,
        )
        return parsed


def _parse_intent(raw_content: str) -> Optional[dict[str, Any]]:
    """Extrai {temas, panoramica} do JSON da resposta. None se inválido."""

    text = raw_content.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None

    if not isinstance(data, dict):
        return None

    raw_topics = data.get("temas")
    if not isinstance(raw_topics, list):
        return None

    topics: List[str] = []
    for item in raw_topics:
        term = str(item or "").strip()
        if term and term.lower() not in {t.lower() for t in topics}:
            topics.append(term)
    if not topics:
        return None

    return {
        "temas": topics[:_MAX_TOPICS],
        "panoramica": bool(data.get("panoramica")),
    }


__all__ = ["QueryUnderstanding", "_parse_intent"]
