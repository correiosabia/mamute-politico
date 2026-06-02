"""Sincroniza presenca em sessoes de plenario da Camara dos Deputados."""

from __future__ import annotations

import json
import logging
import sys
import time
import unicodedata
from contextlib import nullcontext
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import (
    Any,
    Callable,
    ContextManager,
    Dict,
    Iterable,
    List,
    Optional,
    Tuple,
    TYPE_CHECKING,
    TypedDict,
)

import requests
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)

CAMARA_API_BASE_URL = "https://dadosabertos.camara.leg.br/api/v2"
CAMARA_EVENTOS_ENDPOINT = f"{CAMARA_API_BASE_URL}/eventos"
CAMARA_DEPUTADOS_ENDPOINT = f"{CAMARA_API_BASE_URL}/deputados"

PAGE_SIZE = 100
REQUEST_DELAY = 0.1
PLENARY_ORGAN_ACRONYM = "PLEN"
CLOSED_EVENT_STATUS_CODE = "4"
DELIBERATIVE_EVENT_TYPE_CODES = "110,204"
SOURCE_DESCRIPTION_PREFIX = "Camara evento"

if TYPE_CHECKING:  # pragma: no cover
    from mamute_scrappers.db.models import (
        Parliamentarian as ParliamentarianModel,
        PlenaryAttendance as PlenaryAttendanceModel,
    )
    from mamute_scrappers.db.session import session_scope as session_scope_type

    SessionScopeCallable = Callable[[], ContextManager["Session"]]
else:
    ParliamentarianModel = Any
    PlenaryAttendanceModel = Any
    SessionScopeCallable = Callable[[], ContextManager[Session]]

Parliamentarian: Any = None
PlenaryAttendance: Any = None
_SESSION_SCOPE: Optional[SessionScopeCallable] = None


class PlenaryAttendancePayload(TypedDict, total=False):
    event_id: int
    parliamentarian_code: int
    date: date
    description: str
    session_attendance: str
    daily_attendance_justification: Optional[str]


def _ensure_db_dependencies() -> None:
    global Parliamentarian, PlenaryAttendance, _SESSION_SCOPE
    if _SESSION_SCOPE is not None:
        return

    try:
        from mamute_scrappers.db.models import (
            Parliamentarian as ParliamentarianModelRuntime,
            PlenaryAttendance as PlenaryAttendanceModelRuntime,
        )
        from mamute_scrappers.db.session import session_scope as session_scope_runtime
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Nao foi possivel carregar dependencias de banco.") from exc

    Parliamentarian = ParliamentarianModelRuntime
    PlenaryAttendance = PlenaryAttendanceModelRuntime
    _SESSION_SCOPE = session_scope_runtime


def _normalize_text(value: Optional[str]) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(normalized.lower().split())


def _coerce_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = " ".join(value.split())
    else:
        cleaned = " ".join(str(value).split())
    return cleaned or None


def _parse_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: Any) -> Optional[datetime]:
    text = _coerce_text(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _parse_date(value: Any) -> Optional[date]:
    dt = _parse_datetime(value)
    return dt.date() if dt else None


def _ensure_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _request_json(
    url: str,
    *,
    params: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    headers = {"Accept": "application/json"}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Falha ao consultar %s: %s", url, exc)
        return None

    try:
        data = response.json()
    except ValueError as exc:
        logger.error("Erro ao parsear JSON da Camara (%s): %s", url, exc)
        return None

    if not isinstance(data, dict):
        logger.error("Resposta JSON inesperada da Camara (%s): tipo %s", url, type(data))
        return None

    return data


def _source_description_prefix(event_id: int) -> str:
    return f"{SOURCE_DESCRIPTION_PREFIX} {event_id}"


def _build_source_description(event: Dict[str, Any]) -> str:
    event_id = _parse_int(event.get("id"))
    if event_id is None:
        raise ValueError("Evento sem id.")

    event_type = _coerce_text(event.get("descricaoTipo"))
    prefix = _source_description_prefix(event_id)
    return f"{prefix}: {event_type}" if event_type else prefix


def _is_plenary_event(event: Dict[str, Any]) -> bool:
    for organ in _ensure_list(event.get("orgaos")):
        if not isinstance(organ, dict):
            continue
        acronym = _coerce_text(organ.get("sigla"))
        if acronym == PLENARY_ORGAN_ACRONYM:
            return True
    return False


def _is_deliberative_plenary_event(event: Dict[str, Any]) -> bool:
    if not _is_plenary_event(event):
        return False

    event_type = _normalize_text(_coerce_text(event.get("descricaoTipo")))
    if "sessao deliberativa" not in event_type:
        return False
    if "nao deliberativa" in event_type:
        return False

    status = _normalize_text(_coerce_text(event.get("situacao")))
    return status.startswith("encerrada")


def _fetch_event_detail(event_id: int) -> Optional[Dict[str, Any]]:
    data = _request_json(f"{CAMARA_EVENTOS_ENDPOINT}/{event_id}")
    if data is None:
        return None

    dados = data.get("dados")
    if not isinstance(dados, dict):
        logger.error("Resposta sem campo 'dados' para evento %s", event_id)
        return None

    return dados


def _fetch_event_participants(event_id: int) -> List[Dict[str, Any]]:
    data = _request_json(f"{CAMARA_EVENTOS_ENDPOINT}/{event_id}/deputados")
    if data is None:
        return []

    dados = data.get("dados")
    if not isinstance(dados, list):
        return []

    return [item for item in dados if isinstance(item, dict)]


def _iter_plenary_events(
    data_inicio: str,
    *,
    data_fim: Optional[str] = None,
    event_id: Optional[int] = None,
) -> Iterable[Dict[str, Any]]:
    if event_id is not None:
        event = _fetch_event_detail(event_id)
        if event is None:
            return
        if _is_deliberative_plenary_event(event):
            yield event
        else:
            logger.warning(
                "Evento %s nao e sessao deliberativa encerrada do Plenario.",
                event_id,
            )
        return

    page = 1
    while True:
        params: Dict[str, Any] = {
            "dataInicio": data_inicio,
            "codSituacao": CLOSED_EVENT_STATUS_CODE,
            "codTipoEvento": DELIBERATIVE_EVENT_TYPE_CODES,
            "pagina": page,
            "itens": PAGE_SIZE,
            "ordem": "ASC",
            "ordenarPor": "dataHoraInicio",
        }
        if data_fim:
            params["dataFim"] = data_fim

        data = _request_json(CAMARA_EVENTOS_ENDPOINT, params=params)
        if data is None:
            break

        dados = data.get("dados")
        if not isinstance(dados, list) or not dados:
            break

        for item in dados:
            if isinstance(item, dict) and _is_deliberative_plenary_event(item):
                yield item

        links = data.get("links", [])
        has_next = any(
            isinstance(link, dict) and link.get("rel") == "next"
            for link in links
        )
        if not has_next:
            break

        page += 1
        time.sleep(REQUEST_DELAY)


def _iter_deputy_codes_for_date(event_date: date) -> Iterable[int]:
    page = 1
    date_text = event_date.isoformat()

    while True:
        params = {
            "dataInicio": date_text,
            "dataFim": date_text,
            "pagina": page,
            "itens": PAGE_SIZE,
            "ordem": "ASC",
            "ordenarPor": "nome",
        }
        data = _request_json(CAMARA_DEPUTADOS_ENDPOINT, params=params)
        if data is None:
            break

        dados = data.get("dados")
        if not isinstance(dados, list) or not dados:
            break

        for item in dados:
            if not isinstance(item, dict):
                continue
            code = _parse_int(item.get("id"))
            if code is not None:
                yield code

        links = data.get("links", [])
        has_next = any(
            isinstance(link, dict) and link.get("rel") == "next"
            for link in links
        )
        if not has_next:
            break

        page += 1
        time.sleep(REQUEST_DELAY)


def _extract_participant_codes(participants: Iterable[Dict[str, Any]]) -> set[int]:
    codes: set[int] = set()
    for participant in participants:
        code = _parse_int(participant.get("id"))
        if code is not None:
            codes.add(code)
    return codes


def _build_attendance_payloads(
    event: Dict[str, Any],
    participants: Iterable[Dict[str, Any]],
    chamber_parliamentarian_codes: Iterable[int],
) -> List[PlenaryAttendancePayload]:
    event_id = _parse_int(event.get("id"))
    if event_id is None:
        return []

    event_date = _parse_date(event.get("dataHoraInicio"))
    if event_date is None:
        return []

    present_codes = _extract_participant_codes(participants)
    all_codes = {int(code) for code in chamber_parliamentarian_codes}
    all_codes.update(present_codes)
    if not all_codes:
        return []

    source_description = _build_source_description(event)
    event_type = _coerce_text(event.get("descricaoTipo"))
    event_description = _coerce_text(event.get("descricao"))
    event_context = " - ".join(part for part in (event_type, event_description) if part)

    payloads: List[PlenaryAttendancePayload] = []
    for code in sorted(all_codes):
        is_present = code in present_codes
        payloads.append(
            {
                "event_id": event_id,
                "parliamentarian_code": code,
                "date": event_date,
                "description": source_description,
                "session_attendance": "Presente" if is_present else "Ausente",
                "daily_attendance_justification": event_context,
            }
        )

    return payloads


def _debug_print_payload(payload: PlenaryAttendancePayload) -> None:
    debug_repr = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    print(debug_repr)


def _find_parliamentarian(session: Session, parliamentarian_code: int) -> Optional[Any]:
    if Parliamentarian is None:
        raise RuntimeError("Dependencias de banco nao carregadas.")

    query = session.query(Parliamentarian).filter(
        Parliamentarian.parliamentarian_code == parliamentarian_code
    )
    deputy = (
        query.filter(Parliamentarian.type == "Deputado")
        .order_by(Parliamentarian.id)
        .first()
    )
    if deputy is not None:
        return deputy
    return query.order_by(Parliamentarian.id).first()


def _upsert_plenary_attendance(
    session: Session,
    payload: PlenaryAttendancePayload,
) -> Tuple[Optional[Any], bool]:
    if PlenaryAttendance is None or Parliamentarian is None:
        raise RuntimeError("Dependencias de banco nao carregadas.")

    parliamentarian_code = payload.get("parliamentarian_code")
    event_id = payload.get("event_id")
    if parliamentarian_code is None:
        raise ValueError("Payload sem 'parliamentarian_code'.")
    if event_id is None:
        raise ValueError("Payload sem 'event_id'.")

    parliamentarian = _find_parliamentarian(session, int(parliamentarian_code))
    if parliamentarian is None:
        logger.warning(
            "Deputado %s nao encontrado no banco (evento %s)",
            parliamentarian_code,
            event_id,
        )
        return None, False

    description_prefix = _source_description_prefix(int(event_id))
    record = (
        session.query(PlenaryAttendance)
        .filter(PlenaryAttendance.parliamentarian_id == parliamentarian.id)
        .filter(PlenaryAttendance.description.like(f"{description_prefix}%"))
        .order_by(PlenaryAttendance.id)
        .first()
    )
    created = False
    if record is None:
        record = PlenaryAttendance(parliamentarian_id=parliamentarian.id)
        session.add(record)
        created = True

    record.date = payload.get("date")
    record.description = payload.get("description")
    record.session_attendance = payload.get("session_attendance")
    record.daily_attendance_justification = payload.get(
        "daily_attendance_justification"
    )

    return record, created


def plenary_attendance(
    *,
    data_inicio: Optional[str] = None,
    data_fim: Optional[str] = None,
    event_id: Optional[int] = None,
    persist: bool = True,
    interactive: bool = False,
    include_absences: bool = True,
) -> None:
    """Busca presenca de deputados em sessoes deliberativas do Plenario."""
    if persist:
        _ensure_db_dependencies()
        if _SESSION_SCOPE is None:
            raise RuntimeError("Funcao de sessao do banco nao carregada.")

    if data_inicio is None:
        data_inicio = (date.today() - timedelta(days=30)).isoformat()
    if data_fim is None:
        data_fim = date.today().isoformat()

    logger.info(
        "Iniciando sincronizacao de presenca em plenario da Camara "
        "(data_inicio=%s, data_fim=%s, event_id=%s, persist=%s)",
        data_inicio,
        data_fim,
        event_id,
        persist,
    )

    processed = 0
    inserted = 0
    updated = 0
    skipped = 0
    deputy_codes_by_date: Dict[date, List[int]] = {}

    try:
        session_context = (
            _SESSION_SCOPE() if persist and _SESSION_SCOPE else nullcontext(None)
        )
        with session_context as session:
            for event in _iter_plenary_events(
                data_inicio,
                data_fim=data_fim,
                event_id=event_id,
            ):
                parsed_event_id = _parse_int(event.get("id"))
                event_date = _parse_date(event.get("dataHoraInicio"))
                if parsed_event_id is None or event_date is None:
                    continue

                participants = _fetch_event_participants(parsed_event_id)
                chamber_codes: Iterable[int]
                if include_absences:
                    if event_date not in deputy_codes_by_date:
                        deputy_codes_by_date[event_date] = list(
                            _iter_deputy_codes_for_date(event_date)
                        )
                    chamber_codes = deputy_codes_by_date[event_date]
                else:
                    chamber_codes = []

                payloads = _build_attendance_payloads(event, participants, chamber_codes)
                logger.info(
                    "Evento %s (%s): %s registros de presenca/ausencia",
                    parsed_event_id,
                    event_date,
                    len(payloads),
                )

                for payload in payloads:
                    processed += 1
                    if interactive or not persist:
                        _debug_print_payload(payload)
                        if interactive:
                            try:
                                input(
                                    "Pressione ENTER para continuar; "
                                    "Ctrl+C para sair."
                                )
                            except (KeyboardInterrupt, EOFError):
                                logger.info("Execucao interrompida pelo usuario.")
                                return

                    if persist:
                        if session is None:
                            raise RuntimeError(
                                "Sessao de banco indisponivel para persistencia."
                            )
                        record, created = _upsert_plenary_attendance(session, payload)
                        if record is None:
                            skipped += 1
                        elif created:
                            inserted += 1
                        else:
                            updated += 1

    except KeyboardInterrupt:
        logger.info("Execucao interrompida pelo usuario apos %s registros.", processed)
        return

    if processed == 0:
        logger.warning("Nenhuma presenca de plenario retornada pela Camara.")
    elif persist:
        logger.info(
            "Sincronizacao concluida: %s inseridos, %s atualizados, %s ignorados, %s total",
            inserted,
            updated,
            skipped,
            processed,
        )
    else:
        logger.info("Processamento concluido em modo dry-run (%s registros)", processed)


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(
        description="Sincroniza presenca em sessoes de plenario da Camara dos Deputados."
    )
    parser.add_argument(
        "--data-inicio",
        type=str,
        help="Data inicial no formato YYYY-MM-DD (default: ultimos 30 dias).",
    )
    parser.add_argument(
        "--data-fim",
        type=str,
        help="Data final no formato YYYY-MM-DD (default: hoje).",
    )
    parser.add_argument(
        "--event-id",
        type=int,
        help="Sincroniza apenas um evento especifico da Camara.",
    )
    parser.add_argument(
        "--present-only",
        action="store_true",
        help=(
            "Persiste apenas deputados presentes, "
            "sem inferir ausencias pelo universo oficial."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Nao persiste no banco; apenas exibe os payloads.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Pausa apos cada registro para inspecao manual.",
    )

    args = parser.parse_args()

    plenary_attendance(
        data_inicio=args.data_inicio,
        data_fim=args.data_fim,
        event_id=args.event_id,
        persist=not args.dry_run,
        interactive=args.interactive,
        include_absences=not args.present_only,
    )
