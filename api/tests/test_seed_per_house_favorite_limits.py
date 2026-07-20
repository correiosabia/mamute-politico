"""Seed sem regressão: total global -> limite por casa (idempotente)."""
from __future__ import annotations

import json

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from scripts.seed_per_house_favorite_limits import seed_per_house_from_global


def _session(detalhes: dict) -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            create table tiers (
                id integer primary key, tier_name_debug text not null,
                product_id text not null, detalhes text not null,
                created_at datetime, updated_at datetime, deleted_at datetime
            )
            """
        )
        conn.exec_driver_sql(
            "insert into tiers (id, tier_name_debug, product_id, detalhes) "
            "values (1, 'Cidadão', 'cidadao-mamute', :d)",
            {"d": json.dumps(detalhes)},
        )
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_seed_copies_global_to_each_house() -> None:
    session = _session({"qtd_termos": 10})
    updated = seed_per_house_from_global(session)
    assert updated == ["cidadao-mamute"]
    detalhes = json.loads(
        session.execute(text("select detalhes from tiers where id=1")).scalar_one()
    )
    assert detalhes["qtd_termos_camara"] == 10
    assert detalhes["qtd_termos_senado"] == 10
    session.close()


def test_seed_is_idempotent() -> None:
    session = _session({"qtd_termos": 10})
    seed_per_house_from_global(session)
    assert seed_per_house_from_global(session) == []
    session.close()


def test_seed_does_not_overwrite_existing_per_house() -> None:
    session = _session({"qtd_termos": 10, "qtd_termos_camara": 4})
    seed_per_house_from_global(session)
    detalhes = json.loads(
        session.execute(text("select detalhes from tiers where id=1")).scalar_one()
    )
    # câmara já definido não é sobrescrito; senado é semeado do global
    assert detalhes["qtd_termos_camara"] == 4
    assert detalhes["qtd_termos_senado"] == 10
    session.close()


def test_seed_skips_tier_without_global_limit() -> None:
    session = _session({"qtd_consultas_ia_mes": 50})
    assert seed_per_house_from_global(session) == []
    session.close()
