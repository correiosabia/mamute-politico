"""Serviço central do chatbot."""

from __future__ import annotations

import asyncio
from contextlib import suppress
import logging
from time import perf_counter
from typing import Any, AsyncIterator, Dict, Iterable, List, Sequence

from langchain.callbacks.base import AsyncCallbackHandler
from langchain.callbacks.streaming_aiter import AsyncIteratorCallbackHandler
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import RunnableLambda, RunnableParallel, RunnableSequence
from langchain_openai import ChatOpenAI

from ..core.config import get_settings
from .prompts import build_prompt
from .reranker import LLMReranker
from .sql_context import fetch_sql_context
from .vector_store import get_retriever

settings = get_settings()
logger = logging.getLogger(__name__)


class JSONTokenStreamingHandler(AsyncCallbackHandler):
    """Callback customizado para formar eventos JSON."""

    def __init__(self, iterator_handler: AsyncIteratorCallbackHandler) -> None:
        self.iterator_handler = iterator_handler

    async def on_llm_new_token(
        self,
        token: str,
        *,
        run_id: str,
        parent_run_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        await self.iterator_handler.on_llm_new_token(token, run_id=run_id, **kwargs)


class ChatbotService:
    """Encapsula a criação do chain LangChain e o streaming de respostas."""

    def __init__(self) -> None:
        self.prompt = build_prompt()
        self.reranker = LLMReranker()

    @staticmethod
    def _convert_history(raw_history: Sequence[dict[str, str]]) -> List[BaseMessage]:
        """Converte histórico simples em mensagens do LangChain."""

        messages: List[BaseMessage] = []
        for item in raw_history:
            role = item.get("role")
            content = (item.get("content") or "").strip()
            if not content:
                continue
            if role == "assistant":
                messages.append(AIMessage(content=content))
            else:
                messages.append(HumanMessage(content=content))
        return messages

    @staticmethod
    def _format_documents(docs: Iterable[Document]) -> str:
        """Une documentos recuperados com metadados básicos."""

        chunks: List[str] = []
        for doc in docs:
            metadata = doc.metadata or {}
            source = metadata.get("source") or metadata.get("id") or "desconhecido"
            heading = f"Fonte: {source}"
            if "date" in metadata:
                heading += f" • Data: {metadata['date']}"
            body = doc.page_content.strip()
            chunks.append(f"{heading}\n{body}")
        return "\n\n".join(chunks)

    @staticmethod
    def _normalize_filters(raw_filters: Dict[str, Any] | None) -> Dict[str, List[object]] | None:
        """Normaliza filtros vindos da API."""

        if not raw_filters:
            return None

        normalized: Dict[str, List[object]] = {}

        ids = raw_filters.get("parliamentarian_ids") if isinstance(raw_filters, dict) else None
        if isinstance(ids, list):
            norm_ids: List[int] = []
            for value in ids:
                try:
                    norm_ids.append(int(value))
                except (TypeError, ValueError):
                    continue
            if norm_ids:
                normalized["parliamentarian_ids"] = sorted(set(norm_ids))

        def _string_list(values: Any) -> List[str]:
            if not isinstance(values, list):
                return []
            result: List[str] = []
            for value in values:
                text = str(value).strip()
                if text:
                    result.append(text.upper())
            return sorted(set(result))

        parties = _string_list(raw_filters.get("parties") if isinstance(raw_filters, dict) else None)
        if parties:
            normalized["parties"] = parties

        states = _string_list(raw_filters.get("states") if isinstance(raw_filters, dict) else None)
        if states:
            normalized["states"] = states

        roles = _string_list(raw_filters.get("roles") if isinstance(raw_filters, dict) else None)
        if roles:
            normalized["roles"] = roles

        return normalized or None

    @staticmethod
    def _build_retriever_filter(
        normalized_filters: Dict[str, List[object]] | None,
    ) -> Dict[str, Any] | None:
        """Converte filtros simples de entrada em filtros para o vetor."""

        if not normalized_filters:
            return None

        vector_filter: Dict[str, Any] = {}

        ids = normalized_filters.get("parliamentarian_ids")
        if ids:
            vector_filter["parliamentarian_id"] = {"$in": ids}

        parties = normalized_filters.get("parties")
        if parties:
            vector_filter["party"] = {"$in": parties}

        states = normalized_filters.get("states")
        if states:
            vector_filter["state"] = {"$in": states}

        roles = normalized_filters.get("roles")
        if roles:
            vector_filter["role"] = {"$in": roles}

        return vector_filter or None

    async def _retrieve_and_rerank(self, inputs: Dict[str, Any]) -> str:
        """Recupera documentos, executa reranking e prepara o contexto."""

        request_id = str(inputs.get("request_id") or "n/a")
        stage_started = perf_counter()
        question = inputs["question"]
        normalized_filters = inputs.get("filters")
        filter_payload = self._build_retriever_filter(normalized_filters)
        search_kwargs = {"filter": filter_payload} if filter_payload else None
        logger.info(
            "🔍 Retrieval started | request_id=%s | has_vector_filter=%s",
            request_id,
            bool(filter_payload),
        )
        retriever = get_retriever(search_kwargs=search_kwargs)
        documents = await retriever.ainvoke(question)
        logger.info(
            "📄 Retrieval finished | request_id=%s | documents=%s | elapsed_ms=%.2f",
            request_id,
            len(documents),
            (perf_counter() - stage_started) * 1000,
        )
        rerank_started = perf_counter()
        reranked = await self.reranker.arerank(
            question,
            documents,
            settings.rerank_top_k,
            request_id=request_id,
        )
        logger.info(
            "🏅 Rerank finished | request_id=%s | input_docs=%s | output_docs=%s | elapsed_ms=%.2f",
            request_id,
            len(documents),
            len(reranked),
            (perf_counter() - rerank_started) * 1000,
        )
        return self._format_documents(reranked)

    def _build_chain(self) -> RunnableSequence:
        """Monta o pipeline de execução."""

        llm = ChatOpenAI(
            model=settings.openai_model,
            temperature=settings.openai_temperature,
            max_tokens=settings.openai_max_tokens,
            streaming=True,
            api_key=settings.openai_api_key.get_secret_value(),
            base_url=settings.openai_base_url or None,
        )

        retriever_chain = RunnableLambda(self._retrieve_and_rerank)

        sql_chain = RunnableLambda(
            lambda x: fetch_sql_context(
                x["question"],
                x.get("filters"),
                request_id=str(x.get("request_id") or "n/a"),
            )
        )

        history_chain = RunnableLambda(
            lambda x: self._convert_history(x.get("history", []))
        )

        assembler = RunnableParallel(
            question=RunnableLambda(lambda x: x["question"]),
            history=history_chain,
            context=retriever_chain,
            sql_context=sql_chain,
        )

        return assembler | self.prompt | llm

    async def stream_response(
        self, inputs: Dict[str, Any], request_id: str | None = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """Executa o chain e produz eventos incrementais."""

        effective_request_id = request_id or "n/a"
        started_at = perf_counter()
        normalized_filters = self._normalize_filters(inputs.get("filters"))
        if normalized_filters:
            inputs = {
                **inputs,
                "filters": normalized_filters,
                "request_id": effective_request_id,
            }
        else:
            inputs = {
                **{k: v for k, v in inputs.items() if k != "filters"},
                "request_id": effective_request_id,
            }
        logger.info(
            "🚀 Stream pipeline started | request_id=%s | history_messages=%s | has_filters=%s",
            effective_request_id,
            len(inputs.get("history", [])),
            "filters" in inputs,
        )
        iterator_handler = AsyncIteratorCallbackHandler()
        json_handler = JSONTokenStreamingHandler(iterator_handler)
        chain = self._build_chain()

        task = asyncio.create_task(
            chain.ainvoke(
                inputs,
                config={
                    "callbacks": [json_handler],
                },
            )
        )
        task_error: Exception | None = None

        try:
            async for token in iterator_handler.aiter():
                yield {"type": "token", "value": token}
        except asyncio.CancelledError:
            logger.warning(
                "⚠️ Stream pipeline cancelled | request_id=%s",
                effective_request_id,
            )
            task.cancel()
            raise
        finally:
            # Ensure aiter() waiters are always released, including disconnects.
            iterator_handler.done.set()
            if not task.done():
                task.cancel()
            try:
                with suppress(asyncio.CancelledError):
                    await task
            except Exception as exc:
                task_error = exc

        if task_error is not None:
            logger.exception(
                "❌ Stream chain task failed | request_id=%s | error=%s",
                effective_request_id,
                task_error,
            )
            raise task_error

        logger.info(
            "✅ Stream pipeline finished | request_id=%s | elapsed_ms=%.2f",
            effective_request_id,
            (perf_counter() - started_at) * 1000,
        )
        yield {"type": "end"}

    async def invoke(self, inputs: Dict[str, Any], request_id: str | None = None) -> str:
        """Executa o chain de forma síncrona (sem streaming)."""

        effective_request_id = request_id or "n/a"
        started_at = perf_counter()
        normalized_filters = self._normalize_filters(inputs.get("filters"))
        if normalized_filters:
            inputs = {
                **inputs,
                "filters": normalized_filters,
                "request_id": effective_request_id,
            }
        else:
            inputs = {
                **{k: v for k, v in inputs.items() if k != "filters"},
                "request_id": effective_request_id,
            }
        logger.info(
            "🚀 Query pipeline started | request_id=%s | history_messages=%s | has_filters=%s",
            effective_request_id,
            len(inputs.get("history", [])),
            "filters" in inputs,
        )
        chain = self._build_chain()
        result = await chain.ainvoke(inputs)
        logger.info(
            "✅ Query pipeline finished | request_id=%s | elapsed_ms=%.2f",
            effective_request_id,
            (perf_counter() - started_at) * 1000,
        )
        if isinstance(result, str):
            return result
        if isinstance(result, BaseMessage):
            return str(result.content)
        return str(result)


__all__ = ["ChatbotService"]
