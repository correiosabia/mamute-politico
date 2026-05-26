"""Sincroniza tipos de proposições da Câmara dos Deputados."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Callable, ContextManager, Dict, Iterable, List, Optional, TYPE_CHECKING, TypedDict

import requests
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)

CAMARA_API_BASE_URL = "https://dadosabertos.camara.leg.br/api/v2"
CAMARA_TYPES_ENDPOINT = f"{CAMARA_API_BASE_URL}/referencias/proposicoes/siglaTipo"

if TYPE_CHECKING:  # pragma: no cover
    from mamute_scrappers.db.models import PropositionType as PropositionTypeModel
    from mamute_scrappers.db.session import session_scope as session_scope_type

    SessionScopeCallable = Callable[[], ContextManager["Session"]]
else:
    PropositionTypeModel = Any
    SessionScopeCallable = Callable[[], ContextManager[Session]]

PropositionType: Any = None
_SESSION_SCOPE: Optional[SessionScopeCallable] = None


class PropositionTypePayload(TypedDict, total=False):
    acronym: str
    description: Optional[str]
    type: str
    name: Optional[str]
    proposition_type_code: Optional[str]


PROPOSITION_TYPE_MUTABLE_FIELDS = ["acronym", "description", "type", "name", "proposition_type_code"]


def _ensure_db_dependencies() -> None:
    global PropositionType, _SESSION_SCOPE
    if _SESSION_SCOPE is not None:
        return

    try:
        from mamute_scrappers.db.models import PropositionType as PropositionTypeModelRuntime
        from mamute_scrappers.db.session import session_scope as session_scope_runtime
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Não foi possível carregar dependências de banco.") from exc

    PropositionType = PropositionTypeModelRuntime
    _SESSION_SCOPE = session_scope_runtime


def _normalize_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


def _coerce_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return _normalize_text(value)
    return _normalize_text(str(value))


def _request_json(url: str) -> Optional[Any]:
    headers = {"Accept": "application/json"}
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Falha ao consultar %s: %s", url, exc)
        return None

    try:
        return response.json()
    except ValueError as exc:
        logger.error("Erro ao parsear JSON da Câmara (%s): %s", url, exc)
        return None


def _normalize_item(item: Any) -> Optional[PropositionTypePayload]:
    if not isinstance(item, dict):
        return None

    acronym_raw = item.get("sigla") or item.get("Sigla")
    if not isinstance(acronym_raw, str):
        return None
    acronym = acronym_raw.strip()
    if not acronym:
        return None

    cod_raw = item.get("cod")
    proposition_type_code = None
    if isinstance(cod_raw, int):
        proposition_type_code = str(cod_raw)
    elif isinstance(cod_raw, str) and cod_raw.strip():
        proposition_type_code = cod_raw.strip()

    name_raw = item.get("nome") or item.get("Nome")
    name = name_raw.strip() if isinstance(name_raw, str) else None

    description_raw = item.get("descricao") or item.get("Descricao")
    description = description_raw.strip() if isinstance(description_raw, str) else None

    payload: PropositionTypePayload = {
        "acronym": acronym,
        "description": description,
        "type": "Camara",
        "name": name or acronym,
        "proposition_type_code": proposition_type_code,
    }

    return payload


def _iter_payloads(data: Any) -> Iterable[PropositionTypePayload]:
    if not isinstance(data, dict):
        logger.warning("Resposta da Câmara não é um objeto JSON")
        return

    dados = data.get("dados")
    if not isinstance(dados, list):
        logger.warning("Resposta da Câmara sem campo 'dados' ou tipo inválido")
        return

    for item in dados:
        payload = _normalize_item(item)
        if payload:
            yield payload


def _debug_print(payload: PropositionTypePayload) -> None:
    debug_repr = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    print(debug_repr)


def _upsert_proposition_type(session: Session, payload: PropositionTypePayload) -> Any:
    acronym = payload.get("acronym")
    if not acronym:
        raise ValueError("Payload sem 'acronym'.")

    if PropositionType is None:
        raise RuntimeError("Dependências de banco não carregadas.")

    proposition_type_code = payload.get("proposition_type_code")
    query = session.query(PropositionType).filter_by(type="Camara")
    if proposition_type_code:
        query = query.filter_by(proposition_type_code=proposition_type_code)
    else:
        query = query.filter_by(acronym=acronym)

    record = query.order_by(PropositionType.id.asc()).first()
    if record is None:
        record = PropositionType(acronym=acronym, type="Camara")
        session.add(record)

    for field in PROPOSITION_TYPE_MUTABLE_FIELDS:
        if field in payload:
            setattr(record, field, payload[field])

    logger.debug("Tipo de proposição %s (Câmara) sincronizado.", acronym)
    return record


def proposition_type(*, persist: bool = True, interactive: bool = False) -> None:
    """Sincroniza os tipos de proposição fornecidos pela Câmara dos Deputados."""
    logger.info("Iniciando sincronização de tipos de proposição (Câmara).")

    data = _request_json(CAMARA_TYPES_ENDPOINT)
    if data is None:
        logger.warning("Resposta vazia da API de tipos de proposição.")
        return

    _ensure_db_dependencies()
    if _SESSION_SCOPE is None:
        raise RuntimeError("Função de sessão do banco não carregada.")

    payloads = list(_iter_payloads(data))
    if not payloads:
        logger.warning("Nenhum tipo de proposição retornado pela Câmara.")
        return

    processed = 0

    with _SESSION_SCOPE() as session:
        for payload in payloads:
            processed += 1
            if interactive or not persist:
                _debug_print(payload)
                if interactive:
                    try:
                        input("Pressione ENTER para continuar; Ctrl+C para sair.")
                    except (KeyboardInterrupt, EOFError):
                        logger.info("Execução interrompida pelo usuário.")
                        return
            if persist:
                _upsert_proposition_type(session, payload)

    if persist:
        logger.info("Sincronização de tipos concluída (%s registros).", processed)
    else:
        logger.info("Execução em modo dry-run concluída (%s registros).", processed)


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Sincroniza tipos de proposição da Câmara dos Deputados.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Não persiste no banco; apenas exibe os registros.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Pausa entre cada registro para inspeção manual.",
    )

    args = parser.parse_args()

    proposition_type(persist=not args.dry_run, interactive=args.interactive)
