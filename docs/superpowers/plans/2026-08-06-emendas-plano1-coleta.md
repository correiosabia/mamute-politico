# Emendas parlamentares — Plano 1: coleta e casamento

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Coletar emendas parlamentares individuais do Portal da Transparência (2022 → ano corrente), casá-las com a base de parlamentares por nome e persistir tudo — inclusive o que não casou — de forma idempotente e agendada.

**Architecture:** Três módulos puros e testáveis sem rede nem banco (parsing, casamento, cliente HTTP), consumidos por um crawler no molde de `camara_crawler/plenary_attendance.py`. Um orquestrador de backfill no molde de `scripts/backfill_propositions.py` cobre os anos anteriores em fatias, com trava de arquivo e encerramento automático. A exposição em API e UI é o Plano 2.

**Tech Stack:** Python 3.11, SQLAlchemy 2.0, Alembic 1.14, `requests`, pytest.

**Spec:** `docs/superpowers/specs/2026-08-06-emendas-parlamentares-design.md`

## Global Constraints

- Módulo novo em `mamute_scrappers/portal_crawler/` (pacote novo, com `__init__.py`).
- Toda função de parsing e casamento é pura: sem rede, sem banco, sem I/O. Os testes dela nunca tocam a rede.
- Crawlers são idempotentes: rodar de novo atualiza linhas existentes sem duplicar. É convenção registrada em `AGENTS.md`.
- Nomes de tabela e coluna em inglês, snake_case — padrão de todas as tabelas do projeto.
- Mensagens de log e docstrings em português, como no resto de `mamute_scrappers/`.
- `mamute_scrappers/requirements.txt` **não** inclui pytest. Para rodar os testes localmente: `pip install pytest` no venv.
- Comando de teste, a partir da raiz do repositório: `pytest mamute_scrappers/tests/ -v`
- Nunca imprimir a chave de API em log, erro ou mensagem de exceção.

## Contrato da fonte (verificado no OpenAPI em 2026-08-06)

```
GET https://api.portaldatransparencia.gov.br/api-de-dados/emendas
    ?ano=<int>&pagina=<int>
    header: chave-api-dados: <PORTAL_TRANSPARENCIA_API_KEY>
```

**A resposta 200 é um array JSON puro**, não um envelope. Isso difere dos
crawlers existentes da Câmara, que devolvem `{"dados": [...], "links": [...]}`.
Não há campo de total nem link `next`: a paginação termina quando a página vem
vazia.

Cada item:

```json
{
  "codigoEmenda": "202600010001",
  "ano": 2026,
  "tipoEmenda": "...",
  "autor": "...",
  "nomeAutor": "...",
  "numeroEmenda": "...",
  "localidadeDoGasto": "...",
  "funcao": "...",
  "subfuncao": "...",
  "valorEmpenhado": "1.000.000,00",
  "valorLiquidado": "0,00",
  "valorPago": "0,00",
  "valorRestoInscrito": "0,00",
  "valorRestoCancelado": "0,00",
  "valorRestoPago": "0,00"
}
```

Todos os valores monetários chegam como **string em formato brasileiro**.

---

### Task 1: Parsing de valores e classificação de tipo

**Files:**
- Create: `mamute_scrappers/portal_crawler/__init__.py`
- Create: `mamute_scrappers/portal_crawler/parsing.py`
- Test: `mamute_scrappers/tests/test_emendas_parsing.py`

**Interfaces:**
- Consumes: nada (primeira task)
- Produces:
  - `parse_brl(value: Any) -> Optional[Decimal]`
  - `is_individual_amendment(amendment_type: Optional[str]) -> bool`
  - `normalize_text(value: Optional[str]) -> str`

`normalize_text` nasce aqui, e não no módulo de casamento, porque a Task 2 e a
classificação de tipo precisam da mesma normalização.

- [ ] **Step 1: Escreva o teste que falha**

Crie `mamute_scrappers/tests/test_emendas_parsing.py`:

```python
from __future__ import annotations

import importlib.util
from decimal import Decimal
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, relative_path: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


parsing = load_module(
    "test_emendas_parsing_module",
    "mamute_scrappers/portal_crawler/parsing.py",
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("1.000.000,00", Decimal("1000000.00")),
        ("0,00", Decimal("0.00")),
        ("1.500,50", Decimal("1500.50")),
        ("-1.500,50", Decimal("-1500.50")),
        ("250,00", Decimal("250.00")),
        # Sem centavos: o ponto e separador de milhar no formato brasileiro,
        # entao "1.000" vale mil, nunca um inteiro e meio.
        ("1.000", Decimal("1000")),
        ("  2.000,00  ", Decimal("2000.00")),
        ("R$ 3.000,00", Decimal("3000.00")),
    ],
)
def test_parse_brl_converte_formato_brasileiro(raw, expected):
    assert parsing.parse_brl(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", None, "-", "n/a"])
def test_parse_brl_devolve_none_para_vazio_ou_invalido(raw):
    assert parsing.parse_brl(raw) is None


def test_parse_brl_aceita_numero_ja_tipado():
    assert parsing.parse_brl(1500) == Decimal("1500")
    assert parsing.parse_brl(Decimal("12.34")) == Decimal("12.34")


@pytest.mark.parametrize(
    "raw",
    [
        "Individual",
        "INDIVIDUAL",
        "Emenda Individual",
        "Individual - Impositiva",
        "  individual  ",
    ],
)
def test_is_individual_amendment_reconhece_variacoes(raw):
    assert parsing.is_individual_amendment(raw) is True


@pytest.mark.parametrize(
    "raw",
    ["Bancada", "Emenda de Bancada", "Comissão", "Relator", "", None, "Coletiva"],
)
def test_is_individual_amendment_rejeita_demais_tipos(raw):
    assert parsing.is_individual_amendment(raw) is False


def test_normalize_text_remove_acento_e_caixa():
    assert parsing.normalize_text("José  da  SILVA") == "jose da silva"
    assert parsing.normalize_text("  Comissão ") == "comissao"
    assert parsing.normalize_text(None) == ""
```

- [ ] **Step 2: Rode o teste e confirme que falha**

Run: `pytest mamute_scrappers/tests/test_emendas_parsing.py -v`
Expected: FAIL — `FileNotFoundError` / `spec is not None` falhando, porque
`mamute_scrappers/portal_crawler/parsing.py` ainda não existe.

- [ ] **Step 3: Implemente o mínimo**

Crie `mamute_scrappers/portal_crawler/__init__.py` vazio (arquivo em branco).

Crie `mamute_scrappers/portal_crawler/parsing.py`:

```python
"""Conversao dos campos textuais devolvidos pelo Portal da Transparencia.

Todos os valores monetarios chegam como string em formato brasileiro
("1.000.000,00") e o tipo de emenda chega como texto livre, sem enumeracao
declarada no OpenAPI da fonte.
"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

_NON_NUMERIC = re.compile(r"[^0-9,.\-]")

INDIVIDUAL_MARKER = "individual"


def normalize_text(value: Optional[str]) -> str:
    """Minusculas, sem diacriticos, espacos colapsados."""
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", str(value))
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(normalized.lower().split())


def parse_brl(value: Any) -> Optional[Decimal]:
    """Converte "1.000.000,00" em Decimal("1000000.00").

    O ponto e sempre separador de milhar e a virgula sempre separador decimal,
    porque e o formato que a fonte usa. Devolve None quando o valor e vazio ou
    nao representa um numero.
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))

    cleaned = _NON_NUMERIC.sub("", str(value).strip())
    if not cleaned or cleaned in {"-", ",", "."}:
        return None

    cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def is_individual_amendment(amendment_type: Optional[str]) -> bool:
    """Verdadeiro para emendas de autoria individual.

    O OpenAPI da fonte declara `tipoEmenda` como string livre, sem enumerar os
    valores possiveis. A checagem e por substring normalizada para sobreviver a
    variacoes de caixa, acento e sufixo ("Individual - Impositiva").
    """
    return INDIVIDUAL_MARKER in normalize_text(amendment_type)
```

- [ ] **Step 4: Rode os testes e confirme que passam**

Run: `pytest mamute_scrappers/tests/test_emendas_parsing.py -v`
Expected: PASS — 21 testes.

- [ ] **Step 5: Commit**

```bash
git add mamute_scrappers/portal_crawler/__init__.py \
        mamute_scrappers/portal_crawler/parsing.py \
        mamute_scrappers/tests/test_emendas_parsing.py
git commit -m "feat(emendas): parsing de valor em real e classificacao de tipo de emenda"
```

---

### Task 2: Casamento autor → parlamentar

**Files:**
- Create: `mamute_scrappers/portal_crawler/author_matching.py`
- Test: `mamute_scrappers/tests/test_emendas_author_matching.py`

**Interfaces:**
- Consumes: `parsing.normalize_text` da Task 1
- Produces:
  - Constantes `MATCH_STATUS_MATCHED`, `MATCH_STATUS_UNMATCHED`, `MATCH_STATUS_AMBIGUOUS`, `MATCH_STATUS_MANUAL` (valores `"matched"`, `"unmatched"`, `"ambiguous"`, `"manual"`)
  - `ParliamentarianCandidate(NamedTuple)` com campos `id: int`, `name: Optional[str]`, `full_name: Optional[str]`
  - `MatchResult(NamedTuple)` com campos `parliamentarian_id: Optional[int]`, `status: str`
  - `match_author(author_name: Optional[str], candidates: Sequence[ParliamentarianCandidate]) -> MatchResult`

O módulo recebe `ParliamentarianCandidate` e não objetos SQLAlchemy. É o que
permite testar a regra mais delicada do sistema sem levantar banco.

- [ ] **Step 1: Escreva o teste que falha**

Crie `mamute_scrappers/tests/test_emendas_author_matching.py`:

```python
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, relative_path: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


matching = load_module(
    "test_emendas_matching_module",
    "mamute_scrappers/portal_crawler/author_matching.py",
)

Candidate = matching.ParliamentarianCandidate


def candidates():
    return [
        Candidate(id=1, name="José da Silva", full_name="José da Silva Júnior"),
        Candidate(id=2, name="Maria Souza", full_name="Maria de Souza Lima"),
        Candidate(id=3, name="Chico Alencar", full_name="Francisco Rodrigues Alencar"),
    ]


def test_casa_pelo_nome_parlamentar():
    result = matching.match_author("José da Silva", candidates())
    assert result.parliamentarian_id == 1
    assert result.status == matching.MATCH_STATUS_MATCHED


def test_casa_ignorando_acento_e_caixa():
    result = matching.match_author("JOSE DA SILVA", candidates())
    assert result.parliamentarian_id == 1
    assert result.status == matching.MATCH_STATUS_MATCHED


def test_casa_ignorando_espaco_duplicado():
    result = matching.match_author("Maria   Souza", candidates())
    assert result.parliamentarian_id == 2
    assert result.status == matching.MATCH_STATUS_MATCHED


def test_casa_pelo_nome_civil_quando_nome_parlamentar_nao_bate():
    # O Portal publica o nome civil; a nossa base guarda o nome de guerra.
    result = matching.match_author("Francisco Rodrigues Alencar", candidates())
    assert result.parliamentarian_id == 3
    assert result.status == matching.MATCH_STATUS_MATCHED


def test_nome_parlamentar_tem_precedencia_sobre_nome_civil():
    conflito = [
        Candidate(id=10, name="Ana Paula", full_name="Ana Paula Ferreira"),
        Candidate(id=11, name="Ana Paula Ferreira", full_name="Ana Paula Ferreira"),
    ]
    # "Ana Paula" casa exatamente com o `name` de 10 e com nada de 11.
    result = matching.match_author("Ana Paula", conflito)
    assert result.parliamentarian_id == 10
    assert result.status == matching.MATCH_STATUS_MATCHED


def test_sem_candidato_devolve_unmatched():
    result = matching.match_author("Fulano Inexistente", candidates())
    assert result.parliamentarian_id is None
    assert result.status == matching.MATCH_STATUS_UNMATCHED


def test_homonimo_devolve_ambiguous_sem_escolher():
    homonimos = [
        Candidate(id=4, name="João Silva", full_name="João Silva Neto"),
        Candidate(id=5, name="João Silva", full_name="João Silva Filho"),
    ]
    result = matching.match_author("João Silva", homonimos)
    assert result.parliamentarian_id is None
    assert result.status == matching.MATCH_STATUS_AMBIGUOUS


def test_autor_vazio_devolve_unmatched():
    for vazio in ("", "   ", None):
        result = matching.match_author(vazio, candidates())
        assert result.parliamentarian_id is None
        assert result.status == matching.MATCH_STATUS_UNMATCHED


def test_lista_de_candidatos_vazia_devolve_unmatched():
    result = matching.match_author("José da Silva", [])
    assert result.parliamentarian_id is None
    assert result.status == matching.MATCH_STATUS_UNMATCHED


def test_candidato_com_campos_nulos_nao_quebra():
    parciais = [Candidate(id=6, name=None, full_name=None)]
    result = matching.match_author("Qualquer Nome", parciais)
    assert result.status == matching.MATCH_STATUS_UNMATCHED


def test_nao_faz_casamento_aproximado():
    # Um caractere de diferenca nao pode casar: atribuir dinheiro publico por
    # semelhanca e o erro que este modulo existe para evitar.
    result = matching.match_author("Jose da Silvo", candidates())
    assert result.parliamentarian_id is None
    assert result.status == matching.MATCH_STATUS_UNMATCHED
```

- [ ] **Step 2: Rode o teste e confirme que falha**

Run: `pytest mamute_scrappers/tests/test_emendas_author_matching.py -v`
Expected: FAIL — o módulo `author_matching.py` não existe.

- [ ] **Step 3: Implemente o mínimo**

Crie `mamute_scrappers/portal_crawler/author_matching.py`:

```python
"""Casamento entre o autor textual da emenda e a base de parlamentares.

O Portal da Transparencia nao devolve identificador de parlamentar: o autor vem
apenas como texto em `nomeAutor`. Este modulo resolve esse texto para um id da
tabela `parliamentarian`, ou declara explicitamente que nao conseguiu.

Nao existe casamento aproximado aqui, e isso e deliberado. Fuzzy silencioso em
produto de transparencia atribui dinheiro publico a pessoa errada, e o erro e
invisivel justamente por ser silencioso. Sugestao aproximada, se um dia
existir, e trabalho do painel de administracao, revisada por humano.
"""

from __future__ import annotations

from typing import Dict, List, NamedTuple, Optional, Sequence

from .parsing import normalize_text

MATCH_STATUS_MATCHED = "matched"
MATCH_STATUS_UNMATCHED = "unmatched"
MATCH_STATUS_AMBIGUOUS = "ambiguous"
MATCH_STATUS_MANUAL = "manual"


class ParliamentarianCandidate(NamedTuple):
    """Parlamentar candidato, desacoplado do modelo SQLAlchemy."""

    id: int
    name: Optional[str]
    full_name: Optional[str]


class MatchResult(NamedTuple):
    parliamentarian_id: Optional[int]
    status: str


def _index_by(
    candidates: Sequence[ParliamentarianCandidate],
    attribute: str,
) -> Dict[str, List[int]]:
    index: Dict[str, List[int]] = {}
    for candidate in candidates:
        key = normalize_text(getattr(candidate, attribute))
        if not key:
            continue
        index.setdefault(key, []).append(candidate.id)
    return index


def _resolve(ids: List[int]) -> Optional[MatchResult]:
    if len(ids) == 1:
        return MatchResult(ids[0], MATCH_STATUS_MATCHED)
    if len(ids) > 1:
        return MatchResult(None, MATCH_STATUS_AMBIGUOUS)
    return None


def match_author(
    author_name: Optional[str],
    candidates: Sequence[ParliamentarianCandidate],
) -> MatchResult:
    """Resolve o nome textual do autor para um parlamentar.

    A cascata tenta primeiro o nome parlamentar (`name`) e so depois o nome
    civil (`full_name`). Um nome que case com mais de um parlamentar devolve
    `ambiguous` sem escolher nenhum.
    """
    key = normalize_text(author_name)
    if not key or not candidates:
        return MatchResult(None, MATCH_STATUS_UNMATCHED)

    for attribute in ("name", "full_name"):
        resolved = _resolve(_index_by(candidates, attribute).get(key, []))
        if resolved is not None:
            return resolved

    return MatchResult(None, MATCH_STATUS_UNMATCHED)
```

- [ ] **Step 4: Rode os testes e confirme que passam**

Run: `pytest mamute_scrappers/tests/test_emendas_author_matching.py -v`
Expected: PASS — 11 testes.

- [ ] **Step 5: Commit**

```bash
git add mamute_scrappers/portal_crawler/author_matching.py \
        mamute_scrappers/tests/test_emendas_author_matching.py
git commit -m "feat(emendas): casamento deterministico entre autor da emenda e parlamentar"
```

---

### Task 3: Cliente do Portal e modo diagnóstico

**Files:**
- Create: `mamute_scrappers/portal_crawler/client.py`
- Create: `mamute_scrappers/portal_crawler/emendas.py`
- Modify: `mamute_scrappers/.env.example`
- Test: `mamute_scrappers/tests/test_emendas_client.py`

**Interfaces:**
- Consumes: `parsing.parse_brl`, `parsing.is_individual_amendment` (Task 1); `author_matching.match_author`, `ParliamentarianCandidate` (Task 2)
- Produces:
  - `client.PortalTransparenciaClient(api_key: str, *, request_delay: float = 2.0)` com método `iter_amendments(year: int) -> Iterator[Dict[str, Any]]`
  - `client.MissingApiKeyError(RuntimeError)`
  - `emendas.build_payload(item: Dict[str, Any]) -> Dict[str, Any]`
  - `emendas.emendas(*, ano: int, persist: bool = True, dry_run_limit: Optional[int] = None) -> None`

Esta task termina com um comando executável que **não escreve no banco** e
imprime a taxa de casamento. É a fatia diagnóstica da spec: ela decide o peso
das tasks seguintes.

- [ ] **Step 1: Escreva o teste que falha**

Crie `mamute_scrappers/tests/test_emendas_client.py`:

```python
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, relative_path: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


client_mod = load_module(
    "test_emendas_client_module",
    "mamute_scrappers/portal_crawler/client.py",
)


class FakeResponse:
    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise client_mod.requests.HTTPError(f"status {self.status_code}")

    def json(self) -> Any:
        return self._payload


def test_exige_chave_de_api():
    with pytest.raises(client_mod.MissingApiKeyError):
        client_mod.PortalTransparenciaClient("")


def test_pagina_ate_receber_lista_vazia(monkeypatch):
    paginas = {1: [{"codigoEmenda": "a"}], 2: [{"codigoEmenda": "b"}], 3: []}
    chamadas: List[Dict[str, Any]] = []

    def fake_get(url, params=None, headers=None, timeout=None):
        chamadas.append({"url": url, "params": params, "headers": headers})
        return FakeResponse(paginas[params["pagina"]])

    monkeypatch.setattr(client_mod.requests, "get", fake_get)

    api = client_mod.PortalTransparenciaClient("chave-secreta", request_delay=0)
    itens = list(api.iter_amendments(2026))

    assert [i["codigoEmenda"] for i in itens] == ["a", "b"]
    assert [c["params"]["pagina"] for c in chamadas] == [1, 2, 3]
    assert all(c["params"]["ano"] == 2026 for c in chamadas)


def test_envia_a_chave_no_header_esperado(monkeypatch):
    capturado: Dict[str, Any] = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        capturado.update(headers or {})
        return FakeResponse([])

    monkeypatch.setattr(client_mod.requests, "get", fake_get)
    client_mod.PortalTransparenciaClient("chave-secreta", request_delay=0)
    list(client_mod.PortalTransparenciaClient("chave-secreta", request_delay=0)
         .iter_amendments(2026))

    assert capturado["chave-api-dados"] == "chave-secreta"


def test_erro_http_encerra_a_paginacao_sem_propagar(monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        return FakeResponse({}, status_code=500)

    monkeypatch.setattr(client_mod.requests, "get", fake_get)

    api = client_mod.PortalTransparenciaClient("chave", request_delay=0)
    assert list(api.iter_amendments(2026)) == []


def test_resposta_que_nao_e_lista_encerra_a_paginacao(monkeypatch):
    # A fonte devolve array puro; um dict e sinal de erro disfarcado de 200.
    def fake_get(url, params=None, headers=None, timeout=None):
        return FakeResponse({"Erro na API": "..."})

    monkeypatch.setattr(client_mod.requests, "get", fake_get)

    api = client_mod.PortalTransparenciaClient("chave", request_delay=0)
    assert list(api.iter_amendments(2026)) == []


def test_a_chave_nunca_aparece_em_repr():
    api = client_mod.PortalTransparenciaClient("chave-super-secreta")
    assert "chave-super-secreta" not in repr(api)
```

E, no mesmo arquivo, o teste do payload:

```python
emendas_mod = load_module(
    "test_emendas_payload_module",
    "mamute_scrappers/portal_crawler/emendas.py",
)


ITEM = {
    "codigoEmenda": "202600010001",
    "ano": 2026,
    "tipoEmenda": "Individual - Impositiva",
    "autor": "1234",
    "nomeAutor": "José da Silva",
    "numeroEmenda": "0001",
    "localidadeDoGasto": "TERESINA - PI",
    "funcao": "Saúde",
    "subfuncao": "Atenção Básica",
    "valorEmpenhado": "2.000.000,00",
    "valorLiquidado": "500.000,00",
    "valorPago": "500.000,00",
    "valorRestoInscrito": "0,00",
    "valorRestoCancelado": "0,00",
    "valorRestoPago": "0,00",
}


def test_build_payload_converte_campos():
    from decimal import Decimal

    payload = emendas_mod.build_payload(ITEM)

    assert payload["amendment_code"] == "202600010001"
    assert payload["year"] == 2026
    assert payload["amendment_number"] == "0001"
    assert payload["amendment_type"] == "Individual - Impositiva"
    assert payload["author_name_raw"] == "José da Silva"
    assert payload["author_raw"] == "1234"
    assert payload["spending_locality"] == "TERESINA - PI"
    assert payload["function"] == "Saúde"
    assert payload["subfunction"] == "Atenção Básica"
    assert payload["committed_value"] == Decimal("2000000.00")
    assert payload["settled_value"] == Decimal("500000.00")
    assert payload["paid_value"] == Decimal("500000.00")


def test_build_payload_sem_codigo_devolve_none():
    assert emendas_mod.build_payload({"ano": 2026}) is None
```

- [ ] **Step 2: Rode o teste e confirme que falha**

Run: `pytest mamute_scrappers/tests/test_emendas_client.py -v`
Expected: FAIL — `client.py` e `emendas.py` não existem.

- [ ] **Step 3: Implemente o cliente**

Crie `mamute_scrappers/portal_crawler/client.py`:

```python
"""Cliente HTTP do Portal da Transparencia.

A API responde com um array JSON puro, sem envelope e sem contagem total. A
paginacao termina quando uma pagina volta vazia — nao ha link `next` como nas
APIs da Camara.

O limite de requisicoes e por chave, na casa de 30/minuto fora da madrugada.
Por isso o atraso padrao entre paginas e conservador.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Iterator, List, Optional

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://api.portaldatransparencia.gov.br/api-de-dados"
EMENDAS_ENDPOINT = f"{BASE_URL}/emendas"
API_KEY_HEADER = "chave-api-dados"
DEFAULT_REQUEST_DELAY = 2.0
REQUEST_TIMEOUT = 60


class MissingApiKeyError(RuntimeError):
    """Chave do Portal da Transparencia ausente ou vazia."""


class PortalTransparenciaClient:
    def __init__(
        self,
        api_key: str,
        *,
        request_delay: float = DEFAULT_REQUEST_DELAY,
    ) -> None:
        if not api_key or not api_key.strip():
            raise MissingApiKeyError(
                "PORTAL_TRANSPARENCIA_API_KEY nao definida. Cadastre-se em "
                "portaldatransparencia.gov.br/api-de-dados/cadastrar-email"
            )
        self._api_key = api_key.strip()
        self._request_delay = request_delay

    def __repr__(self) -> str:  # nunca expor a chave
        return f"<PortalTransparenciaClient delay={self._request_delay}>"

    def _get_page(self, year: int, page: int) -> Optional[List[Dict[str, Any]]]:
        try:
            response = requests.get(
                EMENDAS_ENDPOINT,
                params={"ano": year, "pagina": page},
                headers={API_KEY_HEADER: self._api_key, "Accept": "application/json"},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Falha ao consultar emendas (ano=%s, pagina=%s): %s", year, page, exc)
            return None

        try:
            data = response.json()
        except ValueError as exc:
            logger.error("JSON invalido do Portal (ano=%s, pagina=%s): %s", year, page, exc)
            return None

        if not isinstance(data, list):
            logger.error(
                "Resposta inesperada do Portal (ano=%s, pagina=%s): esperava lista, veio %s",
                year,
                page,
                type(data).__name__,
            )
            return None

        return [item for item in data if isinstance(item, dict)]

    def iter_amendments(self, year: int) -> Iterator[Dict[str, Any]]:
        """Itera todas as emendas de um ano, pagina a pagina."""
        page = 1
        while True:
            items = self._get_page(year, page)
            if not items:
                return
            yield from items
            page += 1
            if self._request_delay:
                time.sleep(self._request_delay)
```

- [ ] **Step 4: Implemente o crawler em modo diagnóstico**

Crie `mamute_scrappers/portal_crawler/emendas.py`. Nesta task ele **ainda não
persiste** — a persistência entra na Task 5, depois que o modelo existir.

```python
"""Coleta de emendas parlamentares individuais do Portal da Transparencia."""

from __future__ import annotations

import logging
import os
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mamute_scrappers.portal_crawler.author_matching import (  # noqa: E402
    MATCH_STATUS_UNMATCHED,
    ParliamentarianCandidate,
    match_author,
)
from mamute_scrappers.portal_crawler.client import (  # noqa: E402
    PortalTransparenciaClient,
)
from mamute_scrappers.portal_crawler.parsing import (  # noqa: E402
    is_individual_amendment,
    parse_brl,
)

logger = logging.getLogger(__name__)

API_KEY_ENV = "PORTAL_TRANSPARENCIA_API_KEY"


def _coerce_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    cleaned = " ".join(str(value).split())
    return cleaned or None


def _parse_int(value: Any) -> Optional[int]:
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def build_payload(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Converte um item cru da API no dicionario que a tabela espera."""
    amendment_code = _coerce_text(item.get("codigoEmenda"))
    if not amendment_code:
        return None

    return {
        "amendment_code": amendment_code,
        "year": _parse_int(item.get("ano")),
        "amendment_number": _coerce_text(item.get("numeroEmenda")),
        "amendment_type": _coerce_text(item.get("tipoEmenda")),
        "author_name_raw": _coerce_text(item.get("nomeAutor")),
        "author_raw": _coerce_text(item.get("autor")),
        "spending_locality": _coerce_text(item.get("localidadeDoGasto")),
        "function": _coerce_text(item.get("funcao")),
        "subfunction": _coerce_text(item.get("subfuncao")),
        "committed_value": parse_brl(item.get("valorEmpenhado")),
        "settled_value": parse_brl(item.get("valorLiquidado")),
        "paid_value": parse_brl(item.get("valorPago")),
        "remainder_inscribed": parse_brl(item.get("valorRestoInscrito")),
        "remainder_cancelled": parse_brl(item.get("valorRestoCancelado")),
        "remainder_paid": parse_brl(item.get("valorRestoPago")),
    }


def _load_candidates() -> List[ParliamentarianCandidate]:
    from mamute_scrappers.db import session_scope
    from mamute_scrappers.db.models import Parliamentarian

    with session_scope() as session:
        rows = session.query(
            Parliamentarian.id,
            Parliamentarian.name,
            Parliamentarian.full_name,
        ).all()

    return [ParliamentarianCandidate(id=r[0], name=r[1], full_name=r[2]) for r in rows]


def emendas(
    *,
    ano: Optional[int] = None,
    persist: bool = True,
    dry_run_limit: Optional[int] = None,
) -> None:
    """Coleta emendas individuais de um ano e reporta a taxa de casamento."""
    ano = ano or date.today().year
    api_key = os.getenv(API_KEY_ENV, "")
    client = PortalTransparenciaClient(api_key)

    candidates = _load_candidates()
    logger.info("Base de parlamentares carregada: %s candidatos.", len(candidates))

    tipos_vistos: Counter = Counter()
    status_counter: Counter = Counter()
    total = 0
    individuais = 0
    exemplos_nao_casados: List[str] = []

    for item in client.iter_amendments(ano):
        total += 1
        tipos_vistos[_coerce_text(item.get("tipoEmenda")) or "(vazio)"] += 1

        if not is_individual_amendment(item.get("tipoEmenda")):
            continue

        payload = build_payload(item)
        if payload is None:
            continue
        individuais += 1

        result = match_author(payload["author_name_raw"], candidates)
        payload["parliamentarian_id"] = result.parliamentarian_id
        payload["match_status"] = result.status
        status_counter[result.status] += 1

        if result.status == MATCH_STATUS_UNMATCHED and len(exemplos_nao_casados) < 20:
            nome = payload["author_name_raw"]
            if nome and nome not in exemplos_nao_casados:
                exemplos_nao_casados.append(nome)

        if dry_run_limit is not None and individuais >= dry_run_limit:
            break

    logger.info("=== Diagnostico de emendas %s ===", ano)
    logger.info("Total de emendas lidas: %s", total)
    logger.info("Emendas individuais: %s", individuais)
    logger.info("Valores de tipoEmenda vistos: %s", dict(tipos_vistos))
    logger.info("Casamento: %s", dict(status_counter))
    if individuais:
        taxa = 100 * status_counter.get("matched", 0) / individuais
        logger.info("Taxa de casamento: %.1f%%", taxa)
    if exemplos_nao_casados:
        logger.info("Exemplos nao casados: %s", exemplos_nao_casados)

    if persist:
        logger.warning(
            "Persistencia ainda nao implementada (Task 5 do plano 1); "
            "rodando como diagnostico."
        )


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        description="Coleta emendas parlamentares individuais do Portal da Transparencia."
    )
    parser.add_argument("--ano", type=int, help="Ano da coleta (default: ano corrente).")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Nao persiste; apenas reporta o diagnostico.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Interrompe apos N emendas individuais (para diagnostico rapido).",
    )

    args = parser.parse_args()
    emendas(ano=args.ano, persist=not args.dry_run, dry_run_limit=args.limit)
```

- [ ] **Step 5: Declare a variável de ambiente**

Em `mamute_scrappers/.env.example`, acrescente ao final:

```bash
# Chave da API do Portal da Transparencia (emendas parlamentares — CS-17).
# Cadastro gratuito: portaldatransparencia.gov.br/api-de-dados/cadastrar-email
# Apenas o container de scrappers usa; a API e o chatbot nao falam com o Portal.
PORTAL_TRANSPARENCIA_API_KEY=
```

- [ ] **Step 6: Rode os testes e confirme que passam**

Run: `pytest mamute_scrappers/tests/test_emendas_client.py -v`
Expected: PASS — 8 testes.

- [ ] **Step 7: Commit**

```bash
git add mamute_scrappers/portal_crawler/client.py \
        mamute_scrappers/portal_crawler/emendas.py \
        mamute_scrappers/tests/test_emendas_client.py \
        mamute_scrappers/.env.example
git commit -m "feat(emendas): cliente do Portal da Transparencia e modo diagnostico"
```

- [ ] **Step 8: PONTO DE DECISÃO — rode o diagnóstico**

Com a chave em mãos, e o `DATABASE_URL` apontando para uma base com
parlamentares:

```bash
PORTAL_TRANSPARENCIA_API_KEY=<chave> \
  python -m mamute_scrappers.portal_crawler.emendas --ano 2026 --dry-run --limit 500
```

Registre no PR os três números que saem do log:

1. Os valores literais de `tipoEmenda` — confirma se `is_individual_amendment` acerta o filtro.
2. A taxa de casamento.
3. A lista de exemplos não casados.

**Se a taxa for alta (≥ 85%)**, siga o plano como está. **Se for baixa**, pare e
reavalie com o dono do produto antes da Task 4: o painel de administração deixa
de ser conveniência e vira pré-requisito, e talvez seja preciso mapeamento
manual de nomes antes de qualquer interface.

---

### Task 4: Modelo e migration

**Files:**
- Create: `mamute_scrappers/db/models/parliamentary_amendment.py`
- Modify: `mamute_scrappers/db/models/__init__.py`
- Create: `api/db/models/parliamentary_amendment.py`
- Modify: `api/db/models/__init__.py`
- Create: `mamute_scrappers/migrations/versions/b2c3d4e5f6a7_add_parliamentary_amendment.py`
- Modify: `mamute_scrappers/db/models/parliamentarian.py` (relationship)

**Interfaces:**
- Consumes: constantes de `match_status` da Task 2
- Produces: `ParliamentaryAmendment` importável de `mamute_scrappers.db.models` e de `api.db.models`

A migration atual em `head` é `a9b0c1d2e3f4` (`add_trgm_indexes_speeches`).
Confirme antes de escrever: `cd mamute_scrappers && alembic heads`.

- [ ] **Step 1: Escreva o modelo do lado dos scrappers**

Crie `mamute_scrappers/db/models/parliamentary_amendment.py`:

```python
"""Modelo de emenda parlamentar orcamentaria.

Nao confundir com emenda a proposicao (alteracao de texto de projeto), que vive
em `proposition_type`. Aqui e destinacao de verba do orcamento federal.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, Numeric, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..base import Base


class ParliamentaryAmendment(Base):
    __tablename__ = "parliamentary_amendment"

    id = Column(BigInteger, primary_key=True, index=True)
    amendment_code = Column(Text, nullable=False, unique=True, index=True)
    year = Column(Integer, index=True)
    amendment_number = Column(Text)
    amendment_type = Column(Text)

    author_name_raw = Column(Text)
    author_raw = Column(Text)

    # SET NULL, e nao CASCADE como nas demais tabelas ligadas a parlamentar: a
    # emenda e fato orcamentario publico e nao deve sumir se o parlamentar sair
    # da base.
    parliamentarian_id = Column(
        BigInteger,
        ForeignKey("parliamentarian.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    match_status = Column(Text, nullable=False, index=True)

    spending_locality = Column(Text)
    function = Column(Text)
    subfunction = Column(Text)

    committed_value = Column(Numeric(18, 2))
    settled_value = Column(Numeric(18, 2))
    paid_value = Column(Numeric(18, 2))
    remainder_inscribed = Column(Numeric(18, 2))
    remainder_cancelled = Column(Numeric(18, 2))
    remainder_paid = Column(Numeric(18, 2))

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    parliamentarian = relationship("Parliamentarian", back_populates="amendments")


__all__ = ["ParliamentaryAmendment"]
```

- [ ] **Step 2: Registre o modelo e a relação**

Em `mamute_scrappers/db/models/__init__.py`, acrescente o import na ordem
alfabética (depois de `from .parliamentarian import Parliamentarian`):

```python
from .parliamentary_amendment import ParliamentaryAmendment
```

e `"ParliamentaryAmendment"` na lista `__all__`, também em ordem alfabética
(entre `"Parliamentarian"` e `"PlenaryAttendance"`).

Em `mamute_scrappers/db/models/parliamentarian.py`, acrescente ao final da
classe `Parliamentarian`, junto das demais relações:

```python
    amendments = relationship(
        "ParliamentaryAmendment",
        back_populates="parliamentarian",
    )
```

Sem `cascade="all, delete-orphan"`, de propósito — o `ondelete="SET NULL"` da
coluna é quem manda aqui.

- [ ] **Step 3: Espelhe o modelo no lado da API**

Copie `mamute_scrappers/db/models/parliamentary_amendment.py` para
`api/db/models/parliamentary_amendment.py` **sem alterações no conteúdo** (os
dois pacotes usam `..base` da mesma forma), e faça os mesmos dois registros em
`api/db/models/__init__.py`.

Confira se `api/db/models/parliamentarian.py` também declara relações; se sim,
acrescente a mesma relação `amendments` lá.

- [ ] **Step 4: Escreva a migration**

Crie
`mamute_scrappers/migrations/versions/b2c3d4e5f6a7_add_parliamentary_amendment.py`:

```python
"""tabela de emendas parlamentares orcamentarias (CS-17)

O Portal da Transparencia nao devolve identificador de parlamentar, so o nome
do autor em texto livre. Por isso `parliamentarian_id` e anulavel e
`match_status` registra explicitamente o resultado do casamento — inclusive o
que nao casou, que precisa ficar visivel para auditoria.

Revision ID: b2c3d4e5f6a7
Revises: a9b0c1d2e3f4
Create Date: 2026-08-06 12:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "b2c3d4e5f6a7"
down_revision = "a9b0c1d2e3f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "parliamentary_amendment",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("amendment_code", sa.Text(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("amendment_number", sa.Text(), nullable=True),
        sa.Column("amendment_type", sa.Text(), nullable=True),
        sa.Column("author_name_raw", sa.Text(), nullable=True),
        sa.Column("author_raw", sa.Text(), nullable=True),
        sa.Column(
            "parliamentarian_id",
            sa.BigInteger(),
            sa.ForeignKey("parliamentarian.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("match_status", sa.Text(), nullable=False),
        sa.Column("spending_locality", sa.Text(), nullable=True),
        sa.Column("function", sa.Text(), nullable=True),
        sa.Column("subfunction", sa.Text(), nullable=True),
        sa.Column("committed_value", sa.Numeric(18, 2), nullable=True),
        sa.Column("settled_value", sa.Numeric(18, 2), nullable=True),
        sa.Column("paid_value", sa.Numeric(18, 2), nullable=True),
        sa.Column("remainder_inscribed", sa.Numeric(18, 2), nullable=True),
        sa.Column("remainder_cancelled", sa.Numeric(18, 2), nullable=True),
        sa.Column("remainder_paid", sa.Numeric(18, 2), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_parliamentary_amendment_code",
        "parliamentary_amendment",
        ["amendment_code"],
        unique=True,
    )
    op.create_index(
        "ix_parliamentary_amendment_parliamentarian_year",
        "parliamentary_amendment",
        ["parliamentarian_id", "year"],
    )
    op.create_index(
        "ix_parliamentary_amendment_match_status",
        "parliamentary_amendment",
        ["match_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_parliamentary_amendment_match_status", "parliamentary_amendment")
    op.drop_index(
        "ix_parliamentary_amendment_parliamentarian_year", "parliamentary_amendment"
    )
    op.drop_index("ix_parliamentary_amendment_code", "parliamentary_amendment")
    op.drop_table("parliamentary_amendment")
```

- [ ] **Step 5: Verifique a migration contra um Postgres real**

```bash
cd mamute_scrappers
DATABASE_URL=postgresql+psycopg2://<user>:<senha>@localhost:5432/<base_de_teste> \
  alembic upgrade head
```

Expected: `Running upgrade a9b0c1d2e3f4 -> b2c3d4e5f6a7`.

Confirme o `downgrade` também, porque o CI só testa o `upgrade`:

```bash
DATABASE_URL=... alembic downgrade -1 && DATABASE_URL=... alembic upgrade head
```

- [ ] **Step 6: Commit**

```bash
git add mamute_scrappers/db/models/ api/db/models/ \
        mamute_scrappers/migrations/versions/b2c3d4e5f6a7_add_parliamentary_amendment.py
git commit -m "feat(emendas): tabela parliamentary_amendment com FK anulavel e match_status"
```

---

### Task 5: Persistência idempotente

**Files:**
- Modify: `mamute_scrappers/portal_crawler/emendas.py`
- Test: `mamute_scrappers/tests/test_emendas_upsert.py`

**Interfaces:**
- Consumes: `ParliamentaryAmendment` (Task 4), `build_payload` (Task 3)
- Produces: `emendas.upsert_amendment(session, payload: Dict[str, Any]) -> Tuple[Any, bool]` — devolve `(registro, criado)`

- [ ] **Step 1: Escreva o teste que falha**

Crie `mamute_scrappers/tests/test_emendas_upsert.py`. Segue o padrão dos testes
de scrapper existentes: SQLite em memória com um `Base` local que espelha só as
colunas usadas.

```python
from __future__ import annotations

import importlib.util
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Iterator

import pytest
from sqlalchemy import (
    BigInteger,
    Column,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    create_engine,
)
from sqlalchemy.orm import Session, declarative_base, sessionmaker

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, relative_path: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


emendas_mod = load_module(
    "test_emendas_upsert_module",
    "mamute_scrappers/portal_crawler/emendas.py",
)

Base = declarative_base()


class Parliamentarian(Base):
    __tablename__ = "parliamentarian"
    id = Column(BigInteger, primary_key=True)
    name = Column(Text)
    full_name = Column(Text)


class ParliamentaryAmendment(Base):
    __tablename__ = "parliamentary_amendment"
    id = Column(BigInteger, primary_key=True)
    amendment_code = Column(Text, nullable=False, unique=True)
    year = Column(Integer)
    amendment_number = Column(Text)
    amendment_type = Column(Text)
    author_name_raw = Column(Text)
    author_raw = Column(Text)
    parliamentarian_id = Column(BigInteger, ForeignKey("parliamentarian.id"))
    match_status = Column(Text, nullable=False)
    spending_locality = Column(Text)
    function = Column(Text)
    subfunction = Column(Text)
    committed_value = Column(Numeric(18, 2))
    settled_value = Column(Numeric(18, 2))
    paid_value = Column(Numeric(18, 2))
    remainder_inscribed = Column(Numeric(18, 2))
    remainder_cancelled = Column(Numeric(18, 2))
    remainder_paid = Column(Numeric(18, 2))


@pytest.fixture()
def session(monkeypatch) -> Iterator[Session]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine)
    monkeypatch.setattr(emendas_mod, "ParliamentaryAmendment", ParliamentaryAmendment)
    with maker() as s:
        s.add(Parliamentarian(id=1, name="José da Silva", full_name="José da Silva Júnior"))
        s.commit()
        yield s


def payload(**overrides):
    base = {
        "amendment_code": "202600010001",
        "year": 2026,
        "amendment_number": "0001",
        "amendment_type": "Individual",
        "author_name_raw": "José da Silva",
        "author_raw": "1234",
        "parliamentarian_id": 1,
        "match_status": "matched",
        "spending_locality": "TERESINA - PI",
        "function": "Saúde",
        "subfunction": "Atenção Básica",
        "committed_value": Decimal("2000000.00"),
        "settled_value": Decimal("0.00"),
        "paid_value": Decimal("0.00"),
        "remainder_inscribed": None,
        "remainder_cancelled": None,
        "remainder_paid": None,
    }
    base.update(overrides)
    return base


def test_primeira_gravacao_cria_registro(session):
    record, created = emendas_mod.upsert_amendment(session, payload())
    session.commit()

    assert created is True
    assert record.amendment_code == "202600010001"
    assert session.query(ParliamentaryAmendment).count() == 1


def test_segunda_gravacao_atualiza_sem_duplicar(session):
    emendas_mod.upsert_amendment(session, payload())
    session.commit()

    emendas_mod.upsert_amendment(
        session, payload(paid_value=Decimal("500000.00"))
    )
    session.commit()

    assert session.query(ParliamentaryAmendment).count() == 1
    record = session.query(ParliamentaryAmendment).one()
    assert record.paid_value == Decimal("500000.00")


def test_correcao_manual_nao_e_sobrescrita_pelo_robo(session):
    emendas_mod.upsert_amendment(session, payload(parliamentarian_id=None, match_status="unmatched"))
    session.commit()

    # Um humano corrigiu no painel de administracao.
    record = session.query(ParliamentaryAmendment).one()
    record.parliamentarian_id = 1
    record.match_status = "manual"
    session.commit()

    # O crawler roda de novo e continua sem conseguir casar.
    emendas_mod.upsert_amendment(
        session,
        payload(parliamentarian_id=None, match_status="unmatched", paid_value=Decimal("77.00")),
    )
    session.commit()

    record = session.query(ParliamentaryAmendment).one()
    assert record.parliamentarian_id == 1
    assert record.match_status == "manual"
    # Mas o valor financeiro continua sendo atualizado.
    assert record.paid_value == Decimal("77.00")


def test_casamento_novo_substitui_o_anterior_quando_nao_e_manual(session):
    emendas_mod.upsert_amendment(session, payload(parliamentarian_id=None, match_status="unmatched"))
    session.commit()

    emendas_mod.upsert_amendment(session, payload(parliamentarian_id=1, match_status="matched"))
    session.commit()

    record = session.query(ParliamentaryAmendment).one()
    assert record.parliamentarian_id == 1
    assert record.match_status == "matched"
```

- [ ] **Step 2: Rode o teste e confirme que falha**

Run: `pytest mamute_scrappers/tests/test_emendas_upsert.py -v`
Expected: FAIL — `AttributeError: module has no attribute 'upsert_amendment'`.

- [ ] **Step 3: Implemente o upsert**

Em `mamute_scrappers/portal_crawler/emendas.py`, acrescente perto do topo, junto
dos demais imports do pacote:

```python
from mamute_scrappers.portal_crawler.author_matching import (  # noqa: E402
    MATCH_STATUS_MANUAL,
)
```

E, no corpo do módulo, o carregamento tardio do modelo mais o upsert:

```python
ParliamentaryAmendment: Any = None

# Campos que o robo sempre atualiza, mesmo quando houve correcao manual.
_VALUE_FIELDS = (
    "year",
    "amendment_number",
    "amendment_type",
    "author_name_raw",
    "author_raw",
    "spending_locality",
    "function",
    "subfunction",
    "committed_value",
    "settled_value",
    "paid_value",
    "remainder_inscribed",
    "remainder_cancelled",
    "remainder_paid",
)


def _ensure_model() -> None:
    global ParliamentaryAmendment
    if ParliamentaryAmendment is not None:
        return
    from mamute_scrappers.db.models import (
        ParliamentaryAmendment as ParliamentaryAmendmentRuntime,
    )

    ParliamentaryAmendment = ParliamentaryAmendmentRuntime


def upsert_amendment(session, payload: Dict[str, Any]):
    """Grava ou atualiza uma emenda, casando pela chave natural do Portal.

    Os valores financeiros sempre sao atualizados, porque mudam ao longo do ano.
    Ja o vinculo com o parlamentar nao e sobrescrito quando `match_status` esta
    em `manual`: correcao humana prevalece sobre o robo.
    """
    if ParliamentaryAmendment is None:
        _ensure_model()

    record = (
        session.query(ParliamentaryAmendment)
        .filter(ParliamentaryAmendment.amendment_code == payload["amendment_code"])
        .one_or_none()
    )

    created = False
    if record is None:
        record = ParliamentaryAmendment(amendment_code=payload["amendment_code"])
        session.add(record)
        created = True

    for field in _VALUE_FIELDS:
        setattr(record, field, payload.get(field))

    if record.match_status != MATCH_STATUS_MANUAL:
        record.parliamentarian_id = payload.get("parliamentarian_id")
        record.match_status = payload.get("match_status")

    return record, created
```

Note que `_ensure_model()` só é chamado quando `ParliamentaryAmendment` ainda é
`None`; nos testes o `monkeypatch` já injeta o modelo de SQLite, então o import
real nunca acontece.

- [ ] **Step 4: Ligue o upsert ao laço de coleta**

Ainda em `emendas.py`, **substitua a função `emendas()` inteira** pela versão
abaixo. Ela é a da Task 3 acrescida da sessão de banco e da contagem de
persistência; o corpo do diagnóstico continua idêntico, porque ele segue sendo
útil em toda execução.

Acrescente `from contextlib import nullcontext` ao bloco de imports do topo do
arquivo.

```python
def emendas(
    *,
    ano: Optional[int] = None,
    persist: bool = True,
    dry_run_limit: Optional[int] = None,
) -> None:
    """Coleta emendas individuais de um ano, casa por nome e persiste."""
    ano = ano or date.today().year
    api_key = os.getenv(API_KEY_ENV, "")
    client = PortalTransparenciaClient(api_key)

    candidates = _load_candidates()
    logger.info("Base de parlamentares carregada: %s candidatos.", len(candidates))

    if persist:
        _ensure_model()
        from mamute_scrappers.db import session_scope

        session_context = session_scope()
    else:
        session_context = nullcontext(None)

    tipos_vistos: Counter = Counter()
    status_counter: Counter = Counter()
    total = 0
    individuais = 0
    inserted = 0
    updated = 0
    exemplos_nao_casados: List[str] = []

    with session_context as session:
        for item in client.iter_amendments(ano):
            total += 1
            tipos_vistos[_coerce_text(item.get("tipoEmenda")) or "(vazio)"] += 1

            if not is_individual_amendment(item.get("tipoEmenda")):
                continue

            payload = build_payload(item)
            if payload is None:
                continue
            individuais += 1

            result = match_author(payload["author_name_raw"], candidates)
            payload["parliamentarian_id"] = result.parliamentarian_id
            payload["match_status"] = result.status
            status_counter[result.status] += 1

            if result.status == MATCH_STATUS_UNMATCHED and len(exemplos_nao_casados) < 20:
                nome = payload["author_name_raw"]
                if nome and nome not in exemplos_nao_casados:
                    exemplos_nao_casados.append(nome)

            if session is not None:
                _, created = upsert_amendment(session, payload)
                if created:
                    inserted += 1
                else:
                    updated += 1
                # Commit parcial: `session_scope` so commita ao sair do bloco, e
                # um ano inteiro numa unica transacao significa perder 50 mil
                # linhas por causa de uma falha de rede na ultima pagina. Como o
                # upsert e idempotente, retomar do zero apenas reescreve o que ja
                # estava la.
                if (inserted + updated) % 500 == 0:
                    session.commit()

            if dry_run_limit is not None and individuais >= dry_run_limit:
                break

    logger.info("=== Emendas %s ===", ano)
    logger.info("Total de emendas lidas: %s", total)
    logger.info("Emendas individuais: %s", individuais)
    logger.info("Valores de tipoEmenda vistos: %s", dict(tipos_vistos))
    logger.info("Casamento: %s", dict(status_counter))
    if individuais:
        taxa = 100 * status_counter.get("matched", 0) / individuais
        logger.info("Taxa de casamento: %.1f%%", taxa)
    if exemplos_nao_casados:
        logger.info("Exemplos nao casados: %s", exemplos_nao_casados)
    if persist:
        logger.info("Persistencia: %s inseridas, %s atualizadas.", inserted, updated)
```

O `session_scope()` faz commit ao sair do bloco `with` — confira em
`mamute_scrappers/db/session.py` antes de rodar, e não acrescente `commit()`
manual dentro do laço se ele já commita ao final.

- [ ] **Step 5: Rode os testes e confirme que passam**

Run: `pytest mamute_scrappers/tests/ -v -k emendas`
Expected: PASS — os quatro arquivos de teste de emendas.

- [ ] **Step 6: Verifique a idempotência de verdade**

Rode o crawler duas vezes seguidas contra uma base de teste e confira que a
contagem não muda:

```bash
PORTAL_TRANSPARENCIA_API_KEY=<chave> DATABASE_URL=<base_de_teste> \
  python -m mamute_scrappers.portal_crawler.emendas --ano 2026 --limit 200
# repita o mesmo comando
psql <base_de_teste> -c "SELECT count(*), match_status FROM parliamentary_amendment GROUP BY match_status;"
```

Expected: na segunda execução, `inseridas: 0` e o total no banco inalterado.

- [ ] **Step 7: Commit**

```bash
git add mamute_scrappers/portal_crawler/emendas.py \
        mamute_scrappers/tests/test_emendas_upsert.py
git commit -m "feat(emendas): upsert idempotente preservando correcao manual de autoria"
```

---

### Task 6: Backfill 2022 → corrente e agendamento

**Files:**
- Create: `mamute_scrappers/scripts/backfill_emendas.py`
- Modify: `mamute_scrappers/docker/scrappers.cron`
- Test: `mamute_scrappers/tests/test_backfill_emendas.py`

**Interfaces:**
- Consumes: o módulo `mamute_scrappers.portal_crawler.emendas` como subprocesso
- Produces: `backfill_emendas.build_chunks(since_year: int, end_year: int) -> List[Dict[str, Any]]`

- [ ] **Step 1: Escreva o teste que falha**

Crie `mamute_scrappers/tests/test_backfill_emendas.py`:

```python
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, relative_path: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


backfill = load_module(
    "test_backfill_emendas_module",
    "mamute_scrappers/scripts/backfill_emendas.py",
)


def test_um_chunk_por_ano_do_intervalo():
    chunks = backfill.build_chunks(2022, 2026)
    assert [c["ano"] for c in chunks] == [2022, 2023, 2024, 2025, 2026]


def test_cada_chunk_tem_key_estavel():
    chunks = backfill.build_chunks(2022, 2023)
    assert [c["key"] for c in chunks] == ["emendas-2022", "emendas-2023"]


def test_intervalo_invertido_devolve_lista_vazia():
    assert backfill.build_chunks(2026, 2022) == []


def test_ano_unico_devolve_um_chunk():
    assert len(backfill.build_chunks(2026, 2026)) == 1
```

- [ ] **Step 2: Rode o teste e confirme que falha**

Run: `pytest mamute_scrappers/tests/test_backfill_emendas.py -v`
Expected: FAIL — o arquivo não existe.

- [ ] **Step 3: Implemente o orquestrador**

Crie `mamute_scrappers/scripts/backfill_emendas.py`, espelhando a estrutura de
`mamute_scrappers/scripts/backfill_propositions.py` (leia esse arquivo antes:
estado em JSON, `flock`, subprocesso por chunk, `--status`).

```python
"""Orquestrador de backfill de emendas parlamentares (2022 -> ano corrente).

Mesma mecanica do backfill de proposicoes: cada execucao processa poucos chunks
e registra o progresso em arquivo de estado, de modo que o cron horario esvazia
a fila sozinho e depois vira no-op.

Cada chunk e um ano inteiro, entao a fila tem cerca de cinco itens e termina em
uma tarde — bem mais curta que a de proposicoes.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import logging
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger("backfill_emendas")

SINCE_YEAR = 2022
BACKFILL_END_YEAR = date.today().year
CHUNKS_PER_RUN = 2
CHUNK_TIMEOUT_SECONDS = 7200

STATE_FILE = Path(os.getenv("BACKFILL_EMENDAS_STATE_FILE", "/app/state/backfill_emendas.json"))
LOCK_FILE = STATE_FILE.with_name("backfill_emendas.lock")


def _load_state() -> Dict[str, Any]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Estado ilegivel (%s); recomecando do zero.", exc)
    return {"done": [], "updated_at": None}


def _save_state(state: Dict[str, Any]) -> None:
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)


def build_chunks(since_year: int, end_year: int) -> List[Dict[str, Any]]:
    """Um chunk por ano do intervalo, inclusive nas duas pontas."""
    return [
        {"key": f"emendas-{year}", "ano": year}
        for year in range(since_year, end_year + 1)
    ]


def _run_chunk(chunk: Dict[str, Any]) -> bool:
    cmd = [
        sys.executable,
        "-m",
        "mamute_scrappers.portal_crawler.emendas",
        "--ano",
        str(chunk["ano"]),
    ]
    logger.info("Chunk %s: %s", chunk["key"], " ".join(cmd))
    try:
        result = subprocess.run(cmd, timeout=CHUNK_TIMEOUT_SECONDS, check=False)
    except subprocess.TimeoutExpired:
        logger.error("Chunk %s estourou o timeout.", chunk["key"])
        return False
    return result.returncode == 0


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Backfill de emendas parlamentares.")
    parser.add_argument("--chunks-per-run", type=int, default=CHUNKS_PER_RUN)
    parser.add_argument("--status", action="store_true", help="So mostra o progresso.")
    args = parser.parse_args()

    chunks = build_chunks(SINCE_YEAR, BACKFILL_END_YEAR)
    state = _load_state()
    done = set(state.get("done", []))
    pending = [c for c in chunks if c["key"] not in done]

    if args.status:
        logger.info("Progresso: %s/%s chunks concluidos.", len(done), len(chunks))
        return

    if not pending:
        logger.info("Backfill de emendas completo — nada a fazer.")
        return

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK_FILE, "w", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            logger.info("Outro backfill de emendas ainda roda; saindo.")
            return

        for chunk in pending[: args.chunks_per_run]:
            if _run_chunk(chunk):
                done.add(chunk["key"])
                state["done"] = sorted(done)
                _save_state(state)
            else:
                logger.warning("Chunk %s falhou; sera tentado de novo.", chunk["key"])

    restantes = len([c for c in chunks if c["key"] not in done])
    if restantes == 0:
        logger.info("Backfill de emendas completo.")
    else:
        logger.info("Restam %s chunks.", restantes)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Rode os testes e confirme que passam**

Run: `pytest mamute_scrappers/tests/test_backfill_emendas.py -v`
Expected: PASS — 4 testes.

- [ ] **Step 5: Agende no cron**

Em `mamute_scrappers/docker/scrappers.cron`, acrescente ao final. Os minutos 50
(diário, 06h) e 35 (horário) foram escolhidos por estarem livres entre os
dezoito jobs já existentes — confira antes de gravar:

```cron
# Emendas parlamentares — ano corrente (diario as 06h50 UTC). CS-17.
# Os valores empenhado/liquidado/pago mudam ao longo do ano inteiro, entao este
# job continua necessario depois que o backfill encerra.
50 6 * * * cd /app && /app/mamute_scrappers/docker/run-cron-job.sh emendas -- /usr/local/bin/python -m mamute_scrappers.portal_crawler.emendas --ano $(date +\%Y) >> /proc/1/fd/1 2>> /proc/1/fd/2

# Backfill de emendas 2022 -> ano corrente (a cada 1h no minuto 35).
# Sao ~5 chunks (um por ano); a fila esvazia em uma tarde e depois vira no-op.
35 * * * * cd /app && /app/mamute_scrappers/docker/run-cron-job.sh backfill-emendas -- /usr/local/bin/python -m mamute_scrappers.scripts.backfill_emendas --chunks-per-run 2 >> /proc/1/fd/1 2>> /proc/1/fd/2
```

- [ ] **Step 6: Valide a sintaxe do cron**

```bash
crontab -T mamute_scrappers/docker/scrappers.cron 2>/dev/null \
  || awk 'NF && $1 !~ /^#/ && $1 !~ /^[A-Z]+=/ {print NF, $0}' mamute_scrappers/docker/scrappers.cron | head
```

Expected: nenhum erro; cada linha de job com pelo menos 6 campos antes do comando.

- [ ] **Step 7: Commit**

```bash
git add mamute_scrappers/scripts/backfill_emendas.py \
        mamute_scrappers/tests/test_backfill_emendas.py \
        mamute_scrappers/docker/scrappers.cron
git commit -m "feat(emendas): backfill 2022->corrente e agendamento no cron"
```

---

### Task 7: Rodar os testes de scrapper no CI

**Files:**
- Modify: `.github/workflows/deploy-prd.yml`
- Create: `mamute_scrappers/requirements-dev.txt`

**Interfaces:**
- Consumes: os testes das Tasks 1, 2, 3, 5 e 6
- Produces: job `scrappers-tests` no workflow

**Por que esta task existe:** hoje o CI roda `pytest api/tests/`, os testes da
UI, o `alembic upgrade head` e o contrato UI↔API — mas **nunca**
`mamute_scrappers/tests/`. Os quatorze arquivos de teste que já existem lá
rodam só na máquina de quem lembra de rodar. A lógica mais delicada desta
feature (o casamento de autor, que decide a quem se atribui dinheiro público)
nasceria sem rede de proteção no CI.

- [ ] **Step 1: Declare a dependência de teste**

Crie `mamute_scrappers/requirements-dev.txt`:

```
-r requirements.txt
pytest>=8.0,<9.0
```

- [ ] **Step 2: Confirme que a suíte inteira passa localmente**

Run: `pytest mamute_scrappers/tests/ -v`
Expected: PASS. Se algum teste **pré-existente** falhar, não o conserte dentro
desta task: anote no PR e trate em commit separado, para não misturar o
conserto com a introdução do job.

- [ ] **Step 3: Acrescente o job ao workflow**

Em `.github/workflows/deploy-prd.yml`, depois do job `api-smoke` (linha 72 em
diante), acrescente:

```yaml
  scrappers-tests:
    name: Scrappers — pytest
    runs-on: ubuntu-latest
    timeout-minutes: 8
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: pip
          cache-dependency-path: mamute_scrappers/requirements-dev.txt

      - name: Install deps
        working-directory: mamute_scrappers
        run: pip install -r requirements-dev.txt

      - name: Pytest
        run: pytest mamute_scrappers/tests/ -v
```

- [ ] **Step 4: Verifique se o job de deploy depende deste**

Localize o job `deploy:` no mesmo arquivo e inspecione a lista `needs:`. Se ela
já enumera `api-smoke`, acrescente `scrappers-tests` na mesma lista. Se o
`deploy` não tiver `needs`, **não** invente um: registre a observação no corpo
do PR e siga.

- [ ] **Step 5: Valide a sintaxe do YAML**

```bash
python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/deploy-prd.yml')); print('yaml ok')"
```

Expected: `yaml ok`.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/deploy-prd.yml mamute_scrappers/requirements-dev.txt
git commit -m "ci: roda a suite de testes dos scrappers, que hoje nao roda no CI"
```

---

## Encerramento do Plano 1

Ao fim das sete tasks:

- A tabela `parliamentary_amendment` existe e recebe dados de 2022 ao ano corrente.
- O cron mantém o ano corrente atualizado sozinho, e o backfill se encerra sem intervenção.
- Nenhuma emenda individual é descartada: o que não casa fica com `parliamentarian_id` nulo e `match_status` explícito.
- Os testes de scrapper passam a rodar no CI.

Nada disso ainda aparece para o usuário — a exposição é o Plano 2
(`2026-08-06-emendas-plano2-exposicao.md`).

**Antes de abrir o PR**, inclua no corpo os três números do Step 8 da Task 3
(valores literais de `tipoEmenda`, taxa de casamento e exemplos não casados). É
o que permite decidir o peso do painel de administração no Plano 2.
