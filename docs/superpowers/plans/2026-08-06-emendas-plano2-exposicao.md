# Emendas parlamentares — Plano 2: API, interface e auditoria

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expor as emendas já coletadas pelo Plano 1 — aba nova no perfil do parlamentar, resumo anual no card de estatísticas e painel administrativo das emendas que não casaram com nenhum parlamentar.

**Architecture:** Um router FastAPI novo (`/amendments`) com lista e resumo, mais uma rota de auditoria no router `/admin` existente. Na UI, uma tabela no molde de `VotacoesTable`, uma aba nova no `ParlamentarDashboard` e um bloco novo no `EstatisticasCard`, alimentado por query própria em vez do DTO de estatísticas trimestrais.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy 2.0, React 18, TanStack Query, Tailwind, shadcn/ui, vitest.

**Spec:** `docs/superpowers/specs/2026-08-06-emendas-parlamentares-design.md`
**Pré-requisito:** Plano 1 concluído (`2026-08-06-emendas-plano1-coleta.md`). A tabela `parliamentary_amendment` precisa existir e ter dados.

## Global Constraints

- Rotas novas entram sob `api_router` com `dependencies=auth_dependencies` em `api/main.py:118-125`, como todas as rotas de dados. A exceção é `/admin`, que tem o próprio gate.
- O verificador `scripts/check_ui_api_contract.py` roda no CI e exige que toda chamada `request<T>('/path')` da UI tenha rota correspondente na API. Ele compara **apenas o path**, casando pelo prefixo declarado em `APIRouter(prefix=...)`.
- Rotas administrativas usam `Depends(require_ghost_admin)` e devolvem 404 para não-admin — padrão de `api/routers/admin.py`.
- Valores monetários trafegam como **string** no JSON, não como float. `Decimal` serializado em float perde centavo, e é dinheiro público.
- Comandos de teste: `pytest api/tests/ -v` a partir da raiz; `npm run test` dentro de `ui/`.
- Textos de interface em português, com a grafia já usada nas outras abas (caixa alta nos rótulos de aba).

---

### Task 1: Rotas de lista e resumo

**Files:**
- Create: `api/routers/amendments.py`
- Modify: `api/main.py` (import e registro do router)
- Test: `api/tests/test_amendments.py`

**Interfaces:**
- Consumes: modelo `ParliamentaryAmendment` de `api/db/models/` (Plano 1, Task 4)
- Produces:
  - `GET /api/amendments` → `List[AmendmentOut]`
  - `GET /api/amendments/summary` → `AmendmentSummaryOut`
  - `AmendmentOut` com campos `id`, `amendment_code`, `year`, `amendment_number`, `amendment_type`, `author_name_raw`, `parliamentarian_id`, `match_status`, `spending_locality`, `function`, `subfunction`, `committed_value: Optional[str]`, `settled_value: Optional[str]`, `paid_value: Optional[str]`, `created_at`, `updated_at`
  - `AmendmentSummaryOut` com campos `year: Optional[int]`, `count: int`, `committed_total: str`, `paid_total: str`

- [ ] **Step 1: Escreva o teste que falha**

Leia antes `api/tests/conftest.py` para reaproveitar as fixtures de banco e de
autenticação já existentes. Crie `api/tests/test_amendments.py`:

```python
from __future__ import annotations

from decimal import Decimal

import pytest

from api.db.models.parliamentarian import Parliamentarian
from api.db.models.parliamentary_amendment import ParliamentaryAmendment


@pytest.fixture()
def seed_amendments(db_session):
    db_session.add(
        Parliamentarian(id=1, name="José da Silva", type="Deputado", state_elected="PI")
    )
    db_session.add(
        Parliamentarian(id=2, name="Maria Souza", type="Deputado", state_elected="PI")
    )
    db_session.add_all(
        [
            ParliamentaryAmendment(
                amendment_code="202600010001",
                year=2026,
                amendment_number="0001",
                amendment_type="Individual",
                author_name_raw="José da Silva",
                parliamentarian_id=1,
                match_status="matched",
                spending_locality="TERESINA - PI",
                function="Saúde",
                committed_value=Decimal("2000000.00"),
                paid_value=Decimal("500000.00"),
            ),
            ParliamentaryAmendment(
                amendment_code="202600010002",
                year=2026,
                amendment_number="0002",
                amendment_type="Individual",
                author_name_raw="José da Silva",
                parliamentarian_id=1,
                match_status="matched",
                spending_locality="PARNAÍBA - PI",
                function="Educação",
                committed_value=Decimal("1500000.00"),
                paid_value=Decimal("0.00"),
            ),
            ParliamentaryAmendment(
                amendment_code="202500010003",
                year=2025,
                amendment_type="Individual",
                author_name_raw="José da Silva",
                parliamentarian_id=1,
                match_status="matched",
                committed_value=Decimal("900000.00"),
                paid_value=Decimal("900000.00"),
            ),
            ParliamentaryAmendment(
                amendment_code="202600010004",
                year=2026,
                amendment_type="Individual",
                author_name_raw="Fulano Nao Casado",
                parliamentarian_id=None,
                match_status="unmatched",
                committed_value=Decimal("100.00"),
                paid_value=Decimal("0.00"),
            ),
        ]
    )
    db_session.commit()


def test_lista_filtra_por_parlamentar(client, seed_amendments):
    resp = client.get("/api/amendments", params={"parliamentarian_id": 1})
    assert resp.status_code == 200
    assert len(resp.json()) == 3


def test_lista_filtra_por_parlamentar_e_ano(client, seed_amendments):
    resp = client.get("/api/amendments", params={"parliamentarian_id": 1, "year": 2026})
    assert resp.status_code == 200
    codes = {item["amendment_code"] for item in resp.json()}
    assert codes == {"202600010001", "202600010002"}


def test_valores_trafegam_como_string(client, seed_amendments):
    resp = client.get("/api/amendments", params={"parliamentarian_id": 1, "year": 2026})
    item = next(i for i in resp.json() if i["amendment_code"] == "202600010001")
    assert item["committed_value"] == "2000000.00"
    assert item["paid_value"] == "500000.00"


def test_lista_respeita_limit_e_offset(client, seed_amendments):
    todos = client.get("/api/amendments", params={"parliamentarian_id": 1}).json()
    pagina = client.get(
        "/api/amendments", params={"parliamentarian_id": 1, "limit": 1, "offset": 1}
    ).json()
    assert len(pagina) == 1
    assert pagina[0]["amendment_code"] == todos[1]["amendment_code"]


def test_resumo_soma_por_ano(client, seed_amendments):
    resp = client.get(
        "/api/amendments/summary", params={"parliamentarian_id": 1, "year": 2026}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["year"] == 2026
    assert body["count"] == 2
    assert body["committed_total"] == "3500000.00"
    assert body["paid_total"] == "500000.00"


def test_resumo_sem_dado_devolve_zero_e_nao_404(client, seed_amendments):
    resp = client.get(
        "/api/amendments/summary", params={"parliamentarian_id": 2, "year": 2026}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 0
    assert body["committed_total"] == "0.00"
    assert body["paid_total"] == "0.00"


def test_resumo_ignora_emendas_nao_casadas(client, seed_amendments):
    # A emenda 202600010004 nao tem parlamentarian_id e nao pode entrar em
    # resumo nenhum de perfil.
    resp = client.get(
        "/api/amendments/summary", params={"parliamentarian_id": 1, "year": 2026}
    )
    assert resp.json()["count"] == 2
```

- [ ] **Step 2: Rode o teste e confirme que falha**

Run: `pytest api/tests/test_amendments.py -v`
Expected: FAIL — 404 nas rotas, porque o router não existe.

- [ ] **Step 3: Implemente o router**

Crie `api/routers/amendments.py`:

```python
"""Rotas de emendas parlamentares orcamentarias (CS-17).

Nao confundir com emenda a proposicao: aqui e destinacao de verba do orcamento
federal, coletada do Portal da Transparencia.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, field_serializer
from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import Session

try:
    # Execução como pacote (api.routers.amendments).
    from ..db.models.parliamentary_amendment import ParliamentaryAmendment
    from ..dependencies import get_db
except (ImportError, ValueError):
    # Execução local dentro de api/ sem reconhecimento de pacote.
    from db.models.parliamentary_amendment import ParliamentaryAmendment
    from dependencies import get_db

router = APIRouter(prefix="/amendments", tags=["amendments"])

AmendmentSortBy = Literal["year", "committed_value", "paid_value", "id"]
SortOrder = Literal["asc", "desc"]

ZERO = Decimal("0.00")


class AmendmentOut(BaseModel):
    """Emenda parlamentar serializada."""

    id: int
    amendment_code: str
    year: Optional[int] = None
    amendment_number: Optional[str] = None
    amendment_type: Optional[str] = None
    author_name_raw: Optional[str] = None
    parliamentarian_id: Optional[int] = None
    match_status: str
    spending_locality: Optional[str] = None
    function: Optional[str] = None
    subfunction: Optional[str] = None
    committed_value: Optional[Decimal] = None
    settled_value: Optional[Decimal] = None
    paid_value: Optional[Decimal] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("committed_value", "settled_value", "paid_value")
    def _serialize_money(self, value: Optional[Decimal]) -> Optional[str]:
        # String, nunca float: dinheiro publico nao pode perder centavo em
        # ponto flutuante.
        return None if value is None else str(value)


class AmendmentSummaryOut(BaseModel):
    """Totais anuais de emendas de um parlamentar."""

    year: Optional[int] = None
    count: int
    committed_total: Decimal
    paid_total: Decimal

    @field_serializer("committed_total", "paid_total")
    def _serialize_money(self, value: Decimal) -> str:
        return str(value)


@router.get("/summary", response_model=AmendmentSummaryOut)
def get_amendments_summary(
    parliamentarian_id: int = Query(..., description="Parlamentar dono das emendas"),
    year: Optional[int] = Query(None, description="Ano civil; omitido soma todos"),
    db: Session = Depends(get_db),
) -> AmendmentSummaryOut:
    """Totais de valor empenhado e pago de um parlamentar, por ano."""
    stmt = select(
        func.count(ParliamentaryAmendment.id),
        func.coalesce(func.sum(ParliamentaryAmendment.committed_value), ZERO),
        func.coalesce(func.sum(ParliamentaryAmendment.paid_value), ZERO),
    ).where(ParliamentaryAmendment.parliamentarian_id == parliamentarian_id)

    if year is not None:
        stmt = stmt.where(ParliamentaryAmendment.year == year)

    count, committed, paid = db.execute(stmt).one()

    return AmendmentSummaryOut(
        year=year,
        count=count or 0,
        committed_total=Decimal(committed or 0).quantize(ZERO),
        paid_total=Decimal(paid or 0).quantize(ZERO),
    )


@router.get("/", response_model=List[AmendmentOut])
def list_amendments(
    parliamentarian_id: Optional[int] = Query(None),
    year: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    sort_by: AmendmentSortBy = Query("committed_value"),
    sort_order: SortOrder = Query("desc"),
    db: Session = Depends(get_db),
) -> List[AmendmentOut]:
    """Lista emendas, opcionalmente filtradas por parlamentar e ano."""
    stmt = select(ParliamentaryAmendment)

    if parliamentarian_id is not None:
        stmt = stmt.where(
            ParliamentaryAmendment.parliamentarian_id == parliamentarian_id
        )
    if year is not None:
        stmt = stmt.where(ParliamentaryAmendment.year == year)

    column = getattr(ParliamentaryAmendment, sort_by)
    direction = desc if sort_order == "desc" else asc
    # Desempate por id mantem a paginacao estavel quando o criterio empata.
    stmt = stmt.order_by(direction(column), ParliamentaryAmendment.id)
    stmt = stmt.limit(limit).offset(offset)

    return [AmendmentOut.model_validate(row) for row in db.execute(stmt).scalars()]
```

A rota `/summary` é declarada **antes** de `/`, para que o roteador do FastAPI
não tente casar `summary` como parâmetro de caminho de uma rota mais genérica
que venha a ser acrescentada depois.

- [ ] **Step 4: Registre o router**

Em `api/main.py`, acrescente `amendments` à linha de import dos routers (junto
de `analysis`, `authors_proposition`, etc.) e registre-o junto das demais rotas
autenticadas, logo depois de `roll_call_votes` (por volta da linha 122):

```python
    api_router.include_router(amendments.router, dependencies=auth_dependencies)
```

- [ ] **Step 5: Rode os testes e confirme que passam**

Run: `pytest api/tests/test_amendments.py -v`
Expected: PASS — 7 testes.

Depois, a suíte inteira, para garantir que o router novo não quebrou o smoke:

Run: `pytest api/tests/ -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add api/routers/amendments.py api/main.py api/tests/test_amendments.py
git commit -m "feat(emendas): rotas de lista e resumo anual de emendas"
```

---

### Task 2: Rota de auditoria das emendas não casadas

**Files:**
- Modify: `api/routers/admin.py`
- Test: `api/tests/test_admin_amendments.py`

**Interfaces:**
- Consumes: modelo `ParliamentaryAmendment`
- Produces: `GET /api/admin/amendments/unmatched` → `List[UnmatchedAuthorOut]` com campos `author_name_raw: Optional[str]`, `amendment_count: int`, `committed_total: str`, `match_status: str`

- [ ] **Step 1: Escreva o teste que falha**

Leia `api/tests/test_admin_gate.py` para copiar a forma de autenticar como
administrador nos testes. Crie `api/tests/test_admin_amendments.py`:

```python
from __future__ import annotations

from decimal import Decimal

import pytest

from api.db.models.parliamentary_amendment import ParliamentaryAmendment


@pytest.fixture()
def seed_unmatched(db_session):
    db_session.add_all(
        [
            ParliamentaryAmendment(
                amendment_code="A1",
                year=2026,
                author_name_raw="Fulano Sem Par",
                match_status="unmatched",
                committed_value=Decimal("1000.00"),
            ),
            ParliamentaryAmendment(
                amendment_code="A2",
                year=2026,
                author_name_raw="Fulano Sem Par",
                match_status="unmatched",
                committed_value=Decimal("2000.00"),
            ),
            ParliamentaryAmendment(
                amendment_code="A3",
                year=2026,
                author_name_raw="Beltrano Homonimo",
                match_status="ambiguous",
                committed_value=Decimal("500.00"),
            ),
            ParliamentaryAmendment(
                amendment_code="A4",
                year=2026,
                author_name_raw="Casado Certo",
                parliamentarian_id=None,
                match_status="matched",
                committed_value=Decimal("999.00"),
            ),
        ]
    )
    db_session.commit()


def test_agrupa_por_autor_e_soma(admin_client, seed_unmatched):
    resp = admin_client.get("/api/admin/amendments/unmatched")
    assert resp.status_code == 200
    linhas = {item["author_name_raw"]: item for item in resp.json()}

    assert linhas["Fulano Sem Par"]["amendment_count"] == 2
    assert linhas["Fulano Sem Par"]["committed_total"] == "3000.00"
    assert linhas["Fulano Sem Par"]["match_status"] == "unmatched"


def test_inclui_ambiguous_alem_de_unmatched(admin_client, seed_unmatched):
    resp = admin_client.get("/api/admin/amendments/unmatched")
    nomes = {item["author_name_raw"] for item in resp.json()}
    assert "Beltrano Homonimo" in nomes


def test_exclui_o_que_ja_casou(admin_client, seed_unmatched):
    resp = admin_client.get("/api/admin/amendments/unmatched")
    nomes = {item["author_name_raw"] for item in resp.json()}
    assert "Casado Certo" not in nomes


def test_ordena_pelo_maior_valor_primeiro(admin_client, seed_unmatched):
    resp = admin_client.get("/api/admin/amendments/unmatched")
    totais = [item["committed_total"] for item in resp.json()]
    assert totais == sorted(totais, key=lambda v: -float(v))


def test_nao_admin_recebe_404(client, seed_unmatched):
    resp = client.get("/api/admin/amendments/unmatched")
    assert resp.status_code == 404
```

- [ ] **Step 2: Rode o teste e confirme que falha**

Run: `pytest api/tests/test_admin_amendments.py -v`
Expected: FAIL — 404 em todas, inclusive nas que esperam 200.

- [ ] **Step 3: Implemente a rota**

Em `api/routers/admin.py`, acrescente o import do modelo junto dos demais
(dentro dos dois blocos `try`/`except` de import, como o arquivo já faz):

```python
    from ..db.models.parliamentary_amendment import ParliamentaryAmendment
```
```python
    from db.models.parliamentary_amendment import ParliamentaryAmendment
```

E, ao final do arquivo, o modelo de saída e a rota:

```python
class UnmatchedAuthorOut(BaseModel):
    """Autor de emenda que o casamento automatico nao resolveu."""

    author_name_raw: Optional[str] = None
    amendment_count: int
    committed_total: str
    match_status: str


@router.get("/amendments/unmatched", response_model=list[UnmatchedAuthorOut])
def list_unmatched_amendment_authors(
    db: Session = Depends(get_db),
    _admin: str = Depends(require_ghost_admin),
) -> list[UnmatchedAuthorOut]:
    """Autores nao casados, agrupados e ordenados por valor.

    O Portal da Transparencia so devolve o nome do autor em texto livre, entao
    parte das emendas nunca casa automaticamente. Esta rota existe para que esse
    residuo seja visivel e auditavel, em vez de sumir silenciosamente.
    """
    total = func.coalesce(func.sum(ParliamentaryAmendment.committed_value), 0)
    stmt = (
        select(
            ParliamentaryAmendment.author_name_raw,
            ParliamentaryAmendment.match_status,
            func.count(ParliamentaryAmendment.id).label("amendment_count"),
            total.label("committed_total"),
        )
        .where(ParliamentaryAmendment.match_status.in_(("unmatched", "ambiguous")))
        .group_by(
            ParliamentaryAmendment.author_name_raw,
            ParliamentaryAmendment.match_status,
        )
        .order_by(total.desc())
    )

    return [
        UnmatchedAuthorOut(
            author_name_raw=row.author_name_raw,
            match_status=row.match_status,
            amendment_count=row.amendment_count,
            committed_total=str(row.committed_total),
        )
        for row in db.execute(stmt)
    ]
```

- [ ] **Step 4: Rode os testes e confirme que passam**

Run: `pytest api/tests/test_admin_amendments.py -v`
Expected: PASS — 5 testes.

- [ ] **Step 5: Commit**

```bash
git add api/routers/admin.py api/tests/test_admin_amendments.py
git commit -m "feat(emendas): rota admin de auditoria das emendas nao casadas"
```

---

### Task 3: Cliente da UI e tipos

**Files:**
- Modify: `ui/src/api/types.ts`
- Modify: `ui/src/api/endpoints.ts`
- Modify: `ui/src/api/admin.ts`

**Interfaces:**
- Consumes: rotas das Tasks 1 e 2
- Produces:
  - `AmendmentOut`, `AmendmentSummaryOut`, `UnmatchedAuthorOut` (tipos)
  - `listAmendments(params)`, `getAmendmentsSummary(params)` em `endpoints.ts`
  - `listUnmatchedAmendmentAuthors()` em `admin.ts`

- [ ] **Step 1: Declare os tipos**

Em `ui/src/api/types.ts`, acrescente depois de `DashboardStatsOut` (linha 137 em
diante):

```typescript
export interface AmendmentOut {
  id: number;
  amendment_code: string;
  year?: number | null;
  amendment_number?: string | null;
  amendment_type?: string | null;
  author_name_raw?: string | null;
  parliamentarian_id?: number | null;
  match_status: string;
  spending_locality?: string | null;
  function?: string | null;
  subfunction?: string | null;
  // Valores monetarios chegam como string para nao perder centavo em float.
  committed_value?: string | null;
  settled_value?: string | null;
  paid_value?: string | null;
  created_at: string;
  updated_at: string;
}

export interface AmendmentSummaryOut {
  year?: number | null;
  count: number;
  committed_total: string;
  paid_total: string;
}

export interface UnmatchedAuthorOut {
  author_name_raw?: string | null;
  amendment_count: number;
  committed_total: string;
  match_status: string;
}
```

- [ ] **Step 2: Escreva os clientes**

Em `ui/src/api/endpoints.ts`, acrescente depois de `getRollCallVote` (por volta
da linha 218), seguindo o mesmo formato de `listRollCallVotes`:

```typescript
export type AmendmentSortBy = 'year' | 'committed_value' | 'paid_value' | 'id';

export interface ListAmendmentsParams {
  parliamentarian_id?: number;
  year?: number;
  limit?: number;
  offset?: number;
  sort_by?: AmendmentSortBy;
  sort_order?: SortOrder;
}

export function listAmendments(
  params: ListAmendmentsParams = {}
): Promise<AmendmentOut[]> {
  const sp = new URLSearchParams();
  if (params.parliamentarian_id != null)
    sp.set('parliamentarian_id', String(params.parliamentarian_id));
  if (params.year != null) sp.set('year', String(params.year));
  if (params.limit != null) sp.set('limit', String(params.limit));
  if (params.offset != null) sp.set('offset', String(params.offset));
  if (params.sort_by) sp.set('sort_by', params.sort_by);
  if (params.sort_order) sp.set('sort_order', params.sort_order);
  const q = sp.toString();
  return request<AmendmentOut[]>(`/amendments/${q ? `?${q}` : ''}`);
}

export function getAmendmentsSummary(
  parliamentarianId: number,
  year?: number
): Promise<AmendmentSummaryOut> {
  const sp = new URLSearchParams({ parliamentarian_id: String(parliamentarianId) });
  if (year != null) sp.set('year', String(year));
  return request<AmendmentSummaryOut>(`/amendments/summary?${sp.toString()}`);
}
```

Acrescente `AmendmentOut` e `AmendmentSummaryOut` ao bloco de import de tipos no
topo de `endpoints.ts`.

Em `ui/src/api/admin.ts`, acrescente:

```typescript
export function listUnmatchedAmendmentAuthors(): Promise<UnmatchedAuthorOut[]> {
  return request<UnmatchedAuthorOut[]>('/admin/amendments/unmatched');
}
```

com `UnmatchedAuthorOut` importado de `./types`.

- [ ] **Step 3: Verifique o contrato UI ↔ API**

Este é o passo que pega erro de digitação de rota antes do CI:

```bash
python3 scripts/check_ui_api_contract.py
```

Expected: linha de OK, exit 0. Se acusar divergência, o path escrito no cliente
não corresponde ao declarado no router — corrija o cliente, não o verificador.

- [ ] **Step 4: Verifique a tipagem**

```bash
cd ui && npx tsc --noEmit
```

Expected: sem erros.

- [ ] **Step 5: Commit**

```bash
git add ui/src/api/types.ts ui/src/api/endpoints.ts ui/src/api/admin.ts
git commit -m "feat(emendas): tipos e clientes de emendas na UI"
```

---

### Task 4: Tabela de emendas

**Files:**
- Create: `ui/src/components/dashboard/EmendasTable.tsx`
- Test: `ui/src/components/dashboard/EmendasTable.test.tsx`

**Interfaces:**
- Consumes: `listAmendments` (Task 3)
- Produces: `EmendasTable({ parliamentarianId, year }: { parliamentarianId: number; year?: number })`

Leia `ui/src/components/dashboard/VotacoesTable.tsx` antes de começar: a
estrutura de `useQuery`, estados de carregamento e vazio, e as classes da
`Table` do shadcn saem dali.

- [ ] **Step 1: Escreva o teste que falha**

Crie `ui/src/components/dashboard/EmendasTable.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { EmendasTable } from './EmendasTable';
import * as endpoints from '@/api/endpoints';

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const EMENDA = {
  id: 1,
  amendment_code: '202600010001',
  year: 2026,
  amendment_number: '0001',
  amendment_type: 'Individual',
  author_name_raw: 'José da Silva',
  parliamentarian_id: 1,
  match_status: 'matched',
  spending_locality: 'TERESINA - PI',
  function: 'Saúde',
  subfunction: 'Atenção Básica',
  committed_value: '2000000.00',
  settled_value: '500000.00',
  paid_value: '500000.00',
  created_at: '2026-08-01T00:00:00Z',
  updated_at: '2026-08-01T00:00:00Z',
};

describe('EmendasTable', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('mostra a emenda com valores formatados em real', async () => {
    vi.spyOn(endpoints, 'listAmendments').mockResolvedValue([EMENDA]);

    renderWithClient(<EmendasTable parliamentarianId={1} year={2026} />);

    await waitFor(() => {
      expect(screen.getByText('TERESINA - PI')).toBeInTheDocument();
    });
    expect(screen.getByText('Saúde')).toBeInTheDocument();
    expect(screen.getByText('R$ 2.000.000,00')).toBeInTheDocument();
    expect(screen.getByText('R$ 500.000,00')).toBeInTheDocument();
  });

  it('mostra estado vazio quando nao ha emendas', async () => {
    vi.spyOn(endpoints, 'listAmendments').mockResolvedValue([]);

    renderWithClient(<EmendasTable parliamentarianId={1} year={2026} />);

    await waitFor(() => {
      expect(
        screen.getByText(/nenhuma emenda encontrada/i)
      ).toBeInTheDocument();
    });
  });

  it('mostra mensagem de falha quando a consulta quebra', async () => {
    vi.spyOn(endpoints, 'listAmendments').mockRejectedValue(new Error('boom'));

    renderWithClient(<EmendasTable parliamentarianId={1} year={2026} />);

    await waitFor(() => {
      expect(screen.getByText(/falha ao carregar/i)).toBeInTheDocument();
    });
  });

  it('trata valor nulo sem quebrar', async () => {
    vi.spyOn(endpoints, 'listAmendments').mockResolvedValue([
      { ...EMENDA, paid_value: null, spending_locality: null },
    ]);

    renderWithClient(<EmendasTable parliamentarianId={1} year={2026} />);

    await waitFor(() => {
      expect(screen.getByText('Saúde')).toBeInTheDocument();
    });
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
  });
});
```

- [ ] **Step 2: Rode o teste e confirme que falha**

Run: `cd ui && npm run test -- EmendasTable`
Expected: FAIL — não resolve o módulo `./EmendasTable`.

- [ ] **Step 3: Implemente o componente**

Crie `ui/src/components/dashboard/EmendasTable.tsx`:

```tsx
import { useQuery } from '@tanstack/react-query';
import { listAmendments } from '@/api/endpoints';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Loader2 } from 'lucide-react';

interface EmendasTableProps {
  parliamentarianId: number;
  year?: number;
}

const BRL = new Intl.NumberFormat('pt-BR', {
  style: 'currency',
  currency: 'BRL',
});

/** Valores chegam como string para nao perder centavo; so viram numero aqui. */
function formatBRL(value?: string | null): string {
  if (value == null || value === '') return '—';
  const parsed = Number(value);
  return Number.isFinite(parsed) ? BRL.format(parsed) : '—';
}

function textOrDash(value?: string | null): string {
  return value == null || value === '' ? '—' : value;
}

export function EmendasTable({ parliamentarianId, year }: EmendasTableProps) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['amendments', parliamentarianId, year],
    queryFn: () =>
      listAmendments({
        parliamentarian_id: parliamentarianId,
        year,
        limit: 200,
        sort_by: 'committed_value',
        sort_order: 'desc',
      }),
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-2 py-10 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" />
        <span>Carregando emendas...</span>
      </div>
    );
  }

  if (isError) {
    return (
      <p className="py-10 text-center text-muted-foreground">
        Falha ao carregar as emendas do parlamentar.
      </p>
    );
  }

  if (!data || data.length === 0) {
    return (
      <p className="py-10 text-center text-muted-foreground">
        Nenhuma emenda encontrada para este parlamentar.
      </p>
    );
  }

  return (
    <div className="max-h-[440px] overflow-y-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Nº</TableHead>
            <TableHead>Localidade do gasto</TableHead>
            <TableHead>Função</TableHead>
            <TableHead className="text-right">Empenhado</TableHead>
            <TableHead className="text-right">Pago</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.map((emenda) => (
            <TableRow key={emenda.id}>
              <TableCell className="whitespace-nowrap">
                {textOrDash(emenda.amendment_number)}
              </TableCell>
              <TableCell>{textOrDash(emenda.spending_locality)}</TableCell>
              <TableCell>{textOrDash(emenda.function)}</TableCell>
              <TableCell className="whitespace-nowrap text-right">
                {formatBRL(emenda.committed_value)}
              </TableCell>
              <TableCell className="whitespace-nowrap text-right">
                {formatBRL(emenda.paid_value)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
```

- [ ] **Step 4: Rode os testes e confirme que passam**

Run: `cd ui && npm run test -- EmendasTable`
Expected: PASS — 4 testes.

Se o teste de formatação falhar por causa do caractere de espaço, note que
`Intl.NumberFormat('pt-BR')` usa espaço não separável (U+00A0) entre `R$` e o
número. Ajuste a expectativa do teste para o caractere real produzido pelo
runtime, e não o contrário.

- [ ] **Step 5: Commit**

```bash
git add ui/src/components/dashboard/EmendasTable.tsx \
        ui/src/components/dashboard/EmendasTable.test.tsx
git commit -m "feat(emendas): tabela de emendas do parlamentar"
```

---

### Task 5: Aba no perfil e resumo no card de estatísticas

**Files:**
- Modify: `ui/src/pages/ParlamentarDashboard.tsx`
- Modify: `ui/src/components/dashboard/EstatisticasCard.tsx`
- Test: `ui/src/components/dashboard/EstatisticasCard.test.tsx`

**Interfaces:**
- Consumes: `EmendasTable` (Task 4), `getAmendmentsSummary` (Task 3)
- Produces: `EstatisticasCard` passa a aceitar a prop opcional `amendmentsSummary?: AmendmentSummaryOut` e `amendmentsYear?: number`

- [ ] **Step 1: Escreva o teste que falha**

Crie `ui/src/components/dashboard/EstatisticasCard.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { EstatisticasCard } from './EstatisticasCard';

const STATS = {
  propositions_this_week: 120,
  attendance_avg_percent: 91,
  recent_votes_count: 340,
  speeches_count: 88,
};

describe('EstatisticasCard', () => {
  it('mantem os quatro indicadores existentes', () => {
    render(<EstatisticasCard stats={STATS} />);
    expect(screen.getByText('120')).toBeInTheDocument();
    expect(screen.getByText('91%')).toBeInTheDocument();
    expect(screen.getByText('340')).toBeInTheDocument();
    expect(screen.getByText('88')).toBeInTheDocument();
  });

  it('mostra o bloco de emendas quando ha resumo', () => {
    render(
      <EstatisticasCard
        stats={STATS}
        amendmentsYear={2026}
        amendmentsSummary={{
          year: 2026,
          count: 12,
          committed_total: '12500000.00',
          paid_total: '3100000.00',
        }}
      />
    );
    expect(screen.getByText(/emendas 2026/i)).toBeInTheDocument();
    expect(screen.getByText(/destinado/i)).toBeInTheDocument();
    expect(screen.getByText(/pago/i)).toBeInTheDocument();
  });

  it('omite o bloco de emendas quando nao ha resumo', () => {
    render(<EstatisticasCard stats={STATS} />);
    expect(screen.queryByText(/emendas/i)).not.toBeInTheDocument();
  });

  it('mostra o bloco com zero quando o parlamentar nao tem emenda', () => {
    render(
      <EstatisticasCard
        stats={STATS}
        amendmentsYear={2026}
        amendmentsSummary={{
          year: 2026,
          count: 0,
          committed_total: '0.00',
          paid_total: '0.00',
        }}
      />
    );
    // Zero explicito e informacao; ausencia de bloco seria ambigua.
    expect(screen.getByText(/emendas 2026/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Rode o teste e confirme que falha**

Run: `cd ui && npm run test -- EstatisticasCard`
Expected: FAIL — os três últimos testes falham; o componente ainda não aceita
`amendmentsSummary`.

- [ ] **Step 3: Estenda o card**

Em `ui/src/components/dashboard/EstatisticasCard.tsx`, altere a interface de
props e acrescente o bloco. O bloco vai **abaixo** da fileira de círculos, e não
como quinto círculo: os círculos têm 49 px e não comportam um valor monetário.

```tsx
import type { AmendmentSummaryOut, DashboardStatsOut } from '@/api/types';

interface EstatisticasCardProps {
  stats?: DashboardStatsOut;
  isLoading?: boolean;
  amendmentsSummary?: AmendmentSummaryOut;
  amendmentsYear?: number;
}

const BRL_COMPACT = new Intl.NumberFormat('pt-BR', {
  style: 'currency',
  currency: 'BRL',
  notation: 'compact',
  maximumFractionDigits: 1,
});

function formatCompactBRL(value?: string | null): string {
  if (value == null || value === '') return '—';
  const parsed = Number(value);
  return Number.isFinite(parsed) ? BRL_COMPACT.format(parsed) : '—';
}
```

E, dentro do `return`, logo depois do `</div>` que fecha a fileira de círculos e
antes do `</div>` que fecha o card:

```tsx
      {amendmentsSummary != null && (
        <div className="mt-6 border-t border-black/[0.08] pt-4">
          <p className="text-[13px] font-semibold uppercase tracking-wide text-[#383838]">
            Emendas {amendmentsYear ?? amendmentsSummary.year ?? ''}
          </p>
          <div className="mt-2 flex items-start justify-between gap-4">
            <div>
              <p className="text-[18px] font-bold text-[#468fff]">
                {formatCompactBRL(amendmentsSummary.committed_total)}
              </p>
              <p className="text-[13px] text-[#383838]">Destinado</p>
            </div>
            <div>
              <p className="text-[18px] font-bold text-[#468fff]">
                {formatCompactBRL(amendmentsSummary.paid_total)}
              </p>
              <p className="text-[13px] text-[#383838]">Pago</p>
            </div>
          </div>
        </div>
      )}
```

- [ ] **Step 4: Ligue a aba e o resumo no perfil**

Em `ui/src/pages/ParlamentarDashboard.tsx`:

Acrescente o import junto dos demais componentes de dashboard (por volta da
linha 13):

```tsx
import { EmendasTable } from '@/components/dashboard/EmendasTable';
```

e a função de cliente junto das outras (linha 17-21):

```tsx
  getAmendmentsSummary,
```

Depois de `dashboardStatsQuery` (linha 78-82), acrescente:

```tsx
  const emendasYear = new Date().getFullYear();
  const amendmentsSummaryQuery = useQuery({
    queryKey: ['amendments-summary', numericId, emendasYear],
    queryFn: () => getAmendmentsSummary(numericId, emendasYear),
    enabled: isIdValid,
  });
```

Na linha 179, passe as props novas ao card:

```tsx
            <EstatisticasCard
              stats={dashboardStatsQuery.data}
              isLoading={dashboardStatsQuery.isLoading}
              amendmentsSummary={amendmentsSummaryQuery.data}
              amendmentsYear={emendasYear}
            />
```

Na `TabsList` (linha 208-218), acrescente o gatilho depois de TAQUIGRÁFICAS:

```tsx
                  <TabsTrigger value="emendas" className={parlamentarSectionTabTriggerClass}>
                    EMENDAS
                  </TabsTrigger>
```

E, depois do `TabsContent` de `taquigraficas` (linha 228-230), o conteúdo:

```tsx
            <TabsContent value="emendas" className="mt-0 p-6 pt-4 h-[500px]">
              <EmendasTable parliamentarianId={numericId} year={emendasYear} />
            </TabsContent>
```

- [ ] **Step 5: Rode os testes e confirme que passam**

Run: `cd ui && npm run test -- EstatisticasCard`
Expected: PASS — 4 testes.

Run: `cd ui && npm run test`
Expected: PASS — a suíte inteira, incluindo os testes já existentes do perfil.

Run: `cd ui && npx tsc --noEmit`
Expected: sem erros.

- [ ] **Step 6: Commit**

```bash
git add ui/src/pages/ParlamentarDashboard.tsx \
        ui/src/components/dashboard/EstatisticasCard.tsx \
        ui/src/components/dashboard/EstatisticasCard.test.tsx
git commit -m "feat(emendas): aba de emendas no perfil e resumo anual no card de estatisticas"
```

---

### Task 6: Painel administrativo das emendas não casadas

**Files:**
- Create: `ui/src/pages/AdminEmendasPage.tsx`
- Modify: `ui/src/App.tsx` (rota)
- Modify: `ui/src/pages/AdminPage.tsx` (card)
- Test: `ui/src/pages/AdminEmendasPage.test.tsx`

**Interfaces:**
- Consumes: `listUnmatchedAmendmentAuthors` (Task 3)
- Produces: rota `/admin/emendas-nao-casadas`

Leia `ui/src/pages/AdminCoveragePage.tsx` antes: o `AdminShell`, o cabeçalho e o
tratamento de carregamento saem dali.

- [ ] **Step 1: Escreva o teste que falha**

Crie `ui/src/pages/AdminEmendasPage.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import AdminEmendasPage from './AdminEmendasPage';
import * as adminApi from '@/api/admin';

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AdminEmendasPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('AdminEmendasPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('lista os autores nao casados com contagem e valor', async () => {
    vi.spyOn(adminApi, 'listUnmatchedAmendmentAuthors').mockResolvedValue([
      {
        author_name_raw: 'Fulano Sem Par',
        amendment_count: 3,
        committed_total: '3000.00',
        match_status: 'unmatched',
      },
    ]);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Fulano Sem Par')).toBeInTheDocument();
    });
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('R$ 3.000,00')).toBeInTheDocument();
  });

  it('mostra estado vazio quando tudo casou', async () => {
    vi.spyOn(adminApi, 'listUnmatchedAmendmentAuthors').mockResolvedValue([]);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/todas as emendas casaram/i)).toBeInTheDocument();
    });
  });
});
```

- [ ] **Step 2: Rode o teste e confirme que falha**

Run: `cd ui && npm run test -- AdminEmendasPage`
Expected: FAIL — módulo não encontrado.

- [ ] **Step 3: Implemente a página**

Crie `ui/src/pages/AdminEmendasPage.tsx`:

```tsx
import { useQuery } from '@tanstack/react-query';
import { AdminShell } from '@/components/layout/AdminShell';
import { listUnmatchedAmendmentAuthors } from '@/api/admin';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Loader2 } from 'lucide-react';

const BRL = new Intl.NumberFormat('pt-BR', {
  style: 'currency',
  currency: 'BRL',
});

function formatBRL(value: string): string {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? BRL.format(parsed) : '—';
}

const STATUS_LABEL: Record<string, string> = {
  unmatched: 'Sem correspondência',
  ambiguous: 'Homônimo',
};

export default function AdminEmendasPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['admin', 'amendments', 'unmatched'],
    queryFn: () => listUnmatchedAmendmentAuthors(),
  });

  return (
    <AdminShell footer="mammoth">
      <div>
        <h1 className="text-[36px] font-bold leading-none text-[#393939] md:text-[48px]">
          Emendas não casadas
        </h1>
        <p className="mt-1 text-[18px] font-normal text-[#383838]">
          O Portal da Transparência publica o autor da emenda apenas como texto.
          Estes nomes não corresponderam a nenhum parlamentar da base.
        </p>
      </div>

      <div className="mp-card bg-white p-6">
        {isLoading && (
          <div className="flex items-center justify-center gap-2 py-10 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            <span>Carregando...</span>
          </div>
        )}

        {isError && (
          <p className="py-10 text-center text-muted-foreground">
            Falha ao carregar a auditoria de emendas.
          </p>
        )}

        {!isLoading && !isError && (!data || data.length === 0) && (
          <p className="py-10 text-center text-muted-foreground">
            Todas as emendas casaram com algum parlamentar.
          </p>
        )}

        {data && data.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Autor (como veio da fonte)</TableHead>
                <TableHead>Motivo</TableHead>
                <TableHead className="text-right">Emendas</TableHead>
                <TableHead className="text-right">Valor empenhado</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((linha) => (
                <TableRow key={`${linha.author_name_raw}-${linha.match_status}`}>
                  <TableCell>{linha.author_name_raw ?? '—'}</TableCell>
                  <TableCell>
                    {STATUS_LABEL[linha.match_status] ?? linha.match_status}
                  </TableCell>
                  <TableCell className="text-right">{linha.amendment_count}</TableCell>
                  <TableCell className="whitespace-nowrap text-right">
                    {formatBRL(linha.committed_total)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
    </AdminShell>
  );
}
```

- [ ] **Step 4: Registre a rota e o card**

Em `ui/src/App.tsx`, importe a página junto dos demais imports de página e
acrescente a rota **depois** do bloco `/admin/coverage` (linha 198-205) e
**antes** do comentário `{/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}`
da linha 206:

```tsx
              <Route
                path="/admin/emendas-nao-casadas"
                element={
                  <RequireAdmin>
                    <AdminEmendasPage />
                  </RequireAdmin>
                }
              />
```

O `RequireAdmin` não é opcional: sem ele a rota fica acessível a qualquer membro
autenticado, e a auditoria expõe nomes que a fonte publicou mas o sistema não
soube resolver.

Em `ui/src/pages/AdminPage.tsx`, acrescente ao array `PANELS`:

```tsx
  {
    to: '/admin/emendas-nao-casadas',
    title: 'Emendas não casadas',
    desc: 'Autores de emenda que não corresponderam a nenhum parlamentar da base.',
    icon: FileSearch,
    available: true,
  },
```

e importe `FileSearch` de `lucide-react` na linha 2, junto dos demais ícones.

- [ ] **Step 5: Rode os testes e confirme que passam**

Run: `cd ui && npm run test -- AdminEmendasPage`
Expected: PASS — 2 testes.

Run: `cd ui && npm run test && npx tsc --noEmit`
Expected: PASS, sem erros de tipo.

Run: `python3 scripts/check_ui_api_contract.py`
Expected: OK.

- [ ] **Step 6: Commit**

```bash
git add ui/src/pages/AdminEmendasPage.tsx ui/src/pages/AdminEmendasPage.test.tsx \
        ui/src/App.tsx ui/src/pages/AdminPage.tsx
git commit -m "feat(emendas): painel admin de auditoria das emendas nao casadas"
```

---

### Task 7: Documentação

**Files:**
- Modify: `CONTEXT.md`
- Modify: `mamute_scrappers/README.md`

**Interfaces:**
- Consumes: tudo que os dois planos construíram
- Produces: nenhum código

`CONTEXT.md` é o glossário de domínio único do repositório, declarado em
`AGENTS.md` como a fonte de verdade do domínio. Um dado novo que não entra ali
fica invisível para quem chegar depois — inclusive para agentes.

- [ ] **Step 1: Acrescente o termo ao glossário**

Em `CONTEXT.md`, depois da seção "Committee Attendance" (linha 41-43),
acrescente:

```markdown
### Parliamentary Amendment

A budget amendment (*emenda parlamentar orçamentária*) through which a
parliamentarian directs federal funds, stored in `parliamentary_amendment`.
Collected from the Portal da Transparência, which identifies the author only by
free-text name — so `parliamentarian_id` is nullable and `match_status` records
whether the name resolved to a parliamentarian, resolved ambiguously, or not at
all. Not to be confused with an amendment to a proposition, which alters the
text of a bill.
```

- [ ] **Step 2: Documente o crawler**

Em `mamute_scrappers/README.md`, dentro de "Execução dos programas principais"
(linha 49 em diante), acrescente uma subseção no mesmo formato das vizinhas —
título `###` seguido de bloco de comandos comentados:

````markdown
### Coleta de emendas parlamentares (Portal da Transparência)

Exige `PORTAL_TRANSPARENCIA_API_KEY` no `.env`. Cadastro gratuito em
portaldatransparencia.gov.br/api-de-dados/cadastrar-email. O limite é por chave,
na casa de 30 requisições por minuto fora da madrugada.

```bash
# ano corrente, persistindo no banco
python -m mamute_scrappers.portal_crawler.emendas

# ano específico
python -m mamute_scrappers.portal_crawler.emendas --ano 2025

# diagnóstico: não persiste, reporta a taxa de casamento por nome
python -m mamute_scrappers.portal_crawler.emendas --ano 2026 --dry-run --limit 500

# backfill 2022 -> ano corrente (auto-encerra quando a fila zera)
python -m mamute_scrappers.scripts.backfill_emendas --chunks-per-run 2
python -m mamute_scrappers.scripts.backfill_emendas --status
```
````

- [ ] **Step 3: Commit**

```bash
git add CONTEXT.md mamute_scrappers/README.md
git commit -m "docs(emendas): registra emenda orcamentaria no glossario de dominio"
```

---

## Encerramento do Plano 2

Ao fim das sete tasks, o CS-17 está fechado nos três critérios de aceite do
ticket:

- Emendas coletadas via API pública (Plano 1)
- Emendas cruzadas com a base de parlamentares, com o resíduo visível em vez de descartado
- Emendas exibidas na área de perfil do parlamentar

**Antes de abrir o PR**, rode a bateria completa:

```bash
pytest api/tests/ -v
pytest mamute_scrappers/tests/ -v
python3 scripts/check_ui_api_contract.py
cd ui && npm run test && npx tsc --noEmit && npm run build
```

E confirme em ambiente de teste que a aba EMENDAS aparece com dado real, não só
com dado de teste.
