from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List

import pytest

from mamute_scrappers.portal_crawler import client as client_mod
from mamute_scrappers.portal_crawler import emendas as emendas_mod


class FakeResponse:
    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise client_mod.requests.HTTPError(f"status {self.status_code}")

    def json(self) -> Any:
        return self._payload


def test_exige_chave_de_api():
    with pytest.raises(client_mod.MissingApiKeyError):
        client_mod.PortalTransparenciaClient("")


def test_pagina_ate_receber_lista_vazia(monkeypatch):
    paginas = {1: [{"codigoEmenda": "a"}], 2: [{"codigoEmenda": "b"}], 3: []}
    chamadas: List[Dict[str, Any]] = []

    def fake_get(url, params=None, headers=None, timeout=None):
        chamadas.append({"url": url, "params": params, "headers": headers})
        return FakeResponse(paginas[params["pagina"]])

    monkeypatch.setattr(client_mod.requests, "get", fake_get)

    api = client_mod.PortalTransparenciaClient("chave-secreta", request_delay=0)
    itens = list(api.iter_amendments(2026))

    assert [i["codigoEmenda"] for i in itens] == ["a", "b"]
    assert [c["params"]["pagina"] for c in chamadas] == [1, 2, 3]
    assert all(c["params"]["ano"] == 2026 for c in chamadas)


def test_envia_a_chave_no_header_esperado(monkeypatch):
    capturado: Dict[str, Any] = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        capturado.update(headers or {})
        return FakeResponse([])

    monkeypatch.setattr(client_mod.requests, "get", fake_get)
    api = client_mod.PortalTransparenciaClient("chave-secreta", request_delay=0)
    list(api.iter_amendments(2026))

    assert capturado[client_mod.API_KEY_HEADER] == "chave-secreta"


def test_erro_http_encerra_a_paginacao_sem_propagar(monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        return FakeResponse({}, status_code=500)

    monkeypatch.setattr(client_mod.requests, "get", fake_get)

    api = client_mod.PortalTransparenciaClient("chave", request_delay=0)
    assert list(api.iter_amendments(2026)) == []


def test_resposta_que_nao_e_lista_encerra_a_paginacao(monkeypatch):
    # A fonte devolve array puro; um dict e sinal de erro disfarcado de 200.
    def fake_get(url, params=None, headers=None, timeout=None):
        return FakeResponse({"Erro na API": "..."})

    monkeypatch.setattr(client_mod.requests, "get", fake_get)

    api = client_mod.PortalTransparenciaClient("chave", request_delay=0)
    assert list(api.iter_amendments(2026)) == []


def test_a_chave_nunca_aparece_em_repr():
    api = client_mod.PortalTransparenciaClient("chave-super-secreta")
    assert "chave-super-secreta" not in repr(api)


# --- payload -----------------------------------------------------------------

# Item real capturado da API em 2026-08-06.
ITEM = {
    "codigoEmenda": "202632980010",
    "ano": 2026,
    "tipoEmenda": "Emenda Individual - Transferências com Finalidade Definida",
    "autor": "HEITOR SCHUCH",
    "nomeAutor": "HEITOR SCHUCH",
    "numeroEmenda": "0010",
    "localidadeDoGasto": "RIO GRANDE DO SUL (UF)",
    "funcao": "Assistência social",
    "subfuncao": "Alimentação e nutrição",
    "valorEmpenhado": "0,00",
    "valorLiquidado": "1.099.734,20",
    "valorPago": "0,00",
    "valorRestoInscrito": "0,00",
    "valorRestoCancelado": "0,00",
    "valorRestoPago": "0,00",
}


def test_build_payload_converte_campos():
    payload = emendas_mod.build_payload(ITEM)

    assert payload["amendment_code"] == "202632980010"
    assert payload["year"] == 2026
    assert payload["amendment_number"] == "0010"
    assert payload["author_name_raw"] == "HEITOR SCHUCH"
    assert payload["author_raw"] == "HEITOR SCHUCH"
    assert payload["spending_locality"] == "RIO GRANDE DO SUL (UF)"
    assert payload["function"] == "Assistência social"
    assert payload["subfunction"] == "Alimentação e nutrição"
    assert payload["committed_value"] == Decimal("0.00")
    assert payload["settled_value"] == Decimal("1099734.20")
    assert payload["paid_value"] == Decimal("0.00")


def test_build_payload_sem_codigo_devolve_none():
    assert emendas_mod.build_payload({"ano": 2026}) is None
