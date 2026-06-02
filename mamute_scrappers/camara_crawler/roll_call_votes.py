"""Sincroniza votações nominais (roll call votes) dos parlamentares da Câmara dos Deputados."""

from __future__ import annotations

import json
import logging
import sys
import time
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
from sqlalchemy import func
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)

CAMARA_API_BASE_URL = "https://dadosabertos.camara.leg.br/api/v2"
CAMARA_VOTACOES_ENDPOINT = f"{CAMARA_API_BASE_URL}/votacoes"

REQUEST_DELAY = 0.1  # Delay entre requests (segundos)
PAGE_SIZE = 50

if TYPE_CHECKING:  # pragma: no cover - apenas para tipagem
    from mamute_scrappers.db.models import (
        Parliamentarian as ParliamentarianModel,
        Proposition as PropositionModel,
        PropositionType as PropositionTypeModel,
        RollCallVote as RollCallVoteModel,
    )
    from mamute_scrappers.db.session import session_scope as session_scope_type

    SessionScopeCallable = Callable[[], ContextManager["Session"]]
else:
    ParliamentarianModel = Any
    PropositionModel = Any
    PropositionTypeModel = Any
    RollCallVoteModel = Any
    SessionScopeCallable = Callable[[], ContextManager[Session]]

RollCallVote: Any = None
Parliamentarian: Any = None
Proposition: Any = None
PropositionType: Any = None
_SESSION_SCOPE: Optional[SessionScopeCallable] = None


class VotePayload(TypedDict, total=False):
    votacao_id: str
    parlamentarian_code: int
    proposition_code: Optional[int]
    vote: str
    description: Optional[str]
    link: str
    vote_date: Optional[datetime]


def _ensure_db_dependencies() -> None:
    global RollCallVote, Parliamentarian, Proposition, PropositionType, _SESSION_SCOPE
    if _SESSION_SCOPE is not None:
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

    RollCallVote = RollCallVoteModelRuntime
    Parliamentarian = ParliamentarianModelRuntime
    Proposition = PropositionModelRuntime
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


def _request_json(url: str, *, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
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
        logger.error("Erro ao parsear JSON da Câmara (%s): %s", url, exc)
        return None

    if not isinstance(data, dict):
        logger.error("Resposta JSON inesperada da Câmara (%s): tipo %s", url, type(data))
        return None

    return data


def _get_last_vote_date(session: Session) -> Optional[date]:
    """Busca a data da última votação salva no banco (Câmara)."""
    if RollCallVote is None or Parliamentarian is None:
        raise RuntimeError("Dependências de banco não carregadas.")

    # Buscar última votação de deputados (type='Deputado')
    last_vote = (
        session.query(RollCallVote)
        .join(Parliamentarian)
        .filter(Parliamentarian.type == "Deputado")
        .order_by(RollCallVote.created_at.desc())
        .first()
    )

    if last_vote and last_vote.created_at:
        return last_vote.created_at.date()

    return None


def _fetch_votacoes_list(
    data_inicio: str,
    page: int = 1,
    data_fim: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Busca lista paginada de votações."""
    params = {
        "dataInicio": data_inicio,
        "ordem": "ASC",
        "ordenarPor": "dataHoraRegistro",
        "pagina": page,
        "itens": PAGE_SIZE,
    }
    if data_fim:
        params["dataFim"] = data_fim

    logger.debug(
        "Buscando votações (dataInicio=%s, dataFim=%s, página=%s)",
        data_inicio,
        data_fim,
        page,
    )
    return _request_json(CAMARA_VOTACOES_ENDPOINT, params=params)


def _fetch_votacao_detail(votacao_id: str) -> Optional[Dict[str, Any]]:
    """Busca detalhes de uma votação específica."""
    url = f"{CAMARA_VOTACOES_ENDPOINT}/{votacao_id}"

    logger.debug("Buscando detalhes da votação %s", votacao_id)
    data = _request_json(url)

    if data is None:
        return None

    dados = data.get("dados")
    if not isinstance(dados, dict):
        logger.error("Resposta sem campo 'dados' para votação %s", votacao_id)
        return None

    return dados


def _fetch_votacao_votos(votacao_id: str) -> List[Dict[str, Any]]:
    """Busca votos individuais de uma votação."""
    url = f"{CAMARA_VOTACOES_ENDPOINT}/{votacao_id}/votos"

    logger.debug("Buscando votos da votação %s", votacao_id)
    data = _request_json(url)

    if data is None:
        return []

    dados = data.get("dados")
    if not isinstance(dados, list):
        return []

    return dados


def _iter_votacoes_paginated(
    data_inicio: str,
    data_fim: Optional[str] = None,
) -> Iterable[Tuple[str, Dict[str, Any], List[Dict[str, Any]]]]:
    """Itera sobre votações com paginação.

    Yields:
        Tuple[votacao_id, detail, votos]: ID, detalhes e lista de votos
    """
    page = 1
    total_fetched = 0

    while True:
        data = _fetch_votacoes_list(data_inicio, page, data_fim=data_fim)

        if data is None:
            logger.warning("Falha ao buscar página %s", page)
            break

        dados = data.get("dados")
        if not isinstance(dados, list) or not dados:
            logger.debug("Página %s sem dados", page)
            break

        page_count = 0

        for votacao_basic in dados:
            if not isinstance(votacao_basic, dict):
                continue

            votacao_id = votacao_basic.get("id")
            if not votacao_id:
                continue

            page_count += 1
            total_fetched += 1

            # Buscar detalhes
            detail = _fetch_votacao_detail(votacao_id)
            if detail is None:
                logger.warning("Falha ao buscar detalhes da votação %s", votacao_id)
                continue

            if REQUEST_DELAY > 0:
                time.sleep(REQUEST_DELAY)

            # Buscar votos
            votos = _fetch_votacao_votos(votacao_id)

            if REQUEST_DELAY > 0:
                time.sleep(REQUEST_DELAY)

            # Só retornar se tiver votos (votação nominal)
            if votos:
                yield votacao_id, detail, votos
            else:
                logger.debug("Votação %s sem votos individuais (simbólica)", votacao_id)

        logger.info("Página %s processada (%s votações)", page, page_count)

        # Verificar se tem próxima página
        links = data.get("links", [])
        has_next = any(
            isinstance(link, dict) and link.get("rel") == "next"
            for link in links
        )

        if not has_next:
            logger.debug("Última página alcançada (página %s)", page)
            break

        page += 1

    logger.info("Total de votações nominais obtidas: %s", total_fetched)


def _extract_proposition_from_votacao(detail: Dict[str, Any]) -> Optional[int]:
    """Extrai ID da proposição principal de uma votação."""
    proposicoes_afetadas = detail.get("proposicoesAfetadas", [])

    if not isinstance(proposicoes_afetadas, list) or not proposicoes_afetadas:
        return None

    # Pegar primeira proposição afetada
    primeira = proposicoes_afetadas[0]
    if not isinstance(primeira, dict):
        return None

    return _parse_int(primeira.get("id"))


def _build_vote_payloads(
    votacao_id: str,
    detail: Dict[str, Any],
    votos: List[Dict[str, Any]],
) -> List[VotePayload]:
    """Constrói payloads de votos a partir dos dados da API."""
    proposition_code = _extract_proposition_from_votacao(detail)
    description = _coerce_text(detail.get("descricao"))
    vote_date = _parse_datetime(detail.get("dataHoraRegistro"))
    link = f"{CAMARA_VOTACOES_ENDPOINT}/{votacao_id}"

    payloads: List[VotePayload] = []

    for voto in votos:
        if not isinstance(voto, dict):
            continue

        deputado = voto.get("deputado_")
        if not isinstance(deputado, dict):
            continue

        parlamentarian_code = _parse_int(deputado.get("id"))
        if parlamentarian_code is None:
            continue

        tipo_voto = _coerce_text(voto.get("tipoVoto"))
        if not tipo_voto:
            continue

        payload: VotePayload = {
            "votacao_id": votacao_id,
            "parlamentarian_code": parlamentarian_code,
            "proposition_code": proposition_code,
            "vote": tipo_voto,
            "description": description,
            "link": link,
            "vote_date": vote_date,
        }

        payloads.append(payload)

    return payloads


def _debug_print_payload(payload: VotePayload) -> None:
    debug_repr = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    print(debug_repr)


def _get_or_create_proposition(session: Session, proposition_code: int) -> Optional[Any]:
    """Busca proposição no banco ou cria registro básico se não existir."""
    if Proposition is None:
        raise RuntimeError("Dependências de banco não carregadas.")

    proposition = (
        session.query(Proposition)
        .filter_by(proposition_code=proposition_code)
        .one_or_none()
    )

    if proposition is not None:
        return proposition

    # Criar registro básico
    logger.info("Criando proposição %s (referenciada em votação)", proposition_code)
    proposition = Proposition(
        proposition_code=proposition_code,
        link=f"https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={proposition_code}",
    )
    session.add(proposition)
    session.flush()

    return proposition


def _upsert_roll_call_vote(
    session: Session,
    payload: VotePayload,
) -> Tuple[Any, bool]:
    """Insere ou atualiza voto nominal."""
    if RollCallVote is None or Parliamentarian is None:
        raise RuntimeError("Dependências de banco não carregadas.")

    parlamentarian_code = payload.get("parlamentarian_code")
    if parlamentarian_code is None:
        raise ValueError("Payload sem 'parlamentarian_code'.")

    # Buscar deputado
    parliamentarian = (
        session.query(Parliamentarian)
        .filter_by(parliamentarian_code=parlamentarian_code)
        .one_or_none()
    )

    if parliamentarian is None:
        logger.warning(
            "Deputado %s não encontrado no banco (votação %s)",
            parlamentarian_code,
            payload.get("votacao_id"),
        )
        return None, False

    # Buscar/criar proposição
    proposition = None
    proposition_code = payload.get("proposition_code")
    if proposition_code is not None:
        proposition = _get_or_create_proposition(session, proposition_code)

    # Buscar voto existente
    query = (
        session.query(RollCallVote)
        .filter(RollCallVote.parliamentarian_id == parliamentarian.id)
    )

    if proposition is not None:
        query = query.filter(RollCallVote.proposition_id == proposition.id)

    link = payload.get("link")
    if link:
        query = query.filter(RollCallVote.link == link)

    record = query.one_or_none()
    created = False

    if record is None:
        record = RollCallVote(
            parliamentarian=parliamentarian,
            proposition=proposition,
        )
        session.add(record)
        created = True

    # Atualizar campos
    record.vote = payload.get("vote")
    record.description = payload.get("description")
    record.link = link
    vote_date = payload.get("vote_date")
    if vote_date is not None:
        # payload["vote_date"] vem como datetime (dataHoraRegistro tem hora).
        record.vote_date = vote_date.date() if hasattr(vote_date, "date") else vote_date

    return record, created


def roll_call_votes(
    *,
    data_inicio: Optional[str] = None,
    data_fim: Optional[str] = None,
    persist: bool = True,
    interactive: bool = False,
) -> None:
    """Busca votações nominais da Câmara e opcionalmente salva/atualiza o banco.

    Args:
        data_inicio: Data inicial no formato YYYY-MM-DD (default: últimos 30 dias)
        data_fim: Data final no formato YYYY-MM-DD (opcional; permite fatiar o
            backfill por janelas e evitar transações gigantes)
        persist: Se False, apenas exibe payloads (dry-run)
        interactive: Pausa após cada voto
    """
    logger.info(
        "Iniciando sincronização de votações nominais da Câmara (persist=%s)",
        persist,
    )

    _ensure_db_dependencies()
    if _SESSION_SCOPE is None:
        raise RuntimeError("Função de sessão do banco não carregada.")

    # Determinar data inicial
    if data_inicio is None:
        if persist:
            with _SESSION_SCOPE() as session:
                last_date = _get_last_vote_date(session)
                if last_date:
                    # Buscar desde 1 dia antes (margem de segurança)
                    start_date = last_date - timedelta(days=1)
                    data_inicio = start_date.strftime("%Y-%m-%d")
                    logger.info("Última votação no banco: %s", last_date)
                    logger.info("Busca incremental desde: %s", data_inicio)

        if data_inicio is None:
            # Padrão: últimos 30 dias
            start_date = date.today() - timedelta(days=30)
            data_inicio = start_date.strftime("%Y-%m-%d")
            logger.info("Buscando votações desde: %s (últimos 30 dias)", data_inicio)

    processed = 0
    inserted = 0
    updated = 0

    try:
        with _SESSION_SCOPE() as session:
            for votacao_id, detail, votos in _iter_votacoes_paginated(
                data_inicio, data_fim=data_fim
            ):
                payloads = _build_vote_payloads(votacao_id, detail, votos)

                logger.info(
                    "Votação %s: %s votos",
                    votacao_id,
                    len(payloads),
                )

                for payload in payloads:
                    processed += 1

                    if interactive or not persist:
                        _debug_print_payload(payload)
                        if interactive:
                            try:
                                input("Pressione ENTER para continuar; Ctrl+C para sair.")
                            except (KeyboardInterrupt, EOFError):
                                logger.info("Execução interrompida pelo usuário.")
                                return

                    if persist:
                        result = _upsert_roll_call_vote(session, payload)
                        if result[0] is not None:
                            record, created = result
                            if created:
                                inserted += 1
                            else:
                                updated += 1

    except KeyboardInterrupt:
        logger.info("Execução interrompida pelo usuário após %s votos.", processed)
        return

    if processed == 0:
        logger.warning("Nenhuma votação nominal retornada pela Câmara")
    elif persist:
        logger.info(
            "Sincronização concluída: %s inseridos, %s atualizados, %s total",
            inserted,
            updated,
            processed,
        )
    else:
        logger.info("Processamento concluído em modo dry-run (%s votos)", processed)


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(
        description="Sincroniza votações nominais da Câmara dos Deputados."
    )
    parser.add_argument(
        "--data-inicio",
        type=str,
        help="Data inicial no formato YYYY-MM-DD (default: últimos 30 dias ou última votação)",
    )
    parser.add_argument(
        "--data-fim",
        type=str,
        help="Data final no formato YYYY-MM-DD (opcional; usado no backfill por janelas)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Não persiste no banco; apenas exibe os payloads.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Pausa após cada voto para inspeção manual.",
    )

    args = parser.parse_args()

    roll_call_votes(
        data_inicio=args.data_inicio,
        data_fim=args.data_fim,
        persist=not args.dry_run,
        interactive=args.interactive,
    )
