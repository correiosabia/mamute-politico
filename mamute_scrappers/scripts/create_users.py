"""Sincroniza usuários do Ghost com a base local de projetos."""

from __future__ import annotations

import hashlib
import logging
import os
import sys
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Tuple

import jwt
import requests
from dotenv import load_dotenv
from requests import Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from mamute_scrappers.db import session_scope
from mamute_scrappers.db.models import Projetos, Tiers

_SCRIPT_PATH = Path(__file__).resolve()
_ENV_CANDIDATES = [
    _SCRIPT_PATH.parents[2] / ".env",
    _SCRIPT_PATH.parents[1] / ".env",
]

for env_path in _ENV_CANDIDATES:
    if load_dotenv(dotenv_path=env_path, override=False):
        break

logger = logging.getLogger("crawlers.create_users")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

GHOST_API_KEY = os.getenv("GHOST_API") or os.getenv("GHOST_API_KEY")
GHOST_ADMIN_URL = os.getenv("GHOST_ADMIN_URL")

if not GHOST_API_KEY:
    raise RuntimeError(
        "Variável de ambiente GHOST_API não encontrada. "
        "Defina a chave administradora do Ghost para continuar."
    )


@dataclass
class GhostMember:
    email: str
    product_id: str
    name: Optional[str]
    label: Optional[str]


def generate_token() -> str:
    """Gera o JWT necessário para autenticação no painel admin do Ghost."""
    try:
        kid, secret = GHOST_API_KEY.split(":")
    except ValueError as exc:
        raise RuntimeError(
            "Formato inválido para GHOST_API. Esperado '<key>:<secret>'."
        ) from exc
    iat = int(datetime.now(timezone.utc).timestamp())

    header = {"alg": "HS256", "typ": "JWT", "kid": kid}
    payload = {
        "iat": iat,
        "exp": iat + 5 * 60,
        "aud": "/admin/",
    }

    return jwt.encode(
        payload,
        bytes.fromhex(secret),
        algorithm="HS256",
        headers=header,
    )


def _request_ghost_members(token: str, page: int) -> Response:
    url = (
        f"{GHOST_ADMIN_URL.rstrip('/')}/members/"
        f"?limit=all&page={page}&include=tiers,subscriptions"
    )
    headers = {"Authorization": f"Ghost {token}"}
    response = requests.get(url, headers=headers, timeout=30)

    if response.status_code != 200:
        raise RuntimeError(
            f"Falha ao consultar Ghost (status={response.status_code}): {response.text}"
        )

    return response


def fetch_ghost_members() -> List[GhostMember]:
    """Busca todos os membros cadastrados no Ghost."""
    token = generate_token()
    members: List[GhostMember] = []

    page = 1
    total_pages = 1

    while page <= total_pages:
        logger.info("Consultando membros Ghost página %s/%s", page, total_pages)
        response = _request_ghost_members(token, page)
        data = response.json()

        pagination = data.get("meta", {}).get("pagination", {})
        total_pages = int(pagination.get("pages", total_pages))

        for member in data.get("members", []):
            email = member.get("email")
            if not email:
                continue

            product_id = _resolve_product_id(member)
            members.append(
                GhostMember(
                    email=email.lower(),
                    product_id=product_id,
                    name=member.get("name"),
                    label=_resolve_label(member),
                )
            )

        page += 1

    logger.info("Total de membros retornados pelo Ghost: %s", len(members))
    return members


def _resolve_product_id(member: dict) -> str:
    subscriptions = member.get("subscriptions") or []
    if subscriptions:
        tier_info = subscriptions[-1].get("tier") or {}
        return tier_info.get("id", "free")

    tiers = member.get("tiers") or []
    if tiers:
        return tiers[-1].get("id") or "free"

    if member.get("status") == "free":
        return "free"

    return "free"


def _resolve_label(member: dict) -> Optional[str]:
    labels = member.get("labels") or []
    if not labels:
        return None
    return labels[0].get("slug")


def load_tiers(session: Session) -> Dict[str, Tiers]:
    """Retorna um mapa product_id -> Tier."""
    tiers: List[Tiers] = session.query(Tiers).all()
    if not tiers:
        raise RuntimeError("Nenhum tier cadastrado na base. Cadastre tiers antes de sincronizar.")

    tier_map = {tier.product_id: tier for tier in tiers}
    logger.info("Tiers carregados: %s", len(tier_map))
    return tier_map


def load_existing_projects(session: Session) -> Dict[str, Projetos]:
    projetos = session.query(Projetos).all()
    return {projeto.email.lower(): projeto for projeto in projetos}


def sanitize_name(value: Optional[str], fallback: str) -> str:
    base = (value or fallback).strip().lower()
    if not base:
        base = fallback

    sanitized = "".join(char if char.isalnum() else "_" for char in base)
    sanitized = "_".join(filter(None, sanitized.split("_")))
    return sanitized or fallback


def generate_bot_name(email: str, name: Optional[str]) -> str:
    local_part = email.split("@", maxsplit=1)[0]
    base = sanitize_name(name, fallback=local_part)
    digest = hashlib.shake_256(email.encode("utf-8")).hexdigest(4)
    return f"{base}_{digest}"


def sync_projects(
    session: Session,
    members: Iterable[GhostMember],
    tier_map: Dict[str, Tiers],
    existing_projects: Dict[str, Projetos],
) -> Tuple[int, int]:
    created = 0
    updated = 0

    for member in members:
        tier = tier_map.get(member.product_id)
        if not tier:
            logger.debug(
                "Ignorando membro %s: tier %s não encontrado.",
                member.email,
                member.product_id,
            )
            continue

        projeto = existing_projects.get(member.email)
        if projeto is None:
            projeto = Projetos(
                nome=generate_bot_name(member.email, member.name),
                cliente=member.product_id,
                email=member.email,
                tier_id=tier.id,
                qtd_termos=tier.qtd_termos or 0,
                tag_ghost=member.label,
            )
            session.add(projeto)
            existing_projects[member.email] = projeto
            created += 1
            logger.info("Projeto criado para %s (tier=%s).", member.email, member.product_id)
            continue

        changed = False

        if projeto.tier_id != tier.id:
            projeto.tier_id = tier.id
            changed = True

        if projeto.cliente != member.product_id:
            projeto.cliente = member.product_id
            changed = True

        target_qtd_termos = tier.qtd_termos or 0
        if projeto.qtd_termos != target_qtd_termos:
            projeto.qtd_termos = target_qtd_termos
            changed = True

        if member.label and projeto.tag_ghost != member.label:
            projeto.tag_ghost = member.label
            changed = True

        if changed:
            updated += 1
            logger.info("Projeto atualizado para %s (tier=%s).", member.email, member.product_id)

    return created, updated


def main() -> int:
    try:
        members = fetch_ghost_members()
        if not members:
            logger.info("Nenhum membro retornado pelo Ghost.")
            return 0

        with session_scope() as session:
            tier_map = load_tiers(session)
            existing_projects = load_existing_projects(session)
            created, updated = sync_projects(session, members, tier_map, existing_projects)

            logger.info(
                "Sincronização concluída: %s criados, %s atualizados.",
                created,
                updated,
            )
    except (RuntimeError, SQLAlchemyError, requests.RequestException) as exc:
        logger.exception("Falha ao executar create_users: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
