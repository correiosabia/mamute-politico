"""Coleta de emendas parlamentares individuais do Portal da Transparencia.

Emenda orcamentaria (destinacao de verba), nao emenda a proposicao (alteracao
de texto de projeto de lei).

A fonte nao devolve identificador de parlamentar — so `nomeAutor` em texto
livre — entao cada emenda passa pelo casamento por nome de `author_matching`.
O que nao casa e persistido mesmo assim, com `parliamentarian_id` nulo e
`match_status` explicito, para ficar visivel no painel de auditoria.
"""

from __future__ import annotations

import logging
import os
import sys
from collections import Counter
from contextlib import nullcontext
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mamute_scrappers.portal_crawler.author_matching import (  # noqa: E402
    MATCH_STATUS_MANUAL,
    MATCH_STATUS_MATCHED,
    MATCH_STATUS_UNMATCHED,
    ParliamentarianCandidate,
    match_author,
)
from mamute_scrappers.portal_crawler.client import (  # noqa: E402
    PortalTransparenciaClient,
)
from mamute_scrappers.portal_crawler.parsing import (  # noqa: E402
    is_individual_amendment,
    parse_brl,
)

logger = logging.getLogger(__name__)

API_KEY_ENV = "PORTAL_TRANSPARENCIA_API_KEY"
COMMIT_EVERY = 500


def _load_env_file() -> None:
    """Carrega o .env antes de ler a chave da API.

    Nada no processo carrega o .env sozinho: quem faz isso e `db/engine.py`, no
    import. Este crawler le a chave ANTES de tocar no banco, entao sem esta
    chamada a variavel nao existe em producao — onde a chave vive no arquivo, e
    nao no ambiente do container. Localmente o bug fica invisivel se a variavel
    for exportada na mao.

    `override=False` preserva variavel ja exportada no ambiente, mesma politica
    de db/engine.py.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover — dotenv e dependencia declarada
        return

    for env_file in (
        PROJECT_ROOT / "mamute_scrappers" / ".env",
        PROJECT_ROOT / ".env",
        Path.cwd() / ".env",
    ):
        if env_file.exists():
            load_dotenv(env_file, override=False)

ParliamentaryAmendment: Any = None

# Campos que o robo sempre atualiza, mesmo quando houve correcao manual de
# autoria: os valores financeiros mudam ao longo do ano inteiro.
_VALUE_FIELDS = (
    "year",
    "amendment_number",
    "amendment_type",
    "author_name_raw",
    "author_raw",
    "spending_locality",
    "function",
    "subfunction",
    "committed_value",
    "settled_value",
    "paid_value",
    "remainder_inscribed",
    "remainder_cancelled",
    "remainder_paid",
)


def _ensure_model() -> None:
    global ParliamentaryAmendment
    if ParliamentaryAmendment is not None:
        return
    from mamute_scrappers.db.models import (
        ParliamentaryAmendment as ParliamentaryAmendmentRuntime,
    )

    ParliamentaryAmendment = ParliamentaryAmendmentRuntime


def _coerce_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    cleaned = " ".join(str(value).split())
    return cleaned or None


def _parse_int(value: Any) -> Optional[int]:
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def build_payload(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Converte um item cru da API no dicionario que a tabela espera."""
    amendment_code = _coerce_text(item.get("codigoEmenda"))
    if not amendment_code:
        return None

    return {
        "amendment_code": amendment_code,
        "year": _parse_int(item.get("ano")),
        "amendment_number": _coerce_text(item.get("numeroEmenda")),
        "amendment_type": _coerce_text(item.get("tipoEmenda")),
        "author_name_raw": _coerce_text(item.get("nomeAutor")),
        "author_raw": _coerce_text(item.get("autor")),
        "spending_locality": _coerce_text(item.get("localidadeDoGasto")),
        "function": _coerce_text(item.get("funcao")),
        "subfunction": _coerce_text(item.get("subfuncao")),
        "committed_value": parse_brl(item.get("valorEmpenhado")),
        "settled_value": parse_brl(item.get("valorLiquidado")),
        "paid_value": parse_brl(item.get("valorPago")),
        "remainder_inscribed": parse_brl(item.get("valorRestoInscrito")),
        "remainder_cancelled": parse_brl(item.get("valorRestoCancelado")),
        "remainder_paid": parse_brl(item.get("valorRestoPago")),
    }


def upsert_amendment(session: Any, payload: Dict[str, Any]) -> Tuple[Any, bool]:
    """Grava ou atualiza uma emenda, casando pela chave natural do Portal.

    Os valores financeiros sempre sao atualizados, porque mudam ao longo do ano.
    Ja o vinculo com o parlamentar nao e sobrescrito quando `match_status` esta
    em `manual`: correcao humana prevalece sobre o robo.
    """
    if ParliamentaryAmendment is None:
        _ensure_model()

    record = (
        session.query(ParliamentaryAmendment)
        .filter(ParliamentaryAmendment.amendment_code == payload["amendment_code"])
        .one_or_none()
    )

    created = False
    if record is None:
        record = ParliamentaryAmendment(amendment_code=payload["amendment_code"])
        session.add(record)
        created = True

    for field in _VALUE_FIELDS:
        setattr(record, field, payload.get(field))

    if record.match_status != MATCH_STATUS_MANUAL:
        record.parliamentarian_id = payload.get("parliamentarian_id")
        record.match_status = payload.get("match_status")

    if created:
        # Flush apos preencher os campos (match_status e NOT NULL). A sessao do
        # projeto usa autoflush=False e o commit so ocorre a cada COMMIT_EVERY;
        # sem este flush, um mesmo codigo repetido dentro do lote — e o Portal
        # repete registro entre paginas — nao seria encontrado pela consulta
        # acima, viraria duplicata e o commit morreria com UniqueViolation,
        # derrubando o ano inteiro.
        session.flush()

    return record, created


def _load_candidates() -> List[ParliamentarianCandidate]:
    from mamute_scrappers.db import session_scope
    from mamute_scrappers.db.models import Parliamentarian

    with session_scope() as session:
        rows = session.query(
            Parliamentarian.id,
            Parliamentarian.name,
            Parliamentarian.full_name,
        ).all()

    return [ParliamentarianCandidate(id=r[0], name=r[1], full_name=r[2]) for r in rows]


def emendas(
    *,
    ano: Optional[int] = None,
    persist: bool = True,
    dry_run_limit: Optional[int] = None,
) -> None:
    """Coleta emendas individuais de um ano, casa por nome e persiste."""
    ano = ano or date.today().year
    _load_env_file()
    api_key = os.getenv(API_KEY_ENV, "")
    client = PortalTransparenciaClient(api_key)

    candidates = _load_candidates()
    logger.info("Base de parlamentares carregada: %s candidatos.", len(candidates))

    if persist:
        _ensure_model()
        from mamute_scrappers.db import session_scope

        session_context = session_scope()
    else:
        session_context = nullcontext(None)

    tipos_vistos: Counter = Counter()
    status_counter: Counter = Counter()
    total = 0
    individuais = 0
    inserted = 0
    updated = 0
    exemplos_nao_casados: List[str] = []

    with session_context as session:
        for item in client.iter_amendments(ano):
            total += 1
            tipos_vistos[_coerce_text(item.get("tipoEmenda")) or "(vazio)"] += 1

            if not is_individual_amendment(item.get("tipoEmenda")):
                continue

            payload = build_payload(item)
            if payload is None:
                continue
            individuais += 1

            result = match_author(payload["author_name_raw"], candidates)
            payload["parliamentarian_id"] = result.parliamentarian_id
            payload["match_status"] = result.status
            status_counter[result.status] += 1

            if (
                result.status == MATCH_STATUS_UNMATCHED
                and len(exemplos_nao_casados) < 20
            ):
                nome = payload["author_name_raw"]
                if nome and nome not in exemplos_nao_casados:
                    exemplos_nao_casados.append(nome)

            if session is not None:
                _, created = upsert_amendment(session, payload)
                if created:
                    inserted += 1
                else:
                    updated += 1
                # Commit parcial: `session_scope` so commita ao sair do bloco, e
                # um ano inteiro numa transacao unica (~6 mil linhas, medido)
                # some se a rede falhar na ultima das ~400 paginas. Como o
                # upsert e idempotente, retomar apenas reescreve o que ja estava.
                if (inserted + updated) % COMMIT_EVERY == 0:
                    session.commit()

            if dry_run_limit is not None and individuais >= dry_run_limit:
                break

    logger.info("=== Emendas %s ===", ano)
    logger.info("Total de emendas lidas: %s", total)
    logger.info("Emendas individuais: %s", individuais)
    logger.info("Valores de tipoEmenda vistos: %s", dict(tipos_vistos))
    logger.info("Casamento: %s", dict(status_counter))
    if individuais:
        taxa = 100 * status_counter.get(MATCH_STATUS_MATCHED, 0) / individuais
        logger.info("Taxa de casamento: %.1f%%", taxa)
    if exemplos_nao_casados:
        logger.info("Exemplos nao casados: %s", exemplos_nao_casados)
    if persist:
        logger.info("Persistencia: %s inseridas, %s atualizadas.", inserted, updated)
    else:
        logger.info("Modo dry-run: nada foi gravado.")


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        description=(
            "Coleta emendas parlamentares individuais do Portal da Transparencia."
        )
    )
    parser.add_argument("--ano", type=int, help="Ano da coleta (default: ano corrente).")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Nao persiste; apenas reporta o diagnostico.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Interrompe apos N emendas individuais (para diagnostico rapido).",
    )

    args = parser.parse_args()
    emendas(ano=args.ano, persist=not args.dry_run, dry_run_limit=args.limit)
