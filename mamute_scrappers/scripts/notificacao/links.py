"""URLs de exibição alinhadas à API/UI (evita links de API/XML no e-mail)."""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import parse_qs, urlparse

SENADO_PROPOSITION_BASE_URL = (
    "https://www25.senado.leg.br/web/atividade/materias/-/materia"
)
CAMARA_FICHA_URL = (
    "https://www.camara.leg.br/proposicoesWeb/fichadetramitacao"
)

_API_HOST_MARKERS = (
    "dadosabertos.camara.leg.br",
    "legis.senado.leg.br/dadosabertos",
)

_CAMARA_ID_RE = re.compile(r"idProposicao=(\d+)", re.IGNORECASE)


def _is_api_url(url: Optional[str]) -> bool:
    if not url:
        return False
    lowered = url.lower()
    return any(marker in lowered for marker in _API_HOST_MARKERS)


def _is_camara_source(link: Optional[str]) -> bool:
    if not link:
        return False
    lowered = link.lower()
    return "camara.leg.br" in lowered or "dadosabertos.camara" in lowered


def _camara_ficha_url(proposition_id: int) -> str:
    return f"{CAMARA_FICHA_URL}?idProposicao={proposition_id}"


def _extract_camara_proposition_id(link: Optional[str]) -> Optional[int]:
    if not link:
        return None
    match = _CAMARA_ID_RE.search(link)
    if match:
        return int(match.group(1))
    parsed = urlparse(link)
    values = parse_qs(parsed.query).get("idProposicao") or parse_qs(parsed.query).get(
        "idproposicao"
    )
    if values and values[0].isdigit():
        return int(values[0])
    return None


def resolve_proposition_link(
    link: Optional[str],
    proposition_code: Optional[int] = None,
    *,
    camara: bool = False,
) -> Optional[str]:
    """Espelha `api.routers.propositions._build_proposition_link`."""
    if isinstance(link, str) and link.strip():
        stripped = link.strip()
        if not _is_api_url(stripped):
            if "camara.leg.br" in stripped.lower() or "senado.leg.br" in stripped.lower():
                return stripped
        if _is_camara_source(stripped):
            camara_id = _extract_camara_proposition_id(stripped) or proposition_code
            if camara_id is not None:
                return _camara_ficha_url(camara_id)

    if proposition_code is not None:
        if camara or _is_camara_source(link):
            return _camara_ficha_url(proposition_code)
        return f"{SENADO_PROPOSITION_BASE_URL}/{proposition_code}"

    if isinstance(link, str) and link.strip() and not _is_api_url(link):
        return link.strip()
    return None


def resolve_speech_display_link(
    speech_link: Optional[str],
    publication_link: Optional[str] = None,
) -> Optional[str]:
    """URL humana do discurso (evita endpoints de API no e-mail)."""
    for url in (speech_link, publication_link):
        if isinstance(url, str) and url.strip() and not _is_api_url(url):
            return url.strip()
    return None


def resolve_speech_activity_link(
    speech_link: Optional[str],
    publication_link: Optional[str] = None,
    *,
    proposition_link: Optional[str] = None,
    proposition_code: Optional[int] = None,
    camara: bool = False,
) -> Optional[str]:
    """Prioriza ficha de tramitação da proposição vinculada; senão, link do discurso."""
    prop_page = resolve_proposition_link(
        proposition_link,
        proposition_code,
        camara=camara,
    )
    if prop_page:
        return prop_page
    return resolve_speech_display_link(speech_link, publication_link)


def _camara_votes_page(proposition_page: str) -> str:
    """Página humana da proposição (ficha de tramitação)."""
    if "fichadetramitacao" in proposition_page and "?" in proposition_page:
        # Evita `...?idProposicao=123/votacoes` (URL inválida da API legada).
        return proposition_page
    return f"{proposition_page.rstrip('/')}/votacoes"


def resolve_vote_display_link(
    vote_link: Optional[str],
    proposition_link: Optional[str],
    proposition_code: Optional[int] = None,
    *,
    camara: bool = False,
) -> Optional[str]:
    """Espelha o `proposition_votes_link` usado na UI (`mapRollCallVoteOutToVotacao`)."""
    prop_page = resolve_proposition_link(
        proposition_link,
        proposition_code,
        camara=camara,
    )
    if prop_page and "camara.leg.br" in prop_page:
        return _camara_votes_page(prop_page)
    if prop_page:
        return prop_page
    if vote_link and not _is_api_url(vote_link):
        return vote_link
    return None
