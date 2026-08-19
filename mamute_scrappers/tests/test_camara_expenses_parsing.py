"""Parse do CSV anual da cota parlamentar da Camara (CS-57).

A fixture reproduz linhas reais do Ano-2025.csv, cobrindo os casos de borda
medidos na fonte: linha de lideranca sem ideCadastro, telefonia com
ideDocumento='0' (ausente), bilhete SIGEPA sem urlDocumento e valor negativo
de compensacao.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from mamute_scrappers.camara_crawler import expenses as camara_expenses

FIXTURE = Path(__file__).parent / "fixtures" / "cota_camara_2025_sample.csv"


def _rows():
    return list(camara_expenses.iter_csv_rows(FIXTURE))


def test_fixture_tem_todas_as_linhas():
    assert len(_rows()) == 6


def test_build_payload_linha_normal():
    row = _rows()[1]  # Danilo Forte, com ideDocumento e urlDocumento
    payload = camara_expenses.build_payload(row)
    assert payload["house"] == "camara"
    assert payload["ide_cadastro"] == 62881
    assert payload["year"] == 2025
    assert payload["month"] == 2
    assert payload["expense_type"] == (
        "MANUTENÇÃO DE ESCRITÓRIO DE APOIO À ATIVIDADE PARLAMENTAR"
    )
    assert payload["supplier_name"] == "ALARES"
    assert payload["supplier_id"] == "633.560.420/0018-0"
    assert payload["document_number"] == "5771570"
    assert payload["document_date"] == date(2025, 2, 28)
    assert payload["document_value"] == Decimal("104.58")
    assert payload["glosa_value"] == Decimal("0")
    assert payload["net_value"] == Decimal("104.58")
    assert payload["document_url"] == (
        "https://www.camara.leg.br/cota-parlamentar/documentos/publ/2227/2025/7883485.pdf"
    )
    # subcota + ideDocumento + parcela: espacos de id diferentes (SIGEPA x
    # cota) nao colidem e parcela repetida nao vira duplicata.
    assert payload["source_key"] == "1:7883485:0"


def test_lideranca_sem_ide_cadastro_persiste_sem_vinculo():
    payload = camara_expenses.build_payload(_rows()[0])
    assert payload is not None
    assert payload["ide_cadastro"] is None
    assert payload["source_key"] == "1:7877589:0"


def test_glosa_e_valor_liquido():
    payload = camara_expenses.build_payload(_rows()[2])
    assert payload["glosa_value"] == Decimal("2.16")
    assert payload["net_value"] == Decimal("104.58")
    assert payload["document_value"] == Decimal("106.74")


def test_ide_documento_zero_vira_hash_estavel():
    row = _rows()[3]  # TELEFONIA, ideDocumento='0', sem data de emissao
    p1 = camara_expenses.build_payload(row)
    p2 = camara_expenses.build_payload(dict(row))
    assert p1["source_key"] == p2["source_key"]
    assert ":" not in p1["source_key"]  # hash, nao chave composta
    assert len(p1["source_key"]) == 40  # sha1 hex
    assert p1["document_date"] is None
    assert p1["document_url"] is None


def test_sigepa_com_trecho_e_valor_negativo():
    payload = camara_expenses.build_payload(_rows()[5])
    assert payload["net_value"] == Decimal("-2113.91")
    assert payload["document_url"] is None
    assert "BSB/BSB" in payload["details"]
    assert "FRANCISCO DANILO BASTOS FORTE" in payload["details"]
    assert payload["source_key"] == "998:319264:0"


def test_bilhetes_sigepa_e_cota_nao_colidem():
    # Mesmos ideDocumento hipoteticamente iguais em subcotas distintas
    # produzem chaves distintas — o prefixo da subcota separa os espacos.
    rows = _rows()
    keys = {camara_expenses.build_payload(r)["source_key"] for r in rows}
    assert len(keys) == len(rows)
