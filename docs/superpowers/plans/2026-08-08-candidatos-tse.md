# Candidatos do TSE (CS-16) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Importar as candidaturas da Eleição Geral 2026 (DivulgaCandContas/TSE) para a nova tabela `candidacy`, com vínculo a `parliamentarian` e coleta incremental diária.

**Architecture:** Novo pacote `mamute_scrappers/tse_crawler/` espelhando o `portal_crawler`: client HTTP com retry, parsing puro, matching determinístico (CPF → nome), comando idempotente com fingerprint de listagem para buscar detalhe só do que mudou. Spec: `docs/superpowers/specs/2026-08-08-candidatos-tse-design.md`.

**Tech Stack:** Python 3.11, requests, SQLAlchemy, Alembic, pytest (SQLite em memória nos testes de upsert).

## Global Constraints

- Sem mudança de UI/API HTTP (escopo CS-16 = banco somente).
- Matching sem fuzzy: igualdade exata de texto normalizado, ambíguo declarado.
- `match_status = "manual"` nunca é sobrescrito pelo robô.
- Falha de listagem é ruidosa (exit != 0); falha de detalhe é tolerada e retomada.
- Candidatura nunca é deletada pelo crawler.
- Comentários/docstrings em pt-BR sem acento nos arquivos ASCII do scrappers (seguir arquivo vizinho).

---

### Task 1: Modelo `Candidacy` + migração

**Files:**
- Create: `mamute_scrappers/db/models/candidacy.py`
- Create: `mamute_scrappers/migrations/versions/c4d5e6f7a8b9_add_candidacy.py`
- Modify: `mamute_scrappers/db/models/__init__.py` (import + `__all__`)
- Modify: `mamute_scrappers/db/models/parliamentarian.py` (relationship `candidacies`)

**Interfaces:**
- Produces: `Candidacy` (SQLAlchemy model, tabela `candidacy`, unique `(election_year, tse_candidate_id)`).

- [ ] **Step 1: Criar o modelo** — `mamute_scrappers/db/models/candidacy.py`:

```python
"""Modelo de candidatura eleitoral (TSE/DivulgaCandContas).

Uma linha por candidatura por eleicao, chaveada pelo id do candidato na
DivulgaCandContas. `parliamentarian_id` e anulavel: a maioria dos ~29 mil
candidatos de 2026 nao e parlamentar em exercicio, e o vinculo existe para
mostrar "este parlamentar e candidato a X". ON DELETE SET NULL, como nas
emendas: candidatura e fato publico e nao some com o parlamentar.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..base import Base


class Candidacy(Base):
    __tablename__ = "candidacy"
    __table_args__ = (
        UniqueConstraint(
            "election_year", "tse_candidate_id", name="uq_candidacy_election_tse_id"
        ),
    )

    id = Column(BigInteger, primary_key=True, index=True)
    election_year = Column(Integer, nullable=False, index=True)
    tse_candidate_id = Column(BigInteger, nullable=False)

    office_code = Column(Integer, index=True)
    office = Column(Text)
    state = Column(Text, index=True)

    ballot_number = Column(Integer)
    ballot_name = Column(Text)
    full_name = Column(Text)
    party = Column(Text)
    coalition = Column(Text)
    status = Column(Text)
    totalization_status = Column(Text)

    cpf = Column(Text)
    voter_id = Column(Text)
    photo_url = Column(Text)
    tse_last_update = Column(DateTime)

    # So e gravado apos upsert completo com detalhe; ausencia forca nova
    # tentativa de detalhe na proxima execucao.
    listing_fingerprint = Column(Text)

    parliamentarian_id = Column(
        BigInteger,
        ForeignKey("parliamentarian.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    match_status = Column(Text, nullable=False, index=True)

    details = Column(JSONB)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    parliamentarian = relationship("Parliamentarian", back_populates="candidacies")


__all__ = ["Candidacy"]
```

- [ ] **Step 2: Exportar e ligar** — em `db/models/__init__.py` adicionar `from .candidacy import Candidacy` (ordem alfabética) e `"Candidacy"` no `__all__`; em `parliamentarian.py`, abaixo de `amendments`, adicionar:

```python
    candidacies = relationship(
        "Candidacy",
        back_populates="parliamentarian",
    )
```

- [ ] **Step 3: Migração** — `c4d5e6f7a8b9_add_candidacy.py`, `down_revision = "b2c3d4e5f6a7"`, criando a tabela com as mesmas colunas (espelhar estilo de `b2c3d4e5f6a7_add_parliamentary_amendment.py`), unique index `uq_candidacy_election_tse_id` em `(election_year, tse_candidate_id)` e índices em `state`, `office_code`, `match_status`, `parliamentarian_id`. `downgrade()` derruba índices e tabela.

- [ ] **Step 4: Sanity import** — Run: `python3 -c "import mamute_scrappers.db.models"` (com `DATABASE_URL` dummy se o engine exigir). Expected: sem erro.

- [ ] **Step 5: Commit** — `feat(tse): tabela candidacy e modelo`

---

### Task 2: Parsing (payloads, fingerprint, CPF, datas)

**Files:**
- Create: `mamute_scrappers/tse_crawler/__init__.py` (vazio)
- Create: `mamute_scrappers/tse_crawler/parsing.py`
- Test: `mamute_scrappers/tests/test_tse_parsing.py`

**Interfaces:**
- Produces: `coerce_text(v) -> str|None`, `parse_int(v) -> int|None`, `normalize_cpf(v) -> str|None`, `parse_tse_datetime(v) -> datetime|None`, `compute_listing_fingerprint(item: dict) -> str`, `build_listing_payload(item, *, election_year, office_code, office_name, state) -> dict|None`, `merge_detail_payload(payload, detail) -> dict`.

- [ ] **Step 1: Testes que falham** — `test_tse_parsing.py` com item de listagem real reduzido (amostra AC/senador validada em 2026-08-07):

```python
from __future__ import annotations

from datetime import datetime

from mamute_scrappers.tse_crawler import parsing

LISTING_ITEM = {
    "id": 10002536710,
    "nomeUrna": "DR. JUNIOR FEITOSA",
    "numero": 277,
    "nomeCompleto": "RIBAMAR DE SOUSA FEITOZA JÚNIOR",
    "tituloEleitor": "003576712402",
    "cpf": None,
    "descricaoSituacao": "Aguardando julgamento",
    "descricaoTotalizacao": "Concorrendo",
    "ufCandidatura": "AC",
    "nomeColigacao": "DC",
    "partido": {"numero": 27, "sigla": "DC", "nome": "Democracia Crista"},
}

DETAIL = {
    "id": 10002536710,
    "cpf": "67146902234",
    "tituloEleitor": "003576712402",
    "fotoUrl": "https://divulgacandcontas.tse.jus.br/divulga/rest/arquivo/img/20322002026/10002536710/AC",
    "dataUltimaAtualizacao": "2026-08-05 11:25",
}


def test_normalize_cpf_aceita_so_11_digitos():
    assert parsing.normalize_cpf("671.469.022-34") == "67146902234"
    assert parsing.normalize_cpf("67146902234") == "67146902234"
    assert parsing.normalize_cpf("123") is None
    assert parsing.normalize_cpf(None) is None


def test_parse_tse_datetime():
    assert parsing.parse_tse_datetime("2026-08-05 11:25") == datetime(2026, 8, 5, 11, 25)
    assert parsing.parse_tse_datetime(None) is None
    assert parsing.parse_tse_datetime("nao-e-data") is None


def test_fingerprint_estavel_e_sensivel_a_mudanca():
    fp1 = parsing.compute_listing_fingerprint(LISTING_ITEM)
    fp2 = parsing.compute_listing_fingerprint(dict(LISTING_ITEM))
    assert fp1 == fp2

    mudado = dict(LISTING_ITEM, descricaoSituacao="Deferido")
    assert parsing.compute_listing_fingerprint(mudado) != fp1


def test_fingerprint_ignora_campos_volateis():
    com_ruido = dict(LISTING_ITEM, fotoUrl="http://x/y.jpg")
    assert parsing.compute_listing_fingerprint(com_ruido) == (
        parsing.compute_listing_fingerprint(LISTING_ITEM)
    )


def test_build_listing_payload():
    payload = parsing.build_listing_payload(
        LISTING_ITEM,
        election_year=2026,
        office_code=5,
        office_name="Senador",
        state="AC",
    )
    assert payload == {
        "election_year": 2026,
        "tse_candidate_id": 10002536710,
        "office_code": 5,
        "office": "Senador",
        "state": "AC",
        "ballot_number": 277,
        "ballot_name": "DR. JUNIOR FEITOSA",
        "full_name": "RIBAMAR DE SOUSA FEITOZA JÚNIOR",
        "party": "DC",
        "coalition": "DC",
        "status": "Aguardando julgamento",
        "totalization_status": "Concorrendo",
    }


def test_build_listing_payload_sem_id_descarta():
    assert (
        parsing.build_listing_payload(
            {"nomeUrna": "X"},
            election_year=2026,
            office_code=5,
            office_name="Senador",
            state="AC",
        )
        is None
    )


def test_merge_detail_payload():
    payload = parsing.build_listing_payload(
        LISTING_ITEM,
        election_year=2026,
        office_code=5,
        office_name="Senador",
        state="AC",
    )
    merged = parsing.merge_detail_payload(payload, DETAIL)
    assert merged["cpf"] == "67146902234"
    assert merged["voter_id"] == "003576712402"
    assert merged["photo_url"].startswith("https://divulgacandcontas")
    assert merged["tse_last_update"] == datetime(2026, 8, 5, 11, 25)
    assert merged["details"] == DETAIL
```

- [ ] **Step 2: Rodar e ver falhar** — `python3 -m pytest mamute_scrappers/tests/test_tse_parsing.py -q`. Expected: erro de import.

- [ ] **Step 3: Implementar** — `parsing.py`:

```python
"""Conversao dos payloads da DivulgaCandContas.

O fingerprint cobre apenas os campos da LISTAGEM que disparam refetch do
detalhe. Campos volateis ou que so existem no detalhe ficam de fora de
proposito: mudanca neles nao deve custar 29 mil requests.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any, Dict, Optional

from mamute_scrappers.portal_crawler.parsing import normalize_text

_DIGITS_ONLY = re.compile(r"\D")

# Campos da listagem observados na API real em 2026-08-07. `descricaoSituacao`
# e o que mais muda (Aguardando julgamento -> Deferido/Indeferido).
_FINGERPRINT_FIELDS = (
    "nomeUrna",
    "numero",
    "nomeCompleto",
    "descricaoSituacao",
    "descricaoTotalizacao",
    "nomeColigacao",
)


def coerce_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    cleaned = " ".join(str(value).split())
    return cleaned or None


def parse_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def normalize_cpf(value: Any) -> Optional[str]:
    """Digitos do CPF, ou None quando nao ha exatamente 11."""
    if value is None:
        return None
    digits = _DIGITS_ONLY.sub("", str(value))
    return digits if len(digits) == 11 else None


def parse_tse_datetime(value: Any) -> Optional[datetime]:
    """Converte "2026-08-05 11:25" (formato observado no detalhe)."""
    text = coerce_text(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _party_sigla(item: Dict[str, Any]) -> Optional[str]:
    party = item.get("partido")
    if isinstance(party, dict):
        return coerce_text(party.get("sigla"))
    return None


def compute_listing_fingerprint(item: Dict[str, Any]) -> str:
    material = [coerce_text(item.get(field)) for field in _FINGERPRINT_FIELDS]
    material.append(_party_sigla(item))
    blob = json.dumps(material, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def build_listing_payload(
    item: Dict[str, Any],
    *,
    election_year: int,
    office_code: int,
    office_name: str,
    state: str,
) -> Optional[Dict[str, Any]]:
    tse_candidate_id = parse_int(item.get("id"))
    if tse_candidate_id is None:
        return None

    return {
        "election_year": election_year,
        "tse_candidate_id": tse_candidate_id,
        "office_code": office_code,
        "office": office_name,
        "state": state,
        "ballot_number": parse_int(item.get("numero")),
        "ballot_name": coerce_text(item.get("nomeUrna")),
        "full_name": coerce_text(item.get("nomeCompleto")),
        "party": _party_sigla(item),
        "coalition": coerce_text(item.get("nomeColigacao")),
        "status": coerce_text(item.get("descricaoSituacao")),
        "totalization_status": coerce_text(item.get("descricaoTotalizacao")),
    }


def merge_detail_payload(
    payload: Dict[str, Any], detail: Dict[str, Any]
) -> Dict[str, Any]:
    merged = dict(payload)
    merged["cpf"] = normalize_cpf(detail.get("cpf"))
    merged["voter_id"] = coerce_text(detail.get("tituloEleitor"))
    merged["photo_url"] = coerce_text(detail.get("fotoUrl"))
    merged["tse_last_update"] = parse_tse_datetime(detail.get("dataUltimaAtualizacao"))
    merged["details"] = detail
    return merged


__all__ = [
    "build_listing_payload",
    "coerce_text",
    "compute_listing_fingerprint",
    "merge_detail_payload",
    "normalize_cpf",
    "normalize_text",
    "parse_int",
    "parse_tse_datetime",
]
```

- [ ] **Step 4: Rodar e ver passar** — mesmo comando. Expected: PASS.
- [ ] **Step 5: Commit** — `feat(tse): parsing de listagem e detalhe da DivulgaCandContas`

---

### Task 3: Matching candidato → parlamentar

**Files:**
- Create: `mamute_scrappers/tse_crawler/matching.py`
- Test: `mamute_scrappers/tests/test_tse_matching.py`

**Interfaces:**
- Consumes: `normalize_text`, `normalize_cpf` de `tse_crawler.parsing`.
- Produces: `ParliamentarianRecord(id, name, full_name, cpf, state_elected)` (NamedTuple), `MatchIndex`, `build_index(records) -> MatchIndex`, `match_candidacy(*, cpf, full_name, ballot_name, state, index) -> MatchResult(parliamentarian_id, status)`, constantes `MATCH_STATUS_CPF|NAME|AMBIGUOUS|UNMATCHED|MANUAL`.

- [ ] **Step 1: Testes que falham** — `test_tse_matching.py`:

```python
from __future__ import annotations

from mamute_scrappers.tse_crawler.matching import (
    MATCH_STATUS_AMBIGUOUS,
    MATCH_STATUS_CPF,
    MATCH_STATUS_NAME,
    MATCH_STATUS_UNMATCHED,
    ParliamentarianRecord,
    build_index,
    match_candidacy,
)

DEPUTADO = ParliamentarianRecord(
    id=1,
    name="Heitor Schuch",
    full_name="Heitor José Schuch",
    cpf="11122233344",
    state_elected="RS",
)
SENADOR = ParliamentarianRecord(
    id=2,
    name="Marcos Rogério",
    full_name="Marcos Rogério da Silva Brito",
    cpf=None,
    state_elected="RO",
)
HOMONIMO_SP = ParliamentarianRecord(
    id=3, name="João Silva", full_name="João da Silva", cpf=None, state_elected="SP"
)
HOMONIMO_BA = ParliamentarianRecord(
    id=4, name="João Silva", full_name="João da Silva", cpf=None, state_elected="BA"
)

INDEX = build_index([DEPUTADO, SENADOR, HOMONIMO_SP, HOMONIMO_BA])


def test_cpf_casa_mesmo_com_nome_diferente():
    result = match_candidacy(
        cpf="111.222.333-44",
        full_name="NOME COMPLETAMENTE OUTRO",
        ballot_name="OUTRO",
        state="RS",
        index=INDEX,
    )
    assert result.parliamentarian_id == 1
    assert result.status == MATCH_STATUS_CPF


def test_senador_sem_cpf_casa_por_nome_completo():
    result = match_candidacy(
        cpf=None,
        full_name="MARCOS ROGÉRIO DA SILVA BRITO",
        ballot_name="MARCOS ROGERIO",
        state="RO",
        index=INDEX,
    )
    assert result.parliamentarian_id == 2
    assert result.status == MATCH_STATUS_NAME


def test_nome_de_urna_tambem_casa():
    result = match_candidacy(
        cpf=None,
        full_name="NOME CIVIL DIVERGENTE",
        ballot_name="MARCOS ROGÉRIO",
        state="RO",
        index=INDEX,
    )
    assert result.parliamentarian_id == 2
    assert result.status == MATCH_STATUS_NAME


def test_homonimo_desempata_por_uf():
    result = match_candidacy(
        cpf=None,
        full_name="JOÃO DA SILVA",
        ballot_name="JOAO SILVA",
        state="BA",
        index=INDEX,
    )
    assert result.parliamentarian_id == 4
    assert result.status == MATCH_STATUS_NAME


def test_homonimo_sem_desempate_e_ambiguo():
    result = match_candidacy(
        cpf=None,
        full_name="JOÃO DA SILVA",
        ballot_name="JOAO SILVA",
        state="MG",
        index=INDEX,
    )
    assert result.parliamentarian_id is None
    assert result.status == MATCH_STATUS_AMBIGUOUS


def test_desconhecido_nao_casa():
    result = match_candidacy(
        cpf="99988877766",
        full_name="PESSOA NOVA NA POLITICA",
        ballot_name="NOVATO",
        state="SP",
        index=INDEX,
    )
    assert result.parliamentarian_id is None
    assert result.status == MATCH_STATUS_UNMATCHED
```

- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar** — `matching.py`:

```python
"""Casamento entre candidatura do TSE e a base de parlamentares.

CPF primeiro: e identificador civil, imune a homonimo (100% dos deputados tem
CPF na base; medido em producao em 2026-08-07). Senadores nao tem CPF na base,
entao caem na cascata por nome normalizado — exata, sem fuzzy, pela mesma
razao do author_matching das emendas: em produto de transparencia, palpite
silencioso e pior que lacuna declarada.
"""

from __future__ import annotations

from typing import Dict, List, NamedTuple, Optional, Sequence

from .parsing import normalize_cpf, normalize_text

MATCH_STATUS_CPF = "matched_cpf"
MATCH_STATUS_NAME = "matched_name"
MATCH_STATUS_AMBIGUOUS = "ambiguous"
MATCH_STATUS_UNMATCHED = "unmatched"
MATCH_STATUS_MANUAL = "manual"


class ParliamentarianRecord(NamedTuple):
    id: int
    name: Optional[str]
    full_name: Optional[str]
    cpf: Optional[str]
    state_elected: Optional[str]


class MatchResult(NamedTuple):
    parliamentarian_id: Optional[int]
    status: str


class MatchIndex(NamedTuple):
    by_cpf: Dict[str, List[ParliamentarianRecord]]
    by_name: Dict[str, List[ParliamentarianRecord]]


def build_index(records: Sequence[ParliamentarianRecord]) -> MatchIndex:
    by_cpf: Dict[str, List[ParliamentarianRecord]] = {}
    by_name: Dict[str, List[ParliamentarianRecord]] = {}
    for record in records:
        cpf = normalize_cpf(record.cpf)
        if cpf:
            by_cpf.setdefault(cpf, []).append(record)
        for attribute in (record.full_name, record.name):
            key = normalize_text(attribute)
            if key:
                bucket = by_name.setdefault(key, [])
                if record not in bucket:
                    bucket.append(record)
    return MatchIndex(by_cpf=by_cpf, by_name=by_name)


def _resolve_by_state(
    hits: List[ParliamentarianRecord], state: Optional[str]
) -> MatchResult:
    if len(hits) == 1:
        return MatchResult(hits[0].id, MATCH_STATUS_NAME)
    state_key = normalize_text(state)
    filtered = [
        hit for hit in hits if normalize_text(hit.state_elected) == state_key
    ]
    if len(filtered) == 1:
        return MatchResult(filtered[0].id, MATCH_STATUS_NAME)
    return MatchResult(None, MATCH_STATUS_AMBIGUOUS)


def match_candidacy(
    *,
    cpf: Optional[str],
    full_name: Optional[str],
    ballot_name: Optional[str],
    state: Optional[str],
    index: MatchIndex,
) -> MatchResult:
    cpf_key = normalize_cpf(cpf)
    if cpf_key:
        hits = index.by_cpf.get(cpf_key, [])
        if len(hits) == 1:
            return MatchResult(hits[0].id, MATCH_STATUS_CPF)
        if len(hits) > 1:
            return MatchResult(None, MATCH_STATUS_AMBIGUOUS)

    for name in (full_name, ballot_name):
        key = normalize_text(name)
        if not key:
            continue
        hits = index.by_name.get(key, [])
        if hits:
            return _resolve_by_state(hits, state)

    return MatchResult(None, MATCH_STATUS_UNMATCHED)


__all__ = [
    "MATCH_STATUS_AMBIGUOUS",
    "MATCH_STATUS_CPF",
    "MATCH_STATUS_MANUAL",
    "MATCH_STATUS_NAME",
    "MATCH_STATUS_UNMATCHED",
    "MatchIndex",
    "MatchResult",
    "ParliamentarianRecord",
    "build_index",
    "match_candidacy",
]
```

- [ ] **Step 4: Rodar e ver passar.**
- [ ] **Step 5: Commit** — `feat(tse): matching candidato-parlamentar por CPF e nome`

---

### Task 4: Cliente DivulgaCandContas

**Files:**
- Create: `mamute_scrappers/tse_crawler/client.py`
- Test: `mamute_scrappers/tests/test_tse_client.py`

**Interfaces:**
- Produces: `DivulgaCandClient(request_delay=0.5)` com `find_general_election_id(year) -> int|None`, `list_candidates(year, state, election_id, office_code) -> list[dict]` (levanta `IncompleteListingError` em falha persistente), `get_candidate_detail(year, state, election_id, candidate_id) -> dict|None` (None em falha persistente). `BASE_URL`, `IncompleteListingError`.

- [ ] **Step 1: Testes que falham** — `test_tse_client.py` (mock de `requests.get`, sem rede):

```python
from __future__ import annotations

from unittest import mock

import pytest
import requests

from mamute_scrappers.tse_crawler import client as client_mod
from mamute_scrappers.tse_crawler.client import (
    DivulgaCandClient,
    IncompleteListingError,
)


def _response(json_data, status=200):
    resp = mock.Mock()
    resp.raise_for_status = mock.Mock()
    if status >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(str(status))
    resp.json = mock.Mock(return_value=json_data)
    return resp


@pytest.fixture()
def no_sleep(monkeypatch):
    monkeypatch.setattr(client_mod.time, "sleep", lambda *_: None)


def test_find_general_election_id(no_sleep):
    payload = [
        {"id": 20322002026, "ano": 2026, "tipoAbrangencia": "F"},
        {"id": 2045202024, "ano": 2024, "tipoAbrangencia": "M"},
    ]
    with mock.patch.object(client_mod.requests, "get", return_value=_response(payload)):
        assert DivulgaCandClient().find_general_election_id(2026) == 20322002026
        assert DivulgaCandClient().find_general_election_id(2030) is None


def test_listagem_retenta_e_devolve_candidatos(no_sleep):
    ok = _response({"candidatos": [{"id": 1}, {"id": 2}]})
    with mock.patch.object(
        client_mod.requests, "get", side_effect=[_response(None, status=504), ok]
    ):
        candidates = DivulgaCandClient().list_candidates(2026, "AC", 20322002026, 5)
    assert [c["id"] for c in candidates] == [1, 2]


def test_listagem_com_falha_persistente_e_ruidosa(no_sleep):
    bad = requests.ConnectionError("down")
    with mock.patch.object(client_mod.requests, "get", side_effect=bad):
        with pytest.raises(IncompleteListingError):
            DivulgaCandClient().list_candidates(2026, "AC", 20322002026, 5)


def test_detalhe_com_falha_persistente_devolve_none(no_sleep):
    bad = requests.ConnectionError("down")
    with mock.patch.object(client_mod.requests, "get", side_effect=bad):
        detail = DivulgaCandClient().get_candidate_detail(2026, "AC", 20322002026, 99)
    assert detail is None


def test_listagem_vazia_e_fim_legitimo(no_sleep):
    with mock.patch.object(
        client_mod.requests, "get", return_value=_response({"candidatos": []})
    ):
        assert DivulgaCandClient().list_candidates(2026, "RR", 20322002026, 5) == []
```

- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar** — `client.py`:

```python
"""Cliente HTTP da DivulgaCandContas (TSE).

API publica sem chave e sem SLA. Endpoints validados ao vivo em 2026-08-07:
`/eleicao/ordinarias` (id da eleicao geral 2026 = 20322002026),
`/candidatura/listar/...` (CPF vem nulo aqui) e `/candidatura/buscar/...`
(detalhe, com CPF, foto e dataUltimaAtualizacao).

Falha persistente de LISTAGEM levanta IncompleteListingError: truncar em
silencio deixaria a eleicao incompleta com cara de sucesso — o mesmo bug do
504 das emendas 2022. Falha de DETALHE devolve None: o registro fica sem
fingerprint e a proxima execucao tenta de novo.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://divulgacandcontas.tse.jus.br/divulga/rest/v1"
DEFAULT_REQUEST_DELAY = 0.5
REQUEST_TIMEOUT = 60
MAX_ATTEMPTS = 4
RETRY_BACKOFF_SECONDS = 5


class IncompleteListingError(RuntimeError):
    """Uma listagem UF x cargo nao pode ser lida; a eleicao ficaria incompleta."""


class DivulgaCandClient:
    def __init__(self, *, request_delay: float = DEFAULT_REQUEST_DELAY) -> None:
        self._request_delay = request_delay

    def _get_json(self, url: str) -> Optional[Any]:
        try:
            response = requests.get(
                url,
                headers={"Accept": "application/json"},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            logger.error("Falha na DivulgaCandContas (%s): %s", url, exc)
            return None

    def _get_json_with_retry(self, url: str) -> Optional[Any]:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            data = self._get_json(url)
            if data is not None:
                if self._request_delay:
                    time.sleep(self._request_delay)
                return data
            if attempt < MAX_ATTEMPTS:
                wait = RETRY_BACKOFF_SECONDS * attempt
                logger.warning(
                    "Repetindo %s em %ss (tentativa %s/%s)",
                    url,
                    wait,
                    attempt,
                    MAX_ATTEMPTS,
                )
                time.sleep(wait)
        return None

    def find_general_election_id(self, year: int) -> Optional[int]:
        data = self._get_json_with_retry(f"{BASE_URL}/eleicao/ordinarias")
        if not isinstance(data, list):
            return None
        for election in data:
            if not isinstance(election, dict):
                continue
            if election.get("ano") == year and election.get("tipoAbrangencia") == "F":
                return election.get("id")
        return None

    def list_candidates(
        self, year: int, state: str, election_id: int, office_code: int
    ) -> List[Dict[str, Any]]:
        url = (
            f"{BASE_URL}/candidatura/listar/{year}/{state}/"
            f"{election_id}/{office_code}/candidatos"
        )
        data = self._get_json_with_retry(url)
        if data is None:
            raise IncompleteListingError(
                f"Listagem {state} cargo {office_code} ilegivel apos "
                f"{MAX_ATTEMPTS} tentativas; eleicao {year} ficaria incompleta."
            )
        candidates = data.get("candidatos") if isinstance(data, dict) else None
        if not isinstance(candidates, list):
            return []
        return [item for item in candidates if isinstance(item, dict)]

    def get_candidate_detail(
        self, year: int, state: str, election_id: int, candidate_id: int
    ) -> Optional[Dict[str, Any]]:
        url = (
            f"{BASE_URL}/candidatura/buscar/{year}/{state}/"
            f"{election_id}/candidato/{candidate_id}"
        )
        data = self._get_json_with_retry(url)
        return data if isinstance(data, dict) else None


__all__ = [
    "BASE_URL",
    "DEFAULT_REQUEST_DELAY",
    "DivulgaCandClient",
    "IncompleteListingError",
    "MAX_ATTEMPTS",
]
```

- [ ] **Step 4: Rodar e ver passar.**
- [ ] **Step 5: Commit** — `feat(tse): cliente DivulgaCandContas com retry assimetrico`

---

### Task 5: Comando `candidacy` (upsert + fluxo incremental)

**Files:**
- Create: `mamute_scrappers/tse_crawler/candidacy.py`
- Test: `mamute_scrappers/tests/test_tse_candidacy_upsert.py`

**Interfaces:**
- Consumes: tudo das tasks 1–4.
- Produces: `upsert_candidacy(session, payload) -> (record, created)`, `run(ano=None, persist=True, dry_run_limit=None, max_details=None)`, `OFFICES`, executável via `python -m mamute_scrappers.tse_crawler.candidacy`.

- [ ] **Step 1: Testes que falham** — `test_tse_candidacy_upsert.py` (SQLite em memória com modelos-espelho, como `test_emendas_upsert.py`):

```python
from __future__ import annotations

from typing import Iterator

import pytest
from sqlalchemy import Column, ForeignKey, Integer, Text, UniqueConstraint, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from mamute_scrappers.tse_crawler import candidacy as candidacy_mod

Base = declarative_base()


class Parliamentarian(Base):
    __tablename__ = "parliamentarian"
    id = Column(Integer, primary_key=True)


class Candidacy(Base):
    __tablename__ = "candidacy"
    __table_args__ = (
        UniqueConstraint("election_year", "tse_candidate_id"),
    )
    id = Column(Integer, primary_key=True)
    election_year = Column(Integer, nullable=False)
    tse_candidate_id = Column(Integer, nullable=False)
    office_code = Column(Integer)
    office = Column(Text)
    state = Column(Text)
    ballot_number = Column(Integer)
    ballot_name = Column(Text)
    full_name = Column(Text)
    party = Column(Text)
    coalition = Column(Text)
    status = Column(Text)
    totalization_status = Column(Text)
    cpf = Column(Text)
    voter_id = Column(Text)
    photo_url = Column(Text)
    tse_last_update = Column(Text)
    listing_fingerprint = Column(Text)
    parliamentarian_id = Column(Integer, ForeignKey("parliamentarian.id"))
    match_status = Column(Text, nullable=False)


@pytest.fixture()
def session(monkeypatch) -> Iterator[Session]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(candidacy_mod, "Candidacy", Candidacy)
    with maker() as s:
        s.add(Parliamentarian(id=1))
        s.commit()
        yield s


def payload(**overrides):
    base = {
        "election_year": 2026,
        "tse_candidate_id": 10002536710,
        "office_code": 5,
        "office": "Senador",
        "state": "AC",
        "ballot_number": 277,
        "ballot_name": "DR. JUNIOR FEITOSA",
        "full_name": "RIBAMAR DE SOUSA FEITOZA JÚNIOR",
        "party": "DC",
        "coalition": "DC",
        "status": "Aguardando julgamento",
        "totalization_status": "Concorrendo",
        "cpf": "67146902234",
        "voter_id": "003576712402",
        "photo_url": "https://x/foto.jpg",
        "tse_last_update": None,
        "listing_fingerprint": "abc123",
        "parliamentarian_id": None,
        "match_status": "unmatched",
    }
    base.update(overrides)
    return base


def test_primeira_gravacao_cria(session):
    record, created = candidacy_mod.upsert_candidacy(session, payload())
    session.commit()
    assert created is True
    assert session.query(Candidacy).count() == 1
    assert record.listing_fingerprint == "abc123"


def test_upsert_e_idempotente(session):
    candidacy_mod.upsert_candidacy(session, payload())
    session.commit()
    _, created = candidacy_mod.upsert_candidacy(
        session, payload(status="Deferido", listing_fingerprint="def456")
    )
    session.commit()
    assert created is False
    record = session.query(Candidacy).one()
    assert record.status == "Deferido"
    assert record.listing_fingerprint == "def456"


def test_payload_sem_detalhe_nao_apaga_detalhe_anterior(session):
    candidacy_mod.upsert_candidacy(session, payload())
    session.commit()

    sem_detalhe = payload(status="Deferido")
    for campo in ("cpf", "voter_id", "photo_url", "tse_last_update",
                  "listing_fingerprint"):
        sem_detalhe.pop(campo)
    candidacy_mod.upsert_candidacy(session, sem_detalhe)
    session.commit()

    record = session.query(Candidacy).one()
    assert record.status == "Deferido"
    assert record.cpf == "67146902234"
    # Fingerprint fica o anterior: o detalhe nao foi relido, entao a mudanca
    # que o exigiu segue pendente para a proxima execucao... exceto que o
    # fingerprint antigo ja nao casa com a listagem nova — e exatamente por
    # isso o refetch acontece.
    assert record.listing_fingerprint == "abc123"


def test_correcao_manual_nao_e_sobrescrita(session):
    candidacy_mod.upsert_candidacy(session, payload())
    session.commit()
    record = session.query(Candidacy).one()
    record.parliamentarian_id = 1
    record.match_status = "manual"
    session.commit()

    candidacy_mod.upsert_candidacy(
        session, payload(parliamentarian_id=None, match_status="unmatched",
                         status="Deferido")
    )
    session.commit()

    record = session.query(Candidacy).one()
    assert record.parliamentarian_id == 1
    assert record.match_status == "manual"
    assert record.status == "Deferido"


def test_repeticao_no_mesmo_lote_nao_duplica(session):
    candidacy_mod.upsert_candidacy(session, payload())
    _, created = candidacy_mod.upsert_candidacy(session, payload(status="Deferido"))
    session.commit()
    assert created is False
    assert session.query(Candidacy).count() == 1
```

- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar** — `candidacy.py`:

```python
"""Coleta de candidaturas da Eleicao Geral (TSE/DivulgaCandContas) — CS-16.

Fluxo incremental: as listagens UF x cargo (~136 requests) rodam sempre; o
detalhe (que traz CPF e foto) so e buscado para candidatura nova ou cujo
fingerprint de listagem mudou. O fingerprint so e persistido quando o detalhe
foi lido com sucesso, entao falha de detalhe se auto-corrige na proxima
execucao.

Candidatura nunca e deletada: se sumir da listagem, a situacao muda pelo
proprio TSE (indeferido, renuncia, cassacao) e o historico fica.
"""

from __future__ import annotations

import logging
import sys
from collections import Counter
from contextlib import nullcontext
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mamute_scrappers.tse_crawler.client import DivulgaCandClient  # noqa: E402
from mamute_scrappers.tse_crawler.matching import (  # noqa: E402
    MATCH_STATUS_MANUAL,
    ParliamentarianRecord,
    build_index,
    match_candidacy,
)
from mamute_scrappers.tse_crawler.parsing import (  # noqa: E402
    build_listing_payload,
    compute_listing_fingerprint,
    merge_detail_payload,
)

logger = logging.getLogger(__name__)

COMMIT_EVERY = 200

UFS = (
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS",
    "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC",
    "SE", "SP", "TO",
)

# (codigo do cargo na DivulgaCandContas, nome, UFs onde o cargo existe).
# So titulares: vices e suplentes nao aparecem nas listagens destes cargos.
OFFICES = (
    (1, "Presidente", ("BR",)),
    (3, "Governador", UFS),
    (5, "Senador", UFS),
    (6, "Deputado Federal", UFS),
    (7, "Deputado Estadual", tuple(uf for uf in UFS if uf != "DF")),
    (8, "Deputado Distrital", ("DF",)),
)

Candidacy: Any = None

_LISTING_FIELDS = (
    "office_code",
    "office",
    "state",
    "ballot_number",
    "ballot_name",
    "full_name",
    "party",
    "coalition",
    "status",
    "totalization_status",
)

# So atualizados quando presentes no payload (ou seja, quando o detalhe foi
# lido nesta execucao). Um payload sem detalhe nao pode apagar o que ja havia.
_DETAIL_FIELDS = (
    "cpf",
    "voter_id",
    "photo_url",
    "tse_last_update",
    "details",
    "listing_fingerprint",
)


def _load_env_file() -> None:
    """Carrega o .env antes de ler o banco (mesma politica de emendas.py)."""
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover — dotenv e dependencia declarada
        return

    for env_file in (
        PROJECT_ROOT / "mamute_scrappers" / ".env",
        PROJECT_ROOT / ".env",
        Path.cwd() / ".env",
    ):
        if env_file.exists():
            load_dotenv(env_file, override=False)


def _ensure_model() -> None:
    global Candidacy
    if Candidacy is not None:
        return
    from mamute_scrappers.db.models import Candidacy as CandidacyRuntime

    Candidacy = CandidacyRuntime


def upsert_candidacy(
    session: Any, payload: Dict[str, Any]
) -> Tuple[Any, bool]:
    """Grava ou atualiza uma candidatura pela chave natural do TSE.

    Campos de listagem sempre sao atualizados. Campos de detalhe so quando
    presentes no payload. `manual` no match_status prevalece sobre o robo.
    """
    if Candidacy is None:
        _ensure_model()

    record = (
        session.query(Candidacy)
        .filter(
            Candidacy.election_year == payload["election_year"],
            Candidacy.tse_candidate_id == payload["tse_candidate_id"],
        )
        .one_or_none()
    )

    created = False
    if record is None:
        record = Candidacy(
            election_year=payload["election_year"],
            tse_candidate_id=payload["tse_candidate_id"],
        )
        session.add(record)
        created = True

    for field in _LISTING_FIELDS:
        setattr(record, field, payload.get(field))

    for field in _DETAIL_FIELDS:
        if field in payload:
            setattr(record, field, payload[field])

    if record.match_status != MATCH_STATUS_MANUAL:
        record.parliamentarian_id = payload.get("parliamentarian_id")
        record.match_status = payload.get("match_status")

    if created:
        # flush antes do proximo lookup no mesmo lote (autoflush=False na
        # sessao de producao); sem isso, repeticao no lote viraria duplicata.
        session.flush()

    return record, created


def _load_parliamentarian_index():
    from mamute_scrappers.db import session_scope
    from mamute_scrappers.db.models import Parliamentarian

    with session_scope() as session:
        rows = session.query(
            Parliamentarian.id,
            Parliamentarian.name,
            Parliamentarian.full_name,
            Parliamentarian.cpf,
            Parliamentarian.state_elected,
        ).all()

    return build_index(
        [
            ParliamentarianRecord(
                id=r[0], name=r[1], full_name=r[2], cpf=r[3], state_elected=r[4]
            )
            for r in rows
        ]
    )


def _load_known_fingerprints(year: int) -> Dict[int, Optional[str]]:
    _ensure_model()
    from mamute_scrappers.db import session_scope

    with session_scope() as session:
        rows = session.query(
            Candidacy.tse_candidate_id, Candidacy.listing_fingerprint
        ).filter(Candidacy.election_year == year).all()
    return {r[0]: r[1] for r in rows}


def run(
    *,
    ano: Optional[int] = None,
    persist: bool = True,
    dry_run_limit: Optional[int] = None,
    max_details: Optional[int] = None,
) -> None:
    ano = ano or date.today().year
    _load_env_file()
    client = DivulgaCandClient()

    election_id = client.find_general_election_id(ano)
    if election_id is None:
        logger.error("Nenhuma eleicao geral encontrada para %s.", ano)
        raise SystemExit(1)
    logger.info("Eleicao geral %s: id %s", ano, election_id)

    index = _load_parliamentarian_index()
    known = _load_known_fingerprints(ano)
    logger.info("Candidaturas ja conhecidas: %s", len(known))

    if persist:
        _ensure_model()
        from mamute_scrappers.db import session_scope

        session_context = session_scope()
    else:
        session_context = nullcontext(None)

    status_counter: Counter = Counter()
    total = 0
    unchanged = 0
    processed = 0
    inserted = 0
    updated = 0
    details_fetched = 0
    details_failed = 0

    with session_context as session:
        for office_code, office_name, states in OFFICES:
            for uf in states:
                candidates = client.list_candidates(ano, uf, election_id, office_code)
                for item in candidates:
                    total += 1
                    payload = build_listing_payload(
                        item,
                        election_year=ano,
                        office_code=office_code,
                        office_name=office_name,
                        state=uf,
                    )
                    if payload is None:
                        continue

                    fingerprint = compute_listing_fingerprint(item)
                    tse_id = payload["tse_candidate_id"]
                    if known.get(tse_id) == fingerprint:
                        unchanged += 1
                        continue

                    detail = None
                    if max_details is None or details_fetched < max_details:
                        details_fetched += 1
                        detail = client.get_candidate_detail(
                            ano, uf, election_id, tse_id
                        )
                        if detail is None:
                            details_failed += 1

                    if detail is not None:
                        payload = merge_detail_payload(payload, detail)
                        payload["listing_fingerprint"] = fingerprint

                    result = match_candidacy(
                        cpf=payload.get("cpf"),
                        full_name=payload.get("full_name"),
                        ballot_name=payload.get("ballot_name"),
                        state=uf,
                        index=index,
                    )
                    payload["parliamentarian_id"] = result.parliamentarian_id
                    payload["match_status"] = result.status
                    status_counter[result.status] += 1
                    processed += 1

                    if session is not None:
                        _, created = upsert_candidacy(session, payload)
                        if created:
                            inserted += 1
                        else:
                            updated += 1
                        known[tse_id] = payload.get("listing_fingerprint")
                        if (inserted + updated) % COMMIT_EVERY == 0:
                            session.commit()

                    if dry_run_limit is not None and processed >= dry_run_limit:
                        _log_summary(
                            ano, total, unchanged, processed, inserted, updated,
                            details_fetched, details_failed, status_counter,
                            persist,
                        )
                        return

    _log_summary(
        ano, total, unchanged, processed, inserted, updated,
        details_fetched, details_failed, status_counter, persist,
    )


def _log_summary(
    ano, total, unchanged, processed, inserted, updated,
    details_fetched, details_failed, status_counter, persist,
) -> None:
    logger.info("=== Candidaturas %s ===", ano)
    logger.info("Listados: %s | sem mudanca: %s | processados: %s",
                total, unchanged, processed)
    logger.info("Detalhes buscados: %s (falhas: %s)",
                details_fetched, details_failed)
    logger.info("Casamento: %s", dict(status_counter))
    if persist:
        logger.info("Persistencia: %s inseridos, %s atualizados.",
                    inserted, updated)
    else:
        logger.info("Modo dry-run: nada foi gravado.")


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        description="Coleta candidaturas da Eleicao Geral na DivulgaCandContas."
    )
    parser.add_argument("--ano", type=int,
                        help="Ano da eleicao (default: ano corrente).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Nao persiste; apenas reporta.")
    parser.add_argument("--limit", type=int,
                        help="Interrompe apos N candidaturas processadas.")
    parser.add_argument("--max-details", type=int,
                        help="Teto de buscas de detalhe nesta execucao; o "
                             "excedente fica sem fingerprint e e retomado.")

    args = parser.parse_args()
    run(
        ano=args.ano,
        persist=not args.dry_run,
        dry_run_limit=args.limit,
        max_details=args.max_details,
    )
```

- [ ] **Step 4: Rodar e ver passar** — `python3 -m pytest mamute_scrappers/tests/test_tse_candidacy_upsert.py -q`.
- [ ] **Step 5: Commit** — `feat(tse): comando de coleta incremental de candidaturas`

---

### Task 6: Cron + suíte completa

**Files:**
- Modify: `mamute_scrappers/docker/scrappers.cron` (novo job diário)

**Interfaces:**
- Consumes: `python -m mamute_scrappers.tse_crawler.candidacy` (Task 5).

- [ ] **Step 1: Adicionar o job** após o bloco de parlamentares (seguir formato dos vizinhos):

```cron
# Candidaturas do TSE (DivulgaCandContas) — incremental: listagens sempre,
# detalhe so de candidatura nova ou alterada. Diario durante o periodo
# eleitoral; a situacao (deferido/indeferido) muda por semanas apos 15/08.
20 6 * * * cd /app && /app/mamute_scrappers/docker/run-cron-job.sh tse-candidacies -- /usr/local/bin/python -m mamute_scrappers.tse_crawler.candidacy >> /proc/1/fd/1 2>> /proc/1/fd/2
```

- [ ] **Step 2: Suíte completa** — `python3 -m pytest mamute_scrappers/tests/ -q`. Expected: tudo verde (novos + regressão).
- [ ] **Step 3: Commit** — `feat(tse): cron diario tse-candidacies`
- [ ] **Step 4: Push + PR contra main** com resumo executivo, decisões, comando da carga inicial e follow-ups.

## Self-review

- Cobertura do spec: modelo/migração (T1), parsing+fingerprint (T2), matching (T3), client com falha assimétrica (T4), comando incremental+upsert+manual (T5), cron (T6). UI: fora de escopo, sem task — correto.
- Sem placeholders; assinaturas conferidas entre tasks (`build_index`/`match_candidacy` usados em T5 como definidos em T3; `IncompleteListingError` propaga no T5 por design — derruba a execução com exit != 0 e o cron retoma no dia seguinte).
