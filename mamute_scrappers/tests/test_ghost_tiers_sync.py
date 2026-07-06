"""Sync de nome + preço mensal dos tiers a partir do Ghost Admin API."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# mamute_scrappers.db.engine exige DATABASE_URL no import (lazy no sync_tiers).
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg2://test:test@localhost:5432/test_db"
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, rel: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


gts = _load(
    "test_ghost_tiers_sync_module",
    "mamute_scrappers/scripts/ghost_tiers_sync.py",
)


class _Resp:
    def __init__(self, data: Any) -> None:
        self._data = data

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._data


def test_generate_admin_token_roundtrip() -> None:
    # secret precisa ser hex (bytes.fromhex). 'ab'*32 = 32 bytes.
    secret = "ab" * 32
    token = gts.generate_admin_token(f"kid123:{secret}")
    decoded = jwt.decode(
        token, bytes.fromhex(secret), algorithms=["HS256"], audience="/admin/"
    )
    assert decoded["aud"] == "/admin/"
    assert jwt.get_unverified_header(token)["kid"] == "kid123"


def test_parse_ghost_tiers_free_and_paid() -> None:
    payload = {
        "tiers": [
            {
                "id": "t_free",
                "name": "Cidadão Comum",
                "slug": "free",
                "type": "free",
                "monthly_price": None,
            },
            {
                "id": "t_paid",
                "name": "Cidadão Mamute",
                "slug": "cidadao-mamute",
                "type": "paid",
                "monthly_price": 8900,
            },
        ]
    }
    parsed = {t["product_id"]: t for t in gts.parse_ghost_tiers(payload)}
    # gratuito casa por "free", não pelo id
    assert parsed["free"]["name"] == "Cidadão Comum"
    assert parsed["free"]["monthly_price"] == 0.0
    # pago casa pelo id do Ghost; centavos → reais
    assert parsed["t_paid"]["name"] == "Cidadão Mamute"
    assert parsed["t_paid"]["slug"] == "cidadao-mamute"
    assert parsed["t_paid"]["monthly_price"] == 89.0


def test_fetch_ghost_tiers_hits_admin_endpoint() -> None:
    captured: dict[str, Any] = {}

    def http_get(url: str, **kwargs: Any) -> _Resp:
        captured["url"] = url
        captured["headers"] = kwargs.get("headers")
        return _Resp({"tiers": [{"id": "x", "name": "X", "type": "paid", "monthly_price": 5000}]})

    out = gts.fetch_ghost_tiers("https://ghost.example/ghost/api/admin", "tok", http_get)
    assert captured["url"].endswith("/tiers/?include=monthly_price&limit=all")
    assert captured["headers"]["Authorization"] == "Ghost tok"
    assert out[0]["monthly_price"] == 50.0


def _tiers_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """create table tiers (
                id integer primary key, tier_name_debug text not null,
                product_id text not null, detalhes text not null,
                created_at datetime default current_timestamp,
                updated_at datetime default current_timestamp, deleted_at datetime)"""
        )
        conn.exec_driver_sql(
            "insert into tiers (id, tier_name_debug, product_id, detalhes) values "
            "(1, 'debug-free', 'free', :d1), (2, 'debug-mamute', 'ghost_paid_id', :d2)",
            {
                "d1": json.dumps({"qtd_termos": 1}),
                "d2": json.dumps({"qtd_termos": 10, "preco_mensal": 1.0}),
            },
        )
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_sync_tiers_updates_name_and_price() -> None:
    session = _tiers_session()
    ghost_tiers = [
        {
            "product_id": "free",
            "ghost_tier_id": "ghost_free_id",
            "slug": "free",
            "type": "free",
            "name": "Cidadão Comum",
            "monthly_price": 0.0,
        },
        {
            "product_id": "ghost_paid_id",
            "ghost_tier_id": "ghost_paid_id",
            "slug": "cidadao-mamute",
            "type": "paid",
            "name": "Cidadão Mamute",
            "monthly_price": 89.0,
        },
        {"product_id": "sem_match", "name": "Fantasma", "monthly_price": 10.0},
    ]
    updated = gts.sync_tiers(session, ghost_tiers)

    assert set(updated) == {"free", "ghost_paid_id"}  # 'sem_match' ignorado

    from mamute_scrappers.db.models.project import Tiers

    free = session.query(Tiers).filter_by(product_id="free").one()
    paid = session.query(Tiers).filter_by(product_id="ghost_paid_id").one()
    assert free.tier_name_debug == "Cidadão Comum"
    assert free.detalhes["preco_mensal"] == 0.0
    assert free.detalhes["qtd_termos"] == 1  # preserva outros campos
    assert paid.tier_name_debug == "Cidadão Mamute"
    assert paid.detalhes["preco_mensal"] == 89.0
    assert paid.detalhes["qtd_termos"] == 10
    assert paid.detalhes["ghost"]["slug"] == "cidadao-mamute"
    assert paid.detalhes["ghost"]["target_tier_id"] == "ghost_paid_id"
