# Emendas: rótulo de tipo e prestação de contas (CS-56) — Plano de implementação (PR 2 de 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exibir o tipo de cada emenda (`Pix` / `Finalidade definida`) e, para as Pix, a prestação de contas dos entes beneficiários, ingerida da API pública do Transferegov.

**Architecture:** Crawler novo (`transferegov_crawler`) traz `plano_acao_especial` e os dois tipos de relatório de gestão, aplica precedência e grava numa tabela única `amendment_action_plan` com a prestação desnormalizada. A API expõe agregado na listagem de emendas e uma rota de detalhe consumida só quando a linha expande. A UI fica atrás de `useFeatureFlag('emendas_prestacao')`.

**Tech Stack:** Python 3 + SQLAlchemy 2.x + Alembic + `requests`, FastAPI, React 18 + TypeScript + TanStack Query + Vitest.

## Global Constraints

- Spec de referência: `docs/superpowers/specs/2026-08-12-emendas-tipo-e-prestacao-contas-design.md`.
- Depende da PR 1 (`feat/feature-flags`) estar mergeada. Branch nova a partir da `main` atualizada.
- Fonte: `https://api.transferegov.gestao.gov.br/transferenciasespeciais/` (PostgREST, **sem chave de API**).
- `numero_emenda_parlamentar_plano_acao` da fonte **é** o nosso `amendment_code`.
- Relação **1:N** — mediana de 8 planos por emenda, máximo medido 100, 57.827 planos no total.
- Valores monetários em `Numeric(18,2)` no banco e **string** na API. Nunca float.
- Precedência do relatório de gestão: **`Final` vence `Parcial`; mesmo tipo, vence o mais recente por data; `novo` vence `legado`.**
- A tela **nunca** diz "não prestou contas". Ano corrente sem prestação = "prazo aberto".
- Comentários e docstrings em português, sem acento em identificador.

---

### Task 1: Tabela `amendment_action_plan`

**Files:**
- Create: `mamute_scrappers/migrations/versions/b2c3d4e5f6a8_add_amendment_action_plan.py`
- Create: `mamute_scrappers/db/models/amendment_action_plan.py`
- Create: `api/db/models/amendment_action_plan.py`
- Modify: `mamute_scrappers/db/models/__init__.py`, `api/db/models/__init__.py`

**Interfaces:**
- Produces: modelo `AmendmentActionPlan` com os campos listados abaixo.

- [ ] **Step 1: Criar o modelo**

```python
"""Plano de acao de emenda Pix (transferencia especial), do Transferegov.

Uma emenda Pix se desdobra em varios planos de acao, um por ente beneficiario
— mediana de 8, maximo medido 100. Por isso esta tabela e 1:N com
`parliamentary_amendment`.

A prestacao de contas vem desnormalizada: a fonte tem 1,02 relatorio por
plano, entao guardar o mais forte basta. A regra de precedencia esta em
`transferegov_crawler.action_plans.escolher_relatorio`.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger, Column, DateTime, ForeignKey, Integer, Numeric, Text,
)
from sqlalchemy.sql import func

from ..base import Base


class AmendmentActionPlan(Base):
    __tablename__ = "amendment_action_plan"

    # Chave natural da fonte: o upsert casa por ela.
    id_plano_acao = Column(BigInteger, primary_key=True)
    codigo_plano_acao = Column(Text)

    # SET NULL como em parliamentary_amendment.parliamentarian_id: o plano de
    # acao e fato publico e nao deve sumir se a emenda sair da base.
    amendment_code = Column(
        Text,
        ForeignKey("parliamentary_amendment.amendment_code", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    ano = Column(Integer, index=True)
    situacao = Column(Text)

    beneficiario_nome = Column(Text)
    beneficiario_cnpj = Column(Text)
    beneficiario_uf = Column(Text)

    valor_custeio = Column(Numeric(18, 2))
    valor_investimento = Column(Numeric(18, 2))

    prestacao_situacao = Column(Text)
    prestacao_tipo = Column(Text)
    prestacao_valor_executado = Column(Numeric(18, 2))
    prestacao_valor_pendente = Column(Numeric(18, 2))
    prestacao_data = Column(DateTime(timezone=True))
    prestacao_origem = Column(Text)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


__all__ = ["AmendmentActionPlan"]
```

Copiar idêntico para `api/db/models/amendment_action_plan.py` e registrar nos dois `__init__.py` (import + `__all__`, ordem alfabética — vai logo depois de `.agency`).

- [ ] **Step 2: Criar a migration**

`down_revision` = head atual da `main` após a PR 1 (`a1b2c3d4e5f6`). Confirmar com o script de heads antes de escrever.

```python
"""add amendment_action_plan

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f6
"""

from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a8"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "amendment_action_plan",
        sa.Column("id_plano_acao", sa.BigInteger(), primary_key=True),
        sa.Column("codigo_plano_acao", sa.Text()),
        sa.Column("amendment_code", sa.Text(), nullable=True),
        sa.Column("ano", sa.Integer()),
        sa.Column("situacao", sa.Text()),
        sa.Column("beneficiario_nome", sa.Text()),
        sa.Column("beneficiario_cnpj", sa.Text()),
        sa.Column("beneficiario_uf", sa.Text()),
        sa.Column("valor_custeio", sa.Numeric(18, 2)),
        sa.Column("valor_investimento", sa.Numeric(18, 2)),
        sa.Column("prestacao_situacao", sa.Text()),
        sa.Column("prestacao_tipo", sa.Text()),
        sa.Column("prestacao_valor_executado", sa.Numeric(18, 2)),
        sa.Column("prestacao_valor_pendente", sa.Numeric(18, 2)),
        sa.Column("prestacao_data", sa.DateTime(timezone=True)),
        sa.Column("prestacao_origem", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["amendment_code"],
            ["parliamentary_amendment.amendment_code"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_amendment_action_plan_amendment_code",
        "amendment_action_plan", ["amendment_code"],
    )
    op.create_index(
        "ix_amendment_action_plan_ano", "amendment_action_plan", ["ano"]
    )


def downgrade() -> None:
    op.drop_table("amendment_action_plan")
```

- [ ] **Step 3: Verificar head único do Alembic** (mesmo script da PR 1, Task 1 Step 5)

Expected: `heads: ['b2c3d4e5f6a8']`.

- [ ] **Step 4: Commit**

```bash
git add mamute_scrappers/migrations/versions/b2c3d4e5f6a8_add_amendment_action_plan.py \
        mamute_scrappers/db/models/amendment_action_plan.py \
        api/db/models/amendment_action_plan.py \
        mamute_scrappers/db/models/__init__.py api/db/models/__init__.py
git commit -m "feat(emendas): tabela amendment_action_plan (planos de acao Pix)"
```

---

### Task 2: Cliente do Transferegov

**Files:**
- Create: `mamute_scrappers/transferegov_crawler/__init__.py`
- Create: `mamute_scrappers/transferegov_crawler/client.py`
- Test: `mamute_scrappers/tests/test_transferegov_client.py`

**Interfaces:**
- Produces: `TransferegovClient` com
  - `iter_rows(tabela: str, select: str | None = None, page_size: int = 1000) -> Iterator[dict]`
  - `fetch_in(tabela: str, coluna: str, valores: list, chunk: int = 100) -> list[dict]`

- [ ] **Step 1: Escrever os testes que falham**

```python
"""Cliente PostgREST do Transferegov. Sem chave de API."""
from __future__ import annotations

from mamute_scrappers.transferegov_crawler.client import TransferegovClient


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(f"HTTP {self.status_code}")


def test_iter_rows_pagina_ate_esgotar(monkeypatch):
    paginas = [[{"id": 1}, {"id": 2}], [{"id": 3}], []]
    chamadas = []

    def fake_get(url, params=None, timeout=None, headers=None):
        chamadas.append(params)
        return _FakeResponse(paginas[len(chamadas) - 1])

    client = TransferegovClient()
    monkeypatch.setattr(client._session, "get", fake_get)

    linhas = list(client.iter_rows("plano_acao_especial", page_size=2))
    assert [x["id"] for x in linhas] == [1, 2, 3]
    assert chamadas[0]["offset"] == 0
    assert chamadas[1]["offset"] == 2


def test_fetch_in_quebra_em_lotes(monkeypatch):
    recebidos = []

    def fake_get(url, params=None, timeout=None, headers=None):
        recebidos.append(params["id_plano_acao"])
        return _FakeResponse([])

    client = TransferegovClient()
    monkeypatch.setattr(client._session, "get", fake_get)

    client.fetch_in("relatorio_gestao_especial", "id_plano_acao", [1, 2, 3], chunk=2)
    assert recebidos == ["in.(1,2)", "in.(3)"]
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `python -m pytest mamute_scrappers/tests/test_transferegov_client.py -v`
Expected: FAIL — módulo não existe.

- [ ] **Step 3: Implementar o cliente**

```python
"""Cliente da API publica de Transferencias Especiais do Transferegov.

PostgREST, sem chave de API. So o modulo `transferenciasespeciais` existe: o
de Discricionarias e Legais (que cobriria as emendas de Finalidade Definida)
ainda nao tem API — a 1a entrega esta prevista para 10/2026.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterator, List, Optional, Sequence

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://api.transferegov.gestao.gov.br/transferenciasespeciais"
TIMEOUT = 90


class TransferegovClient:
    def __init__(self, base_url: str = BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")
        self._session = requests.Session()

    def iter_rows(
        self,
        tabela: str,
        select: Optional[str] = None,
        page_size: int = 1000,
    ) -> Iterator[Dict[str, Any]]:
        """Percorre a tabela inteira paginando por limit/offset."""
        offset = 0
        while True:
            params: Dict[str, Any] = {"limit": page_size, "offset": offset}
            if select:
                params["select"] = select
            resposta = self._session.get(
                f"{self.base_url}/{tabela}", params=params, timeout=TIMEOUT
            )
            resposta.raise_for_status()
            linhas = resposta.json()
            if not linhas:
                return
            for linha in linhas:
                yield linha
            if len(linhas) < page_size:
                return
            offset += page_size

    def fetch_in(
        self,
        tabela: str,
        coluna: str,
        valores: Sequence[Any],
        chunk: int = 100,
    ) -> List[Dict[str, Any]]:
        """Busca linhas cujo `coluna` esta na lista, em lotes.

        Lote existe porque o filtro `in.()` do PostgREST vai na query string e
        estoura o limite de URL com milhares de ids.
        """
        resultado: List[Dict[str, Any]] = []
        for i in range(0, len(valores), chunk):
            lote = valores[i : i + chunk]
            filtro = "in.(%s)" % ",".join(str(v) for v in lote)
            resposta = self._session.get(
                f"{self.base_url}/{tabela}",
                params={coluna: filtro},
                timeout=TIMEOUT,
            )
            resposta.raise_for_status()
            resultado.extend(resposta.json())
        return resultado
```

- [ ] **Step 4: Rodar os testes** → PASS

- [ ] **Step 5: Commit**

```bash
git add mamute_scrappers/transferegov_crawler/ mamute_scrappers/tests/test_transferegov_client.py
git commit -m "feat(transferegov): cliente PostgREST paginado"
```

---

### Task 3: Precedência do relatório de gestão

**Files:**
- Create: `mamute_scrappers/transferegov_crawler/action_plans.py` (parte 1)
- Test: `mamute_scrappers/tests/test_transferegov_action_plans.py`

**Interfaces:**
- Produces:
  - `escolher_relatorio(relatorios: list[dict]) -> dict | None`
  - `build_plan_payload(plano: dict, relatorio: dict | None) -> dict`

Cada relatório entra normalizado como `{"origem": "novo"|"legado", "situacao": str|None, "tipo": str|None, "valor_executado": Decimal|None, "valor_pendente": Decimal|None, "data": str|None}`.

- [ ] **Step 1: Escrever os testes que falham**

```python
"""Precedencia do relatorio de gestao e montagem do payload do plano."""
from __future__ import annotations

from decimal import Decimal

from mamute_scrappers.transferegov_crawler.action_plans import (
    build_plan_payload,
    escolher_relatorio,
)


def _rel(origem="novo", tipo="Parcial", data="2024-01-01T00:00:00", situacao="DISPONIBILIZADO"):
    return {
        "origem": origem, "tipo": tipo, "data": data, "situacao": situacao,
        "valor_executado": Decimal("10.00"), "valor_pendente": Decimal("0.00"),
    }


def test_sem_relatorio_devolve_none():
    assert escolher_relatorio([]) is None


def test_final_vence_parcial():
    escolhido = escolher_relatorio([
        _rel(tipo="Parcial", data="2025-01-01T00:00:00"),
        _rel(tipo="Final", data="2024-01-01T00:00:00"),
    ])
    assert escolhido["tipo"] == "Final"


def test_mesmo_tipo_vence_o_mais_recente():
    escolhido = escolher_relatorio([
        _rel(tipo="Parcial", data="2024-01-01T00:00:00"),
        _rel(tipo="Parcial", data="2025-06-01T00:00:00"),
    ])
    assert escolhido["data"] == "2025-06-01T00:00:00"


def test_novo_vence_legado_no_mesmo_tipo_e_data():
    escolhido = escolher_relatorio([
        _rel(origem="legado", tipo="Final", data=None),
        _rel(origem="novo", tipo="Final", data=None),
    ])
    assert escolhido["origem"] == "novo"


def test_legado_sem_tipo_nao_quebra():
    """O relatorio legado nao tem campo `tipo`; entra como None."""
    escolhido = escolher_relatorio([_rel(origem="legado", tipo=None, data=None)])
    assert escolhido["origem"] == "legado"


def test_payload_sem_relatorio_deixa_prestacao_nula():
    plano = {
        "id_plano_acao": 1, "codigo_plano_acao": "0903-000001",
        "numero_emenda_parlamentar_plano_acao": "202444660013",
        "ano_plano_acao": 2024, "situacao_plano_acao": "CIENTE",
        "nome_beneficiario_plano_acao": "MUNICIPIO X",
        "cnpj_beneficiario_plano_acao": "00000000000191",
        "uf_beneficiario_plano_acao": "MS",
        "valor_custeio_plano_acao": 0.0,
        "valor_investimento_plano_acao": 1798000.0,
    }
    payload = build_plan_payload(plano, None)
    assert payload["amendment_code"] == "202444660013"
    assert payload["valor_investimento"] == Decimal("1798000.00")
    assert payload["prestacao_situacao"] is None
    assert payload["prestacao_origem"] is None


def test_payload_converte_valores_para_decimal_sem_float():
    plano = {"id_plano_acao": 2, "valor_custeio_plano_acao": 0.1}
    payload = build_plan_payload(plano, None)
    assert payload["valor_custeio"] == Decimal("0.10")
```

- [ ] **Step 2: Rodar e confirmar que falha** → FAIL (módulo não existe)

- [ ] **Step 3: Implementar**

```python
"""Coleta dos planos de acao de emendas Pix e da prestacao de contas.

A fonte tem duas tabelas de prestacao: `relatorio_gestao_novo_especial` (o
regime atual, 42,8% dos planos) e `relatorio_gestao_especial` (legado, 6,4%,
seca a partir de 2025). Uniao medida: 44,2% dos planos.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

CENTS = Decimal("0.01")


def _to_decimal(value: Any) -> Optional[Decimal]:
    """Converte para Decimal com 2 casas, passando por str.

    Passar por str evita a expansao binaria de Decimal(float): a fonte manda
    numero JSON, e dinheiro publico nao pode perder centavo.
    """
    if value is None:
        return None
    try:
        return Decimal(str(value)).quantize(CENTS)
    except (InvalidOperation, ValueError):
        return None


def _texto(value: Any) -> Optional[str]:
    if value is None:
        return None
    limpo = " ".join(str(value).split())
    return limpo or None


def escolher_relatorio(relatorios: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """O relatorio mais forte do plano.

    Precedencia: `Final` vence `Parcial`; mesmo tipo, vence o mais recente por
    data; empatado nisso, `novo` vence `legado`. Guardar so o mais forte basta
    porque a fonte tem 1,02 relatorio por plano.
    """
    if not relatorios:
        return None

    def chave(r: Dict[str, Any]) -> tuple:
        return (
            1 if (r.get("tipo") or "").strip().lower() == "final" else 0,
            r.get("data") or "",
            1 if r.get("origem") == "novo" else 0,
        )

    return max(relatorios, key=chave)


def build_plan_payload(
    plano: Dict[str, Any], relatorio: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """Converte o plano cru da fonte na linha que a tabela espera."""
    return {
        "id_plano_acao": plano.get("id_plano_acao"),
        "codigo_plano_acao": _texto(plano.get("codigo_plano_acao")),
        "amendment_code": _texto(plano.get("numero_emenda_parlamentar_plano_acao")),
        "ano": plano.get("ano_plano_acao"),
        "situacao": _texto(plano.get("situacao_plano_acao")),
        "beneficiario_nome": _texto(plano.get("nome_beneficiario_plano_acao")),
        "beneficiario_cnpj": _texto(plano.get("cnpj_beneficiario_plano_acao")),
        "beneficiario_uf": _texto(plano.get("uf_beneficiario_plano_acao")),
        "valor_custeio": _to_decimal(plano.get("valor_custeio_plano_acao")),
        "valor_investimento": _to_decimal(plano.get("valor_investimento_plano_acao")),
        "prestacao_situacao": _texto(relatorio.get("situacao")) if relatorio else None,
        "prestacao_tipo": _texto(relatorio.get("tipo")) if relatorio else None,
        "prestacao_valor_executado": relatorio.get("valor_executado") if relatorio else None,
        "prestacao_valor_pendente": relatorio.get("valor_pendente") if relatorio else None,
        "prestacao_data": relatorio.get("data") if relatorio else None,
        "prestacao_origem": relatorio.get("origem") if relatorio else None,
    }
```

- [ ] **Step 4: Rodar os testes** → PASS

- [ ] **Step 5: Commit**

```bash
git add mamute_scrappers/transferegov_crawler/action_plans.py \
        mamute_scrappers/tests/test_transferegov_action_plans.py
git commit -m "feat(transferegov): precedencia do relatorio de gestao"
```

---

### Task 4: Upsert e orquestração da coleta

**Files:**
- Modify: `mamute_scrappers/transferegov_crawler/action_plans.py`
- Test: `mamute_scrappers/tests/test_transferegov_action_plans.py` (ampliar)

**Interfaces:**
- Consumes: `TransferegovClient` (T2), `escolher_relatorio`/`build_plan_payload` (T3).
- Produces:
  - `normalizar_relatorios(novos: list[dict], legados: list[dict]) -> dict[int, list[dict]]` — indexado por `id_plano_acao`.
  - `upsert_plan(session, payload: dict) -> tuple[Any, bool]` — `(linha, criada)`.
  - `coletar(client=None, persist=True, limite=None) -> dict` — resumo com contadores.
  - `main()` para `python -m mamute_scrappers.transferegov_crawler.action_plans`.

- [ ] **Step 1: Escrever os testes que falham**

Seguir o padrão de `mamute_scrappers/tests/test_emendas_upsert.py` (modelo declarativo local + SQLite in-memory):

```python
def test_normalizar_relatorios_une_as_duas_tabelas():
    novos = [{
        "id_plano_acao": 1, "tipo_relatorio_gestao_novo": "Final",
        "situacao_relatorio_gestao_novo": "DISPONIBILIZADO",
        "valor_executado_relatorio_gestao_novo": 325098.88,
        "valor_pendente_relatorio_gestao_novo": 0.0,
        "data_e_hora_relatorio_gestao_novo": "2024-12-23T10:47:09",
    }]
    legados = [{"id_plano_acao": 2, "situacao_relatorio_gestao": "EM_ELABORACAO"}]
    idx = normalizar_relatorios(novos, legados)
    assert idx[1][0]["origem"] == "novo"
    assert idx[1][0]["valor_executado"] == Decimal("325098.88")
    assert idx[2][0]["origem"] == "legado"
    assert idx[2][0]["tipo"] is None


def test_upsert_idempotente(session):
    payload = build_plan_payload({"id_plano_acao": 9, "ano_plano_acao": 2024}, None)
    _, criada = upsert_plan(session, payload)
    assert criada is True
    _, criada = upsert_plan(session, payload)
    assert criada is False
    assert session.query(AmendmentActionPlanTest).count() == 1


def test_upsert_atualiza_prestacao_quando_ela_aparece(session):
    base = build_plan_payload({"id_plano_acao": 10}, None)
    upsert_plan(session, base)
    com_rel = build_plan_payload({"id_plano_acao": 10}, {
        "origem": "novo", "tipo": "Final", "situacao": "DISPONIBILIZADO",
        "valor_executado": Decimal("50.00"), "valor_pendente": None, "data": None,
    })
    upsert_plan(session, com_rel)
    linha = session.get(AmendmentActionPlanTest, 10)
    assert linha.prestacao_tipo == "Final"
```

- [ ] **Step 2: Rodar e confirmar que falha**

- [ ] **Step 3: Implementar**

Acrescentar a `action_plans.py`:

```python
CAMPOS_NOVO = {
    "situacao": "situacao_relatorio_gestao_novo",
    "tipo": "tipo_relatorio_gestao_novo",
    "valor_executado": "valor_executado_relatorio_gestao_novo",
    "valor_pendente": "valor_pendente_relatorio_gestao_novo",
    "data": "data_e_hora_relatorio_gestao_novo",
}

COMMIT_EVERY = 500

_ATUALIZAVEIS = (
    "codigo_plano_acao", "amendment_code", "ano", "situacao",
    "beneficiario_nome", "beneficiario_cnpj", "beneficiario_uf",
    "valor_custeio", "valor_investimento",
    "prestacao_situacao", "prestacao_tipo", "prestacao_valor_executado",
    "prestacao_valor_pendente", "prestacao_data", "prestacao_origem",
)


def normalizar_relatorios(novos, legados):
    """Indexa os relatorios das duas tabelas por id_plano_acao."""
    idx: Dict[int, List[Dict[str, Any]]] = {}
    for linha in novos or []:
        idx.setdefault(linha["id_plano_acao"], []).append({
            "origem": "novo",
            "situacao": linha.get(CAMPOS_NOVO["situacao"]),
            "tipo": linha.get(CAMPOS_NOVO["tipo"]),
            "valor_executado": _to_decimal(linha.get(CAMPOS_NOVO["valor_executado"])),
            "valor_pendente": _to_decimal(linha.get(CAMPOS_NOVO["valor_pendente"])),
            "data": linha.get(CAMPOS_NOVO["data"]),
        })
    for linha in legados or []:
        # O legado nao tem tipo, valor nem data: so situacao.
        idx.setdefault(linha["id_plano_acao"], []).append({
            "origem": "legado",
            "situacao": linha.get("situacao_relatorio_gestao"),
            "tipo": None, "valor_executado": None,
            "valor_pendente": None, "data": None,
        })
    return idx


def upsert_plan(session, payload):
    """Grava ou atualiza um plano, casando pela chave natural da fonte."""
    from mamute_scrappers.db.models import AmendmentActionPlan

    registro = session.get(AmendmentActionPlan, payload["id_plano_acao"])
    if registro is None:
        registro = AmendmentActionPlan(**payload)
        session.add(registro)
        return registro, True

    for campo in _ATUALIZAVEIS:
        setattr(registro, campo, payload.get(campo))
    return registro, False
```

E a orquestração `coletar()`, que: busca todos os planos com `iter_rows`, coleta os ids, busca os dois tipos de relatório com `fetch_in`, normaliza, escolhe, monta payload, faz upsert com commit parcial a cada `COMMIT_EVERY`, e loga o resumo — incluindo **quantos planos vieram com `amendment_code` que não existe em `parliamentary_amendment`** (gravados mesmo assim, com FK nula, porque a coleta do Portal pode estar atrás).

- [ ] **Step 4: Rodar os testes** → PASS

- [ ] **Step 5: Smoke test contra a fonte real, sem gravar**

Run: `python -m mamute_scrappers.transferegov_crawler.action_plans --dry-run --limite 200`
Expected: log com ~200 planos lidos, contagem de prestação preenchida > 0.

- [ ] **Step 6: Commit**

---

### Task 5: Cron

**Files:**
- Modify: `mamute_scrappers/docker/scrappers.cron`

- [ ] **Step 1: Adicionar a entrada**

Logo após a linha da coleta de emendas (hoje `50 6 * * *`), com atraso de 1h para a emenda já existir quando o plano tentar casar:

```cron
# Planos de acao das emendas Pix (Transferegov) + prestacao de contas.
# Roda depois da coleta de emendas: o plano casa por amendment_code, entao a
# emenda precisa existir primeiro.
50 7 * * * cd /app && /app/mamute_scrappers/docker/run-cron-job.sh transferegov-action-plans -- /usr/local/bin/python -m mamute_scrappers.transferegov_crawler.action_plans >> /proc/1/fd/1 2>> /proc/1/fd/2
```

- [ ] **Step 2: Commit**

---

### Task 6: API — agregado e rota de detalhe

**Files:**
- Modify: `api/routers/amendments.py`
- Test: `api/tests/test_amendment_action_plans.py`

**Interfaces:**
- Produces:
  - `AmendmentOut` com `planos_total: int`, `planos_com_prestacao: int`, `valor_executado_total: str`.
  - `GET /amendments/{amendment_code}/action-plans` → `list[ActionPlanOut]`.

- [ ] **Step 1: Escrever os testes que falham**

Padrão de `api/tests/test_amendments.py` (SQLite in-memory com DDL cru, incluindo a nova tabela):

```python
def test_agregado_conta_planos_e_prestacoes(client):
    r = client.get("/api/amendments/?parliamentarian_id=1")
    emenda = next(x for x in r.json() if x["amendment_code"] == "202444660013")
    assert emenda["planos_total"] == 8
    assert emenda["planos_com_prestacao"] == 5
    assert emenda["valor_executado_total"] == "445098.88"


def test_emenda_sem_plano_devolve_zeros_e_nao_null(client):
    r = client.get("/api/amendments/?parliamentarian_id=1")
    emenda = next(x for x in r.json() if x["amendment_code"] == "202600010001")
    assert emenda["planos_total"] == 0
    assert emenda["planos_com_prestacao"] == 0
    assert emenda["valor_executado_total"] == "0.00"


def test_rota_de_planos_lista_beneficiarios(client):
    r = client.get("/api/amendments/202444660013/action-plans")
    assert r.status_code == 200
    assert r.json()[0]["beneficiario_nome"] == "MUNICIPIO DE DOURADOS"


def test_rota_de_planos_devolve_vazio_e_nao_404(client):
    r = client.get("/api/amendments/202600010001/action-plans")
    assert r.status_code == 200
    assert r.json() == []
```

- [ ] **Step 2: Rodar e confirmar que falha**

- [ ] **Step 3: Implementar**

Em `list_amendments`, trocar o `select(ParliamentaryAmendment)` por um select com subquery agregada por `amendment_code`:

```python
agregado = (
    select(
        AmendmentActionPlan.amendment_code.label("code"),
        func.count(AmendmentActionPlan.id_plano_acao).label("planos_total"),
        func.count(AmendmentActionPlan.prestacao_situacao).label("com_prestacao"),
        func.coalesce(
            func.sum(AmendmentActionPlan.prestacao_valor_executado), 0
        ).label("executado"),
    )
    .group_by(AmendmentActionPlan.amendment_code)
    .subquery()
)
```

`func.count(coluna)` ignora NULL, então conta exatamente os planos com prestação. `outerjoin` pelo `amendment_code` e `coalesce(..., 0)` nos três campos para emenda sem plano render zeros, nunca `null`.

`AmendmentOut` ganha os três campos com `default=0`/`"0.00"` e `field_serializer` para `valor_executado_total` (string, como os demais valores).

Rota nova, **depois** de `/summary` e **antes** de `/` não é necessário — o path `{amendment_code}/action-plans` não colide com `/summary`. Ainda assim, declarar após `/summary` por consistência com o comentário já existente no arquivo:

```python
@router.get("/{amendment_code}/action-plans", response_model=List[ActionPlanOut])
def list_action_plans(
    amendment_code: str,
    db: Session = Depends(get_db),
) -> List[ActionPlanOut]:
    """Planos de acao (entes beneficiarios) de uma emenda Pix.

    Vazio — nao 404 — para emenda sem plano: e o caso normal das emendas de
    Finalidade Definida, que nao tem plano de acao nenhum.
    """
    stmt = (
        select(AmendmentActionPlan)
        .where(AmendmentActionPlan.amendment_code == amendment_code)
        .order_by(
            AmendmentActionPlan.beneficiario_uf,
            AmendmentActionPlan.beneficiario_nome,
            AmendmentActionPlan.id_plano_acao,
        )
    )
    return [ActionPlanOut.model_validate(r) for r in db.execute(stmt).scalars()]
```

- [ ] **Step 4: Rodar os testes** → PASS, e a suíte de API inteira verde.

- [ ] **Step 5: Commit**

---

### Task 7: UI — rótulo de tipo

**Files:**
- Create: `ui/src/lib/tipoEmenda.ts`
- Create: `ui/src/lib/tipoEmenda.test.ts`
- Modify: `ui/src/lib/featureFlags.ts` (registrar `emendas_prestacao`)

**Interfaces:**
- Produces: `classificarTipoEmenda(amendmentType: string | null | undefined): { chave: 'pix' | 'finalidade' | 'desconhecido'; rotulo: string; oficial: string }`

- [ ] **Step 1: Escrever os testes que falham**

```ts
import { describe, expect, it } from 'vitest';
import { classificarTipoEmenda } from './tipoEmenda';

describe('classificarTipoEmenda', () => {
  it('reconhece transferencia especial como Pix', () => {
    const r = classificarTipoEmenda('Emenda Individual - Transferências Especiais');
    expect(r.chave).toBe('pix');
    expect(r.rotulo).toBe('Pix');
  });

  it('reconhece finalidade definida', () => {
    const r = classificarTipoEmenda(
      'Emenda Individual - Transferências com Finalidade Definida'
    );
    expect(r.chave).toBe('finalidade');
    expect(r.rotulo).toBe('Finalidade definida');
  });

  it('sobrevive a acento, caixa e sufixo diferentes', () => {
    expect(classificarTipoEmenda('EMENDA INDIVIDUAL - TRANSFERENCIAS ESPECIAIS').chave)
      .toBe('pix');
  });

  it('tipo desconhecido ou nulo nao inventa rotulo', () => {
    expect(classificarTipoEmenda(null).chave).toBe('desconhecido');
    expect(classificarTipoEmenda('Emenda de Bancada').chave).toBe('desconhecido');
  });

  it('guarda o nome oficial para o tooltip', () => {
    const r = classificarTipoEmenda('Emenda Individual - Transferências Especiais');
    expect(r.oficial).toBe('Emenda Individual - Transferências Especiais');
  });
});
```

- [ ] **Step 2: Rodar e confirmar que falha**

- [ ] **Step 3: Implementar**

```ts
/**
 * Classificação do tipo de emenda para exibição.
 *
 * A fonte manda texto livre. Em produção existem exatamente dois valores
 * (medido em 2026-08-12: 24.910 de Finalidade Definida e 4.254 Especiais),
 * mas a checagem é por substring normalizada para sobreviver a variação de
 * caixa, acento e sufixo — mesma política de `is_individual_amendment` no
 * crawler.
 *
 * "Pix" é o termo que a imprensa e os usuários jornalistas usam; o nome
 * oficial fica no tooltip.
 */
export type TipoEmendaChave = 'pix' | 'finalidade' | 'desconhecido';

export interface TipoEmenda {
  chave: TipoEmendaChave;
  rotulo: string;
  oficial: string;
}

function normalizar(valor: string): string {
  return valor
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .split(/\s+/)
    .join(' ')
    .trim();
}

export function classificarTipoEmenda(
  amendmentType: string | null | undefined
): TipoEmenda {
  const oficial = amendmentType ?? '';
  const n = normalizar(oficial);

  if (n.includes('especiais') || n.includes('especial')) {
    return { chave: 'pix', rotulo: 'Pix', oficial };
  }
  if (n.includes('finalidade definida')) {
    return { chave: 'finalidade', rotulo: 'Finalidade definida', oficial };
  }
  return { chave: 'desconhecido', rotulo: '—', oficial };
}
```

Registrar a flag em `ui/src/lib/featureFlags.ts`:

```ts
  emendas_prestacao: {
    label: 'Prestação de contas das emendas Pix',
    since: '2026-08-12',
  },
```

- [ ] **Step 4: Rodar os testes** → PASS

- [ ] **Step 5: Commit**

---

### Task 8: UI — coluna de prestação, linha expansível e linguagem

**Files:**
- Create: `ui/src/lib/transferegov.ts`
- Create: `ui/src/components/dashboard/PrestacaoContas.tsx`
- Create: `ui/src/components/dashboard/PrestacaoContas.test.tsx`
- Modify: `ui/src/components/dashboard/EmendasTable.tsx`
- Modify: `ui/src/components/dashboard/EmendasTable.test.tsx`
- Modify: `ui/src/api/endpoints.ts`, `ui/src/api/types.ts`

**Interfaces:**
- Consumes: `classificarTipoEmenda` (T7), `useFeatureFlag` (PR 1).
- Produces:
  - `getTransferegovConsultaUrl(chave: TipoEmendaChave): string | null`
  - `textoPrestacao(plano: ActionPlanOut, anoCorrente: number): string`
  - `listActionPlans(amendmentCode: string): Promise<ActionPlanOut[]>`

- [ ] **Step 1: Escrever os testes da linguagem (falhando)**

Este é o teste que trava a diferença entre jornalismo e calúnia:

```ts
describe('textoPrestacao', () => {
  it('ano corrente sem prestacao diz que o prazo esta aberto', () => {
    expect(textoPrestacao({ ano: 2026, prestacao_situacao: null }, 2026))
      .toMatch(/prazo aberto/i);
  });

  it('ano fechado sem prestacao diz que nao ha registro, nunca que sonegou', () => {
    const texto = textoPrestacao({ ano: 2023, prestacao_situacao: null }, 2026);
    expect(texto).toMatch(/sem prestação registrada/i);
    expect(texto).not.toMatch(/não prestou|sonegou|irregular/i);
  });

  it('com prestacao mostra o tipo', () => {
    expect(textoPrestacao(
      { ano: 2024, prestacao_situacao: 'DISPONIBILIZADO', prestacao_tipo: 'Final' },
      2026
    )).toMatch(/Final/);
  });
});
```

- [ ] **Step 2: Rodar e confirmar que falha**

- [ ] **Step 3: Implementar `transferegov.ts` e `PrestacaoContas.tsx`**

`getTransferegovConsultaUrl`, espelhando `lib/portalTransparencia.ts`:

```ts
const CONSULTA_PLANO_ACAO =
  'https://especiais.transferegov.sistema.gov.br/transferencia-especial/plano-acao/consulta';
const PORTAL_GERAL = 'https://portal.transferegov.sistema.gov.br/portal/home';

/**
 * Consulta pública correspondente ao tipo da emenda.
 *
 * A consulta é um formulário de busca — não aceita o código da emenda por
 * query string. Por isso a tela nunca promete "a prestação desta emenda"
 * atrás do link: para as Pix os dados vêm da nossa base, e o link é só o
 * caminho para o usuário conferir na fonte.
 */
export function getTransferegovConsultaUrl(chave: TipoEmendaChave): string | null {
  if (chave === 'pix') return CONSULTA_PLANO_ACAO;
  if (chave === 'finalidade') return PORTAL_GERAL;
  return null;
}
```

`PrestacaoContas.tsx` exporta `textoPrestacao` e o componente da lista de beneficiários (ente, UF, texto da prestação, valor executado).

- [ ] **Step 4: Adaptar `EmendasTable.tsx`**

1. `const prestacaoOn = useFeatureFlag('emendas_prestacao');` — **único** ponto de leitura da flag.
2. Com a flag **off**: tabela idêntica à de hoje, inclusive o `onClick` da linha abrindo o Portal.
3. Com a flag **on**:
   - Colunas `Tipo` e `Prestação` acrescentadas.
   - Linha de emenda Pix com `planos_total > 0` vira `role="button"`, `aria-expanded`, `aria-controls`, e o clique alterna a expansão.
   - O ícone `ExternalLink` vira `<button>` com `onClick={(e) => { e.stopPropagation(); openSafeExternalUrl(safeLink); }}` e `aria-label="Ver esta emenda no Portal da Transparência"`.
   - Linha expandida renderiza uma `TableRow` extra com `colSpan` e a lista de beneficiários, carregada com `useQuery` habilitada só quando expandida.

- [ ] **Step 5: Escrever os testes de tabela**

```tsx
it('flag off mantém a tabela como hoje', ...)          // sem coluna Tipo, clique abre o Portal
it('flag on mostra o badge por tipo', ...)
it('linha Pix expande e lista beneficiários', ...)
it('linha Finalidade definida não expande', ...)
it('botão de link externo não dispara a expansão', ...) // stopPropagation
```

- [ ] **Step 6: Rodar tudo** → `npx vitest run && npx tsc --noEmit` verde.

- [ ] **Step 7: Commit**

---

### Task 9: Verificação final, carga inicial e PR

- [ ] **Step 1: Suíte completa**

Run: `python -m pytest api/tests/ mamute_scrappers/tests/ -q && cd ui && npx vitest run && npx tsc --noEmit`

- [ ] **Step 2: Abrir a PR** contra a `main`, com o corpo trazendo os números medidos (100% de cobertura de plano, 44,2% de prestação, 1:N com mediana 8) e a justificativa de as 85% ficarem fora.

- [ ] **Step 3: Registrar a pendência de pós-merge**

A primeira execução do crawler é o backfill (~58k linhas). Anotar no corpo da PR que ela pode ser disparada na mão logo após o deploy, em vez de esperar o cron das 7h50.

---

## Self-Review

**Cobertura do spec:** tabela desnormalizada (T1), cliente sem chave (T2), precedência (T3), upsert idempotente + FK nula tolerada + cron (T4/T5), agregado e rota de detalhe (T6), rótulos com nome oficial no tooltip (T7), coluna de prestação, expansão, `stopPropagation` e linguagem por ano (T8). O "fora de escopo" do spec (SICONV, `meta_especial`, `empenho_especial`) não gera task, corretamente.

**Placeholders:** as Tasks 4, 6 e 8 descrevem a orquestração e o JSX em prosa estruturada em vez de código completo, porque dependem de nomes exatos do código existente (`run-cron-job.sh`, helpers de fetch, classes de estilo da tabela). Cada uma lista o comportamento observável e os testes que o travam, que é o contrato real.

**Consistência de tipos:** `TipoEmendaChave` (T7) é consumido por `getTransferegovConsultaUrl` (T8); `ActionPlanOut` da API (T6) é o tipo que `listActionPlans` e `textoPrestacao` (T8) consomem; `build_plan_payload` (T3) produz exatamente as chaves que `upsert_plan` (T4) escreve e que a migration (T1) declara.
