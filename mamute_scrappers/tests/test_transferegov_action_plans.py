"""Precedencia do relatorio de gestao, payload e upsert dos planos de acao."""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import (
    BigInteger, Column, Integer, Numeric, Text, create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from mamute_scrappers.transferegov_crawler.action_plans import (
    build_plan_payload,
    escolher_relatorio,
    normalizar_relatorios,
)

Base = declarative_base()


class PlanoTeste(Base):
    """Espelho do modelo real, sem a FK — o teste nao carrega a base inteira."""

    __tablename__ = "amendment_action_plan"

    id_plano_acao = Column(BigInteger, primary_key=True)
    codigo_plano_acao = Column(Text)
    amendment_code = Column(Text)
    ano = Column(Integer)
    situacao = Column(Text)
    beneficiario_nome = Column(Text)
    beneficiario_cnpj = Column(Text)
    beneficiario_uf = Column(Text)
    valor_custeio = Column(Numeric(18, 2))
    valor_investimento = Column(Numeric(18, 2))
    prestacao_situacao = Column(Text)
    prestacao_tipo = Column(Text)
    prestacao_valor_executado = Column(Numeric(18, 2))
    prestacao_valor_pendente = Column(Numeric(18, 2))
    prestacao_data = Column(Text)
    prestacao_origem = Column(Text)


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _rel(origem="novo", tipo="Parcial", data="2024-01-01T00:00:00",
         situacao="DISPONIBILIZADO"):
    return {
        "origem": origem, "tipo": tipo, "data": data, "situacao": situacao,
        "valor_executado": Decimal("10.00"), "valor_pendente": Decimal("0.00"),
    }


# --- precedencia ------------------------------------------------------------


def test_sem_relatorio_devolve_none():
    assert escolher_relatorio([]) is None


def test_final_vence_parcial_mesmo_sendo_mais_antigo():
    escolhido = escolher_relatorio([
        _rel(tipo="Parcial", data="2025-01-01T00:00:00"),
        _rel(tipo="Final", data="2024-01-01T00:00:00"),
    ])
    assert escolhido["tipo"] == "Final"


def test_mesmo_tipo_vence_o_mais_recente():
    escolhido = escolher_relatorio([
        _rel(tipo="Parcial", data="2024-01-01T00:00:00"),
        _rel(tipo="Parcial", data="2025-06-01T00:00:00"),
    ])
    assert escolhido["data"] == "2025-06-01T00:00:00"


def test_novo_vence_legado_no_empate():
    escolhido = escolher_relatorio([
        _rel(origem="legado", tipo="Final", data=None),
        _rel(origem="novo", tipo="Final", data=None),
    ])
    assert escolhido["origem"] == "novo"


def test_legado_sem_tipo_nao_quebra():
    """O relatorio legado nao tem campo `tipo`; entra como None."""
    escolhido = escolher_relatorio([_rel(origem="legado", tipo=None, data=None)])
    assert escolhido["origem"] == "legado"


def test_normalizar_une_as_duas_tabelas_da_fonte():
    novos = [{
        "id_plano_acao": 1,
        "tipo_relatorio_gestao_novo": "Final",
        "situacao_relatorio_gestao_novo": "DISPONIBILIZADO",
        "valor_executado_relatorio_gestao_novo": 325098.88,
        "valor_pendente_relatorio_gestao_novo": 0.0,
        "data_e_hora_relatorio_gestao_novo": "2024-12-23T10:47:09",
    }]
    legados = [{"id_plano_acao": 2, "situacao_relatorio_gestao": "EM_ELABORACAO"}]

    idx = normalizar_relatorios(novos, legados)
    assert idx[1][0]["origem"] == "novo"
    assert idx[1][0]["valor_executado"] == Decimal("325098.88")
    assert idx[2][0]["origem"] == "legado"
    assert idx[2][0]["tipo"] is None


# --- payload ----------------------------------------------------------------


def test_payload_mapeia_os_campos_da_fonte():
    plano = {
        "id_plano_acao": 75199,
        "codigo_plano_acao": "09032024-075199",
        "numero_emenda_parlamentar_plano_acao": "202444660013",
        "ano_plano_acao": 2024,
        "situacao_plano_acao": "CIENTE",
        "nome_beneficiario_plano_acao": "ESTADO DE MATO GROSSO DO SUL",
        "cnpj_beneficiario_plano_acao": "15412257000128",
        "uf_beneficiario_plano_acao": "MS",
        "valor_custeio_plano_acao": 0.0,
        "valor_investimento_plano_acao": 1798000.0,
    }
    payload = build_plan_payload(plano, None)

    assert payload["amendment_code"] == "202444660013"
    assert payload["valor_investimento"] == Decimal("1798000.00")
    assert payload["prestacao_situacao"] is None
    assert payload["prestacao_origem"] is None


def test_payload_converte_valores_sem_passar_por_float():
    payload = build_plan_payload(
        {"id_plano_acao": 2, "valor_custeio_plano_acao": 0.1}, None
    )
    assert payload["valor_custeio"] == Decimal("0.10")


def test_payload_com_relatorio_preenche_a_prestacao():
    payload = build_plan_payload(
        {"id_plano_acao": 3}, _rel(tipo="Final", origem="novo")
    )
    assert payload["prestacao_tipo"] == "Final"
    assert payload["prestacao_origem"] == "novo"
    assert payload["prestacao_valor_executado"] == Decimal("10.00")


# --- upsert -----------------------------------------------------------------


def test_upsert_idempotente(session, monkeypatch):
    from mamute_scrappers.transferegov_crawler import action_plans

    monkeypatch.setattr(action_plans, "_modelo", lambda: PlanoTeste)

    payload = build_plan_payload({"id_plano_acao": 9, "ano_plano_acao": 2024}, None)
    _, criada = action_plans.upsert_plan(session, payload)
    assert criada is True
    _, criada = action_plans.upsert_plan(session, payload)
    assert criada is False
    assert session.query(PlanoTeste).count() == 1


def test_upsert_grava_a_prestacao_quando_ela_aparece(session, monkeypatch):
    from mamute_scrappers.transferegov_crawler import action_plans

    monkeypatch.setattr(action_plans, "_modelo", lambda: PlanoTeste)

    action_plans.upsert_plan(session, build_plan_payload({"id_plano_acao": 10}, None))
    action_plans.upsert_plan(
        session,
        build_plan_payload({"id_plano_acao": 10}, _rel(tipo="Final")),
    )
    session.flush()
    assert session.get(PlanoTeste, 10).prestacao_tipo == "Final"


def test_upsert_aceita_plano_de_emenda_desconhecida(session, monkeypatch):
    """A coleta do Portal pode estar atras: grava com FK nula em vez de perder."""
    from mamute_scrappers.transferegov_crawler import action_plans

    monkeypatch.setattr(action_plans, "_modelo", lambda: PlanoTeste)

    payload = build_plan_payload(
        {"id_plano_acao": 11, "numero_emenda_parlamentar_plano_acao": "999999999999"},
        None,
    )
    action_plans.upsert_plan(session, payload)
    session.flush()
    assert session.get(PlanoTeste, 11).amendment_code == "999999999999"


# --- schema real ------------------------------------------------------------


def test_schema_real_aceita_plano_de_emenda_que_nao_existe():
    """Regressao: a versao original tinha FK para parliamentary_amendment e a
    carga inteira morria com ForeignKeyViolation em producao.

    A fonte publica plano de acao desde 2020 e a nossa coleta de emendas
    comeca em 2022: 6.331 dos 57.827 planos (10,9%, medido em 2026-08-13)
    apontam para emenda que nunca vai existir aqui.

    O bug passou pelos outros testes porque eles usam `PlanoTeste`, um espelho
    local sem a FK. Este usa o MODELO REAL, com as FKs do SQLite ligadas — que
    e a unica forma de o teste enxergar a restricao.
    """
    from sqlalchemy import event

    from mamute_scrappers.db.models.amendment_action_plan import (
        AmendmentActionPlan,
    )

    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _liga_fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    AmendmentActionPlan.__table__.create(engine)
    sessao = sessionmaker(bind=engine)()

    sessao.add(
        AmendmentActionPlan(
            **build_plan_payload(
                {
                    "id_plano_acao": 3221,
                    "numero_emenda_parlamentar_plano_acao": "202027070006",
                    "ano_plano_acao": 2020,
                },
                None,
            )
        )
    )
    sessao.commit()

    assert (
        sessao.get(AmendmentActionPlan, 3221).amendment_code == "202027070006"
    )
