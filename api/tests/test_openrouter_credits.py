"""Monitoramento de créditos do OpenRouter (CS-31).

Contexto: em 29/07/2026 os créditos zeraram no meio da carga de embeddings e o
chatbot inteiro saiu do ar — chat e embeddings respondendo 402. Não havia
nenhum sinal antes disso acontecer.

A separação chatbot x embeddings não vem da API: `/api/v1/activity` exige
management key, que a chave de inferência não é. Mas `chatbot_usage` já registra
o custo real de cada consulta, então o gasto de embeddings sai por diferença —
exato no agregado e cobrindo todo o histórico.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from api.services import openrouter_credits as oc


def _session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            create table chatbot_usage (
                id integer primary key,
                projeto_id integer not null,
                email text not null,
                request_id text not null unique,
                period_start date not null,
                status text not null,
                question_chars integer not null default 0,
                answer_chars integer not null default 0,
                model text,
                prompt_tokens integer,
                completion_tokens integer,
                cost_usd numeric,
                created_at datetime not null default current_timestamp,
                updated_at datetime not null default current_timestamp
            )
            """
        )
    return sessionmaker(bind=engine)()


def _gasto(db: Session, valor, status="completed", rid=None):
    db.execute(
        text(
            "insert into chatbot_usage (projeto_id,email,request_id,period_start,"
            "status,cost_usd) values (1,'a@b.com',:rid,'2026-07-01',:st,:c)"
        ),
        {"rid": rid or f"r{valor}{status}", "st": status, "c": valor},
    )
    db.commit()


class TestSeparacaoDeCustos:
    def test_embeddings_sai_por_diferenca(self) -> None:
        db = _session()
        _gasto(db, 3.0)
        _gasto(db, 1.5, rid="r2")

        r = oc.split_usage(db, total_usage=10.0)

        assert r["chatbot_usd"] == pytest.approx(4.5)
        assert r["embeddings_usd"] == pytest.approx(5.5)

    def test_sem_uso_de_chat_tudo_e_embeddings(self) -> None:
        r = oc.split_usage(_session(), total_usage=8.0)

        assert r["chatbot_usd"] == 0
        assert r["embeddings_usd"] == pytest.approx(8.0)

    def test_custo_nulo_nao_quebra_a_soma(self) -> None:
        db = _session()
        _gasto(db, None, rid="nulo")
        _gasto(db, 2.0, rid="ok")

        assert oc.split_usage(db, total_usage=5.0)["chatbot_usd"] == pytest.approx(2.0)

    def test_ignora_consultas_nao_concluidas(self) -> None:
        db = _session()
        _gasto(db, 2.0, status="completed", rid="ok")
        _gasto(db, 9.0, status="cancelled", rid="cancelada")

        assert oc.split_usage(db, total_usage=5.0)["chatbot_usd"] == pytest.approx(2.0)

    def test_diferenca_negativa_e_zerada(self) -> None:
        """Arredondamento do provedor não pode gerar embeddings negativo."""

        db = _session()
        _gasto(db, 7.0)

        assert oc.split_usage(db, total_usage=6.5)["embeddings_usd"] == 0


class TestStatusDeAlerta:
    @pytest.mark.parametrize(
        "disponivel,esperado",
        [(50.0, "ok"), (12.0, "ok"), (9.99, "atencao"), (5.01, "atencao"),
         (5.0, "critico"), (0.0, "critico"), (-1.0, "critico")],
    )
    def test_faixas(self, disponivel: float, esperado: str) -> None:
        assert oc.credit_status(disponivel, atencao=10.0, critico=5.0) == esperado

    def test_limiares_sao_configuraveis(self) -> None:
        assert oc.credit_status(30.0, atencao=50.0, critico=20.0) == "atencao"
        assert oc.credit_status(15.0, atencao=50.0, critico=20.0) == "critico"


class TestVisaoGeral:
    def test_monta_o_painel_completo(self, monkeypatch) -> None:
        db = _session()
        _gasto(db, 4.0)
        monkeypatch.setattr(
            oc, "fetch_credits", lambda: {"total_credits": 22.0, "total_usage": 10.0}
        )

        r = oc.credits_overview(db)

        assert r["disponivel_usd"] == pytest.approx(12.0)
        assert r["total_credits_usd"] == pytest.approx(22.0)
        assert r["chatbot_usd"] == pytest.approx(4.0)
        assert r["embeddings_usd"] == pytest.approx(6.0)
        assert r["status"] == "ok"
        assert r["disponivel"] is True

    def test_provedor_indisponivel_nao_derruba_o_painel(self, monkeypatch) -> None:
        """O painel de IA inteiro não pode cair porque o OpenRouter oscilou."""

        monkeypatch.setattr(oc, "fetch_credits", lambda: None)

        r = oc.credits_overview(_session())

        assert r["disponivel"] is False
        assert r["status"] == "desconhecido"
        assert r["total_credits_usd"] is None


class TestEndpoint:
    """Rota do painel — atrás do gate de administrador."""

    def _client(self, db, overview):
        from fastapi.testclient import TestClient
        from api import main
        from api.dependencies import get_db
        from api.security import require_ghost_admin
        from api.routers import admin as admin_router

        main.app.dependency_overrides[get_db] = lambda: db
        main.app.dependency_overrides[require_ghost_admin] = lambda: "admin@mamute.com"
        admin_router.credits_overview = lambda _db: overview
        return TestClient(main.app)

    def teardown_method(self):
        from api import main

        main.app.dependency_overrides.clear()

    def test_expoe_saldo_e_reparticao(self) -> None:
        payload = {
            "disponivel": True,
            "status": "atencao",
            "total_credits_usd": 22.0,
            "total_usage_usd": 12.0,
            "disponivel_usd": 10.0,
            "chatbot_usd": 4.0,
            "embeddings_usd": 8.0,
            "limiar_atencao_usd": 10.0,
            "limiar_critico_usd": 5.0,
        }
        r = self._client(_session(), payload).get("/api/admin/metrics/credits")

        assert r.status_code == 200
        assert r.json()["disponivel_usd"] == 10.0
        assert r.json()["status"] == "atencao"
        assert r.json()["embeddings_usd"] == 8.0

    def test_nao_existe_para_nao_admin(self) -> None:
        from fastapi import HTTPException
        from fastapi.testclient import TestClient
        from api import main
        from api.dependencies import get_db
        from api.security import require_ghost_admin

        def _nega():
            raise HTTPException(status_code=404, detail="Not Found")

        main.app.dependency_overrides[get_db] = lambda: _session()
        main.app.dependency_overrides[require_ghost_admin] = _nega
        assert TestClient(main.app).get("/api/admin/metrics/credits").status_code == 404
