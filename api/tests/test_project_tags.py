"""Tags livres do assinante — SPEC-001, fatia 2.

Cobre o que a spec promete: tag é do dono e ninguém alcança a de outro, o slug
normaliza duplicata óbvia, os tetos são de higiene (com mensagem em português,
não 422 cru), tag em político não monitorado é permitida, político que o
catálogo esconde não é alcançável, e — o mais importante para o negócio —
etiquetar **não** mexe na cota do plano.
"""

from __future__ import annotations

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from api import main
from api.dependencies import get_db
from api.routers import projects


# 101/202 monitorados pelo projeto 10; 303 existe e está em exercício mas não é
# monitorado; 404 está fora de exercício (escondido pelo catálogo padrão).
_PARLAMENTARES = {
    101: ("Deputado", "Em exercício"),
    202: ("Senador", "Em exercício"),
    303: ("Deputado", "Em exercício"),
    404: ("Deputado", "Fim de mandato"),
}


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            create table projetos (
                id integer primary key, nome text not null, cliente text,
                email text not null, tier_id integer, tag_ghost text,
                qtd_termos integer not null default 0,
                created_at datetime not null default current_timestamp,
                updated_at datetime not null default current_timestamp,
                deleted_at datetime
            )
            """
        )
        conn.exec_driver_sql(
            """
            create table parliamentarian (
                id integer primary key, type text, parliamentarian_code integer,
                name text, full_name text, status text, party text,
                state_elected text, details text,
                created_at datetime not null, updated_at datetime not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            create table projetos_parliamentarian (
                id integer primary key, projeto_id integer not null,
                parliamentarian_id integer not null, position integer,
                created_at datetime not null default current_timestamp,
                updated_at datetime not null default current_timestamp,
                deleted_at datetime,
                unique (projeto_id, parliamentarian_id)
            )
            """
        )
        conn.exec_driver_sql(
            """
            create table project_tag (
                id integer primary key, projeto_id integer not null,
                name text not null, slug text not null,
                created_at datetime not null default current_timestamp,
                updated_at datetime not null default current_timestamp,
                unique (projeto_id, slug)
            )
            """
        )
        conn.exec_driver_sql(
            """
            create table marcacoes_config (
                id integer primary key,
                mamutometro_max_level integer not null default 3,
                mamutometro_notice_text text not null,
                mamutometro_escopo text not null default 'monitorados',
                tags_escopo text not null default 'todos',
                updated_at datetime not null default current_timestamp
            )
            """
        )
        conn.exec_driver_sql(
            """
            insert into marcacoes_config
                (id, mamutometro_max_level, mamutometro_notice_text,
                 mamutometro_escopo, tags_escopo)
            values (1, 3, 'aviso', 'monitorados', 'todos')
            """
        )
        conn.exec_driver_sql(
            """
            create table parliamentarian_tag (
                id integer primary key, projeto_id integer not null,
                tag_id integer not null, parliamentarian_id integer not null,
                created_at datetime not null default current_timestamp,
                unique (tag_id, parliamentarian_id)
            )
            """
        )
        for projeto_id, email in ((10, "assinante@example.com"), (20, "outro@example.com")):
            conn.execute(
                text(
                    """
                    insert into projetos (id, nome, email, qtd_termos, created_at, updated_at)
                    values (:id, :nome, :email, 10, '2026-01-01', '2026-01-01')
                    """
                ),
                {"id": projeto_id, "nome": f"Projeto {projeto_id}", "email": email},
            )
        for pid, (tipo, status_) in _PARLAMENTARES.items():
            conn.execute(
                text(
                    """
                    insert into parliamentarian
                        (id, type, name, status, created_at, updated_at)
                    values (:id, :type, :name, :status, '2026-01-01', '2026-01-01')
                    """
                ),
                {"id": pid, "type": tipo, "name": f"Parlamentar {pid}", "status": status_},
            )
        for row_id, pid in enumerate((101, 202), start=1):
            conn.execute(
                text(
                    """
                    insert into projetos_parliamentarian
                        (id, projeto_id, parliamentarian_id, created_at, updated_at)
                    values (:id, 10, :pid, '2026-01-01', '2026-01-01')
                    """
                ),
                {"id": row_id, "pid": pid},
            )
    return Session(engine)


def _client(db: Session, *, token_email: str = "assinante@example.com") -> TestClient:
    app = main.create_app()

    def fake_verify_token(request: Request) -> dict[str, str]:
        request.state.token_email = token_email
        return {"sub": token_email}

    def fake_get_db():
        yield db

    app.dependency_overrides[main.verify_token] = fake_verify_token
    app.dependency_overrides[get_db] = fake_get_db
    app.dependency_overrides[projects.get_db] = fake_get_db
    return TestClient(app)


@pytest.fixture()
def db() -> Session:
    return _make_session()


def _criar_tag(client: TestClient, nome: str):
    return client.post("/api/projects/me/tags", json={"name": nome})


def test_cria_lista_e_conta_tags(db: Session) -> None:
    client = _client(db)

    resposta = _criar_tag(client, "Meio Ambiente")
    assert resposta.status_code == 201
    tag = resposta.json()
    assert tag["name"] == "Meio Ambiente"
    assert tag["slug"] == "meio ambiente"
    assert tag["parliamentarian_count"] == 0

    client.put(
        f"/api/projects/me/parliamentarians/101/tags",
        json={"tag_ids": [tag["id"]]},
    )

    listagem = client.get("/api/projects/me/tags").json()
    assert [t["name"] for t in listagem] == ["Meio Ambiente"]
    assert listagem[0]["parliamentarian_count"] == 1


def test_slug_ignora_acento_caixa_e_espaco_repetido(db: Session) -> None:
    client = _client(db)
    assert _criar_tag(client, "Transparência").status_code == 201

    duplicada = _criar_tag(client, "  transparencia  ")

    assert duplicada.status_code == 409
    assert "já tem a tag" in duplicada.json()["detail"]


def test_nome_vazio_e_longo_demais_falam_portugues(db: Session) -> None:
    client = _client(db)

    vazio = _criar_tag(client, "   ")
    assert vazio.status_code == 422
    assert vazio.json()["detail"] == "Dê um nome para a tag."

    longo = _criar_tag(client, "a" * 31)
    assert longo.status_code == 422
    assert "no máximo 30 caracteres" in longo.json()["detail"]


def test_teto_de_tags_por_projeto(db: Session) -> None:
    client = _client(db)
    for i in range(50):
        assert _criar_tag(client, f"tag {i}").status_code == 201

    excedente = _criar_tag(client, "tag 51")

    assert excedente.status_code == 422
    assert "Renomeie ou apague uma" in excedente.json()["detail"]


def test_teto_de_tags_por_parlamentar(db: Session) -> None:
    client = _client(db)
    ids = [_criar_tag(client, f"tag {i}").json()["id"] for i in range(11)]

    resposta = client.put(
        "/api/projects/me/parliamentarians/101/tags", json={"tag_ids": ids}
    )

    assert resposta.status_code == 422
    assert "no máximo 10 tags" in resposta.json()["detail"]


def test_aplicar_tags_e_idempotente_e_substitui_o_conjunto(db: Session) -> None:
    client = _client(db)
    a = _criar_tag(client, "A").json()["id"]
    b = _criar_tag(client, "B").json()["id"]

    primeira = client.put(
        "/api/projects/me/parliamentarians/101/tags", json={"tag_ids": [a, b]}
    )
    assert primeira.status_code == 200
    assert sorted(primeira.json()["tag_ids"]) == sorted([a, b])

    # Mesma chamada de novo não duplica.
    repetida = client.put(
        "/api/projects/me/parliamentarians/101/tags", json={"tag_ids": [a, b]}
    )
    assert sorted(repetida.json()["tag_ids"]) == sorted([a, b])

    # Enviar só uma remove a outra.
    reduzida = client.put(
        "/api/projects/me/parliamentarians/101/tags", json={"tag_ids": [a]}
    )
    assert reduzida.json()["tag_ids"] == [a]

    mapa = client.get("/api/projects/me/parliamentarian-tags").json()
    assert mapa == [{"parliamentarian_id": 101, "tag_ids": [a]}]


def test_tag_em_politico_nao_monitorado_e_permitida(db: Session) -> None:
    """303 existe e está em exercício, mas não é monitorado pelo projeto."""
    client = _client(db)
    tag = _criar_tag(client, "de olho").json()["id"]

    resposta = client.put(
        "/api/projects/me/parliamentarians/303/tags", json={"tag_ids": [tag]}
    )

    assert resposta.status_code == 200


def test_politico_escondido_pelo_catalogo_nao_e_alcancavel(db: Session) -> None:
    """404 e não 403: responder diferente viraria oráculo de existência."""
    client = _client(db)
    tag = _criar_tag(client, "qualquer").json()["id"]

    resposta = client.put(
        "/api/projects/me/parliamentarians/404/tags", json={"tag_ids": [tag]}
    )

    assert resposta.status_code == 404
    assert resposta.json()["detail"] == "Parlamentar não encontrado."


def test_etiquetar_nao_mexe_na_cota_do_plano(db: Session) -> None:
    """O plano vende monitoramento, não organização (regra 3 da spec)."""
    client = _client(db)
    antes = client.get("/api/projects/me/favorites/quota").json()

    tag = _criar_tag(client, "tema").json()["id"]
    client.put("/api/projects/me/parliamentarians/303/tags", json={"tag_ids": [tag]})

    depois = client.get("/api/projects/me/favorites/quota").json()
    assert antes == depois
    assert len(client.get("/api/projects/me/favorites").json()) == 2


def test_tag_de_outra_conta_e_invisivel_em_toda_operacao(db: Session) -> None:
    dono = _client(db)
    tag_id = _criar_tag(dono, "minha").json()["id"]

    intruso = _client(db, token_email="outro@example.com")

    assert intruso.get("/api/projects/me/tags").json() == []
    assert intruso.patch(f"/api/projects/me/tags/{tag_id}", json={"name": "roubada"}).status_code == 404
    assert intruso.delete(f"/api/projects/me/tags/{tag_id}").status_code == 404
    aplicar = intruso.put(
        "/api/projects/me/parliamentarians/101/tags", json={"tag_ids": [tag_id]}
    )
    assert aplicar.status_code == 404

    # E a tag do dono segue intacta.
    assert [t["name"] for t in dono.get("/api/projects/me/tags").json()] == ["minha"]


def test_renomear_respeita_colisao_de_slug(db: Session) -> None:
    client = _client(db)
    _criar_tag(client, "Economia")
    outra = _criar_tag(client, "Saúde").json()["id"]

    colisao = client.patch(f"/api/projects/me/tags/{outra}", json={"name": "economia"})

    assert colisao.status_code == 409


def test_apagar_tag_tira_a_etiqueta_e_nao_toca_no_monitoramento(db: Session) -> None:
    client = _client(db)
    tag = _criar_tag(client, "temporaria").json()["id"]
    client.put("/api/projects/me/parliamentarians/101/tags", json={"tag_ids": [tag]})

    assert client.delete(f"/api/projects/me/tags/{tag}").status_code == 204

    assert client.get("/api/projects/me/tags").json() == []
    assert client.get("/api/projects/me/parliamentarian-tags").json() == []
    assert len(client.get("/api/projects/me/favorites").json()) == 2
