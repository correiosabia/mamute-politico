"""Utilidades de NLP para análise de discursos do Senado."""

from __future__ import annotations

import json
import logging
import os
from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, TypedDict

try:
    import spacy
    from spacy.language import Language
    from spacy.lang.pt.stop_words import STOP_WORDS as SPACY_STOP_WORDS
except ImportError:  # pragma: no cover - depende de pacotes opcionais
    spacy = None  # type: ignore[assignment]
    Language = None  # type: ignore[assignment]
    SPACY_STOP_WORDS: set[str] = set()

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - depende de pacotes opcionais
    OpenAI = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

DEFAULT_MODEL_CANDIDATES: Tuple[str, ...] = ("pt_core_news_sm", "pt_core_news_md")
DEFAULT_CHATGPT_MODEL = "gpt-4o-mini"
DEFAULT_CHATGPT_ENTITY_LIMIT = 20


class KeywordResult(TypedDict):
    keyword: str
    term: str
    frequency: int
    rank: int


class EntityResult(TypedDict):
    text: str
    label: str
    start_char: Optional[int]
    end_char: Optional[int]


class PortugueseSpeechAnalyzer:
    """Extrai palavras-chave e entidades de discursos em português."""

    def __init__(
        self,
        model: Optional[str] = None,
        *,
        extra_stopwords: Optional[Iterable[str]] = None,
    ) -> None:
        if spacy is None:
            raise RuntimeError(
                "spaCy não está instalado. Instale com 'pip install spacy' e o modelo "
                "'pt_core_news_md' (ou 'pt_core_news_sm')."
            )

        target_models: Sequence[str]
        if model:
            target_models = (model,)
        else:
            target_models = DEFAULT_MODEL_CANDIDATES

        self._nlp: Optional[Language] = None
        last_error: Optional[Exception] = None
        for candidate in target_models:
            try:
                self._nlp = spacy.load(candidate)  # type: ignore[assignment]
            except OSError as exc:  # pragma: no cover - depende do ambiente
                last_error = exc
                logger.debug("Modelo spaCy '%s' indisponível: %s", candidate, exc)
                continue
            else:
                logger.info("Modelo spaCy carregado: %s", candidate)
                break

        if self._nlp is None:
            raise RuntimeError(
                "Nenhum modelo spaCy em português encontrado. Execute "
                "'python -m spacy download pt_core_news_md' (ou pt_core_news_sm)."
            ) from last_error

        base_stopwords = {word.lower() for word in SPACY_STOP_WORDS}
        if extra_stopwords:
            base_stopwords.update(word.lower() for word in extra_stopwords)
        self._stopwords = base_stopwords

    @property
    def nlp(self) -> Language:
        if self._nlp is None:  # pragma: no cover - protegido no __init__
            raise RuntimeError("Pipeline spaCy não foi carregada corretamente.")
        return self._nlp

    def extract_keywords(self, text: str, *, limit: int = 15) -> List[KeywordResult]:
        if not text:
            return []

        doc = self.nlp(text)
        tokens: List[Tuple[str, str]] = []
        for token in doc:
            if not self._is_valid_token(token):
                continue
            lemma = token.lemma_.strip().lower() or token.text.strip().lower()
            term = token.text.strip()
            if not lemma or not term:
                continue
            if lemma in self._stopwords:
                continue
            tokens.append((lemma, term))

        if not tokens:
            return []

        counts = Counter(lemma for lemma, _ in tokens)
        term_variations: Dict[str, Counter[str]] = defaultdict(Counter)
        for lemma, term in tokens:
            term_variations[lemma][term] += 1

        keywords: List[KeywordResult] = []
        for rank, (lemma, frequency) in enumerate(counts.most_common(limit), start=1):
            preferred_term = term_variations[lemma].most_common(1)[0][0]
            keywords.append(
                {
                    "keyword": lemma,
                    "term": preferred_term,
                    "frequency": int(frequency),
                    "rank": rank,
                }
            )
        return keywords

    def extract_entities(self, text: str) -> List[EntityResult]:
        if not text:
            return []

        doc = self.nlp(text)
        entities: List[EntityResult] = []
        for ent in doc.ents:
            entity_text = ent.text.strip()
            if not entity_text:
                continue
            entities.append(
                {
                    "text": entity_text,
                    "label": ent.label_,
                    "start_char": int(ent.start_char),
                    "end_char": int(ent.end_char),
                }
            )
        return entities

    def _is_valid_token(self, token: "spacy.tokens.Token") -> bool:
        if token.is_stop or token.is_punct or token.is_space:
            return False
        if token.like_num:
            return False
        text = token.lemma_.strip() or token.text.strip()
        if len(text) < 3:
            return False
        if text.lower() in self._stopwords:
            return False
        if any(char.isdigit() for char in text):
            return False
        return True


_ANALYZER_CACHE: Dict[str, PortugueseSpeechAnalyzer] = {}


def load_portuguese_analyzer(model: Optional[str] = None) -> PortugueseSpeechAnalyzer:
    """Carrega (com cache) um analisador spaCy para português."""

    cache_key = model or "__default__"
    analyzer = _ANALYZER_CACHE.get(cache_key)
    if analyzer is not None:
        return analyzer

    analyzer = PortugueseSpeechAnalyzer(model=model)
    _ANALYZER_CACHE[cache_key] = analyzer
    return analyzer


def analyze_with_chatgpt(
    text: str,
    *,
    keyword_limit: int = 15,
    entity_limit: int = DEFAULT_CHATGPT_ENTITY_LIMIT,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    temperature: float = 0.2,
) -> Tuple[List[KeywordResult], List[EntityResult]]:
    """Executa análise de palavras-chave e entidades via API da OpenAI."""

    if not text:
        return [], []

    if OpenAI is None:
        raise RuntimeError(
            "Dependência 'openai' não instalada. Execute 'pip install openai'."
        )

    resolved_key = api_key or os.getenv("OPENAI_API_KEY")
    if not resolved_key:
        raise RuntimeError(
            "Variável de ambiente OPENAI_API_KEY não configurada para uso do ChatGPT."
        )

    resolved_model = (
        model
        or os.getenv("OPENAI_MODEL")
        or DEFAULT_CHATGPT_MODEL
    )
    resolved_base_url = base_url or os.getenv("OPENAI_BASE_URL")

    client = (
        OpenAI(api_key=resolved_key, base_url=resolved_base_url)
        if resolved_base_url
        else OpenAI(api_key=resolved_key)
    )

    system_prompt = (
        "Você é um assistente de NLP especializado em discursos políticos brasileiros. "
        "Identifique palavras-chave relevantes (lemmas) e entidades nomeadas no texto."
    )
    user_prompt = (
        "Texto do pronunciamento:\n"
        f"{text}\n\n"
        "Retorne um JSON com o formato:\n"
        "{\n"
        '  "keywords": [\n'
        '    {"keyword": "<lemma>", "term": "<forma encontrada>", "frequency": <int>, "rank": <int>}\n'
        "  ],\n"
        '  "entities": [\n'
        '    {"text": "<entidade>", "label": "<tipo>", "start_char": <int|null>, "end_char": <int|null>}\n'
        "  ]\n"
        "}\n\n"
        "Regras:\n"
        f"- Liste no máximo {keyword_limit} palavras-chave ordenadas da mais relevante para a menos relevante.\n"
        f"- Liste no máximo {entity_limit} entidades; use rótulos NER em português (ex.: PESSOA, ORG, LOCAL, EVENTO).\n"
        "- Frequência deve ser um número inteiro (use 0 quando não tiver certeza).\n"
        "- Utilize lemmas em minúsculas na chave 'keyword'.\n"
        "- Utilize escapes válidos para JSON; não inclua comentários.\n"
    )

    raw_content: Optional[str] = None

    if hasattr(client, "responses"):
        response = client.responses.create(
            model=resolved_model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=temperature,
        )
        raw_content = getattr(response, "output_text", None)
        if raw_content is None:
            try:
                segments = []
                for item in getattr(response, "output", []):
                    for content in getattr(item, "content", []) or []:
                        text_segment = getattr(content, "text", None)
                        if text_segment is not None:
                            segments.append(text_segment)
                raw_content = "".join(segments) or None
            except Exception:  # pragma: no cover - defensive
                raw_content = None
    else:
        completion = client.chat.completions.create(
            model=resolved_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
        )
        if completion.choices:
            raw_content = completion.choices[0].message.content

    if not raw_content or not raw_content.strip():
        raise RuntimeError("Resposta vazia do modelo ao tentar analisar o discurso.")

    try:
        payload = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        logger.debug("Resposta do ChatGPT inválida: %s", raw_content)
        raise RuntimeError("Falha ao interpretar JSON retornado pelo ChatGPT.") from exc

    keywords_data = payload.get("keywords") or []
    entities_data = payload.get("entities") or []

    keywords: List[KeywordResult] = []
    for index, item in enumerate(keywords_data, start=1):
        lemma = str(item.get("keyword") or "").strip().lower()
        term = str(item.get("term") or item.get("keyword") or "").strip()
        if not lemma or not term:
            continue

        try:
            frequency = int(item.get("frequency", 0))
        except (TypeError, ValueError):
            frequency = 0

        try:
            rank = int(item.get("rank", index))
        except (TypeError, ValueError):
            rank = index

        keywords.append(
            {
                "keyword": lemma,
                "term": term,
                "frequency": frequency,
                "rank": rank,
            }
        )

    entities: List[EntityResult] = []
    for item in entities_data[:entity_limit]:
        text_value = str(item.get("text") or "").strip()
        label_value = str(item.get("label") or "OUTRO").strip().upper()
        if not text_value:
            continue

        start_char = item.get("start_char")
        end_char = item.get("end_char")
        try:
            start_char_int: Optional[int] = (
                int(start_char) if start_char is not None else None
            )
        except (TypeError, ValueError):
            start_char_int = None
        try:
            end_char_int: Optional[int] = (
                int(end_char) if end_char is not None else None
            )
        except (TypeError, ValueError):
            end_char_int = None

        entities.append(
            {
                "text": text_value,
                "label": label_value or "OUTRO",
                "start_char": start_char_int,
                "end_char": end_char_int,
            }
        )

    return keywords, entities


__all__ = [
    "EntityResult",
    "KeywordResult",
    "PortugueseSpeechAnalyzer",
    "analyze_with_chatgpt",
    "load_portuguese_analyzer",
]
