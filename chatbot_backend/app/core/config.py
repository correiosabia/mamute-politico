"""Configurações carregadas a partir de variáveis de ambiente."""

from functools import lru_cache
from typing import List, Optional

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações gerais da aplicação."""

    model_config = SettingsConfigDict(
        env_file=(".env", "@.env", "chatbot_backend/.env", "chatbot_backend/@.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: str = Field(default="local", alias="APP_ENV")
    application_name: str = Field(
        default="mamute_chatbot_backend", alias="APPLICATION_NAME"
    )
    openai_api_key: SecretStr = Field(..., alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    openai_temperature: float = Field(default=0.2, alias="OPENAI_TEMPERATURE")
    openai_max_tokens: int = Field(default=1024, alias="OPENAI_MAX_TOKENS")
    openai_embeddings_model: str = Field(
        default="text-embedding-3-large", alias="OPENAI_EMBEDDINGS_MODEL"
    )

    database_url: str = Field(..., alias="DATABASE_URL")
    pgvector_connection: str = Field(..., alias="PGVECTOR_CONNECTION")
    pgvector_collection_name: str = Field(
        default="mamute_chatbot_transcripts", alias="PGVECTOR_COLLECTION"
    )

    retriever_k: int = Field(default=6, alias="RETRIEVER_K")
    retriever_score_threshold: float = Field(
        default=0.35, alias="RETRIEVER_SCORE_THRESHOLD"
    )

    sql_context_limit: int = Field(default=5, alias="SQL_CONTEXT_LIMIT")
    sql_min_keyword_length: int = Field(default=4, alias="SQL_MIN_KEYWORD_LENGTH")
    sql_keyword_stopwords: List[str] = Field(
        default_factory=lambda: [
            "que",
            "para",
            "como",
            "qual",
            "quem",
            "sobre",
            "mais",
            "menos",
            "quando",
            "onde",
            "porque",
            "porquê",
            "por que",
        ],
        alias="SQL_KEYWORD_STOPWORDS",
    )
    sql_frequency_limit: int = Field(default=5, alias="SQL_FREQUENCY_LIMIT")
    sql_keywords_limit: int = Field(default=8, alias="SQL_KEYWORDS_LIMIT")
    sql_entities_limit: int = Field(default=6, alias="SQL_ENTITIES_LIMIT")
    sql_propositions_limit: int = Field(default=6, alias="SQL_PROPOSITIONS_LIMIT")

    rerank_top_k: int = Field(default=5, alias="RERANK_TOP_K", ge=1)

    chatbot_quota_enabled: bool = Field(
        default=False, alias="MAMUTE_CHATBOT_QUOTA_ENABLED"
    )
    chatbot_default_monthly_limit: int = Field(
        default=0, alias="MAMUTE_CHATBOT_DEFAULT_MONTHLY_LIMIT"
    )
    tier_limits_json: str = Field(default="", alias="MAMUTE_TIER_LIMITS_JSON")
    chatbot_monthly_limits_json: str = Field(
        default="", alias="MAMUTE_CHATBOT_MONTHLY_LIMITS_JSON"
    )
    chatbot_quota_fail_open: bool = Field(
        default=False, alias="MAMUTE_CHATBOT_QUOTA_FAIL_OPEN"
    )

    ghost_base_url: Optional[str] = Field(default=None, alias="GHOST_BASE_URL")
    prefix_url: Optional[str] = Field(default=None, alias="PREFIX_URL")
    ghost_members_api_audience: Optional[str] = Field(
        default=None, alias="GHOST_MEMBERS_API_AUDIENCE"
    )
    ghost_members_api_issuer: Optional[str] = Field(
        default=None, alias="GHOST_MEMBERS_API_ISSUER"
    )
    ghost_jwks_path: str = Field(
        default="members/.well-known/jwks.json", alias="GHOST_JWKS_PATH"
    )

    tracing_enabled: bool = Field(default=False, alias="LANGCHAIN_TRACING_V2")
    tracing_project: str = Field(default="mamute-chatbot", alias="LANGCHAIN_PROJECT")


@lru_cache
def get_settings() -> Settings:
    """Retorna uma instância única de Settings."""

    return Settings()  # type: ignore [call-arg]


__all__ = ["Settings", "get_settings"]
