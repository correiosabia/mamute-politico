# Painéis Admin — Plano 2 (Gestão de Tiers) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Painel de gestão que edita a config de tiers no banco (`tiers.detalhes`) — limites por plano + `preco_mensal` — com auditoria, e inverter a precedência para o DB ganhar do `.env` (editar limite passa a valer sem redeploy).

**Architecture:** CRUD admin-gated sobre a tabela `tiers` em `api/routers/admin.py` (reusa o gate do Plano 1). Toda escrita loga em `admin_audit_log`. Dois resolvedores de limite passam a ler o DB **antes** do env: `api/routers/projects.py:_project_favorite_limit` (parlamentares) e `chatbot_backend/app/services/quota.py:resolve_monthly_limit` (consultas IA). Um script de bootstrap copia os valores de `MAMUTE_TIER_LIMITS_JSON` para `tiers.detalhes`, garantindo paridade de comportamento na virada.

**Tech Stack:** FastAPI + SQLAlchemy + Pydantic + Alembic (backend), React 18 + TanStack Query + shadcn/ui (front), pytest com SQLite in-memory (testes).

## Global Constraints

- **Precedência DB-ganha:** nos dois resolvedores, `tiers.detalhes` vence `MAMUTE_TIER_LIMITS_JSON`; env vira fallback. (spec §4, §5 Plano 2)
- **Paridade na virada:** o bootstrap (`scripts/bootstrap_tiers_from_env.py`) semeia `tiers.detalhes` com os mesmos valores do env **antes** de confiar no DB — o lado da api é comportamento de produção AO VIVO (quota do chatbot está OFF, então esse lado é seguro). (spec §8)
- **Models são duplicados por serviço:** adicionar `AdminAuditLog` em `api/db/models/` (usado pelo router). A migration vive na alembic compartilhada `mamute_scrappers/migrations/` (head atual: `a7f3c9e1b2d4`). (descoberta no código)
- **Auditoria `before`/`after` como `Text` (JSON string)** — evita acoplar a coluna ao dialeto JSONB e mantém os testes SQLite-compatíveis. (decisão de robustez)
- **`preco_mensal`** é uma chave dentro de `tiers.detalhes` (numérico ≥ 0), editável no painel. (spec §2)
- **Todas as rotas admin-gated** por `require_ghost_admin` (Plano 1) e escondidas com 404. (spec §4.1)

---

### Task 1: Model `AdminAuditLog` + migration

**Files:**
- Create: `api/db/models/admin_audit_log.py`
- Modify: `api/db/models/__init__.py`
- Create: `mamute_scrappers/migrations/versions/c1d2e3f4a5b6_add_admin_audit_log.py`
- Test: `api/tests/test_smoke.py` (já cobre import de models via app; adicionamos asserção de rota)

**Interfaces:**
- Produces: `AdminAuditLog` (colunas: `id`, `admin_email:str`, `action:str`, `entity:str`, `entity_id:str|None`, `before:str|None`, `after:str|None`, `created_at`).

- [ ] **Step 1: Criar o model**

Create `api/db/models/admin_audit_log.py`:

```python
"""Log de auditoria de ações administrativas (escritas de config)."""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, Text
from sqlalchemy.sql import func

from ..base import Base


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_log"

    id = Column(BigInteger, primary_key=True, index=True)
    admin_email = Column(Text, nullable=False)
    action = Column(Text, nullable=False)
    entity = Column(Text, nullable=False)
    entity_id = Column(Text, nullable=True)
    before = Column(Text, nullable=True)  # JSON serializado
    after = Column(Text, nullable=True)  # JSON serializado
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
```

- [ ] **Step 2: Registrar no `__init__` dos models da api**

Em `api/db/models/__init__.py`, adicione o import (em ordem alfabética, após `from .agency import Agency`):

```python
from .admin_audit_log import AdminAuditLog
```

E adicione `"AdminAuditLog",` no início da lista `__all__`.

- [ ] **Step 3: Criar a migration**

Create `mamute_scrappers/migrations/versions/c1d2e3f4a5b6_add_admin_audit_log.py`:

```python
"""add admin audit log table

Revision ID: c1d2e3f4a5b6
Revises: a7f3c9e1b2d4
Create Date: 2026-07-04 12:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "c1d2e3f4a5b6"
down_revision = "a7f3c9e1b2d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("admin_email", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Text(), nullable=True),
        sa.Column("before", sa.Text(), nullable=True),
        sa.Column("after", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(op.f("ix_admin_audit_log_id"), "admin_audit_log", ["id"], unique=False)
    op.create_index(
        "ix_admin_audit_log_entity", "admin_audit_log", ["entity", "entity_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_admin_audit_log_entity", table_name="admin_audit_log")
    op.drop_index(op.f("ix_admin_audit_log_id"), table_name="admin_audit_log")
    op.drop_table("admin_audit_log")
```

- [ ] **Step 4: Verificar import do model**

Run: `cd /Users/luiz/dev/correio-sabia/mamute-politico && python -c "from api.db.models import AdminAuditLog; print(AdminAuditLog.__tablename__)"`
Expected: `admin_audit_log`

- [ ] **Step 5: Commit**

```bash
git add api/db/models/admin_audit_log.py api/db/models/__init__.py mamute_scrappers/migrations/versions/c1d2e3f4a5b6_add_admin_audit_log.py
git commit -m "feat(admin): model e migration do admin_audit_log"
```

---

### Task 2: CRUD `GET/PUT /admin/tiers` + auditoria

**Files:**
- Modify: `api/routers/admin.py`
- Test: `api/tests/test_admin_tiers.py` (create)

**Interfaces:**
- Consumes: `require_ghost_admin` (Plano 1), `get_db`, `Tiers`, `AdminAuditLog`.
- Produces:
  - `GET /api/admin/tiers` → `list[TierOut]`
  - `PUT /api/admin/tiers/{tier_id}` → `TierOut`
  - `TierOut = {id:int, tier_name_debug:str, product_id:str, detalhes:dict, created_at, updated_at}`
  - `TierDetailsUpdate` (todos opcionais): `qtd_termos:int≥0`, `qtd_consultas_ia_mes:int≥0`, `qtd_email:int≥0`, `periodicidade_email:list[str]`, `orgao:list[str]`, `preco_mensal:float≥0`.

- [ ] **Step 1: Escrever os testes (falhando)**

Create `api/tests/test_admin_tiers.py`:

```python
"""CRUD admin de tiers + auditoria. SQLite in-memory, gate e get_db sobrescritos."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from api import main
from api.dependencies import get_db
from api.security import require_ghost_admin


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            create table tiers (
                id integer primary key,
                tier_name_debug text not null,
                product_id text not null,
                detalhes text not null,
                created_at datetime not null default current_timestamp,
                updated_at datetime not null default current_timestamp,
                deleted_at datetime
            )
            """
        )
        conn.exec_driver_sql(
            """
            create table admin_audit_log (
                id integer primary key,
                admin_email text not null,
                action text not null,
                entity text not null,
                entity_id text,
                before text,
                after text,
                created_at datetime not null default current_timestamp
            )
            """
        )
        conn.exec_driver_sql(
            "insert into tiers (id, tier_name_debug, product_id, detalhes) "
            "values (1, 'Cidadão', 'cidadao-mamute', :d)",
            {"d": json.dumps({"qtd_termos": 10, "qtd_consultas_ia_mes": 200})},
        )
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


@pytest.fixture()
def client() -> TestClient:
    session = _make_session()

    def _override_get_db():
        try:
            yield session
        finally:
            pass

    main.app.dependency_overrides[get_db] = _override_get_db
    main.app.dependency_overrides[require_ghost_admin] = lambda: "admin@x.com"
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()
    session.close()


def test_list_tiers(client: TestClient) -> None:
    resp = client.get("/api/admin/tiers")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["product_id"] == "cidadao-mamute"
    assert data[0]["detalhes"]["qtd_termos"] == 10


def test_update_tier_merges_and_audits(client: TestClient) -> None:
    resp = client.put(
        "/api/admin/tiers/1",
        json={"qtd_consultas_ia_mes": 500, "preco_mensal": 49.9},
    )
    assert resp.status_code == 200
    body = resp.json()
    # merge: mantém qtd_termos, atualiza a consulta e adiciona preço
    assert body["detalhes"]["qtd_termos"] == 10
    assert body["detalhes"]["qtd_consultas_ia_mes"] == 500
    assert body["detalhes"]["preco_mensal"] == 49.9

    # segunda chamada: confere persistência + auditoria
    again = client.get("/api/admin/tiers").json()
    assert again[0]["detalhes"]["qtd_consultas_ia_mes"] == 500


def test_update_rejects_negative(client: TestClient) -> None:
    resp = client.put("/api/admin/tiers/1", json={"qtd_termos": -3})
    assert resp.status_code == 422


def test_update_unknown_tier_404(client: TestClient) -> None:
    resp = client.put("/api/admin/tiers/999", json={"qtd_termos": 5})
    assert resp.status_code == 404
```

- [ ] **Step 2: Rodar (falha — rotas não existem)**

Run: `python -m pytest api/tests/test_admin_tiers.py -v`
Expected: FAIL (404 nas rotas de tiers / atributos ausentes).

- [ ] **Step 3: Implementar o CRUD em `api/routers/admin.py`**

Substitua o conteúdo de `api/routers/admin.py` por:

```python
"""Rotas administrativas — gated por require_ghost_admin (404 para não-admin)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

try:
    from ..security import require_ghost_admin
    from ..dependencies import get_db
    from ..db.models.project import Tiers
    from ..db.models.admin_audit_log import AdminAuditLog
except ImportError:  # execução dentro de api/
    from security import require_ghost_admin
    from dependencies import get_db
    from db.models.project import Tiers
    from db.models.admin_audit_log import AdminAuditLog

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/whoami")
def whoami(admin_email: str = Depends(require_ghost_admin)) -> dict:
    """Valida o gate ponta a ponta: só admin autenticado chega aqui."""
    return {"email": admin_email, "is_admin": True}


class TierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tier_name_debug: str
    product_id: str
    detalhes: dict[str, Any]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TierDetailsUpdate(BaseModel):
    qtd_termos: Optional[int] = Field(default=None, ge=0)
    qtd_consultas_ia_mes: Optional[int] = Field(default=None, ge=0)
    qtd_email: Optional[int] = Field(default=None, ge=0)
    periodicidade_email: Optional[list[str]] = None
    orgao: Optional[list[str]] = None
    preco_mensal: Optional[float] = Field(default=None, ge=0)


def _log_admin_action(
    db: Session,
    *,
    admin_email: str,
    action: str,
    entity: str,
    entity_id: str,
    before: Any,
    after: Any,
) -> None:
    db.add(
        AdminAuditLog(
            admin_email=admin_email,
            action=action,
            entity=entity,
            entity_id=entity_id,
            before=json.dumps(before, ensure_ascii=False),
            after=json.dumps(after, ensure_ascii=False),
        )
    )


@router.get("/tiers", response_model=list[TierOut])
def list_tiers(
    db: Session = Depends(get_db),
    _admin: str = Depends(require_ghost_admin),
) -> list[Tiers]:
    stmt = select(Tiers).where(Tiers.deleted_at.is_(None)).order_by(Tiers.id)
    return list(db.execute(stmt).scalars().all())


@router.put("/tiers/{tier_id}", response_model=TierOut)
def update_tier(
    tier_id: int,
    payload: TierDetailsUpdate,
    db: Session = Depends(get_db),
    admin_email: str = Depends(require_ghost_admin),
) -> Tiers:
    tier = db.get(Tiers, tier_id)
    if tier is None or tier.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tier não encontrado.")

    before = dict(tier.detalhes or {})
    updates = payload.model_dump(exclude_unset=True)
    new_detalhes = dict(before)
    new_detalhes.update(updates)
    tier.detalhes = new_detalhes

    _log_admin_action(
        db,
        admin_email=admin_email,
        action="update_tier",
        entity="tiers",
        entity_id=str(tier_id),
        before=before,
        after=new_detalhes,
    )
    db.commit()
    db.refresh(tier)
    return tier
```

- [ ] **Step 4: Rodar os testes de tiers**

Run: `python -m pytest api/tests/test_admin_tiers.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Regressão da suíte da api**

Run: `python -m pytest api/tests/ -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add api/routers/admin.py api/tests/test_admin_tiers.py
git commit -m "feat(admin): CRUD de tiers (GET/PUT) com auditoria"
```

---

### Task 3: Inverter precedência — api (parlamentares)

Hoje `_project_favorite_limit` usa env → `projetos.qtd_termos`, e **nunca** lê `tiers.detalhes.qtd_termos`. Passa a: DB (`tier.detalhes.qtd_termos`) → env → coluna.

**Files:**
- Modify: `api/routers/projects.py:506-510`
- Test: `api/tests/test_admin_tier_precedence.py` (create)

**Interfaces:**
- Consumes: `_project_tier_details` (já existe em `projects.py`).

- [ ] **Step 1: Escrever o teste (falhando)**

Create `api/tests/test_admin_tier_precedence.py`:

```python
"""DB (tier.detalhes) deve ganhar do env no limite de parlamentares."""
from __future__ import annotations

import pytest

from api.routers import projects


class _FakeTier:
    def __init__(self, detalhes: dict) -> None:
        self.detalhes = detalhes
        self.product_id = "cidadao-mamute"


class _FakeProject:
    def __init__(self, detalhes: dict, qtd_termos_col: int = 0) -> None:
        self.tier = _FakeTier(detalhes)
        self.cliente = "cidadao-mamute"
        self.qtd_termos = qtd_termos_col


def test_db_detalhes_wins_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # env diz 3; DB diz 7 → deve valer 7.
    monkeypatch.setenv(
        "MAMUTE_TIER_LIMITS_JSON",
        '{"cidadao-mamute": {"qtd_termos": 3}}',
    )
    project = _FakeProject({"qtd_termos": 7})
    assert projects._project_favorite_limit(project) == 7


def test_env_used_when_db_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "MAMUTE_TIER_LIMITS_JSON",
        '{"cidadao-mamute": {"qtd_termos": 3}}',
    )
    project = _FakeProject({})  # sem qtd_termos no DB
    assert projects._project_favorite_limit(project) == 3


def test_column_fallback_when_both_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MAMUTE_TIER_LIMITS_JSON", raising=False)
    project = _FakeProject({}, qtd_termos_col=2)
    assert projects._project_favorite_limit(project) == 2
```

- [ ] **Step 2: Rodar (falha — env ainda ganha)**

Run: `python -m pytest api/tests/test_admin_tier_precedence.py -v`
Expected: FAIL em `test_db_detalhes_wins_over_env` (retorna 3, não 7).

- [ ] **Step 3: Inverter a precedência**

Em `api/routers/projects.py`, substitua `_project_favorite_limit` (linhas 506-510) por:

```python
def _tier_limit_from_db(project: Projetos, field_name: str) -> int | None:
    detalhes = _project_tier_details(project)
    raw = detalhes.get(field_name)
    if raw is None:
        return None
    return _coerce_non_negative_int(
        raw, field_name=field_name, slug=_project_tier_slug(project)
    )


def _project_favorite_limit(project: Projetos) -> int:
    db_limit = _tier_limit_from_db(project, "qtd_termos")
    if db_limit is not None:
        return db_limit
    env_limit = _tier_limit_from_env(project, "qtd_termos")
    if env_limit is not None:
        return env_limit
    return max(0, int(project.qtd_termos or 0))
```

- [ ] **Step 4: Rodar os testes + regressão**

Run: `python -m pytest api/tests/test_admin_tier_precedence.py api/tests/test_project_favorite_limits.py -v`
Expected: PASS (novos + os existentes de favoritos, que não setam `tier.detalhes.qtd_termos`).

- [ ] **Step 5: Commit**

```bash
git add api/routers/projects.py api/tests/test_admin_tier_precedence.py
git commit -m "feat(admin): DB (tier.detalhes) ganha do env no limite de parlamentares"
```

---

### Task 4: Inverter precedência — chatbot (consultas IA)

`resolve_monthly_limit` já lê `tier_details` (DB), mas por último. Passa a ler o DB **primeiro**.

**Files:**
- Modify: `chatbot_backend/app/services/quota.py:161-188`
- Test: `chatbot_backend/tests/test_quota_precedence.py` (create — confirmar caminho de testes do chatbot no Step 1)

**Interfaces:**
- Consumes: `ChatProject` (`tier_details`, `tier_slug`, `product_id`), `resolve_monthly_limit`.

- [ ] **Step 1: Descobrir o layout de testes do chatbot**

Run: `ls chatbot_backend/tests/ 2>/dev/null || find chatbot_backend -name "conftest.py" -o -name "test_*.py" | head`
Se houver um `conftest.py` que injete env/settings, siga-o. Caso não exista pasta de testes, crie `chatbot_backend/tests/__init__.py` vazio e um `conftest.py` que garanta `get_settings.cache_clear()` entre testes:

```python
# chatbot_backend/tests/conftest.py
from __future__ import annotations

import pytest

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
```

- [ ] **Step 2: Escrever o teste (falhando)**

Create `chatbot_backend/tests/test_quota_precedence.py`:

```python
"""DB (tier_details) deve ganhar do env em resolve_monthly_limit."""
from __future__ import annotations

import pytest

from app.services.quota import ChatProject, resolve_monthly_limit


def _project(details: dict, product_id: str = "cidadao-mamute") -> ChatProject:
    return ChatProject(
        id=1,
        email="user@x.com",
        product_id=product_id,
        tier_slug=product_id,
        tier_details=details,
    )


def test_db_details_wins_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "MAMUTE_TIER_LIMITS_JSON",
        '{"cidadao-mamute": {"qtd_consultas_ia_mes": 50}}',
    )
    assert resolve_monthly_limit(_project({"qtd_consultas_ia_mes": 200})) == 200


def test_env_used_when_db_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "MAMUTE_TIER_LIMITS_JSON",
        '{"cidadao-mamute": {"qtd_consultas_ia_mes": 50}}',
    )
    assert resolve_monthly_limit(_project({})) == 50
```

- [ ] **Step 3: Inverter a precedência**

Em `chatbot_backend/app/services/quota.py`, substitua o corpo de `resolve_monthly_limit` (linhas 161-188) por:

```python
def resolve_monthly_limit(project: ChatProject) -> int:
    """Resolve the monthly chatbot quota for a project (DB > env > default)."""

    settings = get_settings()

    # 1) DB (tier.detalhes) vence.
    for detail_key in ("qtd_consultas_ia_mes", "ai_queries_monthly_limit"):
        raw_limit = project.tier_details.get(detail_key)
        if raw_limit is None:
            continue
        try:
            return max(0, int(raw_limit))
        except (TypeError, ValueError) as exc:
            raise ChatQuotaConfigError(
                f"Valor inválido de {detail_key} para o tier {project.tier_slug!r}."
            ) from exc

    # 2) Env: override por slug do chatbot.
    env_limits = _parse_monthly_limits(settings.chatbot_monthly_limits_json)
    for key in (project.tier_slug, project.product_id):
        if key and key in env_limits:
            return env_limits[key]

    # 3) Env: MAMUTE_TIER_LIMITS_JSON.
    tier_env_limit = _limit_from_tier_entitlements(
        project,
        _parse_tier_entitlement_limits(settings.tier_limits_json),
    )
    if tier_env_limit is not None:
        return tier_env_limit

    # 4) Default.
    return max(0, int(settings.chatbot_default_monthly_limit))
```

- [ ] **Step 4: Rodar os testes do chatbot**

Run: `cd /Users/luiz/dev/correio-sabia/mamute-politico/chatbot_backend && python -m pytest tests/test_quota_precedence.py -v`
Expected: PASS (2 passed). Rode também a suíte do chatbot se existir: `python -m pytest tests/ -q`.

- [ ] **Step 5: Commit**

```bash
cd /Users/luiz/dev/correio-sabia/mamute-politico
git add chatbot_backend/app/services/quota.py chatbot_backend/tests/
git commit -m "feat(admin): DB (tier.detalhes) ganha do env na quota de IA"
```

---

### Task 5: Bootstrap `env → tiers.detalhes` (idempotente)

Copia `MAMUTE_TIER_LIMITS_JSON` para `tiers.detalhes`, casando por `product_id`. Idempotente. Roda **antes** de desligar as vars de tier no `.env`, garantindo paridade.

**Files:**
- Create: `scripts/bootstrap_tiers_from_env.py`
- Test: `api/tests/test_bootstrap_tiers.py` (create)

**Interfaces:**
- Produces: `bootstrap_tiers_from_env(session, raw_json: str) -> list[str]` (retorna product_ids atualizados).

- [ ] **Step 1: Escrever o teste (falhando)**

Create `api/tests/test_bootstrap_tiers.py`:

```python
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
```

- [ ] **Step 2: Rodar (falha — módulo inexistente)**

Run: `python -m pytest api/tests/test_bootstrap_tiers.py -v`
Expected: FAIL (ImportError).

- [ ] **Step 3: Implementar o script**

Create `scripts/__init__.py` (vazio, se não existir) e `scripts/bootstrap_tiers_from_env.py`:

```python
"""Copia MAMUTE_TIER_LIMITS_JSON para tiers.detalhes (idempotente).

Uso: DATABASE_URL=... MAMUTE_TIER_LIMITS_JSON=... python -m scripts.bootstrap_tiers_from_env
"""
from __future__ import annotations

import json
import os
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

_KEYS = ("qtd_termos", "qtd_consultas_ia_mes")


def bootstrap_tiers_from_env(session: Session, raw_json: str) -> list[str]:
    payload: dict[str, Any] = json.loads(raw_json) if raw_json.strip() else {}
    updated: list[str] = []
    for product_id, entry in payload.items():
        if not isinstance(entry, dict):
            continue
        row = session.execute(
            text("select id, detalhes from tiers where product_id = :pid "
                 "and deleted_at is null"),
            {"pid": product_id},
        ).mappings().first()
        if row is None:
            continue
        current = json.loads(row["detalhes"]) if isinstance(row["detalhes"], str) else dict(row["detalhes"] or {})
        changed = False
        for key in _KEYS:
            if key in entry and current.get(key) != entry[key]:
                current[key] = entry[key]
                changed = True
        if changed:
            session.execute(
                text("update tiers set detalhes = :d where id = :id"),
                {"d": json.dumps(current, ensure_ascii=False), "id": row["id"]},
            )
            updated.append(product_id)
    session.commit()
    return updated


def main() -> None:
    from api.db.engine import SessionLocal  # reusa a engine da api

    raw = os.getenv("MAMUTE_TIER_LIMITS_JSON", "")
    session = SessionLocal()
    try:
        updated = bootstrap_tiers_from_env(session, raw)
        print(f"Tiers atualizados: {updated}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Rodar os testes**

Run: `python -m pytest api/tests/test_bootstrap_tiers.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/__init__.py scripts/bootstrap_tiers_from_env.py api/tests/test_bootstrap_tiers.py
git commit -m "feat(admin): script idempotente de bootstrap env->tiers.detalhes"
```

---

### Task 6: Frontend — Painel de Gestão de Tiers

**Files:**
- Modify: `ui/src/api/admin.ts` (adicionar tipos + `fetchTiers`/`updateTier`)
- Create: `ui/src/hooks/useTiers.ts`
- Create: `ui/src/pages/AdminTiersPage.tsx`
- Modify: `ui/src/pages/AdminPage.tsx` (link/entrada pro painel de tiers) OU `ui/src/App.tsx` (sub-rota `/admin/tiers`)

**Interfaces:**
- Consumes: `request` (`api/client.ts`), shadcn `Card`, `Button`, `Input`, `Label`, `useToast`.
- Produces: `Tier` (`{id, tier_name_debug, product_id, detalhes}`), `fetchTiers(): Promise<Tier[]>`, `updateTier(id, patch): Promise<Tier>`.

- [ ] **Step 1: Estender o client admin**

Adicione ao fim de `ui/src/api/admin.ts`:

```ts
export interface TierDetails {
  qtd_termos?: number;
  qtd_consultas_ia_mes?: number;
  qtd_email?: number;
  periodicidade_email?: string[];
  orgao?: string[];
  preco_mensal?: number;
  [key: string]: unknown;
}

export interface Tier {
  id: number;
  tier_name_debug: string;
  product_id: string;
  detalhes: TierDetails;
}

export function fetchTiers(): Promise<Tier[]> {
  return request<Tier[]>('/admin/tiers');
}

export function updateTier(id: number, patch: TierDetails): Promise<Tier> {
  return request<Tier>(`/admin/tiers/${id}`, {
    method: 'PUT',
    body: JSON.stringify(patch),
  });
}
```

- [ ] **Step 2: Hook de tiers**

Create `ui/src/hooks/useTiers.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchTiers, updateTier, type TierDetails } from '@/api/admin';

export function useTiers() {
  return useQuery({ queryKey: ['admin', 'tiers'], queryFn: fetchTiers });
}

export function useUpdateTier() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: TierDetails }) =>
      updateTier(id, patch),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'tiers'] }),
  });
}
```

- [ ] **Step 3: Página do painel de tiers**

Create `ui/src/pages/AdminTiersPage.tsx`:

```tsx
import { useState } from 'react';
import { useTiers, useUpdateTier } from '@/hooks/useTiers';
import type { Tier } from '@/api/admin';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useToast } from '@/components/ui/use-toast';

const NUM_FIELDS: { key: 'qtd_termos' | 'qtd_consultas_ia_mes' | 'qtd_email' | 'preco_mensal'; label: string }[] = [
  { key: 'qtd_termos', label: 'Parlamentares (qtd_termos)' },
  { key: 'qtd_consultas_ia_mes', label: 'Consultas IA/mês' },
  { key: 'qtd_email', label: 'E-mails (qtd_email)' },
  { key: 'preco_mensal', label: 'Preço mensal (R$)' },
];

function TierCard({ tier }: { tier: Tier }) {
  const update = useUpdateTier();
  const { toast } = useToast();
  const [form, setForm] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      NUM_FIELDS.map((f) => [f.key, tier.detalhes[f.key] != null ? String(tier.detalhes[f.key]) : '']),
    ),
  );

  const save = async () => {
    const patch: Record<string, number> = {};
    for (const f of NUM_FIELDS) {
      if (form[f.key] !== '') patch[f.key] = Number(form[f.key]);
    }
    try {
      await update.mutateAsync({ id: tier.id, patch });
      toast({ title: 'Tier atualizado', description: tier.product_id });
    } catch (e) {
      toast({ title: 'Erro ao salvar', description: String(e), variant: 'destructive' });
    }
  };

  return (
    <Card className="p-6 space-y-4">
      <div>
        <h2 className="text-lg font-semibold">{tier.tier_name_debug}</h2>
        <p className="text-sm text-muted-foreground">{tier.product_id}</p>
      </div>
      <div className="grid grid-cols-2 gap-4">
        {NUM_FIELDS.map((f) => (
          <div key={f.key} className="space-y-1">
            <Label htmlFor={`${tier.id}-${f.key}`}>{f.label}</Label>
            <Input
              id={`${tier.id}-${f.key}`}
              type="number"
              min={0}
              value={form[f.key]}
              onChange={(e) => setForm((s) => ({ ...s, [f.key]: e.target.value }))}
            />
          </div>
        ))}
      </div>
      <Button onClick={save} disabled={update.isPending}>
        {update.isPending ? 'Salvando…' : 'Salvar'}
      </Button>
    </Card>
  );
}

export default function AdminTiersPage() {
  const { data: tiers, isLoading, error } = useTiers();

  return (
    <main className="mx-auto max-w-3xl p-8 space-y-6">
      <h1 className="text-2xl font-semibold">Gestão de Tiers</h1>
      {isLoading && <p className="text-muted-foreground">Carregando…</p>}
      {error && <p className="text-destructive">Erro ao carregar tiers.</p>}
      {tiers?.map((tier) => <TierCard key={tier.id} tier={tier} />)}
    </main>
  );
}
```

- [ ] **Step 4: Rota `/admin/tiers` protegida**

Em `ui/src/App.tsx`, adicione o import (junto aos outros de página):

```tsx
import AdminTiersPage from "./pages/AdminTiersPage";
```

E a rota, logo após a rota `/admin` (dentro do mesmo bloco, acima do catch-all):

```tsx
              <Route
                path="/admin/tiers"
                element={
                  <RequireAdmin>
                    <AdminTiersPage />
                  </RequireAdmin>
                }
              />
```

- [ ] **Step 5: Link do painel na AdminPage**

Substitua o corpo de `ui/src/pages/AdminPage.tsx` por:

```tsx
import { Link } from 'react-router-dom';

export default function AdminPage() {
  return (
    <main className="mx-auto max-w-3xl p-8 space-y-4">
      <h1 className="text-2xl font-semibold">Painel administrativo</h1>
      <ul className="list-disc pl-6">
        <li>
          <Link to="/admin/tiers" className="text-primary underline">
            Gestão de Tiers
          </Link>
        </li>
      </ul>
    </main>
  );
}
```

- [ ] **Step 6: Build/typecheck**

Run: `cd /Users/luiz/dev/correio-sabia/mamute-politico/ui && npm run build`
Expected: build sem erros de TypeScript.

- [ ] **Step 7: Commit**

```bash
cd /Users/luiz/dev/correio-sabia/mamute-politico
git add ui/src/api/admin.ts ui/src/hooks/useTiers.ts ui/src/pages/AdminTiersPage.tsx ui/src/pages/AdminPage.tsx ui/src/App.tsx
git commit -m "feat(admin): painel de gestão de tiers no front"
```

---

### Task 7: Validação local (preview com DB seedado)

O painel **escreve** em `tiers`, então **NÃO** usar o Postgres de prod. Subir um Postgres local (pgvector via OrbStack), rodar as migrations e semear os 3 tiers reais (valores do `api/.env.example`).

**Files:** nenhum (infra + verificação manual).

- [ ] **Step 1: Subir Postgres local (pgvector) via OrbStack**

Run:
```bash
docker run -d --name mamute-admin-preview-db \
  -e POSTGRES_DB=mamute -e POSTGRES_USER=mamute -e POSTGRES_PASSWORD=mamute \
  -p 5433:5432 pgvector/pgvector:pg18-trixie
```

- [ ] **Step 2: Rodar migrations na base local**

Run (da raiz):
```bash
cd mamute_scrappers && DATABASE_URL="postgresql+psycopg2://mamute:mamute@localhost:5433/mamute" \
  python -m alembic upgrade head && cd ..
```
Expected: chega até `c1d2e3f4a5b6` sem erro.

- [ ] **Step 3: Semear os 3 tiers reais**

Run (psql via container):
```bash
docker exec -i mamute-admin-preview-db psql -U mamute -d mamute <<'SQL'
INSERT INTO tiers (tier_name_debug, product_id, detalhes) VALUES
 ('Free', 'free', '{"qtd_termos":1,"qtd_consultas_ia_mes":0}'),
 ('Default', 'default-product', '{"qtd_termos":3,"qtd_consultas_ia_mes":50}'),
 ('Cidadão Mamute', 'cidadao-mamute', '{"qtd_termos":10,"qtd_consultas_ia_mes":200}')
ON CONFLICT (product_id) DO NOTHING;
SQL
```

- [ ] **Step 4: Reapontar a api local pro DB seedado**

Reiniciar o uvicorn com `DATABASE_URL="postgresql+psycopg2://mamute:mamute@localhost:5433/mamute"` (mantendo `GHOST_BASE_URL`, `MAMUTE_ADMIN_PANELS_ENABLED=true`, `MAMUTE_ADMIN_EMAILS`). O front (vite) segue no ar com o bypass de preview.

- [ ] **Step 5: Checklist manual**

- [ ] Abrir `http://localhost:8080/app/admin` → link **Gestão de Tiers** → `/admin/tiers` lista os 3 tiers com valores reais.
- [ ] Editar `Consultas IA/mês` de um tier e Salvar → toast de sucesso; recarregar mostra o novo valor.
- [ ] Conferir no banco: `docker exec -it mamute-admin-preview-db psql -U mamute -d mamute -c "select product_id, detalhes from tiers;"` reflete a edição.
- [ ] Conferir auditoria: `... -c "select admin_email, action, entity_id, after from admin_audit_log;"` tem a linha da edição.
- [ ] `GET /api/admin/tiers` sem token (curl direto no uvicorn) → **404** (gate segue valendo).

- [ ] **Step 6: Sinalizar pro Luiz revisar** antes de PR / Plano 3.

---

## Self-Review

**Spec coverage (Plano 2 — spec §5):** CRUD de tiers ✔ (Task 2), validação Pydantic ✔ (Task 2), `preco_mensal` ✔ (Task 2/6), inverter precedência api ✔ (Task 3) e chatbot ✔ (Task 4), bootstrap env→DB idempotente ✔ (Task 5), auditoria ✔ (Task 1/2), editar sem redeploy ✔ (leitura por request já existente + DB-wins), front `TiersPanel` ✔ (Task 6), validação local ✔ (Task 7).

**Placeholder scan:** sem TBD/TODO; código completo em cada passo.

**Type consistency:** `TierOut`/`TierDetailsUpdate` (backend) ↔ `Tier`/`TierDetails` (front) com os mesmos campos; `_tier_limit_from_db`/`_tier_limit_from_env`/`_project_favorite_limit` encadeados; `bootstrap_tiers_from_env(session, raw)` idêntico entre teste e script; `AdminAuditLog` colunas iguais entre model, migration e DDL dos testes.

**Risco destacado:** Task 3 muda comportamento de produção AO VIVO (limite de parlamentares). Mitigação: rodar o bootstrap (Task 5) para dar paridade DB=env **antes** de remover as vars de tier do `.env`. Ordem de deploy: migration → bootstrap → deploy do código com DB-wins.
