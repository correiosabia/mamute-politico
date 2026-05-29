"""Testes de resolução do campo status em parlamentares."""

from __future__ import annotations

from datetime import date

from api.routers.parliamentarians import _resolve_parliamentarian_status


def test_camara_status_from_details_when_column_empty() -> None:
    details = {"ultimoStatus": {"situacao": "Vacância"}}
    assert (
        _resolve_parliamentarian_status(
            parliamentarian_type="Deputado",
            stored_status=None,
            details=details,
        )
        == "Vacância"
    )


def test_camara_prefers_stored_status() -> None:
    details = {"ultimoStatus": {"situacao": "Vacância"}}
    assert (
        _resolve_parliamentarian_status(
            parliamentarian_type="Deputado",
            stored_status="Exercício",
            details=details,
        )
        == "Exercício"
    )


def test_senado_status_from_mandato_dates() -> None:
    details = {
        "lista": {
            "Mandato": {
                "PrimeiraLegislaturaDoMandato": {
                    "DataInicio": "2023-02-01",
                    "DataFim": "2027-01-31",
                    "NumeroLegislatura": "57",
                },
                "SegundaLegislaturaDoMandato": {
                    "DataInicio": "2027-02-01",
                    "DataFim": "2031-01-31",
                    "NumeroLegislatura": "58",
                },
            }
        }
    }
    assert (
        _resolve_parliamentarian_status(
            parliamentarian_type="Senador",
            stored_status=None,
            details=details,
            reference_date=date(2026, 5, 29),
        )
        == "Exercício"
    )


def test_senado_fim_de_mandato_when_period_ended() -> None:
    details = {
        "lista": {
            "Mandato": {
                "PrimeiraLegislaturaDoMandato": {
                    "DataInicio": "2019-02-01",
                    "DataFim": "2023-01-31",
                }
            }
        }
    }
    assert (
        _resolve_parliamentarian_status(
            parliamentarian_type="Senador",
            stored_status=None,
            details=details,
            reference_date=date(2026, 5, 29),
        )
        == "Fim de mandato"
    )


def test_senado_defaults_to_exercicio_without_mandato() -> None:
    assert (
        _resolve_parliamentarian_status(
            parliamentarian_type="Senador",
            stored_status=None,
            details={"lista": {"IdentificacaoParlamentar": {"NomeParlamentar": "X"}}},
        )
        == "Exercício"
    )
