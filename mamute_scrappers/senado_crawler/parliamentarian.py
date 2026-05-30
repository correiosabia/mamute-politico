"""Raspador de parlamentares do Senado.

Este módulo fornece ganchos para buscar dados dos parlamentares na API do Senado
e persistir as informações nas tabelas relacionadas (`Parliamentarian`,
`SocialNetwork`, `ParliamentarianSocialNetwork`). A função pública
`parliamentarian()` apenas orquestra o fluxo; adapte as funções privadas para
integrar com o endpoint desejado.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import (
    Any,
    Callable,
    ContextManager,
    Dict,
    Iterable,
    List,
    Optional,
    TYPE_CHECKING,
    TypedDict,
)

import requests
from sqlalchemy.orm import Session
from xml.etree import ElementTree as ET

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)

SENADO_API_BASE_URL = "https://legis.senado.leg.br/dadosabertos"  # ajuste se necessário
SENADO_LIST_VERSION = "4"
SENADO_DETAIL_VERSION = "6"

if TYPE_CHECKING:  # pragma: no cover - apenas para tipagem
    from mamute_scrappers.db.models import (
        Parliamentarian as ParliamentarianModel,
        ParliamentarianSocialNetwork as ParliamentarianSocialNetworkModel,
        SocialNetwork as SocialNetworkModel,
    )
    from mamute_scrappers.db.session import session_scope as session_scope_type

    SessionScopeCallable = Callable[[], ContextManager["Session"]]
else:
    ParliamentarianModel = Any
    ParliamentarianSocialNetworkModel = Any
    SocialNetworkModel = Any
    SessionScopeCallable = Callable[[], ContextManager[Session]]

Parliamentarian: Any = None
ParliamentarianSocialNetwork: Any = None
SocialNetwork: Any = None
_SESSION_SCOPE: Optional[SessionScopeCallable] = None


def _ensure_db_dependencies() -> None:
    global Parliamentarian, ParliamentarianSocialNetwork, SocialNetwork, _SESSION_SCOPE
    if _SESSION_SCOPE is not None:
        return

    try:
        from mamute_scrappers.db.models import (
            Parliamentarian as ParliamentarianModelRuntime,
            ParliamentarianSocialNetwork as ParliamentarianSocialNetworkModelRuntime,
            SocialNetwork as SocialNetworkModelRuntime,
        )
        from mamute_scrappers.db.session import session_scope as session_scope_runtime
    except ImportError as exc:  # pragma: no cover - depende do ambiente
        raise RuntimeError("Não foi possível carregar dependências de banco.") from exc

    Parliamentarian = ParliamentarianModelRuntime
    ParliamentarianSocialNetwork = ParliamentarianSocialNetworkModelRuntime
    SocialNetwork = SocialNetworkModelRuntime
    _SESSION_SCOPE = session_scope_runtime


class SocialNetworkPayload(TypedDict, total=False):
    name: str
    url: Optional[str]
    profile_url: Optional[str]


class ParliamentarianPayload(TypedDict, total=False):
    id: int
    type: Optional[str]
    parliamentarian_code: Optional[int]
    name: Optional[str]
    full_name: Optional[str]
    email: Optional[str]
    telephone: Optional[str]
    cpf: Optional[str]
    status: Optional[str]
    party: Optional[str]
    state_of_birth: Optional[str]
    city_of_birth: Optional[str]
    state_elected: Optional[str]
    site: Optional[str]
    education: Optional[str]
    office_name: Optional[str]
    office_building: Optional[str]
    office_number: Optional[str]
    office_floor: Optional[str]
    office_email: Optional[str]
    biography_link: Optional[str]
    biography_text: Optional[str]
    details: Optional[dict]
    social_networks: List[SocialNetworkPayload]


PARLIAMENTARIAN_MUTABLE_FIELDS = [
    "type",
    "parliamentarian_code",
    "name",
    "full_name",
    "email",
    "telephone",
    "cpf",
    "status",
    "party",
    "state_of_birth",
    "city_of_birth",
    "state_elected",
    "site",
    "education",
    "office_name",
    "office_building",
    "office_number",
    "office_floor",
    "office_email",
    "biography_link",
    "biography_text",
    "details",
]


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


def _json_get(container: Optional[Dict[str, Any]], key: str) -> Optional[str]:
    if not isinstance(container, dict):
        return None
    return _coerce_text(container.get(key))


def _find_text(element: Optional[ET.Element], *path: str) -> Optional[str]:
    current = element
    for tag in path:
        if current is None:
            return None
        current = current.find(tag)
    if current is None:
        return None
    return _normalize_text(current.text)


def _collect_telephones(container: Optional[ET.Element]) -> List[str]:
    numbers: List[str] = []
    if container is None:
        return numbers
    for telefone in container.findall("Telefone"):
        number = _find_text(telefone, "NumeroTelefone")
        if number:
            numbers.append(number)
    return numbers


def _collect_telephones_json(identificacao: Optional[Dict[str, Any]]) -> List[str]:
    numbers: List[str] = []
    if not isinstance(identificacao, dict):
        return numbers

    telefones = identificacao.get("Telefones")
    if not isinstance(telefones, dict):
        return numbers

    for telefone in _ensure_list(telefones.get("Telefone")):
        if not isinstance(telefone, dict):
            continue
        number = _coerce_text(telefone.get("NumeroTelefone"))
        if number:
            numbers.append(number)
    return numbers


def _format_telephones(numbers: Iterable[str]) -> Optional[str]:
    formatted = " / ".join(num for num in numbers if num)
    return formatted or None


def _element_to_dict(element: Optional[ET.Element]) -> Optional[Any]:
    if element is None:
        return None
    children = list(element)
    if not children:
        return _normalize_text(element.text)

    result: Dict[str, Any] = {}
    for child in children:
        value = _element_to_dict(child)
        if value is None:
            continue
        existing = result.get(child.tag)
        if existing is None:
            result[child.tag] = value
        else:
            if not isinstance(existing, list):
                result[child.tag] = [existing]
            result[child.tag].append(value)
    return result or None


def _debug_print_payload(payload: ParliamentarianPayload) -> None:
    debug_repr = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    print(debug_repr)


def _wait_for_user() -> bool:
    try:
        input("Pressione ENTER (ou digite algo) para o próximo parlamentar; Ctrl+C para sair.")
        return True
    except (KeyboardInterrupt, EOFError):
        return False


def _request_json(url: str, *, params: Optional[Dict[str, str]] = None) -> Optional[Dict[str, Any]]:
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
        logger.error("Erro ao parsear JSON do Senado (%s): %s", url, exc)
        return None

    if not isinstance(data, dict):
        logger.error("Resposta JSON inesperada do Senado (%s): tipo %s", url, type(data))
        return None

    return data


def _request_xml(url: str, *, params: Optional[Dict[str, str]] = None) -> Optional[ET.Element]:
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Falha ao consultar %s: %s", url, exc)
        return None

    try:
        return ET.fromstring(response.content)
    except ET.ParseError as exc:
        logger.error("Erro ao parsear XML do Senado (%s): %s", url, exc)
        return None


def _fetch_parliamentarian_detail(code: str) -> Optional[ET.Element]:
    url = f"{SENADO_API_BASE_URL}/senador/{code}"
    params = {"v": SENADO_DETAIL_VERSION}
    root = _request_xml(url, params=params)
    if root is None:
        return None
    return root.find("Parlamentar")


def _extract_detail_fields(detail: Optional[ET.Element]) -> Dict[str, Any]:
    if detail is None:
        return {}

    data: Dict[str, Any] = {}
    identificacao = detail.find("IdentificacaoParlamentar")
    dados_basicos = detail.find("DadosBasicosParlamentar")

    data["state_of_birth"] = _find_text(dados_basicos, "UfNaturalidade")
    data["city_of_birth"] = _find_text(dados_basicos, "Naturalidade")
    data["personal_site"] = _find_text(identificacao, "UrlPaginaParticular") or _find_text(
        identificacao, "UrlPaginaParlamentar"
    )
    data["office_address"] = _find_text(dados_basicos, "EnderecoParlamentar")
    data["phones"] = _collect_telephones(detail.find("Telefones"))

    return data


def _extract_parlamentar_items(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    lista = data.get("ListaParlamentarEmExercicio")
    if not isinstance(lista, dict):
        logger.warning("Resposta do Senado sem 'ListaParlamentarEmExercicio'")
        return []

    parlamentares_container = lista.get("Parlamentares")
    if isinstance(parlamentares_container, dict):
        parlamentares = parlamentares_container.get("Parlamentar")
    else:
        parlamentares = None

    items = _ensure_list(parlamentares)
    result: List[Dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            result.append(item)
    if not result:
        logger.warning("Resposta do Senado sem parlamentares válidos")
    return result


def _parse_iso_date(value: Any) -> Optional[date]:
    text = _coerce_text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _collect_mandato_legislatura_periods(mandato: Dict[str, Any]) -> List[tuple[date, date]]:
    periods: List[tuple[date, date]] = []
    for key in ("PrimeiraLegislaturaDoMandato", "SegundaLegislaturaDoMandato"):
        legislatura = mandato.get(key)
        if not isinstance(legislatura, dict):
            continue
        start = _parse_iso_date(legislatura.get("DataInicio"))
        end = _parse_iso_date(legislatura.get("DataFim"))
        if start is not None and end is not None:
            periods.append((start, end))
    return periods


def _derive_status_from_mandato(parlamentar: Dict[str, Any]) -> Optional[str]:
    mandato = parlamentar.get("Mandato")
    if not isinstance(mandato, dict):
        return None

    today = date.today()
    periods = _collect_mandato_legislatura_periods(mandato)
    if not periods:
        return None

    if any(start <= today <= end for start, end in periods):
        return "Exercício"

    latest_end = max(end for _, end in periods)
    if today > latest_end:
        return "Fim de mandato"

    earliest_start = min(start for start, _ in periods)
    if today < earliest_start:
        return "Fora de exercício"

    return None


def _parse_social_networks_json(parlamentar: Dict[str, Any]) -> List[SocialNetworkPayload]:
    candidates: List[Any] = []

    for container in (
        parlamentar.get("RedesSociais"),
        parlamentar.get("IdentificacaoParlamentar", {}).get("RedesSociais")
        if isinstance(parlamentar.get("IdentificacaoParlamentar"), dict)
        else None,
    ):
        if isinstance(container, dict):
            candidates.extend(_ensure_list(container.get("RedeSocial")))

    social_networks: List[SocialNetworkPayload] = []
    for rede in candidates:
        if not isinstance(rede, dict):
            continue
        name = (
            _coerce_text(rede.get("NomeRedeSocial"))
            or _coerce_text(rede.get("DescricaoRedeSocial"))
            or _coerce_text(rede.get("NomeRede"))
            or _coerce_text(rede.get("RedeSocial"))
        )
        profile_url = (
            _coerce_text(rede.get("UrlRedeSocial"))
            or _coerce_text(rede.get("Url"))
            or _coerce_text(rede.get("EnderecoUrl"))
        )
        if not name and not profile_url:
            continue

        social_payload: SocialNetworkPayload = {"name": name or "Rede social"}
        if profile_url:
            social_payload["profile_url"] = profile_url
        social_networks.append(social_payload)

    return social_networks


def _build_payload_from_json(parlamentar: Dict[str, Any]) -> Optional[ParliamentarianPayload]:
    if not isinstance(parlamentar, dict):
        logger.debug("Parlamentar JSON inválido; pulando registro")
        return None

    identificacao = parlamentar.get("IdentificacaoParlamentar")
    if not isinstance(identificacao, dict):
        logger.debug("Campo 'IdentificacaoParlamentar' ausente; pulando registro")
        return None

    codigo_text = _coerce_text(identificacao.get("CodigoParlamentar"))
    if not codigo_text:
        logger.debug("Código parlamentar ausente; pulando registro")
        return None

    try:
        codigo_int = int(codigo_text)
    except (TypeError, ValueError):
        logger.debug("Código parlamentar inválido (%s); pulando registro", codigo_text)
        return None

    detail_element = _fetch_parliamentarian_detail(codigo_text)
    detail_dict = _element_to_dict(detail_element)
    detail_fields = _extract_detail_fields(detail_element)

    phones = _collect_telephones_json(identificacao)
    if not phones:
        phones = detail_fields.get("phones", [])

    telephone = _format_telephones(phones)
    social_networks = _parse_social_networks_json(parlamentar)

    details_payload: Dict[str, Any] = {}
    if parlamentar:
        details_payload["lista"] = parlamentar
    if detail_dict is not None:
        details_payload["detalhe"] = detail_dict

    payload: ParliamentarianPayload = {
        "type": "Senador",
        "parliamentarian_code": codigo_int,
        "social_networks": social_networks,
    }

    base_fields = {
        "name": _json_get(identificacao, "NomeParlamentar"),
        "full_name": _json_get(identificacao, "NomeCompletoParlamentar"),
        "email": _json_get(identificacao, "EmailParlamentar"),
        "party": _json_get(identificacao, "SiglaPartidoParlamentar"),
        "state_elected": _json_get(identificacao, "UfParlamentar"),
    }
    detail_fields_optional = {
        "site": detail_fields.get("personal_site"),
        "state_of_birth": detail_fields.get("state_of_birth"),
        "city_of_birth": detail_fields.get("city_of_birth"),
        "office_name": detail_fields.get("office_address"),
    }

    for field, value in {**base_fields, **detail_fields_optional}.items():
        if value is not None:
            payload[field] = value

    if telephone:
        payload["telephone"] = telephone
    if details_payload:
        payload["details"] = details_payload

    status = _derive_status_from_mandato(parlamentar)
    if status:
        payload["status"] = status

    return payload


def parliamentarian(
    *,
    uf: Optional[str] = None,
    participation: str = "T",
    persist: bool = True,
    interactive: bool = False,
) -> None:
    """Busca parlamentares do Senado e salva/atualiza o banco.

    Quando `persist` for `False`, apenas exibe os payloads. Com `interactive=True`,
    o fluxo aguarda uma confirmação (ENTER) entre cada parlamentar para facilitar
    a inspeção manual.
    """
    logger.info(
        "Iniciando sincronização de parlamentares do Senado (persist=%s, interactive=%s)",
        persist,
        interactive,
    )

    iterator = _fetch_parliamentarians(uf=uf, participation=participation)
    processed = 0

    try:
        if persist:
            _ensure_db_dependencies()
            if _SESSION_SCOPE is None:
                raise RuntimeError("Função de sessão do banco não carregada.")

            with _SESSION_SCOPE() as session:
                for payload in iterator:
                    processed += 1
                    if interactive or not persist:
                        _debug_print_payload(payload)
                        if interactive and not _wait_for_user():
                            logger.info(
                                "Execução interrompida pelo usuário após %s registros.",
                                processed,
                            )
                            return
                    _upsert_parliamentarian(session, payload)
        else:
            for payload in iterator:
                processed += 1
                _debug_print_payload(payload)
                if interactive and not _wait_for_user():
                    logger.info(
                        "Execução interrompida pelo usuário após %s registros.", processed
                    )
                    return
    except KeyboardInterrupt:
        logger.info("Execução interrompida pelo usuário após %s registros.", processed)
        return

    if processed == 0:
        logger.warning("Nenhum parlamentar retornado pela API do Senado")
    elif persist:
        logger.info("Sincronização de parlamentares concluída com sucesso (%s registros)", processed)
    else:
        logger.info("Processamento concluído em modo dry-run (%s registros)", processed)


def _fetch_parliamentarians(
    uf: Optional[str] = None,
    participation: str = "T",
) -> Iterable[ParliamentarianPayload]:
    """Consulta o endpoint oficial (JSON) e transforma em payloads internos."""
    params: Dict[str, str] = {"participacao": participation, "v": SENADO_LIST_VERSION}
    if uf:
        params["uf"] = uf

    url = f"{SENADO_API_BASE_URL}/senador/lista/atual"
    logger.debug("Consultando API do Senado em %s com params %s", url, params)
    data = _request_json(url, params=params)
    if data is None:
        return

    for parlamentar in _extract_parlamentar_items(data):
        payload = _build_payload_from_json(parlamentar)
        if payload is None:
            continue
        yield payload


def _upsert_parliamentarian(session: Session, payload: ParliamentarianPayload) -> Any:
    """Atualiza ou cria um parlamentar conforme o payload informado."""
    code = payload.get("parliamentarian_code")
    if code is None:
        raise ValueError("Payload de parlamentar sem 'parliamentarian_code'.")

    if any(dep is None for dep in (Parliamentarian, ParliamentarianSocialNetwork, SocialNetwork)):
        raise RuntimeError("Dependências de banco não carregadas.")

    record: Any = (
        session.query(Parliamentarian).filter_by(parliamentarian_code=code).one_or_none()
    )
    if record is None:
        record = Parliamentarian(parliamentarian_code=code)
        session.add(record)

    for field in PARLIAMENTARIAN_MUTABLE_FIELDS:
        if field in payload:
            setattr(record, field, payload[field])

    _sync_social_networks(session, record, payload.get("social_networks", []))
    logger.debug("Parlamentar %s sincronizado", record.id)
    return record


def _sync_social_networks(
    session: Session,
    parliamentarian: Any,
    socials: Iterable[SocialNetworkPayload],
) -> None:
    """Sincroniza redes sociais associadas ao parlamentar."""
    existing_links = {link.social_network.name: link for link in parliamentarian.social_networks}
    handled = set()

    for social in socials:
        name = social.get("name")
        if not name:
            continue
        handled.add(name)

        network = session.query(SocialNetwork).filter_by(name=name).one_or_none()
        if network is None:
            network = SocialNetwork(name=name, url=social.get("url"))
            session.add(network)

        link = existing_links.get(name)
        if link is None:
            link = ParliamentarianSocialNetwork(
                parliamentarian=parliamentarian,
                social_network=network,
            )
            session.add(link)

        link.profile_url = social.get("profile_url")

    # Remove vínculos de redes que não estão mais presentes
    for name, link in existing_links.items():
        if name not in handled:
            session.delete(link)


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Sincroniza parlamentares do Senado.")
    parser.add_argument("--uf", help="Filtra por UF específica (ex.: PR).")
    parser.add_argument(
        "--participation",
        default="T",
        help="Filtro de participação (padrão: T - todos).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Não persiste no banco; apenas exibe os payloads.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Pausa após cada parlamentar para inspeção manual.",
    )

    args = parser.parse_args()

    parliamentarian(
        uf=args.uf,
        participation=args.participation,
        persist=not args.dry_run,
        interactive=args.interactive,
    )


