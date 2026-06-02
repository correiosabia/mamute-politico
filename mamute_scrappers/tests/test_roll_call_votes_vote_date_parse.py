"""Testa que os crawlers de roll_call_votes capturam a data da votação no payload.

A persistência em si (gravar `vote_date` na coluna) é exercitada em integração;
estes testes garantem o pedaço puro: parse do JSON da API → campo correto."""

from __future__ import annotations

import importlib.util
from datetime import date, datetime
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, relative_path: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


camara_rcv = _load(
    "test_camara_roll_call_votes_parse",
    "mamute_scrappers/camara_crawler/roll_call_votes.py",
)
senado_rcv = _load(
    "test_senado_roll_call_votes_parse",
    "mamute_scrappers/senado_crawler/roll_call_votes.py",
)


def test_camara_build_vote_payloads_parses_data_hora_registro() -> None:
    detail = {
        "dataHoraRegistro": "2024-08-14T15:30:00",
        "descricao": "Aprovação do parecer",
        "proposicoesAfetadas": [{"id": 999111}],
    }
    votos = [
        {"deputado_": {"id": 220645}, "tipoVoto": "Sim"},
        {"deputado_": {"id": 178982}, "tipoVoto": "Não"},
    ]

    payloads = camara_rcv._build_vote_payloads("VOT-1", detail, votos)

    assert len(payloads) == 2
    assert all(p["vote_date"] == datetime(2024, 8, 14, 15, 30, 0) for p in payloads)
    # Sanidade do shape — proposição e tipo continuam ali, sem regressão.
    assert payloads[0]["proposition_code"] == 999111
    assert payloads[0]["vote"] == "Sim"


def test_camara_build_vote_payloads_handles_missing_data_hora_registro() -> None:
    detail = {"proposicoesAfetadas": [{"id": 1}], "dataHoraRegistro": None}
    votos = [{"deputado_": {"id": 1}, "tipoVoto": "Sim"}]

    payloads = camara_rcv._build_vote_payloads("VOT-2", detail, votos)
    assert payloads[0]["vote_date"] is None


def test_senado_build_vote_payload_parses_data_sessao() -> None:
    entry = {
        "codigoMateria": 12345,
        "codigoSessao": "1",
        "codigoSessaoVotacao": "2",
        "codigoVotacaoSve": "3",
        "dataSessao": "2024-08-14 14:30:00",
        "votos": [
            {"codigoParlamentar": "6331", "siglaVotoParlamentar": "Sim"},
            {"codigoParlamentar": "6332", "siglaVotoParlamentar": "Não"},
        ],
    }

    payload = senado_rcv._build_vote_payload(entry, parliamentarian_code=6331)

    assert payload is not None
    assert payload["session_date"] == datetime(2024, 8, 14, 14, 30, 0)
    assert payload["vote"] == "Sim"


def test_senado_build_vote_payload_supports_capitalized_keys() -> None:
    entry = {
        "CodigoMateria": "9999",
        "CodigoSessao": "10",
        "CodigoSessaoVotacao": "20",
        "DataSessao": "2024-08-14",
        "Votos": [
            {"CodigoParlamentar": "6331", "SiglaVotoParlamentar": "Sim"},
        ],
    }

    payload = senado_rcv._build_vote_payload(entry, parliamentarian_code=6331)

    assert payload is not None
    # Sem hora -> datetime à meia-noite. O upsert grava só a .date().
    assert payload["session_date"] == datetime(2024, 8, 14)
    assert payload["session_date"].date() == date(2024, 8, 14)
