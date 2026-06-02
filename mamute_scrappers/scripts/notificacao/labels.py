"""Rótulos de exibição de proposições no e-mail."""

from __future__ import annotations

from typing import Optional


def is_camara_proposition(link: Optional[str]) -> bool:
    return isinstance(link, str) and "camara.leg.br" in link.lower()


def format_tipo_numero_ano(
    acronym: Optional[str],
    number: Optional[int],
    year: Optional[int],
) -> Optional[str]:
    """Ex.: PL 1234/2025 (mesmo padrão da UI)."""
    sigla = (acronym or "").strip()
    if not sigla:
        return None
    if number is None:
        return sigla
    if year:
        return f"{sigla} {number}/{year}"
    return f"{sigla} {number}"


def format_proposition_display_title(
    *,
    title: Optional[str],
    link: Optional[str],
    acronym: Optional[str] = None,
    number: Optional[int] = None,
    year: Optional[int] = None,
) -> str:
    """
    Título curto para o e-mail.

    Câmara: prioriza sigla + número/ano.
    Demais casas: usa `title` da proposição.
    """
    if is_camara_proposition(link):
        tipo_numero = format_tipo_numero_ano(acronym, number, year)
        if tipo_numero:
            return tipo_numero[:200]

    cleaned = (title or "").strip()
    if cleaned:
        return cleaned[:200]
    return "Proposição"


def chamber_label_from_parliamentarian_type(
    parliamentarian_type: Optional[str],
) -> str:
    """Retorna 'Câmara', 'Senado' ou vazio conforme `parliamentarian.type`."""
    if not parliamentarian_type:
        return ""
    lowered = parliamentarian_type.lower()
    if "senad" in lowered:
        return "Senado"
    if "deput" in lowered:
        return "Câmara"
    return ""


def format_parliamentarian_display_name(name: Optional[str]) -> str:
    """Ex.: MICHEL TEMER → Michel Temer; ARAÚJO BASTO → Araújo Basto."""
    cleaned = (name or "").strip()
    if not cleaned:
        return "Parlamentar"
    return " ".join(
        part[0].upper() + part[1:].lower() if part else "" for part in cleaned.split()
    )


def extract_ementa(
    proposition_description: Optional[str],
    summary: Optional[str],
    *,
    max_length: int = 320,
) -> Optional[str]:
    """Ementa/resumo da proposição (mesma prioridade da UI)."""
    text = (proposition_description or summary or "").strip()
    if not text:
        return None
    if len(text) > max_length:
        return text[: max_length - 3] + "..."
    return text
