"""Cliente PostgREST do Transferegov. API publica, sem chave."""
from __future__ import annotations

from mamute_scrappers.transferegov_crawler.client import TransferegovClient


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(f"HTTP {self.status_code}")


def test_iter_rows_pagina_ate_esgotar(monkeypatch):
    paginas = [[{"id": 1}, {"id": 2}], [{"id": 3}]]
    chamadas = []

    def fake_get(url, params=None, timeout=None):
        chamadas.append(params)
        return _FakeResponse(paginas[len(chamadas) - 1])

    client = TransferegovClient()
    monkeypatch.setattr(client._session, "get", fake_get)

    linhas = list(client.iter_rows("plano_acao_especial", page_size=2))
    assert [x["id"] for x in linhas] == [1, 2, 3]
    assert chamadas[0]["offset"] == 0
    assert chamadas[1]["offset"] == 2


def test_iter_rows_para_na_pagina_vazia(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        return _FakeResponse([])

    client = TransferegovClient()
    monkeypatch.setattr(client._session, "get", fake_get)
    assert list(client.iter_rows("plano_acao_especial", page_size=10)) == []


def test_fetch_in_quebra_em_lotes(monkeypatch):
    """O filtro in.() vai na query string e estoura a URL com milhares de ids."""
    recebidos = []

    def fake_get(url, params=None, timeout=None):
        recebidos.append(params["id_plano_acao"])
        return _FakeResponse([])

    client = TransferegovClient()
    monkeypatch.setattr(client._session, "get", fake_get)

    client.fetch_in("relatorio_gestao_especial", "id_plano_acao", [1, 2, 3], chunk=2)
    assert recebidos == ["in.(1,2)", "in.(3)"]


def test_fetch_in_com_lista_vazia_nao_chama_a_fonte(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        raise AssertionError("nao deveria chamar")

    client = TransferegovClient()
    monkeypatch.setattr(client._session, "get", fake_get)
    assert client.fetch_in("x", "id", [], chunk=2) == []
