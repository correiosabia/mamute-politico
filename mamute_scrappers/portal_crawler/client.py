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

# O Portal devolve 504 esporadico sob carga. Sem retentativa, uma unica falha
# truncava o ano inteiro em silencio.
MAX_PAGE_ATTEMPTS = 4
RETRY_BACKOFF_SECONDS = 10


class MissingApiKeyError(RuntimeError):
    """Chave do Portal da Transparencia ausente ou vazia."""


class IncompletePaginationError(RuntimeError):
    """Uma pagina nao pode ser lida; o ano ficaria incompleto.

    Existe para que a falha seja ruidosa. O crawler sai com codigo != 0, o
    orquestrador de backfill NAO marca o chunk como concluido e tenta o ano de
    novo na proxima execucao.
    """


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

    def _get_page_with_retry(
        self,
        year: int,
        page: int,
    ) -> Optional[List[Dict[str, Any]]]:
        """Busca uma pagina, insistindo em falha transitoria.

        Devolve None so quando todas as tentativas falharam — ou seja, None
        significa "nao consegui ler", nunca "acabaram os dados".
        """
        for attempt in range(1, MAX_PAGE_ATTEMPTS + 1):
            items = self._get_page(year, page)
            if items is not None:
                return items
            if attempt < MAX_PAGE_ATTEMPTS:
                espera = RETRY_BACKOFF_SECONDS * attempt
                logger.warning(
                    "Repetindo ano=%s pagina=%s em %ss (tentativa %s/%s)",
                    year,
                    page,
                    espera,
                    attempt,
                    MAX_PAGE_ATTEMPTS,
                )
                time.sleep(espera)
        return None

    def iter_amendments(self, year: int) -> Iterator[Dict[str, Any]]:
        """Itera todas as emendas de um ano, pagina a pagina.

        Levanta IncompletePaginationError se uma pagina nao puder ser lida apos
        as retentativas. Encerrar em silencio seria pior: o ano ficaria truncado
        com cara de sucesso, o orquestrador marcaria o chunk como concluido e
        ninguem voltaria la. Foi o que aconteceu com 2022 em producao — um 504
        na pagina 299 de 408 cortou ~27% das emendas do ano.
        """
        page = 1
        while True:
            items = self._get_page_with_retry(year, page)
            if items is None:
                raise IncompletePaginationError(
                    f"Nao foi possivel ler a pagina {page} do ano {year} apos "
                    f"{MAX_PAGE_ATTEMPTS} tentativas; ano incompleto."
                )
            if not items:
                return  # pagina vazia = fim legitimo dos dados
            yield from items
            page += 1
            if self._request_delay:
                time.sleep(self._request_delay)


__all__ = [
    "API_KEY_HEADER",
    "IncompletePaginationError",
    "MAX_PAGE_ATTEMPTS",
    "DEFAULT_REQUEST_DELAY",
    "EMENDAS_ENDPOINT",
    "MissingApiKeyError",
    "PortalTransparenciaClient",
]
