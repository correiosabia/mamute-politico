"""Serviço auxiliar para coletar contexto via SQL."""

from __future__ import annotations

import logging
import re
from time import monotonic, perf_counter
from typing import Dict, Iterable, List, Mapping, Sequence

from sqlalchemy import text

from ..core.config import get_settings
from ..core.database import get_session

settings = get_settings()
logger = logging.getLogger(__name__)

_word_pattern = re.compile(r"[A-Za-zÀ-ÿ]{2,}")

# Stoplist gerida no Admin (word_cloud_terms) — a MESMA usada pela nuvem de
# palavras do front. Cache com TTL: muda raramente e é lida a cada pergunta.
_DYNAMIC_STOPWORDS_TTL_S = 30 * 60
_dynamic_stopwords_cache: tuple[float, frozenset[str]] | None = None


def _tokenize(value: str) -> set[str]:
    return {token.lower() for token in _word_pattern.findall(value or "")}


def _load_dynamic_stopwords() -> frozenset[str]:
    """Termos de word_cloud_terms tokenizados, com cache e fail-soft.

    Se a palavra não serve para a nuvem ("exa", "senhor", "bloco"...), ela
    também não serve como palavra-chave de busca no texto dos discursos.
    """

    global _dynamic_stopwords_cache
    now = monotonic()
    if (
        _dynamic_stopwords_cache is not None
        and now - _dynamic_stopwords_cache[0] < _DYNAMIC_STOPWORDS_TTL_S
    ):
        return _dynamic_stopwords_cache[1]

    try:
        rows = _execute_query("SELECT term FROM word_cloud_terms", {})
    except Exception as exc:  # noqa: BLE001 — stoplist nunca derruba a consulta
        logger.warning("⚠️ Falha ao carregar word_cloud_terms (stoplist): %s", exc)
        return _dynamic_stopwords_cache[1] if _dynamic_stopwords_cache else frozenset()

    words: set[str] = set()
    for row in rows:
        words |= _tokenize(str(dict(row).get("term") or ""))

    _dynamic_stopwords_cache = (now, frozenset(words))
    return _dynamic_stopwords_cache[1]


def _filtered_parliamentarian_name_tokens(
    filters: Dict[str, List[object]] | None,
) -> set[str]:
    """Tokens dos nomes dos parlamentares já restringidos por filtro.

    Quando o filtro por id existe, o nome na pergunta ("Jaques Wagner") não é
    tema — e como padrão ILIKE ele casa com qualquer discurso que cite a
    pessoa, poluindo o contexto e encarecendo a busca.
    """

    ids = (filters or {}).get("parliamentarian_ids")
    if not ids:
        return set()
    try:
        rows = _execute_query(
            "SELECT name FROM parliamentarian WHERE id = ANY(:ids)",
            {"ids": [int(i) for i in ids]},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("⚠️ Falha ao buscar nomes p/ stoplist: %s", exc)
        return set()

    tokens: set[str] = set()
    for row in rows:
        tokens |= _tokenize(str(dict(row).get("name") or ""))
    return tokens

_BASE_FROM = """
    FROM speeches_transcripts st
    JOIN parliamentarian p ON p.id = st.parliamentarian_id
"""

_CONTEXT_SELECT = """
    SELECT
        p.name AS parliamentarian_name,
        st.date AS speech_date,
        COALESCE(st.summary, st.speech_text) AS content
""" + _BASE_FROM

_FREQUENCY_SELECT = """
    SELECT
        p.name AS parliamentarian_name,
        COUNT(*)::int AS total
""" + _BASE_FROM

_KEYWORDS_SELECT = """
    SELECT
        LOWER(k.keyword) AS keyword,
        SUM(k.frequency)::int AS total_frequency,
        COUNT(DISTINCT st.id)::int AS speeches_count
    FROM speeches_transcripts st
    JOIN speeches_transcripts_keywords k ON k.speeches_transcripts_id = st.id
    JOIN parliamentarian p ON p.id = st.parliamentarian_id
"""

_ENTITIES_SELECT = """
    SELECT
        e.label AS entity_label,
        e.text AS entity_text,
        COUNT(DISTINCT st.id)::int AS speeches_count
    FROM speeches_transcripts st
    JOIN speeches_transcripts_entities e ON e.speeches_transcripts_id = st.id
    JOIN parliamentarian p ON p.id = st.parliamentarian_id
"""

_PROPOSITIONS_SELECT = """
    SELECT
        pr.id AS proposition_id,
        pr.proposition_acronym,
        pr.proposition_number,
        pr.presentation_year,
        pr.title,
        pr.summary,
        COUNT(DISTINCT st.id)::int AS speeches_count
    FROM speeches_transcripts st
    JOIN speeches_transcripts_proposition stp ON stp.speeches_transcripts_id = st.id
    JOIN proposition pr ON pr.id = stp.proposition_id
    JOIN parliamentarian p ON p.id = st.parliamentarian_id
"""

def _extract_keywords(question: str, extra_stopwords: Iterable[str] = ()) -> List[str]:
    """Gera palavras-chave básicas a partir da pergunta."""

    stopwords = set(settings.sql_keyword_stopwords) | set(extra_stopwords)
    tokens = _tokenize(question)
    filtered = [
        token
        for token in tokens
        if len(token) >= settings.sql_min_keyword_length and token not in stopwords
    ]
    return sorted(filtered)[:5]


def _build_keyword_clauses(keywords: List[str]) -> tuple[List[str], Dict[str, str]]:
    """Transforma palavras-chave em filtros SQL."""

    clauses: List[str] = []
    params: Dict[str, str] = {}
    for index, keyword in enumerate(keywords):
        param_key = f"pattern_{index}"
        clauses.append(
            f"(st.speech_text ILIKE :{param_key} OR st.summary ILIKE :{param_key})"
        )
        params[param_key] = f"%{keyword}%"
    return clauses, params


def _build_filter_clause(
    filters: Dict[str, List[object]] | None,
) -> tuple[str, Dict[str, object]]:
    if not filters:
        return "", {}

    clauses: List[str] = []
    params: Dict[str, object] = {}

    parliamentarian_ids = filters.get("parliamentarian_ids")
    if parliamentarian_ids:
        clauses.append("p.id = ANY(:filter_parliamentarian_ids)")
        params["filter_parliamentarian_ids"] = parliamentarian_ids

    parties = filters.get("parties")
    if parties:
        clauses.append("UPPER(p.party) = ANY(:filter_parties)")
        params["filter_parties"] = parties

    states = filters.get("states")
    if states:
        clauses.append("UPPER(p.state_elected) = ANY(:filter_states)")
        params["filter_states"] = states

    roles = filters.get("roles")
    if roles:
        clauses.append("UPPER(p.type) = ANY(:filter_roles)")
        params["filter_roles"] = roles

    if not clauses:
        return "", {}

    return " AND ".join(clauses), params


def _format_rows(rows: Sequence[Mapping[str, object]]) -> str:
    """Transforma os resultados em texto legível."""

    if not rows:
        return ""

    formatted_chunks: List[str] = []
    for row in rows:
        data = dict(row)
        name = data.get("parliamentarian_name") or "Parlamentar não informado"
        date_value = data.get("speech_date")
        if hasattr(date_value, "isoformat"):
            date_str = date_value.isoformat()
        else:
            date_str = str(date_value) if date_value else "Data não informada"

        summary_text = (data.get("content") or "").strip()
        preview = summary_text[:600]
        if summary_text and len(summary_text) > 600:
            preview += "..."
        formatted_chunks.append(f"- {date_str} • {name}: {preview}")

    header = "Notas relevantes:\n"
    return header + "\n".join(formatted_chunks)


def _format_frequency_rows(rows: Sequence[Mapping[str, object]]) -> str:
    """Agrupa resultados analíticos."""

    if not rows:
        return ""

    lines = ["Frequência por parlamentar:"]
    for row in rows:
        data = dict(row)
        name = data.get("parliamentarian_name") or "Parlamentar não informado"
        total = int(data.get("total") or 0)
        lines.append(f"- {name}: {total} discurso(s) relacionados")
    return "\n".join(lines)


def _format_keyword_rows(rows: Sequence[Mapping[str, object]]) -> str:
    if not rows:
        return ""

    lines = ["Palavras-chave em destaque:"]
    for row in rows:
        data = dict(row)
        keyword = (data.get("keyword") or "").strip()
        total = int(data.get("total_frequency") or 0)
        speeches = int(data.get("speeches_count") or 0)
        if keyword:
            lines.append(f"- {keyword} • {total} ocorrência(s) em {speeches} discurso(s)")
    return "\n".join(lines)


def _format_entity_rows(rows: Sequence[Mapping[str, object]]) -> str:
    if not rows:
        return ""

    lines = ["Entidades citadas:"]
    for row in rows:
        data = dict(row)
        label = (data.get("entity_label") or "").upper()
        text_value = data.get("entity_text") or ""
        speeches = int(data.get("speeches_count") or 0)
        if text_value:
            lines.append(f"- {text_value} ({label}) • {speeches} discurso(s)")
    return "\n".join(lines)


def _format_proposition_rows(rows: Sequence[Mapping[str, object]]) -> str:
    if not rows:
        return ""

    lines = ["Proposições relacionadas:"]
    for row in rows:
        data = dict(row)
        acronym = data.get("proposition_acronym")
        number = data.get("proposition_number")
        year = data.get("presentation_year")
        title = (data.get("title") or "").strip()
        summary = (data.get("summary") or "").strip()
        speeches = int(data.get("speeches_count") or 0)

        descriptor_parts: List[str] = []
        if acronym and number:
            descriptor_parts.append(f"{acronym} {number}")
        elif acronym:
            descriptor_parts.append(str(acronym))
        elif number:
            descriptor_parts.append(f"#{number}")
        if year:
            descriptor_parts.append(str(year))
        descriptor = " ".join(descriptor_parts) or "Proposição sem identificação"

        if title:
            descriptor += f" — {title}"

        if summary:
            truncated = summary[:300]
            if len(summary) > 300:
                truncated += "..."
            descriptor += f"\n  Resumo: {truncated}"

        descriptor += f"\n  Citada em {speeches} discurso(s)."
        lines.append(descriptor)

    return "\n".join(lines)


def _execute_query(query: str, params: Dict[str, object]) -> List[Mapping[str, object]]:
    with get_session() as session:
        timeout_ms = settings.sql_statement_timeout_ms
        if timeout_ms > 0:
            try:
                # SET LOCAL vale só para a transação corrente; protege o chat de
                # travar minutos numa consulta cara (degrada para seção vazia).
                session.execute(
                    text(f"SET LOCAL statement_timeout = {int(timeout_ms)}")
                )
            except Exception:  # noqa: BLE001 — ex.: SQLite nos testes
                pass
        return session.execute(text(query), params).mappings().all()


def _execute_query_soft(
    query: str, params: Dict[str, object], *, section: str, request_id: str
) -> List[Mapping[str, object]]:
    """Executa a consulta degradando para lista vazia em erro/timeout."""

    try:
        return _execute_query(query, params)
    except Exception as exc:  # noqa: BLE001 — contexto parcial > erro no chat
        logger.warning(
            "⚠️ SQL context section skipped | request_id=%s | section=%s | error=%s",
            request_id,
            section,
            exc,
        )
        return []


def fetch_sql_context(
    question: str,
    filters: Dict[str, List[object]] | None = None,
    request_id: str = "n/a",
    topic: str | None = None,
    derived_topics: List[str] | None = None,
) -> str:
    """Executa consultas simples para enriquecer o contexto do LLM.

    Ordem de precedência das âncoras de busca:
    1. `topic` — clique na nuvem de palavras: tema explícito, condição
       obrigatória (frase inteira).
    2. `derived_topics` — temas interpretados da pergunta pelo LLM
       (query_understanding): frases inteiras, OR entre si.
    3. Fallback heurístico — regex + stoplists, só quando a interpretação
       falhou (a heurística olha palavras, não contexto: foi ela que promoveu
       "geral" a termo de busca).
    """

    started_at = perf_counter()
    topic = (topic or "").strip()
    if topic:
        keywords = [topic]
        keyword_clauses = [
            "(st.speech_text ILIKE :topic_pattern OR st.summary ILIKE :topic_pattern)"
        ]
        pattern_params: Dict[str, str] = {"topic_pattern": f"%{topic}%"}
    elif derived_topics:
        keywords = [t.strip() for t in derived_topics if t and t.strip()][:5]
        keyword_clauses, pattern_params = _build_keyword_clauses(keywords)
    else:
        extra_stopwords = _load_dynamic_stopwords() | (
            _filtered_parliamentarian_name_tokens(filters)
        )
        keywords = _extract_keywords(question, extra_stopwords)
        keyword_clauses, pattern_params = _build_keyword_clauses(keywords)
    filter_clause, filter_params = _build_filter_clause(filters)
    logger.info(
        "🧮 SQL context started | request_id=%s | keywords=%s | has_topic=%s | has_filters=%s",
        request_id,
        keywords,
        bool(topic),
        bool(filter_clause),
    )

    if keyword_clauses:
        where_clause = " WHERE " + " OR ".join(keyword_clauses)
    else:
        where_clause = " WHERE st.summary IS NOT NULL"

    if filter_clause:
        where_clause += f" AND {filter_clause}"

    base_params: Dict[str, object] = {
        **pattern_params,
        **filter_params,
    }
    context_query = (
        _CONTEXT_SELECT
        + where_clause
        + "\nORDER BY st.date DESC NULLS LAST, st.id DESC\nLIMIT :limit"
    )
    context_params = {"limit": settings.sql_context_limit, **base_params}
    context_rows = _execute_query_soft(
        context_query, context_params, section="context", request_id=request_id
    )
    logger.info(
        "🧮 SQL context main query done | request_id=%s | rows=%s",
        request_id,
        len(context_rows),
    )

    if not context_rows and keyword_clauses:
        fallback_query = (
            _CONTEXT_SELECT
            + ("\nWHERE " + filter_clause if filter_clause else "")
            + "\nORDER BY st.date DESC NULLS LAST, st.id DESC\nLIMIT :limit"
        )
        context_rows = _execute_query_soft(
            fallback_query,
            {"limit": settings.sql_context_limit, **filter_params},
            section="context_fallback",
            request_id=request_id,
        )
        logger.info(
            "🧮 SQL context fallback query done | request_id=%s | rows=%s",
            request_id,
            len(context_rows),
        )

    frequency_rows: List[Mapping[str, object]] = []
    if keyword_clauses:
        frequency_query = (
            _FREQUENCY_SELECT
            + " WHERE "
            + " OR ".join(keyword_clauses)
            + (f" AND {filter_clause}" if filter_clause else "")
            + "\nGROUP BY p.name\nORDER BY total DESC\nLIMIT :freq_limit"
        )
        frequency_params: Dict[str, object] = {
            **base_params,
            "freq_limit": settings.sql_frequency_limit,
        }
        frequency_rows = _execute_query_soft(
            frequency_query, frequency_params, section="frequency", request_id=request_id
        )

    keyword_rows: List[Mapping[str, object]] = []
    if settings.sql_keywords_limit > 0:
        keywords_query = (
            _KEYWORDS_SELECT
            + where_clause
            + "\nGROUP BY LOWER(k.keyword)\n"
            "ORDER BY total_frequency DESC, speeches_count DESC\n"
            "LIMIT :keywords_limit"
        )
        keyword_params: Dict[str, object] = {
            **base_params,
            "keywords_limit": settings.sql_keywords_limit,
        }
        keyword_rows = _execute_query_soft(
            keywords_query, keyword_params, section="keywords", request_id=request_id
        )

    entities_rows: List[Mapping[str, object]] = []
    if settings.sql_entities_limit > 0:
        entities_query = (
            _ENTITIES_SELECT
            + where_clause
            + "\nGROUP BY e.label, e.text\n"
            "ORDER BY speeches_count DESC, e.label ASC\n"
            "LIMIT :entities_limit"
        )
        entities_params: Dict[str, object] = {
            **base_params,
            "entities_limit": settings.sql_entities_limit,
        }
        entities_rows = _execute_query_soft(
            entities_query, entities_params, section="entities", request_id=request_id
        )

    propositions_rows: List[Mapping[str, object]] = []
    if settings.sql_propositions_limit > 0:
        propositions_query = (
            _PROPOSITIONS_SELECT
            + where_clause
            + "\nGROUP BY pr.id, pr.proposition_acronym, pr.proposition_number, pr.presentation_year, pr.title, pr.summary\n"
            "ORDER BY speeches_count DESC, pr.presentation_year DESC NULLS LAST\n"
            "LIMIT :propositions_limit"
        )
        propositions_params: Dict[str, object] = {
            **base_params,
            "propositions_limit": settings.sql_propositions_limit,
        }
        propositions_rows = _execute_query_soft(
            propositions_query,
            propositions_params,
            section="propositions",
            request_id=request_id,
        )
    sections = []
    context_text = _format_rows(context_rows)
    if context_text:
        sections.append(context_text)

    frequency_text = _format_frequency_rows(frequency_rows)
    if frequency_text:
        sections.append(frequency_text)

    keywords_text = _format_keyword_rows(keyword_rows)
    if keywords_text:
        sections.append(keywords_text)

    entities_text = _format_entity_rows(entities_rows)
    if entities_text:
        sections.append(entities_text)

    propositions_text = _format_proposition_rows(propositions_rows)
    if propositions_text:
        sections.append(propositions_text)
    output = "\n\n".join(sections).strip()
    logger.info(
        "✅ SQL context finished | request_id=%s | context_chars=%s | frequency_rows=%s | keyword_rows=%s | entity_rows=%s | proposition_rows=%s | elapsed_ms=%.2f",
        request_id,
        len(output),
        len(frequency_rows),
        len(keyword_rows),
        len(entities_rows),
        len(propositions_rows),
        (perf_counter() - started_at) * 1000,
    )
    return output


__all__ = ["fetch_sql_context"]
