from __future__ import annotations

from datetime import date

import pytest

from mamute_scrappers.tse_crawler.profile import (
    PROFILE_SOURCE_API,
    PROFILE_SOURCE_CSV,
    extract_profile_from_csv_row,
    extract_profile_from_detail,
    normalize_profile_text,
    parse_birth_date,
)


@pytest.mark.parametrize("sentinela", ["#NE", "#NE#", "#NULO", "#NULO#"])
def test_sentinelas_do_tse_viram_none(sentinela):
    assert normalize_profile_text(sentinela) is None


def test_normalizacao_uppercase_e_espacos():
    assert normalize_profile_text("Superior  completo ") == "SUPERIOR COMPLETO"
    assert normalize_profile_text(None) is None
    assert normalize_profile_text("   ") is None


def test_parse_birth_date_formatos_api_e_csv():
    assert parse_birth_date("1970-10-20") == date(1970, 10, 20)
    assert parse_birth_date("05/02/1956") == date(1956, 2, 5)
    assert parse_birth_date("#NULO") is None
    assert parse_birth_date("data invalida") is None


def test_extract_da_api_normaliza_para_forma_do_csv():
    detail = {
        "dataDeNascimento": "1984-02-14",
        "descricaoSexo": "MASC.",
        "descricaoCorRaca": "PRETA",
        "grauInstrucao": "Superior completo",
        "ocupacao": "Professor de Ensino Fundamental",
        "descricaoEstadoCivil": "Casado(a)",
        "nacionalidade": "Brasileira nata",
    }
    profile = extract_profile_from_detail(detail)
    assert profile == {
        "birth_date": date(1984, 2, 14),
        "gender": "MASCULINO",
        "race": "PRETA",
        "education": "SUPERIOR COMPLETO",
        "occupation": "PROFESSOR DE ENSINO FUNDAMENTAL",
        "marital_status": "CASADO(A)",
        "nationality": "BRASILEIRA NATA",
        "federation": None,
        "profile_source": PROFILE_SOURCE_API,
    }


def test_extract_do_csv_com_sentinelas_pre_2014():
    row = {
        "DT_NASCIMENTO": "05/02/1956",
        "DS_GENERO": "MASCULINO",
        "DS_COR_RACA": "#NE",
        "DS_GRAU_INSTRUCAO": "LÊ E ESCREVE",
        "DS_OCUPACAO": "TRABALHADOR AGRÍCOLA",
        "DS_ESTADO_CIVIL": "CASADO(A)",
        "DS_NACIONALIDADE": "BRASILEIRA",
        "SG_FEDERACAO": None,
    }
    profile = extract_profile_from_csv_row(row)
    assert profile["race"] is None
    assert profile["federation"] is None
    assert profile["education"] == "LÊ E ESCREVE"
    assert profile["profile_source"] == PROFILE_SOURCE_CSV


def test_mesma_pessoa_nas_duas_fontes_produz_valores_identicos():
    """Agregacao cruzada (GROUP BY) depende das fontes convergirem."""
    api = extract_profile_from_detail(
        {
            "descricaoSexo": "FEM.",
            "grauInstrucao": "Superior completo",
            "descricaoEstadoCivil": "Solteiro(a)",
            "ocupacao": "Empresário",
        }
    )
    csv_row = extract_profile_from_csv_row(
        {
            "DS_GENERO": "FEMININO",
            "DS_GRAU_INSTRUCAO": "SUPERIOR COMPLETO",
            "DS_ESTADO_CIVIL": "SOLTEIRO(A)",
            "DS_OCUPACAO": "EMPRESÁRIO",
        }
    )
    for field in ("gender", "education", "marital_status", "occupation"):
        assert api[field] == csv_row[field]
