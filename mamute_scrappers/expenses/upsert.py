"""Upsert de gastos da cota parlamentar, casando por (house, source_key).

Mesmo receituario do upsert de emendas: lista explicita de campos que o robo
sobrescreve e flush() apos criar — a sessao do projeto usa autoflush=False com
commit por lote, e sem o flush uma chave repetida dentro do lote viraria
UniqueViolation e derrubaria o ano inteiro.

Diferenca deliberada: aqui nao ha `match_status` nem correcao manual. As duas
fontes publicam o id do parlamentar (ideCadastro na Camara, codSenador no
Senado), entao o vinculo e um join direto por parliamentarian_code e o robo
pode sobrescrever tudo.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, Tuple

ParliamentaryExpense: Any = None

COMMIT_EVERY = 500

# Tudo que o robo sobrescreve em toda execucao. Valores e ate glosa mudam
# retroativamente o ano inteiro na Camara.
EXPENSE_FIELDS = (
    "parliamentarian_id",
    "year",
    "month",
    "expense_type",
    "supplier_name",
    "supplier_id",
    "document_number",
    "document_date",
    "details",
    "document_value",
    "glosa_value",
    "net_value",
    "document_url",
)


def _ensure_model() -> None:
    global ParliamentaryExpense
    if ParliamentaryExpense is not None:
        return
    from mamute_scrappers.db.models import (
        ParliamentaryExpense as ParliamentaryExpenseRuntime,
    )

    ParliamentaryExpense = ParliamentaryExpenseRuntime


def sequenced_key(base: str, seen: Any) -> str:
    """Desambigua chave repetida DENTRO do mesmo arquivo/ano da fonte.

    Medido no Ano-2025.csv da Camara: ~12 mil linhas reutilizam o mesmo
    ideDocumento — o bilhete SIGEPA aparece uma vez na compra e outra na
    compensacao (valor negativo). Sem o sufixo, a segunda linha sobrescreveria
    a primeira e o total do mes perderia o par que se cancela.

    `seen` e um collections.Counter por execucao: a primeira ocorrencia vira
    "base#0", a segunda "base#1", e assim por diante, na ordem do arquivo. Se
    a fonte reordenar as ocorrencias entre execucoes, os conteudos trocam de
    linha entre si — o conjunto persistido continua identico.
    """
    seq = seen[base]
    seen[base] += 1
    return f"{base}#{seq}"


def fallback_source_key(*parts: Any) -> str:
    """Chave deterministica para linha sem id na fonte (sha1 hex, 40 chars).

    Usada quando a Camara nao publica ideDocumento (telefonia, correios). Duas
    linhas identicas em todos os campos colapsariam numa so — aceitavel: seriam
    indistinguiveis tambem para quem le a fonte.
    """
    raw = ";".join("" if p is None else str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def upsert_expense(session: Any, payload: Dict[str, Any]) -> Tuple[Any, bool]:
    """Grava ou atualiza um gasto pela chave natural (house, source_key)."""
    if ParliamentaryExpense is None:
        _ensure_model()

    record = (
        session.query(ParliamentaryExpense)
        .filter(
            ParliamentaryExpense.house == payload["house"],
            ParliamentaryExpense.source_key == payload["source_key"],
        )
        .one_or_none()
    )

    created = False
    if record is None:
        record = ParliamentaryExpense(
            house=payload["house"], source_key=payload["source_key"]
        )
        session.add(record)
        created = True

    for field in EXPENSE_FIELDS:
        setattr(record, field, payload.get(field))

    if created:
        session.flush()

    return record, created


__all__ = [
    "COMMIT_EVERY",
    "EXPENSE_FIELDS",
    "fallback_source_key",
    "sequenced_key",
    "upsert_expense",
]
