"""Serviço central do chatbot."""

from __future__ import annotations

import asyncio
import logging
from time import perf_counter
from typing import Any, AsyncIterator, Dict, Iterable, List, Sequence

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
            # Sem o autor no cabeçalho o modelo não consegue atribuir a fala a
            # ninguém — era a causa das respostas "não encontrei informações
            # sobre o parlamentar X" mesmo com o trecho dele em mãos.
            speaker = ChatbotService._describe_speaker(metadata)
            if speaker:
                heading += f" • Parlamentar: {speaker}"
            if "date" in metadata:
                heading += f" • Data: {metadata['date']}"
            body = doc.page_content.strip()
            chunks.append(f"{heading}\n{body}")
        return "\n\n".join(chunks)

    @staticmethod
    def _describe_speaker(metadata: Dict[str, Any]) -> str:
        """Descreve o parlamentar de um trecho recuperado."""

        name = str(metadata.get("parliamentarian") or "").strip()
        if not name:
            return ""

        party = str(metadata.get("party") or "").strip().upper()
        state = str(metadata.get("state") or "").strip().upper()

        if party and state:
            return f"{name} ({party}-{state})"
        if party:
            return f"{name} ({party})"
        if state:
            return f"{name} ({state})"
        return name

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

    @staticmethod
    def _prioritize_topic_documents(
        documents: List[Document], topic: str
    ) -> List[Document]:
        """Reordena os documentos: quem menciona o tema literal vem primeiro.

        A busca vetorial sozinha pode enterrar os poucos chunks que citam o
        tema clicado na nuvem ("greve") sob discursos apenas semanticamente
        próximos — era o "diz que não tem a palavra" relatado pelos usuários.
        Ordenação estável: dentro de cada grupo a ordem por similaridade fica.
        """

        needle = topic.casefold()
        with_topic = [d for d in documents if needle in (d.page_content or "").casefold()]
        without_topic = [
            d for d in documents if needle not in (d.page_content or "").casefold()
        ]
        return with_topic + without_topic

    async def _retrieve_and_rerank(self, inputs: Dict[str, Any]) -> str:
        """Recupera documentos, executa reranking e prepara o contexto."""

        request_id = str(inputs.get("request_id") or "n/a")
        stage_started = perf_counter()
        question = inputs["question"]
        topic = str(inputs.get("topic") or "").strip()
        normalized_filters = inputs.get("filters")
        filter_payload = self._build_retriever_filter(normalized_filters)
        search_kwargs: Dict[str, Any] = {}
        if filter_payload:
            search_kwargs["filter"] = filter_payload
        if topic:
            # Com tema conhecido, busca mais candidatos para dar chance aos
            # chunks que citam o termo literal antes do corte do rerank.
            search_kwargs["k"] = max(settings.retriever_k, settings.retriever_topic_k)
        logger.info(
            "🔍 Retrieval started | request_id=%s | has_vector_filter=%s | has_topic=%s",
            request_id,
            bool(filter_payload),
            bool(topic),
        )
        retriever = get_retriever(search_kwargs=search_kwargs or None)
        documents = await retriever.ainvoke(question)
        if topic:
            documents = self._prioritize_topic_documents(list(documents), topic)
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
        formatted = self._format_documents(reranked)
        if topic:
            # Deixa explícito para o modelo que o tema veio de um clique na
            # nuvem de palavras da plataforma (não é invenção do usuário).
            header = (
                "Tema selecionado pelo usuário na nuvem de palavras da "
                f"plataforma: {topic}"
            )
            formatted = f"{header}\n\n{formatted}" if formatted else header
        return formatted

    def _build_chain(self) -> RunnableSequence:
        """Monta o pipeline de execução."""

        llm = ChatOpenAI(
            model=settings.openai_model,
            temperature=settings.openai_temperature,
            max_tokens=settings.openai_max_tokens,
            streaming=True,
            stream_usage=True,
            api_key=settings.openai_api_key.get_secret_value(),
            base_url=settings.openai_base_url or None,
        )

        retriever_chain = RunnableLambda(self._retrieve_and_rerank)

        sql_chain = RunnableLambda(
            lambda x: fetch_sql_context(
                x["question"],
                x.get("filters"),
                request_id=str(x.get("request_id") or "n/a"),
                topic=x.get("topic"),
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
        chain = self._build_chain()

        # chain.astream() é o caminho de streaming nativo do LangChain. O padrão
        # anterior (ainvoke em task + AsyncIteratorCallbackHandler embrulhado num
        # handler custom) parou de streamar em silêncio: o handler não é
        # reconhecido como streaming handler pelo _should_stream, a chamada vira
        # não-streaming e NENHUM token chega ao cliente — a resposta era gerada
        # (usage registrado) mas o usuário via só o indicador de digitação.
        usage: Dict[str, Any] | None = None
        streamed_chars = 0
        try:
            async for chunk in chain.astream(inputs):
                usage_metadata = getattr(chunk, "usage_metadata", None)
                if usage_metadata:
                    usage = {
                        "prompt_tokens": usage_metadata.get("input_tokens"),
                        "completion_tokens": usage_metadata.get("output_tokens"),
                    }
                content = getattr(chunk, "content", chunk)
                if isinstance(content, str) and content:
                    streamed_chars += len(content)
                    yield {"type": "token", "value": content}
        except asyncio.CancelledError:
            logger.warning(
                "⚠️ Stream pipeline cancelled | request_id=%s",
                effective_request_id,
            )
            raise
        except Exception as exc:
            logger.exception(
                "❌ Stream chain failed | request_id=%s | error=%s",
                effective_request_id,
                exc,
            )
            raise

        if streamed_chars == 0:
            # O LLM concluiu sem conteúdo visível (ex.: resposta vazia do
            # provedor). Sem este aviso o cliente ficaria com uma bolha vazia.
            logger.warning(
                "⚠️ Stream finished with empty content | request_id=%s | usage=%s",
                effective_request_id,
                usage,
            )

        logger.info(
            "✅ Stream pipeline finished | request_id=%s | chars=%s | elapsed_ms=%.2f",
            effective_request_id,
            streamed_chars,
            (perf_counter() - started_at) * 1000,
        )
        if usage:
            yield {"type": "usage", **usage}
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
