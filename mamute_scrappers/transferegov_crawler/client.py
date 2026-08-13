"""Cliente da API publica de Transferencias Especiais do Transferegov.

PostgREST, sem chave de API — diferente do Portal da Transparencia, que exige
`PORTAL_TRANSPARENCIA_API_KEY`.

So o modulo `transferenciasespeciais` existe hoje. O de Discricionarias e
Legais, que cobriria as emendas de Finalidade Definida (85% da nossa base),
ainda nao tem API: o cronograma oficial preve a 1a entrega entre 07/2026 e
10/2026, e instrumentos so em 2027.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterator, List, Optional, Sequence

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://api.transferegov.gestao.gov.br/transferenciasespeciais"
TIMEOUT = 90


class TransferegovClient:
    def __init__(self, base_url: str = BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")
        self._session = requests.Session()

    def iter_rows(
        self,
        tabela: str,
        select: Optional[str] = None,
        page_size: int = 1000,
    ) -> Iterator[Dict[str, Any]]:
        """Percorre a tabela inteira paginando por limit/offset.

        Para na primeira pagina vazia ou incompleta — a fonte nao devolve
        contagem sem `Prefer: count=exact`, que custa uma varredura a mais.
        """
        offset = 0
        while True:
            params: Dict[str, Any] = {"limit": page_size, "offset": offset}
            if select:
                params["select"] = select

            resposta = self._session.get(
                f"{self.base_url}/{tabela}", params=params, timeout=TIMEOUT
            )
            resposta.raise_for_status()
            linhas = resposta.json()

            if not linhas:
                return
            for linha in linhas:
                yield linha
            if len(linhas) < page_size:
                return
            offset += page_size

    def fetch_in(
        self,
        tabela: str,
        coluna: str,
        valores: Sequence[Any],
        chunk: int = 100,
    ) -> List[Dict[str, Any]]:
        """Busca as linhas cujo `coluna` esta na lista, em lotes.

        O lote existe porque o filtro `in.()` do PostgREST vai na query string
        e estoura o limite de URL com milhares de ids.
        """
        resultado: List[Dict[str, Any]] = []
        for i in range(0, len(valores), chunk):
            lote = valores[i : i + chunk]
            filtro = "in.(%s)" % ",".join(str(v) for v in lote)
            resposta = self._session.get(
                f"{self.base_url}/{tabela}",
                params={coluna: filtro},
                timeout=TIMEOUT,
            )
            resposta.raise_for_status()
            resultado.extend(resposta.json())
        return resultado


__all__ = ["TransferegovClient", "BASE_URL"]
