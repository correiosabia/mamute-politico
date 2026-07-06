"""Cliente mínimo para consultas ao Ghost Admin API."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import jwt
import requests


@dataclass(frozen=True)
class GhostAdminSettings:
    api_key: str
    admin_url: str


def get_ghost_admin_settings() -> Optional[GhostAdminSettings]:
    api_key = os.getenv("GHOST_API") or os.getenv("GHOST_API_KEY")
    admin_url = os.getenv("GHOST_ADMIN_URL")
    if not api_key or not admin_url:
        return None
    return GhostAdminSettings(api_key=api_key, admin_url=admin_url.rstrip("/"))


def generate_admin_token(api_key: str) -> str:
    """Gera JWT para o Ghost Admin API sem expor a chave em logs."""

    try:
        kid, secret = api_key.split(":")
    except ValueError as exc:
        raise RuntimeError("GHOST_API inválido. Esperado '<key>:<secret>'.") from exc

    iat = int(datetime.now(timezone.utc).timestamp())
    return jwt.encode(
        {"iat": iat, "exp": iat + 5 * 60, "aud": "/admin/"},
        bytes.fromhex(secret),
        algorithm="HS256",
        headers={"alg": "HS256", "typ": "JWT", "kid": kid},
    )


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Ghost {token}"}


def fetch_ghost_tiers(
    admin_url: str,
    token: str,
    http_get: Callable[..., Any] = requests.get,
) -> list[dict[str, Any]]:
    response = http_get(
        f"{admin_url.rstrip('/')}/tiers/",
        params={"include": "monthly_price", "limit": "all"},
        headers=_headers(token),
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    tiers = payload.get("tiers", []) if isinstance(payload, dict) else []
    return [tier for tier in tiers if isinstance(tier, dict)]


def fetch_ghost_members(
    admin_url: str,
    token: str,
    http_get: Callable[..., Any] = requests.get,
) -> list[dict[str, Any]]:
    members: list[dict[str, Any]] = []
    page = 1
    total_pages = 1

    while page <= total_pages:
        response = http_get(
            f"{admin_url.rstrip('/')}/members/",
            params={
                "include": "tiers,subscriptions",
                "limit": "all",
                "page": page,
            },
            headers=_headers(token),
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            break

        members.extend(
            member for member in payload.get("members", []) if isinstance(member, dict)
        )
        pagination = payload.get("meta", {}).get("pagination", {})
        try:
            total_pages = int(pagination.get("pages", total_pages))
        except (TypeError, ValueError):
            total_pages = page
        page += 1

    return members


def fetch_ghost_member_by_email(
    admin_url: str,
    token: str,
    email: str,
    http_get: Callable[..., Any] = requests.get,
) -> Optional[dict[str, Any]]:
    normalized_email = email.strip().lower()
    if not normalized_email:
        return None

    response = http_get(
        f"{admin_url.rstrip('/')}/members/",
        params={
            "filter": f"email:'{normalized_email}'",
            "include": "tiers,subscriptions",
            "limit": 1,
        },
        headers=_headers(token),
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        return None

    for member in payload.get("members", []) or []:
        if not isinstance(member, dict):
            continue
        member_email = member.get("email")
        if isinstance(member_email, str) and member_email.strip().lower() == normalized_email:
            return member
    return None


def fetch_ghost_member_by_email_from_env(email: str) -> Optional[dict[str, Any]]:
    settings = get_ghost_admin_settings()
    if settings is None:
        return None
    token = generate_admin_token(settings.api_key)
    return fetch_ghost_member_by_email(settings.admin_url, token, email)


__all__ = [
    "GhostAdminSettings",
    "fetch_ghost_member_by_email",
    "fetch_ghost_member_by_email_from_env",
    "fetch_ghost_members",
    "fetch_ghost_tiers",
    "generate_admin_token",
    "get_ghost_admin_settings",
]
