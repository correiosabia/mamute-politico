# Feature flags gerenciáveis pelo admin — Plano de implementação (PR 1 de 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mecanismo único de feature flag com três estados (`off`/`admins`/`all`), gerenciado em `/admin/configuracoes` sem redeploy, com a aba Trajetória migrada do gate `isAdmin` improvisado para ele.

**Architecture:** O registro de *quais flags existem* mora em TypeScript (`ui/src/lib/featureFlags.ts`); o banco (`feature_flag`) guarda só *o estado*. Linha ausente = `off`. O endpoint público resolve o tri-estado no servidor e devolve booleano puro, então `useFeatureFlag(key)` é `boolean`. A tela de admin itera sobre o registro, não sobre o banco — é isso que faz uma flag removida sumir do controle sozinha.

**Tech Stack:** FastAPI + SQLAlchemy 2.x + Alembic (backend), React 18 + TypeScript + TanStack Query + Vitest/testing-library (frontend), Postgres 18 (prod) / SQLite in-memory (testes de API).

## Global Constraints

- Spec de referência: `docs/superpowers/specs/2026-08-12-feature-flags-design.md`.
- Estados válidos, exatamente estes três literais: `off`, `admins`, `all`.
- **Linha ausente na tabela = `off`.** Nenhuma flag nova exige migration.
- A flag controla **só a UI**. Nenhum endpoint de dado é fechado por flag.
- Comentários e docstrings em português, sem acento em nome de identificador (padrão do repo).
- Modelos duplicados em `api/db/models/` e `mamute_scrappers/db/models/`, como todas as tabelas do projeto.
- Imports de módulo em `api/` usam o bloco `try: from ..x / except ImportError: from x` (execução como pacote ou dentro de `api/`).
- Head do Alembic hoje: `e6f7a8b9c0d1` (cadeia linear única de 20 migrations, igual ao que está em produção).
- Branch: `feat/feature-flags`, já criada a partir da `main` atualizada. PR contra a `main`.

---

### Task 1: Tabela `feature_flag` (migration + modelos)

**Files:**
- Create: `mamute_scrappers/migrations/versions/a1b2c3d4e5f6_add_feature_flag.py`
- Create: `mamute_scrappers/db/models/feature_flag.py`
- Create: `api/db/models/feature_flag.py`
- Modify: `mamute_scrappers/db/models/__init__.py`
- Modify: `api/db/models/__init__.py`

**Interfaces:**
- Produces: modelo `FeatureFlag` com colunas `key: str` (PK), `state: str`, `updated_at: datetime`. Constantes `STATE_OFF = "off"`, `STATE_ADMINS = "admins"`, `STATE_ALL = "all"`, `VALID_STATES = frozenset({...})` exportadas de ambos os módulos de modelo.

- [ ] **Step 1: Criar o modelo em `mamute_scrappers/db/models/feature_flag.py`**

```python
"""Estado das feature flags da interface.

O registro de QUAIS flags existem mora no front (`ui/src/lib/featureFlags.ts`).
Esta tabela guarda apenas em que estado cada uma esta. Linha ausente vale
`off`, e e isso que faz feature nova nascer desligada sem migration por flag.

Linha aqui sem chave correspondente no registro do front e inerte: a tela de
administracao itera sobre o registro, entao a flag removida do codigo some do
controle sozinha.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Column, DateTime, Text
from sqlalchemy.sql import func

from ..base import Base

STATE_OFF = "off"
STATE_ADMINS = "admins"
STATE_ALL = "all"
VALID_STATES = frozenset({STATE_OFF, STATE_ADMINS, STATE_ALL})


class FeatureFlag(Base):
    __tablename__ = "feature_flag"
    __table_args__ = (
        CheckConstraint(
            "state in ('off', 'admins', 'all')",
            name="ck_feature_flag_state",
        ),
    )

    key = Column(Text, primary_key=True)
    state = Column(Text, nullable=False, server_default=STATE_OFF)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


__all__ = [
    "FeatureFlag",
    "STATE_ADMINS",
    "STATE_ALL",
    "STATE_OFF",
    "VALID_STATES",
]
```

- [ ] **Step 2: Copiar o mesmo arquivo para `api/db/models/feature_flag.py`**

Conteúdo idêntico ao Step 1 (o `from ..base import Base` resolve para o `Base` de cada pacote). Verificar que `api/db/base.py` existe e exporta `Base`:

Run: `grep -n "^Base\|Base =" api/db/base.py`
Expected: linha definindo `Base`.

- [ ] **Step 3: Registrar nos dois `__init__.py`**

Em `mamute_scrappers/db/models/__init__.py`, adicionar em ordem alfabética o import `from .feature_flag import FeatureFlag` (entre `.electoral_history` e `.parliamentarian`) e `"FeatureFlag",` na `__all__`.

Em `api/db/models/__init__.py`, o mesmo (entre `.electoral_history` e `.model_pricing`).

- [ ] **Step 4: Criar a migration**

```python
"""add feature_flag

Revision ID: a1b2c3d4e5f6
Revises: e6f7a8b9c0d1
Create Date: 2026-08-12

Semeia a trajetoria como `admins` porque ela ja esta visivel para admins em
producao — sem o seed, o deploy a esconderia.
"""

from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feature_flag",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column(
            "state", sa.Text(), nullable=False, server_default="off"
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state in ('off', 'admins', 'all')", name="ck_feature_flag_state"
        ),
    )
    op.execute(
        "insert into feature_flag (key, state) values ('trajetoria', 'admins')"
    )


def downgrade() -> None:
    op.drop_table("feature_flag")
```

- [ ] **Step 5: Verificar que a cadeia do Alembic continua com head único**

Run:
```bash
cd mamute_scrappers && python3 -c "
import re, pathlib
revs={}
for p in pathlib.Path('migrations/versions').glob('*.py'):
    t=p.read_text()
    r=re.search(r'^revision(?:\s*:\s*str)?\s*=\s*[\"\']([^\"\']+)', t, re.M)
    d=re.search(r'^down_revision(?:\s*:[^=]+)?\s*=\s*(.+)\$', t, re.M)
    dv=re.findall(r'[\"\']([^\"\']+)[\"\']', d.group(1)) if d else []
    if r: revs[r.group(1)]=dv
par={x for v in revs.values() for x in v}
print('heads:', [r for r in revs if r not in par])
"
```
Expected: `heads: ['a1b2c3d4e5f6']` — head único.

- [ ] **Step 6: Commit**

```bash
git add mamute_scrappers/migrations/versions/a1b2c3d4e5f6_add_feature_flag.py \
        mamute_scrappers/db/models/feature_flag.py api/db/models/feature_flag.py \
        mamute_scrappers/db/models/__init__.py api/db/models/__init__.py
git commit -m "feat(ff): tabela feature_flag com estado tri-valorado"
```

---

### Task 2: `resolve_ghost_admin` — checagem de admin que não levanta exceção

**Files:**
- Modify: `api/security.py:144-169`
- Test: `api/tests/test_feature_flags.py` (criado aqui, ampliado na Task 4)

**Interfaces:**
- Produces: `resolve_ghost_admin(request: Request, authorization: str | None) -> str | None` — devolve o e-mail do admin ou `None`. `require_ghost_admin` passa a delegar nela.

**Por quê:** `require_ghost_admin` levanta 404 para não-admin (esconde a superfície do painel). O endpoint público de flags precisa saber se o chamador é admin **sem** transformar "não é admin" em erro.

- [ ] **Step 1: Escrever o teste que falha**

```python
"""Feature flags: resolucao de estado e rotas."""
from __future__ import annotations

from types import SimpleNamespace

from api.security import resolve_ghost_admin


def test_resolve_ghost_admin_sem_authorization_devolve_none():
    request = SimpleNamespace(state=SimpleNamespace())
    assert resolve_ghost_admin(request, None) is None


def test_resolve_ghost_admin_com_token_invalido_devolve_none():
    request = SimpleNamespace(state=SimpleNamespace())
    assert resolve_ghost_admin(request, "Bearer lixo") is None
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `python -m pytest api/tests/test_feature_flags.py -v`
Expected: FAIL com `ImportError: cannot import name 'resolve_ghost_admin'`.

- [ ] **Step 3: Refatorar `api/security.py`**

Substituir o corpo atual de `require_ghost_admin` (linhas 144-169) por:

```python
def resolve_ghost_admin(
    request: Request, authorization: str | None
) -> str | None:
    """Identifica o admin sem levantar excecao. `None` = nao e admin.

    Existe porque `require_ghost_admin` transforma "nao e admin" em 404 para
    esconder a superficie do painel — comportamento certo para as rotas de
    admin e errado para quem so precisa saber se deve exibir uma feature.
    """
    cfg = get_admin_settings()
    if not cfg["enabled"] or not authorization:
        return None

    try:
        token = _extract_token(authorization)
        decoded = _decode_ghost_jwt(token)
    except Exception:  # noqa: BLE001 — qualquer erro de token vira "nao admin"
        return None

    email = (decoded.get("sub") or "").strip().lower()
    if not email or email not in cfg["emails"]:
        return None

    request.state.token_payload = decoded
    request.state.token_email = email
    request.state.is_admin = True
    return email


def require_ghost_admin(
    request: Request, authorization: str | None = Header(default=None)
) -> str:
    """Gate unico de admin. Qualquer falha vira 404 (esconde a superficie)."""
    email = resolve_ghost_admin(request, authorization)
    if email is None:
        raise HTTPException(status_code=404, detail="Not Found")
    return email
```

Adicionar `"resolve_ghost_admin"` à `__all__` no fim do arquivo.

- [ ] **Step 4: Rodar os testes**

Run: `python -m pytest api/tests/test_feature_flags.py api/tests/ -k "admin or security or whoami" -v`
Expected: PASS, incluindo os testes de admin já existentes (a refatoração não muda o comportamento externo).

- [ ] **Step 5: Commit**

```bash
git add api/security.py api/tests/test_feature_flags.py
git commit -m "refactor(security): resolve_ghost_admin sem excecao, require delega nela"
```

---

### Task 3: Service `feature_flags`

**Files:**
- Create: `api/services/feature_flags.py`
- Test: `api/tests/test_feature_flags.py` (ampliar)

**Interfaces:**
- Consumes: `FeatureFlag`, `VALID_STATES`, `STATE_ADMINS`, `STATE_ALL` (Task 1).
- Produces:
  - `get_states(db: Session) -> dict[str, str]`
  - `resolve_for(db: Session, is_admin: bool) -> dict[str, bool]`
  - `set_state(db: Session, key: str, state: str) -> dict` — devolve `{"key", "state", "updated_at"}`; levanta `ValueError` em estado inválido. Não commita.

- [ ] **Step 1: Escrever os testes que falham**

Acrescentar a `api/tests/test_feature_flags.py`:

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from api.services.feature_flags import get_states, resolve_for, set_state


def _session_com_flags(linhas: list[tuple[str, str]]) -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            create table feature_flag (
                key text primary key,
                state text not null default 'off',
                updated_at datetime not null default current_timestamp
            )
            """
        )
        for key, state in linhas:
            conn.exec_driver_sql(
                "insert into feature_flag (key, state) values (?, ?)",
                (key, state),
            )
    return sessionmaker(bind=engine)()


def test_resolve_for_nao_admin():
    db = _session_com_flags([("a", "all"), ("b", "admins"), ("c", "off")])
    assert resolve_for(db, is_admin=False) == {"a": True, "b": False, "c": False}


def test_resolve_for_admin():
    db = _session_com_flags([("a", "all"), ("b", "admins"), ("c", "off")])
    assert resolve_for(db, is_admin=True) == {"a": True, "b": True, "c": False}


def test_get_states_devolve_tri_estado_cru():
    db = _session_com_flags([("a", "all"), ("c", "off")])
    assert get_states(db) == {"a": "all", "c": "off"}


def test_chave_sem_linha_nao_aparece():
    """O front le a ausencia como off; o backend nao inventa a chave."""
    db = _session_com_flags([("a", "all")])
    assert "inexistente" not in resolve_for(db, is_admin=True)


def test_set_state_cria_linha_quando_nao_existe():
    db = _session_com_flags([])
    resultado = set_state(db, "nova", "admins")
    assert resultado["key"] == "nova"
    assert resultado["state"] == "admins"
    assert get_states(db) == {"nova": "admins"}


def test_set_state_atualiza_linha_existente():
    db = _session_com_flags([("a", "off")])
    set_state(db, "a", "all")
    assert get_states(db) == {"a": "all"}


def test_set_state_recusa_estado_invalido():
    db = _session_com_flags([])
    with pytest.raises(ValueError):
        set_state(db, "a", "talvez")
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `python -m pytest api/tests/test_feature_flags.py -v`
Expected: FAIL com `ModuleNotFoundError: api.services.feature_flags`.

- [ ] **Step 3: Implementar o service**

```python
"""Leitura e escrita do estado das feature flags.

O registro de quais flags existem mora no front. Aqui so ha estado, e a
regra de resolucao do tri-estado para booleano.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

try:
    from ..db.models.feature_flag import (
        STATE_ADMINS,
        STATE_ALL,
        VALID_STATES,
        FeatureFlag,
    )
except ImportError:  # execução dentro de api/
    from db.models.feature_flag import (
        STATE_ADMINS,
        STATE_ALL,
        VALID_STATES,
        FeatureFlag,
    )


def get_states(db: Session) -> dict[str, str]:
    """Tri-estado cru de cada linha gravada."""
    linhas = db.execute(select(FeatureFlag.key, FeatureFlag.state)).all()
    return {key: state for key, state in linhas}


def resolve_for(db: Session, is_admin: bool) -> dict[str, bool]:
    """Aplica o tri-estado ao chamador.

    Devolve booleano, e nao o estado cru, para o front nao precisar repetir
    esta regra — e para o call site do `useFeatureFlag` ser o mais simples
    possivel, que e o que torna a remocao da flag barata.
    """
    return {
        key: state == STATE_ALL or (state == STATE_ADMINS and is_admin)
        for key, state in get_states(db).items()
    }


def set_state(db: Session, key: str, state: str) -> dict:
    """Grava o estado da flag. Nao commita: quem chama decide o momento."""
    if state not in VALID_STATES:
        raise ValueError(f"estado invalido: {state!r}")

    linha = db.get(FeatureFlag, key)
    if linha is None:
        linha = FeatureFlag(key=key, state=state)
        db.add(linha)
    else:
        linha.state = state
    linha.updated_at = datetime.now(timezone.utc)
    db.flush()

    return {"key": linha.key, "state": linha.state, "updated_at": linha.updated_at}
```

- [ ] **Step 4: Rodar os testes**

Run: `python -m pytest api/tests/test_feature_flags.py -v`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
git add api/services/feature_flags.py api/tests/test_feature_flags.py
git commit -m "feat(ff): service com resolucao do tri-estado"
```

---

### Task 4: Rotas — pública e de admin

**Files:**
- Modify: `api/routers/settings.py`
- Modify: `api/routers/admin.py`
- Test: `api/tests/test_feature_flags.py` (ampliar)

**Interfaces:**
- Consumes: `get_states`, `resolve_for`, `set_state` (Task 3), `resolve_ghost_admin` (Task 2).
- Produces:
  - `GET /settings/feature-flags` → `{"trajetoria": false}` (booleano resolvido)
  - `GET /admin/settings/feature-flags` → `[{"key","state","updated_at"}]`
  - `PUT /admin/settings/feature-flags/{key}` body `{"state": "admins"}` → `{"key","state","updated_at"}`

- [ ] **Step 1: Escrever os testes de rota que falham**

Acrescentar a `api/tests/test_feature_flags.py`, seguindo o padrão de `api/tests/test_amendments.py` (SQLite in-memory + `get_db` sobrescrito + `verify_token` sobrescrito):

```python
from fastapi.testclient import TestClient

from api import main
from api.dependencies import get_db
from api.security import require_ghost_admin, verify_token


def _client(linhas: list[tuple[str, str]], admin: bool = False) -> TestClient:
    db = _session_com_flags(linhas)
    app = main.app
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[verify_token] = lambda: {"sub": "u@x.com"}
    if admin:
        app.dependency_overrides[require_ghost_admin] = lambda: "admin@x.com"
    return TestClient(app)


def test_rota_publica_devolve_booleano_resolvido_para_nao_admin():
    client = _client([("a", "all"), ("b", "admins")])
    r = client.get("/api/settings/feature-flags")
    assert r.status_code == 200
    assert r.json() == {"a": True, "b": False}
    main.app.dependency_overrides.clear()


def test_admin_put_cria_e_atualiza():
    client = _client([], admin=True)
    r = client.put("/api/admin/settings/feature-flags/nova", json={"state": "all"})
    assert r.status_code == 200
    assert r.json()["state"] == "all"
    r = client.get("/api/admin/settings/feature-flags")
    assert [x["key"] for x in r.json()] == ["nova"]
    main.app.dependency_overrides.clear()


def test_admin_put_recusa_estado_invalido():
    client = _client([], admin=True)
    r = client.put("/api/admin/settings/feature-flags/x", json={"state": "talvez"})
    assert r.status_code == 422
    main.app.dependency_overrides.clear()
```

Confirmar antes o prefixo real das rotas:
Run: `grep -n "api_router = APIRouter" -A 3 api/main.py`

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `python -m pytest api/tests/test_feature_flags.py -v -k rota or admin_put`
Expected: FAIL com 404 (rotas não existem).

- [ ] **Step 3: Rota pública em `api/routers/settings.py`**

Acrescentar ao bloco de imports `resolve_ghost_admin` (de `..security`) e `resolve_for` (de `..services.feature_flags`), e a rota:

```python
@router.get("/feature-flags")
def read_feature_flags(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    """Estado das flags ja resolvido para quem chamou.

    Devolve booleano e nao o tri-estado: quem nao e admin nao precisa saber
    que a flag existe em modo `admins`.
    """
    is_admin = resolve_ghost_admin(request, authorization) is not None
    return resolve_for(db, is_admin=is_admin)
```

Importar `Header` e `Request` de `fastapi`.

- [ ] **Step 4: Rotas de admin em `api/routers/admin.py`**

Adicionar aos dois blocos de import (`try` e `except ImportError`):
`from ..services.feature_flags import get_states as get_feature_flag_states, set_state as set_feature_flag_state` (e a versão sem `..` no bloco `except`).

Schemas e rotas, junto das rotas de `settings/word-cloud-terms`:

```python
class FeatureFlagUpdate(BaseModel):
    state: Literal["off", "admins", "all"]


class FeatureFlagOut(BaseModel):
    key: str
    state: str
    updated_at: datetime


@router.get("/settings/feature-flags", response_model=list[FeatureFlagOut])
def read_feature_flags_admin(
    db: Session = Depends(get_db),
    _admin: str = Depends(require_ghost_admin),
) -> list[dict]:
    estados = get_feature_flag_states(db)
    linhas = db.execute(select(FeatureFlag)).scalars().all()
    por_chave = {linha.key: linha.updated_at for linha in linhas}
    return [
        {"key": key, "state": state, "updated_at": por_chave.get(key)}
        for key, state in sorted(estados.items())
    ]


@router.put(
    "/settings/feature-flags/{key}", response_model=FeatureFlagOut
)
def update_feature_flag_route(
    key: str,
    payload: FeatureFlagUpdate,
    db: Session = Depends(get_db),
    admin_email: str = Depends(require_ghost_admin),
) -> dict:
    antes = get_feature_flag_states(db).get(key, "off")
    depois = set_feature_flag_state(db, key, payload.state)

    _log_admin_action(
        db,
        admin_email=admin_email,
        action="update_feature_flag",
        entity="feature_flag",
        entity_id=key,
        before={"state": antes},
        after={"state": payload.state},
    )
    db.commit()
    return depois
```

Importar `FeatureFlag` do modelo nos dois blocos, e `Literal` de `typing` (verificar se já está importado).

- [ ] **Step 5: Rodar os testes**

Run: `python -m pytest api/tests/test_feature_flags.py -v`
Expected: PASS (todos).

- [ ] **Step 6: Rodar a suíte de API inteira (não quebrar nada)**

Run: `python -m pytest api/tests/ -q`
Expected: tudo verde.

- [ ] **Step 7: Commit**

```bash
git add api/routers/settings.py api/routers/admin.py api/tests/test_feature_flags.py
git commit -m "feat(ff): rotas publica (booleano resolvido) e de admin (tri-estado)"
```

---

### Task 5: Registro e hook no front

**Files:**
- Create: `ui/src/lib/featureFlags.ts`
- Create: `ui/src/hooks/useFeatureFlag.ts`
- Create: `ui/src/hooks/useFeatureFlag.test.ts`
- Modify: `ui/src/api/endpoints.ts` (adicionar `fetchFeatureFlags`)

**Interfaces:**
- Produces:
  - `FEATURE_FLAGS` — objeto `as const` com `{ label: string; since: string }` por chave.
  - `type FeatureFlagKey = keyof typeof FEATURE_FLAGS`
  - `useFeatureFlag(key: FeatureFlagKey): boolean`
  - `fetchFeatureFlags(): Promise<Record<string, boolean>>`

- [ ] **Step 1: Criar o registro**

```ts
/**
 * Registro das feature flags da interface.
 *
 * Esta lista é a fonte da verdade de QUAIS flags existem; o banco guarda só
 * em que estado cada uma está. Chave sem linha no banco vale `off`.
 *
 * REGRAS
 *
 * 1. Uma flag, um portão, no ponto de montagem. O custo de uma flag não é a
 *    flag: é em quantos lugares ela é lida. Se a feature é uma tela ou uma
 *    aba, o portão é onde ela é montada. Se for um enriquecimento dentro de
 *    um componente existente, o portão fica dentro desse componente e não
 *    vaza para o pai.
 *
 * 2. Flag não aninha em flag. Para melhorar algo que ainda está atrás de uma
 *    flag, estenda a feature existente — não crie uma segunda flag dentro
 *    dela. Como a feature ainda não saiu para ninguém, não há o que separar.
 *
 * 3. Isto é controle de apresentação, não fronteira de segurança. A API
 *    continua aberta e qualquer um a chama direto. Nunca use este mecanismo
 *    para esconder algo que não pode ser visto.
 *
 * COMO REMOVER UMA FLAG (quando a feature está consolidada em produção)
 *
 * 1. Apague a linha daqui.
 * 2. Rode `tsc`. Ele quebra em todos os call sites, porque
 *    `useFeatureFlag('x')` deixa de tipar.
 * 3. Desembrulhe cada condicional que o compilador apontou.
 * 4. `tsc` verde = terminou. Está provado que não sobrou uso.
 *
 * A linha no banco fica órfã e inerte, e some do /admin/configuracoes
 * sozinha, porque a tela renderiza a partir deste registro.
 */
export const FEATURE_FLAGS = {
  trajetoria: {
    label: 'Aba Trajetória no dashboard do parlamentar',
    since: '2026-08-10',
  },
} as const;

export type FeatureFlagKey = keyof typeof FEATURE_FLAGS;

/** Dias desde o nascimento da flag, para a tela cobrar flag velha. */
export function flagAgeInDays(since: string, hoje = new Date()): number {
  const nascimento = new Date(`${since}T00:00:00Z`);
  const ms = hoje.getTime() - nascimento.getTime();
  return Math.max(0, Math.floor(ms / 86_400_000));
}

/** Acima disto a tela destaca a flag como candidata a remoção. */
export const FLAG_AGE_WARNING_DAYS = 60;
```

- [ ] **Step 2: Escrever o teste do hook (falhando)**

```ts
import { describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

import { fetchFeatureFlags } from '@/api/endpoints';
import { useFeatureFlag } from './useFeatureFlag';

vi.mock('@/api/endpoints', () => ({ fetchFeatureFlags: vi.fn() }));

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return React.createElement(QueryClientProvider, { client }, children);
}

describe('useFeatureFlag', () => {
  it('devolve false enquanto carrega', () => {
    vi.mocked(fetchFeatureFlags).mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useFeatureFlag('trajetoria'), { wrapper });
    expect(result.current).toBe(false);
  });

  it('devolve true quando a flag esta ligada para o chamador', async () => {
    vi.mocked(fetchFeatureFlags).mockResolvedValue({ trajetoria: true });
    const { result } = renderHook(() => useFeatureFlag('trajetoria'), { wrapper });
    await waitFor(() => expect(result.current).toBe(true));
  });

  it('devolve false quando a chave nao veio na resposta', async () => {
    vi.mocked(fetchFeatureFlags).mockResolvedValue({});
    const { result } = renderHook(() => useFeatureFlag('trajetoria'), { wrapper });
    await waitFor(() => expect(vi.mocked(fetchFeatureFlags)).toHaveBeenCalled());
    expect(result.current).toBe(false);
  });
});
```

- [ ] **Step 3: Rodar e confirmar que falha**

Run: `cd ui && npx vitest run src/hooks/useFeatureFlag.test.ts`
Expected: FAIL — módulo não existe.

- [ ] **Step 4: Implementar `fetchFeatureFlags` e o hook**

Em `ui/src/api/endpoints.ts`, seguindo o padrão dos demais fetchers do arquivo:

```ts
export async function fetchFeatureFlags(): Promise<Record<string, boolean>> {
  return apiFetch<Record<string, boolean>>('/settings/feature-flags');
}
```

(Verificar o nome real do helper de request no arquivo antes de escrever — pode ser `api.get` ou similar.)

`ui/src/hooks/useFeatureFlag.ts`:

```ts
import { useQuery } from '@tanstack/react-query';

import { fetchFeatureFlags } from '@/api/endpoints';
import type { FeatureFlagKey } from '@/lib/featureFlags';

/**
 * Estado da flag para o usuário atual.
 *
 * Uma única query compartilhada: N chamadas do hook na mesma tela não viram
 * N requests. Enquanto carrega devolve `false` — é preferível a feature
 * aparecer só depois de resolver a piscar na tela de quem não deveria vê-la.
 */
export function useFeatureFlag(key: FeatureFlagKey): boolean {
  const { data } = useQuery({
    queryKey: ['feature-flags'],
    queryFn: fetchFeatureFlags,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  return data?.[key] === true;
}
```

- [ ] **Step 5: Rodar os testes**

Run: `cd ui && npx vitest run src/hooks/useFeatureFlag.test.ts`
Expected: PASS (3 testes).

- [ ] **Step 6: Commit**

```bash
git add ui/src/lib/featureFlags.ts ui/src/hooks/useFeatureFlag.ts \
        ui/src/hooks/useFeatureFlag.test.ts ui/src/api/endpoints.ts
git commit -m "feat(ff): registro no codigo e hook useFeatureFlag"
```

---

### Task 6: Seção "Funcionalidades" em `/admin/configuracoes`

**Files:**
- Create: `ui/src/components/admin/FeatureFlagsPanel.tsx`
- Modify: `ui/src/pages/AdminSettingsPage.tsx`
- Modify: `ui/src/api/admin.ts` (adicionar `fetchFeatureFlagsAdmin`, `saveFeatureFlag`)
- Test: `ui/src/components/admin/FeatureFlagsPanel.test.tsx`

**Interfaces:**
- Consumes: `FEATURE_FLAGS`, `FeatureFlagKey`, `flagAgeInDays`, `FLAG_AGE_WARNING_DAYS` (Task 5).
- Produces: `<FeatureFlagsPanel />`, sem props.
- `fetchFeatureFlagsAdmin(): Promise<Array<{key: string; state: string; updated_at: string | null}>>`
- `saveFeatureFlag(key: string, state: string): Promise<{key: string; state: string}>`

- [ ] **Step 1: Escrever os testes que falham**

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { fetchFeatureFlagsAdmin, saveFeatureFlag } from '@/api/admin';
import { FeatureFlagsPanel } from './FeatureFlagsPanel';

vi.mock('@/api/admin', () => ({
  fetchFeatureFlagsAdmin: vi.fn(),
  saveFeatureFlag: vi.fn(),
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function renderPanel() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <FeatureFlagsPanel />
    </QueryClientProvider>
  );
}

describe('FeatureFlagsPanel', () => {
  beforeEach(() => vi.clearAllMocks());

  it('lista a flag do registro mesmo sem linha no banco, como off', async () => {
    vi.mocked(fetchFeatureFlagsAdmin).mockResolvedValue([]);
    renderPanel();
    const select = await screen.findByLabelText(/Aba Trajetória/i);
    expect((select as HTMLSelectElement).value).toBe('off');
  });

  it('usa o estado vindo do banco quando existe', async () => {
    vi.mocked(fetchFeatureFlagsAdmin).mockResolvedValue([
      { key: 'trajetoria', state: 'admins', updated_at: null },
    ]);
    renderPanel();
    const select = await screen.findByLabelText(/Aba Trajetória/i);
    expect((select as HTMLSelectElement).value).toBe('admins');
  });

  it('NAO lista linha do banco que nao esta no registro do codigo', async () => {
    vi.mocked(fetchFeatureFlagsAdmin).mockResolvedValue([
      { key: 'trajetoria', state: 'off', updated_at: null },
      { key: 'flag_removida_do_codigo', state: 'all', updated_at: null },
    ]);
    renderPanel();
    await screen.findByLabelText(/Aba Trajetória/i);
    expect(screen.queryByText(/flag_removida_do_codigo/i)).not.toBeInTheDocument();
  });

  it('salva ao trocar o estado', async () => {
    vi.mocked(fetchFeatureFlagsAdmin).mockResolvedValue([]);
    vi.mocked(saveFeatureFlag).mockResolvedValue({ key: 'trajetoria', state: 'all' });
    renderPanel();
    const select = await screen.findByLabelText(/Aba Trajetória/i);
    fireEvent.change(select, { target: { value: 'all' } });
    await waitFor(() =>
      expect(vi.mocked(saveFeatureFlag)).toHaveBeenCalledWith('trajetoria', 'all')
    );
  });
});
```

O terceiro teste é o que trava a propriedade central do desenho: flag removida do código some do controle.

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `cd ui && npx vitest run src/components/admin/FeatureFlagsPanel.test.tsx`
Expected: FAIL — componente não existe.

- [ ] **Step 3: Implementar o painel**

`ui/src/components/admin/FeatureFlagsPanel.tsx`, no estilo visual do `AdminSettingsPage` (classes `mp-card`, cores `#383838`/`#090909`):

```tsx
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2 } from 'lucide-react';
import { toast } from 'sonner';

import { fetchFeatureFlagsAdmin, saveFeatureFlag } from '@/api/admin';
import {
  FEATURE_FLAGS,
  FLAG_AGE_WARNING_DAYS,
  flagAgeInDays,
  type FeatureFlagKey,
} from '@/lib/featureFlags';

const ESTADOS = [
  { value: 'off', label: 'Desativado' },
  { value: 'admins', label: 'Só para admins' },
  { value: 'all', label: 'Todos' },
] as const;

export function FeatureFlagsPanel() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'feature-flags'],
    queryFn: fetchFeatureFlagsAdmin,
    retry: false,
  });

  const mutation = useMutation({
    mutationFn: ({ key, state }: { key: string; state: string }) =>
      saveFeatureFlag(key, state),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['admin', 'feature-flags'] });
      // A UI do app lê a versão resolvida; invalidar evita estado velho.
      void queryClient.invalidateQueries({ queryKey: ['feature-flags'] });
      toast.success('Funcionalidade atualizada.');
    },
    onError: () => toast.error('Não foi possível salvar. Tente novamente.'),
  });

  // Itera sobre o REGISTRO, nunca sobre a resposta do banco: é isso que faz
  // uma flag removida do código sumir deste controle sozinha.
  const estadoPorChave = new Map((data ?? []).map((f) => [f.key, f.state]));
  const chaves = Object.keys(FEATURE_FLAGS) as FeatureFlagKey[];

  return (
    <section aria-label="Funcionalidades" className="flex flex-col gap-4">
      <div>
        <h2 className="text-[24px] font-bold leading-none text-[#090909]">
          Funcionalidades
        </h2>
        <p className="mt-1 text-[14px] text-[#383838]/70">
          Valem na hora, sem redeploy. Controlam apenas a exibição na
          interface — os dados seguem disponíveis na API.
        </p>
      </div>

      {isLoading ? (
        <div className="mp-card flex items-center gap-2 bg-white p-6 text-[#383838]/60">
          <Loader2 className="h-5 w-5 animate-spin" aria-hidden />
          Carregando…
        </div>
      ) : (
        <div className="mp-card flex flex-col divide-y divide-[#eee] bg-white">
          {chaves.map((key) => {
            const { label, since } = FEATURE_FLAGS[key];
            const idade = flagAgeInDays(since);
            const velha = idade > FLAG_AGE_WARNING_DAYS;
            return (
              <div
                key={key}
                className="flex flex-col gap-2 p-4 sm:flex-row sm:items-center sm:justify-between"
              >
                <div>
                  <label
                    htmlFor={`ff-${key}`}
                    className="text-[15px] font-semibold text-[#090909]"
                  >
                    {label}
                  </label>
                  <p
                    className={[
                      'text-[13px]',
                      velha ? 'font-semibold text-[#b45309]' : 'text-[#383838]/60',
                    ].join(' ')}
                  >
                    criada há {idade} dias
                    {velha ? ' — candidata a remoção do código' : ''}
                  </p>
                </div>
                <select
                  id={`ff-${key}`}
                  value={estadoPorChave.get(key) ?? 'off'}
                  disabled={mutation.isPending}
                  onChange={(e) =>
                    mutation.mutate({ key, state: e.target.value })
                  }
                  className="rounded-full border border-[#ddd] px-4 py-2 text-[13px] font-semibold text-[#090909]"
                >
                  {ESTADOS.map((op) => (
                    <option key={op.value} value={op.value}>
                      {op.label}
                    </option>
                  ))}
                </select>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 4: Adicionar os fetchers em `ui/src/api/admin.ts`**

Seguindo o padrão dos existentes (`fetchWordCloudTerms`/`saveWordCloudTerms`):

```ts
export interface FeatureFlagAdminOut {
  key: string;
  state: string;
  updated_at: string | null;
}

export async function fetchFeatureFlagsAdmin(): Promise<FeatureFlagAdminOut[]> {
  return adminFetch<FeatureFlagAdminOut[]>('/admin/settings/feature-flags');
}

export async function saveFeatureFlag(
  key: string,
  state: string
): Promise<FeatureFlagAdminOut> {
  return adminFetch<FeatureFlagAdminOut>(
    `/admin/settings/feature-flags/${encodeURIComponent(key)}`,
    { method: 'PUT', body: JSON.stringify({ state }) }
  );
}
```

(Conferir o nome real do helper — `adminFetch` ou equivalente — antes de escrever.)

- [ ] **Step 5: Montar no `AdminSettingsPage`**

Importar e renderizar `<FeatureFlagsPanel />` logo abaixo do cabeçalho "Configurações gerais" e acima do bloco da nuvem de palavras. O painel gerencia a própria query, então não depende do `isLoading` da nuvem.

- [ ] **Step 6: Rodar os testes**

Run: `cd ui && npx vitest run src/components/admin/FeatureFlagsPanel.test.tsx src/pages/AdminSettingsPage.test.tsx`
Expected: PASS. Se `AdminSettingsPage.test.tsx` quebrar por causa do novo painel, adicionar o mock de `@/api/admin` para as duas funções novas.

- [ ] **Step 7: Commit**

```bash
git add ui/src/components/admin/FeatureFlagsPanel.tsx \
        ui/src/components/admin/FeatureFlagsPanel.test.tsx \
        ui/src/pages/AdminSettingsPage.tsx ui/src/api/admin.ts
git commit -m "feat(ff): secao Funcionalidades em /admin/configuracoes"
```

---

### Task 7: Migrar a Trajetória para a flag

**Files:**
- Modify: `ui/src/pages/ParlamentarDashboard.tsx:66-68,235-268`
- Modify: `ui/src/pages/ParlamentarDashboard.trajetoria.test.tsx`

**Interfaces:**
- Consumes: `useFeatureFlag` (Task 5).

- [ ] **Step 1: Adaptar o teste existente (falhando)**

Trocar o mock de `useIsAdmin` por `useFeatureFlag` e reescrever o `describe`:

```tsx
const flagState = { trajetoria: false };

vi.mock('@/hooks/useFeatureFlag', () => ({
  useFeatureFlag: (key: 'trajetoria') => flagState[key],
}));
```

E os casos:

```tsx
describe('gate da aba Trajetória', () => {
  beforeEach(() => {
    flagState.trajetoria = false;
  });

  it('flag desligada esconde a aba', async () => {
    renderPage();
    await screen.findAllByText(/VOTAÇÕES/i);
    expect(screen.queryByText(/TRAJETÓRIA/i)).not.toBeInTheDocument();
  });

  it('flag ligada mostra a aba', async () => {
    flagState.trajetoria = true;
    renderPage();
    await screen.findAllByText(/VOTAÇÕES/i);
    expect(screen.getByText(/TRAJETÓRIA/i)).toBeInTheDocument();
  });
});
```

Manter o mock de `@/hooks/useIsAdmin` no arquivo — outros componentes da árvore (Header) ainda o usam.

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `cd ui && npx vitest run src/pages/ParlamentarDashboard.trajetoria.test.tsx`
Expected: FAIL no caso "flag desligada esconde a aba" — o componente ainda usa `isAdmin`, que o mock não controla mais.

- [ ] **Step 3: Trocar o gate por um portão único**

Em `ParlamentarDashboard.tsx`:

1. Trocar o import e a chamada:
```ts
import { useFeatureFlag } from '@/hooks/useFeatureFlag';
// ...
// Feature flag da aba Trajetória: gerenciada em /admin/configuracoes.
const trajetoriaOn = useFeatureFlag('trajetoria');
```
Remover `useIsAdmin` deste arquivo (o hook continua existindo, usado por `App.tsx` e `Header.tsx` — esses **não** mudam).

2. Substituir as duas condicionais `{isAdmin && (...)}` (linhas 241 e 262) por uma lista derivada, declarada antes do `return`:

```tsx
const abas = [
  { value: 'votacoes', label: 'VOTAÇÕES', content: <VotacoesTable parliamentarianId={numericId} />, className: 'mt-0 p-6 pt-4 h-[500px]' },
  { value: 'proposicoes', label: 'PROPOSIÇÕES', content: <ProposicoesTable parliamentarianId={id} />, className: 'mt-0 p-6 pt-4' },
  { value: 'taquigraficas', label: 'TAQUIGRÁFICAS', content: <TaquigraficasTable parliamentarianId={numericId} />, className: 'mt-0 p-6 pt-4 h-[500px]' },
  { value: 'emendas', label: 'EMENDAS', content: <EmendasTable parliamentarianId={numericId} year={emendasYear} />, className: 'mt-0 p-6 pt-4 h-[500px]' },
  ...(trajetoriaOn
    ? [{ value: 'trajetoria', label: 'TRAJETÓRIA', content: <TrajetoriaTab parliamentarianId={numericId} />, className: 'mt-0 p-6 pt-4 h-[500px]' }]
    : []),
];
```

E no JSX:

```tsx
<TabsList>
  {abas.map((aba) => (
    <TabsTrigger key={aba.value} value={aba.value} className={parlamentarSectionTabTriggerClass}>
      {aba.label}
    </TabsTrigger>
  ))}
</TabsList>
...
{abas.map((aba) => (
  <TabsContent key={aba.value} value={aba.value} className={aba.className}>
    {aba.content}
  </TabsContent>
))}
```

Conferir os `label` e `className` reais de cada aba no arquivo antes de escrever — os acima vieram da leitura das linhas 235-268 e precisam bater exatamente, inclusive o texto visível.

- [ ] **Step 4: Rodar os testes**

Run: `cd ui && npx vitest run src/pages/`
Expected: PASS, incluindo os demais testes de `ParlamentarDashboard`.

- [ ] **Step 5: Verificar que não sobrou `isAdmin` como feature flag**

Run: `grep -n "isAdmin" ui/src/pages/ParlamentarDashboard.tsx`
Expected: nenhuma ocorrência.

- [ ] **Step 6: Commit**

```bash
git add ui/src/pages/ParlamentarDashboard.tsx ui/src/pages/ParlamentarDashboard.trajetoria.test.tsx
git commit -m "refactor(trajetoria): gate isAdmin em 2 pontos vira flag em 1"
```

---

### Task 8: Verificação final e PR

- [ ] **Step 1: Suíte completa**

Run: `python -m pytest api/tests/ -q && cd ui && npx vitest run && npx tsc --noEmit`
Expected: tudo verde.

- [ ] **Step 2: Provar o procedimento de remoção (a seco, sem commitar)**

Apagar temporariamente a entrada `trajetoria` de `FEATURE_FLAGS` e rodar:

Run: `cd ui && npx tsc --noEmit`
Expected: erro apontando `useFeatureFlag('trajetoria')` em `ParlamentarDashboard.tsx` e nos testes — provando que o compilador é o checklist de remoção.

Restaurar a entrada (`git checkout ui/src/lib/featureFlags.ts`) e confirmar `tsc` verde.

- [ ] **Step 3: Abrir a PR**

```bash
git push -u origin feat/feature-flags
gh pr create --base main --title "feat(ff): feature flags gerenciáveis pelo admin (off/admins/todos)" --body "..."
```

Corpo da PR: o que o mecanismo faz, o procedimento de remoção, a nota de que é controle de apresentação e não de segurança, e o link para o spec.

---

## Self-Review

**Cobertura do spec:** tabela + seed (T1), `resolve_ghost_admin` (T2), service com as três funções (T3), três rotas (T4), registro + hook + `since` (T5), painel iterando o registro + idade (T6), migração da Trajetória para portão único (T7), procedimento de remoção provado (T8). As três regras de uso entram no docstring em T5.

**Placeholders:** nenhum. Os três pontos em que o plano manda *conferir antes de escrever* (nome do helper de fetch em `endpoints.ts` e `admin.ts`, prefixo do `api_router`, labels reais das abas) são verificações contra o código existente, não lacunas de decisão.

**Consistência de tipos:** `FeatureFlagKey` (T5) é consumido em T6 e T7; `get_states`/`resolve_for`/`set_state` (T3) são consumidos em T4 com as mesmas assinaturas; `fetchFeatureFlags` (público, `Record<string, boolean>`) e `fetchFeatureFlagsAdmin` (admin, array com `state`) são deliberadamente distintos e não se confundem.
