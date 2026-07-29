"""Funções utilitárias para criação de documentos a partir das notas taquigráficas."""

from __future__ import annotations

from typing import Mapping, Sequence

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

DEFAULT_CHUNK_SIZE = 1200
DEFAULT_CHUNK_OVERLAP = 150
DEFAULT_SEPARATORS = ["\n\n", "\n", ". ", " "]


def create_splitter() -> RecursiveCharacterTextSplitter:
    """Retorna o splitter padrão utilizado na indexação."""

    return RecursiveCharacterTextSplitter(
        chunk_size=DEFAULT_CHUNK_SIZE,
        chunk_overlap=DEFAULT_CHUNK_OVERLAP,
        separators=DEFAULT_SEPARATORS,
    )


def build_documents(
    row: Mapping[str, object],
    splitter: RecursiveCharacterTextSplitter,
) -> list[Document]:
    """Constrói documentos chunkados prontos para inserção no vetor."""

    summary = (row.get("summary") or "").strip()
    speech_text = (row.get("speech_text") or "").strip()
    speech_id = row.get("id")
    parliamentarian_id = row.get("parliamentarian_id")

    if not summary and not speech_text:
        return []

    segments: list[str] = []
    if summary:
        segments.append(f"Resumo:\n{summary}")
    if speech_text:
        segments.append(f"Discurso completo:\n{speech_text}")

    merged_content = "\n\n---\n\n".join(segments)

    row_id = row.get("id")
    source = f"speeches_transcripts:{row_id}"
    party = (row.get("parliamentarian_party") or "").upper() or None
    state = (row.get("parliamentarian_state") or "").upper() or None
    role_type = (row.get("parliamentarian_role") or "").upper() or None

    metadata = {
        "source": source,
        "date": _format_date(row.get("date")),
        "session_number": row.get("session_number"),
        "type": row.get("type"),
        "parliamentarian": row.get("parliamentarian_name"),
        "speech_id": row_id,
        "parliamentarian_id": parliamentarian_id,
    }

    if party:
        metadata["party"] = party
    if state:
        metadata["state"] = state
    if role_type:
        metadata["role"] = role_type

    documents = splitter.create_documents(
        texts=[merged_content],
        metadatas=[metadata],
    )

    # Cada chunk é recuperado isoladamente pela busca vetorial. Sem repetir a
    # identificação em todos eles, um trecho que caia no meio do discurso chega
    # ao LLM sem dizer quem falou — foi assim que perguntas do tipo "o que o
    # parlamentar X diz sobre Y" passaram a não encontrar nada.
    header = _build_speaker_header(row)

    for index, document in enumerate(documents):
        if header:
            document.page_content = f"{header}\n{document.page_content}"
        document.metadata["chunk_index"] = index
        document.metadata["chunk_id"] = f"{source}:{index}"

    return documents


def _build_speaker_header(row: Mapping[str, object]) -> str:
    """Monta a linha de identificação repetida em todos os chunks."""

    name = (str(row.get("parliamentarian_name") or "")).strip()
    if not name:
        return ""

    party = (str(row.get("parliamentarian_party") or "")).strip().upper()
    state = (str(row.get("parliamentarian_state") or "")).strip().upper()
    role = (str(row.get("parliamentarian_role") or "")).strip()

    identification = name
    if party and state:
        identification += f" ({party}-{state})"
    elif party:
        identification += f" ({party})"
    elif state:
        identification += f" ({state})"

    parts = [f"Parlamentar: {identification}"]
    if role:
        parts.append(role.capitalize())

    date = _format_date(row.get("date"))
    if date:
        parts.append(f"Data: {date}")

    return " • ".join(parts)


def _format_date(value: object) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


__all__ = ["create_splitter", "build_documents"]
