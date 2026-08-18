"""Rotas de emendas parlamentares: lista e resumo anual.

SQLite in-memory com DDL cru e get_db sobrescrito — mesmo padrão de
test_word_cloud_terms.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from api import main
from api.feature_gate import FeatureAccess, emendas_access
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
            create table parliamentary_amendment (
                id integer primary key,
                amendment_code text not null unique,
                year integer,
                amendment_number text,
                amendment_type text,
                author_name_raw text,
                author_raw text,
                parliamentarian_id integer,
                match_status text not null,
                spending_locality text,
                function text,
                subfunction text,
                committed_value numeric(18,2),
                settled_value numeric(18,2),
                paid_value numeric(18,2),
                remainder_inscribed numeric(18,2),
                remainder_cancelled numeric(18,2),
                remainder_paid numeric(18,2),
                created_at datetime not null default current_timestamp,
                updated_at datetime not null default current_timestamp
            )
            """
        )
        # A listagem agrega os planos de acao (CS-56); sem a tabela, o join
        # da rota quebra mesmo em cenario que nao usa plano nenhum.
        conn.exec_driver_sql(
            """
            create table amendment_action_plan (
                id_plano_acao integer primary key,
                codigo_plano_acao text,
                amendment_code text,
                ano integer,
                situacao text,
                beneficiario_nome text,
                beneficiario_cnpj text,
                beneficiario_uf text,
                valor_custeio numeric(18,2),
                valor_investimento numeric(18,2),
                prestacao_situacao text,
                prestacao_tipo text,
                prestacao_valor_executado numeric(18,2),
                prestacao_valor_pendente numeric(18,2),
                prestacao_data text,
                prestacao_origem text,
                created_at datetime not null default current_timestamp,
                updated_at datetime not null default current_timestamp
            )
            """
        )
        # Localidades reais da fonte: granularidade de UF ou "Nacional".
        conn.exec_driver_sql(
            """
            insert into parliamentary_amendment
                (amendment_code, year, amendment_number, amendment_type,
                 author_name_raw, parliamentarian_id, match_status,
                 spending_locality, function, committed_value, paid_value)
            values
                ('202600010001', 2026, '0001', 'Emenda Individual',
                 'HEITOR SCHUCH', 1, 'matched',
                 'RIO GRANDE DO SUL (UF)', 'Saúde', 2000000.00, 500000.00),
                ('202600010002', 2026, '0002', 'Emenda Individual',
                 'HEITOR SCHUCH', 1, 'matched',
                 'Nacional', 'Educação', 1500000.00, 0.00),
                ('202500010003', 2025, '0003', 'Emenda Individual',
                 'HEITOR SCHUCH', 1, 'matched',
                 'Nacional', 'Saúde', 900000.00, 900000.00),
                ('202600010004', 2026, '0004', 'Emenda Individual',
                 'FATIMA PELAES', null, 'unmatched',
                 'Nacional', 'Saúde', 100.00, 0.00)
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
    main.app.dependency_overrides[emendas_access] = lambda: FeatureAccess(full=True)
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def test_lista_filtra_por_parlamentar(client):
    resp = client.get("/api/amendments/", params={"parliamentarian_id": 1})
    assert resp.status_code == 200
    assert len(resp.json()) == 3


def test_lista_filtra_por_parlamentar_e_ano(client):
    resp = client.get(
        "/api/amendments/", params={"parliamentarian_id": 1, "year": 2026}
    )
    assert resp.status_code == 200
    codes = {item["amendment_code"] for item in resp.json()}
    assert codes == {"202600010001", "202600010002"}


def test_valores_trafegam_como_string(client):
    resp = client.get(
        "/api/amendments/", params={"parliamentarian_id": 1, "year": 2026}
    )
    item = next(i for i in resp.json() if i["amendment_code"] == "202600010001")
    assert item["committed_value"] == "2000000.00"
    assert item["paid_value"] == "500000.00"


def test_lista_respeita_limit_e_offset(client):
    todos = client.get("/api/amendments/", params={"parliamentarian_id": 1}).json()
    pagina = client.get(
        "/api/amendments/",
        params={"parliamentarian_id": 1, "limit": 1, "offset": 1},
    ).json()
    assert len(pagina) == 1
    assert pagina[0]["amendment_code"] == todos[1]["amendment_code"]


def test_lista_ordena_por_valor_empenhado_desc_por_padrao(client):
    itens = client.get("/api/amendments/", params={"parliamentarian_id": 1}).json()
    valores = [float(i["committed_value"]) for i in itens]
    assert valores == sorted(valores, reverse=True)


def test_resumo_soma_por_ano(client):
    resp = client.get(
        "/api/amendments/summary", params={"parliamentarian_id": 1, "year": 2026}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["year"] == 2026
    assert body["count"] == 2
    assert body["committed_total"] == "3500000.00"
    assert body["paid_total"] == "500000.00"


def test_resumo_sem_ano_soma_todos(client):
    body = client.get(
        "/api/amendments/summary", params={"parliamentarian_id": 1}
    ).json()
    assert body["count"] == 3
    assert body["committed_total"] == "4400000.00"


def test_resumo_sem_dado_devolve_zero_e_nao_404(client):
    resp = client.get(
        "/api/amendments/summary", params={"parliamentarian_id": 99, "year": 2026}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 0
    assert body["committed_total"] == "0.00"
    assert body["paid_total"] == "0.00"


def test_resumo_ignora_emendas_nao_casadas(client):
    # A emenda de FATIMA PELAES nao tem parliamentarian_id e nao pode entrar em
    # resumo nenhum de perfil.
    body = client.get(
        "/api/amendments/summary", params={"parliamentarian_id": 1, "year": 2026}
    ).json()
    assert body["count"] == 2


def test_emenda_nao_casada_nao_aparece_em_perfil_nenhum(client):
    itens = client.get("/api/amendments/", params={"parliamentarian_id": 1}).json()
    assert all(i["author_name_raw"] != "FATIMA PELAES" for i in itens)
