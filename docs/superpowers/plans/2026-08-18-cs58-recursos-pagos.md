# CS-58 — Recursos pagos (cadeado + prévia desfocada) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recursos pagos visíveis com cadeado e prévia desfocada, com modo por
plano configurável no admin e gate de verdade no backend.

**Architecture:** `feature_flag_tier` ganha coluna `mode`
(`liberado`/`cadeado`; ausência = oculto). A resolução passa de booleano para
tri-valor (`liberada`/`bloqueada`/`oculta`). Dependency FastAPI
`feature_access(key)` protege as 5 rotas de dado (truncagem servidor-side na
prévia). Front ganha `useFeatureAccess`, overlay de blur com CTA e preview de
admin via header `X-Feature-Preview`.

**Tech Stack:** FastAPI + SQLAlchemy + alembic (migrations em
`mamute_scrappers/migrations`), React + TanStack Query + vitest.

**Spec:** `docs/superpowers/specs/2026-08-18-cs58-recursos-pagos-design.md`

## Global Constraints

- Branch: `feat/cs58-recursos-pagos` (já criada a partir de `origin/main`).
- Migration nova: `down_revision = "c3d4e5f6a9b0"` (head atual).
- Modos no banco: `'liberado' | 'cadeado'`; valores resolvidos:
  `'liberada' | 'bloqueada' | 'oculta'`. N de linhas da prévia: **3**.
- Deploy não pode mudar comportamento: seed da flag `emendas` em `all` +
  `mode='liberado'` para todos os tiers ativos (a aba EMENDAS hoje é aberta).
- Modelos duplicados: toda mudança em `api/db/models/feature_flag.py` se
  espelha em `mamute_scrappers/db/models/feature_flag.py`.
- Testes API: `cd api && python -m pytest tests/ -q` (SQLite in-memory, DDL
  cru, dependency_overrides — padrão de `test_feature_flags.py`).
- Testes front: `cd ui && npx vitest run <arquivo>`; type-check:
  `npx tsc -p tsconfig.app.json --noEmit` (a main tem ~17 erros
  pré-existentes de mocks — comparar contagem, não esperar zero).
- Textos de UI em pt-BR, código comentado em pt-BR como o entorno.

---

### Task 1: Migration + modelos (coluna `mode` e seed de `emendas`)

**Files:**
- Create: `mamute_scrappers/migrations/versions/d4e5f6a7b8c9_add_feature_flag_tier_mode.py`
- Modify: `api/db/models/feature_flag.py`
- Modify: `mamute_scrappers/db/models/feature_flag.py` (mesmo conteúdo)

**Interfaces:**
- Produces: `FeatureFlagTier.mode` (Text, not null, default `'liberado'`),
  constantes `MODE_LIBERADO = "liberado"`, `MODE_CADEADO = "cadeado"`,
  `VALID_MODES = frozenset({...})` exportadas de ambos os módulos de modelo.

- [ ] **Step 1: Migration**

```python
"""add feature_flag_tier mode

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a9b0
Create Date: 2026-08-18

CS-58: o vinculo plano x feature deixa de ser binario (linha presente =
liberado) e ganha modo: 'liberado' (acesso pleno) ou 'cadeado' (entrada
visivel + previa desfocada). Ausencia de linha segue valendo oculto.

Seed de 'emendas': a aba EMENDAS hoje e aberta a todos; sem o seed, criar a
flag a esconderia no deploy. 'all' + linha 'liberado' em todo tier ativo
preserva o comportamento atual ate o admin configurar o cadeado.
"""

from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a9b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "feature_flag_tier",
        sa.Column("mode", sa.Text(), nullable=False, server_default="liberado"),
    )
    op.create_check_constraint(
        "ck_feature_flag_tier_mode",
        "feature_flag_tier",
        "mode in ('liberado', 'cadeado')",
    )
    op.execute(
        "insert into feature_flag (key, state) values ('emendas', 'all') "
        "on conflict (key) do nothing"
    )
    op.execute(
        "insert into feature_flag_tier (flag_key, tier_id, mode) "
        "select 'emendas', id, 'liberado' from tiers where deleted_at is null "
        "on conflict do nothing"
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_feature_flag_tier_mode", "feature_flag_tier", type_="check"
    )
    op.drop_column("feature_flag_tier", "mode")
    op.execute("delete from feature_flag_tier where flag_key = 'emendas'")
    op.execute("delete from feature_flag where key = 'emendas'")
```

- [ ] **Step 2: Modelo em `api/db/models/feature_flag.py`**

Adicionar após `VALID_STATES`:

```python
MODE_LIBERADO = "liberado"
MODE_CADEADO = "cadeado"
VALID_MODES = frozenset({MODE_LIBERADO, MODE_CADEADO})
```

Em `FeatureFlagTier`, adicionar coluna e constraint (e atualizar o docstring
do PONTO DE EXTENSAO, que agora foi construído):

```python
    __table_args__ = (
        CheckConstraint(
            "mode in ('liberado', 'cadeado')",
            name="ck_feature_flag_tier_mode",
        ),
    )
    ...
    mode = Column(Text, nullable=False, server_default=MODE_LIBERADO)
```

Acrescentar `MODE_LIBERADO`, `MODE_CADEADO`, `VALID_MODES` ao `__all__`.
Espelhar o arquivo inteiro em `mamute_scrappers/db/models/feature_flag.py`.

- [ ] **Step 3: Rodar os testes atuais para ver o que quebra**

Run: `cd api && python -m pytest tests/test_feature_flags.py -q`
Expected: PASS (a coluna nova tem default; o DDL cru dos testes ainda não a
tem — os serviços só a usam a partir da Task 2).

- [ ] **Step 4: Commit**

```bash
git add mamute_scrappers/migrations api/db/models/feature_flag.py mamute_scrappers/db/models/feature_flag.py
git commit -m "feat(cs58): coluna mode em feature_flag_tier + seed da flag emendas"
```

---

### Task 2: Serviços — resolução tri-valorada e escrita com modo

**Files:**
- Modify: `api/services/feature_flags.py`
- Modify: `api/tests/test_feature_flags.py`

**Interfaces:**
- Produces:
  - `ACCESS_LIBERADA = "liberada"`, `ACCESS_BLOQUEADA = "bloqueada"`,
    `ACCESS_OCULTA = "oculta"` (constantes exportadas);
  - `enabled_flags_for_tier(db, tier_id) -> dict[str, str]` (chave → modo);
  - `resolve_for(db, is_admin, modos: Mapping[str, str] | None) -> dict[str, str]`
    (chave → valor resolvido);
  - `set_tier_flags(db, tier_id, modos: Mapping[str, str]) -> dict[str, str]`;
  - `count_tiers_enabled(db) -> dict[str, dict[str, int]]`
    (chave → `{"liberado": n, "cadeado": n}`).
- Consumes: `MODE_LIBERADO`, `MODE_CADEADO`, `VALID_MODES` da Task 1.

- [ ] **Step 1: Atualizar o DDL dos testes e escrever os testes novos (falhando)**

Em `api/tests/test_feature_flags.py`, no `_session_com_flags`, adicionar a
coluna ao DDL de `feature_flag_tier`:

```sql
create table feature_flag_tier (
    flag_key text not null,
    tier_id integer not null,
    mode text not null default 'liberado',
    created_at datetime not null default current_timestamp,
    primary key (flag_key, tier_id)
)
```

Atualizar TODOS os call sites de `resolve_for` no arquivo: o parâmetro
`liberadas={"a"}` vira `modos={"a": "liberado"}` e os valores esperados viram
strings. Exemplos das asserções novas (substituem as booleanas):

```python
def test_all_sem_plano_fica_oculta():
    db = _session_com_flags([("a", "all"), ("b", "admins"), ("c", "off")])
    assert resolve_for(db, is_admin=False, modos={}) == {
        "a": "oculta",
        "b": "oculta",
        "c": "oculta",
    }


def test_all_com_modo_liberado_resolve_liberada():
    db = _session_com_flags([("a", "all")])
    assert resolve_for(db, is_admin=False, modos={"a": "liberado"}) == {
        "a": "liberada"
    }


def test_all_com_modo_cadeado_resolve_bloqueada():
    """O cerne da CS-58: plano sem o recurso, mas com vitrine."""
    db = _session_com_flags([("a", "all")])
    assert resolve_for(db, is_admin=False, modos={"a": "cadeado"}) == {
        "a": "bloqueada"
    }


def test_admins_nao_vira_cadeado_para_nao_admin():
    """Recurso nao lancado nao vira vitrine: cadeado so existe em `all`."""
    db = _session_com_flags([("b", "admins")])
    assert resolve_for(db, is_admin=False, modos={"b": "cadeado"}) == {
        "b": "oculta"
    }


def test_admin_resolve_liberada_para_tudo_menos_off():
    db = _session_com_flags([("a", "all"), ("b", "admins"), ("c", "off")])
    assert resolve_for(db, is_admin=True, modos={}) == {
        "a": "liberada",
        "b": "liberada",
        "c": "oculta",
    }


def test_enabled_flags_for_tier_devolve_modos():
    db = _session_com_flags([("a", "all"), ("b", "all")])
    db.execute(text(
        "insert into tiers (id, tier_name_debug, product_id) values (1, 't', 'p1')"
    ))
    db.execute(text(
        "insert into feature_flag_tier (flag_key, tier_id, mode) "
        "values ('a', 1, 'liberado'), ('b', 1, 'cadeado')"
    ))
    from api.services.feature_flags import enabled_flags_for_tier
    assert enabled_flags_for_tier(db, 1) == {"a": "liberado", "b": "cadeado"}


def test_set_tier_flags_grava_e_substitui_modos():
    db = _session_com_flags([])
    db.execute(text(
        "insert into tiers (id, tier_name_debug, product_id) values (1, 't', 'p1')"
    ))
    from api.services.feature_flags import enabled_flags_for_tier, set_tier_flags
    set_tier_flags(db, 1, {"a": "liberado", "b": "cadeado"})
    assert enabled_flags_for_tier(db, 1) == {"a": "liberado", "b": "cadeado"}
    set_tier_flags(db, 1, {"b": "liberado"})
    assert enabled_flags_for_tier(db, 1) == {"b": "liberado"}


def test_set_tier_flags_recusa_modo_invalido():
    db = _session_com_flags([])
    from api.services.feature_flags import set_tier_flags
    with pytest.raises(ValueError):
        set_tier_flags(db, 1, {"a": "gratis"})
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd api && python -m pytest tests/test_feature_flags.py -q`
Expected: FAIL (assinaturas/valores antigos).

- [ ] **Step 3: Implementar em `api/services/feature_flags.py`**

Importar também `MODE_CADEADO`, `MODE_LIBERADO`, `VALID_MODES` (nos dois
ramos do try/except de import). Adicionar constantes e reescrever as quatro
funções (docstrings seguem o tom das atuais; o PONTO DE EXTENSAO do
`enabled_flags_for_tier` sai, porque foi construído):

```python
ACCESS_LIBERADA = "liberada"
ACCESS_BLOQUEADA = "bloqueada"
ACCESS_OCULTA = "oculta"


def resolve_for(
    db: Session,
    is_admin: bool,
    modos: Mapping[str, str] | None = None,
) -> dict[str, str]:
    do_plano = dict(modos or {})
    resolvido: dict[str, str] = {}
    for key, state in get_states(db).items():
        if is_admin:
            resolvido[key] = (
                ACCESS_OCULTA if state == STATE_OFF else ACCESS_LIBERADA
            )
        elif state == STATE_ALL and do_plano.get(key) == MODE_LIBERADO:
            resolvido[key] = ACCESS_LIBERADA
        elif state == STATE_ALL and do_plano.get(key) == MODE_CADEADO:
            resolvido[key] = ACCESS_BLOQUEADA
        else:
            resolvido[key] = ACCESS_OCULTA
    return resolvido


def enabled_flags_for_tier(db: Session, tier_id: int | None) -> dict[str, str]:
    if tier_id is None:
        return {}
    linhas = db.execute(
        select(FeatureFlagTier.flag_key, FeatureFlagTier.mode).where(
            FeatureFlagTier.tier_id == tier_id
        )
    ).all()
    return {key: mode for key, mode in linhas}


def set_tier_flags(
    db: Session, tier_id: int, modos: Mapping[str, str]
) -> dict[str, str]:
    desejadas = {str(k): str(v) for k, v in (modos or {}).items()}
    invalidos = set(desejadas.values()) - VALID_MODES
    if invalidos:
        raise ValueError(f"modo invalido: {sorted(invalidos)!r}")

    atuais = {
        linha.flag_key: linha
        for linha in db.execute(
            select(FeatureFlagTier).where(FeatureFlagTier.tier_id == tier_id)
        ).scalars()
    }
    for key, linha in atuais.items():
        if key not in desejadas:
            db.delete(linha)
        elif linha.mode != desejadas[key]:
            linha.mode = desejadas[key]
    for key in set(desejadas) - set(atuais):
        db.add(FeatureFlagTier(flag_key=key, tier_id=tier_id, mode=desejadas[key]))
    db.flush()
    return dict(sorted(desejadas.items()))


def count_tiers_enabled(db: Session) -> dict[str, dict[str, int]]:
    linhas = db.execute(
        select(
            FeatureFlagTier.flag_key,
            FeatureFlagTier.mode,
            func.count(FeatureFlagTier.tier_id),
        )
        .join(Tiers, Tiers.id == FeatureFlagTier.tier_id)
        .where(Tiers.deleted_at.is_(None))
        .group_by(FeatureFlagTier.flag_key, FeatureFlagTier.mode)
    ).all()
    contagem: dict[str, dict[str, int]] = {}
    for key, mode, total in linhas:
        contagem.setdefault(key, {}).update({mode: total})
    return contagem
```

(`Mapping` entra no import de `collections.abc`; o import local de `Tiers`
em `count_tiers_enabled` permanece como está.)

- [ ] **Step 4: Rodar até os testes do serviço passarem**

Run: `cd api && python -m pytest tests/test_feature_flags.py -q`
Expected: os testes de resolução/serviço PASSAM; os de ROTA ainda podem
falhar (rotas mudam nas Tasks 3-4 — se falharem, seguir adiante, as Tasks
3-4 os cobrem).

- [ ] **Step 5: Commit**

```bash
git add api/services/feature_flags.py api/tests/test_feature_flags.py
git commit -m "feat(cs58): resolucao tri-valorada (liberada/bloqueada/oculta) nos servicos"
```

---

### Task 3: Rota pública `/settings/feature-flags` devolve o tri-valor

**Files:**
- Modify: `api/routers/settings.py:61-82`
- Modify: `api/tests/test_feature_flags.py` (testes de rota pública)

**Interfaces:**
- Produces: `GET /api/settings/feature-flags` → `dict[str, str]` com valores
  `'liberada' | 'bloqueada' | 'oculta'`.
- Consumes: `resolve_for(db, is_admin, modos)` da Task 2.

- [ ] **Step 1: Atualizar os testes de rota pública (falhando)**

Em `test_rota_publica_resolve_pelo_plano_do_chamador` e vizinhos, o JSON
esperado vira strings. Adicionar um caso de cadeado:

```python
def test_rota_publica_devolve_bloqueada_para_plano_com_cadeado():
    try:
        client = _client([("a", "all")], plano_com={"a": "cadeado"})
        r = client.get("/api/settings/feature-flags")
        assert r.status_code == 200
        assert r.json() == {"a": "bloqueada"}
    finally:
        main.app.dependency_overrides.clear()
```

(Adaptar o helper `_client` do arquivo para aceitar `plano_com:
dict[str, str]` e semear `tiers`/`projetos`/`feature_flag_tier` com modo —
hoje ele já semeia o vínculo; é trocar a lista por dict.)

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd api && python -m pytest tests/test_feature_flags.py -q -k rota_publica`
Expected: FAIL.

- [ ] **Step 3: Implementar**

Em `read_feature_flags` (settings.py), o retorno vira `dict[str, str]` e o
parâmetro muda de nome:

```python
    return resolve_for(
        db,
        is_admin=is_admin,
        modos=enabled_flags_for_tier(db, tier_id),
    )
```

Atualizar a anotação de retorno para `dict[str, str]` e o docstring (o
trecho "os endpoints de dado seguem abertos — não é fronteira de segurança"
sai: a Task 6 torna isso falso; registrar que o gate mora em
`api/feature_gate.py`).

- [ ] **Step 4: Rodar e ver passar**

Run: `cd api && python -m pytest tests/test_feature_flags.py -q`
Expected: PASS (rotas admin ainda na Task 4; se algum teste de admin falhar
por contrato, ele é atualizado lá).

- [ ] **Step 5: Commit**

```bash
git add api/routers/settings.py api/tests/test_feature_flags.py
git commit -m "feat(cs58): /settings/feature-flags devolve liberada/bloqueada/oculta"
```

---

### Task 4: Rotas admin — tier features com modo e contagem por modo

**Files:**
- Modify: `api/routers/admin.py:495-616`
- Modify: `api/tests/test_feature_flags.py` (testes das rotas admin)

**Interfaces:**
- Produces:
  - `GET/PUT /api/admin/tiers/{id}/features` com
    `{"tier_id": int, "features": {"<key>": "liberado"|"cadeado"}}`;
  - `FeatureFlagOut` com `tiers_liberados: int`, `tiers_cadeado: int`
    (substituem `tiers_ligados`), `tiers_total: int` mantido.
- Consumes: `set_tier_flags(db, tier_id, modos)` e
  `count_tiers_enabled` (dict por modo) da Task 2.

- [ ] **Step 1: Atualizar/escrever testes das rotas admin (falhando)**

No mesmo arquivo de testes: o PUT de tier features envia
`{"features": {"a": "cadeado"}}` e espera o mesmo shape de volta; o GET
devolve dict; `read_feature_flags_admin` devolve `tiers_liberados`/
`tiers_cadeado`. Exemplo:

```python
def test_admin_tier_features_com_modo():
    try:
        client = _client([("a", "all")], admin=True, com_tier=1)
        r = client.put(
            "/api/admin/tiers/1/features",
            json={"features": {"a": "cadeado"}},
        )
        assert r.status_code == 200
        assert r.json() == {"tier_id": 1, "features": {"a": "cadeado"}}

        r = client.get("/api/admin/settings/feature-flags")
        linha = next(f for f in r.json() if f["key"] == "a")
        assert linha["tiers_liberados"] == 0
        assert linha["tiers_cadeado"] == 1
    finally:
        main.app.dependency_overrides.clear()


def test_admin_tier_features_recusa_modo_invalido():
    try:
        client = _client([("a", "all")], admin=True, com_tier=1)
        r = client.put(
            "/api/admin/tiers/1/features",
            json={"features": {"a": "gratis"}},
        )
        assert r.status_code == 422
    finally:
        main.app.dependency_overrides.clear()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd api && python -m pytest tests/test_feature_flags.py -q -k admin`
Expected: FAIL.

- [ ] **Step 3: Implementar em admin.py**

```python
class FeatureFlagOut(BaseModel):
    key: str
    state: str
    updated_at: Optional[datetime] = None
    # Quantos planos ativos liberam / mostram cadeado. Denuncia o caso
    # silencioso: flag em `all` sem nenhum plano nao aparece para ninguem.
    tiers_liberados: int = 0
    tiers_cadeado: int = 0
    tiers_total: int = 0


class TierFeaturesUpdate(BaseModel):
    """Mapa completo recurso -> modo do plano. Salvar substitui tudo."""

    features: dict[str, Literal["liberado", "cadeado"]] = Field(
        default_factory=dict
    )


class TierFeaturesOut(BaseModel):
    tier_id: int
    features: dict[str, str]
```

(`Literal` já vem de `typing` no import do arquivo; conferir e acrescentar
se faltar.) Em `read_feature_flags_admin`:

```python
    ligados = count_feature_flag_tiers(db)
    ...
        {
            "key": key,
            "state": state,
            "updated_at": quando.get(key),
            "tiers_liberados": ligados.get(key, {}).get("liberado", 0),
            "tiers_cadeado": ligados.get(key, {}).get("cadeado", 0),
            "tiers_total": total,
        }
```

`read_tier_features` devolve
`{"tier_id": tier_id, "features": enabled_flags_for_tier(db, tier_id)}`
(sem `sorted` — agora é dict). `update_tier_features` passa
`payload.features` direto a `set_tier_flags` e loga
`before/after` com os dicts.

- [ ] **Step 4: Rodar a suíte inteira da API**

Run: `cd api && python -m pytest tests/ -q`
Expected: PASS (nada além de feature flags usa esses contratos).

- [ ] **Step 5: Commit**

```bash
git add api/routers/admin.py api/tests/test_feature_flags.py
git commit -m "feat(cs58): modo por plano nas rotas admin de tier features"
```

---

### Task 5: `feature_gate.py` — a dependency que é a fronteira de segurança

**Files:**
- Create: `api/feature_gate.py`
- Create: `api/tests/test_feature_gate.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) FeatureAccess(full: bool)`;
  - `PREVIEW_ROWS = 3`;
  - `feature_access(key: str)` → dependency FastAPI;
  - instâncias module-level `emendas_access = feature_access("emendas")` e
    `trajetoria_access = feature_access("trajetoria")` — são elas que as
    rotas usam em `Depends(...)`, e são elas que os testes de rota
    sobrescrevem por identidade em `dependency_overrides`.
- Consumes: `resolve_ghost_admin` (security), `resolve_for`,
  `enabled_flags_for_tier`, `tier_id_for_email`, `ACCESS_*` (services).

- [ ] **Step 1: Escrever os testes (falhando)**

`api/tests/test_feature_gate.py`, testando a dependency direto (sem app),
com o mesmo `_session_com_flags` importado de `test_feature_flags`:

```python
"""Gate de plano nas rotas de dado (CS-58).

O desfoque no front e vitrine; a fronteira e esta dependency.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from api import feature_gate
from api.feature_gate import FeatureAccess, feature_access
from api.tests.test_feature_flags import _session_com_flags


def _request(email: str | None = "u@x.com") -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(token_email=email))


def _db_com_plano(modo: str | None):
    db = _session_com_flags([("emendas", "all")])
    db.execute(text(
        "insert into tiers (id, tier_name_debug, product_id) values (1, 't', 'p1')"
    ))
    db.execute(text(
        "insert into projetos (id, nome, email, tier_id) "
        "values (1, 'p', 'u@x.com', 1)"
    ))
    if modo is not None:
        db.execute(text(
            "insert into feature_flag_tier (flag_key, tier_id, mode) "
            f"values ('emendas', 1, '{modo}')"
        ))
    return db


def _resolver(dep, db, *, admin=False, preview=None):
    """Chama a dependency interna como funcao pura."""
    return dep(
        request=_request(),
        authorization=None,
        x_feature_preview=preview,
        db=db,
        _admin_resolvido=admin,  # ver Step 3: hook de teste explicito
    )


def test_plano_liberado_da_acesso_pleno():
    acesso = _resolver(feature_access("emendas"), _db_com_plano("liberado"))
    assert acesso == FeatureAccess(full=True)


def test_plano_cadeado_da_previa():
    acesso = _resolver(feature_access("emendas"), _db_com_plano("cadeado"))
    assert acesso == FeatureAccess(full=False)


def test_sem_linha_no_plano_e_403():
    with pytest.raises(HTTPException) as exc:
        _resolver(feature_access("emendas"), _db_com_plano(None))
    assert exc.value.status_code == 403


def test_flag_off_e_403_mesmo_com_linha():
    db = _db_com_plano("liberado")
    db.execute(text("update feature_flag set state = 'off'"))
    with pytest.raises(HTTPException) as exc:
        _resolver(feature_access("emendas"), db)
    assert exc.value.status_code == 403


def test_admin_e_sempre_pleno():
    acesso = _resolver(
        feature_access("emendas"), _db_com_plano(None), admin=True
    )
    assert acesso == FeatureAccess(full=True)


def test_admin_com_header_preview_ve_a_previa():
    acesso = _resolver(
        feature_access("emendas"),
        _db_com_plano(None),
        admin=True,
        preview="emendas, trajetoria",
    )
    assert acesso == FeatureAccess(full=False)


def test_header_preview_sem_admin_e_ignorado():
    """Usuario comum nao ganha nada forjando o header."""
    acesso = _resolver(
        feature_access("emendas"),
        _db_com_plano("liberado"),
        preview="emendas",
    )
    assert acesso == FeatureAccess(full=True)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd api && python -m pytest tests/test_feature_gate.py -q`
Expected: FAIL (módulo não existe).

- [ ] **Step 3: Implementar `api/feature_gate.py`**

```python
"""Gate de plano nas rotas de dado (CS-58).

O desfoque no front e vitrine, nao seguranca: a fronteira e esta dependency.
Uma rota gatada declara `Depends(emendas_access)` e recebe um FeatureAccess:

* `full=True`  — devolve tudo (plano libera, ou admin);
* `full=False` — devolve a PREVIA: no maximo PREVIEW_ROWS linhas, em ordem
  fixa, IGNORANDO filtros e paginacao do cliente — honrar filtro em previa
  vira oraculo de extracao (enumerar o dataset variando o filtro);
* sem acesso   — 403 antes de tocar a rota.

O header `X-Feature-Preview` (lista de chaves separadas por virgula) forca a
previa e so e honrado para admin: e a lente de inspecao do painel, nao um
modo do produto. Para usuario comum ele e ignorado por completo.

A chave passada a `feature_access` tem de existir no registro do front
(`ui/src/lib/featureFlags.ts`) — e o mesmo contrato do resto do sistema de
flags: o registro mora la, o banco so guarda estado.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

try:
    from .dependencies import get_db
    from .security import resolve_ghost_admin
    from .services.feature_flags import (
        ACCESS_BLOQUEADA,
        ACCESS_LIBERADA,
        enabled_flags_for_tier,
        resolve_for,
        tier_id_for_email,
    )
except ImportError:  # execução dentro de api/
    from dependencies import get_db
    from security import resolve_ghost_admin
    from services.feature_flags import (
        ACCESS_BLOQUEADA,
        ACCESS_LIBERADA,
        enabled_flags_for_tier,
        resolve_for,
        tier_id_for_email,
    )

# Tamanho da previa. Pequeno de proposito: e vitrine, nao amostra util.
PREVIEW_ROWS = 3


@dataclass(frozen=True)
class FeatureAccess:
    """Resultado do gate, ja resolvido para quem chamou."""

    full: bool


def _chaves_preview(header: str | None) -> set[str]:
    return {k.strip() for k in (header or "").split(",") if k.strip()}


def feature_access(key: str):
    """Fabrica a dependency de uma chave. As rotas usam as instancias
    module-level (`emendas_access`, `trajetoria_access`): e por identidade
    delas que os testes sobrescrevem o gate em dependency_overrides.
    """

    def dependency(
        request: Request,
        authorization: str | None = Header(default=None),
        x_feature_preview: str | None = Header(default=None),
        db: Session = Depends(get_db),
        _admin_resolvido: bool | None = None,
    ) -> FeatureAccess:
        # `_admin_resolvido` existe para os testes chamarem a funcao pura
        # sem montar token de Ghost; o FastAPI nunca o preenche (nao e
        # parametro declarado de request).
        is_admin = (
            _admin_resolvido
            if _admin_resolvido is not None
            else resolve_ghost_admin(request, authorization) is not None
        )
        if is_admin:
            return FeatureAccess(full=key not in _chaves_preview(x_feature_preview))

        email = getattr(request.state, "token_email", None)
        tier_id = tier_id_for_email(db, email)
        resolvido = resolve_for(
            db, is_admin=False, modos=enabled_flags_for_tier(db, tier_id)
        ).get(key)
        if resolvido == ACCESS_LIBERADA:
            return FeatureAccess(full=True)
        if resolvido == ACCESS_BLOQUEADA:
            return FeatureAccess(full=False)
        raise HTTPException(
            status_code=403, detail="Recurso não disponível no seu plano."
        )

    return dependency


emendas_access = feature_access("emendas")
trajetoria_access = feature_access("trajetoria")

__all__ = [
    "PREVIEW_ROWS",
    "FeatureAccess",
    "feature_access",
    "emendas_access",
    "trajetoria_access",
]
```

Nota para o teste: `_admin_resolvido: bool | None = None` sem `Header`/
`Depends` seria interpretado pelo FastAPI como query param — para não abrir
brecha, declarar com `fastapi.params` neutro NÃO resolve. Solução: excluir
do schema com `Query(default=None, include_in_schema=False)`? Ainda seria
query param. **Implementação correta:** não pôr `_admin_resolvido` na
assinatura; em vez disso os testes fazem
`monkeypatch.setattr(feature_gate, "resolve_ghost_admin", lambda *a: "adm@x")`
para o caso admin e `lambda *a: None` para o comum. Ajustar `_resolver` dos
testes para usar `monkeypatch` e chamar
`dep(request=..., authorization=None, x_feature_preview=..., db=db)`.

- [ ] **Step 4: Rodar e ver passar**

Run: `cd api && python -m pytest tests/test_feature_gate.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/feature_gate.py api/tests/test_feature_gate.py
git commit -m "feat(cs58): dependency feature_access — gate de plano no backend"
```

---

### Task 6: Aplicar o gate às 5 rotas de dado (com prévia truncada)

**Files:**
- Modify: `api/routers/amendments.py` (3 rotas)
- Modify: `api/routers/electoral_history.py` (2 rotas)
- Modify: `api/tests/test_amendments.py`, `api/tests/test_amendment_action_plans.py`,
  `api/tests/test_electoral_history.py` (override do gate no setup)
- Modify: `api/tests/test_feature_gate.py` (testes de rota com TestClient)

**Interfaces:**
- Consumes: `emendas_access`, `trajetoria_access`, `FeatureAccess`,
  `PREVIEW_ROWS` da Task 5.

- [ ] **Step 1: Destravar os testes existentes**

Nos três arquivos de teste de rotas, onde o `TestClient` é montado,
adicionar o override do gate (acesso pleno — o comportamento antigo):

```python
from api.feature_gate import FeatureAccess, emendas_access, trajetoria_access

app.dependency_overrides[emendas_access] = lambda: FeatureAccess(full=True)
app.dependency_overrides[trajetoria_access] = lambda: FeatureAccess(full=True)
```

(usar o que cada arquivo precisa: amendments/action_plans → `emendas_access`;
electoral_history → `trajetoria_access`.)

- [ ] **Step 2: Testes novos de comportamento de rota (falhando)**

Em `test_feature_gate.py`, com TestClient e override do gate para
`FeatureAccess(full=False)` (e `get_db`/`verify_token` como em
`test_amendments.py` — copiar o setup de lá, que já cria as tabelas de
emendas com dados):

```python
def test_lista_de_emendas_em_previa_trunca_e_ignora_filtros():
    # setup: 5+ emendas do parlamentar 1, client com gate full=False
    r = client.get("/api/amendments/?parliamentarian_id=1&limit=200&offset=3&sort_by=year")
    assert r.status_code == 200
    corpo = r.json()
    assert len(corpo) == 3  # PREVIEW_ROWS, nao o limit pedido
    # offset ignorado: a resposta e identica a sem offset
    r2 = client.get("/api/amendments/?parliamentarian_id=1")
    assert corpo == r2.json()


def test_summary_em_previa_e_403():
    r = client.get("/api/amendments/summary?parliamentarian_id=1")
    assert r.status_code == 403


def test_trajetoria_em_previa_trunca_e_nunca_inclui_bens():
    r = client.get(
        "/api/parliamentarians/1/electoral-history?include_assets=true"
    )
    assert r.status_code == 200
    entries = r.json()["entries"]
    assert len(entries) <= 3
    assert all("assets" not in e or e["assets"] is None for e in entries)
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `cd api && python -m pytest tests/test_feature_gate.py -q`
Expected: FAIL (rotas ainda não truncam).

- [ ] **Step 4: Implementar nas rotas**

`amendments.py` — imports (nos dois ramos try/except):

```python
from ..feature_gate import PREVIEW_ROWS, FeatureAccess, emendas_access
```

`get_amendments_summary` ganha o parâmetro e o gate estrito:

```python
    access: FeatureAccess = Depends(emendas_access),
) -> AmendmentSummaryOut:
    """Totais de valor empenhado e pago de um parlamentar, por ano."""
    if not access.full:
        # O agregado E o produto: nao ha previa de um numero so.
        raise HTTPException(status_code=403, detail="Recurso não disponível no seu plano.")
```

(adicionar `HTTPException` ao import de fastapi.)

`list_amendments` ganha `access: FeatureAccess = Depends(emendas_access)` e,
antes de montar o statement:

```python
    if not access.full:
        # PREVIA: mantem o contexto da tela (parlamentar/ano), mas pina
        # ordenacao e corte no servidor. Honrar limit/offset/sort aqui
        # viraria oraculo de extracao via paginacao.
        limit = PREVIEW_ROWS
        offset = 0
        sort_by = "committed_value"
        sort_order = "desc"
```

`list_action_plans` ganha o mesmo parâmetro e, no final, trunca:

```python
    linhas = list(db.execute(stmt).scalars())
    if not access.full:
        linhas = linhas[:PREVIEW_ROWS]
    return [ActionPlanOut.model_validate(row) for row in linhas]
```

`electoral_history.py` — import `from ..feature_gate import PREVIEW_ROWS,
FeatureAccess, trajetoria_access` (2 ramos). `_timeline` ganha
`full: bool`:

```python
def _timeline(
    db: Session, where_clause: Any, include_assets: bool, full: bool = True
) -> ElectoralHistoryOut:
    stmt = (
        select(ElectoralHistory)
        .where(where_clause)
        .order_by(ElectoralHistory.election_year.desc(), ElectoralHistory.id)
    )
    if not full:
        # PREVIA: corte fixo no servidor; bens nunca trafegam.
        stmt = stmt.limit(PREVIEW_ROWS)
        include_assets = False
```

As duas rotas ganham `access: FeatureAccess = Depends(trajetoria_access)` e
passam `full=access.full` ao `_timeline`.

- [ ] **Step 5: Rodar a suíte inteira**

Run: `cd api && python -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add api/routers/amendments.py api/routers/electoral_history.py api/tests/
git commit -m "feat(cs58): gate de plano nas rotas de emendas e trajetoria"
```

---

### Task 7: Front — registro, contrato e hooks (`useFeatureAccess`)

**Files:**
- Modify: `ui/src/lib/featureFlags.ts` (entrada `emendas`)
- Modify: `ui/src/api/endpoints.ts:536-544` (tipo do fetch)
- Modify: `ui/src/hooks/useFeatureFlag.ts`
- Create: `ui/src/hooks/useFeatureAccess.ts`
- Modify: `ui/src/hooks/useFeatureFlag.test.ts`
- Create: `ui/src/hooks/useFeatureAccess.test.ts`

**Interfaces:**
- Produces:
  - `FEATURE_FLAGS.emendas` (registro);
  - `type FeatureAccessValue = 'liberada' | 'bloqueada' | 'oculta'` exportado
    de `useFeatureAccess.ts`;
  - `useFeatureAccess(key: FeatureFlagKey): FeatureAccessValue`;
  - `useFeatureFlag(key): boolean` (assinatura intacta).
- Consumes: `isFeaturePreviewOn(key)` da Task 8 — NESTA task o hook ainda
  não consulta o preview; o fio entra na Task 8.

- [ ] **Step 1: Registro e contrato**

`featureFlags.ts` — nova entrada no objeto:

```typescript
  emendas: {
    label: 'Aba Emendas no dashboard do parlamentar',
    since: '2026-08-18',
  },
```

`endpoints.ts`:

```typescript
/**
 * Estado das feature flags já resolvido para o usuário atual:
 * 'liberada' | 'bloqueada' (cadeado + prévia) | 'oculta'. Chave ausente vale
 * 'oculta'. Consumido via `useFeatureFlag` / `useFeatureAccess`.
 */
export function fetchFeatureFlags(): Promise<Record<string, string>> {
  return request<Record<string, string>>('/settings/feature-flags');
}
```

- [ ] **Step 2: Testes dos hooks (falhando)**

Atualizar `useFeatureFlag.test.ts`: onde o mock devolvia
`{ trajetoria: true }` passa a devolver `{ trajetoria: 'liberada' }` etc.
Criar `useFeatureAccess.test.ts` no mesmo molde (renderHook + QueryClient
wrapper, mock de `fetchFeatureFlags`):

```typescript
it('devolve o valor resolvido da API', async () => {
  mockFetch.mockResolvedValue({ emendas: 'bloqueada' });
  const { result } = renderHook(() => useFeatureAccess('emendas'), { wrapper });
  await waitFor(() => expect(result.current).toBe('bloqueada'));
});

it('chave ausente e erro de rede valem oculta', async () => {
  mockFetch.mockResolvedValue({});
  const { result } = renderHook(() => useFeatureAccess('emendas'), { wrapper });
  await waitFor(() => expect(result.current).toBe('oculta'));
});
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `cd ui && npx vitest run src/hooks`
Expected: FAIL.

- [ ] **Step 4: Implementar**

`useFeatureFlag.ts` (mesma query key, valor muda):

```typescript
  return data?.[key] === 'liberada';
```

`useFeatureAccess.ts`:

```typescript
import { useQuery } from '@tanstack/react-query';

import { fetchFeatureFlags } from '@/api/endpoints';
import type { FeatureFlagKey } from '@/lib/featureFlags';

export type FeatureAccessValue = 'liberada' | 'bloqueada' | 'oculta';

/**
 * Acesso resolvido do usuário a uma feature, nos três valores da CS-58.
 *
 * `useFeatureFlag` continua sendo o portão comum (booleano). Este hook é só
 * para os pontos de montagem que sabem renderizar o estado 'bloqueada'
 * (cadeado + prévia desfocada). Carregando/erro/chave ausente valem
 * 'oculta' — o mais restritivo, como no hook booleano.
 */
export function useFeatureAccess(key: FeatureFlagKey): FeatureAccessValue {
  const { data } = useQuery({
    queryKey: ['feature-flags'],
    queryFn: fetchFeatureFlags,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  const value = data?.[key];
  if (value === 'liberada' || value === 'bloqueada') return value;
  return 'oculta';
}
```

- [ ] **Step 5: Rodar e ver passar**

Run: `cd ui && npx vitest run src/hooks`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ui/src/lib/featureFlags.ts ui/src/api/endpoints.ts ui/src/hooks
git commit -m "feat(cs58): useFeatureAccess e contrato tri-valorado no front"
```

---

### Task 8: Front — preview de admin ("ver como bloqueada")

**Files:**
- Create: `ui/src/lib/featurePreview.ts`
- Create: `ui/src/lib/featurePreview.test.ts`
- Modify: `ui/src/api/client.ts` (header)
- Modify: `ui/src/hooks/useFeatureAccess.ts` (consultar o preview)
- Modify: `ui/src/components/admin/FeatureFlagsPanel.tsx` (toggle)
- Modify: `ui/src/components/admin/FeatureFlagsPanel.test.tsx`

**Interfaces:**
- Produces (de `featurePreview.ts`):
  - `getPreviewKeys(): string[]`
  - `isFeaturePreviewOn(key: string): boolean`
  - `toggleFeaturePreview(key: string): void`
  - `subscribeFeaturePreview(cb: () => void): () => void`
  - `previewHeaderValue(): string | null` (chaves separadas por vírgula)
- Consumes: `useFeatureAccess` da Task 7.

- [ ] **Step 1: Testes do módulo (falhando)**

```typescript
// featurePreview.test.ts
import {
  getPreviewKeys,
  isFeaturePreviewOn,
  previewHeaderValue,
  toggleFeaturePreview,
} from './featurePreview';

beforeEach(() => localStorage.clear());

it('liga, desliga e serializa o header', () => {
  expect(getPreviewKeys()).toEqual([]);
  expect(previewHeaderValue()).toBeNull();
  toggleFeaturePreview('emendas');
  expect(isFeaturePreviewOn('emendas')).toBe(true);
  toggleFeaturePreview('trajetoria');
  expect(previewHeaderValue()).toBe('emendas,trajetoria');
  toggleFeaturePreview('emendas');
  expect(isFeaturePreviewOn('emendas')).toBe(false);
});

it('notifica assinantes ao alternar', () => {
  const spy = vi.fn();
  const off = subscribeFeaturePreview(spy);
  toggleFeaturePreview('emendas');
  expect(spy).toHaveBeenCalled();
  off();
});
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd ui && npx vitest run src/lib/featurePreview.test.ts`
Expected: FAIL.

- [ ] **Step 3: Implementar `featurePreview.ts`**

```typescript
/**
 * Preview de admin: "ver como bloqueada" (CS-58).
 *
 * Lente de inspeção, não config do produto: vive no localStorage DESTE
 * navegador e não vai ao banco. Com o preview ligado para uma chave, a UI
 * renderiza a feature como bloqueada (cadeado + blur + CTA) e as chamadas de
 * dado saem com `X-Feature-Preview`, que o backend só honra para admin — a
 * truncagem real entra na simulação. Usuário comum que forjar isto só borra
 * a própria tela: o header é ignorado no servidor.
 */

const STORAGE_KEY = 'mp-feature-preview';
const EVENTO = 'mp-feature-preview-change';

export function getPreviewKeys(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? (JSON.parse(raw) as unknown) : [];
    return Array.isArray(parsed) ? parsed.filter((k) => typeof k === 'string') : [];
  } catch {
    return [];
  }
}

export function isFeaturePreviewOn(key: string): boolean {
  return getPreviewKeys().includes(key);
}

export function toggleFeaturePreview(key: string): void {
  const atual = getPreviewKeys();
  const proximo = atual.includes(key)
    ? atual.filter((k) => k !== key)
    : [...atual, key];
  localStorage.setItem(STORAGE_KEY, JSON.stringify(proximo));
  window.dispatchEvent(new Event(EVENTO));
}

export function subscribeFeaturePreview(cb: () => void): () => void {
  window.addEventListener(EVENTO, cb);
  window.addEventListener('storage', cb);
  return () => {
    window.removeEventListener(EVENTO, cb);
    window.removeEventListener('storage', cb);
  };
}

/** Valor do header `X-Feature-Preview`, ou null sem preview ativo. */
export function previewHeaderValue(): string | null {
  const keys = getPreviewKeys();
  return keys.length > 0 ? keys.join(',') : null;
}
```

- [ ] **Step 4: Fiação — client, hook e painel**

`client.ts`, no bloco de headers de `request()`:

```typescript
import { previewHeaderValue } from '@/lib/featurePreview';
...
  const preview = previewHeaderValue();
  if (preview) {
    (headers as Record<string, string>)['X-Feature-Preview'] = preview;
  }
```

`useFeatureAccess.ts` — consultar o preview de forma reativa
(`useSyncExternalStore`), degradando SÓ `liberada → bloqueada` (preview
nunca revela o que está oculto):

```typescript
import { useSyncExternalStore } from 'react';
import {
  isFeaturePreviewOn,
  subscribeFeaturePreview,
} from '@/lib/featurePreview';
...
  const previewOn = useSyncExternalStore(
    subscribeFeaturePreview,
    () => isFeaturePreviewOn(key),
    () => false
  );
  const value = data?.[key];
  if (value === 'liberada') return previewOn ? 'bloqueada' : 'liberada';
  if (value === 'bloqueada') return 'bloqueada';
  return 'oculta';
```

`FeatureFlagsPanel.tsx` — por linha de flag, ao lado do select, botão de
preview (ícone `Eye`/`EyeOff` de lucide-react), com estado vindo do módulo:

```tsx
const previewOn = previewKeys.includes(key);
...
<button
  type="button"
  onClick={() => toggleFeaturePreview(key)}
  title={
    previewOn
      ? 'Deixar de ver como bloqueada'
      : 'Ver como bloqueada (só afeta você, neste navegador)'
  }
  aria-pressed={previewOn}
  className={`rounded-full border px-3 py-2 text-[12px] font-semibold ${
    previewOn
      ? 'border-[#b45309] bg-amber-50 text-[#b45309]'
      : 'border-[#383838]/15 text-[#383838]/70'
  }`}
>
  {previewOn ? <EyeOff className="h-4 w-4" aria-hidden /> : <Eye className="h-4 w-4" aria-hidden />}
</button>
```

(`previewKeys` via `useSyncExternalStore(subscribeFeaturePreview, getPreviewKeys)`
— atenção: `getSnapshot` precisa devolver referência estável; guardar o JSON
em cache no módulo ou comparar por string. Solução simples: no módulo,
memoizar `getPreviewKeys` devolvendo o mesmo array enquanto o JSON não
mudar.)

Atualizar `FeatureFlagsPanel.test.tsx`: os mocks de
`fetchFeatureFlagsAdmin` ganham `tiers_liberados`/`tiers_cadeado` no lugar
de `tiers_ligados` (contrato da Task 4 — o texto do painel muda na Task 9) e
teste novo do toggle:

```typescript
it('alterna o preview "ver como bloqueada"', async () => {
  render(<FeatureFlagsPanel />, { wrapper });
  const botao = await screen.findAllByTitle(/Ver como bloqueada/);
  fireEvent.click(botao[0]);
  expect(isFeaturePreviewOn('trajetoria')).toBe(true);
});
```

- [ ] **Step 5: Rodar e ver passar**

Run: `cd ui && npx vitest run src/lib/featurePreview.test.ts src/components/admin/FeatureFlagsPanel.test.tsx src/hooks`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ui/src/lib/featurePreview.ts ui/src/lib/featurePreview.test.ts ui/src/api/client.ts ui/src/hooks/useFeatureAccess.ts ui/src/components/admin/FeatureFlagsPanel.tsx ui/src/components/admin/FeatureFlagsPanel.test.tsx
git commit -m "feat(cs58): preview de admin — ver como bloqueada, com header honrado so p/ admin"
```

---

### Task 9: Front — admin de planos com 3 posições + contadores do painel

**Files:**
- Modify: `ui/src/api/admin.ts:364-407` (tipos e funções)
- Modify: `ui/src/components/admin/TierFeaturesFields.tsx`
- Modify: `ui/src/components/admin/TierFeaturesFields.test.tsx`
- Modify: `ui/src/components/admin/FeatureFlagsPanel.tsx` (texto do contador)

**Interfaces:**
- Produces:
  - `type TierFeatureMode = 'liberado' | 'cadeado'`;
  - `TierFeaturesOut { tier_id: number; features: Record<string, TierFeatureMode> }`;
  - `saveTierFeatures(tierId, features: Record<string, TierFeatureMode>)`;
  - `FeatureFlagAdminOut { ..., tiers_liberados: number; tiers_cadeado: number }`.
- Consumes: contratos das Tasks 4 e 8.

- [ ] **Step 1: Testes (falhando)**

`TierFeaturesFields.test.tsx`: mocks passam a devolver
`{ tier_id: 1, features: { trajetoria: 'liberado' } }`; teste novo do
seletor:

```typescript
it('salva o modo cadeado ao selecionar', async () => {
  render(<TierFeaturesFields tierId={1} />, { wrapper });
  const select = await screen.findByLabelText(/Aba Emendas/);
  fireEvent.change(select, { target: { value: 'cadeado' } });
  await waitFor(() =>
    expect(mockSave).toHaveBeenCalledWith(1, expect.objectContaining({
      emendas: 'cadeado',
    }))
  );
});
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd ui && npx vitest run src/components/admin/TierFeaturesFields.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implementar**

`admin.ts`:

```typescript
export type TierFeatureMode = 'liberado' | 'cadeado';

export interface FeatureFlagAdminOut {
  key: string;
  state: string;
  updated_at: string | null;
  /** Planos ativos com acesso pleno. */
  tiers_liberados: number;
  /** Planos ativos com cadeado (entrada visível + prévia desfocada). */
  tiers_cadeado: number;
  tiers_total: number;
}

export interface TierFeaturesOut {
  tier_id: number;
  /** recurso -> modo; chave ausente = oculto no plano. */
  features: Record<string, TierFeatureMode>;
}

export function saveTierFeatures(
  tierId: number,
  features: Record<string, TierFeatureMode>
): Promise<TierFeaturesOut> { ... mesmo corpo, body JSON.stringify({ features }) ... }
```

`TierFeaturesFields.tsx` — o estado local vira
`Record<string, TierFeatureMode>`; cada feature renderiza `<select>` com as
3 posições em vez de checkbox:

```tsx
const MODOS = [
  { value: 'oculto', label: 'Oculto' },
  { value: 'cadeado', label: 'Cadeado (prévia desfocada)' },
  { value: 'liberado', label: 'Liberado' },
] as const;

const alterar = (key: string, valor: string) => {
  const proximas = { ...modos };
  if (valor === 'oculto') delete proximas[key];
  else proximas[key] = valor as TierFeatureMode;
  setModos(proximas);
  mutation.mutate(proximas);
};
...
<label ...>
  <span className="flex-1 text-[13px] font-semibold text-[#383838]">
    {FEATURE_FLAGS[key].label}
  </span>
  <select
    id={`${tierId}-feature-${key}`}
    value={modos[key] ?? 'oculto'}
    disabled={disabled || mutation.isPending}
    onChange={(e) => alterar(key, e.target.value)}
    className="rounded-full border border-[#383838]/15 px-3 py-1.5 text-[12px] font-semibold text-[#090909]"
  >
    {MODOS.map((op) => (
      <option key={op.value} value={op.value}>{op.label}</option>
    ))}
  </select>
</label>
```

Texto de rodapé atualizado:
`"Oculto some da tela; Cadeado mostra a entrada com prévia desfocada e
chamada para assinar; Liberado dá o recurso. Vale só com a funcionalidade
'liberada' em Configurações gerais. Plano novo nasce com tudo oculto."`

`FeatureFlagsPanel.tsx` — contador (linha do `semPlano`):

```tsx
const comRecurso =
  (linha?.tiers_liberados ?? 0) + (linha?.tiers_cadeado ?? 0);
const semPlano = estado === 'all' && comRecurso === 0;
...
{semPlano
  ? 'Nenhum plano libera esta funcionalidade — ninguém a vê. Configure em Planos.'
  : `Liberada em ${linha?.tiers_liberados ?? 0} de ${linha?.tiers_total} planos` +
    ((linha?.tiers_cadeado ?? 0) > 0
      ? `, com cadeado em ${linha?.tiers_cadeado}.`
      : '.')}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd ui && npx vitest run src/components/admin`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ui/src/api/admin.ts ui/src/components/admin
git commit -m "feat(cs58): seletor oculto/cadeado/liberado por plano no admin"
```

---

### Task 10: Front — cadeado nas abas, blur com CTA e cadeado no card

**Files:**
- Create: `ui/src/components/paywall/PaywallOverlay.tsx`
- Create: `ui/src/components/paywall/PaywallOverlay.test.tsx`
- Modify: `ui/src/pages/ParlamentarDashboard.tsx`
- Modify: `ui/src/components/dashboard/EstatisticasCard.tsx`
- Modify: `ui/src/pages/ParlamentarDashboard.trajetoria.test.tsx`

**Interfaces:**
- Consumes: `useFeatureAccess` (Task 7), `PLANS_URL` de
  `@/components/auth/config`.
- Produces: `<PaywallOverlay>{children}</PaywallOverlay>` — envolve o
  conteúdo real (que já chega truncado do backend) com blur + CTA;
  `EstatisticasCardProps.emendasBloqueadas?: boolean`.

- [ ] **Step 1: PaywallOverlay + teste (falhando primeiro)**

Teste:

```typescript
it('borra o conteudo e mostra o CTA de assinatura', () => {
  render(
    <PaywallOverlay recurso="a aba Emendas">
      <p>conteudo real</p>
    </PaywallOverlay>
  );
  expect(screen.getByText('conteudo real')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /assinar/i })).toHaveAttribute(
    'href',
    expect.stringContaining('/#/portal/account/plans')
  );
});
```

Componente:

```tsx
import { Lock } from 'lucide-react';

import { PLANS_URL } from '@/components/auth/config';

interface PaywallOverlayProps {
  /** Nome do recurso no texto do CTA, ex.: "a aba Emendas". */
  recurso: string;
  children: React.ReactNode;
}

/**
 * Vitrine do recurso pago (CS-58): o conteúdo real fica embaixo, desfocado e
 * inerte; por cima, a chamada para assinar. O desfoque é apresentação — o
 * dado que chega aqui já veio truncado do backend (`feature_gate.py`), então
 * inspecionar o DOM não revela nada além da prévia.
 */
export function PaywallOverlay({ recurso, children }: PaywallOverlayProps) {
  return (
    <div className="relative h-full overflow-hidden">
      <div
        aria-hidden
        className="pointer-events-none h-full select-none blur-[6px]"
      >
        {children}
      </div>
      <div className="absolute inset-0 flex items-center justify-center bg-gradient-to-b from-white/30 via-white/60 to-white/90">
        <div className="mx-6 flex max-w-md flex-col items-center gap-3 rounded-[20px] border border-black/10 bg-white p-6 text-center shadow-lg">
          <span className="flex h-10 w-10 items-center justify-center rounded-full bg-[#f5f5f5]">
            <Lock className="h-5 w-5 text-[#090909]" aria-hidden />
          </span>
          <p className="text-[15px] font-semibold text-[#090909]">
            Este conteúdo é exclusivo para assinantes
          </p>
          <p className="text-[13px] text-[#383838]/80">
            Assine um plano que inclui {recurso} para ver tudo — o que você vê
            atrás do desfoque é só uma amostra.
          </p>
          <a
            href={PLANS_URL}
            className="rounded-[76px] bg-[#1b76ff] px-6 py-2 text-[13px] font-semibold text-white transition hover:opacity-90"
          >
            ASSINAR PARA VER TUDO
          </a>
        </div>
      </div>
    </div>
  );
}
```

Run: `cd ui && npx vitest run src/components/paywall` → PASS.

- [ ] **Step 2: Abas do ParlamentarDashboard**

Testes primeiro (`ParlamentarDashboard.trajetoria.test.tsx`): os mocks de
`fetchFeatureFlags` passam de boolean para string; casos:
`{ trajetoria: 'oculta' }` → aba ausente (regressão);
`{ trajetoria: 'liberada' }` → aba normal;
`{ trajetoria: 'bloqueada', emendas: 'bloqueada' }` → aba presente com
cadeado (`screen.getByText('TRAJETÓRIA')` + ícone) e conteúdo com CTA.

Implementação em `ParlamentarDashboard.tsx`:

```tsx
import { Lock } from 'lucide-react';           // junto dos demais lucide
import { useFeatureAccess } from '@/hooks/useFeatureAccess';
import { PaywallOverlay } from '@/components/paywall/PaywallOverlay';
...
  const emendasAccess = useFeatureAccess('emendas');
  const trajetoriaAccess = useFeatureAccess('trajetoria');
...
  // Emendas é grandeza de ano civil...; só busca com acesso pleno — no
  // cadeado o card mostra o bloqueio sem tocar a API (a rota devolveria 403).
  const amendmentsSummaryQuery = useQuery({
    queryKey: ['amendments-summary', numericId, emendasYear],
    queryFn: () => getAmendmentsSummary(numericId, emendasYear),
    enabled: isIdValid && emendasAccess === 'liberada',
  });
```

A lista `abas` (cada item ganha `locked?: boolean`):

```tsx
  const abas = [
    { value: 'votacoes', ... },      // inalteradas
    { value: 'proposicoes', ... },
    { value: 'taquigraficas', ... },
    ...(emendasAccess !== 'oculta'
      ? [
          {
            value: 'emendas',
            label: 'EMENDAS',
            locked: emendasAccess === 'bloqueada',
            className: 'mt-0 p-6 pt-4 h-[500px]',
            content:
              emendasAccess === 'bloqueada' ? (
                <PaywallOverlay recurso="a aba Emendas">
                  <EmendasTable parliamentarianId={numericId} year={emendasYear} />
                </PaywallOverlay>
              ) : (
                <EmendasTable parliamentarianId={numericId} year={emendasYear} />
              ),
          },
        ]
      : []),
    ...(trajetoriaAccess !== 'oculta'
      ? [
          {
            value: 'trajetoria',
            label: 'TRAJETÓRIA',
            locked: trajetoriaAccess === 'bloqueada',
            className: 'mt-0 p-6 pt-4 h-[500px]',
            content:
              trajetoriaAccess === 'bloqueada' ? (
                <PaywallOverlay recurso="a aba Trajetória">
                  <TrajetoriaTab parliamentarianId={numericId} />
                </PaywallOverlay>
              ) : (
                <TrajetoriaTab parliamentarianId={numericId} />
              ),
          },
        ]
      : []),
  ];
```

(A flag `trajetoria` deixa de usar `useFeatureFlag` — remover
`const trajetoriaOn` e o import se ficar sem uso.)

No `TabsTrigger`, o estado bloqueado:

```tsx
<TabsTrigger
  key={aba.value}
  value={aba.value}
  className={`${parlamentarSectionTabTriggerClass}${
    aba.locked
      ? ' data-[state=inactive]:text-[#090909]/45 data-[state=active]:bg-[#6b6b6b]'
      : ''
  }`}
>
  {aba.locked && <Lock className="mr-1.5 h-3.5 w-3.5" aria-hidden />}
  {aba.label}
</TabsTrigger>
```

- [ ] **Step 3: EstatisticasCard com cadeado**

Prop nova e bloco condicional (substitui `amendmentsSummary != null` por um
`||`):

```tsx
interface EstatisticasCardProps {
  ...
  /** Recurso emendas em modo cadeado: mostra o bloqueio, sem números. */
  emendasBloqueadas?: boolean;
}
...
      {(amendmentsSummary != null || emendasBloqueadas) && (
        <div className="mt-6 border-t border-black/[0.08] pt-4">
          <p className="text-[13px] font-semibold uppercase tracking-wide text-[#383838]">
            Emendas {amendmentsYear ?? amendmentsSummary?.year ?? ''}
          </p>
          {emendasBloqueadas ? (
            <p className="mt-2 flex items-center gap-2 text-[13px] text-[#383838]/70">
              <Lock className="h-4 w-4" aria-hidden />
              Exclusivo para assinantes
            </p>
          ) : (
            <div className="mt-2 flex items-start justify-between gap-4">
              ... (bloco atual, com amendmentsSummary!) ...
            </div>
          )}
        </div>
      )}
```

No `ParlamentarDashboard`:

```tsx
<EstatisticasCard
  stats={dashboardStatsQuery.data}
  isLoading={dashboardStatsQuery.isLoading}
  amendmentsSummary={amendmentsSummaryQuery.data}
  amendmentsYear={emendasYear}
  emendasBloqueadas={emendasAccess === 'bloqueada'}
/>
```

- [ ] **Step 4: Rodar os testes do front inteiros + type-check**

Run: `cd ui && npx vitest run && npx tsc -p tsconfig.app.json --noEmit`
Expected: vitest PASS; tsc com a MESMA contagem de erros da main (~17,
todos pré-existentes de mocks).

- [ ] **Step 5: Commit**

```bash
git add ui/src/components/paywall ui/src/pages/ParlamentarDashboard.tsx ui/src/components/dashboard/EstatisticasCard.tsx ui/src/pages/ParlamentarDashboard.trajetoria.test.tsx
git commit -m "feat(cs58): aba com cadeado, previa desfocada com CTA e cadeado no card"
```

---

### Task 11: Verificação final e PR

**Files:** nenhum novo (correções pontuais se a verificação apontar).

- [ ] **Step 1: Suítes completas**

```bash
cd api && python -m pytest tests/ -q
cd ui && npx vitest run
cd ui && npx tsc -p tsconfig.app.json --noEmit   # comparar contagem com a main
```

- [ ] **Step 2: Push + PR contra a main**

```bash
git push -u origin feat/cs58-recursos-pagos
```

PR com `gh pr create` (ou MCP do GitHub), título
`feat(cs58): recursos pagos — cadeado com prévia desfocada, configurável por plano`,
corpo cobrindo: o que muda para o usuário, o modelo (modo por plano), o gate
no backend, o seed de `emendas` (deploy não muda comportamento), o preview
de admin, e o passo pós-merge: configurar os modos por plano nas telas de
admin quando decidir cobrar.
