"""Bootstrap idempotente env -> tiers.detalhes."""
from __future__ import annotations

import json

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from scripts.bootstrap_tiers_from_env import bootstrap_tiers_from_env

RAW = '{"cidadao-mamute": {"qtd_termos": 10, "qtd_consultas_ia_mes": 200}}'


def _session() -> Session:
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
            "values (1, 'Cidadão', 'cidadao-mamute', '{}')"
        )
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_bootstrap_fills_and_is_idempotent() -> None:
    session = _session()
    updated = bootstrap_tiers_from_env(session, RAW)
    assert updated == ["cidadao-mamute"]
    row = session.execute(text("select detalhes from tiers where id=1")).scalar_one()
    assert json.loads(row)["qtd_termos"] == 10
    assert json.loads(row)["qtd_consultas_ia_mes"] == 200

    # segunda rodada: sem mudanças
    updated2 = bootstrap_tiers_from_env(session, RAW)
    assert updated2 == []
    session.close()


def test_bootstrap_fills_per_house_keys() -> None:
    session = _session()
    raw = '{"cidadao-mamute": {"qtd_termos_camara": 6, "qtd_termos_senado": 4}}'
    updated = bootstrap_tiers_from_env(session, raw)
    assert updated == ["cidadao-mamute"]
    detalhes = json.loads(
        session.execute(text("select detalhes from tiers where id=1")).scalar_one()
    )
    assert detalhes["qtd_termos_camara"] == 6
    assert detalhes["qtd_termos_senado"] == 4
    session.close()
