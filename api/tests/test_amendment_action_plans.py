"""Planos de acao das emendas Pix: agregado na listagem e rota de detalhe.

SQLite in-memory com DDL cru e get_db sobrescrito — mesmo padrao de
test_amendments.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from api import main
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
        # Uma Pix com 3 planos (2 prestando contas) e uma de Finalidade
        # Definida, que nunca tem plano de acao.
        conn.exec_driver_sql(
            """
            insert into parliamentary_amendment
                (amendment_code, year, amendment_number, amendment_type,
                 author_name_raw, parliamentarian_id, match_status,
                 spending_locality, function, committed_value, paid_value)
            values
                ('202444660013', 2024, '0013',
                 'Emenda Individual - Transferências Especiais',
                 'RODOLFO NOGUEIRA', 1, 'matched',
                 'MATO GROSSO DO SUL (UF)', 'Educação', 1798000.00, 1798000.00),
                ('202444660014', 2024, '0014',
                 'Emenda Individual - Transferências com Finalidade Definida',
                 'RODOLFO NOGUEIRA', 1, 'matched',
                 'MÚLTIPLO', 'Saúde', 900000.00, 0.00)
            """
        )
        conn.exec_driver_sql(
            """
            insert into amendment_action_plan
                (id_plano_acao, codigo_plano_acao, amendment_code, ano,
                 situacao, beneficiario_nome, beneficiario_uf,
                 valor_investimento, prestacao_situacao, prestacao_tipo,
                 prestacao_valor_executado, prestacao_origem)
            values
                (1, '0903-000001', '202444660013', 2024, 'CIENTE',
                 'MUNICIPIO DE DOURADOS', 'MS', 500000.00,
                 'DISPONIBILIZADO', 'Final', 325098.88, 'novo'),
                (2, '0903-000002', '202444660013', 2024, 'CIENTE',
                 'MUNICIPIO DE TRES LAGOAS', 'MS', 400000.00,
                 'DISPONIBILIZADO', 'Parcial', 120000.00, 'novo'),
                (3, '0903-000003', '202444660013', 2024, 'CIENTE',
                 'MUNICIPIO DE CORUMBA', 'MS', 898000.00,
                 null, null, null, null)
            """
        )
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


@pytest.fixture()
def client() -> TestClient:
    session = _make_session()
    main.app.dependency_overrides[get_db] = lambda: session
    main.app.dependency_overrides[verify_token] = lambda: None
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()
    session.close()


def _emenda(resposta, code):
    return next(x for x in resposta.json() if x["amendment_code"] == code)


def test_agregado_conta_planos_e_prestacoes(client):
    r = client.get("/api/amendments/", params={"parliamentarian_id": 1})
    emenda = _emenda(r, "202444660013")
    assert emenda["planos_total"] == 3
    assert emenda["planos_com_prestacao"] == 2
    assert emenda["valor_executado_total"] == "445098.88"


def test_emenda_sem_plano_devolve_zeros_e_nao_null(client):
    """Finalidade Definida nunca tem plano de acao: zero, nao null."""
    r = client.get("/api/amendments/", params={"parliamentarian_id": 1})
    emenda = _emenda(r, "202444660014")
    assert emenda["planos_total"] == 0
    assert emenda["planos_com_prestacao"] == 0
    assert emenda["valor_executado_total"] == "0.00"


def test_agregado_nao_duplica_a_emenda_na_listagem(client):
    """O join com 3 planos nao pode multiplicar a linha da emenda."""
    r = client.get("/api/amendments/", params={"parliamentarian_id": 1})
    codes = [x["amendment_code"] for x in r.json()]
    assert sorted(codes) == ["202444660013", "202444660014"]


def test_rota_de_planos_lista_beneficiarios(client):
    r = client.get("/api/amendments/202444660013/action-plans")
    assert r.status_code == 200
    nomes = [p["beneficiario_nome"] for p in r.json()]
    assert "MUNICIPIO DE DOURADOS" in nomes
    assert len(nomes) == 3


def test_rota_de_planos_serializa_dinheiro_como_string(client):
    r = client.get("/api/amendments/202444660013/action-plans")
    plano = next(p for p in r.json() if p["id_plano_acao"] == 1)
    assert plano["prestacao_valor_executado"] == "325098.88"
    assert plano["valor_investimento"] == "500000.00"


def test_rota_de_planos_devolve_vazio_e_nao_404(client):
    """Emenda de Finalidade Definida: ausencia de plano e o caso normal."""
    r = client.get("/api/amendments/202444660014/action-plans")
    assert r.status_code == 200
    assert r.json() == []


def test_rota_de_planos_expoe_o_ano_para_o_front_julgar_o_prazo(client):
    """Sem o ano do plano, a tela nao distingue prazo aberto de omissao."""
    r = client.get("/api/amendments/202444660013/action-plans")
    assert all(p["ano"] == 2024 for p in r.json())
