"""Rotina diária (04h) que preenche os caches dos painéis admin.

Roda no container dos scrappers (único com cron). NÃO pode importar `api.*` —
o container só tem `mamute_scrappers/`. Por isso a lógica de cobertura e as
funções de contagem das APIs abertas são reimplementadas aqui em SQL cru /
funções puras (mesma filosofia da duplicação de models api↔scrappers).

Faz três coisas, cada uma isolada (uma falha não aborta as outras):

  1. api_coverage  — contagens das APIs abertas (Câmara/Senado) por ano/tipo.
  2. coverage_snapshot — resultado já computado da cobertura do banco (pesado
     ao vivo por causa do EXISTS por proposição), gravado como um único JSON.
  3. usd_brl_rate  — cotação USD→BRL do dia via API pública.

A API (container `api`) só LÊ essas tabelas — resposta instantânea.

Uso:
    python -m mamute_scrappers.scripts.refresh_admin_caches
    python -m mamute_scrappers.scripts.refresh_admin_caches --coverage-start 2018
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import date, datetime
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("refresh_admin_caches")

CAMARA_URL = "https://dadosabertos.camara.leg.br/api/v2/proposicoes"
SENADO_URL = "https://legis.senado.leg.br/dadosabertos/materia/pesquisa/lista"
USD_BRL_URL = "https://economia.awesomeapi.com.br/last/USD-BRL"
DEFAULT_TYPES = ["PL", "PEC", "PDL", "PLP", "MPV", "PLV"]

# Casa por proposição: senado se houver autor senador; senão câmara se houver
# autor; senão desconhecido. ESPELHA api/services/admin_coverage.py::_HOUSE_EXPR
# — manter os dois em sincronia.
_HOUSE_EXPR = """
    CASE
        WHEN EXISTS (
            SELECT 1 FROM authors_proposition ap
            JOIN parliamentarian par ON par.id = ap.parliamentarian_id
            WHERE ap.proposition_id = p.id
              AND lower(COALESCE(par.type, '')) LIKE '%senad%'
        ) THEN 'senado'
        WHEN EXISTS (
            SELECT 1 FROM authors_proposition ap WHERE ap.proposition_id = p.id
        ) THEN 'camara'
        ELSE 'desconhecido'
    END
"""


# --------------------------------------------------------------------------- #
# Contagens das APIs abertas (funções puras, testáveis com http_get fake).
# Duplicadas de scripts/sync_api_coverage.py (que importa api.* e não roda aqui).
# --------------------------------------------------------------------------- #
def count_senado_materias(payload: dict[str, Any]) -> int:
    node = payload.get("PesquisaBasicaMateria") or {}
    materias = node.get("Materias") if isinstance(node, dict) else None
    materia = materias.get("Materia") if isinstance(materias, dict) else None
    if isinstance(materia, list):
        return len(materia)
    return 1 if materia else 0


def parse_last_page(payload: dict[str, Any]) -> int:
    for link in payload.get("links", []) or []:
        if link.get("rel") == "last":
            href = link.get("href") or ""
            pagina = parse_qs(urlparse(href).query).get("pagina", [None])[0]
            if pagina and pagina.isdigit():
                return int(pagina)
    return len(payload.get("dados", []) or [])


def fetch_camara_count(year: int, sigla: str, http_get: Callable[..., Any]) -> int:
    resp = http_get(
        CAMARA_URL,
        params={"ano": year, "siglaTipo": sigla, "itens": 1, "pagina": 1},
        headers={"accept": "application/json"},
        timeout=20,
    )
    resp.raise_for_status()
    return parse_last_page(resp.json())


def fetch_senado_count(year: int, sigla: str, http_get: Callable[..., Any]) -> int:
    resp = http_get(
        SENADO_URL,
        params={"ano": year, "sigla": sigla},
        headers={"accept": "application/json"},
        timeout=25,
    )
    resp.raise_for_status()
    return count_senado_materias(resp.json())


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


def sync_api_coverage(
    session: Session,
    http_get: Callable[..., Any],
    start: int,
    end: int,
) -> int:
    total = 0
    for year in range(start, end + 1):
        for sigla in DEFAULT_TYPES:
            try:
                camara = fetch_camara_count(year, sigla, http_get)
                upsert_api_coverage(session, "camara", year, sigla, camara)
                senado = fetch_senado_count(year, sigla, http_get)
                upsert_api_coverage(session, "senado", year, sigla, senado)
                total += 2
            except Exception:  # noqa: BLE001 — uma combinação não pode abortar o resto
                logger.exception("Falha ao sincronizar api_coverage %s/%s", year, sigla)
    return total


# --------------------------------------------------------------------------- #
# Cobertura do banco (espelha api/services/admin_coverage.py::db_coverage).
# --------------------------------------------------------------------------- #
def build_coverage_payload(session: Session) -> dict[str, Any]:
    year_house_rows = (
        session.execute(
            text(
                f"""
                SELECT year, house, COUNT(*) AS n FROM (
                    SELECT p.id AS id, p.presentation_year AS year, {_HOUSE_EXPR} AS house
                    FROM proposition p
                ) sub
                GROUP BY year, house
                """
            )
        )
        .mappings()
        .all()
    )

    by_year: dict[Any, dict[str, int]] = {}
    for row in year_house_rows:
        year = row["year"]
        bucket = by_year.setdefault(year, {"camara": 0, "senado": 0, "desconhecido": 0})
        house = row["house"] if row["house"] in bucket else "desconhecido"
        bucket[house] += int(row["n"])

    api_rows = (
        session.execute(
            text(
                "SELECT source, year, SUM(api_count) AS n FROM api_coverage "
                "GROUP BY source, year"
            )
        )
        .mappings()
        .all()
    )
    api_camara_by_year: dict[Any, int] = {}
    api_senado_by_year: dict[Any, int] = {}
    for row in api_rows:
        target = api_senado_by_year if row["source"] == "senado" else api_camara_by_year
        target[row["year"]] = int(row["n"] or 0)

    by_year_house = []
    for year, v in by_year.items():
        api_camara = api_camara_by_year.get(year)
        api_senado = api_senado_by_year.get(year)
        by_year_house.append(
            {
                "year": year,
                "camara": v["camara"],
                "senado": v["senado"],
                "desconhecido": v["desconhecido"],
                "total": v["camara"] + v["senado"] + v["desconhecido"],
                "api_camara": api_camara,
                "cobertura_camara_pct": (
                    round(v["camara"] / api_camara * 100, 1) if api_camara else None
                ),
                "api_senado": api_senado,
                "cobertura_senado_pct": (
                    round(v["senado"] / api_senado * 100, 1) if api_senado else None
                ),
            }
        )
    by_year_house.sort(key=lambda r: (r["year"] is None, r["year"]), reverse=True)

    type_rows = (
        session.execute(
            text(
                """
                SELECT COALESCE(pt.acronym, pt.name, '—') AS type, COUNT(*) AS n
                FROM proposition p
                LEFT JOIN proposition_type pt ON pt.id = p.proposition_type_id
                GROUP BY COALESCE(pt.acronym, pt.name, '—')
                ORDER BY n DESC
                """
            )
        )
        .mappings()
        .all()
    )
    by_type = [{"type": row["type"], "count": int(row["n"])} for row in type_rows]

    def _count(table: str) -> int:
        return int(session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one() or 0)

    totals = {
        "proposicoes": _count("proposition"),
        "votacoes": _count("roll_call_votes"),
        "discursos": _count("speeches_transcripts"),
    }

    return {"by_year_house": by_year_house, "by_type": by_type, "totals": totals}


def store_coverage_snapshot(session: Session, payload: dict[str, Any]) -> None:
    """Substitui o snapshot (mantemos só a linha mais recente)."""
    session.execute(text("DELETE FROM coverage_snapshot"))
    session.execute(
        text(
            "INSERT INTO coverage_snapshot (payload, computed_at) "
            "VALUES (CAST(:payload AS JSONB), CURRENT_TIMESTAMP)"
        ),
        {"payload": json.dumps(payload)},
    )


# --------------------------------------------------------------------------- #
# Câmbio USD→BRL do dia.
# --------------------------------------------------------------------------- #
def fetch_usd_brl_bid(http_get: Callable[..., Any]) -> float:
    resp = http_get(USD_BRL_URL, timeout=10)
    resp.raise_for_status()
    return float(resp.json()["USDBRL"]["bid"])


def store_usd_brl_rate(session: Session, bid: float, today: date) -> None:
    session.execute(
        text(
            """
            INSERT INTO usd_brl_rate (rate_date, bid, fetched_at)
            VALUES (:d, :bid, CURRENT_TIMESTAMP)
            ON CONFLICT (rate_date) DO UPDATE SET
                bid = EXCLUDED.bid,
                fetched_at = CURRENT_TIMESTAMP
            """
        ),
        {"d": today, "bid": bid},
    )


# --------------------------------------------------------------------------- #
def main() -> None:
    import requests

    from mamute_scrappers.db.session import get_session

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )

    current_year = datetime.now().year
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage-start", type=int, default=2019)
    parser.add_argument("--coverage-end", type=int, default=current_year)
    args = parser.parse_args()

    session = get_session()
    try:
        # 1) APIs abertas → api_coverage
        try:
            n = sync_api_coverage(
                session, requests.get, args.coverage_start, args.coverage_end
            )
            session.commit()
            logger.info("api_coverage: %s combinações sincronizadas.", n)
        except Exception:  # noqa: BLE001
            session.rollback()
            logger.exception("api_coverage falhou.")

        # 2) Snapshot da cobertura do banco
        try:
            payload = build_coverage_payload(session)
            store_coverage_snapshot(session, payload)
            session.commit()
            logger.info(
                "coverage_snapshot atualizado (%s anos, %s tipos).",
                len(payload["by_year_house"]),
                len(payload["by_type"]),
            )
        except Exception:  # noqa: BLE001
            session.rollback()
            logger.exception("coverage_snapshot falhou.")

        # 3) Câmbio do dia
        try:
            bid = fetch_usd_brl_bid(requests.get)
            store_usd_brl_rate(session, bid, datetime.now().date())
            session.commit()
            logger.info("usd_brl_rate do dia = %s", bid)
        except Exception:  # noqa: BLE001
            session.rollback()
            logger.exception("usd_brl_rate falhou.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
