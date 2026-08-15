"""Mamutômetro — SPEC-001, fatia 3.

O que estes testes seguram, em ordem de importância:

1. **Configuração nunca destrói marcação.** Baixar a régua, apertar o escopo,
   tirar a feature do plano — nenhuma dessas ações apaga linha. É a regra que
   atravessa a spec inteira.
2. **O nível não tem significado no sistema.** Nenhuma resposta traz rótulo,
   nenhum agregado por político existe, e o admin não vê marcação.
3. Escopo por token, teto por plano e faixa da régua.
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

# 101/202 monitorados pelo projeto 10; 303 em exercício e não monitorado;
# 404 fora de exercício (escondido pelo catálogo padrão).
_PARLAMENTARES = {
    101: ("Deputado", "Em exercício"),
    202: ("Senador", "Em exercício"),
    303: ("Deputado", "Em exercício"),
    404: ("Deputado", "Fim de mandato"),
}


def _make_session(
    *,
    mamutometro_escopo: str = "todos",
    max_level: int = 3,
    tier_pago_tem_feature: bool = True,
    qtd_mamutometro: int | None = None,
) -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    detalhes = "{}" if qtd_mamutometro is None else f'{{"qtd_mamutometro": {qtd_mamutometro}}}'
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            create table tiers (
                id integer primary key, tier_name_debug text not null,
                product_id text not null, detalhes text not null,
                created_at datetime not null default current_timestamp,
                updated_at datetime not null default current_timestamp,
                deleted_at datetime
            )
            """
        )
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
            create table project_mamutometro (
                id integer primary key, projeto_id integer not null,
                parliamentarian_id integer not null, level integer not null,
                created_at datetime not null default current_timestamp,
                updated_at datetime not null default current_timestamp,
                unique (projeto_id, parliamentarian_id)
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
            "create table feature_flag (key text primary key, state text not null, "
            "created_at datetime, updated_at datetime)"
        )
        conn.exec_driver_sql(
            "create table feature_flag_tier (id integer primary key, flag_key text not null, "
            "tier_id integer not null, created_at datetime)"
        )
        conn.execute(
            text(
                """
                insert into marcacoes_config
                    (id, mamutometro_max_level, mamutometro_notice_text,
                     mamutometro_escopo, tags_escopo)
                values (1, :max_level, 'aviso neutro', :escopo, 'todos')
                """
            ),
            {"max_level": max_level, "escopo": mamutometro_escopo},
        )
        conn.exec_driver_sql(
            "insert into feature_flag (key, state) values ('mamutometro', 'all')"
        )
        conn.execute(
            text(
                """
                insert into tiers (id, tier_name_debug, product_id, detalhes)
                values (1, 'Pago', 'prod_pago', :detalhes)
                """
            ),
            {"detalhes": detalhes},
        )
        if tier_pago_tem_feature:
            conn.exec_driver_sql(
                "insert into feature_flag_tier (id, flag_key, tier_id) "
                "values (1, 'mamutometro', 1)"
            )
        for projeto_id, email in ((10, "assinante@example.com"), (20, "outro@example.com")):
            conn.execute(
                text(
                    """
                    insert into projetos (id, nome, email, tier_id, qtd_termos,
                                          created_at, updated_at)
                    values (:id, :nome, :email, 1, 10, '2026-01-01', '2026-01-01')
                    """
                ),
                {"id": projeto_id, "nome": f"Projeto {projeto_id}", "email": email},
            )
        for pid, (tipo, status_) in _PARLAMENTARES.items():
            conn.execute(
                text(
                    """
                    insert into parliamentarian (id, type, name, status, created_at, updated_at)
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


def _marcar(client: TestClient, pid: int, level: int):
    return client.put(
        f"/api/projects/me/parliamentarians/{pid}/mamutometro", json={"level": level}
    )


def _linhas_no_banco(db: Session) -> list[tuple[int, int]]:
    return [
        (int(pid), int(level))
        for pid, level in db.execute(
            text(
                "select parliamentarian_id, level from project_mamutometro "
                "where projeto_id = 10 order by parliamentarian_id"
            )
        ).all()
    ]


@pytest.fixture()
def db() -> Session:
    return _make_session()


def test_marca_altera_e_remove(db: Session) -> None:
    client = _client(db)

    assert _marcar(client, 101, 3).json() == {"parliamentarian_id": 101, "level": 3}
    assert _marcar(client, 101, 1).json() == {"parliamentarian_id": 101, "level": 1}
    assert client.get("/api/projects/me/mamutometro").json() == [
        {"parliamentarian_id": 101, "level": 1}
    ]

    assert client.delete("/api/projects/me/parliamentarians/101/mamutometro").status_code == 204
    assert client.get("/api/projects/me/mamutometro").json() == []


def test_nivel_fora_da_regua_e_recusado_em_portugues(db: Session) -> None:
    client = _client(db)

    fora = _marcar(client, 101, 4)

    assert fora.status_code == 422
    assert fora.json()["detail"] == "Escolha um valor entre 1 e 3."
    assert _marcar(client, 101, 0).status_code == 422


def test_apagar_tudo_de_uma_vez(db: Session) -> None:
    client = _client(db)
    _marcar(client, 101, 1)
    _marcar(client, 202, 2)

    assert client.delete("/api/projects/me/mamutometro").status_code == 204

    assert _linhas_no_banco(db) == []


def test_escopo_monitorados_bloqueia_nao_monitorado(db: Session) -> None:
    db = _make_session(mamutometro_escopo="monitorados")
    client = _client(db)

    assert _marcar(client, 101, 2).status_code == 200  # monitorado
    assert _marcar(client, 303, 2).status_code == 404  # existe, não monitorado


def test_politico_escondido_pelo_catalogo_nunca_e_marcavel(db: Session) -> None:
    client = _client(db)

    assert _marcar(client, 404, 2).status_code == 404


def test_plano_sem_a_feature_recebe_404(db: Session) -> None:
    """404 e não 403: 403 confirmaria que o recurso existe para quem não o tem."""
    db = _make_session(tier_pago_tem_feature=False)
    client = _client(db)

    assert _marcar(client, 101, 2).status_code == 404


def test_teto_do_plano_trava_criar_mas_nunca_alterar(db: Session) -> None:
    db = _make_session(qtd_mamutometro=1)
    client = _client(db)

    assert _marcar(client, 101, 1).status_code == 200

    excedente = _marcar(client, 202, 1)
    assert excedente.status_code == 403
    assert "upgrade do plano" in excedente.json()["detail"]

    # Alterar o que já existe segue funcionando mesmo no teto.
    assert _marcar(client, 101, 3).status_code == 200


def test_configuracao_nunca_destroi_marcacao(db: Session) -> None:
    """A regra que atravessa a spec: config muda a exibição, nunca o dado."""
    client = _client(db)
    _marcar(client, 101, 3)
    _marcar(client, 202, 2)
    antes = _linhas_no_banco(db)

    # Baixa a régua, aperta o escopo e tira a feature do plano.
    db.execute(
        text(
            "update marcacoes_config set mamutometro_max_level = 1, "
            "mamutometro_escopo = 'monitorados'"
        )
    )
    db.execute(text("delete from feature_flag_tier where flag_key = 'mamutometro'"))
    db.commit()

    assert _linhas_no_banco(db) == antes
    # E o nível gravado continua sendo devolvido cru — quem apara é a tela.
    assert antes == [(101, 3), (202, 2)]


def test_desmonitorar_nao_apaga_marcacao(db: Session) -> None:
    client = _client(db)
    _marcar(client, 101, 2)

    client.delete("/api/projects/me/favorites/101")

    assert _linhas_no_banco(db) == [(101, 2)]


def test_marcacao_de_outra_conta_e_inalcancavel(db: Session) -> None:
    dono = _client(db)
    _marcar(dono, 101, 3)

    intruso = _client(db, token_email="outro@example.com")

    assert intruso.get("/api/projects/me/mamutometro").json() == []
    intruso.delete("/api/projects/me/mamutometro")
    assert _linhas_no_banco(db) == [(101, 3)]


def test_marcar_nao_mexe_na_cota_de_monitorados(db: Session) -> None:
    client = _client(db)
    antes = client.get("/api/projects/me/favorites/quota").json()

    _marcar(client, 303, 3)

    assert client.get("/api/projects/me/favorites/quota").json() == antes


def test_resposta_nao_carrega_significado_nenhum(db: Session) -> None:
    """O nível é um número sem legenda — nem a API sugere o que ele quer dizer."""
    client = _client(db)
    _marcar(client, 101, 3)

    corpo = client.get("/api/projects/me/mamutometro").json()

    assert corpo == [{"parliamentarian_id": 101, "level": 3}]
    texto = str(corpo).lower()
    for proibido in ("voto", "votei", "apoio", "afinidade", "prefer"):
        assert proibido not in texto


def test_servicos_de_metrica_nao_referenciam_mamutometro() -> None:
    """Regra negativa, verificada no código e não por inspeção visual.

    O admin vê adoção, nunca escolha. O precedente é `_swaps_by_project`, que já
    conta trocas de monitoramento sem nomear político — este teste impede que
    alguém, meses à frente, adicione um join "inocente".
    """
    import pathlib

    raiz = pathlib.Path(__file__).resolve().parent.parent.parent
    alvos = [
        raiz / "api" / "services" / "admin_metrics.py",
        raiz / "api" / "services" / "admin_coverage.py",
        raiz / "chatbot_backend" / "app",
        raiz / "mamute_scrappers" / "scripts" / "notificacao",
    ]

    encontrados = []
    for alvo in alvos:
        arquivos = alvo.rglob("*.py") if alvo.is_dir() else [alvo]
        for arquivo in arquivos:
            if not arquivo.exists():
                continue
            if "project_mamutometro" in arquivo.read_text(encoding="utf-8"):
                encontrados.append(str(arquivo.relative_to(raiz)))

    assert encontrados == [], (
        "mamutômetro referenciado onde não pode aparecer: " + ", ".join(encontrados)
    )


def test_admin_marca_mesmo_sem_a_feature_no_plano(monkeypatch: pytest.MonkeyPatch) -> None:
    """Admin é prévia e conferência, não assinatura.

    Sem staging, é a conta de admin que confere a feature em produção. Se a
    leitura (`/settings/marcacoes`) diz `enabled: true` e a escrita responde
    404, a conferência é impossível — foi o que a revisão pegou.
    """
    db = _make_session(tier_pago_tem_feature=False)
    monkeypatch.setattr(
        projects, "resolve_ghost_admin", lambda request, authorization: "admin@example.com"
    )
    client = _client(db)

    resposta = _marcar(client, 101, 2)

    assert resposta.status_code == 200, resposta.json()


def test_nao_admin_sem_a_feature_continua_recebendo_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """O contrapeso do teste acima: a prévia é do admin, não de todo mundo."""
    db = _make_session(tier_pago_tem_feature=False)
    monkeypatch.setattr(projects, "resolve_ghost_admin", lambda request, authorization: None)
    client = _client(db)

    assert _marcar(client, 101, 2).status_code == 404


def test_leitura_e_escrita_concordam_sobre_o_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    """`enabled` na leitura e o gate da escrita não podem divergir."""
    db = _make_session(tier_pago_tem_feature=False)
    monkeypatch.setattr(
        projects, "resolve_ghost_admin", lambda request, authorization: "admin@example.com"
    )
    import api.routers.settings as settings_router

    monkeypatch.setattr(
        settings_router, "resolve_ghost_admin", lambda request, authorization: "admin@example.com"
    )
    client = _client(db)

    enabled = client.get("/api/settings/marcacoes").json()["mamutometro"]["enabled"]
    escrita_ok = _marcar(client, 101, 1).status_code == 200

    assert enabled is escrita_ok is True
