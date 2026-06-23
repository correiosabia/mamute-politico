"""Ghost Members JWT helpers for the chatbot backend."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import jwt
import requests
from fastapi import HTTPException, status
from jwt.algorithms import RSAAlgorithm
from jwt.exceptions import ExpiredSignatureError, InvalidSignatureError, InvalidTokenError
from requests import RequestException

from .core.config import get_settings

JWT_ALGORITHM = "RS512"


def _normalize_base_url(value: str) -> str:
    value = value.strip()
    if not value.endswith("/"):
        value += "/"
    return value


@lru_cache(maxsize=1)
def get_ghost_settings() -> Dict[str, str]:
    """Resolve Ghost Members JWT settings from the chatbot environment."""

    settings = get_settings()
    base_url = settings.ghost_base_url or settings.prefix_url
    if not base_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Configuração de autenticação Ghost ausente "
                "(GHOST_BASE_URL ou PREFIX_URL)."
            ),
        )

    base_url = _normalize_base_url(base_url)
    audience = settings.ghost_members_api_audience or urljoin(base_url, "members/api")
    issuer = settings.ghost_members_api_issuer or audience
    jwks_url = urljoin(base_url, settings.ghost_jwks_path)

    return {
        "base_url": base_url,
        "audience": audience,
        "issuer": issuer,
        "jwks_url": jwks_url,
    }


@lru_cache(maxsize=1)
def get_public_key() -> Any:
    """Fetch and cache the Ghost Members public key."""

    settings = get_ghost_settings()
    try:
        response = requests.get(settings["jwks_url"], timeout=5)
        response.raise_for_status()
    except RequestException as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Falha ao obter a chave pública do Ghost Members.",
        ) from exc

    jwk_data = response.json()
    keys = jwk_data.get("keys")
    if not keys:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Formato inesperado recebido ao buscar a chave pública do Ghost Members.",
        )

    return RSAAlgorithm.from_jwk(json.dumps(keys[0]))


def _extract_token(authorization_header: Optional[str]) -> str:
    if not authorization_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Cabeçalho Authorization ausente.",
        )
    parts = authorization_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Cabeçalho Authorization inválido.",
        )
    return parts[1]


def verify_token_header(authorization_header: Optional[str]) -> Dict[str, Any]:
    """Validate a Ghost Members JWT from an Authorization header."""

    settings = get_ghost_settings()
    token = _extract_token(authorization_header)
    public_key = get_public_key()

    try:
        return jwt.decode(
            token,
            public_key,
            algorithms=[JWT_ALGORITHM],
            audience=settings["audience"],
            issuer=settings["issuer"],
        )
    except InvalidSignatureError:
        get_public_key.cache_clear()
        public_key = get_public_key()
        return jwt.decode(
            token,
            public_key,
            algorithms=[JWT_ALGORITHM],
            audience=settings["audience"],
            issuer=settings["issuer"],
        )
    except ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="O token expirou.",
        ) from exc
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="O token é inválido.",
        ) from exc


__all__ = ["verify_token_header", "get_ghost_settings", "get_public_key"]
