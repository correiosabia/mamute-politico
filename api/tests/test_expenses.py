"""Rotas de gastos da cota parlamentar (CS-57): lista e resumo mensal.

SQLite in-memory com DDL cru e get_db sobrescrito — mesmo padrão de
test_amendments.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from api import main
from api.feature_gate import FeatureAccess, cota_access
from api.dependencies import get_db
from api.security import verify_token


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            create table parliamentary_expense (
                id integer primary key,
                house text not null,
                source_key text not null,
                parliamentarian_id integer,
                year integer not null,
                month integer not null,
                expense_type text not null,
                supplier_name text,
                supplier_id text,
                document_number text,
                document_date date,
                details text,
                document_value numeric(18,2),
                glosa_value numeric(18,2),
                net_value numeric(18,2) not null,
                document_url text,
                created_at datetime not null default current_timestamp,
                updated_at datetime not null default current_timestamp,
                unique (house, source_key)
            )
            """
        )
        conn.exec_driver_sql(
            """
            insert into parliamentary_expense
                (house, source_key, parliamentarian_id, year, month,
                 expense_type, supplier_name, supplier_id, net_value,
                 document_url)
            values
                ('camara', '1:100:0', 1, 2026, 1,
                 'MANUTENÇÃO DE ESCRITÓRIO', 'ALARES', '11.111', 1000.00,
                 'https://camara.leg.br/doc/100.pdf'),
                ('camara', '1:101:0', 1, 2026, 1,
                 'MANUTENÇÃO DE ESCRITÓRIO', 'AMORETTO', '22.222', 500.00,
                 null),
                ('camara', '1:102:0', 1, 2026, 2,
                 'DIVULGAÇÃO DA ATIVIDADE PARLAMENTAR.', 'AGENCIA X', '33.333',
                 2000.00, null),
                ('camara', '998:103:0', 1, 2025, 12,
                 'PASSAGEM AÉREA - SIGEPA', 'AZUL', null, 750.25, null),
                ('camara', '1:104:0', 2, 2026, 1,
                 'MANUTENÇÃO DE ESCRITÓRIO', 'ALARES', '11.111', 999.00, null),
                ('camara', '1:105:0', null, 2026, 1,
                 'MANUTENÇÃO DE ESCRITÓRIO', 'LIDERANCA LTDA', '44.444',
                 123.00, null)
            """
        )
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


@pytest.fixture()
def session() -> Session:
    s = _make_session()
    yield s
    s.close()


@pytest.fixture()
def client(session: Session) -> TestClient:
    main.app.dependency_overrides[get_db] = lambda: session
    main.app.dependency_overrides[verify_token] = lambda: None
    main.app.dependency_overrides[cota_access] = lambda: FeatureAccess(full=True)
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


@pytest.fixture()
def client_bloqueado(session: Session) -> TestClient:
    main.app.dependency_overrides[get_db] = lambda: session
    main.app.dependency_overrides[verify_token] = lambda: None
    main.app.dependency_overrides[cota_access] = lambda: FeatureAccess(full=False)
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


# --- Lista -------------------------------------------------------------------


def test_lista_filtra_por_parlamentar_e_ano(client):
    resp = client.get(
        "/api/expenses/", params={"parliamentarian_id": 1, "year": 2026}
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 3


def test_lista_filtra_por_mes(client):
    resp = client.get(
        "/api/expenses/",
        params={"parliamentarian_id": 1, "year": 2026, "month": 2},
    )
    assert [i["source_key"] for i in resp.json()] == ["1:102:0"]


def test_valores_trafegam_como_string(client):
    resp = client.get(
        "/api/expenses/", params={"parliamentarian_id": 1, "year": 2025}
    )
    item = resp.json()[0]
    assert item["net_value"] == "750.25"
    assert item["document_value"] is None


def test_lista_ordena_por_valor_desc_por_padrao_com_desempate_estavel(client):
    itens = client.get(
        "/api/expenses/", params={"parliamentarian_id": 1, "year": 2026}
    ).json()
    valores = [float(i["net_value"]) for i in itens]
    assert valores == sorted(valores, reverse=True)

    pagina = client.get(
        "/api/expenses/",
        params={"parliamentarian_id": 1, "year": 2026, "limit": 1, "offset": 1},
    ).json()
    assert pagina[0]["source_key"] == itens[1]["source_key"]


def test_previa_corta_em_3_e_ignora_paginacao(client_bloqueado):
    resp = client_bloqueado.get(
        "/api/expenses/",
        params={"parliamentarian_id": 1, "limit": 200, "offset": 2},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 3  # PREVIEW_ROWS, offset ignorado


# --- Resumo ------------------------------------------------------------------


def test_resumo_agrega_mes_por_tipo(client):
    resp = client.get(
        "/api/expenses/summary", params={"parliamentarian_id": 1, "year": 2026}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["year"] == 2026
    assert body["count"] == 3
    assert body["total"] == "3500.00"
    mensal = {(m["month"], m["expense_type"]): m["total"] for m in body["monthly"]}
    assert mensal[(1, "MANUTENÇÃO DE ESCRITÓRIO")] == "1500.00"
    assert mensal[(2, "DIVULGAÇÃO DA ATIVIDADE PARLAMENTAR.")] == "2000.00"


def test_resumo_top_fornecedores_ordenado_por_total(client):
    body = client.get(
        "/api/expenses/summary", params={"parliamentarian_id": 1, "year": 2026}
    ).json()
    tops = body["top_suppliers"]
    assert tops[0]["supplier_name"] == "AGENCIA X"
    assert tops[0]["total"] == "2000.00"
    assert tops[0]["count"] == 1
    nomes = [t["supplier_name"] for t in tops]
    assert nomes == ["AGENCIA X", "ALARES", "AMORETTO"]


def test_resumo_nao_vaza_gastos_de_outros_nem_sem_vinculo(client):
    # O gasto do parlamentar 2 e o da lideranca (parliamentarian_id nulo) nao
    # podem entrar no resumo do parlamentar 1.
    body = client.get(
        "/api/expenses/summary", params={"parliamentarian_id": 1, "year": 2026}
    ).json()
    fornecedores = {t["supplier_name"] for t in body["top_suppliers"]}
    assert "LIDERANCA LTDA" not in fornecedores
    assert body["count"] == 3


def test_resumo_sem_dado_devolve_zero_e_nao_404(client):
    body = client.get(
        "/api/expenses/summary", params={"parliamentarian_id": 99, "year": 2026}
    ).json()
    assert body["count"] == 0
    assert body["total"] == "0.00"
    assert body["monthly"] == []
    assert body["top_suppliers"] == []


def test_resumo_bloqueado_devolve_403(client_bloqueado):
    resp = client_bloqueado.get(
        "/api/expenses/summary", params={"parliamentarian_id": 1, "year": 2026}
    )
    assert resp.status_code == 403
