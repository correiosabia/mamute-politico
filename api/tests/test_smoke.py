"""Smoke tests: garantem que a aplicacao FastAPI sobe e expoe rotas corretamente.

Cobertura intencional:
- Detecta ImportError em qualquer router/modulo (regressao de empacotamento).
- Detecta rotas que sumiram do `/api/...` (regressao de wiring).
- Detecta routers que esquecem de declarar prefix (rotas vazando fora de /api/).
- Detecta quebra do schema OpenAPI (parametros invalidos, response models bugados).

Nao testam logica de negocio nem hit em DB; sao testes de fronteira que rodam
em < 1s no CI e bloqueiam deploy quando o app sequer instancia.
"""
from __future__ import annotations

import importlib

import pytest


def test_app_instantiates() -> None:
    """O app FastAPI deve poder ser importado sem erro."""
    from api.main import app

    assert app is not None
    assert app.title == "Mamute Político API"


def test_all_routers_importable() -> None:
    """Cada router declarado em api/routers/ deve importar sem ImportError.

    Pega bugs como o que ocorreu nos scrappers (commit 0531302):
    imports relativos quebrando porque o pacote nao foi instalado certo.
    """
    routers = [
        "analysis",
        "authors_proposition",
        "parliamentarians",
        "projects",
        "propositions",
        "roll_call_votes",
        "speeches_transcripts",
        "speeches_transcripts_proposition",
    ]
    for name in routers:
        module = importlib.import_module(f"api.routers.{name}")
        assert hasattr(module, "router"), f"api.routers.{name} nao expoe `router`"


def test_critical_routes_registered() -> None:
    """Rotas chave devem estar registradas sob /api/ (sem isso, UI quebra)."""
    from api.main import app

    paths = {route.path for route in app.routes if hasattr(route, "path")}
    expected = {
        "/api/parliamentarians/",
        "/api/propositions/",
        "/api/projects/me/favorites",
        "/api/projects/me/dashboard-stats",
        "/api/projects/me/dashboard-activity",
    }
    missing = expected - paths
    assert not missing, f"Rotas esperadas nao registradas: {sorted(missing)}"


def test_no_routes_outside_api_prefix() -> None:
    """Apenas rotas internas do FastAPI (docs, openapi) podem existir fora de /api/."""
    from api.main import app

    allowed_outside = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
    leaked = []
    for route in app.routes:
        path = getattr(route, "path", None)
        if path is None:
            continue
        if not path.startswith("/api") and path not in allowed_outside:
            leaked.append(path)
    assert not leaked, f"Rotas vazando fora de /api/: {leaked}"


def test_openapi_schema_generates() -> None:
    """O schema OpenAPI deve ser gerado sem erro (pega Pydantic models quebrados)."""
    from api.main import app

    schema = app.openapi()
    assert schema["info"]["title"] == "Mamute Político API"
    assert "paths" in schema
    assert len(schema["paths"]) > 0


@pytest.mark.parametrize(
    "path",
    [
        "/api/projects/me/favorites",
        "/api/projects/me/dashboard-stats",
        "/api/projects/me/dashboard-activity",
        "/api/parliamentarians/",
        "/api/propositions/",
    ],
)
def test_protected_get_routes_block_anonymous(path: str) -> None:
    """Rotas GET sensiveis devem rejeitar request sem credencial.

    Tres possibilidades aceitas:
      - 401 (caminho ideal: HTTPException explicita do verify_token)
      - 403 (Forbidden — token presente mas insuficiente)
      - 422 com erro localizado em ['header','authorization'] (FastAPI tratando
        Authorization como required Field; semanticamente errado mas funcional —
        request e bloqueado)

    Bloqueia: 200 (rota aberta sem auth!), 5xx (crash) e 422 que nao seja
    relacionado ao header de auth (mascarando rota aberta que falhou por outro
    motivo).
    """
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    response = client.get(path)
    code = response.status_code

    if code in {401, 403}:
        return  # caminho ideal

    if code == 422:
        # Aceita 422 SO se o detail aponta pra ['header', 'authorization'].
        try:
            body = response.json()
        except ValueError:
            body = {}
        details = body.get("detail", []) if isinstance(body, dict) else []
        is_auth_related = any(
            isinstance(d, dict)
            and "loc" in d
            and "authorization" in [str(x).lower() for x in d.get("loc", [])]
            for d in details
        )
        assert is_auth_related, (
            f"GET {path} retornou 422 nao relacionado a auth — possivelmente "
            f"rota aberta que falhou por outro motivo: {response.text[:300]}"
        )
        return

    pytest.fail(
        f"GET {path} retornou {code} sem auth (esperado 401/403/422-auth, "
        f"NAO 200/5xx): {response.text[:200]}"
    )
