"""Reranker baseado em LLM para priorizar os melhores chunks recuperados."""

from __future__ import annotations

import json
import logging
from time import perf_counter
from typing import Iterable, List, Sequence

from langchain_core.documents import Document
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
                "Você é um assistente que ranqueia trechos conforme a pertinência "
                "à pergunta informada. Responda exclusivamente em JSON seguindo o "
                "formato: {{\"ranking\": [{{\"index\": <int>, \"score\": <float>}}]}}.\n"
                "O índice deve usar base 1 (primeiro trecho = 1). O score deve estar "
                "entre 0 e 1. Ordene por score decrescente e inclua apenas trechos "
                "realmente relevantes."
            ),
        ),
        (
            "human",
            (
                "Pergunta do usuário:\n{question}\n\n"
                "Trechos recuperados:\n{documents}\n\n"
                "Retorne apenas o JSON especificado."
            ),
        ),
    ]
)


class LLMReranker:
    """Executa reranking dos documentos utilizando ChatGPT."""

    def __init__(self) -> None:
        self.llm = ChatOpenAI(
            model=settings.openai_model,
            temperature=0.0,
            max_tokens=256,
            api_key=settings.openai_api_key.get_secret_value(),
            base_url=settings.openai_base_url or None,
        )

    async def arerank(
        self,
        question: str,
        documents: Sequence[Document],
        top_k: int,
        request_id: str = "n/a",
    ) -> List[Document]:
        """Retorna os documentos mais relevantes segundo o LLM."""

        started_at = perf_counter()
        if len(documents) <= 1 or top_k <= 0:
            logger.info(
                "🏅 Reranker skipped | request_id=%s | docs=%s | top_k=%s",
                request_id,
                len(documents),
                top_k,
            )
            return list(documents)

        serialized_docs = self._serialize_documents(documents)
        if not serialized_docs:
            return list(documents)[:top_k]

        chain = _PROMPT | self.llm
        try:
            response = await chain.ainvoke(
                {"question": question, "documents": serialized_docs}
            )
            content = getattr(response, "content", None) or ""
            ranking = self._parse_ranking(content, len(documents))
        except Exception as exc:
            logger.exception(
                "❌ Reranker failed, fallback to original order | request_id=%s | docs=%s | top_k=%s | error=%s",
                request_id,
                len(documents),
                top_k,
                exc,
            )
            ranking = []

        if not ranking:
            logger.info(
                "⚠️ Reranker returned empty ranking, using fallback | request_id=%s | docs=%s | top_k=%s | elapsed_ms=%.2f",
                request_id,
                len(documents),
                top_k,
                (perf_counter() - started_at) * 1000,
            )
            return list(documents)[:top_k]

        ordered_docs: List[Document] = []
        seen = set()
        for index in ranking:
            if 0 <= index < len(documents) and index not in seen:
                ordered_docs.append(documents[index])
                seen.add(index)

        for idx, doc in enumerate(documents):
            if idx not in seen:
                ordered_docs.append(doc)

        result = ordered_docs[:top_k]
        logger.info(
            "✅ Reranker finished | request_id=%s | docs_in=%s | docs_out=%s | elapsed_ms=%.2f",
            request_id,
            len(documents),
            len(result),
            (perf_counter() - started_at) * 1000,
        )
        return result

    @staticmethod
    def _serialize_documents(documents: Sequence[Document]) -> str:
        """Gera string com os documentos enumerados para uso no prompt."""

        if not documents:
            return ""

        serialized_chunks: List[str] = []
        for idx, doc in enumerate(documents, start=1):
            metadata = doc.metadata or {}
            source = metadata.get("source") or metadata.get("id") or "desconhecido"
            date = metadata.get("date")
            header = f"[{idx}] Fonte: {source}"
            if date:
                header += f" • Data: {date}"
            body = doc.page_content.strip()
            if len(body) > 1200:
                body = body[:1200] + "..."
            serialized_chunks.append(f"{header}\n{body}")

        return "\n\n".join(serialized_chunks)

    @staticmethod
    def _parse_ranking(raw_content: str, doc_count: int) -> List[int]:
        """Extrai a lista de índices baseada na resposta JSON."""

        try:
            data = json.loads(raw_content)
        except json.JSONDecodeError:
            # tenta localizar JSON em meio a outros textos
            start = raw_content.find("{")
            end = raw_content.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return []
            try:
                data = json.loads(raw_content[start : end + 1])
            except json.JSONDecodeError:
                return []

        ranking_items = data.get("ranking")
        if not isinstance(ranking_items, Iterable):
            return []

        parsed_indexes: List[int] = []
        for item in ranking_items:
            if not isinstance(item, dict):
                continue
            index = item.get("index")
            if not isinstance(index, int):
                continue
            zero_based = index - 1
            if 0 <= zero_based < doc_count:
                parsed_indexes.append(zero_based)

        return parsed_indexes


__all__ = ["LLMReranker"]
