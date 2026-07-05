"""Cobertura do banco: quanto temos preenchido por ano, casa e tipo.

Casa da proposição é derivada da casa do autor (authors_proposition →
parliamentarian.type). Comparação com a API aberta (percentuais) é uma etapa
seguinte — aqui ficam as contagens do nosso banco.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

# Casa por proposição: senado se houver autor senador; senão câmara se houver
# autor; senão desconhecido. Evita dupla contagem de props multi-autor.
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


def db_coverage(db: Session) -> dict[str, Any]:
    year_house_rows = (
        db.execute(
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
        bucket = by_year.setdefault(
            year, {"camara": 0, "senado": 0, "desconhecido": 0}
        )
        house = row["house"] if row["house"] in bucket else "desconhecido"
        bucket[house] += int(row["n"])

    # Contagens da API aberta da Câmara por ano (se já sincronizadas).
    api_rows = (
        db.execute(
            text(
                "SELECT year, SUM(api_count) AS n FROM api_coverage "
                "WHERE source = 'camara' GROUP BY year"
            )
        )
        .mappings()
        .all()
    )
    api_camara_by_year = {row["year"]: int(row["n"] or 0) for row in api_rows}

    by_year_house = []
    for year, v in by_year.items():
        api_camara = api_camara_by_year.get(year)
        cobertura_pct = (
            round(v["camara"] / api_camara * 100, 1)
            if api_camara
            else None
        )
        by_year_house.append(
            {
                "year": year,
                "camara": v["camara"],
                "senado": v["senado"],
                "desconhecido": v["desconhecido"],
                "total": v["camara"] + v["senado"] + v["desconhecido"],
                "api_camara": api_camara,
                "cobertura_camara_pct": cobertura_pct,
            }
        )
    by_year_house.sort(key=lambda r: (r["year"] is None, r["year"]), reverse=True)

    type_rows = (
        db.execute(
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
        return int(db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one() or 0)

    totals = {
        "proposicoes": _count("proposition"),
        "votacoes": _count("roll_call_votes"),
        "discursos": _count("speeches_transcripts"),
    }

    return {"by_year_house": by_year_house, "by_type": by_type, "totals": totals}
