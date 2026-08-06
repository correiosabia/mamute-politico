"""Cliente HTTP do Portal da Transparencia.

A API responde com um array JSON puro, sem envelope e sem contagem total. A
paginacao termina quando uma pagina volta vazia — nao ha link `next` como nas
APIs da Camara.

Medido em 2026-08-06: 15 registros por pagina (fixo, sem parametro de tamanho);
2022 tem 408 paginas, 2024 tem 466 e 2026 tem 355.

O limite e por chave: 30 requisicoes/minuto fora da madrugada, ou seja 2s por
requisicao cravados. O atraso padrao e 2.2s para nao raspar o teto, o que da
~15 min por ano coletado.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Iterator, List, Optional

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://api.portaldatransparencia.gov.br/api-de-dados"
EMENDAS_ENDPOINT = f"{BASE_URL}/emendas"
API_KEY_HEADER = "chave-api-dados"
DEFAULT_REQUEST_DELAY = 2.2
REQUEST_TIMEOUT = 60


class MissingApiKeyError(RuntimeError):
    """Chave do Portal da Transparencia ausente ou vazia."""


class PortalTransparenciaClient:
    def __init__(
        self,
        api_key: str,
        *,
        request_delay: float = DEFAULT_REQUEST_DELAY,
    ) -> None:
        if not api_key or not api_key.strip():
            raise MissingApiKeyError(
                "PORTAL_TRANSPARENCIA_API_KEY nao definida. Cadastre-se em "
                "portaldatransparencia.gov.br/api-de-dados/cadastrar-email"
            )
        self._api_key = api_key.strip()
        self._request_delay = request_delay

    def __repr__(self) -> str:  # nunca expor a chave
        return f"<PortalTransparenciaClient delay={self._request_delay}>"

    def _get_page(self, year: int, page: int) -> Optional[List[Dict[str, Any]]]:
        try:
            response = requests.get(
                EMENDAS_ENDPOINT,
                params={"ano": year, "pagina": page},
                headers={API_KEY_HEADER: self._api_key, "Accept": "application/json"},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.error(
                "Falha ao consultar emendas (ano=%s, pagina=%s): %s", year, page, exc
            )
            return None

        try:
            data = response.json()
        except ValueError as exc:
            logger.error(
                "JSON invalido do Portal (ano=%s, pagina=%s): %s", year, page, exc
            )
            return None

        if not isinstance(data, list):
            # A fonte devolve array puro; um dict e erro disfarcado de 200.
            logger.error(
                "Resposta inesperada do Portal (ano=%s, pagina=%s): "
                "esperava lista, veio %s",
                year,
                page,
                type(data).__name__,
            )
            return None

        return [item for item in data if isinstance(item, dict)]

    def iter_amendments(self, year: int) -> Iterator[Dict[str, Any]]:
        """Itera todas as emendas de um ano, pagina a pagina."""
        page = 1
        while True:
            items = self._get_page(year, page)
            if not items:
                return
            yield from items
            page += 1
            if self._request_delay:
                time.sleep(self._request_delay)


__all__ = [
    "API_KEY_HEADER",
    "DEFAULT_REQUEST_DELAY",
    "EMENDAS_ENDPOINT",
    "MissingApiKeyError",
    "PortalTransparenciaClient",
]
