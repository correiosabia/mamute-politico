"""Regras de normalização e persistência dos termos da nuvem de palavras."""

from __future__ import annotations

from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

try:
    from ..db.models.word_cloud_term import KIND_EXCLUDED, KIND_STOPWORD, WordCloudTerm
except ImportError:  # execução dentro de api/
    from db.models.word_cloud_term import KIND_EXCLUDED, KIND_STOPWORD, WordCloudTerm


def normalize_term(value: str) -> str:
    """Caixa baixa e espaços colapsados, acentuação preservada.

    A acentuação faz parte do termo em português — normalizar "sessão" para
    "sessao" faria a lista deixar de casar com o que vem do banco.
    """

    return " ".join(str(value or "").split()).lower()


def normalize_terms(values: Iterable[str]) -> list[str]:
    """Normaliza, descarta vazios e deduplica preservando ordem alfabética."""

    limpos = {normalize_term(v) for v in values or []}
    limpos.discard("")
    return sorted(limpos)


def get_terms(db: Session) -> dict[str, list[str]]:
    """Listas atuais, prontas para a resposta da API."""

    linhas = db.execute(select(WordCloudTerm.term, WordCloudTerm.kind)).all()
    return {
        "stopwords": sorted(t for t, k in linhas if k == KIND_STOPWORD),
        "excluded_terms": sorted(t for t, k in linhas if k == KIND_EXCLUDED),
    }


def replace_terms(
    db: Session,
    stopwords: Iterable[str],
    excluded_terms: Iterable[str],
) -> dict[str, list[str]]:
    """Substitui as duas listas por completo.

    A tela edita listas inteiras e salva de uma vez, então substituir é o que
    espelha a intenção do usuário. Não faz commit: quem chama decide o momento,
    para que a linha de auditoria entre na mesma transação.
    """

    novos = {
        KIND_STOPWORD: normalize_terms(stopwords),
        KIND_EXCLUDED: normalize_terms(excluded_terms),
    }

    for linha in db.execute(select(WordCloudTerm)).scalars().all():
        db.delete(linha)
    db.flush()

    for kind, termos in novos.items():
        for termo in termos:
            db.add(WordCloudTerm(term=termo, kind=kind))
    db.flush()

    return {
        "stopwords": novos[KIND_STOPWORD],
        "excluded_terms": novos[KIND_EXCLUDED],
    }
