"""Sincroniza votações nominais (roll call votes) dos parlamentares do Senado."""

from __future__ import annotations

import json
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, ContextManager, Dict, Iterable, List, Optional, Tuple, TypedDict

import requests
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)

SENADO_API_BASE_URL = "https://legis.senado.leg.br/dadosabertos"
SENADO_VOTE_VERSION = "1"
ROLL_CALL_DETAILS_KEY = "roll_call_votes"

class VotePayload(TypedDict, total=False):
    parliamentarian_code: int
    proposition_code: int
    process_id: Optional[int]
    session_code: Optional[int]
    session_vote_code: Optional[int]
    vote_code: Optional[int]
    vote_result: Optional[str]
    vote: Optional[str]
    vote_description: Optional[str]
    vote_full_text: Optional[str]
    vote_link: Optional[str]
    proposition_identification: Optional[str]
    proposition_sigla: Optional[str]
    proposition_number: Optional[int]
    proposition_year: Optional[int]
    proposition_summary: Optional[str]
    proposition_presentation: Optional[date]
    proposition_link: Optional[str]
    session_date: Optional[datetime]


RollCallVoteModel: Any = None
ParliamentarianModel: Any = None
PropositionModel: Any = None
PropositionTypeModel: Any = None
_SESSION_SCOPE: Optional[Callable[[], ContextManager[Session]]] = None

def _ensure_db_dependencies() -> None:
    """Garante o carregamento preguiçoso dos modelos necessários."""
    global RollCallVoteModel, ParliamentarianModel, PropositionModel, PropositionTypeModel, _SESSION_SCOPE
    if RollCallVoteModel is not None and _SESSION_SCOPE is not None:
        return

    try:
        from mamute_scrappers.db.models import (
            Parliamentarian as ParliamentarianModelRuntime,
            Proposition as PropositionModelRuntime,
            PropositionType as PropositionTypeModelRuntime,
            RollCallVote as RollCallVoteModelRuntime,
        )
        from mamute_scrappers.db.session import session_scope as session_scope_runtime
    except ImportError as exc:  # pragma: no cover - depende do ambiente
        raise RuntimeError("Não foi possível carregar dependências de banco.") from exc

    RollCallVoteModel = RollCallVoteModelRuntime
    ParliamentarianModel = ParliamentarianModelRuntime
    PropositionModel = PropositionModelRuntime
    PropositionTypeModel = PropositionTypeModelRuntime
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


def _ensure_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _parse_int(value: Any) -> Optional[int]:
    text = _coerce_text(value)
    if not text:
        return None
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> Optional[date]:
    text = _coerce_text(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _parse_datetime(value: Any) -> Optional[datetime]:
    text = _coerce_text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _request_json(url: str, *, params: Optional[Dict[str, str]] = None) -> Optional[Any]:
    headers = {"Accept": "application/json"}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Falha ao consultar %s: %s", url, exc)
        return None

    try:
        return response.json()
    except ValueError as exc:
        logger.error("Erro ao parsear JSON do Senado (%s): %s", url, exc)
        return None


def _flatten_votes_payload(data: Any) -> List[Dict[str, Any]]:
    """Extrai uma lista de votações do JSON retornado."""
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        candidates: List[Dict[str, Any]] = []
        for key in ("ListaVotacoes", "listaVotacoes", "Votacoes", "votacoes", "Votacao", "votacao"):
            value = data.get(key)
            if isinstance(value, list):
                candidates.extend([item for item in value if isinstance(item, dict)])
            elif isinstance(value, dict):
                nested = _flatten_votes_payload(value)
                if nested:
                    candidates.extend(nested)
        if candidates:
            return candidates

        aggregated: List[Dict[str, Any]] = []
        for value in data.values():
            nested = _flatten_votes_payload(value)
            if nested:
                aggregated.extend(nested)
        return aggregated
    return []


def _build_vote_payload(
    entry: Dict[str, Any],
    parliamentarian_code: int,
) -> Optional[VotePayload]:
    votes_info = entry.get("votos") or entry.get("Votos")
    votes_list = _ensure_list(votes_info)
    selected_vote: Optional[Dict[str, Any]] = None
    for vote_entry in votes_list:
        if not isinstance(vote_entry, dict):
            continue
        code = _parse_int(vote_entry.get("codigoParlamentar") or vote_entry.get("CodigoParlamentar"))
        if code == parliamentarian_code:
            selected_vote = vote_entry
            break

    if selected_vote is None:
        logger.debug(
            "Ignorando votação %s sem voto do parlamentar %s.",
            entry.get("codigoSessaoVotacao"),
            parliamentarian_code,
        )
        return None

    proposition_code = _parse_int(entry.get("codigoMateria") or entry.get("CodigoMateria"))
    if proposition_code is None:
        # Sem código de matéria não conseguimos relacionar com proposições.
        logger.debug(
            "Votação %s ignorada por ausência de código da matéria.",
            entry.get("codigoSessaoVotacao"),
        )
        return None

    process_id = _parse_int(entry.get("idProcesso") or entry.get("IdProcesso"))
    session_code = _parse_int(entry.get("codigoSessao") or entry.get("CodigoSessao"))
    session_vote_code = _parse_int(entry.get("codigoSessaoVotacao") or entry.get("CodigoSessaoVotacao"))
    vote_code = _parse_int(entry.get("codigoVotacaoSve") or entry.get("CodigoVotacaoSve"))
    vote_result = _coerce_text(entry.get("resultadoVotacao") or entry.get("ResultadoVotacao"))
    vote_description = _coerce_text(entry.get("descricaoVotacao") or entry.get("DescricaoVotacao"))

    vote_payload: VotePayload = {
        "parliamentarian_code": parliamentarian_code,
        "proposition_code": proposition_code,
        "process_id": process_id,
        "session_code": session_code,
        "session_vote_code": session_vote_code,
        "vote_code": vote_code,
        "vote_result": vote_result,
        "vote_description": vote_description,
        "vote_full_text": _coerce_text(entry.get("informeLegislativo", {}).get("texto"))
        if isinstance(entry.get("informeLegislativo"), dict)
        else _coerce_text(entry.get("informeLegislativo")),
        "vote": _coerce_text(
            selected_vote.get("siglaVotoParlamentar")
            or selected_vote.get("descricaoVotoParlamentar")
            or selected_vote.get("SiglaVotoParlamentar")
        ),
        "proposition_identification": _coerce_text(entry.get("identificacao") or entry.get("Identificacao")),
        "proposition_sigla": _coerce_text(entry.get("sigla") or entry.get("Sigla")),
        "proposition_number": _parse_int(entry.get("numero") or entry.get("Numero")),
        "proposition_year": _parse_int(entry.get("ano") or entry.get("Ano")),
        "proposition_summary": _coerce_text(entry.get("ementa") or entry.get("Ementa")),
        "proposition_presentation": _parse_date(entry.get("dataApresentacao") or entry.get("DataApresentacao")),
        "session_date": _parse_datetime(entry.get("dataSessao") or entry.get("DataSessao")),
    }

    if vote_code is not None:
        vote_payload["vote_link"] = f"{SENADO_API_BASE_URL}/votacao/{vote_code}?v={SENADO_VOTE_VERSION}"
    elif session_vote_code is not None:
        vote_payload["vote_link"] = (
            f"{SENADO_API_BASE_URL}/votacao?codigoSessaoVotacao={session_vote_code}&v={SENADO_VOTE_VERSION}"
        )

    if proposition_code is not None:
        vote_payload["proposition_link"] = (
            f"https://www25.senado.leg.br/web/atividade/materias/-/materia/{proposition_code}"
        )

    return vote_payload


def _fetch_roll_call_votes(
    parliamentarian_code: int,
    *,
    start_date: Optional[date],
    end_date: Optional[date],
) -> Iterable[VotePayload]:
    params: Dict[str, str] = {"codigoParlamentar": str(parliamentarian_code), "v": SENADO_VOTE_VERSION}
    if start_date is not None:
        params["dataInicio"] = start_date.strftime("%Y-%m-%d")
    if end_date is not None:
        params["dataFim"] = end_date.strftime("%Y-%m-%d")

    url = f"{SENADO_API_BASE_URL}/votacao"
    logger.debug(
        "Consultando votações nominais do parlamentar %s (%s).",
        parliamentarian_code,
        json.dumps(params, ensure_ascii=False),
    )
    data = _request_json(url, params=params)
    if data is None:
        return []

    entries = _flatten_votes_payload(data)
    payloads: List[VotePayload] = []
    for entry in entries:
        payload = _build_vote_payload(entry, parliamentarian_code)
        if payload is not None:
            payloads.append(payload)

    return payloads


def _iter_target_parliamentarians(
    session: Session,
    parliamentarian_code: Optional[int] = None,
) -> List[Any]:
    if ParliamentarianModel is None:
        raise RuntimeError("Dependências de banco não carregadas.")

    query = session.query(ParliamentarianModel)
    if parliamentarian_code is not None:
        query = query.filter(ParliamentarianModel.parliamentarian_code == parliamentarian_code)

    parliamentarians = [
        parliamentarian
        for parliamentarian in query.all()
        if parliamentarian.parliamentarian_code is not None
    ]

    if not parliamentarians and parliamentarian_code is not None:
        logger.warning(
            "Nenhum parlamentar encontrado com o código %s.",
            parliamentarian_code,
        )

    return parliamentarians


def _merge_details(record: Any, payload: VotePayload) -> None:
    if not hasattr(record, "details"):
        return
    if payload.get("session_vote_code") is None and payload.get("vote_code") is None:
        return

    details = record.details or {}
    if not isinstance(details, dict):
        details = {}

    roll_call_data = details.get(ROLL_CALL_DETAILS_KEY) or {}
    if not isinstance(roll_call_data, dict):
        roll_call_data = {}

    roll_call_data.update(
        {
            "last_session_vote_code": payload.get("session_vote_code"),
            "last_vote_code": payload.get("vote_code"),
            "last_vote_result": payload.get("vote_result"),
        }
    )

    details[ROLL_CALL_DETAILS_KEY] = roll_call_data
    record.details = details


def _assign_type(
    session: Session,
    record: Any,
    payload: VotePayload,
) -> None:
    if PropositionTypeModel is None:
        raise RuntimeError("Dependências de banco não carregadas.")

    acronym = payload.get("proposition_sigla")
    if not acronym:
        return

    type_record = (
        session.query(PropositionTypeModel)
        .filter_by(acronym=acronym, type="Senado")
        .order_by(PropositionTypeModel.id.asc())
        .first()
    )
    if type_record is None:
        type_record = PropositionTypeModel(
            acronym=acronym,
            type="Senado",
            name=acronym,
            description=acronym,
        )
        session.add(type_record)
        session.flush()

    record.proposition_type = type_record


def _update_proposition(
    session: Session,
    payload: VotePayload,
) -> Optional[Any]:
    if PropositionModel is None:
        raise RuntimeError("Dependências de banco não carregadas.")

    code = payload.get("proposition_code")
    if code is None:
        return None

    record = session.query(PropositionModel).filter_by(proposition_code=code).one_or_none()
    created = False
    if record is None:
        record = PropositionModel(proposition_code=code)
        session.add(record)
        created = True

    field_values = {
        "title": payload.get("proposition_identification"),
        "link": payload.get("proposition_link"),
        "proposition_acronym": payload.get("proposition_sigla"),
        "proposition_number": payload.get("proposition_number"),
        "presentation_year": payload.get("proposition_year"),
        "summary": payload.get("proposition_summary"),
        "proposition_description": payload.get("proposition_summary"),
    }

    presentation_date = payload.get("proposition_presentation")
    if presentation_date is not None:
        field_values["presentation_date"] = presentation_date
        field_values["presentation_month"] = presentation_date.month

    for field, value in field_values.items():
        if value is None:
            continue
        setattr(record, field, value)

    _merge_details(record, payload)
    _assign_type(session, record, payload)

    session.flush()
    return record


def _upsert_roll_call_vote(
    session: Session,
    parliamentarian: Any,
    proposition: Any,
    payload: VotePayload,
) -> Tuple[Any, bool]:
    if RollCallVoteModel is None:
        raise RuntimeError("Dependências de banco não carregadas.")

    query = (
        session.query(RollCallVoteModel)
        .filter(RollCallVoteModel.parliamentarian_id == parliamentarian.id)
        .filter(RollCallVoteModel.proposition_id == proposition.id)
    )
    vote_link = payload.get("vote_link")
    if vote_link:
        query = query.filter(RollCallVoteModel.link == vote_link)

    record = query.one_or_none()
    created = False
    if record is None:
        record = RollCallVoteModel(
            parliamentarian=parliamentarian,
            proposition=proposition,
        )
        if vote_link:
            record.link = vote_link
        session.add(record)
        created = True

    if payload.get("vote") is not None:
        record.vote = payload["vote"]
    vote_description = payload.get("vote_description") or payload.get("vote_full_text")
    if vote_description is not None:
        record.description = vote_description
    if vote_link and record.link != vote_link:
        record.link = vote_link
    session_dt = payload.get("session_date")
    if session_dt is not None:
        # payload["session_date"] vem como datetime; persistimos só a data.
        record.vote_date = session_dt.date() if hasattr(session_dt, "date") else session_dt

    return record, created


def roll_call_votes(
    *,
    parliamentarian_code: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    persist: bool = True,
    dry_run_limit: Optional[int] = None,
) -> None:
    """Sincroniza votações nominais de parlamentares."""
    logger.info(
        "Iniciando sincronização de votações nominais (persist=%s).",
        persist,
    )

    _ensure_db_dependencies()
    if _SESSION_SCOPE is None:
        raise RuntimeError("Função de sessão do banco não carregada.")

    today = date.today()
    if start_date is None and end_date is None:
        start_date = today.replace(month=1, day=1)
        end_date = today
    elif start_date is None and end_date is not None:
        start_date = end_date - timedelta(days=365)
    elif start_date is not None and end_date is None:
        end_date = today

    processed = 0
    created_votes = 0
    updated_votes = 0

    try:
        with _SESSION_SCOPE() as session:
            parliamentarians = _iter_target_parliamentarians(session, parliamentarian_code)
            if not parliamentarians:
                logger.warning("Nenhum parlamentar elegível para sincronizar votações.")
                return

            for parliamentarian_record in parliamentarians:
                code = parliamentarian_record.parliamentarian_code
                payloads = _fetch_roll_call_votes(code, start_date=start_date, end_date=end_date)
                if not payloads:
                    logger.debug(
                        "Nenhuma votação retornada para o parlamentar %s.",
                        code,
                    )
                    continue

                for payload in payloads:
                    processed += 1
                    if not persist:
                        logger.info(
                            "Payload de votação (dry-run): %s",
                            json.dumps(payload, ensure_ascii=False, default=str),
                        )
                        if dry_run_limit is not None and processed >= dry_run_limit:
                            logger.info("Limite de dry-run atingido (%s). Encerrando.", dry_run_limit)
                            return
                        continue

                    proposition_record = _update_proposition(session, payload)
                    if proposition_record is None:
                        logger.warning(
                            "Não foi possível obter proposição para o código %s.",
                            payload.get("proposition_code"),
                        )
                        continue

                    record, created = _upsert_roll_call_vote(
                        session,
                        parliamentarian_record,
                        proposition_record,
                        payload,
                    )
                    created_votes += int(created)
                    updated_votes += int(not created)
    except KeyboardInterrupt:
        logger.info("Execução interrompida manualmente após %s votações.", processed)
        return

    if processed == 0:
        logger.warning("Nenhuma votação retornada pela API do Senado.")
    elif persist:
        logger.info(
            "Sincronização concluída (%s votações processadas, %s inseridas, %s atualizadas).",
            processed,
            created_votes,
            updated_votes,
        )
    else:
        logger.info("Processamento concluído em modo dry-run (%s votações).", processed)


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Sincroniza votações nominais do Senado.")
    parser.add_argument(
        "--parliamentarian-code",
        type=int,
        help="Filtra por código específico de parlamentar (ex.: 6331).",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        help="Data inicial no formato YYYY-MM-DD (opcional).",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        help="Data final no formato YYYY-MM-DD (opcional).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Não persiste no banco; apenas exibe as votações obtidas.",
    )
    parser.add_argument(
        "--dry-run-limit",
        type=int,
        help="Limita a quantidade de registros exibidos em modo dry-run.",
    )

    args = parser.parse_args()

    def _parse_cli_date(raw: Optional[str]) -> Optional[date]:
        if not raw:
            return None
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError as exc:
            raise SystemExit(f"Data inválida: {raw}. Use YYYY-MM-DD.") from exc

    roll_call_votes(
        parliamentarian_code=args.parliamentarian_code,
        start_date=_parse_cli_date(args.start_date),
        end_date=_parse_cli_date(args.end_date),
        persist=not args.dry_run,
        dry_run_limit=args.dry_run_limit,
    )
