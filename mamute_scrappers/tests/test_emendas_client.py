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


def test_erro_http_persistente_levanta_em_vez_de_truncar(monkeypatch):
    """Um 504 nao pode virar "acabaram os dados".

    Em producao um 504 na pagina 299 de 408 cortou ~27% das emendas de 2022, e o
    chunk foi marcado como concluido. Falhar alto e o comportamento correto: o
    orquestrador tenta o ano de novo.
    """
    monkeypatch.setattr(client_mod.time, "sleep", lambda _s: None)

    def fake_get(url, params=None, headers=None, timeout=None):
        return FakeResponse({}, status_code=504)

    monkeypatch.setattr(client_mod.requests, "get", fake_get)

    api = client_mod.PortalTransparenciaClient("chave", request_delay=0)
    with pytest.raises(client_mod.IncompletePaginationError):
        list(api.iter_amendments(2026))


def test_erro_transitorio_e_superado_por_retentativa(monkeypatch):
    monkeypatch.setattr(client_mod.time, "sleep", lambda _s: None)
    tentativas = {"n": 0}

    def fake_get(url, params=None, headers=None, timeout=None):
        if params["pagina"] == 1:
            tentativas["n"] += 1
            if tentativas["n"] < 3:  # falha duas vezes, acerta na terceira
                return FakeResponse({}, status_code=504)
            return FakeResponse([{"codigoEmenda": "a"}])
        return FakeResponse([])

    monkeypatch.setattr(client_mod.requests, "get", fake_get)

    api = client_mod.PortalTransparenciaClient("chave", request_delay=0)
    itens = list(api.iter_amendments(2026))

    assert [i["codigoEmenda"] for i in itens] == ["a"]
    assert tentativas["n"] == 3


def test_pagina_vazia_encerra_normalmente_sem_erro(monkeypatch):
    # Pagina vazia e fim legitimo — nao pode virar excecao.
    def fake_get(url, params=None, headers=None, timeout=None):
        return FakeResponse([]) if params["pagina"] > 1 else FakeResponse(
            [{"codigoEmenda": "a"}]
        )

    monkeypatch.setattr(client_mod.requests, "get", fake_get)
    api = client_mod.PortalTransparenciaClient("chave", request_delay=0)
    assert len(list(api.iter_amendments(2026))) == 1


def test_resposta_que_nao_e_lista_levanta(monkeypatch):
    # A fonte devolve array puro; um dict e erro disfarcado de 200.
    monkeypatch.setattr(client_mod.time, "sleep", lambda _s: None)

    def fake_get(url, params=None, headers=None, timeout=None):
        return FakeResponse({"Erro na API": "..."})

    monkeypatch.setattr(client_mod.requests, "get", fake_get)

    api = client_mod.PortalTransparenciaClient("chave", request_delay=0)
    with pytest.raises(client_mod.IncompletePaginationError):
        list(api.iter_amendments(2026))


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


# --- carregamento do .env -----------------------------------------------------


def test_le_a_chave_do_arquivo_env_sem_variavel_exportada(tmp_path, monkeypatch):
    """Regressao: em producao a chave vive no .env, nao no ambiente.

    O crawler le a chave ANTES de tocar no banco, e e o import de db/engine.py
    que carrega o .env — entao sem carregamento proprio a variavel nao existe.
    Localmente o bug ficava invisivel porque a variavel era exportada na mao.
    """
    monkeypatch.delenv(emendas_mod.API_KEY_ENV, raising=False)
    # Isola de um .env real do repositorio, que venceria por vir antes na lista
    # de candidatos e tornaria o teste dependente da maquina.
    monkeypatch.setattr(emendas_mod, "PROJECT_ROOT", tmp_path)

    env_file = tmp_path / ".env"
    env_file.write_text(
        f"{emendas_mod.API_KEY_ENV}=chave-vinda-do-arquivo\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    emendas_mod._load_env_file()

    import os

    assert os.getenv(emendas_mod.API_KEY_ENV) == "chave-vinda-do-arquivo"


def test_variavel_exportada_tem_precedencia_sobre_o_arquivo(tmp_path, monkeypatch):
    monkeypatch.setenv(emendas_mod.API_KEY_ENV, "chave-do-ambiente")
    monkeypatch.setattr(emendas_mod, "PROJECT_ROOT", tmp_path)

    env_file = tmp_path / ".env"
    env_file.write_text(
        f"{emendas_mod.API_KEY_ENV}=chave-do-arquivo\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    emendas_mod._load_env_file()

    import os

    assert os.getenv(emendas_mod.API_KEY_ENV) == "chave-do-ambiente"


# --- conferencia por codigo ----------------------------------------------------


def test_fetch_amendment_consulta_por_codigo_e_devolve_o_item(monkeypatch):
    capturado: Dict[str, Any] = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        capturado.update(params or {})
        return FakeResponse([ITEM])

    monkeypatch.setattr(client_mod.requests, "get", fake_get)
    api = client_mod.PortalTransparenciaClient("chave-secreta", request_delay=0)

    item = api.fetch_amendment("202632980010")

    assert capturado == {"codigoEmenda": "202632980010"}
    assert item is not None
    assert item["valorLiquidado"] == "1.099.734,20"


def test_fetch_amendment_ignora_item_de_outro_codigo(monkeypatch):
    """A resposta e um array; so aceitamos o codigo que pedimos."""
    monkeypatch.setattr(
        client_mod.requests,
        "get",
        lambda *a, **k: FakeResponse([{**ITEM, "codigoEmenda": "999"}]),
    )
    api = client_mod.PortalTransparenciaClient("chave-secreta", request_delay=0)

    assert api.fetch_amendment("202632980010") is None


@pytest.mark.parametrize("resposta", [[], {"erro": "x"}])
def test_fetch_amendment_devolve_none_sem_levantar(monkeypatch, resposta):
    """Conferir e melhor-esforco: falha nao pode derrubar a coleta do ano."""
    monkeypatch.setattr(
        client_mod.requests, "get", lambda *a, **k: FakeResponse(resposta)
    )
    api = client_mod.PortalTransparenciaClient("chave-secreta", request_delay=0)

    assert api.fetch_amendment("202632980010") is None


def test_fetch_amendment_devolve_none_quando_a_rede_falha(monkeypatch):
    def fake_get(*a, **k):
        raise client_mod.requests.ConnectionError("sem rede")

    monkeypatch.setattr(client_mod.requests, "get", fake_get)
    api = client_mod.PortalTransparenciaClient("chave-secreta", request_delay=0)

    assert api.fetch_amendment("202632980010") is None


def test_fetch_amendment_respeita_o_atraso_entre_requisicoes(monkeypatch):
    """O teto de 30 req/min do Portal e por chave: as conferencias somam no
    mesmo balde da paginacao."""
    dormidas: List[float] = []
    monkeypatch.setattr(client_mod.time, "sleep", dormidas.append)
    monkeypatch.setattr(
        client_mod.requests, "get", lambda *a, **k: FakeResponse([ITEM])
    )
    api = client_mod.PortalTransparenciaClient("chave-secreta", request_delay=2.2)

    api.fetch_amendment("202632980010")

    assert dormidas == [2.2]
