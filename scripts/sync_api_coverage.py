"""Sincroniza api_coverage com contagens da API aberta da Câmara.

Truque: com itens=1, a página "last" dos links = total de itens. Assim
obtemos a contagem por (ano, siglaTipo) sem baixar tudo.

Uso: DATABASE_URL=... python -m scripts.sync_api_coverage [ano_inicio] [ano_fim]

Senado fica para uma etapa seguinte (API com estrutura diferente).
"""
from __future__ import annotations

import sys
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from sqlalchemy import text
from sqlalchemy.orm import Session

CAMARA_URL = "https://dadosabertos.camara.leg.br/api/v2/proposicoes"
SENADO_URL = "https://legis.senado.leg.br/dadosabertos/materia/pesquisa/lista"
DEFAULT_TYPES = ["PL", "PEC", "PDL", "PLP", "MPV", "PLV"]


def count_senado_materias(payload: dict[str, Any]) -> int:
    """Conta matérias na resposta do Senado (lista Materia)."""
    node = payload.get("PesquisaBasicaMateria") or {}
    materias = node.get("Materias") if isinstance(node, dict) else None
    materia = materias.get("Materia") if isinstance(materias, dict) else None
    if isinstance(materia, list):
        return len(materia)
    return 1 if materia else 0


def fetch_senado_count(year: int, sigla: str, http_get: Callable[..., Any]) -> int:
    resp = http_get(
        SENADO_URL,
        params={"ano": year, "sigla": sigla},
        headers={"accept": "application/json"},
        timeout=25,
    )
    resp.raise_for_status()
    return count_senado_materias(resp.json())


def parse_last_page(payload: dict[str, Any]) -> int:
    """Conta itens a partir do link 'last' (pagina=N com itens=1) ou dos dados."""
    for link in payload.get("links", []) or []:
        if link.get("rel") == "last":
            href = link.get("href") or ""
            pagina = parse_qs(urlparse(href).query).get("pagina", [None])[0]
            if pagina and pagina.isdigit():
                return int(pagina)
    # Sem link 'last': só há a página atual.
    return len(payload.get("dados", []) or [])


def fetch_camara_count(
    year: int, sigla: str, http_get: Callable[..., Any]
) -> int:
    resp = http_get(
        CAMARA_URL,
        params={"ano": year, "siglaTipo": sigla, "itens": 1, "pagina": 1},
        headers={"accept": "application/json"},
        timeout=20,
    )
    resp.raise_for_status()
    return parse_last_page(resp.json())


def upsert_api_coverage(
    session: Session, source: str, year: int, sigla: str, count: int
) -> None:
    session.execute(
        text(
            """
            INSERT INTO api_coverage (source, year, sigla_type, api_count, synced_at)
            VALUES (:source, :year, :sigla, :count, CURRENT_TIMESTAMP)
            ON CONFLICT (source, year, sigla_type) DO UPDATE SET
                api_count = EXCLUDED.api_count,
                synced_at = CURRENT_TIMESTAMP
            """
        ),
        {"source": source, "year": year, "sigla": sigla, "count": count},
    )


def main() -> None:
    import requests

    from api.db.engine import SessionLocal

    start = int(sys.argv[1]) if len(sys.argv) > 1 else 2023
    end = int(sys.argv[2]) if len(sys.argv) > 2 else 2025

    session = SessionLocal()
    try:
        total = 0
        for year in range(start, end + 1):
            for sigla in DEFAULT_TYPES:
                camara = fetch_camara_count(year, sigla, requests.get)
                upsert_api_coverage(session, "camara", year, sigla, camara)
                senado = fetch_senado_count(year, sigla, requests.get)
                upsert_api_coverage(session, "senado", year, sigla, senado)
                total += 2
                print(f"{year} {sigla}: camara={camara} senado={senado}")
        session.commit()
        print(f"api_coverage sincronizado: {total} combinações.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
