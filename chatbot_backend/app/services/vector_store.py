"""Fábrica de repositórios vetoriais utilizando pgvector."""

from __future__ import annotations

from functools import lru_cache
import logging
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from langchain_community.vectorstores.pgvector import PGVector
from langchain_core.vectorstores import VectorStoreRetriever
from langchain_openai import OpenAIEmbeddings
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from ..core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


def _with_application_name(url: str) -> str:
    """Garante que o connection string tenha application_name definido."""

    parsed = urlparse(url)
    query_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query_params.setdefault("application_name", settings.application_name)
    new_query = urlencode(query_params, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


@lru_cache
def get_embeddings() -> OpenAIEmbeddings:
    """Retorna o objeto de embeddings configurado."""

    return OpenAIEmbeddings(
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.openai_embeddings_model,
        base_url=settings.openai_base_url or None,
        # Teto de textos por requisição HTTP. É esta trava — e não o tamanho do
        # lote montado pelo script — que impede estourar o limite de tokens da
        # API, já que o número de chunks por discurso varia muito.
        chunk_size=settings.openai_embeddings_batch_size,
    )


@lru_cache
def get_vector_store() -> PGVector:
    """Cria (ou reutiliza) a conexão com o índice vetorial."""

    connection_string = _with_application_name(settings.pgvector_connection)
    parsed = urlparse(connection_string)

    logger.info(
        "🔎 Connecting to Vector DB | host=%s | port=%s | database=%s | collection=%s | application_name=%s",
        parsed.hostname or "unknown",
        parsed.port or "default",
        parsed.path.lstrip("/") or "unknown",
        settings.pgvector_collection_name,
        settings.application_name,
    )

    vector_store = PGVector(
        connection_string=connection_string,
        embedding_function=get_embeddings(),
        collection_name=settings.pgvector_collection_name,
        use_jsonb=True,
    )

    logger.info(
        "✅ Vector DB connected | collection=%s | embedding_model=%s",
        settings.pgvector_collection_name,
        settings.openai_embeddings_model,
    )

    return vector_store


@lru_cache
def get_vector_engine() -> Engine:
    """Engine SQLAlchemy apontando para o banco do índice vetorial.

    O `PGVector` não expõe remoção por metadado — `delete()` só age sobre `ids`.
    Operações de manutenção que precisam filtrar por `cmetadata` usam esta
    engine diretamente.
    """

    return create_engine(
        _with_application_name(settings.pgvector_connection),
        future=True,
    )


def get_retriever(
    search_kwargs: Optional[dict[str, object]] = None,
    *,
    diverse: bool = False,
) -> VectorStoreRetriever:
    """Expõe um retriever com parâmetros padrão.

    `diverse=True` usa MMR: para perguntas panorâmicas (sem filtro de
    parlamentar), a similaridade pura tende a devolver k chunks do MESMO
    orador dominante — caso real: "o que parlamentares falaram sobre a APAE"
    trouxe 5 de 6 chunks de um único deputado. O MMR troca um pouco de
    similaridade por variedade de fontes.
    """

    kwargs: dict[str, object] = {"k": settings.retriever_k}
    if search_kwargs:
        kwargs.update(search_kwargs)

    if diverse:
        # MMR não aceita score_threshold; fetch_k amplia o pool a diversificar.
        kwargs.setdefault("fetch_k", int(kwargs["k"]) * 5)
        kwargs.pop("score_threshold", None)
        search_type = "mmr"
    elif settings.retriever_score_threshold is not None:
        kwargs.setdefault("score_threshold", settings.retriever_score_threshold)
        search_type = "similarity_score_threshold"
    else:
        search_type = "similarity"

    return get_vector_store().as_retriever(
        search_type=search_type,
        search_kwargs=kwargs,
    )


__all__ = [
    "get_embeddings",
    "get_vector_store",
    "get_vector_engine",
    "get_retriever",
]
