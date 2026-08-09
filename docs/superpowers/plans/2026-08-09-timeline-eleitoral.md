# Timeline eleitoral (CS-54) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tabela `electoral_history` com a linha do tempo eleitoral (disputas + resultado + patrimônio por eleição) de candidatos 2026 e parlamentares, coletada da DivulgaCandContas, exposta em dois GETs da API.

**Architecture:** Pipeline de sementes em `tse_crawler/electoral_history.py` (3 fases: semear do JSONB local, semear parlamentares sem candidatura 2026 via gerais 2018/2022, drenar bens incremental via `assets_fetched_at` NULL). Reuso integral de `DivulgaCandClient`, `parsing` e `matching` da CS-16. Spec: `docs/superpowers/specs/2026-08-09-timeline-eleitoral-design.md`.

**Tech Stack:** Python 3.11, SQLAlchemy/Alembic, FastAPI, pytest (SQLite espelho).

## Global Constraints

- Somente backend (banco + coleta + endpoint); nenhuma UI.
- Matching sem fuzzy; CPF confirma quando existir; ambíguo/não-casado declarado.
- Linhas nunca deletadas pelo robô; entrada malformada é pulada com log.
- Dinheiro serializado como string na API (padrão amendments).
- Falha de listagem ruidosa; falha de detalhe tolerada (retenta via NULL).

---

### Task 1: Modelo `ElectoralHistory` + migração + espelhos da API

**Files:**
- Create: `mamute_scrappers/db/models/electoral_history.py`
- Create: `mamute_scrappers/migrations/versions/e6f7a8b9c0d1_add_electoral_history.py` (`down_revision = "c4d5e6f7a8b9"`)
- Create: `api/db/models/candidacy.py`, `api/db/models/electoral_history.py`
- Modify: `mamute_scrappers/db/models/__init__.py`, `api/db/models/__init__.py`, `mamute_scrappers/db/models/parliamentarian.py`, `mamute_scrappers/db/models/candidacy.py` (relationships)

**Interfaces:**
- Produces: `ElectoralHistory` (scrappers + espelho API), tabela `electoral_history`, unique `uq_electoral_history_year_tse_id (election_year, tse_candidate_id)`.

- [ ] **Step 1:** Modelo scrappers:

```python
"""Linha do tempo eleitoral de um politico (TSE/DivulgaCandContas) — CS-54.

Uma linha por pessoa x eleicao x cargo, semeada do `eleicoesAnteriores` que a
DivulgaCandContas devolve no detalhe de cada candidatura. `tse_candidate_id`
e o id da pessoa NAQUELA eleicao (muda a cada ano); o vinculo estavel com a
pessoa e `parliamentarian_id` e/ou `candidacy_id` (candidatura 2026),
denormalizados em todas as linhas.

`assets_fetched_at` NULL significa patrimonio pendente de busca — mesmo papel
do fingerprint da tabela candidacy: falha de detalhe se auto-corrige na
proxima execucao.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger, Column, DateTime, ForeignKey, Integer, Numeric, Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..base import Base


class ElectoralHistory(Base):
    __tablename__ = "electoral_history"
    __table_args__ = (
        UniqueConstraint(
            "election_year", "tse_candidate_id",
            name="uq_electoral_history_year_tse_id",
        ),
    )

    id = Column(BigInteger, primary_key=True, index=True)
    election_year = Column(Integer, nullable=False, index=True)
    tse_candidate_id = Column(BigInteger, nullable=False)
    tse_election_id = Column(BigInteger)

    parliamentarian_id = Column(
        BigInteger, ForeignKey("parliamentarian.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    candidacy_id = Column(
        BigInteger, ForeignKey("candidacy.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    office = Column(Text)
    state = Column(Text)
    locality = Column(Text)
    party = Column(Text)
    ballot_name = Column(Text)
    full_name = Column(Text)
    ballot_number = Column(Integer)
    result = Column(Text)

    declared_assets = Column(Numeric(18, 2))
    assets_count = Column(Integer)
    assets = Column(JSONB)
    assets_fetched_at = Column(DateTime)

    source_link = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
        nullable=False,
    )

    parliamentarian = relationship("Parliamentarian", back_populates="electoral_history")
    candidacy = relationship("Candidacy", back_populates="electoral_history")


__all__ = ["ElectoralHistory"]
```

- [ ] **Step 2:** Relationships: em `parliamentarian.py`, após `candidacies`, e em `candidacy.py`, após `parliamentarian`:

```python
    electoral_history = relationship(
        "ElectoralHistory",
        back_populates="parliamentarian",  # "candidacy" no modelo Candidacy
    )
```

Exports: `from .electoral_history import ElectoralHistory` + `"ElectoralHistory"` no `__all__` (ordem alfabética) em `mamute_scrappers/db/models/__init__.py`.

- [ ] **Step 3:** Migração `e6f7a8b9c0d1` espelhando o estilo de `c4d5e6f7a8b9_add_candidacy.py`: `create_table` com as colunas acima (JSONB para `assets`), unique index `uq_electoral_history_year_tse_id (election_year, tse_candidate_id)`, índices `ix_electoral_history_parliamentarian_id`, `ix_electoral_history_candidacy_id`, `ix_electoral_history_election_year`. Downgrade derruba índices e tabela. Docstring explica chave natural e `assets_fetched_at`.

- [ ] **Step 4:** Espelhos da API (sem relationships, padrão `api/db/models/parliamentary_amendment.py`): `api/db/models/candidacy.py` (colunas da tabela candidacy) e `api/db/models/electoral_history.py` (colunas acima); exports nos dois `__init__.py`.

- [ ] **Step 5:** Sanity: `DATABASE_URL="postgresql://x:x@localhost/x" python3 -c "import mamute_scrappers.db.models; import api.db.models"` sem erro. Commit `feat(tse): tabela electoral_history e modelos`.

---

### Task 2: Parsing do histórico e dos bens

**Files:**
- Create: `mamute_scrappers/tse_crawler/history_parsing.py`
- Test: `mamute_scrappers/tests/test_tse_history_parsing.py`

**Interfaces:**
- Consumes: `coerce_text`, `parse_int` de `tse_crawler.parsing`.
- Produces: `build_history_payload(entry, *, candidacy_id=None, parliamentarian_id=None) -> dict|None`; `build_assets_payload(detail_or_details: dict) -> dict` com `declared_assets: Decimal|None`, `assets_count: int`, `assets: list`.

- [ ] **Step 1:** Teste (fixture = entrada real do Sergio Moro validada em produção 2026-08-09):

```python
from __future__ import annotations

from decimal import Decimal

from mamute_scrappers.tse_crawler import history_parsing

ENTRY_2022 = {
    "id": "160001621846",
    "sgUe": "PR",
    "cargo": "Senador",
    "local": "PARANÁ",
    "nrAno": 2022,
    "txLink": "https://divulgacandcontas.tse.jus.br/divulga/#/candidato/2022/2040602022/PR/160001621846",
    "partido": "UNIÃO",
    "nomeUrna": "SERGIO MORO",
    "idEleicao": "2040602022",
    "nrCandidato": 444,
    "nomeCandidato": "SERGIO FERNANDO MORO",
    "situacaoTotalizacao": "Eleito",
}


def test_build_history_payload():
    payload = history_parsing.build_history_payload(
        ENTRY_2022, candidacy_id=7, parliamentarian_id=3
    )
    assert payload == {
        "election_year": 2022,
        "tse_candidate_id": 160001621846,
        "tse_election_id": 2040602022,
        "office": "Senador",
        "state": "PR",
        "locality": "PARANÁ",
        "party": "UNIÃO",
        "ballot_name": "SERGIO MORO",
        "full_name": "SERGIO FERNANDO MORO",
        "ballot_number": 444,
        "result": "Eleito",
        "source_link": ENTRY_2022["txLink"],
        "candidacy_id": 7,
        "parliamentarian_id": 3,
    }


def test_entrada_sem_id_ou_ano_e_descartada():
    assert history_parsing.build_history_payload({"nrAno": 2022}) is None
    assert history_parsing.build_history_payload({"id": "123"}) is None
    assert history_parsing.build_history_payload({"id": "abc", "nrAno": 2022}) is None


def test_build_assets_payload_usa_total_da_fonte():
    detail = {"totalDeBens": 1036642.25, "bens": [{"valor": 1000.0}, {"valor": 500.5}]}
    payload = history_parsing.build_assets_payload(detail)
    assert payload["declared_assets"] == Decimal("1036642.25")
    assert payload["assets_count"] == 2
    assert payload["assets"] == detail["bens"]


def test_build_assets_payload_soma_quando_nao_ha_total():
    detail = {"totalDeBens": None, "bens": [{"valor": 1000.0}, {"valor": 500.5}]}
    assert history_parsing.build_assets_payload(detail)["declared_assets"] == Decimal("1500.50")


def test_build_assets_payload_sem_bens():
    payload = history_parsing.build_assets_payload({"totalDeBens": None, "bens": None})
    assert payload == {"declared_assets": None, "assets_count": 0, "assets": []}
```

- [ ] **Step 2:** Rodar e ver falhar (import).
- [ ] **Step 3:** Implementar:

```python
"""Conversao do historico eleitoral (`eleicoesAnteriores`) e dos bens.

`eleicoesAnteriores` vem no detalhe de cada candidatura da DivulgaCandContas
com ids em string e inclui a propria eleicao corrente. Entrada sem id ou sem
ano nao tem como virar linha de timeline — e descartada pelo chamador, com
log, nunca com excecao.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from .parsing import coerce_text, parse_int


def _parse_decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def build_history_payload(
    entry: Dict[str, Any],
    *,
    candidacy_id: Optional[int] = None,
    parliamentarian_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    tse_candidate_id = parse_int(entry.get("id"))
    election_year = parse_int(entry.get("nrAno"))
    if tse_candidate_id is None or election_year is None:
        return None

    return {
        "election_year": election_year,
        "tse_candidate_id": tse_candidate_id,
        "tse_election_id": parse_int(entry.get("idEleicao")),
        "office": coerce_text(entry.get("cargo")),
        "state": coerce_text(entry.get("sgUe")),
        "locality": coerce_text(entry.get("local")),
        "party": coerce_text(entry.get("partido")),
        "ballot_name": coerce_text(entry.get("nomeUrna")),
        "full_name": coerce_text(entry.get("nomeCandidato")),
        "ballot_number": parse_int(entry.get("nrCandidato")),
        "result": coerce_text(entry.get("situacaoTotalizacao")),
        "source_link": coerce_text(entry.get("txLink")),
        "candidacy_id": candidacy_id,
        "parliamentarian_id": parliamentarian_id,
    }


def build_assets_payload(detail: Dict[str, Any]) -> Dict[str, Any]:
    """Extrai patrimonio de um payload de detalhe (ou do `details` da 2026).

    `totalDeBens` e a fonte da verdade; na ausencia dele, soma dos itens.
    """
    bens = detail.get("bens")
    items: List[Dict[str, Any]] = bens if isinstance(bens, list) else []

    total = _parse_decimal(detail.get("totalDeBens"))
    if total is None and items:
        parcels = [_parse_decimal(item.get("valor")) for item in items]
        valid = [p for p in parcels if p is not None]
        total = sum(valid, Decimal("0.00")) if valid else None

    return {"declared_assets": total, "assets_count": len(items), "assets": items}


__all__ = ["build_assets_payload", "build_history_payload"]
```

- [ ] **Step 4:** Rodar e ver passar. Commit `feat(tse): parsing do historico eleitoral e dos bens`.

---

### Task 3: Comando `electoral_history` (3 fases + upsert)

**Files:**
- Create: `mamute_scrappers/tse_crawler/electoral_history.py`
- Test: `mamute_scrappers/tests/test_tse_history_upsert.py`

**Interfaces:**
- Consumes: Task 1 (`ElectoralHistory`), Task 2 (`build_history_payload`, `build_assets_payload`), CS-16 (`DivulgaCandClient`, `normalize_text`, `normalize_cpf`).
- Produces: `upsert_history(session, payload) -> (record, created)`; `run(persist=True, max_details=None, skip_seed=False, parliamentarians_only=False)`; executável `python -m mamute_scrappers.tse_crawler.electoral_history`.

- [ ] **Step 1:** Testes de upsert (SQLite espelho, padrão `test_tse_candidacy_upsert.py` — espelhos `Parliamentarian(id)`, `Candidacy(id, election_year, tse_candidate_id, parliamentarian_id, details' como Text? não: seed testado à parte)`, `ElectoralHistory` com as colunas do upsert):

```python
def test_primeira_gravacao_cria(session):
    record, created = eh_mod.upsert_history(session, payload())
    session.commit()
    assert created is True and record.result == "Eleito"

def test_upsert_atualiza_resultado_sem_duplicar(session):
    eh_mod.upsert_history(session, payload())
    session.commit()
    _, created = eh_mod.upsert_history(session, payload(result="Não eleito"))
    session.commit()
    assert created is False
    assert session.query(ElectoralHistory).one().result == "Não eleito"

def test_reseed_sem_vinculo_nao_apaga_vinculo_existente(session):
    eh_mod.upsert_history(session, payload(parliamentarian_id=1, candidacy_id=1))
    session.commit()
    eh_mod.upsert_history(session, payload(parliamentarian_id=None, candidacy_id=None))
    session.commit()
    row = session.query(ElectoralHistory).one()
    assert row.parliamentarian_id == 1 and row.candidacy_id == 1

def test_payload_sem_assets_nao_apaga_assets(session):
    com_assets = payload()
    com_assets.update({"declared_assets": Decimal("100.00"), "assets_count": 1,
                       "assets": [{"valor": 100.0}], "assets_fetched_at": FIXED_DT})
    eh_mod.upsert_history(session, com_assets)
    session.commit()
    eh_mod.upsert_history(session, payload(result="Eleito"))
    session.commit()
    row = session.query(ElectoralHistory).one()
    assert row.declared_assets == Decimal("100.00")
    assert row.assets_fetched_at is not None

def test_repeticao_no_mesmo_lote_nao_duplica(session):
    eh_mod.upsert_history(session, payload())
    _, created = eh_mod.upsert_history(session, payload())
    session.commit()
    assert created is False
    assert session.query(ElectoralHistory).count() == 1
```

`payload()` base: election_year 2022, tse_candidate_id 160001621846, office Senador, state PR, result "Eleito", parliamentarian_id None, candidacy_id None (mais campos da Task 2).

- [ ] **Step 2:** Rodar e ver falhar.
- [ ] **Step 3:** Implementar o módulo. Estrutura (código completo):

```python
"""Constroi a timeline eleitoral (electoral_history) — CS-54.

Tres fases, todas idempotentes:
1. Semear do JSONB local: `eleicoesAnteriores` de cada candidacy 2026. A fase
   re-roda sempre (barata, zero API), entao o `result` acompanha o TSE e
   candidaturas novas ganham timeline sozinhas. A linha do proprio 2026 ja
   nasce com patrimonio, copiado de candidacy.details (bens ja armazenados).
2. Semear parlamentares sem candidatura 2026: varre listagens das gerais
   2022/2018 (cargos 1/3/5/6), casa por nome+UF com confirmacao de CPF via
   detalhe quando o parlamentar tem CPF, e semeia a timeline completa a
   partir do `eleicoesAnteriores` do detalhe (municipais incluidas).
3. Drenar patrimonio: linhas com assets_fetched_at NULL -> detalhe daquele
   ano/eleicao -> bens. Parlamentares primeiro, depois anos mais recentes.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mamute_scrappers.tse_crawler.client import DivulgaCandClient  # noqa: E402
from mamute_scrappers.tse_crawler.history_parsing import (  # noqa: E402
    build_assets_payload,
    build_history_payload,
)
from mamute_scrappers.tse_crawler.parsing import (  # noqa: E402
    normalize_cpf,
    normalize_text,
)

logger = logging.getLogger(__name__)

COMMIT_EVERY = 200
SEED_ELECTION_YEARS = (2022, 2018)
SEED_OFFICE_CODES = (1, 3, 5, 6)  # presidente, governador, senador, dep. federal

ElectoralHistory: Any = None
Candidacy: Any = None
Parliamentarian: Any = None

_DISPUTE_FIELDS = (
    "tse_election_id", "office", "state", "locality", "party",
    "ballot_name", "full_name", "ballot_number", "result", "source_link",
)
_LINK_FIELDS = ("parliamentarian_id", "candidacy_id")
_ASSET_FIELDS = ("declared_assets", "assets_count", "assets", "assets_fetched_at")


def _ensure_models() -> None: ...  # lazy import como candidacy.py

def upsert_history(session, payload) -> Tuple[Any, bool]:
    # lookup por (election_year, tse_candidate_id); create + flush no lote;
    # _DISPUTE_FIELDS sempre; _LINK_FIELDS so quando payload traz valor nao
    # nulo (reseed de outra origem nao apaga vinculo); _ASSET_FIELDS so
    # quando "assets_fetched_at" in payload.

def seed_from_candidacies(session) -> Dict[str, int]:
    # query (id, parliamentarian_id, election_year, details) de Candidacy
    # where details isnot None; para cada entry de details["eleicoesAnteriores"]:
    #   payload = build_history_payload(entry, candidacy_id=..., parliamentarian_id=...)
    #   if payload is None: malformed += 1; continue
    #   if payload["election_year"] == cand.election_year:
    #       payload.update(build_assets_payload(cand.details)); payload["assets_fetched_at"] = datetime.utcnow()
    #   upsert + commit a cada COMMIT_EVERY

def seed_missing_parliamentarians(session, client) -> Dict[str, int]:
    # pending = parlamentares sem linha em electoral_history
    # indexa pending por nome normalizado (name + full_name) -> [registro]
    # para year em SEED_ELECTION_YEARS (para quando pending esvaziar):
    #   election_id = client.find_general_election_id(year)
    #   para office em SEED_OFFICE_CODES, uf em UFS (BR so p/ presidente):
    #     para item na listagem: nomes do item (nomeCompleto, nomeUrna) no indice?
    #       hit unico com UF == state_elected (ou BR):
    #         detail = client.get_candidate_detail(...)
    #         se pending tem cpf e normalize_cpf(detail["cpf"]) != cpf: rejeita
    #         seed de detail["eleicoesAnteriores"] com parliamentarian_id
    #         linha do proprio year: payload.update(build_assets_payload(detail)) + fetched_at
    #         remove do pending
    # log de quem sobrou sem match (nomes), sem falhar

def drain_assets(session, client, max_details) -> Dict[str, int]:
    # rows: assets_fetched_at IS NULL, order by (parliamentarian_id IS NULL), election_year desc, id
    # ate max_details: detail = client.get_candidate_detail(election_year, state, tse_election_id, tse_candidate_id)
    #   None -> failed += 1, continue (fica NULL)
    #   upsert_history(session, {chave natural, **build_assets_payload(detail), "assets_fetched_at": datetime.utcnow()})
    #   commit a cada COMMIT_EVERY

def run(*, persist=True, max_details=None, skip_seed=False, parliamentarians_only=False):
    # _load_env_file() (mesma funcao de candidacy.py, copiada);
    # session_scope; fases conforme flags; log de resumo por fase.

if __name__ == "__main__":
    # argparse: --dry-run, --max-details, --skip-seed, --parliamentarians-only
```

O corpo real de cada função segue exatamente os comentários acima (são a especificação); nenhuma lógica além delas.

- [ ] **Step 4:** Rodar `test_tse_history_upsert.py` e ver passar; suíte completa dos scrappers verde. Commit `feat(tse): comando electoral-history com 3 fases`.

---

### Task 4: Endpoint REST + testes

**Files:**
- Create: `api/routers/electoral_history.py`
- Modify: `api/main.py` (import + `include_router(electoral_history.router, dependencies=auth_dependencies)`)
- Test: `api/tests/test_electoral_history.py`

**Interfaces:**
- Consumes: espelhos `ElectoralHistory`, `Candidacy`, `Parliamentarian` de `api/db/models`.
- Produces: `GET /api/parliamentarians/{id}/electoral-history` e `GET /api/candidacies/{id}/electoral-history`, resposta `{"entries": [...]}`.

- [ ] **Step 1:** Teste (SQLite DDL cru + overrides, padrão `test_amendments.py`): tabelas `parliamentarian(id, name)`, `candidacy(id, election_year, tse_candidate_id, parliamentarian_id)`, `electoral_history(...)`; seeds: parlamentar 1 com linhas 2026 (Concorrendo, assets 1036642.25, 12 itens) e 2022 (Eleito, assets nulos); candidacy 10 ligada às mesmas linhas; casos:

```python
def test_timeline_do_parlamentar_ordenada_por_ano_desc(client):
    resp = client.get("/api/parliamentarians/1/electoral-history")
    assert resp.status_code == 200
    years = [e["year"] for e in resp.json()["entries"]]
    assert years == [2026, 2022]
    assert "assets" not in resp.json()["entries"][0]

def test_declared_assets_trafega_como_string(client):
    entry = client.get("/api/parliamentarians/1/electoral-history").json()["entries"][0]
    assert entry["declared_assets"] == "1036642.25"

def test_include_assets_traz_a_lista(client):
    resp = client.get("/api/parliamentarians/1/electoral-history",
                      params={"include_assets": "true"})
    assert isinstance(resp.json()["entries"][0]["assets"], list)

def test_timeline_da_candidatura(client):
    resp = client.get("/api/candidacies/10/electoral-history")
    assert resp.status_code == 200 and len(resp.json()["entries"]) == 2

def test_404_quando_nao_existe(client):
    assert client.get("/api/parliamentarians/999/electoral-history").status_code == 404
    assert client.get("/api/candidacies/999/electoral-history").status_code == 404

def test_lista_vazia_quando_existe_sem_timeline(client):
    # parlamentar 2 sem linhas
    resp = client.get("/api/parliamentarians/2/electoral-history")
    assert resp.status_code == 200 and resp.json()["entries"] == []
```

- [ ] **Step 2:** Rodar e ver falhar (404 da rota inexistente).
- [ ] **Step 3:** Implementar o router:

```python
"""Timeline eleitoral de politicos e candidatos (CS-54)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, field_serializer
from sqlalchemy import select
from sqlalchemy.orm import Session

try:
    from ..db.models.candidacy import Candidacy
    from ..db.models.electoral_history import ElectoralHistory
    from ..db.models.parliamentarian import Parliamentarian
    from ..dependencies import get_db
except (ImportError, ValueError):
    from db.models.candidacy import Candidacy
    from db.models.electoral_history import ElectoralHistory
    from db.models.parliamentarian import Parliamentarian
    from dependencies import get_db

router = APIRouter(tags=["electoral-history"])


class ElectoralHistoryEntryOut(BaseModel):
    year: int
    office: Optional[str] = None
    state: Optional[str] = None
    locality: Optional[str] = None
    party: Optional[str] = None
    ballot_name: Optional[str] = None
    result: Optional[str] = None
    declared_assets: Optional[Decimal] = None
    assets_count: Optional[int] = None
    source_link: Optional[str] = None
    assets: Optional[Any] = None

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("declared_assets")
    def _serialize_money(self, value: Optional[Decimal]) -> Optional[str]:
        return None if value is None else str(value)


class ElectoralHistoryOut(BaseModel):
    entries: List[ElectoralHistoryEntryOut]


def _entries(db, where_clause, include_assets) -> ElectoralHistoryOut:
    stmt = (
        select(ElectoralHistory)
        .where(where_clause)
        .order_by(ElectoralHistory.election_year.desc(), ElectoralHistory.id)
    )
    entries = []
    for row in db.execute(stmt).scalars():
        entry = ElectoralHistoryEntryOut(
            year=row.election_year, office=row.office, state=row.state,
            locality=row.locality, party=row.party, ballot_name=row.ballot_name,
            result=row.result, declared_assets=row.declared_assets,
            assets_count=row.assets_count, source_link=row.source_link,
            assets=row.assets if include_assets else None,
        )
        entries.append(entry)
    return ElectoralHistoryOut(entries=entries)
```

Rotas: `/parliamentarians/{parliamentarian_id}/electoral-history` (404 se `db.get(Parliamentarian, id)` None) e `/candidacies/{candidacy_id}/electoral-history` (404 análogo), ambas com `include_assets: bool = Query(False)`. No JSON de saída, `assets` deve ser omitido quando não pedido: usar `response_model_exclude_none=True` no decorator (por isso o teste checa `"assets" not in entry`).

- [ ] **Step 4:** Registrar no `api/main.py` junto aos demais `include_router(..., dependencies=auth_dependencies)`. Rodar testes da API e ver passar. Commit `feat(api): endpoints de timeline eleitoral`.

---

### Task 5: Cron + suítes completas + PR

- [ ] **Step 1:** `mamute_scrappers/docker/scrappers.cron`, após o bloco tse-candidacies:

```cron
# Timeline eleitoral (historico + patrimonio) — semeia do JSONB local e drena
# ate 5000 detalhes de bens por dia; retomavel, parlamentares primeiro.
50 6 * * * cd /app && /app/mamute_scrappers/docker/run-cron-job.sh tse-electoral-history -- /usr/local/bin/python -m mamute_scrappers.tse_crawler.electoral_history --max-details 5000 >> /proc/1/fd/1 2>> /proc/1/fd/2
```

- [ ] **Step 2:** `python3 -m pytest mamute_scrappers/tests/ api/tests/ -q` → tudo verde.
- [ ] **Step 3:** Smoke real sem banco: script inline que chama `build_history_payload` sobre `eleicoesAnteriores` de um detalhe vivo da DivulgaCand.
- [ ] **Step 4:** Push + PR contra main (resumo executivo, decisões, passos pós-merge: migração + primeira execução manual com `--max-details` e cron assumindo).

## Self-review

- Cobertura do spec: modelo/migração/espelhos (T1), parsing histórico+bens (T2), 3 fases+upsert (T3), endpoints+404+include_assets (T4), cron+PR (T5). Flags do spec presentes no T3. UI/notificação: fora de escopo, sem task — correto.
- Sem placeholders (T3 usa comentários-especificação com todas as regras nomeadas; nenhuma decisão em aberto).
- Consistência de nomes: `upsert_history`, `build_history_payload`, `build_assets_payload`, `assets_fetched_at` idênticos entre tasks.
