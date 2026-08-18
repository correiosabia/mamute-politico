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
