from __future__ import annotations

from decimal import Decimal

import pytest

from mamute_scrappers.portal_crawler import parsing


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("1.000.000,00", Decimal("1000000.00")),
        ("0,00", Decimal("0.00")),
        ("1.500,50", Decimal("1500.50")),
        ("-1.500,50", Decimal("-1500.50")),
        ("250,00", Decimal("250.00")),
        # Sem centavos: o ponto e separador de milhar no formato brasileiro,
        # entao "1.000" vale mil, nunca um inteiro e meio.
        ("1.000", Decimal("1000")),
        ("  2.000,00  ", Decimal("2000.00")),
        ("R$ 3.000,00", Decimal("3000.00")),
        # Valores reais observados na fonte.
        ("1.099.734,20", Decimal("1099734.20")),
        ("7,00", Decimal("7.00")),
    ],
)
def test_parse_brl_converte_formato_brasileiro(raw, expected):
    assert parsing.parse_brl(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", None, "-", "n/a"])
def test_parse_brl_devolve_none_para_vazio_ou_invalido(raw):
    assert parsing.parse_brl(raw) is None


def test_parse_brl_aceita_numero_ja_tipado():
    assert parsing.parse_brl(1500) == Decimal("1500")
    assert parsing.parse_brl(Decimal("12.34")) == Decimal("12.34")


@pytest.mark.parametrize(
    "raw",
    [
        "Individual",
        "INDIVIDUAL",
        "Emenda Individual",
        "Individual - Impositiva",
        "  individual  ",
        # Valor literal observado na fonte em 2026-08-06.
        "Emenda Individual - Transferências com Finalidade Definida",
    ],
)
def test_is_individual_amendment_reconhece_variacoes(raw):
    assert parsing.is_individual_amendment(raw) is True


@pytest.mark.parametrize(
    "raw",
    [
        "Bancada",
        "Emenda de Bancada",  # segundo valor literal observado na fonte
        "Comissão",
        "Relator",
        "",
        None,
        "Coletiva",
    ],
)
def test_is_individual_amendment_rejeita_demais_tipos(raw):
    assert parsing.is_individual_amendment(raw) is False


def test_normalize_text_remove_acento_e_caixa():
    assert parsing.normalize_text("José  da  SILVA") == "jose da silva"
    assert parsing.normalize_text("  Comissão ") == "comissao"
    assert parsing.normalize_text(None) == ""


def test_normalize_text_lida_com_caixa_alta_da_fonte():
    # O Portal devolve nomes em caixa alta: "HEITOR SCHUCH".
    assert parsing.normalize_text("HEITOR SCHUCH") == "heitor schuch"
    assert parsing.normalize_text("ADRIANO DO BALDY") == "adriano do baldy"
