"""Aplicação FastAPI para exposição dos dados coletados."""

from fastapi import APIRouter, Depends, FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

try:
    # Permite execução como pacote (api.main).
    from .routers import (
        admin,
        analysis,
        authors_proposition,
        ghost_webhooks,
        projects,
        parliamentarians,
        propositions,
        roll_call_votes,
        speeches_transcripts,
        speeches_transcripts_proposition,
    )
    from .security import verify_token
except ImportError:
    # Permite execução dentro do diretório api/ (python main.py / uvicorn main:app).
    from routers import (
        admin,
        analysis,
        authors_proposition,
        ghost_webhooks,
        projects,
        parliamentarians,
        propositions,
        roll_call_votes,
        speeches_transcripts,
        speeches_transcripts_proposition,
    )
    from security import verify_token


def create_app() -> FastAPI:
    """Cria e configura a aplicação FastAPI."""
    app = FastAPI(
        title="Mamute Político API",
        description="API para consulta das tabelas do projeto Mamute Político.",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url="/api/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    auth_dependencies = [Depends(verify_token)]

    api_router = APIRouter(prefix="/api")

    api_router.include_router(ghost_webhooks.router)
    api_router.include_router(admin.router)

    api_router.include_router(analysis.router, dependencies=auth_dependencies)
    api_router.include_router(parliamentarians.router, dependencies=auth_dependencies)
    api_router.include_router(propositions.router, dependencies=auth_dependencies)
    api_router.include_router(projects.router, dependencies=auth_dependencies)
    api_router.include_router(authors_proposition.router, dependencies=auth_dependencies)
    api_router.include_router(roll_call_votes.router, dependencies=auth_dependencies)
    api_router.include_router(speeches_transcripts.router, dependencies=auth_dependencies)
    api_router.include_router(
        speeches_transcripts_proposition.router, dependencies=auth_dependencies
    )

    @api_router.get("", response_class=HTMLResponse, include_in_schema=False)
    @api_router.get("/", response_class=HTMLResponse, include_in_schema=False)
    def read_api_root() -> str:
        return """
        <!DOCTYPE html>
        <html lang="pt-BR">
            <head>
                <meta charset="utf-8" />
                <title>Mamute Político API</title>
                <style>
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                        background: #0f172a;
                        color: #e2e8f0;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        min-height: 100vh;
                        margin: 0;
                    }
                    .card {
                        background: rgba(15, 23, 42, 0.75);
                        border: 1px solid rgba(148, 163, 184, 0.3);
                        border-radius: 16px;
                        padding: 32px;
                        max-width: 560px;
                        text-align: center;
                        box-shadow: 0 20px 50px rgba(15, 23, 42, 0.4);
                    }
                    h1 {
                        margin-top: 0;
                        font-size: 2.2rem;
                    }
                    p {
                        line-height: 1.6;
                        margin: 16px 0 24px;
                    }
                    a {
                        color: #38bdf8;
                        text-decoration: none;
                        font-weight: 600;
                    }
                    a:hover {
                        text-decoration: underline;
                    }
                </style>
            </head>
            <body>
                <main class="card">
                    <h1>Bem-vindo à Mamute Político API</h1>
                    <p>
                        Consulte a documentação interativa em
                        <a href="/api/docs">/api/docs</a> ou acesse o schema JSON em
                        <a href="/api/openapi.json">/api/openapi.json</a>.
                    </p>
                </main>
            </body>
        </html>
        """

    app.include_router(api_router)

    return app


app = create_app()


__all__ = ["app", "create_app"]
