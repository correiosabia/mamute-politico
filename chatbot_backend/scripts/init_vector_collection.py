"""Inicializa a coleção vetorial utilizada pelo chatbot."""

from __future__ import annotations

import argparse
from typing import ClassVar, Optional, Tuple

from pathlib import Path
from typing import Optional

from langchain_openai import OpenAIEmbeddings
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import ArgumentError


class InitCollectionConfig(BaseSettings):
    """Configurações mínimas para criação da coleção vetorial."""

    ENV_CANDIDATES: ClassVar[Tuple[str, ...]] = (
        ".env",
        "@.env",
        "chatbot_backend/.env",
        "chatbot_backend/@.env",
    )

    model_config = SettingsConfigDict(
        env_file=ENV_CANDIDATES,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    pgvector_connection: str = Field(..., alias="PGVECTOR_CONNECTION")
    pgvector_collection_name: str = Field(
        default="mamute_chatbot_transcripts", alias="PGVECTOR_COLLECTION"
    )
    application_name: str = Field(
        default="mamute_chatbot_backend", alias="APPLICATION_NAME"
    )
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: Optional[str] = Field(default=None, alias="OPENAI_BASE_URL")
    openai_embeddings_model: str = Field(
        default="text-embedding-3-large", alias="OPENAI_EMBEDDINGS_MODEL"
    )


def _normalize_connection_url(connection: str) -> str:
    url = connection.strip()
    if "://" not in url:
        url = f"postgresql+psycopg://{url}"
    return url


def _safe_connection_display(connection: str) -> str:
    try:
        url = make_url(_normalize_connection_url(connection))
    except ArgumentError:
        return "<PGVECTOR_CONNECTION inválido>"
    return url.render_as_string(hide_password=True)


def _create_engine(connection: str, application_name: str) -> Engine:
    normalized_connection = _normalize_connection_url(connection)
    try:
        url = make_url(normalized_connection)
    except ArgumentError as exc:
        raise SystemExit(
            "PGVECTOR_CONNECTION inválido. Forneça um URL compatível com SQLAlchemy, "
            "por exemplo: postgresql+psycopg://usuario:senha@host:5432/banco"
        ) from exc

    connect_args: dict[str, str] = {}
    if url.get_backend_name().startswith("postgresql"):
        connect_args["application_name"] = application_name
    return create_engine(url, future=True, connect_args=connect_args or None)


def _ensure_extensions(engine: Engine) -> None:
    statements = [
        "CREATE EXTENSION IF NOT EXISTS vector",
        "CREATE EXTENSION IF NOT EXISTS pgcrypto",
    ]
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))


def _get_embedding_dimension(
    config: InitCollectionConfig, force_dimension: Optional[int] = None
) -> int:
    if force_dimension:
        return force_dimension

    if not config.openai_api_key:
        raise SystemExit(
            "OPENAI_API_KEY não encontrado. Defina a variável ou informe --dimension."
        )

    embeddings = OpenAIEmbeddings(
        api_key=config.openai_api_key,
        model=config.openai_embeddings_model,
        base_url=config.openai_base_url or None,
    )
    sample_vector = embeddings.embed_query("teste de dimensão")
    return len(sample_vector)


def _existing_dimension(engine: Engine) -> Optional[int]:
    query = text(
        """
        SELECT atttypmod
        FROM pg_attribute
        WHERE attrelid = 'langchain_pg_embedding'::regclass
          AND attname = 'embedding'
          AND attnum > 0
          AND NOT attisdropped
        """
    )
    with engine.begin() as conn:
        result = conn.execute(query).scalar()
    if result is None or result < 0:
        return None
    return result - 4  # typmod armazena dimensão + 4


def _drop_existing_tables(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS langchain_pg_embedding CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS langchain_pg_collection CASCADE"))


def _ensure_tables(engine: Engine, dimension: int) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS langchain_pg_collection (
                    id bigserial PRIMARY KEY,
                    uuid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
                    name TEXT UNIQUE NOT NULL,
                    cmetadata JSONB,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
                """
            )
        )
        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS langchain_pg_embedding (
                    id bigserial PRIMARY KEY,
                    uuid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
                    custom_id TEXT UNIQUE,
                    collection_id UUID REFERENCES langchain_pg_collection(uuid) ON DELETE CASCADE,
                    embedding VECTOR({dimension}),
                    document TEXT,
                    cmetadata JSONB,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS langchain_pg_embedding_collection_idx
                ON langchain_pg_embedding (collection_id)
                """
            )
        )
        if dimension <= 2000:
            conn.execute(
                text(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1
                            FROM pg_indexes
                            WHERE schemaname = current_schema()
                              AND indexname = 'langchain_pg_embedding_embedding_idx'
                        ) THEN
                            CREATE INDEX langchain_pg_embedding_embedding_idx
                            ON langchain_pg_embedding
                            USING ivfflat (embedding vector_cosine_ops)
                            WITH (lists = 100);
                        END IF;
                    END $$;
                    """
                )
            )
        else:
            print(
                "[aviso] Dimensão do embedding excede 2000; índice IVFFLAT não será criado. "
                "Considere usar um modelo de embeddings menor ou ajustar manualmente a estratégia de indexação."
            )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS langchain_pg_embedding_parliamentarian_idx
                ON langchain_pg_embedding (((cmetadata->>'parliamentarian_id')::bigint))
                WHERE cmetadata ? 'parliamentarian_id'
                """
            )
        )


def _ensure_collection(engine: Engine, collection_name: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO langchain_pg_collection (name, cmetadata)
                VALUES (:name, '{}'::jsonb)
                ON CONFLICT (name) DO NOTHING
                """
            ),
            {"name": collection_name},
        )


def run(force_dimension: Optional[int] = None, reset: bool = False) -> None:
    present_envs = [
        str(Path(candidate).resolve())
        for candidate in InitCollectionConfig.ENV_CANDIDATES
        if Path(candidate).exists()
    ]
    if present_envs:
        print("[debug] Arquivos .env encontrados:", ", ".join(present_envs))
    else:
        print("[debug] Nenhum arquivo .env encontrado nas rotas padrão.")

    config = InitCollectionConfig()
    safe_connection = _safe_connection_display(config.pgvector_connection)
    print("[debug] PGVECTOR_CONNECTION lido:", safe_connection)

    engine = _create_engine(config.pgvector_connection, config.application_name)

    if reset:
        print("[info] Dropando tabelas anteriores antes da recriação.")
        _drop_existing_tables(engine)
    _ensure_extensions(engine)
    target_dimension = _get_embedding_dimension(config, force_dimension)
    existing_dim = None
    try:
        existing_dim = _existing_dimension(engine)
    except Exception:
        existing_dim = None

    if existing_dim is not None and existing_dim != target_dimension:
        print(
            f"Aviso: a coluna existente possui dimensão {existing_dim}, "
            f"enquanto a configuração atual indica {target_dimension}."
        )

    _ensure_tables(engine, target_dimension)
    _ensure_collection(engine, config.pgvector_collection_name)

    print("Coleção vetorial pronta.")
    print(f"- Connection string: {safe_connection}")
    print(f"- Collection name: {config.pgvector_collection_name}")
    print(f"- Dimensão do embedding: {target_dimension}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cria a coleção vetorial utilizada pelo chatbot."
    )
    parser.add_argument(
        "--dimension",
        type=int,
        default=None,
        help=(
            "Sobrescreve a dimensão do vetor (por padrão detectada automaticamente via API de embeddings)."
        ),
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Remove as tabelas existentes antes de criar a coleção.",
    )

    args = parser.parse_args()
    run(force_dimension=args.dimension, reset=args.reset)


if __name__ == "__main__":
    main()
