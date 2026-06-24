"""Aplicação FastAPI dedicada ao chatbot Mamute Político."""

from __future__ import annotations

from contextlib import suppress
import logging

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from .core.database import engine
from .core.config import get_settings
from .routers import chat
from .schemas import HealthcheckResponse

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Inicializa a aplicação FastAPI."""

    settings = get_settings()

    app = FastAPI(
        title="Mamute Político Chatbot",
        description=(
            "Serviço de conversação baseado em LangChain, combinando vetores no "
            "PostgreSQL (pgvector) e consultas SQL diretas às notas taquigráficas."
        ),
        version="0.1.0",
        docs_url="/chat/docs",
        openapi_url="/chat/openapi.json",
        redoc_url="/chat/redoc",        
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(chat.router, prefix="/chat")

    @app.get("/chat/health", response_model=HealthcheckResponse, tags=["infra"])
    async def healthcheck() -> HealthcheckResponse:
        """Verifica o status da API e conectividade com ambos os bancos."""

        db_status = {"mamute_db": "error", "vector_db": "error"}

        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            db_status["mamute_db"] = "ok"

            vector_engine = create_engine(
                settings.pgvector_connection,
                pool_pre_ping=True,
                future=True,
            )
            try:
                with vector_engine.connect() as connection:
                    connection.execute(text("SELECT 1"))
                db_status["vector_db"] = "ok"
            finally:
                with suppress(Exception):
                    vector_engine.dispose()

        except SQLAlchemyError as exc:
            logger.exception("Chatbot healthcheck database connectivity failed")
            raise HTTPException(
                status_code=503,
                detail={
                    "status": "error",
                    "environment": settings.environment,
                    "databases": db_status,
                    "reason": "Falha ao verificar conectividade dos bancos.",
                },
            ) from exc

        return HealthcheckResponse(
            status="ok",
            environment=settings.environment,
            databases=db_status,
        )

    return app


app = create_app()

__all__ = ["app", "create_app"]
