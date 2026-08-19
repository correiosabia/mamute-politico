"""Coleta dos gastos da cota parlamentar (CEAPS) do Senado — CS-57.

Fonte: API JSON de dados abertos administrativos,
https://adm.senado.gov.br/adm-dadosabertos/api/v1/senadores/despesas_ceaps/{ano}
(~24 mil itens/ano, cobertura 2008->hoje, atualizada diariamente). Preferida ao
CSV do portal LAI, que vem em latin-1 e identifica o senador so por nome; aqui
`codSenador` e o mesmo CodigoParlamentar que guardamos em parliamentarian_code
para type='Senador' — join direto, sem casamento por nome.

Documento fiscal: o id do PDF de download do portal NAO existe nesta API (nem
no CSV) — e um terceiro espaco de ids que so aparece nas paginas HTML. Por
decisao da spec (CS-57), `document_url` aponta a pagina de detalhe do portal,
que e deterministica por senador/categoria/mes e deixa o comprovante a um
clique. O mapeamento tipoDespesa -> categoria do portal foi levantado
empiricamente em 19/08/2026; tipo sem mapeamento fica sem url.
"""

from __future__ import annotations

import logging
import sys
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import requests  # noqa: E402

from mamute_scrappers.expenses.upsert import (  # noqa: E402
    COMMIT_EVERY,
    sequenced_key,
    upsert_expense,
)

logger = logging.getLogger(__name__)

API_URL = (
    "https://adm.senado.gov.br/adm-dadosabertos/api/v1/senadores/despesas_ceaps/{ano}"
)
DETAIL_URL = (
    "https://www6g.senado.leg.br/transparencia/sen/{cod}/ceaps/{categoria}"
    "/detalhe/?mesAno={mes:02d}/{ano}"
)
REQUEST_TIMEOUT = 120
HOUSE = "senado"
TIPO_NAO_INFORMADO = "Não informado"

# Prefixo normalizado do tipoDespesa -> id de categoria nas paginas do portal
# (www6g.senado.leg.br/transparencia/sen/{cod}/ceaps/{categoria}/). Levantado
# na pagina de um senador em 19/08/2026; os ids pulam 6 e 7 na propria fonte.
_CATEGORIA_POR_PREFIXO = (
    ("aluguel de imoveis", 1),
    ("aquisicao de material de consumo", 2),
    ("locomocao, hospedagem", 3),
    ("contratacao de consultorias", 4),
    ("divulgacao da atividade parlamentar", 5),
    ("passagens aereas", 8),
    ("servicos de seguranca privada", 9),
)


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.strip().lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def portal_category_for(tipo_despesa: Optional[str]) -> Optional[int]:
    if not tipo_despesa:
        return None
    normalized = _normalize(tipo_despesa)
    for prefix, categoria in _CATEGORIA_POR_PREFIXO:
        if normalized.startswith(prefix):
            return categoria
    return None


def detail_url(
    cod_senador: int, tipo_despesa: Optional[str], ano: int, mes: int
) -> Optional[str]:
    categoria = portal_category_for(tipo_despesa)
    if categoria is None:
        return None
    return DETAIL_URL.format(cod=cod_senador, categoria=categoria, mes=mes, ano=ano)


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    cleaned = " ".join(str(value).split())
    return cleaned or None


def _decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        # str() antes de Decimal: a API devolve float, e Decimal(float) faria
        # a expansao binaria (1387.75 -> 1387.7499999...).
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _date(value: Any) -> Optional[date]:
    text = _text(value)
    if text is None:
        return None
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def build_payload(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Converte um item da API no payload de upsert_expense.

    Devolve tambem `cod_senador`, que o laco troca por parliamentarian_id.
    """
    source_id = item.get("id")
    ano = item.get("ano")
    mes = item.get("mes")
    cod_senador = item.get("codSenador")
    net_value = _decimal(item.get("valorReembolsado"))
    if source_id is None or ano is None or mes is None or net_value is None:
        return None
    if cod_senador is None:
        return None

    tipo = _text(item.get("tipoDespesa"))

    return {
        "house": HOUSE,
        "source_key": str(source_id),
        "cod_senador": int(cod_senador),
        "year": int(ano),
        "month": int(mes),
        # NOT NULL no banco; a fonte publica tipo nulo em ~0,3% dos itens e a
        # linha e fato publico que nao deve sumir por isso.
        "expense_type": tipo or TIPO_NAO_INFORMADO,
        "supplier_name": _text(item.get("fornecedor")),
        "supplier_id": _text(item.get("cpfCnpj")),
        "document_number": _text(item.get("documento")),
        "document_date": _date(item.get("data")),
        "details": _text(item.get("detalhamento")),
        "document_value": None,  # o Senado so publica o reembolsado
        "glosa_value": None,
        "net_value": net_value,
        "document_url": detail_url(int(cod_senador), tipo, int(ano), int(mes)),
    }


def fetch_year(ano: int) -> List[Dict[str, Any]]:
    url = API_URL.format(ano=ano)
    logger.info("Buscando %s", url)
    resp = requests.get(
        url, headers={"Accept": "application/json"}, timeout=REQUEST_TIMEOUT
    )
    resp.raise_for_status()
    return resp.json()


def _senator_map(session: Any) -> Dict[int, int]:
    """parliamentarian_code -> id interno, so senadores."""
    from mamute_scrappers.db.models import Parliamentarian

    rows = (
        session.query(Parliamentarian.parliamentarian_code, Parliamentarian.id)
        .filter(Parliamentarian.type == "Senador")
        .filter(Parliamentarian.parliamentarian_code.isnot(None))
        .all()
    )
    return {int(code): pid for code, pid in rows}


def expenses(
    *,
    ano: Optional[int] = None,
    persist: bool = True,
    dry_run_limit: Optional[int] = None,
) -> None:
    """Coleta os gastos CEAPS de um ano e persiste por upsert idempotente."""
    ano = ano or date.today().year

    if persist:
        from mamute_scrappers.db import session_scope

        session_context = session_scope()
    else:
        from contextlib import nullcontext

        session_context = nullcontext(None)

    items = fetch_year(ano)
    logger.info("Itens recebidos: %s", len(items))

    total = 0
    sem_vinculo = 0
    sem_url = 0
    inserted = 0
    updated = 0
    # Ids da API medidos unicos em 2025, mas a unicidade e garantia nossa.
    from collections import Counter

    seen_keys: Counter = Counter()

    with session_context as session:
        senators = _senator_map(session) if session is not None else {}
        logger.info("Senadores na base: %s", len(senators))

        for item in items:
            payload = build_payload(item)
            if payload is None:
                continue
            total += 1

            payload["source_key"] = sequenced_key(
                payload["source_key"], seen_keys
            )
            cod_senador = payload.pop("cod_senador")
            payload["parliamentarian_id"] = senators.get(cod_senador)
            if payload["parliamentarian_id"] is None:
                sem_vinculo += 1
            if payload["document_url"] is None:
                sem_url += 1

            if session is not None:
                _, created = upsert_expense(session, payload)
                if created:
                    inserted += 1
                else:
                    updated += 1
                if (inserted + updated) % COMMIT_EVERY == 0:
                    session.commit()

            if dry_run_limit is not None and total >= dry_run_limit:
                break

    logger.info("=== Cota Senado (CEAPS) %s ===", ano)
    logger.info("Itens processados: %s", total)
    logger.info("Senador fora da base: %s", sem_vinculo)
    logger.info("Sem url de documento (tipo sem categoria): %s", sem_url)
    if persist:
        logger.info("Persistencia: %s inseridos, %s atualizados.", inserted, updated)
    else:
        logger.info("Modo dry-run: nada foi gravado.")


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        description="Coleta gastos da cota parlamentar (CEAPS) do Senado."
    )
    parser.add_argument("--ano", type=int, help="Ano da coleta (default: corrente).")
    parser.add_argument("--dry-run", action="store_true", help="Nao persiste.")
    parser.add_argument("--limit", type=int, help="Para apos N itens.")

    args = parser.parse_args()
    expenses(ano=args.ano, persist=not args.dry_run, dry_run_limit=args.limit)
