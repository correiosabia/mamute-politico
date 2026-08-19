"""Parse da API de despesas CEAPS do Senado (CS-57).

A fixture tem um item real de cada tipo de despesa da fonte, mais um item com
tipoDespesa nulo (76 ocorrencias medidas em 2025) — que vira "Não informado",
porque expense_type e NOT NULL e a linha e fato publico que nao deve sumir.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from mamute_scrappers.senado_crawler import expenses as senado_expenses

FIXTURE = Path(__file__).parent / "fixtures" / "ceaps_2025_sample.json"


def _items():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _by_prefix(prefix: str):
    for item in _items():
        if (item.get("tipoDespesa") or "").startswith(prefix):
            return item
    raise AssertionError(f"fixture sem item {prefix!r}")


def test_mapa_de_categorias_do_portal():
    """Categorias levantadas empiricamente no portal em 19/08/2026."""
    casos = {
        "Aluguel de imóveis": 1,
        "Aquisição de material de consumo": 2,
        "Locomoção, hospedagem": 3,
        "Contratação de consultorias": 4,
        "Divulgação da atividade parlamentar": 5,
        "Passagens aéreas": 8,
        "Serviços de Segurança Privada": 9,
    }
    for prefix, categoria in casos.items():
        tipo = _by_prefix(prefix)["tipoDespesa"]
        assert senado_expenses.portal_category_for(tipo) == categoria, tipo


def test_tipo_desconhecido_nao_tem_categoria_nem_url():
    assert senado_expenses.portal_category_for("Despesa inventada") is None
    assert senado_expenses.portal_category_for(None) is None
    assert senado_expenses.detail_url(475, "Despesa inventada", 2025, 1) is None


def test_detail_url_deterministica():
    tipo = _by_prefix("Aluguel")["tipoDespesa"]
    assert senado_expenses.detail_url(475, tipo, 2025, 1) == (
        "https://www6g.senado.leg.br/transparencia/sen/475/ceaps/1/detalhe/?mesAno=01/2025"
    )


def test_build_payload_item_completo():
    item = _by_prefix("Aluguel")
    payload = senado_expenses.build_payload(item)
    assert payload["house"] == "senado"
    assert payload["source_key"] == str(item["id"])
    assert payload["cod_senador"] == 475
    assert payload["year"] == 2025
    assert payload["month"] == 9
    # float da fonte passa por str antes de virar Decimal, sem expansao binaria
    assert payload["net_value"] == Decimal("1387.75")
    assert payload["document_value"] is None
    assert payload["glosa_value"] is None
    assert payload["supplier_id"] == item["cpfCnpj"]
    assert payload["document_url"] == (
        "https://www6g.senado.leg.br/transparencia/sen/475/ceaps/1/detalhe/?mesAno=09/2025"
    )


def test_tipo_nulo_vira_nao_informado_sem_url():
    item = next(i for i in _items() if not i.get("tipoDespesa"))
    payload = senado_expenses.build_payload(item)
    assert payload is not None
    assert payload["expense_type"] == "Não informado"
    assert payload["document_url"] is None
