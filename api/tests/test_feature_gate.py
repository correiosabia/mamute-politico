"""Gate de plano nas rotas de dado (CS-58).

O desfoque no front e vitrine; a fronteira e a dependency de
`api/feature_gate.py`. Aqui ela e testada como funcao pura (com
`resolve_ghost_admin` monkeypatchado) e depois no comportamento das rotas
gatadas (truncagem da previa, filtros ignorados, 403 do agregado).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from api import feature_gate
from api.feature_gate import PREVIEW_ROWS, FeatureAccess, feature_access
from api.tests.test_feature_flags import _session_com_flags


def _request(email: str | None = "u@x.com") -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(token_email=email))


def _db_com_plano(modo: str | None):
    db = _session_com_flags([("emendas", "all")])
    db.execute(
        text(
            "insert into tiers (id, tier_name_debug, product_id)"
            " values (1, 't', 'p1')"
        )
    )
    db.execute(
        text(
            "insert into projetos (id, nome, email, tier_id)"
            " values (1, 'p', 'u@x.com', 1)"
        )
    )
    if modo is not None:
        db.execute(
            text(
                "insert into feature_flag_tier (flag_key, tier_id, mode)"
                " values ('emendas', 1, :m)"
            ),
            {"m": modo},
        )
    db.commit()
    return db


def _resolver(db, *, admin=False, preview=None, monkeypatch=None):
    """Chama a dependency como funcao pura, simulando o admin por patch."""
    monkeypatch.setattr(
        feature_gate,
        "resolve_ghost_admin",
        (lambda *a, **k: "adm@x.com") if admin else (lambda *a, **k: None),
    )
    dep = feature_access("emendas")
    return dep(
        request=_request(),
        authorization=None,
        x_feature_preview=preview,
        db=db,
    )


def test_plano_liberado_da_acesso_pleno(monkeypatch):
    acesso = _resolver(_db_com_plano("liberado"), monkeypatch=monkeypatch)
    assert acesso == FeatureAccess(full=True)


def test_plano_cadeado_da_previa(monkeypatch):
    acesso = _resolver(_db_com_plano("cadeado"), monkeypatch=monkeypatch)
    assert acesso == FeatureAccess(full=False)


def test_sem_linha_no_plano_e_403(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        _resolver(_db_com_plano(None), monkeypatch=monkeypatch)
    assert exc.value.status_code == 403


def test_flag_off_e_403_mesmo_com_linha(monkeypatch):
    db = _db_com_plano("liberado")
    db.execute(text("update feature_flag set state = 'off'"))
    db.commit()
    with pytest.raises(HTTPException) as exc:
        _resolver(db, monkeypatch=monkeypatch)
    assert exc.value.status_code == 403


def test_admin_e_sempre_pleno(monkeypatch):
    acesso = _resolver(
        _db_com_plano(None), admin=True, monkeypatch=monkeypatch
    )
    assert acesso == FeatureAccess(full=True)


def test_admin_com_header_preview_ve_a_previa(monkeypatch):
    """A lente de inspecao do painel: simulacao de ponta a ponta."""
    acesso = _resolver(
        _db_com_plano(None),
        admin=True,
        preview="emendas, trajetoria",
        monkeypatch=monkeypatch,
    )
    assert acesso == FeatureAccess(full=False)


def test_header_preview_sem_admin_e_ignorado(monkeypatch):
    """Usuario comum nao ganha (nem perde) nada forjando o header."""
    acesso = _resolver(
        _db_com_plano("liberado"), preview="emendas", monkeypatch=monkeypatch
    )
    assert acesso == FeatureAccess(full=True)


# --- comportamento das rotas gatadas em modo previa -------------------------

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text as sql_text  # noqa: E402

from api import main  # noqa: E402
from api.dependencies import get_db  # noqa: E402
from api.security import verify_token  # noqa: E402
from api.feature_gate import emendas_access, trajetoria_access  # noqa: E402
from api.tests.test_amendments import _make_session as _emendas_session  # noqa: E402
from api.tests.test_electoral_history import (  # noqa: E402
    _make_session as _trajetoria_session,
)


def _client_previa(session, gate) -> TestClient:
    main.app.dependency_overrides[get_db] = lambda: session
    main.app.dependency_overrides[verify_token] = lambda: None
    main.app.dependency_overrides[gate] = lambda: FeatureAccess(full=False)
    return TestClient(main.app)


def test_lista_de_emendas_em_previa_trunca_e_ignora_paginacao():
    session = _emendas_session()
    # Mais emendas que PREVIEW_ROWS para provar o corte no servidor.
    session.execute(
        sql_text(
            "insert into parliamentary_amendment"
            " (amendment_code, year, parliamentarian_id, match_status,"
            "  committed_value, paid_value)"
            " values ('202600010005', 2026, 1, 'matched', 50.0, 0.0),"
            "        ('202600010006', 2026, 1, 'matched', 40.0, 0.0)"
        )
    )
    session.commit()
    try:
        client = _client_previa(session, emendas_access)
        r = client.get(
            "/api/amendments/?parliamentarian_id=1&limit=200&offset=2&sort_by=year"
        )
        assert r.status_code == 200
        corpo = r.json()
        assert len(corpo) == PREVIEW_ROWS
        # Paginacao e ordenacao do cliente sao ignoradas: resposta identica.
        r2 = client.get("/api/amendments/?parliamentarian_id=1")
        assert corpo == r2.json()
    finally:
        main.app.dependency_overrides.clear()
        session.close()


def test_summary_em_previa_e_403():
    session = _emendas_session()
    try:
        client = _client_previa(session, emendas_access)
        r = client.get("/api/amendments/summary?parliamentarian_id=1")
        assert r.status_code == 403
    finally:
        main.app.dependency_overrides.clear()
        session.close()


def test_planos_de_acao_em_previa_truncam():
    session = _emendas_session()
    session.execute(
        sql_text(
            "insert into amendment_action_plan"
            " (id_plano_acao, amendment_code, beneficiario_uf)"
            " values (1, '202600010001', 'AC'), (2, '202600010001', 'BA'),"
            "        (3, '202600010001', 'CE'), (4, '202600010001', 'DF'),"
            "        (5, '202600010001', 'ES')"
        )
    )
    session.commit()
    try:
        client = _client_previa(session, emendas_access)
        r = client.get("/api/amendments/202600010001/action-plans")
        assert r.status_code == 200
        assert len(r.json()) == PREVIEW_ROWS
    finally:
        main.app.dependency_overrides.clear()
        session.close()


def test_trajetoria_em_previa_trunca_e_nunca_inclui_bens():
    session = _trajetoria_session()
    try:
        client = _client_previa(session, trajetoria_access)
        r = client.get(
            "/api/parliamentarians/1/electoral-history?include_assets=true"
        )
        assert r.status_code == 200
        entries = r.json()["entries"]
        assert len(entries) <= PREVIEW_ROWS
        # Mesmo pedindo os bens, a previa nao os entrega.
        assert all(e.get("assets") is None for e in entries)
    finally:
        main.app.dependency_overrides.clear()
        session.close()
